#!/usr/bin/env python3
"""Step 4: QC for every patient's selected series, with explicit failure reports."""
import argparse
import json
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
from torchvision.models import ResNet18_Weights

from scripts.summarize_series import file_hash
from src.data_checks import PROJECT_ROOT, load_config, project_path, read_manifest
from src.preprocessing import preprocess_dicom


def draw_triplet(axes, stages, caption, center, width):
    if stages is None:
        for axis in axes:
            axis.text(0.5, 0.5, "READ / PREPROCESS ERROR", ha="center", color="red")
            axis.axis("off")
        return
    axes[0].imshow(stages.raw, cmap="gray", vmin=stages.raw.min(), vmax=stages.raw.max())
    axes[1].imshow(stages.windowed, cmap="gray", vmin=center-width/2, vmax=center+width/2)
    # Display the [0,1] resized image, not ImageNet-standardized channels.
    axes[2].imshow(stages.resized[0].numpy(), cmap="gray", vmin=0, vmax=1)
    for axis in axes:
        axis.set_xticks([])
        axis.set_yticks([])
    axes[0].set_ylabel(caption, fontsize=8)


def check_integrity():
    inventory = pd.read_csv(PROJECT_ROOT / "outputs/data/source_integrity.csv")
    actual = {p.relative_to(PROJECT_ROOT).as_posix()
              for p in (PROJECT_ROOT / "data/raw").rglob("*.dcm")}
    changed = []
    if actual != set(inventory.image_path):
        changed.append("raw_inventory_changed")
    for row in inventory.itertuples():
        path = project_path(row.image_path)
        if not path.is_file() or path.stat().st_size != row.bytes or file_hash(path) != row.sha256:
            changed.append(row.image_path)
    return len(inventory), changed


def run_qc(config):
    out = PROJECT_ROOT / "outputs/qc"
    out.mkdir(parents=True, exist_ok=True)
    frame = read_manifest(config["data"]["selected_manifest"])
    if not frame.groupby("patient_id").series_uid.nunique().eq(1).all():
        raise ValueError("QC requires exactly one selected series per patient")
    fractions = np.asarray(config["qc"]["slice_fractions"], float)
    if fractions.size < 2 or not np.isfinite(fractions).all() or ((fractions < 0) | (fractions > 1)).any():
        raise ValueError("QC requires at least two slice fractions within [0,1]")
    center = float(config["preprocessing"]["window_center"])
    width = float(config["preprocessing"]["window_width"])
    image_size = int(config["preprocessing"]["image_size"])
    records, examples = [], {}
    for patient, group in frame.groupby("patient_id", sort=True):
        group = group.copy()
        group["position_z"] = pd.to_numeric(group.position_z, errors="raise")
        group = group.sort_values("position_z")
        if group.position_z.isna().any() or group.position_z.duplicated().any():
            raise ValueError(f"Ambiguous slice position ordering: {patient}")
        indices = sorted(set(round(float(f)*(len(group)-1)) for f in fractions))
        if len(indices) < 2:
            raise ValueError(f"Too few slices for QC: {patient}")
        samples = []
        for rank in indices:
            row = group.iloc[rank]
            record = {"patient_id": patient, "collection": row.collection,
                      "series_uid": row.series_uid, "series_description": row.series_description,
                      "image_path": row.image_path, "rank": rank, "position_z": row.position_z,
                      "flags": "", "warnings": "", "error": ""}
            stages, flags = None, []
            try:
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    stages = preprocess_dicom(project_path(row.image_path), config, return_stages=True)
                record["warnings"] = "; ".join(str(w.message) for w in caught)
                if stages.metadata["PatientID"] != patient or stages.metadata["SeriesInstanceUID"] != row.series_uid:
                    raise ValueError("Header/selected manifest mismatch")
                for name, image in (("raw", stages.raw), ("hu", stages.hu),
                                    ("window", stages.windowed), ("normalized", stages.normalized)):
                    record[f"{name}_min"] = float(image.min())
                    record[f"{name}_max"] = float(image.max())
                record.update(rows=stages.raw.shape[0], columns=stages.raw.shape[1],
                              tensor_shape=str(tuple(stages.tensor.shape)),
                              tensor_min=float(stages.tensor.min()), tensor_max=float(stages.tensor.max()),
                              slope=stages.metadata["slope"], intercept=stages.metadata["intercept"],
                              black_fraction=float((stages.normalized <= 0).mean()),
                              white_fraction=float((stages.normalized >= 1).mean()))
                if not torch.isfinite(stages.tensor).all():
                    flags.append("nonfinite_tensor")
                if stages.tensor.shape != (3, image_size, image_size):
                    flags.append("unexpected_tensor_shape")
                if float(stages.normalized.std()) < 0.001:
                    flags.append("near_constant_grayscale")
                for color in ("black", "white"):
                    if record[f"{color}_fraction"] >= config["qc"]["saturation_fraction"]:
                        flags.append(f"nearly_all_{color}")
                spacing = stages.metadata["pixel_spacing"]
                if len(spacing) != 2 or not np.isfinite(spacing).all() or min(spacing) <= 0:
                    flags.append("invalid_pixel_spacing")
                else:
                    aspect = stages.raw.shape[1]*spacing[1] / (stages.raw.shape[0]*spacing[0])
                    record["physical_aspect_ratio"] = aspect
                    if abs(aspect-1) > config["qc"]["aspect_ratio_tolerance"]:
                        flags.append("square_resize_distorts_aspect")
                if record["warnings"]:
                    flags.append("preprocessing_warning_requires_review")
                print(f"{patient} rank={rank}: HU [{record['hu_min']:g}, {record['hu_max']:g}] "
                      f"Window [{record['window_min']:g}, {record['window_max']:g}] "
                      f"Normalized [{record['normalized_min']:g}, {record['normalized_max']:g}]")
            except Exception as exc:
                record["error"] = f"{type(exc).__name__}: {exc}"
                flags.append("read_or_preprocessing_failed")
                stages = None
                print(f"ERROR: {row.image_path}: {record['error']}", file=sys.stderr)
            record["flags"] = ";".join(flags)
            records.append(record)
            samples.append((record, stages))
        examples[patient] = samples

    metrics = pd.DataFrame(records)
    metrics.to_csv(out / "preprocessing_metrics.csv", index=False)
    inventory_count, changed = check_integrity()
    preset = ResNet18_Weights.DEFAULT.transforms()
    report = {"patients_checked": len(examples), "slices_checked": len(metrics),
              "read_or_preprocessing_errors": int(metrics.error.ne("").sum()),
              "flagged_samples": int(metrics["flags"].ne("").sum()),
              "source_hashes_verified": inventory_count-len(changed), "source_changes": changed,
              "qc_status": "STOP" if metrics["flags"].ne("").any() or changed else "AWAITING_VISUAL_REVIEW",
              "preprocessing": config["preprocessing"], "sampling": "spatial z-order fractions per patient",
              "scope": "Sample QC only, not full-volume or diagnostic validation",
              "imagenet_mean": preset.mean, "imagenet_std": preset.std}
    (out / "qc_summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    titles = ("Raw stored values (auto min/max)", f"HU lung window | C={center:g}, W={width:g}",
              f"{image_size} x {image_size} | [0,1] display")
    for patient, samples in examples.items():
        fig, axes = plt.subplots(len(samples), 3, figsize=(10, 3.2*len(samples)), squeeze=False)
        for i, (record, stages) in enumerate(samples):
            draw_triplet(axes[i], stages, f"Slice rank {record['rank']}\nz={record['position_z']:g} mm", center, width)
        for axis, title in zip(axes[0], titles):
            axis.set_title(title, fontsize=9)
        fig.suptitle(f"{patient}\n{samples[0][0]['series_description']} | spatial sampling", fontsize=11)
        fig.tight_layout(rect=[0, 0, 1, .94])
        fig.savefig(out / f"{patient}.png", dpi=140)
        plt.close(fig)
    classes = {c: sorted(frame.loc[frame.collection.eq(c), "patient_id"].unique())
               for c in ("MIDRC-RICORD-1A", "MIDRC-RICORD-1B")}
    count = max(map(len, classes.values()))
    fig, axes = plt.subplots(count, 6, figsize=(18, 2.85*count), squeeze=False)
    for column, (collection, patients) in enumerate(classes.items()):
        for row in range(count):
            triplet = axes[row, column*3:column*3+3]
            if row >= len(patients):
                for axis in triplet:
                    axis.axis("off")
                continue
            patient = patients[row]
            samples = examples[patient]
            record, stages = samples[len(samples)//2]
            draw_triplet(triplet, stages, f"{collection[-2:]} / {patient.split('-')[-1]}\nrank {record['rank']}", center, width)
        for axis, title in zip(axes[0, column*3:column*3+3], titles):
            axis.set_title(title, fontsize=9)
    fig.suptitle("EpiLocate | Preprocessing QC\n1A (left) and 1B (right) | middle sample per patient", fontsize=16)
    fig.text(.5, .008, "Display stops before ImageNet normalization; model tensors use torchvision ResNet18 weight mean/std. No model predictions.", ha="center", fontsize=10)
    fig.tight_layout(rect=[0, .02, 1, .95])
    fig.savefig(out / "preprocessing_grid.png", dpi=140)
    plt.close(fig)
    print(json.dumps(report, indent=2))
    print("Stopped at Step 4. Review outputs/qc/preprocessing_grid.png before proceeding.")
    return 1 if report["qc_status"] == "STOP" else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/baseline.yaml")
    args = parser.parse_args()
    raise SystemExit(run_qc(load_config(args.config)))
