"""Metadata-only head records. Never open CT or localization references here."""
from collections.abc import Mapping
import re

SPLITS = frozenset({"train_weak", "val_classification", "dev_localization", "test_localization"})
FIELDS = frozenset({
    "record_id", "dataset_id", "version", "patient_group_id", "patient_group_status",
    "study_key", "series_key", "source_diagnosis", "study_imaging_finding",
    "task_label", "label_definition_id", "split", "image_ref", "image_sha256",
    "image_missing_reason", "access_status", "geometry_qa",
})
MD_LABEL = "MD_SOURCE_DIAGNOSIS_WEAK_V1"
DEFINITIONS = frozenset({MD_LABEL, "RICORD_PARTIAL_LOCALIZATION_V1", "COVID1920_LOCALIZATION_V1"})


def source_diagnosis_label(value):
    """Publisher case category only; no inference about visible CT infection."""
    return {"COVID-19": 1, "CAP": 1, "Normal": 0}[value]


def _text(value, nullable=False):
    return (nullable and value is None) or (isinstance(value, str) and bool(value.strip()))


def validate_records(records, *, executable=False):
    """Validate global cohort before filtering. No file reads or split assignment.

    Candidate validation permits unresolved references/groups, but is never a
    training readiness receipt. Group IDs must be reconciled across datasets by
    DATA; unique folder names alone do not verify patient independence.
    """
    records = list(records)
    groups, hashes, ids, images, studies, series = {}, {}, set(), {}, {}, {}
    for row in records:
        if not isinstance(row, Mapping) or set(row) != FIELDS:
            raise ValueError("record fields must exactly match EPI_DATA_RECORD_V1; no GT input")
        for key in ("record_id", "dataset_id", "version"):
            if not _text(row[key]):
                raise ValueError(f"invalid {key}")
        if row["record_id"] in ids:
            raise ValueError("duplicate record_id")
        ids.add(row["record_id"])
        for key in ("patient_group_id", "study_key", "series_key", "image_ref", "image_missing_reason"):
            if not _text(row[key], nullable=True):
                raise ValueError(f"invalid {key}")
        split = row["split"]
        if split not in SPLITS and split is not None:
            raise ValueError("unknown split")
        if row["patient_group_status"] not in {"VERIFIED", "UNKNOWN"}:
            raise ValueError("unknown patient grouping status")
        if row["access_status"] not in {"APPROVED_EXACT_SCOPE", "NOT_APPROVED", "UNKNOWN"}:
            raise ValueError("unknown access status")
        if row["geometry_qa"] not in {"PASS", "NOT_RUN", "QUARANTINED"}:
            raise ValueError("unknown geometry QA")
        if row["study_imaging_finding"] not in {"UNKNOWN", "VISIBLE_INFECTION_CONFIRMED", "NO_VISIBLE_INFECTION_CONFIRMED"}:
            raise ValueError("unknown imaging finding")
        diagnosis = row["source_diagnosis"]
        if not isinstance(diagnosis, Mapping) or set(diagnosis) != {"value", "original_value", "provenance"}:
            raise ValueError("diagnosis must retain original value and provenance")
        if not all(_text(diagnosis[k], nullable=True) for k in ("value", "original_value")):
            raise ValueError("invalid diagnosis values")
        provenance = diagnosis["provenance"]
        if not isinstance(provenance, Mapping) or set(provenance) != {"source_url", "evidence_ref", "verification"}:
            raise ValueError("invalid provenance fields; no nested GT input")
        if provenance["verification"] not in {"VERIFIED", "PUBLIC_SOURCE_ONLY", "UNKNOWN"}:
            raise ValueError("invalid provenance verification")
        if not all(_text(provenance[k], nullable=True) for k in ("source_url", "evidence_ref")):
            raise ValueError("invalid provenance references")
        definition = row["label_definition_id"]
        if definition not in DEFINITIONS:
            raise ValueError("unknown label definition")
        label = row["task_label"]
        if label is not None and (type(label) is not int or label not in (0, 1)):
            raise ValueError("invalid task label")
        if definition == MD_LABEL:
            if row["dataset_id"] != "COVID-CT-MD":
                raise ValueError("MD weak definition is source-specific")
            if diagnosis["value"] not in {"COVID-19", "CAP", "Normal"}:
                raise ValueError("unresolved MD category")
            if label != source_diagnosis_label(diagnosis["value"]):
                raise ValueError("category/label conflict; CAP is positive")
            if not _text(diagnosis["original_value"]):
                raise ValueError("missing original category")
        elif label is not None or split in {"train_weak", "val_classification"}:
            raise ValueError("localization record cannot become head training label")
        digest = row["image_sha256"]
        if digest is not None and (not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise ValueError("invalid image SHA256")
        if row["image_ref"] is None and not _text(row["image_missing_reason"]):
            raise ValueError("missing image requires reason")
        if executable:
            if split is None or row["patient_group_status"] != "VERIFIED" or row["patient_group_id"] is None:
                raise ValueError("executable cohort requires assigned split and verified global group")
            if not all(row[k] is not None for k in ("study_key", "series_key", "image_ref", "image_sha256")):
                raise ValueError("executable cohort requires exact image identity")
            if row["image_missing_reason"] is not None or row["access_status"] != "APPROVED_EXACT_SCOPE" or row["geometry_qa"] != "PASS":
                raise ValueError("executable cohort requires approved scope and geometry PASS")
            if provenance["verification"] != "VERIFIED" or not all(_text(provenance[k]) for k in ("source_url", "evidence_ref")):
                raise ValueError("executable cohort requires verified source evidence")
        for key, ledger in (("patient_group_id", groups), ("image_sha256", hashes),
                            ("image_ref", images), ("study_key", studies), ("series_key", series)):
            identity = row[key]
            if identity is not None and split is not None:
                if identity in ledger and ledger[identity] != split:
                    raise ValueError(f"cross-split {key} leakage")
                ledger[identity] = split
    return records


def classification_records(records):
    """Return validated executable head metadata, never reference registry data."""
    cohort = validate_records(records, executable=True)
    return [row for row in cohort if row["split"] in {"train_weak", "val_classification"}]
