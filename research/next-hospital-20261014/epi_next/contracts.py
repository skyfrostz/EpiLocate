"""Versioned research contracts. No implicit clinical labels or sealed inputs."""
from dataclasses import dataclass, field, asdict
from enum import Enum
import math
import re
from typing import Any

import numpy as np


class AlgorithmStatus(str, Enum):
    OK = "OK"
    PARTIAL_BUDGET = "PARTIAL_BUDGET"
    NO_RELIABLE_RESPONSE = "NO_RELIABLE_RESPONSE"
    NO_FEASIBLE_MASK = "NO_FEASIBLE_MASK"
    GEOMETRY_INVALID = "GEOMETRY_INVALID"
    INPUT_UNSUPPORTED = "INPUT_UNSUPPORTED"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    FAILED = "FAILED"


class EvidenceType(str, Enum):
    MODEL_SCORE = "MODEL_SCORE"
    CAM_CONTRIBUTION = "CAM_CONTRIBUTION"
    INPUT_OCCLUSION = "INPUT_OCCLUSION"
    FEATURE_OCCLUSION = "FEATURE_OCCLUSION"
    EXPERT_REFERENCE = "EXPERT_REFERENCE"
    OPTIMIZED_INPUT_MASK = "OPTIMIZED_INPUT_MASK"


def require_hash(value: str, name: str, length: int = 64) -> None:
    if not isinstance(value, str) or not re.fullmatch(f"[0-9a-f]{{{length}}}", value):
        raise ValueError(f"{name} must be a lowercase {length}-character hash")


def finite_array(value: Any, name: str) -> np.ndarray:
    array = np.asarray(value)
    if not np.issubdtype(array.dtype, np.number) or not np.isfinite(array).all():
        raise ValueError(f"{name} must contain finite numbers")
    return array


@dataclass
class VolumeRecord:
    # Identifiers stay in private run assets, never public reports.
    patient_id: str
    split: str
    series_uid: str
    source_sops: list[str]
    raw_hash: str
    volume_hu: np.ndarray
    valid_mask: np.ndarray
    affine_lps: np.ndarray
    transform_ledger: list[dict]
    label_definition_id: str
    task_labels: dict
    support_status: str
    native_shape: tuple[int, int, int]
    coordinate_convention: str = "array_zyx_to_LPS_mm"

    def validate(self, approved_membership: dict | None = None) -> None:
        if self.split not in {"train", "observed_validation", "synthetic"}:
            raise ValueError("sealed, test, unknown, or unapproved splits are forbidden")
        if self.split != "synthetic":
            # The caller must obtain this mapping from a separately approved,
            # hash-locked manifest. A self-declared split is not authorization.
            member = (approved_membership or {}).get(self.patient_id)
            if not member or member.get("split") != self.split or self.series_uid not in member.get("series_uids", []):
                raise ValueError("patient/series is absent from approved membership")
        if not self.patient_id or not self.series_uid or not self.label_definition_id:
            raise ValueError("identity and task definition are required")
        require_hash(self.raw_hash, "raw_hash")
        volume = finite_array(self.volume_hu, "volume_hu")
        if volume.ndim != 3 or min(volume.shape) < 1:
            raise ValueError("volume_hu must be nonempty ZYX")
        valid = np.asarray(self.valid_mask)
        if valid.dtype != np.bool_ or valid.shape != volume.shape or not valid.any():
            raise ValueError("explicit nonempty boolean support mask is required")
        affine = finite_array(self.affine_lps, "affine_lps")
        if affine.shape != (4, 4) or not np.allclose(affine[3], [0, 0, 0, 1]):
            raise ValueError("invalid homogeneous affine")
        if abs(np.linalg.det(affine[:3, :3])) < 1e-12:
            raise ValueError("singular affine")
        if self.coordinate_convention != "array_zyx_to_LPS_mm":
            raise ValueError("unsupported coordinate convention")
        if len(self.native_shape) != 3 or any(type(n) is not int or n <= 0 for n in self.native_shape):
            raise ValueError("native_shape must contain three positive integers")
        if (len(self.source_sops) != self.native_shape[0]
                or len(set(self.source_sops)) != len(self.source_sops)
                or not all(self.source_sops)):
            raise ValueError("native SOP mapping must be complete and unique")
        if not self.transform_ledger or not self.support_status or not self.task_labels:
            raise ValueError("transform, support, and explicit task label provenance required")


@dataclass
class PredictionResult:
    model_id: str
    checkpoint_sha: str | None
    preprocess_hash: str
    target: int
    logits: list[float]
    prediction_score: float | None
    coarse_map: dict | None
    candidate_map: dict | None
    candidate_regions: list[dict]
    evidence_type: EvidenceType
    status: AlgorithmStatus
    run_id: str
    reason: str
    support_status: str
    calibration_status: str = "UNCALIBRATED"
    schema_version: str = "EPI-NEXT-1"

    def validate(self) -> None:
        status, evidence = AlgorithmStatus(self.status), EvidenceType(self.evidence_type)
        if self.checkpoint_sha is None:
            if status != AlgorithmStatus.MODEL_UNAVAILABLE or self.logits:
                raise ValueError("unknown checkpoint hash is only valid before model availability")
        else:
            require_hash(self.checkpoint_sha, "checkpoint_sha")
        require_hash(self.preprocess_hash, "preprocess_hash")
        if not self.model_id.startswith("EPI-NEXT") or not self.run_id.startswith("EPI-NEXT"):
            raise ValueError("new models and runs require EPI-NEXT identifiers")
        if evidence == EvidenceType.EXPERT_REFERENCE:
            raise ValueError("model predictions cannot be expert references")
        logits = finite_array(self.logits, "logits")
        preinference_failure = status in {AlgorithmStatus.MODEL_UNAVAILABLE, AlgorithmStatus.INPUT_UNSUPPORTED,
                                         AlgorithmStatus.GEOMETRY_INVALID, AlgorithmStatus.FAILED, AlgorithmStatus.TIMEOUT}
        if type(self.target) is not int or self.target < 0:
            raise ValueError("fixed target must be a nonnegative integer")
        if logits.size == 0 and preinference_failure:
            if self.prediction_score is not None or self.coarse_map or self.candidate_map or self.candidate_regions:
                raise ValueError("failure without logits cannot contain fabricated predictions")
        elif logits.ndim != 1 or logits.size < 2 or self.target >= logits.size:
            raise ValueError("fixed target must index the full logit vector")
        if self.prediction_score is not None and (not math.isfinite(self.prediction_score) or not 0 <= self.prediction_score <= 1):
            raise ValueError("prediction_score must be null or finite in [0,1]")
        if self.calibration_status != "UNCALIBRATED":
            raise ValueError("this version has no validated calibration contract")
        if not self.reason or not self.support_status:
            raise ValueError("reason and support status are required")
        if status in {AlgorithmStatus.NO_RELIABLE_RESPONSE, AlgorithmStatus.NO_FEASIBLE_MASK} and (self.candidate_regions or self.candidate_map):
            raise ValueError("abstention must not fabricate candidates")
        for asset in (self.coarse_map, self.candidate_map):
            if asset is not None:
                require_hash(asset["sha256"], "map asset hash")
                if not asset.get("coordinate_space") or not asset.get("path") or not asset.get("evidence_type"):
                    raise ValueError("maps require spatial and evidence provenance")
                if EvidenceType(asset["evidence_type"]) == EvidenceType.EXPERT_REFERENCE:
                    raise ValueError("model maps cannot be expert references")
        if self.coarse_map and self.coarse_map["evidence_type"] != EvidenceType.CAM_CONTRIBUTION:
            raise ValueError("coarse map must retain CAM contribution provenance")
        if self.candidate_map and self.candidate_map["evidence_type"] != evidence:
            raise ValueError("candidate map evidence must match algorithm evidence")
        for region in self.candidate_regions:
            if region.get("coordinate_space") != "LPS" or region.get("unit") != "mm":
                raise ValueError("candidate native coordinates require LPS millimeters")
            bbox = finite_array(region.get("bbox_mm"), "bbox_mm")
            if bbox.shape != (2, 3) or not (bbox[1] > bbox[0]).all():
                raise ValueError("invalid native bounding box")
            for key in ("margin_response", "probability_response", "scale_mm", "stage", "fill", "spatial_support", "source_sops", "raw_score"):
                if key not in region:
                    raise ValueError(f"candidate missing {key}")
            for key in ("margin_response", "probability_response", "raw_score"):
                if not math.isfinite(region[key]):
                    raise ValueError(f"candidate {key} must be finite")
            scales = finite_array(region["scale_mm"], "scale_mm")
            if not (scales > 0).all() or scales.size == 0:
                raise ValueError("candidate scale must be positive")

    def to_dict(self) -> dict:
        self.validate()
        result = asdict(self)
        result["status"] = AlgorithmStatus(self.status).value
        result["evidence_type"] = EvidenceType(self.evidence_type).value
        return result


@dataclass
class RunManifest:
    run_id: str
    git_sha: str
    config_sha: str
    split_manifest_sha: str
    model_sha: str | None
    seed: int
    environment: dict
    hardware: dict
    started_at: str
    timings: dict[str, float]
    actual_model_calls: int
    peak_memory_bytes: int | None
    failed_cases: list[dict]
    artifact_hashes: dict[str, str]
    metrics_scope: str
    weight_license: str
    pretraining_overlap_status: str = "unknown"
    source_dirty: bool = False
    command: list[str] = field(default_factory=list)
    exit_code: int | None = None
    process_running: bool = False

    def validate(self) -> None:
        if not self.run_id.startswith("EPI-NEXT"):
            raise ValueError("EPI-NEXT run ID required")
        require_hash(self.git_sha, "git_sha", 40)
        for key in ("config_sha", "split_manifest_sha"):
            require_hash(getattr(self, key), key)
        if self.model_sha is None:
            if self.actual_model_calls != 0:
                raise ValueError("executed model calls require an actual model hash")
        else:
            require_hash(self.model_sha, "model_sha")
        for key, digest in self.artifact_hashes.items():
            require_hash(digest, f"artifact {key}")
        if self.pretraining_overlap_status not in {"unknown", "overlap_found", "verified_disjoint"}:
            raise ValueError("invalid overlap status")
        if type(self.actual_model_calls) is not int or self.actual_model_calls < 0:
            raise ValueError("actual model calls must be a nonnegative integer")
        if any(not math.isfinite(v) or v < 0 for v in self.timings.values()):
            raise ValueError("timings must be finite and nonnegative")
        if self.peak_memory_bytes is not None and (type(self.peak_memory_bytes) is not int or self.peak_memory_bytes < 0):
            raise ValueError("memory must be measured nonnegative bytes or null")
        if not self.environment or not self.hardware or not self.metrics_scope or not self.weight_license:
            raise ValueError("runtime and evidence scope must be explicit")

    def to_dict(self) -> dict:
        self.validate()
        return asdict(self)
