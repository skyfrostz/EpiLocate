"""Thin v2 result adapter around the existing frozen Baseline implementation."""
from __future__ import annotations

import hashlib
import io
import json
import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from algorithm.service import (
    FrozenBaseline, MODEL_ID, MODEL_SHA, PREPROCESSING_VERSION, PROTOCOL_ID,
    validate_dicom,
)


class ModelHashMismatch(RuntimeError):
    pass


class InvalidWorkerInput(RuntimeError):
    pass


@dataclass
class InferenceOutput:
    result: dict
    assets: dict[str, tuple[bytes, str]]


class FrozenRunner:
    """Loads the frozen checkpoint once and delegates all model math to FrozenBaseline."""

    def __init__(self, frozen_root: Path, expected_hash: str):
        if expected_hash != MODEL_SHA:
            raise ModelHashMismatch("Configured model hash does not match the frozen Baseline")
        self.baseline = FrozenBaseline(frozen_root)
        if not self.baseline.ready():
            raise ModelHashMismatch("Frozen checkpoint, protocol, or configuration hash check failed")
        self.model_hash = MODEL_SHA
        self.hardware = {"accelerator": str(self.baseline.device).upper()}

    @staticmethod
    def _prediction(value: dict) -> dict:
        return {key: value[key] for key in (
            "predicted_class", "class_label", "positive_probability",
            "predicted_class_confidence", "inference_time_ms",
        )}

    @staticmethod
    def _comparison_png(path: Path, maximum: float) -> bytes:
        grid = json.loads(path.read_text(encoding="utf-8"))
        if len(grid) != 14 or any(len(row) != 14 for row in grid):
            raise InvalidWorkerInput("Comparison grid has invalid dimensions")
        denominator = max(maximum, 1e-6)
        pixels = []
        for row in grid:
            for value in row:
                if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                    raise InvalidWorkerInput("Comparison grid contains invalid values")
                pixels.append(min(255, round(float(value) / denominator * 255)))
        image = Image.frombytes("L", (14, 14), bytes(pixels))
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        return stream.getvalue()

    def run(self, claim: dict, input_path: Path, output_dir: Path) -> InferenceOutput:
        model = claim["model_version"]
        params = claim["job_parameters"]
        if (model.get("model_id"), model.get("checkpoint_sha256"),
            model.get("preprocessing_version"), model.get("protocol_id")) != (
            MODEL_ID, self.model_hash, PREPROCESSING_VERSION, PROTOCOL_ID,
        ):
            raise ModelHashMismatch("Claim model or protocol does not match the local frozen Baseline")
        if params.get("kind") not in {"PREDICTION", "OCCLUSION"}:
            raise InvalidWorkerInput("Unsupported job kind")
        case_id, slice_id = claim["case_id"], params["slice_id"]
        validate_dicom(input_path.read_bytes(), 50_000_000)
        if params["kind"] == "PREDICTION":
            prediction, _ = self.baseline.predict(input_path, case_id, slice_id)
            source = prediction
            summaries, comparisons, positions, assets = [], [], [], {}
        else:
            scales = params.get("scales")
            if not isinstance(scales, list) or not scales or len(scales) != len(set(scales)) or not set(scales).issubset({16, 32, 64}):
                raise InvalidWorkerInput("Unsupported occlusion scales")
            source = self.baseline.occlusion(input_path, case_id, slice_id, scales, output_dir)
            summaries = source["scale_summaries"]
            comparisons = source["cross_scale"]
            positions = [item for scale in scales for item in source["positions"][str(scale)]]
            assets = {}
            for summary in summaries:
                for field in ("response_layer", "candidate_layer", "comparison_grid_layer"):
                    layer = summary.get(field)
                    if layer is None:
                        continue
                    asset_id = layer["asset_id"]
                    if Path(asset_id).name != asset_id:
                        raise InvalidWorkerInput("Unsafe generated asset ID")
                    if field == "comparison_grid_layer":
                        # Backend v2 currently accepts PNG layers. The frozen
                        # 14x14 numeric grid stays derivable from exact positions.
                        png_id = Path(asset_id).with_suffix(".png").name
                        data = self._comparison_png(output_dir / asset_id, float(layer["value_max"]))
                        layer["asset_id"] = png_id
                        asset_id = png_id
                    else:
                        data = (output_dir / asset_id).read_bytes()
                    if asset_id in assets or not data.startswith(b"\x89PNG\r\n\x1a\n"):
                        raise InvalidWorkerInput("Invalid generated PNG asset")
                    assets[asset_id] = (data, "image/png")
            prediction = source["prediction"]
        if prediction.get("source") != "LIVE_CASE" or prediction.get("case_id") != case_id or prediction.get("slice_id") != slice_id:
            raise InvalidWorkerInput("Frozen Baseline returned a mismatched result")
        result = {
            "contract_version": "2.0", "source": "LIVE_CASE", "case_id": case_id,
            "slice_id": slice_id, "kind": params["kind"], "model_id": MODEL_ID,
            "model_version": self.model_hash, "preprocessing_version": PREPROCESSING_VERSION,
            "protocol_id": PROTOCOL_ID, "prediction": self._prediction(prediction),
        }
        if params["kind"] == "OCCLUSION":
            result.update(scale_summaries=summaries, cross_scale=comparisons, positions=positions)
        return InferenceOutput(result=result, assets=assets)


def manifest_for_success(worker_id: str, claim: dict, input_hash: str, output: InferenceOutput) -> dict:
    descriptors = []
    layers = {layer["asset_id"]: layer for summary in output.result.get("scale_summaries", [])
              for layer in (summary.get("response_layer"), summary.get("candidate_layer"),
                            summary.get("comparison_grid_layer")) if layer is not None}
    for name, (data, media_type) in sorted(output.assets.items()):
        layer = layers[name]
        descriptors.append({"asset_id": name, "part_name": name, "layer_kind": layer["layer_kind"],
                            "media_type": media_type, "size_bytes": len(data),
                            "sha256": hashlib.sha256(data).hexdigest()})
    return {"worker_id": worker_id, "job_id": claim["job_id"], "attempt_id": claim["attempt_id"],
            "lease_token": claim["lease_token"], "outcome": "SUCCEEDED", "model_id": MODEL_ID,
            "checkpoint_sha256": claim["model_version"]["checkpoint_sha256"],
            "input_sha256": input_hash, "result": output.result, "assets": descriptors}


def manifest_for_failure(worker_id: str, claim: dict, code: str) -> dict:
    return {"worker_id": worker_id, "job_id": claim["job_id"], "attempt_id": claim["attempt_id"],
            "lease_token": claim["lease_token"], "outcome": "FAILED", "model_id": claim["model_version"]["model_id"],
            "checkpoint_sha256": claim["model_version"]["checkpoint_sha256"],
            "input_sha256": claim["input_reference"]["sha256"], "result": None, "assets": [],
            "error": {"code": code, "message": "Worker could not complete this attempt."}}
