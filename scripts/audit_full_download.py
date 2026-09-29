#!/usr/bin/env python3
"""Audit the completed full IDC download without loading pixel data."""
import argparse
import csv
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pydicom

from src.data_checks import PROJECT_ROOT


COLLECTIONS = {
    "midrc_ricord_1a": "MIDRC-RICORD-1A",
    "midrc_ricord_1b": "MIDRC-RICORD-1B",
}


def audit(root):
    all_files = [path for path in root.rglob("*") if path.is_file()]
    dicom_files = sorted(path for path in all_files if path.suffix.lower() == ".dcm")
    grouped = {
        key: {"patients": set(), "studies": set(), "series": set(), "dicom_files": 0,
              "read_errors": 0, "read_error_details": []}
        for key in COLLECTIONS
    }
    patient_collections = {}
    full_sop_uids = set()
    development_manifest = PROJECT_ROOT / "data/data_manifest.csv"
    development_sop_uids = set()
    if development_manifest.is_file():
        with development_manifest.open(newline="", encoding="utf-8") as handle:
            development_sop_uids = {
                row["sop_uid"] for row in csv.DictReader(handle) if row.get("sop_uid")
            }
    for path in dicom_files:
        relative = path.relative_to(root)
        collection_key = relative.parts[0] if relative.parts else "unknown"
        record = grouped.setdefault(collection_key, {
            "patients": set(), "studies": set(), "series": set(), "dicom_files": 0,
            "read_errors": 0, "read_error_details": []
        })
        record["dicom_files"] += 1
        try:
            ds = pydicom.dcmread(path, stop_before_pixels=True, force=False)
            patient = str(getattr(ds, "PatientID", "") or "")
            study = str(getattr(ds, "StudyInstanceUID", "") or "")
            series = str(getattr(ds, "SeriesInstanceUID", "") or "")
            if patient:
                record["patients"].add(patient)
                patient_collections.setdefault(patient, set()).add(collection_key)
            if study:
                record["studies"].add(study)
            if series:
                record["series"].add(series)
            if str(getattr(ds, "SOPInstanceUID", "") or ""):
                full_sop_uids.add(str(ds.SOPInstanceUID))
        except Exception as exc:
            record["read_errors"] += 1
            record["read_error_details"].append({
                "image_path": path.relative_to(PROJECT_ROOT).as_posix(),
                "error": f"{type(exc).__name__}: {exc}",
            })

    def serialize(key, record):
        return {
            "collection": COLLECTIONS.get(key, key),
            "idc_collection_id": key,
            "patients": len(record["patients"]),
            "studies": len(record["studies"]),
            "series": len(record["series"]),
            "dicom_files": record["dicom_files"],
            "read_errors": record["read_errors"],
            "read_error_details": record["read_error_details"],
        }

    usage = shutil.disk_usage(PROJECT_ROOT)
    conflicts = sorted(
        {patient: sorted(collections) for patient, collections in patient_collections.items()
         if len(collections) > 1}.items()
    )
    result = {
        "audit_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "notice": "FULL DOWNLOAD INTEGRITY AUDIT",
        "download_directory": root.relative_to(PROJECT_ROOT).as_posix(),
        "all_files": len(all_files),
        "dicom_files": len(dicom_files),
        "collection_1a": serialize("midrc_ricord_1a", grouped["midrc_ricord_1a"]),
        "collection_1b": serialize("midrc_ricord_1b", grouped["midrc_ricord_1b"]),
        "patient_id_conflicts": [
            {"patient_id": patient, "collection_ids": collections}
            for patient, collections in conflicts
        ],
        "patient_id_conflict_count": len(conflicts),
        "development_dataset_overlap": {
            "development_manifest_dicom_files": len(development_sop_uids),
            "sop_uid_overlap": len(development_sop_uids & full_sop_uids),
            "development_sop_uids_missing_from_full_download": len(
                development_sop_uids - full_sop_uids
            ),
            "note": "Expected content overlap because full_raw is a separate untouched copy of the full collections.",
        },
        "total_read_errors": sum(record["read_errors"] for record in grouped.values()),
        "disk": {
            "full_raw_bytes": sum(path.stat().st_size for path in dicom_files),
            "disk_total_bytes": usage.total,
            "disk_used_bytes": usage.used,
            "disk_free_bytes": usage.free,
        },
    }
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download-dir", default="data/full_raw")
    parser.add_argument("--output", default="outputs/data/full_download_report.json")
    args = parser.parse_args()
    root = PROJECT_ROOT / args.download_dir
    output = PROJECT_ROOT / args.output
    if not root.is_dir():
        raise SystemExit(f"Missing download directory: {root}")
    report = audit(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "all_files": report["all_files"],
        "dicom_files": report["dicom_files"],
        "collection_1a": report["collection_1a"],
        "collection_1b": report["collection_1b"],
        "total_read_errors": report["total_read_errors"],
        "patient_id_conflict_count": report["patient_id_conflict_count"],
    }, indent=2, ensure_ascii=False))
