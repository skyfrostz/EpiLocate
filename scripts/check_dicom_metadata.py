#!/usr/bin/env python3
"""Read-only pixel-interpretation and sequence audit; never select/filter slices."""
import argparse
from collections import Counter
import json
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
import pydicom

from scripts.organize_dicoms import classify_dataset, value_text
from scripts.summarize_series import file_hash
from src.data_checks import PROJECT_ROOT, load_config, project_path, read_manifest


def numeric_metadata(ds, key):
    value = value_text(ds, key)
    if not value:
        return None, "missing"
    try:
        number = float(value)
    except ValueError:
        return None, "invalid"
    return (number, "ok") if np.isfinite(number) else (None, "nonfinite")


def distribution(records, keyword):
    values = [r[keyword] for r in records if r[f"{keyword}_status"] == "ok"]
    return {"value_counts": dict(Counter(str(v) for v in values)),
            "missing": sum(r[f"{keyword}_status"] == "missing" for r in records),
            "invalid_or_nonfinite": sum(r[f"{keyword}_status"] in ("invalid", "nonfinite") for r in records),
            "min": min(values) if values else None, "max": max(values) if values else None}


def dimension_flags(group):
    flags = []
    if group["rows"].nunique() > 1 or group["columns"].nunique() > 1:
        flags.append("variable_dimensions")
    if any(not value.isdigit() or int(value) <= 1 for value in [*group["rows"], *group["columns"]]):
        flags.append("invalid_dimensions")
    return flags


def check(config):
    out = PROJECT_ROOT / "outputs/data"
    out.mkdir(parents=True, exist_ok=True)
    full = read_manifest(config["data"]["manifest"])
    selected = read_manifest(config["data"]["selected_manifest"])
    selected_series = set(selected.series_uid)
    raw_files = sorted((PROJECT_ROOT / "data/raw").rglob("*.dcm"))
    if {p.relative_to(PROJECT_ROOT).as_posix() for p in raw_files} != set(full.image_path):
        raise ValueError("Raw DICOM inventory and full manifest differ")
    protected_paths = [project_path(config["data"]["manifest"]),
                       project_path(config["data"]["selected_manifest"]),
                       *(PROJECT_ROOT / "data/splits").glob("*.csv")]
    protected = {path: file_hash(path) for path in protected_paths}
    expected = full.set_index("image_path")
    records, issues = [], []
    for path in raw_files:
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        row = expected.loc[rel]
        try:
            with warnings.catch_warnings(record=True) as notices:
                warnings.simplefilter("always")
                ds = pydicom.dcmread(path, stop_before_pixels=True)
                for field, keyword in (("patient_id", "PatientID"), ("study_uid", "StudyInstanceUID"),
                                       ("series_uid", "SeriesInstanceUID"), ("sop_uid", "SOPInstanceUID")):
                    if value_text(ds, keyword) != row[field]:
                        raise ValueError(f"Header/manifest mismatch: {field}")
                collection, _, warning = classify_dataset(ds)
                if warning or collection != row.collection:
                    raise ValueError(f"Collection mismatch/uncertainty: {collection}; {warning}")
                types = [str(v).upper() for v in getattr(ds, "ImageType", [])]
                orient = np.asarray(getattr(ds, "ImageOrientationPatient", []), dtype=float)
                normal = np.cross(orient[:3], orient[3:]) if orient.shape == (6,) else np.full(3, np.nan)
                axial = bool(np.isfinite(normal).all() and np.allclose(abs(normal), [0, 0, 1], atol=.01, rtol=0))
                record = {"image_path": rel, "series_uid": value_text(ds, "SeriesInstanceUID"),
                          "patient_id": value_text(ds, "PatientID"), "collection": collection,
                          "modality": value_text(ds, "Modality"),
                          "series_description": value_text(ds, "SeriesDescription"),
                          "rows": value_text(ds, "Rows"), "columns": value_text(ds, "Columns"),
                          "photometric_interpretation": value_text(ds, "PhotometricInterpretation"),
                          "localizer": "LOCALIZER" in types or any(s in value_text(ds, "SeriesDescription").upper() for s in ("SCOUT", "LOCALIZER")),
                          "non_axial": not axial,
                          "reformatted": "REFORMATTED" in types,
                          "selected_previously": row.series_uid in selected_series}
                for keyword in ("RescaleSlope", "RescaleIntercept", "InstanceNumber"):
                    record[keyword], record[f"{keyword}_status"] = numeric_metadata(ds, keyword)
                records.append(record)
            for notice in notices:
                issues.append({"image_path": rel, "kind": "header_warning", "detail": str(notice.message)})
        except Exception as exc:
            issues.append({"image_path": rel, "kind": "read_or_header_error", "detail": f"{type(exc).__name__}: {exc}"})
    detail = pd.DataFrame(records)
    detail.to_csv(out / "metadata_per_slice.csv", index=False)
    pd.DataFrame(issues, columns=["image_path", "kind", "detail"]).to_csv(out / "metadata_read_issues.csv", index=False)
    summaries, blockers = [], []
    if issues:
        blockers.append(f"{len(issues)} header reading issues; see metadata_read_issues.csv")
    for uid, group in detail.groupby("series_uid", sort=True):
        numbers = group.loc[group.InstanceNumber_status.eq("ok"), "InstanceNumber"]
        duplicates = numbers[numbers.duplicated(keep=False)]
        valid_integer = bool((numbers % 1 == 0).all())
        gap_count = int(numbers.max()-numbers.min()+1-numbers.nunique()) if len(numbers) and valid_integer else None
        flags = []
        if group.localizer.any():
            flags.append("suspected_localizer_scout")
        if group.non_axial.any():
            flags.append("non_axial_geometry")
        if group.reformatted.any():
            flags.append("reformatted_series")
        if group.photometric_interpretation.ne("MONOCHROME2").any():
            flags.append("unsupported_or_missing_photometric_interpretation")
        if group.modality.ne("CT").any():
            flags.append("non_CT_modality")
        if len(duplicates):
            flags.append("duplicate_instance_numbers")
        if group.InstanceNumber_status.ne("ok").any() or not valid_integer:
            flags.append("missing_invalid_instance_numbers")
        if gap_count:
            flags.append("instance_number_gaps")
        for keyword in ("RescaleSlope", "RescaleIntercept"):
            if group[f"{keyword}_status"].ne("ok").any():
                flags.append(f"missing_invalid_{keyword}")
            if group[keyword].nunique() > 1:
                flags.append(f"variable_{keyword}")
        if group.RescaleSlope.le(0).any():
            flags.append("nonpositive_slope")
        flags.extend(dimension_flags(group))
        summary = {"series_uid": uid, "slice_count": len(group),
                   "instance_number_missing": int(group.InstanceNumber_status.eq("missing").sum()),
                   "instance_number_invalid": int(group.InstanceNumber_status.isin(["invalid", "nonfinite"]).sum()) + int((numbers % 1 != 0).sum()),
                   "instance_number_min": float(numbers.min()) if len(numbers) else None,
                   "instance_number_max": float(numbers.max()) if len(numbers) else None,
                   "duplicate_instance_number_values": json.dumps(sorted(set(duplicates))),
                   "duplicate_instance_number_rows": len(duplicates),
                   "instance_number_gap_count": gap_count, "audit_flags": ";".join(flags),
                   "selected_previously": uid in selected_series}
        for field in ("collection", "patient_id", "modality", "series_description", "rows", "columns", "photometric_interpretation"):
            summary[field] = " || ".join(sorted(set(group[field])))
        summaries.append(summary)
        if uid in selected_series and flags:
            blockers.append(f"Selected series {uid}: {';'.join(flags)}")
    summary = pd.DataFrame(summaries)
    previous = out / "series_summary.csv"
    if previous.exists():
        old = pd.read_csv(previous, dtype=str, keep_default_na=False)
        if old.series_uid.duplicated().any():
            raise ValueError("Previous summary has duplicate series UID")
        extras = [c for c in old.columns if c not in summary.columns]
        summary = summary.merge(old[["series_uid", *extras]], on="series_uid", how="left", validate="one_to_one")
    summary.to_csv(previous, index=False)
    hashes = pd.read_csv(out / "source_integrity.csv")
    changed = [r.image_path for r in hashes.itertuples() if file_hash(project_path(r.image_path)) != r.sha256]
    if changed:
        blockers.append(f"{len(changed)} original DICOM hashes changed")
    for path, digest in protected.items():
        if file_hash(path) != digest:
            blockers.append(f"Manifest/split changed: {path}")
    report = {"files": len(raw_files), "series": len(summary), "header_issues": issues,
              "photometric_interpretation": detail.photometric_interpretation.value_counts().to_dict(),
              "rescale_slope": distribution(records, "RescaleSlope"),
              "rescale_intercept": distribution(records, "RescaleIntercept"),
              "series_with_duplicate_instance_numbers": int(summary.duplicate_instance_number_rows.gt(0).sum()),
              "missing_instance_numbers": int(summary.instance_number_missing.sum()),
              "invalid_instance_numbers": int(summary.instance_number_invalid.sum()),
              "series_with_number_gaps": int(summary.instance_number_gap_count.gt(0).sum()),
              "flagged_series": int(summary.audit_flags.ne("").sum()),
              "localizer_series": int(detail.groupby("series_uid").localizer.any().sum()),
              "non_axial_series": int(detail.groupby("series_uid").non_axial.any().sum()),
              "reformatted_series": int(detail.groupby("series_uid").reformatted.any().sum()),
              "source_hashes_verified": len(hashes)-len(changed), "source_changes": changed,
              "manifests_and_splits_unchanged": all(file_hash(p) == digest for p, digest in protected.items()),
              "blockers": blockers, "status": "STOP" if blockers else "PASS",
              "policy": "Report only; no new selection, filtering, pixel writes or file moves"}
    (out / "metadata_audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if len(summary[summary.audit_flags.ne("")]):
        print(summary.loc[summary.audit_flags.ne(""), ["patient_id", "series_description", "slice_count", "selected_previously", "audit_flags"]].to_string(index=False))
    return 1 if blockers else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/baseline.yaml")
    args = parser.parse_args()
    raise SystemExit(check(load_config(args.config)))
