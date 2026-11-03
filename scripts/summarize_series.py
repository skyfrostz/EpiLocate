#!/usr/bin/env python3
"""Step 1: audit every header, preserve hashes, and document series selection."""
import argparse
import hashlib
import json
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
import pydicom

from scripts.organize_dicoms import classify_dataset, value_text
from src.data_checks import PROJECT_ROOT, load_config, project_path, read_manifest


def file_hash(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def audit(config):
    out = PROJECT_ROOT / "outputs/data"
    out.mkdir(parents=True, exist_ok=True)
    frame = read_manifest(config["data"]["manifest"])
    raw_paths = {p.relative_to(PROJECT_ROOT).as_posix()
                 for p in (PROJECT_ROOT / "data/raw").rglob("*.dcm")}
    if raw_paths != set(frame.image_path):
        raise ValueError("Manifest/raw file inventory mismatch")
    records, errors, inventory = [], [], []
    rule = config["series_selection"]
    tags = {"patient_id": "PatientID", "study_uid": "StudyInstanceUID",
            "series_uid": "SeriesInstanceUID", "sop_uid": "SOPInstanceUID",
            "modality": "Modality", "series_description": "SeriesDescription"}
    for row in frame.to_dict("records"):
        path = project_path(row["image_path"])
        inventory.append({"image_path": row["image_path"], "sha256": file_hash(path),
                          "bytes": path.stat().st_size})
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                ds = pydicom.dcmread(path, stop_before_pixels=True)
                for column, keyword in tags.items():
                    if row[column] != value_text(ds, keyword):
                        raise ValueError(f"Header differs from manifest: {column}")
                collection, _, warning = classify_dataset(ds)
                if collection != row["collection"]:
                    raise ValueError(f"Collection mismatch: {collection}")
                if warning:
                    raise ValueError(warning)
                image_types = [str(v).upper() for v in getattr(ds, "ImageType", [])]
                orientation = np.asarray(getattr(ds, "ImageOrientationPatient", []), float)
                position = np.asarray(getattr(ds, "ImagePositionPatient", []), float)
                normal = (np.cross(orientation[:3], orientation[3:])
                          if orientation.shape == (6,) else np.full(3, np.nan))
                axial = bool(np.isfinite(normal).all() and
                             np.allclose(np.abs(normal), [0, 0, 1], rtol=0,
                                         atol=rule["axial_normal_tolerance"]))
                kernel = value_text(ds, "ConvolutionKernel")
                thickness = float(getattr(ds, "SliceThickness", "nan"))
                reasons = []
                if row["modality"] != "CT":
                    reasons.append("not_CT")
                if "LOCALIZER" in image_types:
                    reasons.append("localizer")
                if not set(rule["required_image_types"]).issubset(image_types):
                    reasons.append("not_original_primary_axial")
                if not axial:
                    reasons.append("not_axial_geometry")
                if kernel != rule["convolution_kernel"]:
                    reasons.append("kernel_not_STANDARD")
                if not np.isclose(thickness, rule["slice_thickness"]):
                    reasons.append("thickness_not_1.25mm")
                records.append({**row, "image_type": "|".join(image_types),
                    "rows": int(getattr(ds, "Rows", 0)),
                    "columns": int(getattr(ds, "Columns", 0)),
                    "pixel_spacing": value_text(ds, "PixelSpacing"),
                    "slice_thickness": thickness, "convolution_kernel": kernel,
                    "normal": json.dumps(normal.tolist()),
                    "position_z": float(position[2]) if position.shape == (3,) else None,
                    "contrast_agent": value_text(ds, "ContrastBolusAgent"),
                    "selection_reason": ";".join(reasons) or "eligible"})
            for notice in caught:
                errors.append({"image_path": row["image_path"], "error": str(notice.message)})
        except Exception as exc:
            errors.append({"image_path": row["image_path"], "error": f"{type(exc).__name__}: {exc}"})
    pd.DataFrame(errors, columns=["image_path", "error"]).to_csv(out / "header_errors.csv", index=False)
    if errors:
        raise ValueError(f"Header audit raised {len(errors)} issues; see header_errors.csv")
    details = pd.DataFrame(records)
    summaries = []
    for uid, group in details.groupby("series_uid", sort=True):
        summary = {"series_uid": uid, "slice_count": len(group)}
        for field in ("patient_id", "collection", "label", "study_uid", "series_description",
                      "modality", "image_type", "rows", "columns", "pixel_spacing",
                      "slice_thickness", "convolution_kernel", "normal", "contrast_agent"):
            summary[field] = " || ".join(sorted(set(group[field].astype(str))))
        summary["selection_reason"] = ";".join(sorted({
            reason for value in group.selection_reason for reason in value.split(";")
        }))
        summary["selected"] = group.selection_reason.eq("eligible").all()
        summary["position_z_count"] = group.position_z.nunique()
        summaries.append(summary)
    summary = pd.DataFrame(summaries)
    summary.to_csv(out / "series_summary.csv", index=False)
    candidates = summary[summary.selected]
    counts = candidates.groupby("patient_id").size().reindex(frame.patient_id.unique(), fill_value=0)
    if not counts.eq(1).all():
        raise ValueError(f"Ambiguous series selection, candidates per patient: {counts.to_dict()}")
    selected = details[details.series_uid.isin(candidates.series_uid)]
    for uid, group in selected.groupby("series_uid"):
        if group.position_z.isna().any() or group.position_z.duplicated().any():
            raise ValueError(f"Missing/repeated slice positions in selected series {uid}")
    selected.to_csv(project_path(config["data"]["selected_manifest"]), index=False)
    # Preserve the first verified inventory so a later run cannot reset the baseline.
    hashes = pd.DataFrame(inventory).sort_values("image_path").reset_index(drop=True)
    hash_path = out / "source_integrity.csv"
    if hash_path.exists():
        previous = pd.read_csv(hash_path).sort_values("image_path").reset_index(drop=True)
        if not previous.equals(hashes):
            raise ValueError("Source inventory/hash changed since previous audit")
    else:
        hashes.to_csv(hash_path, index=False)
    report = {"dicom_count": len(frame), "patients": frame.patient_id.nunique(),
              "studies": frame.study_uid.nunique(), "series": len(summary),
              "selected_series": len(candidates), "selected_slices": len(selected),
              "excluded_slices": len(frame)-len(selected), "header_errors": 0,
              "label_conflicts": 0, "selection_rule": rule,
              "modalities": frame.modality.value_counts().to_dict()}
    (out / "audit_summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print("Patient counts by collection:")
    print(frame.groupby("collection").patient_id.nunique().to_string())
    print("All series and slice counts (full UID in series_summary.csv):")
    print(summary[["patient_id", "series_description", "slice_count", "selected", "selection_reason"]].to_string(index=False))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/baseline.yaml")
    args = parser.parse_args()
    try:
        audit(load_config(args.config))
    except Exception as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        raise SystemExit(1)
