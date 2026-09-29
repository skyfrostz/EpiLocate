"""Shared manifest validation and project-relative configuration."""
from pathlib import Path

import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLASS_MAPPING = {"MIDRC-RICORD-1A": "1", "MIDRC-RICORD-1B": "0"}


def project_path(value):
    return PROJECT_ROOT / Path(value)


def load_config(path="configs/baseline.yaml"):
    with project_path(path).open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def read_manifest(path):
    frame = pd.read_csv(project_path(path), dtype=str, keep_default_na=False)
    required = {"patient_id", "collection", "label", "study_uid", "series_uid",
                "sop_uid", "image_path", "modality", "series_description"}
    if missing := required - set(frame):
        raise ValueError(f"Missing manifest fields: {sorted(missing)}")
    if frame.empty:
        raise ValueError("Empty manifest")
    for column in required - {"series_description"}:
        if frame[column].eq("").any():
            raise ValueError(f"Blank manifest field: {column}")
    if "read_error" in frame and frame.read_error.ne("").any():
        raise ValueError("Manifest contains DICOM read errors")
    for patient, rows in frame.groupby("patient_id"):
        if rows.collection.nunique() != 1 or rows.label.nunique() != 1:
            raise ValueError(f"Patient label conflict: {patient}")
    expected = frame.collection.map(CLASS_MAPPING)
    if expected.isna().any() or not expected.eq(frame.label).all():
        raise ValueError("Collection/label mismatch; require 1A=1 and 1B=0")
    for column in ("image_path", "sop_uid"):
        if frame[column].duplicated().any():
            raise ValueError(f"Duplicate {column}")
    for column in ("study_uid", "series_uid"):
        if frame.groupby(column).patient_id.nunique().gt(1).any():
            raise ValueError(f"{column} belongs to multiple patients")
    for value in frame.image_path:
        path = Path(value)
        if path.is_absolute() or not project_path(path).resolve().is_relative_to(
            (PROJECT_ROOT / "data/raw").resolve()
        ):
            raise ValueError(f"Unsafe image_path: {value}")
        if not project_path(path).is_file():
            raise ValueError(f"Missing DICOM: {value}")
    return frame
