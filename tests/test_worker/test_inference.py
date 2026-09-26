"""Synthetic DICOM result adaptation; no frozen model execution in unit tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

from algorithm.service import MODEL_SHA, PREPROCESSING_VERSION, PROTOCOL_ID
from worker.config import WorkerConfig
from worker.inference import FrozenRunner, ModelHashMismatch, manifest_for_success


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "docs/interfaces/fixtures/p0_synthetic_ct.dcm"


def claim(kind="OCCLUSION"):
    return {"job_id": "job_synthetic", "case_id": "case_synthetic", "attempt_id": "attempt_synthetic",
            "lease_token": "lease_synthetic", "input_reference": {"sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest()},
            "model_version": {"model_id": "baseline_resnet18", "checkpoint_sha256": MODEL_SHA,
                              "preprocessing_version": PREPROCESSING_VERSION, "protocol_id": PROTOCOL_ID},
            "job_parameters": {"kind": kind, "slice_id": "slice_synthetic", "scales": [16] if kind == "OCCLUSION" else []}}


def prediction():
    return {"case_id": "case_synthetic", "slice_id": "slice_synthetic", "source": "LIVE_CASE",
            "predicted_class": 0, "class_label": "negative", "positive_probability": 0.1,
            "predicted_class_confidence": 0.9, "inference_time_ms": 5}


class FakeBaseline:
    def __init__(self, valid=True):
        self.valid = valid

    def predict(self, _path, _case, _slice):
        return prediction(), None

    def occlusion(self, _path, _case, _slice, _scales, output_dir):
        output_dir.mkdir(parents=True)
        Image.new("L", (224, 224), 125).save(output_dir / "response-16.png")
        (output_dir / "comparison-16.json").write_text(json.dumps([[0.25] * 14 for _ in range(14)]))
        def layer(name, kind, size):
            return {"asset_id": name, "layer_kind": kind, "width": size, "height": size,
                    "coordinate_space": "ALGORITHM_224" if size == 224 else "COMPARISON_14",
                    "origin": "TOP_LEFT_PIXEL_EDGE", "value_min": 0.0, "value_max": 0.25,
                    "x_axis": "RIGHT", "y_axis": "DOWN", "display_interpolation_only": True}
        summary = {"block_size": 16, "stride": 8, "fill": 0.5,
                   "baseline_positive_probability": 0.1, "median_absolute_probability_change": 0.02,
                   "flip_rate": 0.0, "candidate_status": "valid" if self.valid else "insufficient_positive_response",
                   "candidate_area_fraction": 0.1 if self.valid else None,
                   "response_layer": layer("response-16.png", "CANDIDATE_RESPONSE", 224) if self.valid else None,
                   "candidate_layer": None,
                   "comparison_grid_layer": layer("comparison-16.json", "COMPARISON_GRID", 14) if self.valid else None}
        return {"prediction": prediction(), "scale_summaries": [summary], "cross_scale": [],
                "positions": {"16": [{"x": 0, "y": 0, "block_size": 16,
                                      "baseline_positive_probability": 0.1,
                                      "masked_positive_probability": 0.08,
                                      "prediction_flip": False,
                                      "decision_confidence_drop": -0.02,
                                      "candidate_response": 0.0}]}}


def runner(valid=True):
    value = object.__new__(FrozenRunner)
    value.baseline = FakeBaseline(valid)
    value.model_hash = MODEL_SHA
    return value


def test_synthetic_occlusion_assets_and_manifest(tmp_path):
    output = runner().run(claim(), FIXTURE, tmp_path / "assets")
    assert output.result["contract_version"] == "2.0"
    assert output.result["source"] == "LIVE_CASE"
    assert output.result["positions"][0]["candidate_response"] == 0.0
    summary = output.result["scale_summaries"][0]
    assert summary["comparison_grid_layer"]["asset_id"] == "comparison-16.png"
    assert set(output.assets) == {"response-16.png", "comparison-16.png"}
    manifest = manifest_for_success("node_synthetic", claim(), hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), output)
    assert {item["asset_id"] for item in manifest["assets"]} == set(output.assets)
    for item in manifest["assets"]:
        data, mime = output.assets[item["part_name"]]
        assert mime == "image/png" and item["sha256"] == hashlib.sha256(data).hexdigest()


def test_insufficient_response_has_no_candidate_assets(tmp_path):
    output = runner(False).run(claim(), FIXTURE, tmp_path / "assets")
    summary = output.result["scale_summaries"][0]
    assert summary["candidate_status"] == "insufficient_positive_response"
    assert summary["candidate_area_fraction"] is None
    assert summary["candidate_layer"] is None
    assert output.assets == {}


def test_claim_model_hash_mismatch_rejected_before_inference(tmp_path):
    item = claim("PREDICTION")
    item["model_version"]["checkpoint_sha256"] = "a" * 64
    with pytest.raises(ModelHashMismatch):
        runner().run(item, FIXTURE, tmp_path / "assets")


def test_config_rejects_plain_http_and_frozen_storage(tmp_path):
    with pytest.raises(ValueError, match="HTTPS"):
        WorkerConfig("node_test", "http://backend.example", "token", MODEL_SHA,
                     tmp_path / "frozen", tmp_path / "worker")
    with pytest.raises(ValueError, match="separate"):
        WorkerConfig("node_test", "https://backend.example", "token", MODEL_SHA,
                     tmp_path / "frozen", tmp_path / "frozen" / "temp")
