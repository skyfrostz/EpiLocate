#!/usr/bin/env python3
"""Safely organize root-level DICOM files and build a slice manifest."""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pydicom


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT / "data"
RAW_ROOT = DATA_ROOT / "raw"
MANIFEST_PATH = DATA_ROOT / "data_manifest.csv"
LOG_PATH = DATA_ROOT / "organize_log.csv"

COLLECTION_1A = "MIDRC-RICORD-1A"
COLLECTION_1B = "MIDRC-RICORD-1B"
UNKNOWN = "UNKNOWN"
COLLECTIONS = (COLLECTION_1A, COLLECTION_1B, UNKNOWN)
PRIVATE_COLLECTION_TAG = (0x0013, 0x1010)

MANIFEST_FIELDS = (
    "patient_id",
    "collection",
    "study_uid",
    "series_uid",
    "sop_uid",
    "instance_number",
    "modality",
    "series_description",
    "image_path",
    "label",
    "read_error",
)


@dataclass
class DicomPlan:
    source: Path
    target: Path
    patient_id: str = ""
    collection: str = UNKNOWN
    study_uid: str = ""
    series_uid: str = ""
    sop_uid: str = ""
    instance_number: str = ""
    modality: str = ""
    series_description: str = ""
    classification_source: str = ""
    warning: str = ""
    read_error: str = ""


def value_text(dataset: Any, keyword: str) -> str:
    value = getattr(dataset, keyword, "")
    return "" if value is None else str(value).strip()


def private_collection_text(dataset: Any) -> str:
    element = dataset.get(PRIVATE_COLLECTION_TAG)
    return "" if element is None else str(element.value).strip()


def collection_from_value(value: str) -> str | None:
    normalized = value.strip().upper().replace("_", "-")
    if normalized == COLLECTION_1A or normalized.startswith(f"{COLLECTION_1A}-"):
        return COLLECTION_1A
    if normalized == COLLECTION_1B or normalized.startswith(f"{COLLECTION_1B}-"):
        return COLLECTION_1B
    return None


def classify_dataset(dataset: Any) -> tuple[str, str, str]:
    """Return collection, evidence source, and an optional warning."""
    evidence = {
        "PatientID": collection_from_value(value_text(dataset, "PatientID")),
        "PatientName": collection_from_value(value_text(dataset, "PatientName")),
        "PrivateTag(0013,1010)": collection_from_value(
            private_collection_text(dataset)
        ),
    }
    recognized = {value for value in evidence.values() if value is not None}
    if len(recognized) > 1:
        details = ", ".join(
            f"{source}={collection}"
            for source, collection in evidence.items()
            if collection is not None
        )
        return UNKNOWN, "conflicting_metadata", f"collection conflict: {details}"

    patient_collection = evidence["PatientID"]
    if patient_collection is not None:
        corroborating = ",".join(
            source
            for source, collection in evidence.items()
            if collection == patient_collection
        )
        return patient_collection, corroborating, ""

    if len(recognized) == 1:
        collection = recognized.pop()
        sources = ",".join(
            source for source, value in evidence.items() if value == collection
        )
        return collection, sources, "PatientID did not identify the collection"

    return UNKNOWN, "unrecognized_metadata", "collection could not be identified"


def safe_directory_name(value: str, fallback: str = "unknown") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    cleaned = cleaned.strip("._")[:180]
    return cleaned or fallback


def read_plan(source: Path) -> DicomPlan:
    try:
        dataset = pydicom.dcmread(source, stop_before_pixels=True)
        patient_id = value_text(dataset, "PatientID")
        collection, classification_source, warning = classify_dataset(dataset)
        patient_directory = safe_directory_name(patient_id)
        target = RAW_ROOT / collection / patient_directory / source.name
        return DicomPlan(
            source=source,
            target=target,
            patient_id=patient_id,
            collection=collection,
            study_uid=value_text(dataset, "StudyInstanceUID"),
            series_uid=value_text(dataset, "SeriesInstanceUID"),
            sop_uid=value_text(dataset, "SOPInstanceUID"),
            instance_number=value_text(dataset, "InstanceNumber"),
            modality=value_text(dataset, "Modality"),
            series_description=value_text(dataset, "SeriesDescription"),
            classification_source=classification_source,
            warning=warning,
        )
    except Exception as exc:  # Keep unreadable source files safe and visible.
        message = f"{type(exc).__name__}: {exc}"
        return DicomPlan(
            source=source,
            target=RAW_ROOT / UNKNOWN / "read_errors" / source.name,
            warning="DICOM header read failed",
            read_error=message,
        )


def scan_root_dicoms() -> list[DicomPlan]:
    sources = sorted(PROJECT_ROOT.glob("*.dcm"), key=lambda path: path.name)
    return [read_plan(source) for source in sources]


def print_scan_summary(plans: list[DicomPlan]) -> None:
    counts = Counter(plan.collection for plan in plans)
    patients: dict[str, set[str]] = defaultdict(set)
    for plan in plans:
        if plan.patient_id:
            patients[plan.collection].add(plan.patient_id)

    print(f"Found {len(plans)} root-level DICOM files")
    print(f"{COLLECTION_1A}: {counts[COLLECTION_1A]} DICOM, {len(patients[COLLECTION_1A])} patients")
    print(f"{COLLECTION_1B}: {counts[COLLECTION_1B]} DICOM, {len(patients[COLLECTION_1B])} patients")
    print(f"Unknown: {counts[UNKNOWN]}")
    print(f"Read errors: {sum(bool(plan.read_error) for plan in plans)}")

    warnings = [plan for plan in plans if plan.warning]
    for plan in warnings[:20]:
        print(f"WARNING: {plan.source.name}: {plan.warning}", file=sys.stderr)
        if plan.read_error:
            print(f"         {plan.read_error}", file=sys.stderr)
    if len(warnings) > 20:
        print(f"WARNING: {len(warnings) - 20} additional warnings omitted", file=sys.stderr)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def preflight_collisions(plans: list[DicomPlan]) -> tuple[list[DicomPlan], list[DicomPlan]]:
    identical: list[DicomPlan] = []
    conflicting: list[DicomPlan] = []
    destinations: dict[Path, Path] = {}

    for plan in plans:
        prior_source = destinations.get(plan.target)
        if prior_source is not None and prior_source != plan.source:
            conflicting.append(plan)
            continue
        destinations[plan.target] = plan.source

        if not plan.target.exists():
            continue
        try:
            is_identical = (
                plan.source.stat().st_size == plan.target.stat().st_size
                and sha256(plan.source) == sha256(plan.target)
            )
        except OSError:
            is_identical = False
        if is_identical:
            identical.append(plan)
        else:
            conflicting.append(plan)

    return identical, conflicting


def safe_move_without_overwrite(source: Path, target: Path) -> None:
    """Move within the project filesystem without an overwrite race."""
    target.parent.mkdir(parents=True, exist_ok=True)
    os.link(source, target)
    try:
        source.unlink()
    except Exception:
        try:
            target.unlink()
        except OSError:
            pass
        raise


def write_operation_log(rows: list[dict[str, str]]) -> None:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    temporary = LOG_PATH.with_suffix(".csv.tmp")
    fields = ("action", "source", "target", "collection", "patient_id", "detail")
    with temporary.open("w", newline="", encoding="utf-8") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(LOG_PATH)


def move_plans(plans: list[DicomPlan], identical: list[DicomPlan]) -> int:
    identical_sources = {plan.source for plan in identical}
    log_rows: list[dict[str, str]] = []
    moved = 0

    for plan in plans:
        relative_source = plan.source.relative_to(PROJECT_ROOT).as_posix()
        relative_target = plan.target.relative_to(PROJECT_ROOT).as_posix()
        if plan.source in identical_sources:
            print(
                f"WARNING: identical target already exists; source retained: {relative_source}",
                file=sys.stderr,
            )
            log_rows.append(
                {
                    "action": "retained_identical_source",
                    "source": relative_source,
                    "target": relative_target,
                    "collection": plan.collection,
                    "patient_id": plan.patient_id,
                    "detail": "target content confirmed identical",
                }
            )
            continue

        try:
            safe_move_without_overwrite(plan.source, plan.target)
            moved += 1
            log_rows.append(
                {
                    "action": "moved",
                    "source": relative_source,
                    "target": relative_target,
                    "collection": plan.collection,
                    "patient_id": plan.patient_id,
                    "detail": plan.read_error or plan.warning,
                }
            )
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            log_rows.append(
                {
                    "action": "move_failed",
                    "source": relative_source,
                    "target": relative_target,
                    "collection": plan.collection,
                    "patient_id": plan.patient_id,
                    "detail": detail,
                }
            )
            write_operation_log(log_rows)
            raise RuntimeError(
                f"move failed for {relative_source}; no overwrite was performed: {detail}"
            ) from exc

    if log_rows or not LOG_PATH.exists():
        write_operation_log(log_rows)
    return moved


def collection_from_organized_path(path: Path) -> str:
    try:
        top_directory = path.relative_to(RAW_ROOT).parts[0]
    except (ValueError, IndexError):
        return UNKNOWN
    return top_directory if top_directory in COLLECTIONS else UNKNOWN


def manifest_row(path: Path) -> dict[str, str]:
    path_collection = collection_from_organized_path(path)
    row = {field: "" for field in MANIFEST_FIELDS}
    row["collection"] = path_collection
    row["image_path"] = path.relative_to(PROJECT_ROOT).as_posix()
    row["label"] = "1" if path_collection == COLLECTION_1A else "0" if path_collection == COLLECTION_1B else ""

    try:
        dataset = pydicom.dcmread(path, stop_before_pixels=True)
        row.update(
            {
                "patient_id": value_text(dataset, "PatientID"),
                "study_uid": value_text(dataset, "StudyInstanceUID"),
                "series_uid": value_text(dataset, "SeriesInstanceUID"),
                "sop_uid": value_text(dataset, "SOPInstanceUID"),
                "instance_number": value_text(dataset, "InstanceNumber"),
                "modality": value_text(dataset, "Modality"),
                "series_description": value_text(dataset, "SeriesDescription"),
            }
        )
    except Exception as exc:
        row["read_error"] = f"{type(exc).__name__}: {exc}"
    return row


def write_manifest() -> int:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    files = sorted(RAW_ROOT.rglob("*.dcm"), key=lambda path: path.as_posix())
    temporary = MANIFEST_PATH.with_suffix(".csv.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        for path in files:
            writer.writerow(manifest_row(path))
    temporary.replace(MANIFEST_PATH)
    return len(files)


def ensure_collection_directories() -> None:
    for collection in COLLECTIONS:
        (RAW_ROOT / collection).mkdir(parents=True, exist_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Organize project-root DICOM files without modifying their content."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="perform the planned moves; without this flag the script is a dry run",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plans = scan_root_dicoms()
    print_scan_summary(plans)

    identical, conflicting = preflight_collisions(plans)
    if conflicting:
        print("ERROR: target collisions detected; no files were moved.", file=sys.stderr)
        for plan in conflicting[:20]:
            print(
                f"ERROR: {plan.source.relative_to(PROJECT_ROOT)} -> "
                f"{plan.target.relative_to(PROJECT_ROOT)}",
                file=sys.stderr,
            )
        return 2

    if not args.execute:
        print("Dry run complete. No files were moved.")
        print("Run again with --execute after reviewing the summary.")
        return 0

    ensure_collection_directories()
    try:
        moved = move_plans(plans, identical)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3

    manifest_rows = write_manifest()
    print(f"Moved {moved} DICOM files without overwriting existing files")
    print(f"Manifest rows: {manifest_rows}")
    print(f"Manifest: {MANIFEST_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Operation log: {LOG_PATH.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
