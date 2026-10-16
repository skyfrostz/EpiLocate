"""Evaluate saved direct E1/E2 results after independent inverse raster QA."""
import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np
from PIL import Image

from .data_delivery import read_bound
from .data_eval import summarize_patients
from .evaluation_protocol import BUDGETS, evaluate_variant, fixed_slice_binding, support_budget_cap
from .gt_vnext import sha256
from .prepared_mapping_qa import require_close


def native_cell_lookup(model_size=224, native_size=512):
    """Independent half-pixel cell lookup: floor((native_center+.5)*ratio)."""
    return np.floor((np.arange(native_size) + .5) * model_size / native_size).astype(int)


def reconstruct_e1(records, scale):
    scores = np.zeros((224, 224), float); reliable = np.zeros((224, 224), bool)
    covered = np.zeros((224, 224), bool)
    for record in records:
        if record["scale_pixels"] != scale:
            continue
        (y0, y1), (x0, x1) = record["bounds_yx"]
        if not 0 <= y0 < y1 <= 224 or not 0 <= x0 < x1 <= 224 or covered[y0:y1, x0:x1].any():
            raise ValueError("E1 grid overlap or invalid bounds")
        baseline, perturbed = np.array(record["baseline_logits"]), np.array(record["perturbed_logits"])
        delta = float((baseline[1] - baseline[0]) - (perturbed[1] - perturbed[0]))
        require_close(record["margin_delta"], delta, "E1 fixed-target margin mismatch", 1e-6)
        if record["target"] != 1 or record["accepted"] != (delta > 0):
            raise ValueError("E1 target/reliability differs from fixed threshold")
        scores[y0:y1, x0:x1] = record["margin_delta"]
        reliable[y0:y1, x0:x1] = record["accepted"]
        covered[y0:y1, x0:x1] = True
    if not covered.all():
        raise ValueError("E1 scale grid incomplete")
    return scores, reliable


def evaluate_run(run_path, run_sha, template_path, template_sha, prepared_qa_path, prepared_qa_sha):
    run = read_bound(run_path, run_sha)
    template = read_bound(template_path, template_sha)
    prepared_qa = read_bound(prepared_qa_path, prepared_qa_sha)
    if (prepared_qa["status"] != "TECHNICAL_PASS" or run["prepared_delivery_sha256"] != prepared_qa["prepared_delivery_sha256"]
            or run["data_delivery_sha256"] != template["delivery_sha256"]
            or run["slice_lock_sha256"] != template["fixed_slice_lock_sha256"]):
        raise ValueError("run not bound to independently checked prepared inputs")
    prepared = read_bound(run["prepared_delivery_path"], run["prepared_delivery_sha256"])
    lock = read_bound(template["fixed_slice_lock_path"], template["fixed_slice_lock_sha256"])
    gt_path = Path(template["gt_manifest_path"])
    gt = read_bound(gt_path, template["gt_manifest_sha256"])
    if len(run["records"]) != 3 or {r["case_index"] for r in run["records"]} != {1, 2, 3}:
        raise ValueError("real result membership mismatch")
    output, mapping_qa = [], []
    lookup = native_cell_lookup()
    for record in run["records"]:
        i = record["case_index"]
        selected = next(s for s in lock["slices"] if s["case_index"] == i)
        case_ref = next(c for c in gt["cases"] if c["patient_id"] == selected["patient_id"])
        case = read_bound(gt_path.parent / case_ref["manifest_path"], case_ref["manifest_sha256"])
        index, sop = fixed_slice_binding(lock, selected["patient_id"], case, case_ref["manifest_sha256"])
        entry = next(c for c in template["case_inputs"] if c["patient_id"] == selected["patient_id"])
        if sha256(entry["support_path"]) != entry["support_sha256"]:
            raise ValueError("fixed support changed")
        support = np.load(entry["support_path"], allow_pickle=False)
        if support.dtype != np.bool_ or support.shape != (512, 512) or not support.all():
            raise ValueError("fixed full native FOV required")
        result = read_bound(record["result_path"], record["result_sha256"])
        upstream_input = next(c for c in prepared["records"] if c["case_index"] == i)
        if result["input_sha256"] != upstream_input["prepared_contract"]["input_sha256"]:
            raise ValueError("result input mismatch")
        scales = {"E1": {}, "E2": {}}
        assets = result["candidate_maps"]["assets"]
        expected_pairs = {}
        for scale in [16, 32, 64]:
            expected_pairs[("E1", str(scale))] = reconstruct_e1(result["E1"]["records"], scale)
        e2_score = np.zeros((224, 224), float); e2_reliable = np.zeros((224, 224), bool)
        for candidate in result["E2"]["candidates"]:
            indices = candidate["mask_flat_indices"]
            e2_reliable.flat[indices] = True
            e2_score.flat[indices] = np.maximum(e2_score.flat[indices], candidate["peak_gap"])
        if result["E2"]["status"] == "NO_FEASIBLE_MASK" and e2_reliable.any():
            raise ValueError("abstention has candidates")
        expected_pairs[("E2", "benchmark-4x4")] = (e2_score, e2_reliable)
        for (algorithm, scale), (model_score, model_reliable) in expected_pairs.items():
            prefix = f"E1-{scale}" if algorithm == "E1" else "E2-final"
            score_name = "response" if algorithm == "E1" else "cpf-gap-score"
            expected_native_score = model_score[np.ix_(lookup, lookup)]
            expected_native_reliable = model_reliable[np.ix_(lookup, lookup)]
            for name, expected_model, expected_native in [(score_name, model_score, expected_native_score),
                                                        ("reliable", model_reliable, expected_native_reliable)]:
                for grid, expected in [("model", expected_model), ("native", expected_native)]:
                    spec = assets[f"{prefix}-{name}-{grid}"]
                    if sha256(spec["path"]) != spec["sha256"]:
                        raise ValueError("candidate array hash mismatch")
                    saved = np.load(spec["path"], allow_pickle=False)
                    if saved.shape != expected.shape or not np.array_equal(saved, expected):
                        raise ValueError("candidate raw-record/inverse raster mismatch")
            specs = [s for s in result["candidate_maps"]["evaluation_native_npz"] if s["algorithm"] == algorithm and s["scale"] == scale]
            if len(specs) != 1 or sha256(specs[0]["path"]) != specs[0]["sha256"]:
                raise ValueError("bound prediction NPZ missing or altered")
            with np.load(specs[0]["path"], allow_pickle=False) as arrays:
                if (str(arrays["native_case_manifest_sha256"].item()) != case_ref["manifest_sha256"]
                        or str(arrays["SOPInstanceUID"].item()) != sop or int(arrays["native_slice_index"].item()) != index
                        or not np.array_equal(arrays["scores"], expected_native_score)
                        or not np.array_equal(arrays["reliable"], expected_native_reliable)):
                    raise ValueError("bound prediction NPZ/native identity mismatch")
                scales[algorithm][scale] = {"scores": arrays["scores"].copy(), "reliable": arrays["reliable"].copy()}
        key = tuple(entry["reference_key"])
        objects = []
        for obj in case["annotations"]:
            obj_key = (obj["raw_label"]["name"], obj["raw_annotation"].get("createdById"), obj["raw_label"]["label_group_id"], obj["raw_annotation"]["labelId"])
            if obj["status"] != "PASS" or obj["identity"]["SOPInstanceUID"] != sop or obj_key != key:
                continue
            mask_path = gt_path.parent / obj["mask_path"]
            if sha256(mask_path) != obj["mask_sha256"]:
                raise ValueError("GT mask changed")
            with Image.open(mask_path) as image:
                mask = np.asarray(image, bool)
            objects.append({"annotation_id": obj["annotation_id"], "reference_key": key, "mask": mask})
        for algorithm in ["E1", "E2"]:
            measured = evaluate_variant(scales[algorithm], objects, support, key, spacing_krc_mm=case["geometry"]["spacing_krc_mm"])
            output.append({"patient_id": selected["patient_id"], "case_index": i, "algorithm": algorithm,
                           "algorithm_status": result[algorithm]["status"], "actual_model_calls": result[algorithm]["model_calls"],
                           "SOPInstanceUID": sop, "native_slice_index": index, "reference_key": list(key),
                           "applicable_polygon_objects": len(objects), **measured})
        mapping_qa.append({"case_index": i, "status": "PASS", "checked_model_native_pairs": 8,
                           "checked_bound_prediction_npz": 4, "inverse_raster_max_error": 0,
                           "result_path": record["result_path"], "result_sha256": record["result_sha256"]})
    summaries = {}
    for algorithm, names in [("E1", ["16", "32", "64"]), ("E2", ["benchmark-4x4"])]:
        for fraction in BUDGETS:
            for scale in names:
                rows = []
                for case in [c for c in output if c["algorithm"] == algorithm]:
                    metric = case["budgets"][str(fraction)]["scales"][scale]
                    count = metric["candidate_voxels"]
                    rows.append({"patient_id": case["patient_id"], "status": "NO_RELIABLE_RESPONSE" if count == 0 else
                                 "PARTIAL_BUDGET" if count < int(262144 * fraction) else "OK",
                                 "observed_reference_coverage": metric["observed_reference_coverage"], "candidate_voxels": count})
                summaries[f"{algorithm}/{fraction}/{scale}"] = {**summarize_patients(rows),
                    "effective_candidate_rate": sum(r["candidate_voxels"] > 0 for r in rows) / 3,
                    "algorithm_status_counts": dict(Counter(c["algorithm_status"] for c in output if c["algorithm"] == algorithm))}
    return {"schema": "DATA_FIRST_REAL_E1E2_EVALUATION_V1", "status": "PARTIAL_REFERENCE_EVALUATED",
            "run_delivery_path": str(run_path), "run_delivery_sha256": run_sha,
            "request_template_sha256": template_sha, "prepared_mapping_qa_sha256": prepared_qa_sha,
            "candidate_inverse_mapping_status": "PASS", "mapping_qa": mapping_qa, "case_results": output,
            "patient_summaries": summaries, "model_forwards_by_DATA": 0,
            "F_factor_status": "DIRECT_OLD_CLASSIFIER_ONLY; F0/F1 factorial experiment NOT RUN",
            "E2_cross_scale_status": "final4x4 benchmark after7x7 PSMI only; separate raw-scale candidates NOT PUBLISHED",
            "complete_reference_metrics_eligible": False, "independent_test_eligible": False,
            "missing_reference_policy": "NULL_COVERAGE_NO_RESELECTION_UNKNOWN_NOT_NORMAL"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["run", "run-sha", "template", "template-sha", "prepared-qa", "prepared-qa-sha", "output"]:
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    result = evaluate_run(args.run, args.run_sha, args.template, args.template_sha, args.prepared_qa, args.prepared_qa_sha)
    with Path(args.output).open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False); stream.write("\n")
