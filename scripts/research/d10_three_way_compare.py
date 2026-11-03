#!/usr/bin/env python3
"""Verify and compare the three synthetic D10 capture lanes without model imports.

This module reads reviewed numeric .npy captures, never image/GT/checkpoint files.
Layer thresholds are diagnostics. Probability compatibility is one prerequisite
for D10, and this tool never grants D10 PASS or research authorization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

FROZEN_TOLERANCE = 0.0001
EXPECTED_INPUT_SHA256 = "8e73851ac16215180f7a3e17d72c85814886fa25ef62fbfbc618686dc8df54ee"
EXPECTED_CHECKPOINT_SHA256 = "548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734"
LAYERS = (
    "input", "conv1", "layer1.0", "layer1.1", "layer2.0", "layer2.1",
    "layer3.0", "layer3.1", "layer4.0", "layer4.1", "avgpool", "fc", "logits", "probability",
)
SAMPLES = ("baseline", "position_691_batch1", "position_691_batch32")
PREPROCESSING = ("raw", "hu", "windowed", "normalized", "resized", "tensor")
SMALL_REFERENCE = (
    "masked_tensors", "logits_batch1", "probabilities_batch1", "logits_formal", "probabilities_formal",
)
REPEATABILITY = ("baseline", "position_691_batch1", "position_691_formal")
ENVIRONMENT_FIELDS = (
    "os", "python", "torch", "torchvision", "numpy", "pydicom", "cuda_runtime", "driver",
    "cudnn_version", "gpu_model", "gpu_compute_capability", "cpu_model", "device",
    "input_dtype", "model_dtype", "precision_flags",
)
FLAG_FIELDS = (
    "cuda_matmul_allow_tf32", "cudnn_allow_tf32", "cudnn_benchmark", "cudnn_deterministic",
    "torch_deterministic_algorithms", "float32_matmul_precision", "autocast_cpu",
    "autocast_cuda", "amp_used_by_tool", "cublas_workspace_config",
)
IDENTITY_FIELDS = (
    "architecture", "parameter_count", "state_dict_key_count", "state_dict_keys_sha256",
    "state_dict_values_sha256", "eval", "dtype",
)
DEVICE_PLACEMENT_FIELDS = frozenset(("device", "input_device", "model_device"))


class CaptureValidationError(ValueError):
    """A capture lacks required evidence or is inconsistent with that evidence."""


@dataclass
class VerifiedCapture:
    metadata: dict[str, Any]
    arrays: dict[str, np.ndarray]
    manifest_sha256: str


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(array: np.ndarray) -> str:
    """Match the established D10 dtype/shape/C-order canonical tensor hash."""
    value = np.ascontiguousarray(array)
    header = json.dumps({"dtype": str(value.dtype), "shape": list(value.shape)}, sort_keys=True).encode()
    return hashlib.sha256(header + b"\n" + value.tobytes(order="C")).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CaptureValidationError(message)


def _valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _hash_map(value: Any, label: str) -> None:
    _require(isinstance(value, dict) and bool(value), f"{label}: nonempty hash map required")
    for name, digest in value.items():
        _require(isinstance(name, str) and bool(name), f"{label}: invalid hash name")
        _require(_valid_sha256(digest), f"{label}/{name}: invalid SHA-256")


def _without_device_placement(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key not in DEVICE_PLACEMENT_FIELDS}


def _shared_model_identity(value: dict[str, Any]) -> dict[str, Any]:
    # The frozen top-level checkpoint is mandatory; older captures may omit its
    # redundant nested copy, which is verified separately when present.
    return {key: item for key, item in _without_device_placement(value).items() if key != "checkpoint_sha256"}


def _required_keys() -> set[str]:
    return (
        {f"preprocessing/{name}" for name in PREPROCESSING}
        | {f"{sample}/{layer}" for sample in SAMPLES for layer in LAYERS}
        | {f"small_reference/{name}" for name in SMALL_REFERENCE}
        | {f"repeatability/{name}" for name in REPEATABILITY}
    )


def expected_small_reference_positions() -> list[dict[str, int]]:
    """The approved 68 entries, in per-scale frozen grid order."""
    positions = []
    for scale, indexes in ((16, range(672, 704)), (32, range(32)), (64, range(32, 36))):
        stride = scale // 2
        side = (224 - scale) // stride + 1
        for index in indexes:
            positions.append({"index": index, "scale": scale,
                              "x": (index % side) * stride, "y": (index // side) * stride})
    return positions


def _validate_environment(environment: Any, lane: str, device: str) -> None:
    _require(isinstance(environment, dict), f"lane {lane}: environment map required")
    missing = set(ENVIRONMENT_FIELDS) - environment.keys()
    _require(not missing, f"lane {lane}: missing environment fields {sorted(missing)}")
    _require(environment["device"] == device, f"lane {lane}: environment device mismatch")
    for name in ("os", "python", "torch", "torchvision", "numpy", "pydicom", "cpu_model"):
        _require(isinstance(environment[name], str) and bool(environment[name]), f"lane {lane}: {name} is not recorded")
    for name in ("input_dtype", "model_dtype"):
        _require(environment[name] in ("float32", "torch.float32"), f"lane {lane}: {name} must be float32")
    flags = environment["precision_flags"]
    _require(isinstance(flags, dict), f"lane {lane}: precision_flags map required")
    missing_flags = set(FLAG_FIELDS) - flags.keys()
    _require(not missing_flags, f"lane {lane}: missing precision flags {sorted(missing_flags)}")
    for name in FLAG_FIELDS:
        if name not in ("float32_matmul_precision", "cublas_workspace_config"):
            _require(type(flags[name]) is bool, f"lane {lane}: {name} must record an actual boolean")
    _require(flags["float32_matmul_precision"] in ("highest", "high", "medium"), f"lane {lane}: matmul precision not recorded")
    _require(flags["cublas_workspace_config"] is None or isinstance(flags["cublas_workspace_config"], str),
             f"lane {lane}: invalid CUBLAS_WORKSPACE_CONFIG")
    if lane in ("B", "C"):
        _require(_valid_sha256(environment.get("node_fingerprint")), f"lane {lane}: hashed node_fingerprint required")
        for name in ("cuda_runtime", "driver", "cudnn_version", "gpu_model", "gpu_compute_capability"):
            _require(environment[name] is not None and environment[name] != "", f"lane {lane}: GPU runtime field {name} is not recorded")
        model_name = str(environment["gpu_model"]).lower().replace(" ", "")
        _require("rtx3090" in model_name and "3090ti" not in model_name,
                 f"lane {lane}: approved RTX 3090 required; hardware substitution is not authorized")
    elif "node_fingerprint" in environment:
        _require(_valid_sha256(environment["node_fingerprint"]), f"lane {lane}: invalid hashed node_fingerprint")


def _validate_model(identity: Any, lane: str) -> None:
    _require(isinstance(identity, dict), f"lane {lane}: runtime model_identity map required")
    missing = set(IDENTITY_FIELDS) - identity.keys()
    _require(not missing, f"lane {lane}: missing model identity fields {sorted(missing)}")
    for name in ("state_dict_keys_sha256", "state_dict_values_sha256"):
        _require(_valid_sha256(identity[name]), f"lane {lane}: {name} not recorded")
    if "checkpoint_sha256" in identity:
        _require(identity["checkpoint_sha256"] == EXPECTED_CHECKPOINT_SHA256, f"lane {lane}: model checkpoint differs")
    _require(identity["eval"] is True, f"lane {lane}: model must be in eval mode")
    _require(identity["dtype"] in ("float32", "torch.float32"), f"lane {lane}: model identity dtype must be float32")
    _require(isinstance(identity["architecture"], str) and bool(identity["architecture"]), f"lane {lane}: architecture not recorded")
    for name in ("parameter_count", "state_dict_key_count"):
        _require(type(identity[name]) is int and identity[name] > 0, f"lane {lane}: {name} must be positive")
    for name in ("batchnorm_training_count", "dropout_training_count"):
        if name in identity:
            _require(identity[name] == 0, f"lane {lane}: training-state modules detected")


def _validate_positions(value: Any, lane: str) -> int:
    _require(isinstance(value, list) and bool(value), f"lane {lane}: small_reference_positions required")
    seen = set()
    for position in value:
        _require(isinstance(position, dict), f"lane {lane}: invalid reference position")
        _require(set(("index", "scale", "x", "y")) <= position.keys(), f"lane {lane}: incomplete reference position")
        _require(all(type(position[key]) is int and position[key] >= 0 for key in ("index", "scale", "x", "y")),
                 f"lane {lane}: invalid position coordinates")
        _require(position["scale"] in (16, 32, 64), f"lane {lane}: unexpected occlusion scale")
        identifier = (position["scale"], position["index"])
        _require(identifier not in seen, f"lane {lane}: duplicate reference position")
        seen.add(identifier)
    targets = [i for i, pos in enumerate(value) if (pos["scale"], pos["index"]) == (16, 691)]
    _require(len(targets) == 1, f"lane {lane}: position 691 at scale 16 required once")
    target = value[targets[0]]
    _require((target["x"], target["y"]) == (128, 200), f"lane {lane}: historical position 691 coordinates mismatch")
    _require(value == expected_small_reference_positions(),
             f"lane {lane}: expected exactly the approved 68 reference positions in frozen grid order")
    return targets[0]


def load_capture(directory: str | Path, expected_lane: str) -> VerifiedCapture:
    """Load only a complete capture after checking every referenced tensor hash."""
    root = Path(directory).resolve()
    manifest = root / "capture.json"
    try:
        metadata = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise CaptureValidationError(f"lane {expected_lane}: cannot read capture.json: {error}") from error
    _require(isinstance(metadata, dict), f"lane {expected_lane}: capture manifest must be an object")
    _require(metadata.get("schema") == "D10_LANE_CAPTURE_V1", f"lane {expected_lane}: unsupported capture schema")
    _require(metadata.get("lane") == expected_lane, f"lane {expected_lane}: lane label mismatch")
    device = "CUDA" if expected_lane == "C" else "CPU"
    _require(metadata.get("device") == device, f"lane {expected_lane}: requested device mismatch; fallback forbidden")
    _require(isinstance(metadata.get("run_id"), str) and bool(metadata["run_id"]), f"lane {expected_lane}: run_id required")
    _require(metadata.get("input_sha256") == EXPECTED_INPUT_SHA256, f"lane {expected_lane}: fixed synthetic input SHA mismatch")
    _require(metadata.get("checkpoint_sha256") == EXPECTED_CHECKPOINT_SHA256, f"lane {expected_lane}: frozen checkpoint SHA mismatch")
    _hash_map(metadata.get("config_sha256"), f"lane {expected_lane} config_sha256")
    _hash_map(metadata.get("source_sha256"), f"lane {expected_lane} source_sha256")
    _require(metadata.get("layer_order") == list(LAYERS), f"lane {expected_lane}: layer order incomplete or changed")
    _validate_model(metadata.get("model_identity"), expected_lane)
    _validate_environment(metadata.get("environment"), expected_lane, device)
    target_index = _validate_positions(metadata.get("small_reference_positions"), expected_lane)
    tensors = metadata.get("tensors")
    _require(isinstance(tensors, dict), f"lane {expected_lane}: tensor map required")
    missing = _required_keys() - tensors.keys()
    _require(not missing, f"lane {expected_lane}: missing tensors {sorted(missing)}")
    arrays = {}
    used_files = set()
    for key, tensor in tensors.items():
        _require(isinstance(key, str) and isinstance(tensor, dict), f"lane {expected_lane}: invalid tensor metadata")
        relative = tensor.get("file")
        _require(isinstance(relative, str) and bool(relative), f"lane {expected_lane} {key}: relative npy file required")
        relative_path = Path(relative)
        _require(not relative_path.is_absolute() and ".." not in relative_path.parts and relative_path.suffix == ".npy",
                 f"lane {expected_lane} {key}: file must be a relative .npy without traversal")
        path = (root / relative_path).resolve()
        _require(path.is_relative_to(root), f"lane {expected_lane} {key}: tensor path escapes capture directory")
        _require(path not in used_files, f"lane {expected_lane} {key}: tensor file is reused")
        used_files.add(path)
        try:
            array = np.load(path, allow_pickle=False)
        except (OSError, ValueError) as error:
            raise CaptureValidationError(f"lane {expected_lane} {key}: cannot load numeric npy: {error}") from error
        _require(isinstance(array, np.ndarray) and array.dtype.kind in "biuf", f"lane {expected_lane} {key}: real numeric array required")
        _require(array.size > 0 and bool(np.isfinite(array).all()), f"lane {expected_lane} {key}: empty or nonfinite array")
        _require(tensor.get("shape") == list(array.shape), f"lane {expected_lane} {key}: shape metadata mismatch")
        _require(tensor.get("dtype") == str(array.dtype), f"lane {expected_lane} {key}: dtype metadata mismatch")
        recorded_hash = tensor.get("sha256", tensor.get("canonical_sha256"))
        _require(_valid_sha256(recorded_hash) and canonical_sha256(array) == recorded_hash,
                 f"lane {expected_lane} {key}: canonical tensor SHA-256 mismatch")
        if "file_sha256" in tensor:
            _require(_valid_sha256(tensor["file_sha256"]) and file_sha256(path) == tensor["file_sha256"],
                     f"lane {expected_lane} {key}: npy file SHA-256 mismatch")
        if key not in {f"preprocessing/{name}" for name in ("raw", "hu")}:
            _require(array.dtype == np.dtype("float32"), f"lane {expected_lane} {key}: float32 capture required")
        array.flags.writeable = False
        arrays[key] = array
    _require(np.array_equal(arrays["preprocessing/tensor"], arrays["baseline/input"]),
             f"lane {expected_lane}: preprocessing tensor and model baseline input differ")
    _require(np.array_equal(arrays["position_691_batch1/input"], arrays["position_691_batch32/input"]),
             f"lane {expected_lane}: position 691 input differs by batch size")
    count = len(metadata["small_reference_positions"])
    masked = arrays["small_reference/masked_tensors"]
    _require(masked.shape[0] == count, f"lane {expected_lane}: masked tensor/position count mismatch")
    _require(np.array_equal(masked[target_index], arrays["position_691_batch1/input"]),
             f"lane {expected_lane}: position 691 does not match small reference masked tensor")
    for sample in SAMPLES:
        for output in ("fc", "logits", "probability"):
            _require(arrays[f"{sample}/{output}"].shape == (2,), f"lane {expected_lane}: {sample}/{output} must have two classes")
        _require(np.array_equal(arrays[f"{sample}/fc"], arrays[f"{sample}/logits"]),
                 f"lane {expected_lane}: {sample} fc and logits differ")
    for name in SMALL_REFERENCE[1:]:
        _require(arrays[f"small_reference/{name}"].shape == (count, 2), f"lane {expected_lane}: {name}/position shape mismatch")
    for name in REPEATABILITY:
        _require(arrays[f"repeatability/{name}"].shape == (3, 2), f"lane {expected_lane}: three two-class repeats required")
    for key, array in arrays.items():
        if key.endswith("/probability") or "probabilities_" in key or key.startswith("repeatability/"):
            _require(bool(((array >= 0) & (array <= 1)).all()), f"lane {expected_lane}: {key} has invalid probability values")
    return VerifiedCapture(metadata, arrays, file_sha256(manifest))


def numeric_metrics(left: np.ndarray, right: np.ndarray) -> dict[str, Any]:
    """Symmetric relative difference is 2|a-b|/(|a|+|b|), with 0/0=0."""
    _require(left.shape == right.shape, "numeric comparison shape mismatch")
    _require(left.dtype == right.dtype, "numeric comparison dtype mismatch")
    _require(left.size > 0 and left.dtype.kind in "biuf", "numeric comparison requires nonempty real arrays")
    a, b = left.astype(np.float64), right.astype(np.float64)
    _require(bool(np.isfinite(a).all() and np.isfinite(b).all()), "numeric comparison nonfinite values")
    # Scale the denominator to avoid overflow at very large finite magnitudes.
    difference = np.abs(a - b)
    scale = np.maximum(np.abs(a), np.abs(b))
    relative = np.zeros_like(difference)
    nonzero = scale != 0
    scaled_a = np.divide(a, scale, out=np.zeros_like(a), where=nonzero)
    scaled_b = np.divide(b, scale, out=np.zeros_like(b), where=nonzero)
    denominator = np.abs(scaled_a) + np.abs(scaled_b)
    np.divide(2 * np.abs(scaled_a - scaled_b), denominator, out=relative, where=nonzero)
    _require(bool(np.isfinite(difference).all()), "absolute difference exceeds float64 range")
    index = list(np.unravel_index(int(np.argmax(difference)), difference.shape))
    return {
        "shape": list(left.shape), "dtype": str(left.dtype), "element_count": int(left.size),
        "max_abs_diff": float(difference.max()), "mean_abs_diff": float(difference.mean()),
        "max_symmetric_relative_diff": float(relative.max()),
        "mean_symmetric_relative_diff": float(relative.mean()),
        "relative_diff_definition": "2*abs(a-b)/(abs(a)+abs(b)); zero/zero=0",
        "max_abs_diff_index": [int(v) for v in index], "exactly_equal": bool(np.array_equal(left, right)),
        "exceeds_diagnostic_threshold": bool(difference.max() > FROZEN_TOLERANCE),
    }


def _positive_metrics(left: np.ndarray, right: np.ndarray) -> dict[str, Any]:
    result = numeric_metrics(left[..., 1:2], right[..., 1:2])
    result["frozen_probability_tolerance"] = FROZEN_TOLERANCE
    result["compatible_at_frozen_tolerance"] = result["max_abs_diff"] <= FROZEN_TOLERANCE
    return result


def _validate_shared(captures: dict[str, VerifiedCapture]) -> None:
    reference = captures["A"]
    for lane, capture in captures.items():
        for name in ("input_sha256", "checkpoint_sha256", "config_sha256", "source_sha256", "small_reference_positions", "layer_order"):
            _require(capture.metadata[name] == reference.metadata[name], f"lane {lane}: shared {name} mismatch")
        _require(_shared_model_identity(capture.metadata["model_identity"]) ==
                 _shared_model_identity(reference.metadata["model_identity"]), f"lane {lane}: runtime model identity mismatch")
        _require(capture.arrays.keys() == reference.arrays.keys(), f"lane {lane}: tensor key set mismatch")
        for key, array in capture.arrays.items():
            expected = reference.arrays[key]
            _require(array.shape == expected.shape, f"lane {lane}: tensor shape differs at {key}")
            _require(array.dtype == expected.dtype, f"lane {lane}: tensor dtype differs at {key}")
    linux, cuda = captures["B"].metadata, captures["C"].metadata
    _require(linux["run_id"] == cuda["run_id"], "B/C run_id mismatch; compare the same experimental run")
    _require(_without_device_placement(linux["environment"]) == _without_device_placement(cuda["environment"]),
             "B/C environment differs beyond device placement")


def _layer_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    nonzero = next((row["layer"] for row in rows if row["max_abs_diff"] > 0), None)
    over = next((row["layer"] for row in rows if row["max_abs_diff"] > FROZEN_TOLERANCE), None)
    growth = []
    for before, after in zip(rows, rows[1:]):
        previous, current = before["max_abs_diff"], after["max_abs_diff"]
        if current > previous:
            growth.append({
                "from_layer": before["layer"], "to_layer": after["layer"],
                "previous_max_abs_diff": previous, "current_max_abs_diff": current,
                "absolute_growth": current - previous,
                "growth_ratio": current / previous if previous > 0 else None,
                "zero_to_nonzero": previous == 0,
            })
    finite_growth = [item for item in growth if item["growth_ratio"] is not None]
    return {
        "first_nonzero_divergence": nonzero, "first_threshold_exceeding_divergence": over,
        "first_observed_adjacent_growth": growth[0] if growth else None,
        "largest_adjacent_absolute_growth": max(growth, key=lambda item: item["absolute_growth"]) if growth else None,
        "largest_adjacent_growth_ratio": max(finite_growth, key=lambda item: item["growth_ratio"]) if finite_growth else None,
        "observed_adjacent_growth": growth, "first_major_amplification": None,
        "amplification_interpretation": "Observed adjacent max-difference growth only; no protocol major-amplification cutoff or causal claim.",
    }


def _batch_and_repeatability(capture: VerifiedCapture) -> dict[str, Any]:
    arrays = capture.arrays
    repeatability = {}
    for name in REPEATABILITY:
        values = arrays[f"repeatability/{name}"]
        reference = np.broadcast_to(values[0:1], values.shape)
        repeatability[name] = _positive_metrics(reference, values)
    return {
        "position_691_batch1_vs_formal": {
            "logits": numeric_metrics(arrays["position_691_batch1/logits"], arrays["position_691_batch32/logits"]),
            "positive_probability": _positive_metrics(arrays["position_691_batch1/probability"], arrays["position_691_batch32/probability"]),
        },
        "small_reference_batch1_vs_formal": {
            "logits": numeric_metrics(arrays["small_reference/logits_batch1"], arrays["small_reference/logits_formal"]),
            "positive_probability": _positive_metrics(arrays["small_reference/probabilities_batch1"], arrays["small_reference/probabilities_formal"]),
        },
        "repeatability": repeatability,
    }


def compare_captures(lane_a: str | Path, lane_b: str | Path, lane_c: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fail closed on invalid identities/environment before numerical comparison."""
    captures = {lane: load_capture(path, lane) for lane, path in (("A", lane_a), ("B", lane_b), ("C", lane_c))}
    _validate_shared(captures)
    pairs = {}
    layer_pairs = {}
    probability_keys = [f"{sample}/probability" for sample in SAMPLES] + [
        "small_reference/probabilities_batch1", "small_reference/probabilities_formal",
    ]
    for left_lane, right_lane in (("A", "B"), ("B", "C"), ("A", "C")):
        label = f"{left_lane}_vs_{right_lane}"
        left, right = captures[left_lane].arrays, captures[right_lane].arrays
        preprocessing_keys = [f"preprocessing/{name}" for name in PREPROCESSING]
        ordered_keys = preprocessing_keys + sorted(left.keys() - set(preprocessing_keys))
        all_metrics = {key: numeric_metrics(left[key], right[key]) for key in ordered_keys}
        probability = {key: _positive_metrics(left[key], right[key]) for key in probability_keys}
        probability_max = max(value["max_abs_diff"] for value in probability.values())
        preprocessing_equal = all(all_metrics[f"preprocessing/{name}"]["exactly_equal"] for name in PREPROCESSING)
        model_input_equal = all_metrics["preprocessing/tensor"]["exactly_equal"]
        pairs[label] = {
            "tensors": all_metrics, "positive_probability": probability,
            "preprocessing_stages_exactly_equal": preprocessing_equal,
            "model_input_tensor_exactly_equal": model_input_equal,
            "small_reference_probability_compatibility": {
                "max_abs_diff": probability_max, "tolerance": FROZEN_TOLERANCE,
                "compatible": probability_max <= FROZEN_TOLERANCE,
                "scope": "Captured baseline, position 691 and small reference probabilities only; no full D10 PASS assertion.",
            },
            "neural_backend_attribution_supported_by_equal_input": model_input_equal,
        }
        samples = {}
        for sample in SAMPLES:
            rows = [{"layer": layer, **all_metrics[f"{sample}/{layer}"]} for layer in LAYERS]
            samples[sample] = {"layers": rows, **_layer_summary(rows)}
        layer_pairs[label] = {"samples": samples}
    ab = pairs["A_vs_B"]["small_reference_probability_compatibility"]["compatible"]
    bc = pairs["B_vs_C"]["small_reference_probability_compatibility"]["compatible"]
    cases = {
        (True, False): ("CASE_1", "Investigate CUDA backend, precision flags and kernels."),
        (False, True): ("CASE_2", "Investigate platform, PyTorch version and CPU backend."),
        (False, False): ("CASE_3", "Both platform/runtime and CPU/CUDA differences need investigation."),
        (True, True): ("CASE_4", "Captured small references are compatible; this does not prove the historical deviation is resolved."),
    }
    case, suggestion = cases[(ab, bc)]
    inputs_equal = all(value["model_input_tensor_exactly_equal"] for value in pairs.values())
    if not inputs_equal:
        suggestion = "Model input tensors differ: investigate preprocessing/library differences before attributing output changes to neural CUDA drift."
    common = {
        "frozen_tolerance": FROZEN_TOLERANCE, "status": "DIAGNOSTIC_COMPARISON_COMPLETE",
        "root_cause": "NOT_ESTABLISHED_BY_COMPARISON_ALONE", "d10_pass_asserted": False,
        "formal_cuda_research_authorized": False, "stage_b_training": "NOT_AUTHORIZED",
    }
    comparison = {
        "schema": "D10_THREE_WAY_COMPARISON_V1", **common,
        "verified_shared_identities": {
            name: captures["A"].metadata[name] for name in (
                "input_sha256", "checkpoint_sha256", "config_sha256", "source_sha256", "model_identity", "small_reference_positions",
            )
        },
        "lanes": {lane: {"manifest_sha256": capture.manifest_sha256,
                          "run_id": capture.metadata["run_id"], "device": capture.metadata["device"],
                          "environment": capture.metadata["environment"],
                          "verified_tensor_count": len(capture.arrays)} for lane, capture in captures.items()},
        "linux_cpu_cuda_environment_equal_except_device": True,
        "pairs": pairs,
        "batch_size_and_repeatability": {lane: _batch_and_repeatability(capture) for lane, capture in captures.items()},
        "interpretation": {"observed_small_probability_compatibility_case": case,
                           "model_input_tensors_exactly_equal_all_pairs": inputs_equal,
                           "next_investigation": suggestion, "causal_classification": None},
    }
    layerwise = {
        "schema": "D10_LAYERWISE_GPU_COMPARISON_V1", **common,
        "layer_order": list(LAYERS), "pairs": layer_pairs,
        "diagnostic_threshold_interpretation": "0.0001 marks layer differences for investigation; only probability compatibility uses the frozen gate.",
        "preprocessing_checked_before_forward_attribution": True,
    }
    return comparison, layerwise


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    compare = commands.add_parser("compare", help="Verify all capture evidence and compare A/B/C")
    for name in ("a", "b", "c"):
        compare.add_argument(f"--lane-{name}", type=Path, required=True)
    compare.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.out_dir.exists():
        parser.error("output directory already exists; preserve prior evidence and choose a new directory")
    try:
        comparison, layerwise = compare_captures(args.lane_a, args.lane_b, args.lane_c)
    except CaptureValidationError as error:
        parser.error(str(error))
    # Validate serializability before creating any output directory or files.
    serialized = [json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n" for value in (comparison, layerwise)]
    try:
        args.out_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
        for filename, value in zip(("three_way_comparison.json", "layerwise_comparison_gpu.json"), serialized):
            descriptor = os.open(args.out_dir / filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(value)
    except OSError as error:
        parser.error(f"cannot preserve comparison output: {error}")
    print(json.dumps({"status": comparison["status"], "d10_pass_asserted": False,
                      "probability_max_abs_diff": {name: pair["small_reference_probability_compatibility"]["max_abs_diff"]
                                                   for name, pair in comparison["pairs"].items()}}, sort_keys=True))


if __name__ == "__main__":
    main()
