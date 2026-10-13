"""One native-space development protocol for E1/E2 x F0/F1.

Observed annotation coverage is not full-lesion recall. Polygon objects are
annotation units, not 3D lesions. This asset never qualifies complete Dice/IoU/FP.
No inference, training, threshold fitting or device execution occurs here.
"""
from __future__ import annotations

import argparse
from itertools import combinations
import json
import math
from pathlib import Path

import numpy as np

from .data_eval import budget_candidates, localization_metrics, summarize_patients
from .data_delivery import read_bound, verify_delivery
from .gt_vnext import INFECTION_CLASSES, sha256

VARIANTS = ("E1/F0", "E1/F1", "E2/F0", "E2/F1")
BUDGETS = (.05, .10, .20)


def fixed_slice_binding(lock, patient_id, case, case_sha):
    """Validate the pre-model geometry-only middle SOP against native ledger."""
    if lock.get("model_outputs_used") is not False or lock.get("gt_used_for_selection") is not False:
        raise ValueError("slice selection must precede model/GT use")
    rows = [s for s in lock["slices"] if s["patient_id"] == patient_id]
    if len(rows) != 1:
        raise ValueError("fixed slice membership mismatch")
    row = rows[0]
    index = (case["geometry"]["shape_krc"][0] - 1) // 2
    by_index = {s["native_slice_index"]: s["SOPInstanceUID"] for s in case["sops"]}
    if (row["native_slice_index_zero_based"] != index or row["sop_uid"] != by_index[index]
            or row["native_manifest_sha256"] != case_sha
            or row["native_shape_krc"] != case["geometry"]["shape_krc"]):
        raise ValueError("fixed slice disagrees with middle native SOP ledger")
    return index, by_index[index]


def support_budget_cap(support, fraction):
    slices = support[None] if support.ndim == 2 else support
    return sum(math.floor(int(s.sum()) * fraction) for s in slices)


def fixed_area_candidate(scores, reliable, support, fraction):
    if support.ndim == 2:
        return budget_candidates(scores, reliable, support, fraction)
    if support.ndim != 3 or np.shape(scores) != support.shape or np.shape(reliable) != support.shape:
        raise ValueError("native arrays must be matching slice,row,column")
    return np.stack([budget_candidates(scores[k], reliable[k], support[k], fraction) for k in range(len(support))])


def cross_scale_consistency(candidates):
    pairs = []
    for a, b in combinations(sorted(candidates), 2):
        left, right = candidates[a], candidates[b]
        union = int((left | right).sum()); overlap = int((left & right).sum())
        pairs.append({"scales": [a, b], "candidate_set_jaccard": overlap / union if union else None,
                      "status": "OK" if union else "BOTH_EMPTY_UNDEFINED"})
    values = [p["candidate_set_jaccard"] for p in pairs if p["candidate_set_jaccard"] is not None]
    return {"pairs": pairs, "conditional_mean_candidate_set_jaccard": math.fsum(values) / len(values) if values else None,
            "meaning": "agreement between native candidate sets; not GT IoU or lesion accuracy"}


def evaluate_variant(scales, objects, support, reference_key, *, budgets=BUDGETS, spacing_krc_mm=None):
    support = np.asarray(support)
    if support.dtype != np.bool_ or support.ndim not in (2, 3):
        raise ValueError("predeclared native support must be 2D/3D bool")
    if not reference_key or reference_key[0] not in INFECTION_CLASSES:
        raise ValueError("one explicit infection category/creator/group/label target required")
    if len(reference_key) != 4 or any(not isinstance(x, str) or not x for x in reference_key):
        raise ValueError("missing creator/group/label cannot form a reference union")
    if spacing_krc_mm is not None:
        spacing = np.asarray(spacing_krc_mm, dtype=float)
        if spacing.shape != (3,) or not np.isfinite(spacing).all() or np.any(spacing <= 0):
            raise ValueError("positive native slice,row,column spacing required")
    ids = [o["annotation_id"] for o in objects]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate annotation unit")
    reference = np.zeros(support.shape, bool)
    for obj in objects:
        if tuple(obj["reference_key"]) != tuple(reference_key):
            raise ValueError("mixed medical class or creator/group/label")
        mask = np.asarray(obj["mask"])
        target = reference if support.ndim == 2 else reference[obj["slice_index"]]
        if mask.dtype != np.bool_ or mask.shape != target.shape:
            raise ValueError("annotation mask not on native grid")
        target |= mask
    output = {}
    for fraction in budgets:
        candidates, scale_results = {}, {}
        for scale, arrays in sorted(scales.items()):
            candidate = fixed_area_candidate(np.asarray(arrays["scores"]), np.asarray(arrays["reliable"]), support, fraction)
            candidates[scale] = candidate
            metrics = localization_metrics(candidate, reference, support)
            unit_metrics = []
            for obj in objects:
                sl = obj.get("slice_index")
                source = support if support.ndim == 2 else support[sl]
                chosen = candidate if support.ndim == 2 else candidate[sl]
                observed = obj["mask"] & source; n = int(observed.sum())
                overlap = int((chosen & observed).sum())
                unit_metrics.append({"annotation_id": obj["annotation_id"], "observed_pixels_in_support": n,
                                     "observed_pixels_outside_support": int((obj["mask"] & ~source).sum()),
                                     "coverage": overlap / n if n else None, "hit": bool(overlap) if n else None})
            metrics.update(annotation_units=unit_metrics, annotation_unit_identity="POLYGON_NOT_3D_LESION",
                           annotation_units_hit=sum(m["hit"] is True for m in unit_metrics),
                           annotation_units_evaluable=sum(m["hit"] is not None for m in unit_metrics),
                           candidate_area_budget_fraction=fraction,
                           budget_policy="per-SOP floor(fraction * fixed native support pixels); no padding to quota")
            if spacing_krc_mm is not None:
                candidates_by_sop = candidate[None] if candidate.ndim == 2 else candidate
                metrics["per_sop_candidate_area_mm2"] = [int(sl.sum()) * float(spacing[1] * spacing[2]) for sl in candidates_by_sop]
                metrics["candidate_volume_mm3"] = int(candidate.sum()) * float(np.prod(spacing)) if candidate.ndim == 3 else None
            scale_results[scale] = metrics
        output[str(fraction)] = {"scales": scale_results, "cross_scale": cross_scale_consistency(candidates)}
    return {"status": "OK" if scales else "MISSING_PREDICTION", "budgets": output,
            "complete_metrics_eligible": False, "independent_test_eligible": False}


def matrix_status(expected_patients, records):
    """Keep every expected patient/variant, including missing and failed cases."""
    expected_patients = list(expected_patients)
    if len(set(expected_patients)) != len(expected_patients) or any(not x for x in expected_patients):
        raise ValueError("unique expected patient IDs required")
    indexed = {}
    for record in records:
        key = (record["patient_id"], record["variant"])
        if key[0] not in expected_patients or key[1] not in VARIANTS or key in indexed:
            raise ValueError("unexpected/duplicate patient variant")
        indexed[key] = record
    result = {}
    for variant in VARIANTS:
        rows = [indexed.get((p, variant), {"patient_id": p, "status": "MISSING_PREDICTION"}) for p in expected_patients]
        summary = summarize_patients(rows)
        summary["effective_candidate_rate"] = sum(r.get("candidate_voxels", 0) > 0 and r["status"] in
                                                   {"OK", "PARTIAL_BUDGET"} for r in rows) / len(rows) if rows else None
        summary["effective_candidate_definition"] = "nonempty valid candidate / all expected patients, per declared budget and scale"
        result[variant] = summary
    return result


def evaluate_request(request):
    """Offline native predictions; the caller supplies SHA-bound fixed support.

    Each case selects ONE category/creator/group/label reference. Repeat the
    protocol with other predeclared strata, never silently union across strata.
    """
    expected_scales = request["expected_scales"]
    if not expected_scales or len(set(expected_scales)) != len(expected_scales) or any(not isinstance(s, str) or not s for s in expected_scales):
        raise ValueError("predeclared unique scale names required")
    delivery = verify_delivery(Path(request["delivery_path"]), request["delivery_sha256"])
    allowlist = read_bound(delivery["allowlist_path"], delivery["allowlist_sha256"])
    gt_path = Path(request["gt_manifest_path"])
    manifest = read_bound(gt_path, request["gt_manifest_sha256"])
    if manifest["allowlist_sha256"] != delivery["allowlist_sha256"] or manifest["counts"]["patients"] != 3:
        raise ValueError("GT membership/authority mismatch")
    expected = [c["patient_id"] for c in allowlist["records"]]
    slice_lock = None
    if "fixed_slice_lock_path" in request:
        slice_lock = read_bound(request["fixed_slice_lock_path"], request["fixed_slice_lock_sha256"])
        if (slice_lock["data_delivery_sha256"] != request["delivery_sha256"]
                or slice_lock["allowlist_sha256"] != delivery["allowlist_sha256"]
                or sorted(s["patient_id"] for s in slice_lock["slices"]) != sorted(expected)):
            raise ValueError("slice lock delivery/membership mismatch")
    cases = {c["patient_id"]: c for c in manifest["cases"]}
    if set(cases) != set(expected):
        raise ValueError("GT patient membership mismatch")
    results, summaries = [], []
    seen_cases = set()
    for entry in request["case_inputs"]:
        pid = entry["patient_id"]
        if pid not in expected or pid in seen_cases:
            raise ValueError("unexpected/duplicate case input")
        seen_cases.add(pid)
        case_ref = cases[pid]
        case = read_bound(gt_path.parent / case_ref["manifest_path"], case_ref["manifest_sha256"])
        if case["geometry"]["status"] != "PASS" or case["native_volume"]["status"] != "TECHNICAL_PASS":
            raise ValueError("quarantined case cannot be evaluated")
        if entry["native_case_manifest_sha256"] != case_ref["manifest_sha256"]:
            raise ValueError("prediction grid ledger differs from GT native ledger")
        if entry["support_selection_basis"] != "PREDECLARED_NATIVE_DOMAIN_INDEPENDENT_OF_PREDICTIONS_AND_GT":
            raise ValueError("support domain must be fixed independently")
        support_path = Path(entry["support_path"])
        if sha256(support_path) != entry["support_sha256"]:
            raise ValueError("support SHA mismatch")
        support = np.load(support_path, allow_pickle=False)
        fixed_slice = fixed_sop = None
        if slice_lock is not None:
            fixed_slice, fixed_sop = fixed_slice_binding(slice_lock, pid, case, case_ref["manifest_sha256"])
        shape = tuple(case["geometry"]["shape_krc"])
        expected_shape = shape[1:] if slice_lock is not None else shape
        if support.shape != expected_shape or support.dtype != np.bool_:
            raise ValueError("support grid mismatch")
        if slice_lock is not None and not support.all():
            raise ValueError("first fixed-slice protocol requires full native FOV support")
        reference_key = tuple(entry["reference_key"])
        sop_to_index = {s["SOPInstanceUID"]: s["native_slice_index"] for s in case["sops"]}
        objects = []
        from PIL import Image
        for obj in case["annotations"]:
            if obj["status"] != "PASS":
                continue
            if fixed_sop is not None and obj["identity"]["SOPInstanceUID"] != fixed_sop:
                continue
            key = (obj["raw_label"]["name"], obj["raw_annotation"].get("createdById"), obj["raw_label"]["label_group_id"], obj["raw_annotation"]["labelId"])
            if key == reference_key:
                path = gt_path.parent / obj["mask_path"]
                if sha256(path) != obj["mask_sha256"]:
                    raise ValueError("GT mask SHA mismatch")
                with Image.open(path) as image:
                    mask = np.asarray(image, dtype=bool)
                objects.append({"annotation_id": obj["annotation_id"], "mask": mask, "reference_key": key,
                                "slice_index": sop_to_index[obj["identity"]["SOPInstanceUID"]]})
        if not objects and slice_lock is None:
            raise ValueError("no observed reference in requested stratum")
        seen_variants = set()
        for prediction in entry["predictions"]:
            variant = prediction["variant"]
            if variant not in VARIANTS or variant in seen_variants:
                raise ValueError("duplicate/unknown variant")
            seen_variants.add(variant)
            if prediction.get("status") == "FAILED":
                results.append({"patient_id": pid, "variant": variant, "status": "FAILED", "reason": prediction.get("reason")})
                for fraction in BUDGETS:
                    for scale in expected_scales:
                        summaries.append({"patient_id": pid, "variant": variant, "budget": str(fraction), "scale": scale, "status": "FAILED"})
                continue
            if prediction["mapping_status"] != "VERIFIED_NATIVE_GRID":
                raise ValueError("resampled scores require separately verified DATA mapping before this native interface")
            scales = {}
            for item in prediction["scales"]:
                path = Path(item["path"])
                if sha256(path) != item["sha256"] or item["scale"] in scales or item["scale"] not in expected_scales:
                    raise ValueError("score SHA or duplicate scale")
                with np.load(path, allow_pickle=False) as arrays:
                    if str(arrays["native_case_manifest_sha256"].item()) != case_ref["manifest_sha256"]:
                        raise ValueError("prediction NPZ does not bind native ordered-SOP/affine ledger")
                    if fixed_sop is not None and (str(arrays["SOPInstanceUID"].item()) != fixed_sop
                                                  or int(arrays["native_slice_index"].item()) != fixed_slice):
                        raise ValueError("prediction NPZ does not bind fixed SOP")
                    if arrays["scores"].shape != expected_shape or arrays["reliable"].shape != expected_shape:
                        raise ValueError("prediction grid mismatch")
                    scales[item["scale"]] = {"scores": arrays["scores"], "reliable": arrays["reliable"]}
            measured = evaluate_variant(scales, objects, support, reference_key, spacing_krc_mm=case["geometry"]["spacing_krc_mm"])
            results.append({"patient_id": pid, "variant": variant, **measured,
                            "native_slice_index": fixed_slice, "SOPInstanceUID": fixed_sop,
                            "reference_status": "OBSERVED_PARTIAL_REFERENCE" if objects else "NO_APPLICABLE_POLYGON_UNKNOWN"})
            for budget, data in measured["budgets"].items():
                for scale, metric in data["scales"].items():
                    predicted = metric["candidate_voxels"]
                    cap = support_budget_cap(support, float(budget))
                    status = "NO_RELIABLE_RESPONSE" if predicted == 0 else "PARTIAL_BUDGET" if predicted < cap else "OK"
                    summaries.append({"patient_id": pid, "variant": variant, "budget": budget, "scale": scale,
                                      "status": status, "candidate_voxels": predicted,
                                      "observed_reference_coverage": metric["observed_reference_coverage"]})
    strata = [(str(fraction), scale) for fraction in BUDGETS for scale in expected_scales]
    return {"schema": "EPI_NEXT_E1_E2_F0_F1_DEVELOPMENT_EVAL_V1", "status": "EVALUATED_OFFLINE_ARRAYS" if summaries else "NOT_RUN_NO_PREDICTIONS",
            "evidence_type": "DEVELOPMENT_PREDICTION_REPLAY" if summaries else "INTERFACE_CHECK_NO_MODEL_RESULTS",
            "independent_test_eligible": False, "complete_metrics_eligible": False, "case_results": results,
            "evaluation_scope": "FIXED_MIDDLE_NATIVE_SOP" if slice_lock is not None else "FULL_NATIVE_VOLUME",
            "patient_summaries": {f"{budget}/{scale}": matrix_status(expected, [r for r in summaries if r["budget"] == budget and r["scale"] == scale]) for budget, scale in strata},
            "model_execution": "NONE_OFFLINE_ARRAYS_ONLY"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate_request(json.loads(args.request.read_text()))
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False); stream.write("\n")
