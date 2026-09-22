#!/usr/bin/env python3
"""Step 7.5: add baseline eligibility without changing patient splits."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd

from src.data_checks import PROJECT_ROOT, load_config, project_path, read_manifest


def counts(frame):
    patients = frame[["patient_id", "label"]].drop_duplicates()
    series = frame[["series_uid", "label"]].drop_duplicates()
    return {
        "patients": int(frame.patient_id.nunique()),
        "series": int(frame.series_uid.nunique()),
        "slices": int(len(frame)),
        "positive_patients": int(patients.label.eq("1").sum()),
        "negative_patients": int(patients.label.eq("0").sum()),
        "positive_series": int(series.label.eq("1").sum()),
        "negative_series": int(series.label.eq("0").sum()),
        "positive_slices": int(frame.label.eq("1").sum()),
        "negative_slices": int(frame.label.eq("0").sum()),
    }


def create_index(config):
    full = read_manifest(config["data"]["manifest"])
    selected = read_manifest(config["data"]["selected_manifest"])
    patient_split = pd.read_csv(PROJECT_ROOT / "data/splits/patient_split.csv", dtype=str)
    if patient_split.patient_id.duplicated().any() or set(patient_split.split) != {"train", "val", "test"}:
        raise ValueError("Invalid fixed patient split")
    if set(patient_split.patient_id) != set(full.patient_id):
        raise ValueError("Fixed patient split does not cover the manifest exactly")

    series_summary = pd.read_csv(PROJECT_ROOT / "outputs/data/series_summary.csv", dtype=str,
                                 keep_default_na=False)
    reason = series_summary[["series_uid", "selection_reason"]].drop_duplicates()
    if reason.series_uid.duplicated().any():
        raise ValueError("Series summary has conflicting eligibility reasons")

    index = full.merge(reason, on="series_uid", how="left", validate="many_to_one")
    if index.selection_reason.eq("").any() or index.selection_reason.isna().any():
        raise ValueError("Missing eligibility reason for one or more series")
    selected_paths = set(selected.image_path)
    index["baseline_eligible"] = index.image_path.isin(selected_paths)
    index["eligibility_reason"] = index.selection_reason.where(
        ~index.baseline_eligible, "eligible_axial_diagnostic_selected_series"
    )
    index = index.drop(columns="selection_reason").merge(
        patient_split[["patient_id", "split"]], on="patient_id", validate="many_to_one"
    )
    index["development_notice"] = "SMOKE / DEVELOPMENT ONLY"

    eligible = index[index.baseline_eligible].copy()
    if set(eligible.image_path) != selected_paths or len(eligible) != len(selected):
        raise ValueError("Eligibility index disagrees with selected manifest")
    expected_by_split = {
        split: set(read_manifest(config["data"][f"{split}_csv"]).image_path)
        for split in ("train", "val", "test")
    }
    for split, expected in expected_by_split.items():
        actual = set(eligible.loc[eligible.split.eq(split), "image_path"])
        if actual != expected:
            raise ValueError(f"Eligibility index disagrees with fixed {split} split")
    patient_splits = index.groupby("patient_id").split.nunique()
    if not patient_splits.eq(1).all():
        raise ValueError("Patient leakage detected inside eligibility index")
    groups = {name: set(index.loc[index.split.eq(name), "patient_id"])
              for name in ("train", "val", "test")}
    if any(groups[a] & groups[b] for a, b in (("train", "val"), ("train", "test"), ("val", "test"))):
        raise ValueError("Patient leakage detected across fixed splits")

    output = project_path(config["data"]["eligibility_index"])
    output.parent.mkdir(parents=True, exist_ok=True)
    index.sort_values(["patient_id", "series_uid", "instance_number", "image_path"]).to_csv(
        output, index=False, lineterminator="\n"
    )
    report = {
        "notice": "SMOKE / DEVELOPMENT ONLY",
        "before_filter": counts(index),
        "after_filter": counts(eligible),
        "excluded": counts(index[~index.baseline_eligible]),
        "patient_leakage": 0,
        "split_assignment_changed": False,
        "eligibility_index": output.relative_to(PROJECT_ROOT).as_posix(),
    }
    report_path = output.with_suffix(".summary.json")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/baseline.yaml")
    args = parser.parse_args()
    try:
        create_index(load_config(args.config))
    except Exception as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        raise SystemExit(1)
