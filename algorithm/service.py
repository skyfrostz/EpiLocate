"""Single-slice frozen baseline and Stage 1 occlusion service.

The source checkpoint and frozen protocol are read-only. No train or test manifests
are opened by this module. API objects are allowlisted and contain no DICOM tags.
"""
from __future__ import annotations

import hashlib
import io
import itertools
import json
import os
import threading
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pydicom
import torch
import yaml
from PIL import Image

from scripts.occlusion_runner import (
    EPSILON_NUM, add_response_metrics, build_grid, infer_logits, mask_resized,
    project_area_average, rasterize_block_scores, spatial_metrics,
)
from src.model import build_model
from src.preprocessing import preprocess_dicom

MODEL_SHA = "548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734"
PROTOCOL_SHA = "204e34ae2474ab91076cbe3d2fb8ba5ad6f5affb631274c3feed57ed2da7160b"
CONFIG_SHA = "6a9d1b011250e59956f443add621e786e04ceb6716a8329bc08df1e1e12f2b8a"
PREPROCESSING_VERSION = "formal-resnet18-baseline-rule-b-v1"
PROTOCOL_ID = "stage1-occlusion-instability-v1"
MODEL_ID = "baseline_resnet18"
SCALES = {16: 8, 32: 16, 64: 32}


def reserved_module():
    return {"status": "NOT_IMPLEMENTED", "method_version": None, "model_id": None,
            "stage": None, "scale": None, "regions": [], "final_region": None,
            "layer": None, "runtime_ms": None}


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ModelUnavailable(RuntimeError):
    pass


class FrozenBaseline:
    def __init__(self, frozen_root: Path | None = None):
        self.root = Path(frozen_root or os.environ.get("EPILOCATE_FROZEN_ROOT", "")).resolve() if (frozen_root or os.environ.get("EPILOCATE_FROZEN_ROOT")) else None
        self._model = None
        self._config = None
        self._lock = threading.RLock()
        self.device = torch.device("cpu")

    def _paths(self):
        if self.root is None:
            raise ModelUnavailable("Frozen baseline root is not configured.")
        return (
            self.root / "outputs/experiments/FORMAL-BL-R18-V1/training/best_model.pth",
            self.root / "docs/occlusion_instability_protocol_v1.md",
            self.root / "configs/occlusion_instability_v1.yaml",
            self.root / "configs/formal_baseline_rule_b_v1.yaml",
        )

    def ready(self) -> bool:
        try:
            self.load()
            return True
        except (ModelUnavailable, OSError, ValueError, RuntimeError):
            return False

    def load(self):
        with self._lock:
            if self._model is not None:
                return self._model
            checkpoint_path, protocol_path, stage_path, baseline_path = self._paths()
            try:
                if (file_hash(checkpoint_path), file_hash(protocol_path), file_hash(stage_path)) != (MODEL_SHA, PROTOCOL_SHA, CONFIG_SHA):
                    raise ModelUnavailable("Frozen baseline hash verification failed.")
                baseline = yaml.safe_load(baseline_path.read_text(encoding="utf-8"))
                stage = yaml.safe_load(stage_path.read_text(encoding="utf-8"))
                if stage["status"] != "FROZEN" or stage["protocol_id"] != PROTOCOL_ID or stage["baseline"]["checkpoint_sha256"] != MODEL_SHA or int(stage["baseline"]["best_epoch"]) != 2:
                    raise ModelUnavailable("Frozen baseline metadata verification failed.")
                if baseline["preprocessing"]["image_size"] != 224 or baseline["model"]["class_index"] != {"negative": 0, "positive": 1}:
                    raise ModelUnavailable("Frozen baseline configuration mismatch.")
                no_download = {**baseline, "model": {**baseline["model"], "pretrained": False}}
                model = build_model(no_download)
                # The file is trusted only after its exact frozen SHA-256 check.
                checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
                if int(checkpoint.get("epoch", -1)) != 2:
                    raise ModelUnavailable("Frozen checkpoint epoch mismatch.")
                model.load_state_dict(checkpoint["model_state_dict"], strict=True)
                model.eval().to(self.device)
                self._model, self._config = model, baseline
                return model
            except (OSError, KeyError, TypeError, ValueError) as exc:
                raise ModelUnavailable("Frozen baseline is unavailable or invalid.") from exc

    def stages(self, path: Path):
        self.load()
        return preprocess_dicom(path, self._config, return_stages=True)

    def predict(self, path: Path, case_id: str, slice_id: str):
        started = time.perf_counter()
        with self._lock:
            stages = self.stages(path)
            _, probabilities = infer_logits(self._model, [stages.tensor], self.device, batch_size=1)
        p = float(probabilities[0, 1])
        label = int(p >= 0.5)
        result = {
            "prediction_id": "PRED-" + hashlib.sha256((case_id + slice_id + MODEL_SHA).encode()).hexdigest()[:16],
            "case_id": case_id, "slice_id": slice_id, "unit": "slice", "aggregation": None,
            "model_id": MODEL_ID, "model_version": MODEL_SHA,
            "predicted_class": label, "class_label": "positive" if label else "negative",
            "positive_probability": p, "predicted_class_confidence": p if label else 1 - p,
            "inference_status": "COMPLETED", "inference_time_ms": max(0, round((time.perf_counter() - started) * 1000)),
            "preprocessing_version": PREPROCESSING_VERSION, "source": "LIVE_CASE",
        }
        return result, stages

    def occlusion(self, path: Path, case_id: str, slice_id: str, scales: list[int], asset_dir: Path):
        with self._lock:
            prediction, stages = self.predict(path, case_id, slice_id)
            p0 = prediction["positive_probability"]
            baseline_class = prediction["predicted_class"]
            rows = []
            for size in scales:
                stride = SCALES[size]
                positions = build_grid(224, size, stride)
                tensors = [mask_resized(stages.resized, x, y, size, 0.5) for x, y in positions]
                _, probs = infer_logits(self._model, tensors, self.device, batch_size=32)
                for (x, y), prob in zip(positions, probs):
                    pg = float(prob[1])
                    rows.append({
                        "fixture_id": slice_id, "block_size": size, "stride": stride,
                        "x": x, "y": y, "p0": p0, "pg": pg,
                        "baseline_class": baseline_class, "masked_class": int(pg >= 0.5),
                        "q0": p0 if baseline_class else 1 - p0,
                        "qg": pg if baseline_class else 1 - pg,
                    })
            frame = add_response_metrics(rows)
            asset_dir.mkdir(parents=True, exist_ok=True)
            summaries, positions_result, maps = [], {}, {}
            for size in scales:
                group = frame.loc[frame.block_size.eq(size)].copy()
                status = str(group.candidate_status.iloc[0])
                response = rasterize_block_scores(group, "candidate_response")
                selected = rasterize_block_scores(group.assign(candidate_response=group.candidate_selected.astype(float)), "candidate_response") > 0
                response_asset = f"response-{size}.png"
                max_value = float(response.max())
                Image.fromarray(np.rint(response / max(max_value, EPSILON_NUM) * 255).astype(np.uint8)).save(asset_dir / response_asset)
                if status == "valid":
                    candidate_asset = f"candidate-{size}.png"
                    Image.fromarray(selected.astype(np.uint8) * 255).save(asset_dir / candidate_asset)
                    maps[size] = (project_area_average(response), project_area_average(selected.astype(float)) > 0)
                else:
                    candidate_asset = None
                def layer(name, kind, width, height, maximum):
                    return None if name is None else {
                        "asset_id": name, "layer_kind": kind, "width": width, "height": height,
                        "coordinate_space": "ALGORITHM_224" if width == 224 else "COMPARISON_14",
                        "value_min": 0.0, "value_max": maximum,
                        "origin": "TOP_LEFT_PIXEL_EDGE", "x_axis": "RIGHT", "y_axis": "DOWN",
                        "display_interpolation_only": True,
                    }
                grid_asset = None
                if status == "valid":
                    grid_asset = f"comparison-{size}.json"
                    (asset_dir / grid_asset).write_text(json.dumps(project_area_average(response).tolist()), encoding="utf-8")
                summaries.append({
                    "block_size": size, "stride": SCALES[size], "fill": 0.5,
                    "baseline_positive_probability": p0,
                    "median_absolute_probability_change": float(group.absolute_probability_change.median()),
                    "flip_rate": float(group.prediction_flip.mean()),
                    "candidate_status": status,
                    "candidate_area_fraction": float(selected.mean()) if status == "valid" else None,
                    "response_layer": layer(response_asset if status == "valid" else None, "CANDIDATE_RESPONSE", 224, 224, max_value),
                    "candidate_layer": layer(candidate_asset, "CANDIDATE_TOP10", 224, 224, 1.0),
                    "comparison_grid_layer": layer(grid_asset, "COMPARISON_GRID", 14, 14, max_value),
                })
                positions_result[str(size)] = [{
                    "x": int(r.x), "y": int(r.y), "block_size": size,
                    "baseline_positive_probability": p0, "masked_positive_probability": float(r.pg),
                    "prediction_flip": bool(r.prediction_flip),
                    "decision_confidence_drop": float(r.decision_confidence_drop),
                    "candidate_response": float(r.candidate_response),
                } for r in group.itertuples(index=False)]
            comparisons = []
            for left, right in itertools.combinations(sorted(maps), 2):
                comparisons.append({"scale_a": left, "scale_b": right,
                                    **spatial_metrics(maps[left][0], maps[right][0], maps[left][1], maps[right][1])})
            result_id = "RESULT-" + hashlib.sha256((case_id + slice_id + str(scales) + MODEL_SHA).encode()).hexdigest()[:16]
            return {
                "contract_version": "1.0", "result_id": result_id,
                "case_id": case_id, "slice_id": slice_id, "source": "LIVE_CASE", "status": "COMPLETED",
                "protocol_id": PROTOCOL_ID, "model_id": MODEL_ID, "model_version": MODEL_SHA,
                "preprocessing_version": PREPROCESSING_VERSION,
                "prediction": prediction, "scale_summaries": summaries, "cross_scale": comparisons,
                "positions": positions_result,
                "coarse_localization": reserved_module(), "lime": reserved_module(),
                "clinical_explanation": {"status": "NOT_IMPLEMENTED", "method_version": None, "summary": None, "evidence_region_ids": []},
                "paired_model_results": [], "qa_status": "NOT_RUN",
                "provenance": {"checkpoint_sha256": MODEL_SHA, "checkpoint_epoch": 2,
                               "protocol_sha256": PROTOCOL_SHA, "config_sha256": CONFIG_SHA},
            }


def validate_dicom(data: bytes, max_pixels: int) -> tuple[int, int]:
    try:
        ds = pydicom.dcmread(io.BytesIO(data), stop_before_pixels=True)
        if str(getattr(ds, "Modality", "")) != "CT" or str(getattr(ds, "PhotometricInterpretation", "")) != "MONOCHROME2":
            raise ValueError("Only monochrome CT is supported.")
        if "LOCALIZER" in getattr(ds, "ImageType", []):
            raise ValueError("Scout images are unsupported.")
        rows, columns = int(ds.Rows), int(ds.Columns)
        if rows < 2 or columns < 2 or rows * columns > max_pixels or int(getattr(ds, "NumberOfFrames", 1)) != 1:
            raise ValueError("Invalid or oversized single slice.")
        forbidden = ("PatientName", "PatientID", "PatientBirthDate", "PatientAddress",
                     "InstitutionName", "ReferringPhysicianName", "AccessionNumber")
        if (any(str(getattr(ds, key, "")).strip() for key in forbidden)
                or any(element.tag.is_private for element in ds.iterall())
                or str(getattr(ds, "PatientIdentityRemoved", "")).upper() != "YES"
                or str(getattr(ds, "BurnedInAnnotation", "")).upper() != "NO"):
            raise ValueError("DICOM must be de-identified before upload.")
        return rows, columns
    except (AttributeError, TypeError, ValueError, pydicom.errors.InvalidDicomError) as exc:
        raise ValueError("DICOM parsing or de-identification check failed.") from exc
