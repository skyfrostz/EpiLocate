#!/usr/bin/env python3
"""Compare verified D10 CUDA factor attempts with the unadjusted CUDA baseline.

Successful captures and failed attempts are retained individually. Single-factor
flag deltas are checked separately from the disclosed combined research mode.
Results are diagnostic and never grant D10 PASS or training authorization.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

try:
    from . import d10_three_way_compare as numerical
except ImportError:  # Direct invocation from outside the repository.
    import d10_three_way_compare as numerical

SINGLE_FACTORS = ("tf32-off", "deterministic-on", "benchmark-off", "amp-off")
MODES = frozenset((*SINGLE_FACTORS, "research"))
RESEARCH_SEED = 20260925
BASELINE_RUN_ID = "RUN-D10-CUDA-BASELINE"
RESEARCH_FLAGS = {
    "cuda_matmul_allow_tf32": False,
    "cudnn_allow_tf32": False,
    "cudnn_benchmark": False,
    "cudnn_deterministic": True,
    "torch_deterministic_algorithms": True,
    "float32_matmul_precision": "highest",
    "autocast_cpu": False,
    "autocast_cuda": False,
    "amp_used_by_tool": False,
    "cublas_workspace_config": ":4096:8",
}
ALLOWED_FLAG_CHANGES = {
    "tf32-off": frozenset(("cuda_matmul_allow_tf32", "cudnn_allow_tf32", "float32_matmul_precision")),
    "deterministic-on": frozenset(("torch_deterministic_algorithms",)),
    "benchmark-off": frozenset(("cudnn_benchmark",)),
    "amp-off": frozenset(),
    "research": frozenset(RESEARCH_FLAGS),
}
SHARED_FIELDS = (
    "input_sha256", "checkpoint_sha256", "config_sha256", "source_sha256", "small_reference_positions",
    "layer_order", "base_sha", "audit_script_sha256", "position_691", "formal_batch_size", "mask_fill",
    "grid_counts", "probability_computation_device", "frozen_tolerance",
)


@dataclass
class FactorRecord:
    metadata: dict[str, Any]
    record_sha256: str
    capture: numerical.VerifiedCapture | None
    context: dict[str, Any]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise numerical.CaptureValidationError(message)


def _differences(before: Any, after: Any, prefix: str = "") -> list[dict[str, Any]]:
    """Record actual values and missing fields instead of hiding extra flags."""
    if isinstance(before, dict) and isinstance(after, dict):
        result = []
        for key in sorted(before.keys() | after.keys()):
            name = f"{prefix}.{key}" if prefix else key
            if key not in before or key not in after:
                result.append({"field": name, "before": before.get(key), "after": after.get(key),
                               "before_present": key in before, "after_present": key in after})
            else:
                result.extend(_differences(before[key], after[key], name))
        return result
    if type(before) is not type(after) or before != after:
        return [{"field": prefix, "before": before, "after": after,
                 "before_present": True, "after_present": True}]
    return []


def _validate_provenance(metadata: dict[str, Any], baseline: numerical.VerifiedCapture,
                         *, complete: bool) -> bool:
    digest = metadata.get("baseline_capture_sha256")
    if digest is None and not complete:
        return False
    _require(digest == baseline.manifest_sha256, "factor baseline_capture_sha256 does not match verified baseline")
    return True


def _expected_before(baseline: numerical.VerifiedCapture, mode: str) -> dict[str, Any]:
    expected = copy.deepcopy(baseline.metadata["environment"])
    if mode == "research":
        expected["precision_flags"]["cublas_workspace_config"] = RESEARCH_FLAGS["cublas_workspace_config"]
    return expected


def _validate_effective_environment(baseline: numerical.VerifiedCapture, mode: str,
                                    before: dict[str, Any], effective: dict[str, Any]) -> dict[str, Any]:
    numerical._validate_environment(before, "C", "CUDA")
    numerical._validate_environment(effective, "C", "CUDA")
    _require(before == _expected_before(baseline, mode),
             f"{mode}: environment_before_adjustment differs from verified unadjusted baseline")
    deltas = _differences(baseline.metadata["environment"], effective)
    allowed = {f"precision_flags.{name}" for name in ALLOWED_FLAG_CHANGES[mode]}
    confounds = [delta["field"] for delta in deltas if delta["field"] not in allowed]
    _require(not confounds, f"{mode}: unrelated environment changes: {confounds}")
    flags = effective["precision_flags"]
    if mode == "tf32-off":
        _require(flags["cuda_matmul_allow_tf32"] is False and flags["cudnn_allow_tf32"] is False,
                 "tf32-off: both TF32 flags must actually be false")
        precision_delta = next((item for item in deltas if item["field"] == "precision_flags.float32_matmul_precision"), None)
        if precision_delta is not None:
            _require(flags["float32_matmul_precision"] == "highest",
                     "tf32-off: unexpected matmul precision change; only the effective TF32-off highest setting is allowed")
    elif mode == "deterministic-on":
        _require(flags["torch_deterministic_algorithms"] is True,
                 "deterministic-on: deterministic algorithms must actually be enabled")
    elif mode == "benchmark-off":
        _require(flags["cudnn_benchmark"] is False, "benchmark-off: cuDNN benchmark must actually be disabled")
    elif mode == "amp-off":
        _require(not flags["autocast_cpu"] and not flags["autocast_cuda"] and not flags["amp_used_by_tool"],
                 "amp-off: recorded AMP/autocast must actually be off")
    else:
        for name, expected in RESEARCH_FLAGS.items():
            _require(flags[name] == expected, f"research: documented research flag {name} differs")
    direct = {
        "tf32-off": {"cuda_matmul_allow_tf32", "cudnn_allow_tf32"},
        "deterministic-on": {"torch_deterministic_algorithms"},
        "benchmark-off": {"cudnn_benchmark"}, "amp-off": set(), "research": set(RESEARCH_FLAGS),
    }[mode]
    direct_deltas = [delta for delta in deltas if delta["field"].removeprefix("precision_flags.") in direct]
    property_side_effects = [delta for delta in deltas if delta not in direct_deltas]
    return {
        "environment_verified_against_baseline": True, "actual_environment_deltas": deltas,
        "direct_factor_flag_deltas": direct_deltas, "related_property_deltas": property_side_effects,
        "effective_flag_change_observed": bool(deltas), "baseline_already_had_requested_flags": not direct_deltas,
        "explicit_amp_off_scope": mode in ("amp-off", "research"),
        "scope_evidence": "Verified capture mode and matching audit-script hash; explicit autocast(enabled=False) scope does not change the ambient flags."
                          if mode in ("amp-off", "research") else None,
        "interpretation": "Combined, disclosed research settings; never a single-factor isolation." if mode == "research" else
                          "No runtime flag delta; this attempt cannot isolate an effect of changing a flag." if not deltas else
                          "Single requested factor; related effective matmul precision changes are recorded as property side effects.",
    }


def _validate_capture_shared(baseline: numerical.VerifiedCapture, capture: numerical.VerifiedCapture) -> None:
    for name in SHARED_FIELDS:
        _require(name in baseline.metadata and name in capture.metadata, f"shared capture field {name} is required")
        _require(capture.metadata[name] == baseline.metadata[name], f"factor shared {name} mismatch")
    _require(numerical._shared_model_identity(capture.metadata["model_identity"]) ==
             numerical._shared_model_identity(baseline.metadata["model_identity"]), "factor runtime model identity mismatch")
    _require(capture.arrays.keys() == baseline.arrays.keys(), "factor tensor key set mismatch")
    for key, array in capture.arrays.items():
        reference = baseline.arrays[key]
        _require(array.shape == reference.shape and array.dtype == reference.dtype,
                 f"factor tensor shape/dtype mismatch at {key}")
    for key in [f"preprocessing/{name}" for name in numerical.PREPROCESSING] + [
        f"{sample}/input" for sample in numerical.SAMPLES
    ] + ["small_reference/masked_tensors"]:
        _require(np.array_equal(capture.arrays[key], baseline.arrays[key]),
                 f"factor input/preprocessing changed at {key}; a precision-only comparison is confounded")


def _resolve_record(path: str | Path) -> tuple[Path, bool]:
    location = Path(path)
    if location.is_dir():
        capture = location / "capture.json"
        failure = location / "failure.json"
        _require(not (capture.exists() and failure.exists()), "ambiguous factor directory has capture and failure; select a record explicitly")
        return (capture, False) if capture.exists() else (failure, True)
    _require(location.name in ("capture.json", "failure.json"), "factor must be a capture directory, capture.json, or failure.json")
    return location, location.name == "failure.json"


def _read_record(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise numerical.CaptureValidationError(f"cannot read factor record: {error}") from error
    _require(isinstance(value, dict), "factor record must be a JSON object")
    return value


def _load_record(path: str | Path, baseline: numerical.VerifiedCapture) -> FactorRecord:
    record_path, failure = _resolve_record(path)
    metadata = _read_record(record_path)
    mode = metadata.get("mode")
    _require(isinstance(mode, str) and mode in MODES, "factor mode must identify one approved factor or disclosed research combination")
    _require(metadata.get("lane") == "C", "factor record must be CUDA lane C")
    _require(isinstance(metadata.get("run_id"), str) and bool(metadata["run_id"]), "factor run_id required")
    digest = numerical.file_sha256(record_path)
    if not failure:
        capture = numerical.load_capture(record_path.parent, "C")
        _require(capture.manifest_sha256 == digest, "factor manifest changed during validation")
        _require(metadata.get("status") == "CAPTURED_NOT_D10_PASS", "factor capture must retain diagnostic capture status")
        _validate_provenance(metadata, baseline, complete=True)
        _validate_capture_shared(baseline, capture)
        _require(isinstance(metadata.get("environment_before_adjustment"), dict), "factor pre-adjustment environment required")
        context = _validate_effective_environment(baseline, mode, metadata["environment_before_adjustment"], metadata["environment"])
        _require("seed" in metadata and metadata["seed"] == (RESEARCH_SEED if mode == "research" else baseline.metadata.get("seed")),
                 f"{mode}: documented seed differs from required configuration")
        if mode in SINGLE_FACTORS:
            _require(not metadata.get("factor_capture_sha256") and not metadata.get("factor_attempt_status"),
                     f"{mode}: a single factor cannot claim combined factor provenance")
        context["adjusted_attempt_verified"] = True
        return FactorRecord(metadata, digest, capture, context)
    _require(metadata.get("schema") == "D10_ATTEMPT_V1" and metadata.get("status") == "FAILED", "failure record must be an explicit failed D10 attempt")
    _require(isinstance(metadata.get("error"), str) and isinstance(metadata.get("error_type"), str), "failed attempt must retain error and error_type")
    proven = _validate_provenance(metadata, baseline, complete=False)
    for name in ("input_sha256", "checkpoint_sha256", "audit_script_sha256", "base_sha"):
        if name in metadata:
            _require(metadata[name] == baseline.metadata[name], f"failed factor shared {name} mismatch")
    before, flags = metadata.get("environment_before_adjustment"), metadata.get("effective_precision_flags")
    context = {"baseline_provenance_verified": proven, "adjusted_attempt_verified": False,
               "environment_verified_against_baseline": False,
               "interpretation": "Incomplete failed attempt retained; no numeric result or factor effect is inferred."}
    if before is not None:
        _require(isinstance(before, dict), "failed factor pre-adjustment environment must be a map")
        numerical._validate_environment(before, "C", "CUDA")
        _require(before == _expected_before(baseline, mode), f"failed {mode}: pre-adjustment environment confound")
    if flags is not None:
        _require(isinstance(flags, dict) and isinstance(before, dict), "effective failure flags require recorded pre-adjustment environment")
        effective = {**before, "precision_flags": flags}
        context.update(_validate_effective_environment(baseline, mode, before, effective))
        context["baseline_provenance_verified"] = proven
        context["adjusted_attempt_verified"] = proven and metadata.get("audit_script_sha256") == baseline.metadata["audit_script_sha256"]
        context["interpretation"] = "Actual adjusted attempt failed; no successful numerical comparison exists." if context["adjusted_attempt_verified"] else "Incomplete failed attempt retained; baseline linkage or audit-script evidence is missing."
    if mode == "research" and "seed" in metadata:
        _require(metadata["seed"] == RESEARCH_SEED, "failed research: documented seed differs from required configuration")
    return FactorRecord(metadata, digest, None, context)


def _validate_research_provenance(record: FactorRecord, records: list[FactorRecord]) -> dict[str, Any]:
    metadata = record.metadata
    hashes = metadata.get("factor_capture_sha256")
    _require(isinstance(hashes, list) and len(hashes) == 4 and all(numerical._valid_sha256(item) for item in hashes) and len(set(hashes)) == 4,
             "research requires exactly four distinct provided single-factor record hashes")
    by_hash = {item.record_sha256: item for item in records}
    referenced = []
    for digest in hashes:
        _require(digest in by_hash, "research references a missing single-factor attempt")
        item = by_hash[digest]
        _require(item.metadata["mode"] in SINGLE_FACTORS, "research provenance cannot reference another combined research run")
        _require(item.context["adjusted_attempt_verified"], "research references an incomplete, unverified factor attempt")
        referenced.append(item)
    _require({item.metadata["mode"] for item in referenced} == set(SINGLE_FACTORS), "research requires each of the four single factors")
    actual_status = [{"mode": item.metadata["mode"], "status": item.metadata["status"]} for item in referenced]
    _require(metadata.get("factor_attempt_status") == actual_status, "research factor-attempt statuses differ from preserved records")
    return {"single_factor_provenance_verified": True, "factor_attempts": [
        {"mode": item.metadata["mode"], "record_sha256": item.record_sha256,
         "status": item.metadata["status"], "successful_capture": item.capture is not None} for item in referenced
    ]}


def _capture_deltas(baseline: numerical.VerifiedCapture, capture: numerical.VerifiedCapture) -> dict[str, Any]:
    reference, variant = baseline.arrays, capture.arrays
    preprocessing = [f"preprocessing/{name}" for name in numerical.PREPROCESSING]
    keys = preprocessing + sorted(reference.keys() - set(preprocessing))
    metrics = {key: numerical.numeric_metrics(reference[key], variant[key]) for key in keys}
    probability_keys = [f"{sample}/probability" for sample in numerical.SAMPLES] + [
        "small_reference/probabilities_batch1", "small_reference/probabilities_formal",
    ]
    probability = {key: numerical._positive_metrics(reference[key], variant[key]) for key in probability_keys}
    layers = {}
    for sample in numerical.SAMPLES:
        rows = [{"layer": layer, **metrics[f"{sample}/{layer}"]} for layer in numerical.LAYERS]
        layers[sample] = {"layers": rows, **numerical._layer_summary(rows)}
    target = {}
    for sample in ("position_691_batch1", "position_691_batch32"):
        target[sample] = {
            "baseline_logits": reference[f"{sample}/logits"].tolist(), "variant_logits": variant[f"{sample}/logits"].tolist(),
            "logit_delta": metrics[f"{sample}/logits"],
            "baseline_positive_probability": float(reference[f"{sample}/probability"][1]),
            "variant_positive_probability": float(variant[f"{sample}/probability"][1]),
            "positive_probability_delta": probability[f"{sample}/probability"],
            "baseline_masked_tensor_sha256": baseline.metadata["tensors"][f"{sample}/input"]["sha256"],
            "variant_masked_tensor_sha256": capture.metadata["tensors"][f"{sample}/input"]["sha256"],
        }
    maximum = max(item["max_abs_diff"] for item in probability.values())
    return {
        "tensors": metrics, "positive_probability": probability, "layerwise": layers,
        "position_691": {"position": baseline.metadata["position_691"], "samples": target},
        "captured_probability_delta_summary": {"max_abs_diff": maximum, "tolerance": numerical.FROZEN_TOLERANCE,
                                               "within_frozen_probability_tolerance": maximum <= numerical.FROZEN_TOLERANCE,
                                               "scope": "Variant CUDA vs baseline CUDA captures only; no CPU/GPU retest or D10 PASS assertion."},
        "baseline_batch_size_and_repeatability": numerical._batch_and_repeatability(baseline),
        "variant_batch_size_and_repeatability": numerical._batch_and_repeatability(capture),
    }


def compare_factors(baseline_path: str | Path, factor_paths: list[str | Path]) -> dict[str, Any]:
    baseline_location = Path(baseline_path)
    if baseline_location.name == "capture.json":
        baseline_location = baseline_location.parent
    baseline = numerical.load_capture(baseline_location, "C")
    metadata = baseline.metadata
    _require(metadata.get("mode") == "baseline" and metadata.get("run_id") == BASELINE_RUN_ID,
             f"baseline must be the unadjusted {BASELINE_RUN_ID} CUDA capture")
    _require(metadata.get("status") == "CAPTURED_NOT_D10_PASS", "baseline capture status must remain diagnostic")
    _require(metadata.get("baseline_capture_sha256") is None and not metadata.get("factor_capture_sha256"),
             "baseline must precede factor adjustments")
    _require(metadata.get("seed") is None, "unadjusted baseline must not use a research seed")
    _require(metadata.get("environment_before_adjustment") == metadata["environment"], "baseline was adjusted during capture")
    _require(all(name in metadata for name in SHARED_FIELDS), "baseline shared scientific/provenance fields are incomplete")
    _require(numerical._valid_sha256(metadata.get("audit_script_sha256")), "baseline capture audit-script SHA-256 required")
    _require(metadata.get("frozen_tolerance") == numerical.FROZEN_TOLERANCE, "baseline frozen tolerance changed")
    _require(bool(factor_paths), "at least one factor attempt must be provided")
    records = [_load_record(path, baseline) for path in factor_paths]
    _require(len({item.record_sha256 for item in records}) == len(records), "duplicate factor record supplied")
    rows = []
    for record in records:
        mode = record.metadata["mode"]
        row = {
            "mode": mode, "run_id": record.metadata["run_id"], "record_sha256": record.record_sha256,
            "record_status": record.metadata["status"],
            "comparison_kind": "DISCLOSED_COMBINED_RESEARCH_CONFIGURATION" if mode == "research" else "SINGLE_FACTOR_ATTEMPT",
            "baseline_capture_sha256": record.metadata.get("baseline_capture_sha256"),
            "configuration_validation": record.context, "successful_capture": record.capture is not None,
            "documented_seed": record.metadata.get("seed"), "numeric_comparison": None,
            "root_cause": "NOT_ESTABLISHED_BY_FACTOR_COMPARISON_ALONE", "d10_pass_asserted": False,
        }
        if mode == "research" and record.capture is not None:
            row["combined_research_provenance"] = _validate_research_provenance(record, records)
        elif mode == "research":
            seed_recorded = record.metadata.get("seed") == RESEARCH_SEED
            factor_provenance_recorded = "factor_capture_sha256" in record.metadata and "factor_attempt_status" in record.metadata
            if factor_provenance_recorded:
                row["combined_research_provenance"] = _validate_research_provenance(record, records)
            else:
                row["combined_research_provenance"] = {"single_factor_provenance_verified": False,
                                                     "reason": "Failed research attempt did not record prior factor hashes/statuses."}
            row["combined_research_provenance"]["seed_provenance_verified"] = seed_recorded
            row["combined_research_provenance"]["configuration_fully_documented"] = seed_recorded and factor_provenance_recorded
        if record.capture is not None:
            row["numeric_comparison"] = _capture_deltas(baseline, record.capture)
            row["attempt_interpretation"] = "SUCCESSFUL_DIAGNOSTIC_CAPTURE"
        else:
            row["failure_evidence"] = record.metadata
            row["attempt_interpretation"] = "TESTED_ATTEMPT_FAILED" if record.context["adjusted_attempt_verified"] else "INCOMPLETE_ATTEMPT_FAILED"
        rows.append(row)
    present = {item.metadata["mode"] for item in records if item.metadata["mode"] in SINGLE_FACTORS}
    tested = {item.metadata["mode"] for item in records if item.metadata["mode"] in SINGLE_FACTORS and item.context["adjusted_attempt_verified"]}
    return {
        "schema": "D10_FACTOR_ISOLATION_MATRIX_V1", "status": "DIAGNOSTIC_FACTOR_COMPARISON_COMPLETE",
        "baseline": {"manifest_sha256": baseline.manifest_sha256, "run_id": metadata["run_id"],
                     "environment": metadata["environment"], "verified_tensor_count": len(baseline.arrays),
                     "source_sha256": metadata["source_sha256"], "config_sha256": metadata["config_sha256"],
                     "input_sha256": metadata["input_sha256"], "checkpoint_sha256": metadata["checkpoint_sha256"]},
        "attempts": rows, "single_factor_coverage": {"provided_modes": sorted(present), "verified_tested_modes": sorted(tested),
                                                     "missing_modes": sorted(set(SINGLE_FACTORS) - present),
                                                     "all_four_adjusted_attempts_verified": tested == set(SINGLE_FACTORS)},
        "frozen_tolerance": numerical.FROZEN_TOLERANCE, "root_cause": "NOT_ESTABLISHED_BY_FACTOR_COMPARISON_ALONE",
        "d10_pass_asserted": False, "formal_cuda_research_authorized": False, "stage_b_training": "NOT_AUTHORIZED",
        "interpretation": "Failed and no-op attempts remain visible. Numerical deltas are CUDA baseline vs variant only; combined settings are separately disclosed.",
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--factor", type=Path, action="append", required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.out_dir.exists():
        parser.error("output directory already exists; preserve evidence and select a new directory")
    try:
        result = compare_factors(args.baseline, args.factor)
        serialized = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    except (numerical.CaptureValidationError, ValueError) as error:
        parser.error(str(error))
    try:
        args.out_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
        descriptor = os.open(args.out_dir / "factor_isolation_matrix.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(serialized)
    except OSError as error:
        parser.error(f"cannot preserve factor comparison output: {error}")
    print(json.dumps({"status": result["status"], "attempt_count": len(result["attempts"]),
                      "successful_capture_count": sum(item["successful_capture"] for item in result["attempts"]),
                      "d10_pass_asserted": False}, sort_keys=True))


if __name__ == "__main__":
    main()
