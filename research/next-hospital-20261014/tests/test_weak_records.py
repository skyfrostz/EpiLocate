from copy import deepcopy
import pytest
from epi_next.weak_records import classification_records, source_diagnosis_label, validate_records


def record(group="SYNTH-P1", split="train_weak", category="CAP"):
    return dict(record_id=group + split, dataset_id="COVID-CT-MD", version="SYNTH-v1",
                patient_group_id=group, patient_group_status="VERIFIED", study_key=group + "study",
                series_key=group + "series", source_diagnosis={"value": category, "original_value": category,
                    "provenance": {"source_url": "https://example.invalid/synthetic", "evidence_ref": "SYNTH-source",
                                   "verification": "VERIFIED"}}, study_imaging_finding="UNKNOWN",
                task_label=source_diagnosis_label(category), label_definition_id="MD_SOURCE_DIAGNOSIS_WEAK_V1",
                split=split, image_ref="SYNTH/"+group, image_sha256=("a" if group == "SYNTH-P1" else "b")*64,
                image_missing_reason=None, access_status="APPROVED_EXACT_SCOPE", geometry_qa="PASS")


def test_case_category_keeps_cap_positive_and_imaging_unknown():
    rows = [record(), record("SYNTH-P2", "val_classification", "Normal")]
    assert [r["task_label"] for r in classification_records(rows)] == [1, 0]
    assert rows[0]["study_imaging_finding"] == "UNKNOWN"
    assert source_diagnosis_label("COVID-19") == 1


@pytest.mark.parametrize("split", ["val_classification", "dev_localization", "test_localization"])
def test_same_patient_different_scan_cannot_cross_splits(split):
    a, b = record(), record(split=split)
    b.update(study_key="SYNTH-followup", series_key="SYNTH-reconstruction", image_ref="SYNTH-other", image_sha256="c"*64)
    with pytest.raises(ValueError, match="cross-split patient_group_id"):
        validate_records([a, b])


def test_content_duplicate_cannot_escape_with_new_patient_identity():
    a, b = record(), record("SYNTH-P2", "val_classification")
    b["image_sha256"] = a["image_sha256"]
    with pytest.raises(ValueError, match="cross-split image_sha256"):
        validate_records([a, b])


@pytest.mark.parametrize("key", ["study_key", "series_key"])
def test_native_identity_alias_cannot_cross_split(key):
    a, b = record(), record("SYNTH-P2", "test_localization")
    b[key] = a[key]
    with pytest.raises(ValueError, match="cross-split " + key):
        validate_records([a, b])


@pytest.mark.parametrize("where", ["record", "provenance"])
def test_gt_reference_rejected_even_if_nested(where):
    row = record()
    target = row if where == "record" else row["source_diagnosis"]["provenance"]
    target["localization_reference"] = "SYNTH-mask.npz"
    with pytest.raises(ValueError):
        classification_records([row])


def test_unacquired_candidate_is_not_executable():
    row = record()
    row.update(patient_group_id=None, patient_group_status="UNKNOWN", study_key=None, series_key=None,
               split=None, image_ref=None, image_sha256=None, image_missing_reason="NOT_ACQUIRED",
               access_status="NOT_APPROVED", geometry_qa="NOT_RUN")
    row["source_diagnosis"]["provenance"]["verification"] = "PUBLIC_SOURCE_ONLY"
    assert validate_records([row]) == [row]
    with pytest.raises(ValueError, match="verified global group"):
        classification_records([row])


def test_cap_negative_or_non_md_category_cannot_train():
    row = record(); row["task_label"] = 0
    with pytest.raises(ValueError, match="CAP is positive"):
        classification_records([row])
    row = record(); row["dataset_id"] = "RICORD"
    with pytest.raises(ValueError, match="source-specific"):
        classification_records([row])


def test_localization_records_excluded_from_head_without_reference_paths():
    row = record("SYNTH-P2", "dev_localization")
    row.update(dataset_id="COVID-19-20", label_definition_id="COVID1920_LOCALIZATION_V1", task_label=None)
    assert classification_records([record(), row]) == [record()]


def test_same_image_ref_and_unknown_group_are_not_independent_patients():
    a, b = record(), record("SYNTH-P2", "val_classification")
    b["image_ref"] = a["image_ref"]
    with pytest.raises(ValueError, match="cross-split image_ref"):
        validate_records([a, b])
    b = deepcopy(a); b["patient_group_status"] = "UNKNOWN"
    with pytest.raises(ValueError, match="verified global group"):
        classification_records([b])
