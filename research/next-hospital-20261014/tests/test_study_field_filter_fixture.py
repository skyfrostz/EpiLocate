"""Synthetic contract rehearsal only; no archive reader or access authorization.

The test-local projector uses invented Study/label IDs. Real dictionary lookup,
approval validation and source-container traversal are deliberately absent.
"""
import json

import pytest

from epi_next.gt_vnext import top_level_metadata


FIELDS = {"id", "StudyInstanceUID", "labelId", "createdById", "createdAt", "updatedAt", "groupId"}


def project_fixture(raw):
    identity = top_level_metadata(raw, {"StudyInstanceUID", "labelId"})
    if identity.get("StudyInstanceUID") not in {"synthetic-study-a", "synthetic-study-b", "synthetic-study-c"}:
        return None
    if identity.get("labelId") not in {"synthetic-infection", "synthetic-normal"}:
        return None
    # Reject non-null data without decoding object/array content.
    data = top_level_metadata(raw, {"data"})
    if "data" not in data or data["data"] is not None:
        raise ValueError("GLOBAL data must be explicitly null")
    fields = top_level_metadata(raw, FIELDS)
    if any(not fields.get(key) for key in ("id", "StudyInstanceUID", "labelId")):
        raise ValueError("required identity absent")
    return fields


def fixture(**updates):
    record = {"id": "synthetic-annotation", "StudyInstanceUID": "synthetic-study-a",
              "labelId": "synthetic-infection", "createdById": "synthetic-reader",
              "createdAt": "synthetic-time", "updatedAt": None, "groupId": "synthetic-group", "data": None}
    record.update(updates)
    return json.dumps(record)


def test_selected_fields_exclude_unrequested_content():
    raw = fixture(note="excluded", updateHistory=[{"secret": "excluded"}], clinical={"MRN": "synthetic"})
    assert project_fixture(raw) == {key: value for key, value in json.loads(fixture()).items() if key in FIELDS}


@pytest.mark.parametrize("field,value", [("StudyInstanceUID", "outside"), ("labelId", "outside")])
def test_outside_scope_skips_body_before_semantic_decode(field, value):
    raw = fixture(**{field: value}).replace('"data": null', '"data": {"opaque": NOT_JSON}')
    assert project_fixture(raw) is None


def test_nested_identity_cannot_authorize():
    raw = '{"data":{"StudyInstanceUID":"synthetic-study-a","labelId":"synthetic-infection"},"StudyInstanceUID":"outside"}'
    assert project_fixture(raw) is None


@pytest.mark.parametrize("data", [{"opaque": "excluded"}, [], "unexpected"])
def test_selected_non_null_data_rejected(data):
    with pytest.raises(ValueError):
        project_fixture(fixture(data=data))


def test_missing_data_rejected():
    record = json.loads(fixture())
    del record["data"]
    with pytest.raises(ValueError, match="explicitly null"):
        project_fixture(json.dumps(record))


def test_duplicate_identity_rejected():
    raw = fixture()[:-1] + ',"StudyInstanceUID":"outside"}'
    with pytest.raises(ValueError, match="duplicate"):
        project_fixture(raw)


def test_duplicate_authorized_field_rejected():
    raw = fixture()[:-1] + ',"createdById":"other"}'
    with pytest.raises(ValueError, match="duplicate"):
        project_fixture(raw)


def test_selected_unrequested_body_not_decoded():
    raw = fixture()[:-1] + ',"note":{"opaque":NOT_JSON}}'
    assert set(project_fixture(raw)) == FIELDS
