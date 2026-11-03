import io
import json
from zipfile import ZipFile

import numpy as np
import pydicom
import pytest

import epi_next.gt_vnext as gt
from epi_next.gt_prep import rasterize_native_polygon


def test_metadata_after_data_ignores_nested_uid():
    raw = '{"data":{"SOPInstanceUID":"approved","note":"braces } [ \\\""},"SOPInstanceUID":"unapproved"}'
    assert gt.top_level_metadata(raw, {"SOPInstanceUID"}) == {"SOPInstanceUID": "unapproved"}


def test_duplicate_identity_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        gt.top_level_metadata('{"SOPInstanceUID":"a","SOPInstanceUID":"b"}', {"SOPInstanceUID"})


def test_framing_escapes_and_large_chunks():
    objects = [{"data": "x" * 70000 + '}["', "id": "a"}, {"id": "b"}]
    source = json.dumps({"annotations": objects}).encode()
    assert [json.loads(r) for r in gt.array_objects(io.BytesIO(source), "annotations")] == objects


def test_skip_unapproved_body_without_json_decode(tmp_path, monkeypatch):
    approved = {"data": {"vertices": [[1, 1], [3, 1], [3, 3]]}, "id": "allowed",
                "StudyInstanceUID": "study", "SeriesInstanceUID": "series", "SOPInstanceUID": "sop", "labelId": "label"}
    # Invalid semantic body is still lexically balanced: must never be decoded.
    skipped = '{"data":{"bad":NOT_JSON},"StudyInstanceUID":"other","SeriesInstanceUID":"other","SOPInstanceUID":"other","labelId":"label"}'
    groups = [{"id": "group", "name": "group", "labels": [{"id": "label", "name": "Infectious opacity", "scope": "INSTANCE"}]}]
    raw = '{"labelGroups":' + json.dumps(groups) + ',"annotations":[' + skipped + ',' + json.dumps(approved) + ']}'
    path = tmp_path / "fixture.zip"
    with ZipFile(path, "w") as z:
        z.writestr("fixture.json", raw)
    monkeypatch.setattr(gt, "OFFICIAL_SHA", gt.sha256(path))
    cases = [{"rows": [{"study_uid": "study", "series_uid": "series", "sop_uid": "sop"}]}]
    _, selected = gt.selected_annotations(path, cases)
    assert [a["id"] for a in selected] == ["allowed"]


@pytest.mark.parametrize("vertices", [
    [[1.2, 1.2], [3.8, 1.2], [3.8, 3.8], [1.2, 3.8]],
    [[1, 1], [5, 2], [3, 5]],
    [[1, 1], [5, 1], [5, 5], [1, 5], [1, 1]],
])
def test_native_pixel_centre_raster_matches_independent_primitive(vertices):
    result = gt.polygon_mask(vertices, (8, 8))
    assert np.array_equal(result, rasterize_native_polygon(vertices, (8, 8))["mask"])


@pytest.mark.parametrize("vertices", [
    [[1, 1], [5, 5], [1, 5], [5, 1]],
    [[1, 1], [2, 1], [3, 1]],
    [[0, 1], [3, 1], [3, 3]],
    [[-1, 1], [3, 1], [3, 3]],
    [[1, 1], [float("nan"), 1], [3, 3]],
    [[1.1, 1.1], [1.2, 1.1], [1.2, 1.2]],
])
def test_invalid_or_review_polygon_not_passed(vertices):
    with pytest.raises(ValueError):
        gt.polygon_mask(vertices, (8, 8))


def test_category_reader_group_and_unknown_creator_separation():
    mask = np.ones((3, 3), bool)
    items = [({"id": "a", "labelId": "l1", "createdById": "r"}, {"name": "Infectious opacity", "label_group_id": "g"}, mask),
             ({"id": "b", "labelId": "l1", "createdById": "r"}, {"name": "Infectious opacity", "label_group_id": "g"}, mask),
             ({"id": "c", "labelId": "l2", "createdById": "r"}, {"name": "Atelectasis", "label_group_id": "g"}, mask),
             ({"id": "d", "labelId": "l1"}, {"name": "Infectious opacity", "label_group_id": "g"}, mask),
             ({"id": "e", "labelId": "l1"}, {"name": "Infectious opacity", "label_group_id": "g"}, mask)]
    unions = gt.category_unions(items)
    assert len(unions) == 4
    assert all(m.sum() == 9 for m in unions.values())


def headers():
    datasets, rows = [], []
    for i in range(3):
        ds = pydicom.Dataset()
        ds.PatientID = "synthetic"; ds.StudyInstanceUID = "1.2.3"; ds.SeriesInstanceUID = "1.2.4"
        ds.SOPInstanceUID = f"1.2.5.{i}"; ds.FrameOfReferenceUID = "1.2.6"; ds.Modality = "CT"
        ds.Rows = ds.Columns = 8; ds.ImagePositionPatient = [0, 0, i * 1.25]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]; ds.PixelSpacing = [.7, .8]
        ds.RescaleSlope = 1; ds.RescaleIntercept = -1024
        datasets.append(ds); rows.append({"patient_id": "synthetic", "study_uid": "1.2.3", "series_uid": "1.2.4", "sop_uid": str(ds.SOPInstanceUID)})
    return datasets, rows


def test_native_geometry_order_spacing_and_inverse():
    ds, rows = headers()
    result = gt.native_geometry(ds[::-1], rows[::-1])
    assert result["order"] == [2, 1, 0]
    assert result["spacing_krc_mm"] == [1.25, .7, .8]
    assert result["roundtrip_max_voxel_error"] < 1e-8


@pytest.mark.parametrize("field,value", [("FrameOfReferenceUID", "1.2.99"), ("Rows", 9),
                                         ("PixelSpacing", [.9, .8]), ("RescaleSlope", 0)])
def test_mixed_or_invalid_native_geometry_isolated(field, value):
    ds, rows = headers(); setattr(ds[1], field, value)
    with pytest.raises(ValueError):
        gt.native_geometry(ds, rows)


def test_permission_failure_precedes_annotation_or_dicom_reads(tmp_path, monkeypatch):
    def tripwire(*args, **kwargs):
        raise AssertionError("data access before authorization")
    monkeypatch.setattr(gt, "selected_annotations", tripwire)
    monkeypatch.setattr(gt.pydicom, "dcmread", tripwire)
    path = tmp_path / "bad-delivery.json"; path.write_text("{}")
    from types import SimpleNamespace
    with pytest.raises(ValueError, match="SHA mismatch"):
        gt.build(SimpleNamespace(delivery=path, delivery_sha256="0" * 64, output=tmp_path / "output"))
    assert not (tmp_path / "output").exists()
