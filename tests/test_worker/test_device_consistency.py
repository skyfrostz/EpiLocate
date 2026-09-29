"""Device selection, OOM classification, and preregistered comparison bounds."""
from __future__ import annotations

import copy
import hashlib
import io
import time
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import torch
from PIL import Image

from algorithm.service import MODEL_SHA, PREPROCESSING_VERSION, PROTOCOL_ID
from worker.agent import WorkerAgent
import worker.agent as agent_module
from worker.config import WorkerConfig
from worker.consistency import capture_bundle, compare_bundles
from worker.device import DeviceUnavailable, select_device
from worker.device import DeviceSelection
from worker.inference import FrozenRunner, InferenceOutput
import worker.inference as inference_module


def test_explicit_cuda_never_falls_back_and_auto_can_choose_cpu(monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    assert select_device("CPU").actual == "CPU"
    assert select_device("AUTO").actual == "CPU"
    with pytest.raises(DeviceUnavailable, match="CUDA requested"):
        select_device("CUDA")


def test_cuda_capability_selection_reports_actual_hardware_without_running_cuda(monkeypatch):
    monkeypatch.setattr(torch.version, "cuda", "test-runtime")
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(torch.cuda, "device_count", lambda: 1)
    monkeypatch.setattr(torch.cuda, "get_device_properties",
                        lambda _index: SimpleNamespace(name="synthetic-gpu", total_memory=8 * 1024**3))
    selected = select_device("AUTO")
    assert selected.actual == "CUDA" and selected.hardware == {"accelerator": "CUDA", "gpu_memory_mib": 8192}
    assert selected.torch_device.type == "cuda"


def test_frozen_runner_rejects_cuda_before_model_load_when_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    with pytest.raises(DeviceUnavailable):
        FrozenRunner(tmp_path, MODEL_SHA, "CUDA")


def test_model_load_oom_clears_local_cuda_cache(tmp_path, monkeypatch):
    class OomBaseline:
        def __init__(self, _root):
            self.device = torch.device("cpu")

        def load(self):
            assert self.device.type == "cuda"
            raise torch.cuda.OutOfMemoryError("simulated model allocation failure")

    cleared = []
    monkeypatch.setattr(inference_module, "select_device",
                        lambda _mode: DeviceSelection("CUDA", "CUDA", torch.device("cuda:0")))
    monkeypatch.setattr(inference_module, "FrozenBaseline", OomBaseline)
    monkeypatch.setattr(torch.cuda, "empty_cache", lambda: cleared.append(True))
    with pytest.raises(DeviceUnavailable, match="out of memory"):
        FrozenRunner(tmp_path, MODEL_SHA, "CUDA")
    assert cleared == [True]


def test_worker_config_device_modes(tmp_path):
    base = ("node_gpu_test", "https://backend.example", "secret", MODEL_SHA,
            tmp_path / "frozen", tmp_path / "worker", MODEL_SHA)
    assert WorkerConfig(*base).device == "CPU"
    assert WorkerConfig(*base, device="AUTO").device == "AUTO"
    with pytest.raises(ValueError, match="WORKER_DEVICE"):
        WorkerConfig(*base, device="MPS")


def test_cuda_oom_reports_retryable_backend_code_and_cleans_attempt(tmp_path):
    data = b"synthetic input"
    now = datetime.now(timezone.utc)
    iso = lambda seconds: (now + timedelta(seconds=seconds)).isoformat()
    claim = {"job_id": "job_gpu_test", "case_id": "case_gpu_test",
             "attempt_id": "b0d4df30-31df-4b75-86f8-8095c982214b", "lease_token": "lease-test",
             "lease_expire_time": iso(90),
             "input_reference": {"url": "https://objects.example/input", "sha256": hashlib.sha256(data).hexdigest(),
                                 "expires_at": iso(300)},
             "model_version": {"model_id": "baseline_resnet18", "checkpoint_sha256": MODEL_SHA,
                               "preprocessing_version": PREPROCESSING_VERSION, "protocol_id": PROTOCOL_ID},
             "job_parameters": {"kind": "PREDICTION", "slice_id": "slice_gpu_test", "scales": []}}

    class Runner:
        hardware = {"accelerator": "CUDA"}
        released = False

        def run(self, *_args):
            raise torch.cuda.OutOfMemoryError("simulated allocation failure")

        def release_cached_memory(self):
            self.released = True

    class Client:
        manifest = None

        def heartbeat(self, *_args):
            return {"server_time": iso(0), "lease_expire_time": iso(90)}

        def submit(self, _job_id, manifest, assets):
            self.manifest = manifest
            assert assets == {}
            return {"accepted": True, "job_id": claim["job_id"], "attempt_id": claim["attempt_id"]}

    client, runner = Client(), Runner()
    config = WorkerConfig("node_gpu_test", "https://backend.example", "secret", MODEL_SHA,
                          tmp_path / "frozen", tmp_path / "worker", MODEL_SHA)
    agent = WorkerAgent(config, client=client, runner=runner,
                        download_transport=httpx.MockTransport(lambda _request: httpx.Response(200, content=data)))
    assert agent.process_claim(claim)["accepted"]
    assert client.manifest["outcome"] == "FAILED"
    assert client.manifest["error"]["code"] == "TEMPORARY_GPU_UNAVAILABLE"
    assert runner.released and list(agent.temp_root.iterdir()) == []


def test_background_heartbeat_renews_lease_during_long_inference(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_module, "HEARTBEAT_INTERVAL_SECONDS", 0.01)
    data = b"synthetic input"
    now = datetime.now(timezone.utc)
    iso = lambda seconds: (now + timedelta(seconds=seconds)).isoformat()
    claim = {"job_id": "job_heartbeat", "case_id": "case_heartbeat",
             "attempt_id": "04b91f1c-c849-44cc-899d-7975ead53c0d", "lease_token": "lease-test",
             "lease_expire_time": iso(90),
             "input_reference": {"url": "https://objects.example/input", "sha256": hashlib.sha256(data).hexdigest(),
                                 "expires_at": iso(300)},
             "model_version": {"model_id": "baseline_resnet18", "checkpoint_sha256": MODEL_SHA,
                               "preprocessing_version": PREPROCESSING_VERSION, "protocol_id": PROTOCOL_ID},
             "job_parameters": {"kind": "PREDICTION", "slice_id": "slice_heartbeat", "scales": []}}

    class Client:
        active_heartbeats = 0

        def heartbeat(self, _worker_id, activity, _active):
            if activity == "RUNNING":
                self.active_heartbeats += 1
            return {"server_time": iso(0), "lease_expire_time": iso(90)}

        def submit(self, _job_id, manifest, _assets):
            assert manifest["outcome"] == "SUCCEEDED"
            return {"accepted": True, "job_id": claim["job_id"], "attempt_id": claim["attempt_id"]}

    class SlowRunner:
        hardware = {"accelerator": "CPU"}

        def run(self, *_args):
            time.sleep(0.08)
            return InferenceOutput({"contract_version": "2.0", "source": "LIVE_CASE",
                                    "case_id": claim["case_id"], "slice_id": "slice_heartbeat",
                                    "kind": "PREDICTION", "model_id": "baseline_resnet18",
                                    "model_version": MODEL_SHA, "preprocessing_version": PREPROCESSING_VERSION,
                                    "protocol_id": PROTOCOL_ID,
                                    "prediction": {"predicted_class": 0, "class_label": "negative",
                                                   "positive_probability": 0.1,
                                                   "predicted_class_confidence": 0.9,
                                                   "inference_time_ms": 80}}, {})

    client = Client()
    config = WorkerConfig("node_gpu_test", "https://backend.example", "secret", MODEL_SHA,
                          tmp_path / "frozen", tmp_path / "worker", MODEL_SHA)
    agent = WorkerAgent(config, client=client, runner=SlowRunner(),
                        download_transport=httpx.MockTransport(lambda _request: httpx.Response(200, content=data)))
    agent.start_heartbeats()
    try:
        assert agent.process_claim(claim)["accepted"]
    finally:
        agent.stop()
    assert client.active_heartbeats >= 2


def _bundle(pixel: int = 20):
    stream = io.BytesIO()
    Image.new("L", (2, 2), pixel).save(stream, format="PNG")
    layer = {"asset_id": "response-16.png", "layer_kind": "CANDIDATE_RESPONSE",
             "width": 2, "height": 2, "coordinate_space": "ALGORITHM_224",
             "origin": "TOP_LEFT_PIXEL_EDGE", "x_axis": "RIGHT", "y_axis": "DOWN",
             "display_interpolation_only": True, "value_min": 0.0, "value_max": 0.5}
    result = {"contract_version": "2.0", "source": "LIVE_CASE", "case_id": "case_synthetic",
              "slice_id": "slice_synthetic", "kind": "OCCLUSION", "model_id": "baseline_resnet18",
              "model_version": MODEL_SHA, "preprocessing_version": PREPROCESSING_VERSION,
              "protocol_id": PROTOCOL_ID,
              "prediction": {"predicted_class": 0, "class_label": "negative",
                             "positive_probability": 0.1, "predicted_class_confidence": 0.9,
                             "inference_time_ms": 1},
              "scale_summaries": [{"block_size": 16, "stride": 8, "fill": 0.5,
                                   "candidate_status": "valid", "candidate_area_fraction": 0.1,
                                   "baseline_positive_probability": 0.1,
                                   "median_absolute_probability_change": 0.02, "flip_rate": 0.0,
                                   "response_layer": layer, "candidate_layer": None,
                                   "comparison_grid_layer": None}],
              "positions": [{"block_size": 16, "x": 0, "y": 0, "prediction_flip": False,
                             "baseline_positive_probability": 0.1, "masked_positive_probability": 0.09,
                             "decision_confidence_drop": 0.01, "candidate_response": 0.01}],
              "cross_scale": []}
    return capture_bundle(InferenceOutput(result, {"response-16.png": (stream.getvalue(), "image/png")}),
                          "a" * 64, "CPU")


def test_consistency_checks_numeric_geometry_and_decoded_png():
    reference = _bundle()
    same = copy.deepcopy(reference)
    same["device"] = "CUDA"
    same["result"]["prediction"]["inference_time_ms"] = 999
    assert compare_bundles(reference, same)["passed"]
    changed = copy.deepcopy(same)
    changed["result"]["prediction"]["positive_probability"] += 0.001
    assert "prediction.positive_probability" in compare_bundles(reference, changed)["failures"]
    pixels = _bundle(23)
    assert "assets.response-16.png.pixels" in compare_bundles(reference, pixels)["failures"]
