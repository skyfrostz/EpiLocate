#!/usr/bin/env python3
"""Inspect organized DICOM headers and report dataset-level consistency."""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import pydicom


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = PROJECT_ROOT / "data" / "raw"
COLLECTION_1A = "MIDRC-RICORD-1A"
COLLECTION_1B = "MIDRC-RICORD-1B"
UNKNOWN = "UNKNOWN"
KNOWN_COLLECTIONS = {COLLECTION_1A, COLLECTION_1B, UNKNOWN}


def value_text(dataset: Any, keyword: str) -> str:
    value = getattr(dataset, keyword, "")
    return "" if value is None else str(value).strip()


def collection_from_path(path: Path) -> str:
    try:
        collection = path.relative_to(RAW_ROOT).parts[0]
    except (ValueError, IndexError):
        return UNKNOWN
    return collection if collection in KNOWN_COLLECTIONS else UNKNOWN


def print_header(path: Path, dataset: Any) -> None:
    print(f"File: {path.relative_to(PROJECT_ROOT).as_posix()}")
    for keyword in (
        "PatientID",
        "StudyInstanceUID",
        "SeriesInstanceUID",
        "SOPInstanceUID",
        "InstanceNumber",
        "Modality",
        "SeriesDescription",
        "Rows",
        "Columns",
        "RescaleSlope",
        "RescaleIntercept",
    ):
        print(f"{keyword}: {value_text(dataset, keyword)}")
    print()


def main() -> int:
    files = sorted(RAW_ROOT.rglob("*.dcm"), key=lambda path: path.as_posix())
    if not files:
        print(f"ERROR: no DICOM files found under {RAW_ROOT}", file=sys.stderr)
        return 1

    patients: set[str] = set()
    studies: set[str] = set()
    series: set[str] = set()
    patients_by_collection: dict[str, set[str]] = defaultdict(set)
    patient_collections: dict[str, set[str]] = defaultdict(set)
    read_errors: list[tuple[Path, str]] = []
    path_header_mismatches: list[tuple[Path, str, str]] = []
    printable: list[tuple[Path, Any]] = []

    for path in files:
        collection = collection_from_path(path)
        try:
            dataset = pydicom.dcmread(path, stop_before_pixels=True)
        except Exception as exc:
            read_errors.append((path, f"{type(exc).__name__}: {exc}"))
            continue

        if len(printable) < 10:
            printable.append((path, dataset))

        patient_id = value_text(dataset, "PatientID") or path.parent.name
        study_uid = value_text(dataset, "StudyInstanceUID")
        series_uid = value_text(dataset, "SeriesInstanceUID")
        patients.add(patient_id)
        if study_uid:
            studies.add(study_uid)
        if series_uid:
            series.add(series_uid)
        patients_by_collection[collection].add(patient_id)
        patient_collections[patient_id].add(collection)

        upper_patient_id = patient_id.upper()
        expected = (
            COLLECTION_1A
            if upper_patient_id.startswith(f"{COLLECTION_1A}-")
            else COLLECTION_1B
            if upper_patient_id.startswith(f"{COLLECTION_1B}-")
            else UNKNOWN
        )
        if expected != collection:
            path_header_mismatches.append((path, collection, expected))

    print("First 10 readable DICOM headers")
    print("=" * 72)
    for path, dataset in printable:
        print_header(path, dataset)

    conflicts = {
        patient_id: collections
        for patient_id, collections in patient_collections.items()
        if COLLECTION_1A in collections and COLLECTION_1B in collections
    }

    print("Dataset summary")
    print("=" * 72)
    print(f"Patients: {len(patients)}")
    print(f"Studies: {len(studies)}")
    print(f"Series: {len(series)}")
    print(f"DICOM files: {len(files)}")
    print(f"1A patients: {len(patients_by_collection[COLLECTION_1A])}")
    print(f"1B patients: {len(patients_by_collection[COLLECTION_1B])}")
    print(f"Unknown patients: {len(patients_by_collection[UNKNOWN])}")
    print(f"Read errors: {len(read_errors)}")
    print(f"Patient label conflicts: {len(conflicts)}")
    print(f"Path/header collection mismatches: {len(path_header_mismatches)}")

    for patient_id, collections in sorted(conflicts.items()):
        print(
            f"ERROR: patient {patient_id} appears in both 1A and 1B: "
            f"{sorted(collections)}",
            file=sys.stderr,
        )
    for path, path_collection, header_collection in path_header_mismatches[:20]:
        print(
            f"ERROR: {path.relative_to(PROJECT_ROOT)} is under {path_collection} "
            f"but PatientID indicates {header_collection}",
            file=sys.stderr,
        )
    for path, error in read_errors[:20]:
        print(f"WARNING: cannot read {path.relative_to(PROJECT_ROOT)}: {error}", file=sys.stderr)

    return 2 if conflicts or path_header_mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
