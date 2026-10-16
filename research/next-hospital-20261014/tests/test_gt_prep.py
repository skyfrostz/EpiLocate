import numpy as np
import pytest

from epi_next.gt_prep import (pending_authorization_template, prepare_sop_reference,
                              rasterize_native_polygon)


def obj(name="a", vertices=None, **kwargs):
    return {"annotation_id": name, "study_uid": "synthetic-study", "series_uid": "synthetic-series",
            "sop_uid": "synthetic-sop", "reader_id": "reader-a", "group_id": "group-a",
            "category": "infection", "vertices_xy": vertices or [[1,1],[3,1],[3,3],[1,3]], **kwargs}


def prepare(objects):
    return prepare_sop_reference(objects, shape_rc=(8,9), study_uid="synthetic-study",
        series_uid="synthetic-series", sop_uid="synthetic-sop", approved_categories={"infection"})


def test_polygon_native_xy_pixel_center_boundary_and_no_transposition():
    result = rasterize_native_polygon([[2,1],[5,1],[5,3],[2,3]], (7,9))
    expected = np.zeros((7,9), bool); expected[1:4,2:6] = True
    np.testing.assert_array_equal(result["mask"], expected)
    assert result["geometry_status"] == "SYNTHETIC_GEOMETRY_PASS"


def test_multipolygon_union_preserves_objects_and_source():
    a = obj(); b = obj("b", [[3,1],[5,1],[5,3],[3,3]])
    result = prepare([a,b])
    assert len(result["objects"]) == 2 and result["objects"][0]["source"] == a
    assert len(result["sensitivity_groups"]) == 1
    assert result["sensitivity_groups"][0]["mask"].sum() == 15
    assert result["whole_sop_union"] is result["consensus_mask"] is None
    assert not result["full_reference_metrics_eligible"]


def test_different_readers_groups_categories_never_form_consensus():
    result = prepare([obj(), obj("b",reader_id="reader-b"), obj("c",group_id="group-b"),
                      obj("d",category="atelectasis")])
    assert len(result["sensitivity_groups"]) == 3
    assert result["objects"][3]["status"] == "CATEGORY_OUT_OF_SCOPE"


@pytest.mark.parametrize("field", ["reader_id", "group_id"])
def test_unknown_relationship_objects_stay_separate(field):
    result = prepare([obj(**{field:None}),obj("b", **{field:None})])
    assert len(result["sensitivity_groups"]) == 2
    assert all(g["meaning"] == "SINGLE_OBJECT_UNKNOWN_RELATIONSHIP" for g in result["sensitivity_groups"])


@pytest.mark.parametrize("vertices", [
    [[1,1],[4,4],[1,4],[4,1]],  # self crossing
    [[1,1],[2,2],[3,3]],        # zero area
    [[1,1],[3,1],[3,1],[1,3]],  # repeated point
    [[-1,1],[2,1],[2,3],[1,3]], # out of grid
    [[1,1],[6,1],[3,1],[3,3],[1,3]], # overlapping adjacent edges
])
def test_bad_polygons_retained_not_silently_dropped(vertices):
    result = prepare([obj(vertices=vertices)])
    assert result["objects"][0]["status"] == "INVALID_POLYGON"
    assert result["sensitivity_groups"] == []


def test_edge_touch_stays_review_and_missing_polygon_is_unknown():
    result = prepare([obj(vertices=[[0,1],[2,1],[2,3],[0,3]])])
    assert result["objects"][0]["status"] == "EDGE_TOUCH_REVIEW_REQUIRED"
    assert result["sensitivity_groups"] == []
    missing = prepare([])
    assert missing["status"] == "NO_POLYGON_ANNOTATION"
    assert missing["annotation_completeness"] == "UNKNOWN"


def test_duplicate_identity_and_wrong_sop_fail_closed():
    with pytest.raises(ValueError):prepare([obj(),obj()])
    with pytest.raises(ValueError):prepare([obj(sop_uid="not-approved")])


def test_pending_template_grants_no_access():
    t = pending_authorization_template("a"*64)
    assert t["status"] == "PENDING" and t["approved_scope"] == []
    assert not any(v for k,v in t.items() if k.startswith("permit_"))
    assert t["approver"] is None
    with pytest.raises(ValueError):pending_authorization_template("missing")
