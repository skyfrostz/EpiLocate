import numpy as np
import pytest

from epi_next.evaluation_protocol import VARIANTS, cross_scale_consistency, evaluate_variant, fixed_area_candidate, matrix_status, fixed_slice_binding, support_budget_cap

KEY = ("Infectious opacity", "reader", "group", "label")


def fixture():
    support = np.ones((10, 10), bool)
    large = np.zeros_like(support); large[1:3, 1:3] = True
    small = np.zeros_like(support); small[8, 8] = True
    objects = [{"annotation_id": "large", "mask": large, "reference_key": KEY},
               {"annotation_id": "small", "mask": small, "reference_key": KEY}]
    score = large.astype(float)
    return support, objects, {"16": {"scores": score, "reliable": large}, "32": {"scores": score, "reliable": large}}


def test_partial_reference_and_small_annotation_unit_preserved():
    support, objects, scales = fixture()
    result = evaluate_variant(scales, objects, support, KEY)
    metric = result["budgets"]["0.1"]["scales"]["16"]
    assert metric["observed_reference_coverage"] == .8
    assert metric["annotation_units_hit"] == 1 and metric["annotation_units_evaluable"] == 2
    assert metric["dice"] is metric["iou"] is metric["false_positive_voxels"] is None
    assert metric["candidate_voxels"] == 4  # no fill to the 10-pixel cap


def test_all_four_variants_share_numerical_interface():
    support, objects, scales = fixture()
    values = [evaluate_variant(scales, objects, support, KEY) for _ in VARIANTS]
    assert all(v == values[0] for v in values)


def test_no_cross_class_or_reader_union():
    support, objects, scales = fixture()
    objects[1]["reference_key"] = ("Atelectasis", "reader", "group", "label")
    with pytest.raises(ValueError, match="mixed"):
        evaluate_variant(scales, objects, support, KEY)


def test_three_dimensional_budget_is_fixed_per_sop():
    support = np.ones((2, 10, 10), bool); reliable = support.copy()
    scores = np.arange(200).reshape(support.shape)
    result = fixed_area_candidate(scores, reliable, support, .05)
    assert list(result.sum(axis=(1, 2))) == [5, 5]


def test_candidate_area_uses_actual_native_spacing():
    support, objects, scales = fixture()
    result = evaluate_variant(scales, objects, support, KEY, spacing_krc_mm=[1.25, .7, .8])
    metric = result["budgets"]["0.1"]["scales"]["16"]
    assert metric["per_sop_candidate_area_mm2"] == pytest.approx([4 * .7 * .8])


def test_empty_empty_consistency_is_undefined():
    empty = np.zeros((2, 2), bool)
    result = cross_scale_consistency({"16": empty, "32": empty})
    assert result["conditional_mean_candidate_set_jaccard"] is None


def test_disjoint_consistency_is_zero():
    left = np.eye(2, dtype=bool); right = ~left
    assert cross_scale_consistency({"16": left, "32": right})["conditional_mean_candidate_set_jaccard"] == 0


def test_expected_denominator_includes_failure_abstention_and_missing():
    summary = matrix_status(["a", "b", "c"], [{"patient_id": "a", "variant": "E1/F0", "status": "OK", "candidate_voxels": 3,
                                             "observed_reference_coverage": .5},
                                            {"patient_id": "b", "variant": "E1/F0", "status": "FAILED"}])
    assert summary["E1/F0"]["patients_expected"] == 3
    assert summary["E1/F0"]["effective_candidate_rate"] == 1 / 3
    assert summary["E2/F1"]["patients_unavailable"] == 3


def test_duplicate_patient_variant_rejected():
    record = {"patient_id": "a", "variant": "E1/F0", "status": "FAILED"}
    with pytest.raises(ValueError):
        matrix_status(["a"], [record, record])


def test_no_polygon_is_unknown_and_candidate_metrics_still_available():
    support, _, scales = fixture()
    result = evaluate_variant(scales, [], support, KEY)
    metric = result["budgets"]["0.05"]["scales"]["16"]
    assert metric["observed_reference_coverage"] is None
    assert metric["dice"] is metric["iou"] is metric["false_positive_voxels"] is None
    assert metric["candidate_voxels"] == 4
    assert metric["annotation_units_evaluable"] == 0


def test_single_sop_budget_does_not_floor_each_row():
    assert support_budget_cap(np.ones((512, 512), bool), .05) == 13107
    assert support_budget_cap(np.ones((2, 512, 512), bool), .05) == 26214


def slice_fixture():
    case = {"geometry": {"shape_krc": [4, 2, 2]}, "sops": [
        {"native_slice_index": k, "SOPInstanceUID": str(k)} for k in range(4)]}
    lock = {"model_outputs_used": False, "gt_used_for_selection": False, "slices": [
        {"patient_id": "p", "native_slice_index_zero_based": 1, "sop_uid": "1",
         "native_manifest_sha256": "sha", "native_shape_krc": [4, 2, 2]}]}
    return case, lock


def test_fixed_slice_exact_middle_uid_binding():
    case, lock = slice_fixture()
    assert fixed_slice_binding(lock, "p", case, "sha") == (1, "1")


@pytest.mark.parametrize("field,value", [("native_slice_index_zero_based", 2), ("sop_uid", "2"),
                                       ("native_manifest_sha256", "other"), ("native_shape_krc", [5, 2, 2])])
def test_fixed_slice_reselection_and_stale_grid_rejected(field, value):
    case, lock = slice_fixture(); lock["slices"][0][field] = value
    with pytest.raises(ValueError, match="disagrees"):
        fixed_slice_binding(lock, "p", case, "sha")


def test_model_dependent_slice_lock_rejected():
    case, lock = slice_fixture(); lock["model_outputs_used"] = True
    with pytest.raises(ValueError, match="precede"):
        fixed_slice_binding(lock, "p", case, "sha")


@pytest.mark.parametrize("annotated_sop,expected_coverage", [("1", 0.0), ("0", None)])
def test_fixed_slice_request_excludes_other_sop_reference(tmp_path, monkeypatch, annotated_sop, expected_coverage):
    from PIL import Image
    from epi_next import evaluation_protocol as ep
    from epi_next.gt_vnext import sha256
    case, lock = slice_fixture()
    case["geometry"].update(status="PASS", spacing_krc_mm=[1, 1, 1])
    case["native_volume"] = {"status": "TECHNICAL_PASS"}
    maskpath = tmp_path / "mask.png"
    Image.fromarray(np.array([[255, 0], [0, 0]], dtype=np.uint8)).save(maskpath)
    case["annotations"] = [{"status": "PASS", "identity": {"SOPInstanceUID": annotated_sop},
        "raw_label": {"name": KEY[0], "label_group_id": KEY[2]},
        "raw_annotation": {"createdById": KEY[1], "labelId": KEY[3]},
        "annotation_id": "unit", "mask_path": "mask.png", "mask_sha256": sha256(maskpath)}]
    delivery = {"allowlist_path": "allow", "allowlist_sha256": "allowsha"}
    manifest = {"allowlist_sha256": "allowsha", "counts": {"patients": 3}, "cases": [
        {"patient_id": p, "manifest_path": "case", "manifest_sha256": "sha"} for p in ["p", "q", "r"]]}
    lock.update(data_delivery_sha256="deliverysha", allowlist_sha256="allowsha")
    lock["slices"].extend([dict(lock["slices"][0], patient_id=p) for p in ["q", "r"]])
    bound = {"allow": {"records": [{"patient_id": p} for p in ["p", "q", "r"]]},
             str(tmp_path / "gt"): manifest, str(tmp_path / "case"): case, "lock": lock}
    monkeypatch.setattr(ep, "verify_delivery", lambda *a: delivery)
    monkeypatch.setattr(ep, "read_bound", lambda path, _: bound[str(path)])
    supportpath = tmp_path / "support.npy"; np.save(supportpath, np.ones((2, 2), bool))
    predpath = tmp_path / "pred.npz"
    np.savez(predpath, scores=np.array([[1., 0], [0, 0]]), reliable=np.ones((2, 2), bool),
             native_case_manifest_sha256="sha", SOPInstanceUID="1", native_slice_index=1)
    request = {"expected_scales": ["s"], "delivery_path": "delivery", "delivery_sha256": "deliverysha",
        "gt_manifest_path": str(tmp_path / "gt"), "gt_manifest_sha256": "gtsha",
        "fixed_slice_lock_path": "lock", "fixed_slice_lock_sha256": "locksha", "case_inputs": [{
        "patient_id": "p", "native_case_manifest_sha256": "sha", "support_path": str(supportpath),
        "support_sha256": sha256(supportpath), "support_selection_basis": "PREDECLARED_NATIVE_DOMAIN_INDEPENDENT_OF_PREDICTIONS_AND_GT",
        "reference_key": KEY, "predictions": [{"variant": "E1/F0", "mapping_status": "VERIFIED_NATIVE_GRID",
        "scales": [{"scale": "s", "path": str(predpath), "sha256": sha256(predpath)}]}]}]}
    result = ep.evaluate_request(request)
    metric = result["case_results"][0]["budgets"]["0.2"]["scales"]["s"]
    assert metric["observed_reference_coverage"] == expected_coverage
    assert result["evaluation_scope"] == "FIXED_MIDDLE_NATIVE_SOP"
    assert len(metric["annotation_units"]) == (annotated_sop == "1")
