#!/usr/bin/env python3
"""Step 2: deterministic patient-stratified splits; never randomize slices."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from src.data_checks import PROJECT_ROOT, load_config, project_path, read_manifest

SPLITS = ("train", "val", "test")


def allocation(n, settings):
    if settings["mode"] == "smoke":
        counts = np.asarray(settings["counts_per_class"], dtype=int)
        if counts.shape != (3,) or (counts <= 0).any() or counts.sum() != n:
            raise ValueError(f"Smoke split requires exactly {counts.tolist()} patients per class; got {n}")
        return counts
    ratios = np.asarray(settings["ratios"], dtype=float)
    if ratios.shape != (3,) or not np.isfinite(ratios).all() or (ratios <= 0).any() or not np.isclose(ratios.sum(), 1):
        raise ValueError("Ratios must be three positive finite values summing to 1")
    exact = ratios * n
    counts = np.floor(exact).astype(int)
    order = np.argsort(-(exact - counts), kind="stable")
    counts[order[:n-int(counts.sum())]] += 1
    if (counts == 0).any():
        raise ValueError("Too few patients for these ratios: each class/split needs a patient")
    return counts


def build_patient_split(frame, settings, seed):
    patients = frame[["patient_id", "collection", "label"]].drop_duplicates().sort_values("patient_id")
    if patients.patient_id.duplicated().any():
        raise ValueError("Patient label conflict")
    rng = np.random.default_rng(seed)
    assignments = []
    for label, group in patients.groupby("label", sort=True):
        shuffled = rng.permutation(group.patient_id.to_numpy())
        start = 0
        for split, count in zip(SPLITS, allocation(len(group), settings)):
            assignments.extend({"patient_id": p, "split": split} for p in shuffled[start:start+count])
            start += count
    result = patients.merge(pd.DataFrame(assignments), on="patient_id", validate="one_to_one")
    groups = {s: set(result.loc[result.split.eq(s), "patient_id"]) for s in SPLITS}
    assert not (groups["train"] & groups["val"]), "Patient leakage: train/val"
    assert not (groups["train"] & groups["test"]), "Patient leakage: train/test"
    assert not (groups["val"] & groups["test"]), "Patient leakage: val/test"
    assert set.union(*groups.values()) == set(patients.patient_id)
    return result.sort_values("patient_id").reset_index(drop=True)


def create_splits(config):
    full = read_manifest(config["data"]["manifest"])
    selected = read_manifest(config["data"]["selected_manifest"])
    if set(full.patient_id) != set(selected.patient_id):
        raise ValueError("Series selection excluded a patient; review before splitting")
    expected = full.set_index("image_path")
    for row in selected.itertuples():
        for column in ("patient_id", "collection", "label", "study_uid", "series_uid", "sop_uid"):
            if expected.loc[row.image_path, column] != getattr(row, column):
                raise ValueError("Selected manifest disagrees with source manifest")
    assignment = build_patient_split(full, config["splits"], config["seed"])
    all_slices = full.merge(assignment[["patient_id", "split"]], on="patient_id", validate="many_to_one")
    selected_slices = selected.merge(assignment[["patient_id", "split"]], on="patient_id", validate="many_to_one")
    assert all_slices.groupby("patient_id").split.nunique().eq(1).all()
    assert selected_slices.groupby("patient_id").split.nunique().eq(1).all()
    assert len(all_slices) == len(full) and len(selected_slices) == len(selected)
    # All original slices receive a split, even if their series is excluded from the baseline.
    outputs = {PROJECT_ROOT / "data/splits/patient_split.csv": assignment,
               PROJECT_ROOT / "data/splits/all_slice_assignments.csv": all_slices}
    for split in SPLITS:
        outputs[project_path(config["data"][f"{split}_csv"])] = selected_slices[selected_slices.split.eq(split)].sort_values("image_path")
    # Never silently replace an established split with a different assignment or seed.
    serialized = {path: frame.to_csv(index=False, lineterminator="\n") for path, frame in outputs.items()}
    for path, content in serialized.items():
        if path.exists() and path.read_text(encoding="utf-8") != content:
            raise ValueError(f"Existing split differs: {path.relative_to(PROJECT_ROOT)}; preserve/review it first")
    for path, content in serialized.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    for split in SPLITS:
        group = assignment[assignment.split.eq(split)]
        print(f"{split.title()} patients: {len(group)}")
        print(f"{split.title()} positive / negative: {(group.label == '1').sum()} / {(group.label == '0').sum()}")
        print(f"{split.title()} slices: {(selected_slices.split == split).sum()} selected; {(all_slices.split == split).sum()} total")
    print("Patient leakage: 0")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/baseline.yaml")
    parser.add_argument("--mode", choices=["smoke", "ratios"])
    parser.add_argument("--ratios", type=float, nargs=3, metavar=("TRAIN", "VAL", "TEST"))
    args = parser.parse_args()
    config = load_config(args.config)
    if args.mode:
        config["splits"]["mode"] = args.mode
    if args.ratios:
        config["splits"]["mode"] = "ratios"
        config["splits"]["ratios"] = args.ratios
    try:
        create_splits(config)
    except Exception as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        raise SystemExit(1)
