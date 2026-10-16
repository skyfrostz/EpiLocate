"""Post-hoc frozen-map diagnostics, including locked equal-area random reference.

GT is read only for scoring. No model, candidate algorithm or parameter changes.
"""
import argparse
import json
from pathlib import Path
import resource
import time

import numpy as np
from PIL import Image

from .data_delivery import read_bound
from .data_eval import budget_candidates
from .gt_vnext import sha256


def coverage(mask, reference):
    total = int(reference.sum())
    return int((mask & reference).sum()) / total if total else None


def tie_diagnostic(scores, reliable, chosen, reference):
    if not chosen.any():
        return {"cutoff_score": None, "eligible_at_cutoff": 0, "selected_at_cutoff": 0,
                "cutoff_splits_plateau": False, "tie_rule": "descending score then native C-order flat index"}
    cutoff = float(scores[chosen].min())
    plateau = reliable & (scores == cutoff)
    return {"cutoff_score": cutoff, "eligible_at_cutoff": int(plateau.sum()),
            "selected_at_cutoff": int((chosen & plateau).sum()),
            "cutoff_splits_plateau": int((chosen & plateau).sum()) < int(plateau.sum()),
            "reference_pixels_at_cutoff": int((plateau & reference).sum()),
            "selected_reference_pixels_at_cutoff": int((plateau & chosen & reference).sum()),
            "tie_rule": "descending score then native C-order flat index"}


def distribution(values):
    a = np.asarray([v for v in values if v is not None], float)
    return {"n": len(a), "mean": float(a.mean()) if len(a) else None,
            "sample_sd": float(a.std(ddof=1)) if len(a) > 1 else None,
            "min": float(a.min()) if len(a) else None, "max": float(a.max()) if len(a) else None}


def diagnose(protocol_path, protocol_sha):
    started = time.perf_counter()
    protocol = read_bound(protocol_path, protocol_sha)
    if (protocol["status"] != "LOCKED_BEFORE_SAMPLING" or len(protocol["seeds"]) != 20
            or protocol["seeds"] != list(range(2026100900, 2026100920)) or protocol["new_model_forwards"] != 0):
        raise ValueError("random protocol changed")
    evaluation = read_bound(protocol["evaluation_path"], protocol["evaluation_sha256"])
    template = read_bound(protocol["template_path"], protocol["template_sha256"])
    gt_path = Path(template["gt_manifest_path"])
    gt = read_bound(gt_path, template["gt_manifest_sha256"])
    lock = read_bound(template["fixed_slice_lock_path"], template["fixed_slice_lock_sha256"])
    run = read_bound(evaluation["run_delivery_path"], evaluation["run_delivery_sha256"])
    records = []
    for selected in lock["slices"]:
        i = selected["case_index"]; pid = selected["patient_id"]
        entry = next(c for c in template["case_inputs"] if c["patient_id"] == pid)
        case_ref = next(c for c in gt["cases"] if c["patient_id"] == pid)
        case = read_bound(gt_path.parent / case_ref["manifest_path"], case_ref["manifest_sha256"])
        key = tuple(entry["reference_key"])
        masks = []; object_ids = []
        for obj in case["annotations"]:
            obj_key = (obj["raw_label"]["name"], obj["raw_annotation"].get("createdById"), obj["raw_label"]["label_group_id"], obj["raw_annotation"]["labelId"])
            if obj["status"] != "PASS" or obj["identity"]["SOPInstanceUID"] != selected["sop_uid"] or obj_key != key:
                continue
            path = gt_path.parent / obj["mask_path"]
            if sha256(path) != obj["mask_sha256"]:
                raise ValueError("GT changed")
            with Image.open(path) as image:
                masks.append(np.asarray(image, bool))
            object_ids.append(obj["annotation_id"])
        reference = np.logical_or.reduce(masks) if masks else np.zeros((512, 512), bool)
        support = np.ones((512, 512), bool)
        report = next(r for r in run["records"] if r["case_index"] == i)
        result = read_bound(report["result_path"], report["result_sha256"])
        random_cache = {}
        # Draw before scoring. One reusable permutation per fixed seed/case.
        permutations = {seed: np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed, i]))).permutation(262144)
                        for seed in protocol["seeds"]}
        for spec in result["candidate_maps"]["evaluation_native_npz"]:
            if sha256(spec["path"]) != spec["sha256"]:
                raise ValueError("prediction changed")
            with np.load(spec["path"], allow_pickle=False) as arrays:
                if str(arrays["SOPInstanceUID"].item()) != selected["sop_uid"]:
                    raise ValueError("fixed SOP mismatch")
                scores, reliable = arrays["scores"].copy(), arrays["reliable"].copy()
            values = scores[reference]
            quantiles = dict(zip(["0", "10", "25", "50", "75", "90", "100"],
                                 [float(x) for x in np.quantile(values, [0, .1, .25, .5, .75, .9, 1])])) if len(values) else None
            positive = scores > 0
            before = coverage(reliable, reference)
            for fraction in [.05, .10, .20]:
                chosen = budget_candidates(scores, reliable, support, fraction)
                count = int(chosen.sum())
                measured = next(c for c in evaluation["case_results"] if c["case_index"] == i and c["algorithm"] == spec["algorithm"])
                original = measured["budgets"][str(fraction)]["scales"][spec["scale"]]
                after = coverage(chosen, reference)
                if count != original["candidate_voxels"] or after != original["observed_reference_coverage"]:
                    raise ValueError("frozen evaluation no longer reproduces")
                if count not in random_cache:
                    trials = []
                    for seed, permutation in permutations.items():
                        random_mask = np.zeros(262144, bool); random_mask[permutation[:count]] = True
                        random_mask = random_mask.reshape(512, 512)
                        trials.append({"seed": seed, "actual_area_pixels": count,
                                       "observed_reference_coverage": coverage(random_mask, reference),
                                       "polygon_objects_hit": sum(bool((random_mask & mask).any()) for mask in masks)})
                    random_cache[count] = trials
                trials = random_cache[count]
                records.append({"case_index": i, "patient_id": pid, "algorithm": spec["algorithm"], "scale": spec["scale"],
                    "budget_fraction": fraction, "native_slice_index": selected["native_slice_index_zero_based"],
                    "reference_key": list(key), "reference_union_pixels": int(reference.sum()),
                    "reference_sum_instance_pixels": sum(int(m.sum()) for m in masks), "reference_objects": len(masks),
                    "reference_area_mm2": int(reference.sum()) * float(np.prod(case["geometry"]["spacing_krc_mm"][1:])),
                    "reliable_candidate_pixels": int(reliable.sum()), "actual_selected_pixels": count,
                    "actual_selected_fraction": count / 262144, "budget_cap_pixels": int(262144 * fraction),
                    "selected_area_mm2": original["per_sop_candidate_area_mm2"][0],
                    "GT_raw_response_quantiles": quantiles,
                    "GT_positive_response_coverage": coverage(positive, reference),
                    "before_budget_reliable_reference_coverage": before, "after_budget_reference_coverage": after,
                    "reference_coverage_removed_by_budget": before - after if before is not None else None,
                    "selected_polygon_objects_hit": original["annotation_units_hit"],
                    "tie_diagnostic": tie_diagnostic(scores, reliable, chosen, reference),
                    "random_equal_actual_area_trials": trials,
                    "random_reference_coverage": distribution([t["observed_reference_coverage"] for t in trials]),
                    "random_polygon_object_hits": distribution([t["polygon_objects_hit"] for t in trials]),
                    "model_to_native_mapping": "halfpixel224/512; floor((native_index+.5)*224/512); independentQA PASS",
                    "score_semantics": "raw fixed-target margin response" if spec["algorithm"] == "E1" else
                        "final CPF retained score; zero does not describe rejected optimization mask response",
                    "diagnostic_type": "POST_HOC_GT_GUIDED_SCORING_NOT_CANDIDATE_GENERATION"})
                if time.perf_counter() - started > protocol["cpu_wall_budget_seconds"]:
                    raise TimeoutError("locked diagnostic CPU wall budget exceeded")
    patient_means = {}
    for algorithm, scales in [("E1", ["16", "32", "64"]), ("E2", ["benchmark-4x4"])]:
        for fraction in [.05, .10, .20]:
            for scale in scales:
                rows = [r for r in records if r["algorithm"] == algorithm and r["scale"] == scale and r["budget_fraction"] == fraction]
                if len(rows) != 3:
                    raise ValueError("three patient denominator lost")
                means = [distribution([r["random_equal_actual_area_trials"][j]["observed_reference_coverage"] for r in rows])["mean"]
                         for j in range(20)]
                patient_means[f"{algorithm}/{fraction}/{scale}"] = {
                    "patients_expected": 3, "actual_patient_equal_mean_coverage": distribution([r["after_budget_reference_coverage"] for r in rows])["mean"],
                    "random_patient_equal_mean_coverage": distribution(means)}
    return {"schema": "DATA_EVAL_DIAGNOSTIC_V2", "status": "COMPLETED_FROZEN_MAP_DIAGNOSTIC",
            "protocol_path": str(protocol_path), "protocol_sha256": protocol_sha, "evaluation_sha256": protocol["evaluation_sha256"],
            "records": records, "patient_equal_summaries": patient_means, "seeds": protocol["seeds"],
            "clinical_significance": "NOT_TESTED_NO_PVALUES", "completeDiceIoUFP": None,
            "scope": "3 already observed train slices; fullFOV uniform pixel reference is not anatomical baseline",
            "cost": {"wall_seconds": time.perf_counter() - started, "peak_rss_bytes_macos": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                     "forward_calls": 0, "backward_calls": 0, "MPS": "NOT_RUN", "native_HU_reads": 0}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--protocol-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = diagnose(args.protocol, args.protocol_sha)
    raw = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if len(raw.encode()) > 5242880:
        raise ValueError("diagnostic output budget exceeded")
    with args.output.open("x") as stream:
        stream.write(raw)
