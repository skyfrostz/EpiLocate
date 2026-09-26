"""Worker loop and recovery tests against a deterministic in-memory Backend."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from algorithm.service import MODEL_SHA, PREPROCESSING_VERSION, PROTOCOL_ID
from worker.agent import WorkerAgent
from worker.client import BackendUnavailable, WorkerAPIError, WorkerClient
from worker.config import WorkerConfig
from worker.inference import InferenceOutput


INPUT = b"synthetic input"


def _iso(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def _config(tmp_path):
    return WorkerConfig("node_integration", "https://backend.example", "secret", MODEL_SHA,
                        tmp_path / "frozen", tmp_path / "worker", MODEL_SHA, poll_seconds=0.01)


def _claim():
    return {
        "job_id": "job_integration", "case_id": "case_integration",
        "attempt_id": "7dac4763-495f-4ac9-811f-b6d21e08adbe", "lease_token": "opaque-lease",
        "lease_expire_time": _iso(90),
        "input_reference": {"url": "https://objects.example/input",
                            "sha256": hashlib.sha256(INPUT).hexdigest(), "expires_at": _iso(300)},
        "model_version": {"model_id": "baseline_resnet18", "checkpoint_sha256": MODEL_SHA,
                          "preprocessing_version": PREPROCESSING_VERSION, "protocol_id": PROTOCOL_ID},
        "job_parameters": {"kind": "PREDICTION", "slice_id": "slice_integration", "scales": []},
    }


class Runner:
    hardware = {"accelerator": "CPU"}

    def __init__(self, error=None):
        self.calls = 0
        self.error = error

    def run(self, claim, input_path, _output_dir):
        self.calls += 1
        assert input_path.read_bytes() == INPUT
        if self.error:
            raise self.error
        return InferenceOutput({
            "contract_version": "2.0", "source": "LIVE_CASE", "case_id": claim["case_id"],
            "slice_id": claim["job_parameters"]["slice_id"], "kind": "PREDICTION",
            "model_id": "baseline_resnet18", "model_version": MODEL_SHA,
            "preprocessing_version": PREPROCESSING_VERSION, "protocol_id": PROTOCOL_ID,
            "prediction": {"predicted_class": 0, "class_label": "negative",
                           "positive_probability": 0.1, "predicted_class_confidence": 0.9,
                           "inference_time_ms": 1},
        }, {})


def _download():
    return httpx.MockTransport(lambda _request: httpx.Response(200, content=INPUT))


def test_config_requires_matching_explicit_model_hash(tmp_path, monkeypatch):
    for name, value in {
        "WORKER_ID": "node_integration", "BACKEND_URL": "https://backend.example",
        "TOKEN": "secret", "MODEL_VERSION": MODEL_SHA,
        "EPILOCATE_FROZEN_ROOT": str(tmp_path / "frozen"),
        "WORKER_DATA_ROOT": str(tmp_path / "worker"),
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("MODEL_HASH", raising=False)
    with pytest.raises(ValueError, match="MODEL_HASH"):
        WorkerConfig.from_env()
    monkeypatch.setenv("MODEL_HASH", "a" * 64)
    with pytest.raises(ValueError, match="MODEL_HASH"):
        WorkerConfig.from_env()
    monkeypatch.setenv("MODEL_HASH", MODEL_SHA)
    assert WorkerConfig.from_env().model_hash == MODEL_SHA


def test_heartbeat_outage_and_backend_restart_reconnect(tmp_path):
    class Client:
        registrations = 0
        heartbeats = 0

        def register(self, *_args):
            self.registrations += 1
            return {"worker_id": "node_integration", "registered": True,
                    "heartbeat_interval_seconds": 15, "lease_seconds": 90}

        def heartbeat(self, *_args):
            self.heartbeats += 1
            if self.heartbeats == 2:
                raise BackendUnavailable("temporary outage")
            if self.heartbeats == 3:
                raise WorkerAPIError(403, "WORKER_NOT_REGISTERED")
            return {"server_time": _iso(0), "lease_expire_time": None}

    client = Client()
    agent = WorkerAgent(_config(tmp_path), client=client, runner=Runner())
    agent.register()
    agent.heartbeat_once()
    assert agent._connected
    with pytest.raises(BackendUnavailable):
        agent.heartbeat_once()
    assert not agent._connected
    with pytest.raises(WorkerAPIError, match="WORKER_NOT_REGISTERED"):
        agent._heartbeat_tick()
    assert agent._register_again
    agent._heartbeat_tick()
    assert client.registrations == 2 and client.heartbeats == 4
    assert agent._connected and not agent._register_again and not agent._fatal


def test_full_worker_loop_register_claim_infer_submit(tmp_path):
    order = []
    holder = {}

    class Client:
        def register(self, *_args):
            order.append("register")
            return {"worker_id": "node_integration", "registered": True,
                    "heartbeat_interval_seconds": 15, "lease_seconds": 90}

        def heartbeat(self, _worker_id, activity, _active):
            order.append("heartbeat:" + activity)
            return {"server_time": _iso(0), "lease_expire_time": _iso(90) if activity == "RUNNING" else None}

        def claim(self, *_args):
            order.append("claim")
            return _claim()

        def submit(self, _job_id, manifest, assets):
            order.append("submit")
            assert manifest["result"]["source"] == "LIVE_CASE" and assets == {}
            holder["agent"].stop_event.set()
            return {"accepted": True, "job_id": "job_integration",
                    "attempt_id": _claim()["attempt_id"], "job_status": "COMPLETED"}

    runner = Runner()
    agent = WorkerAgent(_config(tmp_path), client=Client(), runner=runner, download_transport=_download())
    holder["agent"] = agent
    agent.run_forever()
    assert order == ["register", "heartbeat:IDLE", "claim", "heartbeat:RUNNING", "submit"]
    assert runner.calls == 1 and list(agent.temp_root.iterdir()) == []


@pytest.mark.parametrize("error,code", [
    (ValueError("corrupted DICOM"), "PREPROCESSING_FAILED"),
    (RuntimeError("model execution failed"), "INFERENCE_FAILED"),
])
def test_failed_inference_reports_stable_error(tmp_path, error, code):
    class Client:
        manifest = None

        def heartbeat(self, *_args):
            return {"server_time": _iso(0), "lease_expire_time": _iso(90)}

        def submit(self, _job_id, manifest, assets):
            self.manifest = manifest
            assert assets == {}
            return {"accepted": True, "job_id": "job_integration",
                    "attempt_id": _claim()["attempt_id"], "job_status": "FAILED"}

    client = Client()
    runner = Runner(error)
    agent = WorkerAgent(_config(tmp_path), client=client, runner=runner, download_transport=_download())
    assert agent.process_claim(_claim())["accepted"]
    assert runner.calls == 1
    assert client.manifest["outcome"] == "FAILED" and client.manifest["error"]["code"] == code
    assert list(agent.temp_root.iterdir()) == []


def test_result_upload_retries_same_payload_after_backend_timeout(tmp_path):
    class Client:
        payloads = []

        def heartbeat(self, *_args):
            return {"server_time": _iso(0), "lease_expire_time": _iso(90)}

        def submit(self, _job_id, manifest, assets):
            self.payloads.append((json.dumps(manifest, sort_keys=True), dict(assets)))
            if len(self.payloads) == 1:
                raise BackendUnavailable("read timeout")
            return {"accepted": True, "job_id": "job_integration",
                    "attempt_id": _claim()["attempt_id"], "job_status": "COMPLETED"}

    client = Client()
    agent = WorkerAgent(_config(tmp_path), client=client, runner=Runner(), download_transport=_download())
    agent.stop_event.wait = lambda _seconds: False
    assert agent.process_claim(_claim())["accepted"]
    assert len(client.payloads) == 2 and client.payloads[0] == client.payloads[1]


def test_transport_read_timeout_is_backend_unavailable():
    def timeout(request):
        raise httpx.ReadTimeout("request timed out", request=request)

    client = WorkerClient("https://backend.example", "secret", httpx.MockTransport(timeout))
    with pytest.raises(BackendUnavailable):
        client.register("node_integration", MODEL_SHA, {"accelerator": "CPU"})


def test_signed_url_refresh_outage_is_not_reported_as_inference_failure(tmp_path):
    class Client:
        submissions = 0

        def heartbeat(self, *_args):
            return {"server_time": _iso(0), "lease_expire_time": _iso(90)}

        def claim(self, *_args):
            raise BackendUnavailable("refresh failed")

        def submit(self, *_args):
            self.submissions += 1
            pytest.fail("transient refresh outage must not be submitted as inference failure")

    client = Client()
    runner = Runner()
    unavailable_input = httpx.MockTransport(lambda _request: httpx.Response(403))
    agent = WorkerAgent(_config(tmp_path), client=client, runner=runner,
                        download_transport=unavailable_input)
    with pytest.raises(BackendUnavailable):
        agent.process_claim(_claim(), "d1e0f379-d60f-44d5-b527-fd04d9e610bd")
    assert runner.calls == 0 and client.submissions == 0
    assert list(agent.temp_root.iterdir()) == []
