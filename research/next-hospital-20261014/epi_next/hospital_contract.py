"""Opt-in hospital sidecar v1. Existing Result 2.0 and research contracts stay intact.

All indices are zero-based ZYX pixel centres; bounds are half-open integer
index ranges. Matrices map model centres to native centres, then native to LPS.
Validation establishes mathematical consistency, not native CT acceptance.
"""
from enum import Enum
from itertools import product
from pathlib import PurePosixPath

import numpy as np

from .artifacts import canonical_json, sha256
from .contracts import finite_array, require_hash
from .geometry import transform_points


class ExecutionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    NO_RELIABLE_RESPONSE = "NO_RELIABLE_RESPONSE"
    PARTIAL_BUDGET = "PARTIAL_BUDGET"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    NOT_RUN = "NOT RUN"


ALGORITHMS = {
    "E1": {"version": "EPI-NEXT-E1-fixed-target-margin-v1", "evidence_type": "INPUT_OCCLUSION",
           "label": "固定目标遮挡响应", "dimensions": 2, "response_fields": ["signed_margin_delta", "target_probability_delta"]},
    "E2": {"version": "EPI-NEXT-E2-HSPI-independent-projected-Adam-v1", "evidence_type": "OPTIMIZED_INPUT_MASK",
           "label": "HSPI 全 logits 一致性掩膜", "dimensions": 2, "response_fields": ["similarity", "sparsity", "peak_gap"]},
    "F0": {"version": "EPI-NEXT-F0-signed-CAM-v1", "evidence_type": "CAM_CONTRIBUTION",
           "label": "编码器线性头有符号 CAM 贡献", "dimensions": 3, "response_fields": ["signed_contribution"]},
    "F1": {"version": "EPI-NEXT-F1-residual-input-refreshed-coarse-v2", "evidence_type": "INPUT_OCCLUSION",
           "label": "残余输入遮挡响应", "dimensions": 3, "response_fields": ["signed_margin_delta", "target_probability_delta"]},
}
SPATIAL_CHECKS = ("left_right", "slice_order", "world_coordinates", "crop", "resize", "resampling")


def positive_int(value, name):
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def affine(value):
    matrix = finite_array(value, "affine").astype(float)
    if (matrix.shape != (4, 4) or not np.allclose(matrix[3], [0, 0, 0, 1], rtol=0, atol=1e-12)
            or abs(np.linalg.det(matrix[:3, :3])) < 1e-12):
        raise ValueError("finite invertible homogeneous affine required")
    return matrix


def shape3(value):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError("ZYX shape required")
    for n in value:
        positive_int(n, "shape")
    return np.asarray(value, dtype=int)


def transform_chain(spatial):
    """Derive every step rather than trust an unverified caller affine.

    resize: align_corners=False half-pixel convention. resample: explicit
    physical spacing ratio, first centre preserved. No arbitrary warp or pad.
    """
    native_shape = shape3(spatial["native_shape_zyx"])
    current = native_shape.copy()
    matrix = np.eye(4)
    steps = spatial["operations"]
    if not isinstance(steps, list) or not steps:
        raise ValueError("explicit transform ledger required (identity if unchanged)")
    for step in steps:
        if not np.array_equal(shape3(step["input_shape_zyx"]), current):
            raise ValueError("transform input shape mismatch")
        out = shape3(step["output_shape_zyx"])
        mapping = np.eye(4)
        kind = step["operation"]
        if kind == "identity":
            if not np.array_equal(out, current):
                raise ValueError("identity changes shape")
        elif kind == "crop":
            start = np.asarray(step["start_zyx"])
            if (start.shape != (3,) or start.dtype.kind not in "iu" or (start < 0).any()
                    or (start + out > current).any()):
                raise ValueError("invalid crop")
            mapping[:3, 3] = start
        elif kind == "resize":
            if step.get("convention") != "half_pixel_align_corners_false":
                raise ValueError("unsupported resize convention")
            ratio = current / out
            mapping[:3, :3] = np.diag(ratio)
            mapping[:3, 3] = (ratio - 1) / 2
        elif kind == "resample":
            old = finite_array(step["input_spacing_zyx_mm"], "input spacing")
            new = finite_array(step["output_spacing_zyx_mm"], "output spacing")
            if old.shape != (3,) or new.shape != (3,) or (old <= 0).any() or (new <= 0).any():
                raise ValueError("positive ZYX spacing required")
            observed = np.linalg.norm((affine(spatial["native_affine_lps"]) @ matrix)[:3, :3], axis=0)
            if not np.allclose(old, observed, atol=1e-6, rtol=0):
                raise ValueError("resampling spacing differs from transform chain")
            if step.get("convention") != "first_center_preserved":
                raise ValueError("unsupported resampling convention")
            expected = np.ceil((current - 1) * old / new).astype(int) + 1
            if not np.array_equal(out, expected):
                raise ValueError("resampling shape mismatch")
            mapping[:3, :3] = np.diag(new / old)
        else:
            raise ValueError("unsupported spatial operation")
        matrix = matrix @ mapping
        current = out
    if not np.array_equal(current, shape3(spatial["model_shape_zyx"])):
        raise ValueError("model shape differs from ledger")
    if not np.allclose(matrix, affine(spatial["model_to_native_zyx"]), atol=1e-9, rtol=0):
        raise ValueError("model-to-native transform differs from ledger")
    return matrix


def validate_request(request):
    if request.get("schema") != "EPI-NEXT-HOSPITAL-INPUT-1":
        raise ValueError("unsupported hospital input schema")
    if not str(request["run_id"]).startswith("EPI-NEXT-"):
        raise ValueError("EPI-NEXT run identity required")
    require_hash(request["source_git_sha"], "source Git", 40)
    spec = ALGORITHMS[request["algorithm_id"]]
    if request["algorithm_version"] != spec["version"]:
        raise ValueError("algorithm version differs from registry")
    for key in ("case_id", "study_uid", "series_uid", "model_id", "model_version", "preprocessing_version"):
        if not isinstance(request.get(key), str) or not request[key]:
            raise ValueError(f"missing {key}")
    for key in ("input_manifest_sha256", "model_sha256", "preprocessing_sha256"):
        require_hash(request[key], key)
    require_hash(request["algorithm_config_sha256"], "algorithm config hash")
    if not isinstance(request["algorithm_config"], dict) or sha256(canonical_json(request["algorithm_config"])) != request["algorithm_config_sha256"]:
        raise ValueError("algorithm config differs from locked hash")
    task = request["task"]
    if not task.get("definition_id") or not task.get("target_label"):
        raise ValueError("task definition and target label required")
    require_hash(task["definition_sha256"], "task definition hash")
    if type(task["target_class"]) is not int or task["target_class"] < 0:
        raise ValueError("target class must be nonnegative integer")
    if request["source"] not in {"SYNTHETIC", "LIVE_CASE"}:
        raise ValueError("explicit input evidence source required")
    if request["source"] == "LIVE_CASE":
        require_hash(request["access_approval_sha256"], "externally approved CT inventory")
    budget = request["resource_budget"]
    if budget["device"] not in {"cpu", "mps"}:
        raise ValueError("remote RTX 3090 and CUDA are paused")
    for key in ("max_model_calls", "max_input_voxels", "max_input_bytes"):
        positive_int(budget[key], key)
    seconds = budget["max_seconds"]
    if type(seconds) not in (int, float) or not np.isfinite(seconds) or seconds <= 0:
        raise ValueError("positive finite wall-clock budget required")
    if budget.get("deadline_enforcement") != "BETWEEN_FORWARDS":
        raise ValueError("synchronous adapter cannot promise hard cancellation")
    spatial = request["spatial"]
    if spatial["convention"] != "ZYX_CENTERS_TO_LPS_MM":
        raise ValueError("unsupported coordinate convention")
    native_shape = shape3(spatial["native_shape_zyx"])
    model_shape = shape3(spatial["model_shape_zyx"])
    if spec["dimensions"] == 2 and model_shape[0] != 1:
        raise ValueError("E1/E2 require one explicitly selected slice")
    if int(np.prod(model_shape, dtype=object)) > budget["max_input_voxels"]:
        raise ValueError("input exceeds voxel budget")
    if request.get("model_input_dtype") not in {"float32", "float64"}:
        raise ValueError("explicit floating model input dtype required")
    positive_int(request["model_input_channels"], "model input channels")
    # Minimum input+boolean support storage, not a peak process-memory promise.
    input_bytes = int(np.prod(model_shape, dtype=object)) * (
        np.dtype(request["model_input_dtype"]).itemsize * request["model_input_channels"] + 1)
    if input_bytes > budget["max_input_bytes"]:
        raise ValueError("input and support exceed byte budget")
    sops = spatial["source_sops"]
    if len(sops) != native_shape[0] or len(set(sops)) != len(sops) or not all(sops):
        raise ValueError("complete unique sorted native SOP inventory required")
    if len(spatial["source_file_sha256"]) != len(sops):
        raise ValueError("source SOP hash inventory mismatch")
    for digest in spatial["source_file_sha256"]:
        require_hash(digest, "source file hash")
    affine(spatial["native_affine_lps"])
    transform_chain(spatial)
    canonical_json(request)  # also rejects nonfinite or unserializable configs


def request_hash(request):
    validate_request(request)
    return sha256(canonical_json(request))


def spatial_from_volume(record, *, approved_membership=None):
    """Consume an existing reader ledger; never select data or create approvals."""
    record.validate(approved_membership)
    first = record.transform_ledger[0]
    if first.get("operation") != "dicom_to_hu_regular_stack" or first.get("version") != "EPI-NEXT-CT-1":
        raise ValueError("unsupported native DICOM ledger")
    native = affine(first["native_affine_lps"])
    shape = list(record.native_shape)
    operations = []
    accumulated = native.copy()
    for step in record.transform_ledger[1:]:
        if step.get("operation") != "resample_regular_hu" or step.get("version") != "EPI-NEXT-CT-1":
            raise ValueError("unknown reader transform; formal spatial handoff required")
        if step["input_shape"] != shape:
            raise ValueError("reader ledger shape mismatch")
        mapping = affine(step["output_to_input_zyx"])
        if not np.allclose(mapping[:3, :3], np.diag(np.diag(mapping)[:3])) or not np.allclose(mapping[:3, 3], 0):
            raise ValueError("unsupported reader resample mapping")
        operations.append({"operation": "resample", "input_shape_zyx": shape,
                           "output_shape_zyx": step["output_shape"],
                           "input_spacing_zyx_mm": np.linalg.norm(accumulated[:3, :3], axis=0).tolist(),
                           "output_spacing_zyx_mm": step["spacing_zyx_mm"],
                           "convention": "first_center_preserved"})
        shape = step["output_shape"]
        accumulated = accumulated @ mapping
    if not np.allclose(accumulated, record.affine_lps, rtol=0, atol=1e-9):
        raise ValueError("reader output affine differs from ledger")
    if not operations:
        operations = [{"operation": "identity", "input_shape_zyx": shape, "output_shape_zyx": shape}]
    spatial = {"convention": "ZYX_CENTERS_TO_LPS_MM", "native_shape_zyx": list(record.native_shape),
               "model_shape_zyx": list(record.volume_hu.shape), "native_affine_lps": native.tolist(),
               "model_to_native_zyx": (np.linalg.inv(native) @ record.affine_lps).tolist(),
               "operations": operations, "source_sops": record.source_sops,
               "source_file_sha256": first["source_file_sha256"]}
    transform_chain(spatial)
    return spatial


def map_region(bounds, spatial):
    """Retain 8 oriented LPS corners; axis-aligned bbox is only a summary."""
    bounds = np.asarray(bounds)
    if (bounds.shape != (3, 2) or bounds.dtype.kind not in "iu" or (bounds[:, 0] < 0).any()
            or (bounds[:, 1] <= bounds[:, 0]).any()
            or (bounds[:, 1] > shape3(spatial["model_shape_zyx"])).any()):
        raise ValueError("invalid model region bounds")
    corners = np.array(list(product(*[(a - .5, b - .5) for a, b in bounds])))
    native = transform_points(corners, transform_chain(spatial))
    limit = shape3(spatial["native_shape_zyx"]) - .5
    if (native < -.5 - 1e-8).any() or (native > limit + 1e-8).any():
        raise ValueError("candidate extends outside native inventory")
    lps = transform_points(native, affine(spatial["native_affine_lps"]))
    # A slice belongs iff its voxel slab has positive overlap; boundary contact
    # alone does not associate a candidate with an adjacent SOP.
    indices = [z for z in range(len(spatial["source_sops"]))
               if z + .5 > native[:, 0].min() + 1e-8 and z - .5 < native[:, 0].max() - 1e-8]
    return {"bounds_zyx": bounds.tolist(), "corners_lps_mm": lps.tolist(),
            "bbox_lps_mm": [lps.min(0).tolist(), lps.max(0).tolist()],
            "source_sops": [spatial["source_sops"][z] for z in indices],
            "coordinate_space": "LPS", "unit": "mm"}


def validate_result(request, result):
    if (result.get("schema") != "EPI-NEXT-HOSPITAL-OUTPUT-1"
            or result["request_sha256"] != request_hash(request)
            or result["run_id"] != request["run_id"]
            or result["algorithm_id"] != request["algorithm_id"]):
        raise ValueError("result/request association mismatch")
    status = ExecutionStatus(result["status"])
    if result["evidence_type"] != ALGORITHMS[request["algorithm_id"]]["evidence_type"]:
        raise ValueError("algorithm evidence mismatch; model evidence cannot be GT")
    logits = finite_array(result["logits"], "logits")
    if logits.size and (logits.ndim != 1 or len(logits) < 2 or request["task"]["target_class"] >= len(logits)):
        raise ValueError("full logits required")
    if status in {ExecutionStatus.SUCCESS, ExecutionStatus.NO_RELIABLE_RESPONSE} and not logits.size:
        raise ValueError("completed inference requires real logits")
    prediction = result["raw_prediction"]
    if logits.size:
        if (not isinstance(prediction, dict) or prediction.get("class_index") != int(logits.argmax())
                or prediction.get("calibration_status") != "UNCALIBRATED"):
            raise ValueError("raw prediction must derive from recorded logits")
        probabilities = finite_array(prediction["scores"], "raw scores")
        expected = np.exp(logits - logits.max()); expected /= expected.sum()
        if probabilities.shape != logits.shape or not np.allclose(probabilities, expected, rtol=0, atol=1e-9):
            raise ValueError("raw scores differ from logits")
    elif prediction is not None:
        raise ValueError("no fabricated prediction before inference")
    if status not in {ExecutionStatus.SUCCESS, ExecutionStatus.PARTIAL_BUDGET} and result["candidate_regions"]:
        raise ValueError("noncandidate execution state must not expose candidates")
    if result["candidate_regions"] and not logits.size:
        raise ValueError("candidates require recorded inference logits")
    for region in result["candidate_regions"]:
        expected = map_region(region["bounds_zyx"], request["spatial"])
        if region["spatial"] != expected:
            raise ValueError("candidate spatial mapping mismatch")
        if not region.get("response") or not region.get("support"):
            raise ValueError("candidate response/support required")
        response = region["response"]
        for key in ALGORITHMS[request["algorithm_id"]]["response_fields"]:
            value = response.get(key)
            if type(value) not in (int, float) or not np.isfinite(value):
                raise ValueError("candidate response must contain finite " + key)
        if set(response) != set(ALGORITHMS[request["algorithm_id"]]["response_fields"]):
            raise ValueError("unregistered response semantics")
        canonical_json(region["response"])
    if (type(result["actual_model_calls"]) is not int or result["actual_model_calls"] < 0
            or result["actual_model_calls"] > request["resource_budget"]["max_model_calls"]):
        raise ValueError("invalid model call accounting")
    if logits.size and result["actual_model_calls"] == 0:
        raise ValueError("recorded inference requires counted model calls")
    if (type(result["runtime_seconds"]) not in (float, int) or not np.isfinite(result["runtime_seconds"])
            or result["runtime_seconds"] < 0 or not result["reason"]):
        raise ValueError("execution reason and finite timing required")
    for asset in result["artifacts"]:
        path = PurePosixPath(asset["path"])
        if path.is_absolute() or ".." in path.parts or len(path.parts) != 1:
            raise ValueError("run-local artifact paths required")
        require_hash(asset["sha256"], "artifact hash")
    if result["geometry_status"] not in {"MATHEMATICAL_ONLY", "INVALID"}:
        raise ValueError("native geometry acceptance comes from independent evidence")
    if result["geometry_status"] == "INVALID" and result["candidate_regions"]:
        raise ValueError("invalid geometry cannot expose candidates")
    canonical_json(result)
