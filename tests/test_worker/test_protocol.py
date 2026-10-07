"""Worker Protocol v1 boundaries with an in-memory HTTPS Backend."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from torch.cuda import OutOfMemoryError

from algorithm.service import MODEL_SHA, PREPROCESSING_VERSION, PROTOCOL_ID
from worker.agent import LeaseExpired, WorkerAgent
from worker.client import BackendUnavailable, WorkerAPIError, WorkerClient
from worker.config import WorkerConfig
from worker.inference import InferenceOutput, InvalidWorkerInput, ModelHashMismatch


def iso(seconds: int = 0):
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def config(tmp_path):
    return WorkerConfig("node_test", "https://backend.example", "test-worker-secret", MODEL_SHA,
                        tmp_path / "frozen", tmp_path / "worker", MODEL_SHA, poll_seconds=0.01)


def claim(data: bytes, *, kind="PREDICTION", expires=90):
    return {
        "job_id": "job_test", "case_id": "case_test", "attempt_id": "71300ddc-1e31-4bb6-a941-7174615c39ab",
        "lease_token": "opaque-lease-token", "lease_expire_time": iso(expires),
        "input_reference": {"url": "https://objects.example/input", "sha256": hashlib.sha256(data).hexdigest(),
                            "expires_at": iso(300)},
        "model_version": {"model_id": "baseline_resnet18", "checkpoint_sha256": MODEL_SHA,
                          "preprocessing_version": PREPROCESSING_VERSION, "protocol_id": PROTOCOL_ID},
        "job_parameters": {"kind": kind, "slice_id": "slice_test", "scales": [16, 32, 64] if kind == "OCCLUSION" else []},
    }


class FakeRunner:
    hardware = {"accelerator": "CPU"}

    def __init__(self):
        self.calls = 0

    def run(self, assignment, input_path: Path, output_dir: Path):
        self.calls += 1
        assert input_path.read_bytes() == b"synthetic input"
        return InferenceOutput({
            "contract_version": "2.0", "source": "LIVE_CASE", "case_id": assignment["case_id"],
            "slice_id": assignment["job_parameters"]["slice_id"], "kind": "PREDICTION",
            "model_id": "baseline_resnet18", "model_version": MODEL_SHA,
            "preprocessing_version": PREPROCESSING_VERSION, "protocol_id": PROTOCOL_ID,
            "prediction": {"predicted_class": 0, "class_label": "negative", "positive_probability": 0.1,
                           "predicted_class_confidence": 0.9, "inference_time_ms": 1},
        }, {})


def test_register_heartbeat_claim_and_submit_wire_contract():
    calls = []
    assigned = claim(b"synthetic input")

    def backend(request):
        assert request.url.scheme == "https"
        assert request.headers["Authorization"] == "Bearer test-worker-secret"
        assert request.headers["X-Request-ID"]
        calls.append(request)
        path = request.url.path
        if path.endswith("/register"):
            body = json.loads(request.content)
            assert body["max_concurrent_jobs"] == 1
            assert body["supported_model_versions"][0]["checkpoint_sha256"] == MODEL_SHA
            return httpx.Response(200, json={"worker_id": "node_test", "registered": True,
                "heartbeat_interval_seconds": 15, "lease_seconds": 90})
        if path.endswith("/heartbeat"):
            body = json.loads(request.content)
            assert body["activity_state"] == "RUNNING"
            assert body["active_attempt"]["lease_token"] == assigned["lease_token"]
            return httpx.Response(200, json={"lease_expire_time": iso(90), "server_time": iso()})
        if path.endswith("/claim"):
            assert request.headers["Idempotency-Key"] == "4a3ed831-efc4-4182-a715-092dd210eafb"
            assert json.loads(request.content)["available_capacity"] == 1
            return httpx.Response(200, json=assigned)
        if path.endswith("/jobs/job_test/result"):
            assert b'name="manifest"' in request.content
            assert b'"outcome":"SUCCEEDED"' in request.content
            return httpx.Response(200, json={"job_id": "job_test", "attempt_id": assigned["attempt_id"],
                                            "accepted": True, "job_status": "COMPLETED", "result_id": "result_test"})
        return httpx.Response(404)

    client = WorkerClient("https://backend.example", "test-worker-secret", httpx.MockTransport(backend))
    assert client.register("node_test", MODEL_SHA, {"accelerator": "CPU"})["registered"] is True
    assert client.claim("node_test", MODEL_SHA, "4a3ed831-efc4-4182-a715-092dd210eafb", 1)["job_id"] == "job_test"
    client.heartbeat("node_test", "RUNNING", {"job_id": "job_test", "attempt_id": assigned["attempt_id"],
                                                "lease_token": assigned["lease_token"]})
    assert client.submit("job_test", {"job_id": "job_test", "outcome": "SUCCEEDED"}, {})["accepted"] is True
    assert len(calls) == 4


def test_claim_network_retry_reuses_persisted_key(tmp_path):
    class Client:
        calls = []

        def claim(self, worker_id, model_hash, key, capacity):
            self.calls.append((key, capacity))
            if len(self.calls) == 1:
                raise BackendUnavailable("lost claim response")
            return None

    client = Client()
    agent = WorkerAgent(config(tmp_path), client=client, runner=FakeRunner())
    assert agent.run_once() is None
    assert agent.claim_key_file.exists()
    assert agent.run_once() is None
    assert client.calls[0][0] == client.calls[1][0]
    assert [capacity for _, capacity in client.calls] == [1, 0]
    assert not agent.claim_key_file.exists()


def test_full_mock_inference_result_upload_and_temp_cleanup(tmp_path):
    data = b"synthetic input"
    assigned = claim(data)

    class Client:
        submissions = []

        def heartbeat(self, worker_id, activity, active):
            return {"lease_expire_time": iso(90), "server_time": iso()}

        def submit(self, job_id, manifest, assets):
            self.submissions.append((job_id, manifest, assets))
            return {"job_id": job_id, "attempt_id": assigned["attempt_id"], "accepted": True,
                    "job_status": "COMPLETED", "result_id": "result_test"}

    def input_server(request):
        return httpx.Response(200, content=data)

    runner, client = FakeRunner(), Client()
    agent = WorkerAgent(config(tmp_path), client=client, runner=runner,
                        download_transport=httpx.MockTransport(input_server))
    assert agent.process_claim(assigned)["accepted"] is True
    assert runner.calls == 1
    job_id, manifest, assets = client.submissions[0]
    assert job_id == assigned["job_id"] and manifest["input_sha256"] == assigned["input_reference"]["sha256"]
    assert manifest["result"]["source"] == "LIVE_CASE" and manifest["assets"] == [] and assets == {}
    assert list(agent.temp_root.iterdir()) == []


def test_unconfirmed_lease_skips_inference_and_upload(tmp_path):
    class Client:
        def heartbeat(self, *_args):
            raise BackendUnavailable("offline")

        def submit(self, *_args):
            pytest.fail("expired lease submitted a result")

    runner = FakeRunner()
    agent = WorkerAgent(config(tmp_path), client=Client(), runner=runner)
    with pytest.raises(BackendUnavailable):
        agent.process_claim(claim(b"synthetic input", expires=-1))
    assert runner.calls == 0


def test_server_expired_lease_skips_inference_and_upload(tmp_path):
    class Client:
        def heartbeat(self, *_args):
            return {"lease_expire_time": iso(-1), "server_time": iso()}

        def submit(self, *_args):
            pytest.fail("stale lease submitted a result")

    runner = FakeRunner()
    agent = WorkerAgent(config(tmp_path), client=Client(), runner=runner)
    with pytest.raises(LeaseExpired):
        agent.process_claim(claim(b"synthetic input"))
    assert runner.calls == 0


def test_model_hash_mismatch_reports_failure_without_inference(tmp_path):
    assigned = claim(b"synthetic input")
    assigned["model_version"]["checkpoint_sha256"] = "a" * 64

    class BadRunner(FakeRunner):
        def run(self, *_args):
            raise ModelHashMismatch("wrong model")

    class Client:
        manifest = None

        def heartbeat(self, *_args):
            return {"lease_expire_time": iso(90), "server_time": iso()}

        def submit(self, job_id, manifest, assets):
            self.manifest = manifest
            assert assets == {}
            return {"job_id": job_id, "attempt_id": assigned["attempt_id"], "accepted": True,
                    "job_status": "FAILED", "result_id": None}

    client = Client()
    agent = WorkerAgent(config(tmp_path), client=client, runner=BadRunner(),
                        download_transport=httpx.MockTransport(lambda _r: httpx.Response(200, content=b"synthetic input")))
    assert agent.process_claim(assigned)["accepted"] is True
    assert client.manifest["outcome"] == "FAILED"
    assert client.manifest["error"]["code"] == "MODEL_HASH_MISMATCH"


def test_duplicate_result_after_lost_response_reuses_identical_manifest(tmp_path):
    assigned = claim(b"synthetic input")

    class Client:
        calls = []

        def heartbeat(self, *_args):
            return {"lease_expire_time": iso(90), "server_time": iso()}

        def submit(self, job_id, manifest, assets):
            self.calls.append(json.dumps(manifest, sort_keys=True))
            if len(self.calls) == 1:
                raise BackendUnavailable("response lost after acceptance")
            return {"job_id": job_id, "attempt_id": assigned["attempt_id"], "accepted": True,
                    "job_status": "COMPLETED", "result_id": "result_test"}

    client = Client()
    agent = WorkerAgent(config(tmp_path), client=client, runner=FakeRunner(),
                        download_transport=httpx.MockTransport(lambda _r: httpx.Response(200, content=b"synthetic input")))
    agent.stop_event.wait = lambda _seconds: False
    assert agent.process_claim(assigned)["accepted"] is True
    assert len(client.calls) == 2 and client.calls[0] == client.calls[1]


def test_expired_signed_url_refreshes_same_claim_key(tmp_path):
    assigned = claim(b"synthetic input")
    refreshed = {**assigned, "input_reference": {**assigned["input_reference"],
                                                  "url": "https://objects.example/refreshed"}}

    class Client:
        claims = []

        def heartbeat(self, *_args):
            return {"lease_expire_time": iso(90), "server_time": iso()}

        def claim(self, worker_id, model_hash, key, capacity):
            self.claims.append((key, capacity))
            return refreshed

        def submit(self, job_id, manifest, assets):
            return {"job_id": job_id, "attempt_id": assigned["attempt_id"], "accepted": True,
                    "job_status": "COMPLETED", "result_id": "result_test"}

    def input_server(request):
        return httpx.Response(403 if request.url.path == "/input" else 200,
                              content=b"synthetic input" if request.url.path != "/input" else b"")

    client = Client()
    agent = WorkerAgent(config(tmp_path), client=client, runner=FakeRunner(),
                        download_transport=httpx.MockTransport(input_server))
    assert agent.process_claim(assigned, "4a3ed831-efc4-4182-a715-092dd210eafb")["accepted"] is True
    assert client.claims == [("4a3ed831-efc4-4182-a715-092dd210eafb", 0)]


def test_backend_auth_error_has_only_stable_code():
    def backend(_request):
        return httpx.Response(401, json={"code": "WORKER_UNAUTHENTICATED", "message": "secret detail"})

    client = WorkerClient("https://backend.example", "test-worker-secret", httpx.MockTransport(backend))
    with pytest.raises(WorkerAPIError, match="WORKER_UNAUTHENTICATED") as exc:
        client.register("node_test", MODEL_SHA, {"accelerator": "CPU"})
    assert "secret detail" not in str(exc.value)


# These are synthetic leak sentinels, not credentials or patient data.
_DIAGNOSTIC_SECRET = (
    '/private/synthetic-patient/file.dcm token=synthetic-secret '
    'https://synthetic-user:synthetic-password@objects.example/input?signature=synthetic-signature '
    'PatientName=SyntheticLeakSentinel'
)


class UnprintableDiagnosticError(RuntimeError):
    def __str__(self):
        raise AssertionError('diagnostics must not stringify an exception')


# A custom type name must not become a log label either.
UnprintableDiagnosticError.__name__ = 'SyntheticPrivateTypeName'


@pytest.mark.parametrize('error_type,category,code', [
    (InvalidWorkerInput, 'invalid_worker_input', 'PREPROCESSING_FAILED'),
    (OutOfMemoryError, 'cuda_out_of_memory', 'TEMPORARY_GPU_UNAVAILABLE'),
    (ModelHashMismatch, 'model_hash', 'MODEL_HASH_MISMATCH'),
    (ValueError, 'value_error', 'PREPROCESSING_FAILED'),
    (RuntimeError, 'runtime_error', 'INFERENCE_FAILED'),
    (ModuleNotFoundError, 'module_not_found', 'INFERENCE_FAILED'),
    (ImportError, 'import_error', 'INFERENCE_FAILED'),
    (FileNotFoundError, 'file_not_found', 'INFERENCE_FAILED'),
    (PermissionError, 'permission_error', 'INFERENCE_FAILED'),
    (OSError, 'os_error', 'INFERENCE_FAILED'),
    (TypeError, 'type_error', 'INFERENCE_FAILED'),
    (MemoryError, 'memory_error', 'INFERENCE_FAILED'),
    (UnprintableDiagnosticError, 'unclassified', 'INFERENCE_FAILED'),
], ids=['invalid-input', 'cuda-oom', 'model-hash', 'value', 'runtime', 'module', 'import', 'file', 'permission', 'os', 'type', 'memory', 'custom'])
def test_failure_diagnostics_are_closed_set_and_preserve_protocol(
        tmp_path, caplog, error_type, category, code):
    assigned = claim(b'synthetic input')

    class FailingRunner(FakeRunner):
        released = False

        def run(self, *_args):
            self.calls += 1
            try:
                raise RuntimeError(_DIAGNOSTIC_SECRET)
            except RuntimeError as cause:
                raise error_type(_DIAGNOSTIC_SECRET) from cause

        def release_cached_memory(self):
            self.released = True

    class Client:
        submissions = []

        def heartbeat(self, *_args):
            return {'lease_expire_time': iso(90), 'server_time': iso()}

        def submit(self, job_id, manifest, assets):
            self.submissions.append((manifest, assets))
            return {'job_id': job_id, 'attempt_id': assigned['attempt_id'],
                    'accepted': True, 'job_status': 'FAILED', 'result_id': None}

    runner, client = FailingRunner(), Client()
    agent = WorkerAgent(config(tmp_path), client=client, runner=runner,
                       download_transport=httpx.MockTransport(
                           lambda _r: httpx.Response(200, content=b'synthetic input')))
    with caplog.at_level('ERROR', logger='epilocate.worker'):
        assert agent.process_claim(assigned)['accepted'] is True
    assert runner.calls == 1 and runner.released
    assert len(client.submissions) == 1
    manifest, assets = client.submissions[0]
    assert manifest['outcome'] == 'FAILED'
    assert manifest['error']['code'] == code and assets == {}
    assert list(agent.temp_root.iterdir()) == []
    assert agent._active is None and agent._lease_deadline == 0.0
    records = [record for record in caplog.records if record.name == 'epilocate.worker']
    assert len(records) == 1
    record = records[0]
    assert record.getMessage() == f'Worker attempt failed: code={code} category={category}'
    assert record.args == (code, category)
    assert record.exc_info is None and record.exc_text is None and record.stack_info is None
    output = caplog.text + json.dumps(manifest)
    for sentinel in [_DIAGNOSTIC_SECRET, 'synthetic-secret', 'synthetic-password',
                     'synthetic-signature', 'SyntheticLeakSentinel', 'SyntheticPrivateTypeName',
                     '/private/synthetic-patient']:
        assert sentinel not in output


def test_failure_diagnostic_known_worker_categories(caplog):
    import torch
    from worker.agent import InputDownloadFailed, InputHashMismatch, _log_attempt_failure
    from worker.inference import InvalidWorkerInput

    for error_type, category, code in [
        (InputDownloadFailed, 'input_download', 'INPUT_DOWNLOAD_FAILED'),
        (InputHashMismatch, 'input_hash', 'INPUT_HASH_MISMATCH'),
        (ModelHashMismatch, 'model_hash', 'MODEL_HASH_MISMATCH'),
        (InvalidWorkerInput, 'invalid_worker_input', 'PREPROCESSING_FAILED'),
        (torch.cuda.OutOfMemoryError, 'cuda_out_of_memory', 'TEMPORARY_GPU_UNAVAILABLE'),
    ]:
        caplog.clear()
        with caplog.at_level('ERROR', logger='epilocate.worker'):
            _log_attempt_failure(error_type(_DIAGNOSTIC_SECRET), code)
        assert caplog.messages == [f'Worker attempt failed: code={code} category={category}']
        assert caplog.records[0].exc_info is None


@pytest.mark.parametrize('mode,code,category', [
    ('download', 'INPUT_DOWNLOAD_FAILED', 'input_download'),
    ('hash', 'INPUT_HASH_MISMATCH', 'input_hash'),
])
def test_download_failure_diagnostics_preserve_protocol(tmp_path, caplog, mode, code, category):
    assigned = claim(b'synthetic input')
    assigned['input_reference']['url'] += '?signature=synthetic-signature'

    class Client:
        submissions = []

        def heartbeat(self, *_args):
            return {'lease_expire_time': iso(90), 'server_time': iso()}

        def submit(self, job_id, manifest, assets):
            self.submissions.append((manifest, assets))
            return {'job_id': job_id, 'attempt_id': assigned['attempt_id'],
                    'accepted': True, 'job_status': 'FAILED', 'result_id': None}

    def input_server(request):
        if mode == 'download':
            raise httpx.ReadError(_DIAGNOSTIC_SECRET, request=request)
        return httpx.Response(200, content=_DIAGNOSTIC_SECRET.encode())

    runner, client = FakeRunner(), Client()
    agent = WorkerAgent(config(tmp_path), client=client, runner=runner,
                       download_transport=httpx.MockTransport(input_server))
    with caplog.at_level('ERROR', logger='epilocate.worker'):
        assert agent.process_claim(assigned)['accepted'] is True
    assert runner.calls == 0 and len(client.submissions) == 1
    manifest, assets = client.submissions[0]
    assert manifest['outcome'] == 'FAILED'
    assert manifest['error']['code'] == code and assets == {}
    assert list(agent.temp_root.iterdir()) == []
    assert agent._active is None and agent._lease_deadline == 0.0
    assert caplog.messages == [f'Worker attempt failed: code={code} category={category}']
    record = caplog.records[0]
    assert record.args == (code, category)
    assert record.exc_info is None and record.exc_text is None and record.stack_info is None
    output = caplog.text + json.dumps(manifest)
    for sentinel in ['synthetic-secret', 'synthetic-password', 'synthetic-signature',
                     'SyntheticLeakSentinel', '/private/synthetic-patient']:
        assert sentinel not in output


@pytest.mark.parametrize('error', [
    BackendUnavailable(_DIAGNOSTIC_SECRET),
    WorkerAPIError(503, 'WORKER_NOT_REGISTERED'),
    LeaseExpired(_DIAGNOSTIC_SECRET),
], ids=['backend-unavailable', 'worker-api', 'lease-expired'])
def test_control_flow_errors_do_not_become_failure_diagnostics(tmp_path, caplog, error):
    class FailingRunner(FakeRunner):
        released = False

        def run(self, *_args):
            raise error

        def release_cached_memory(self):
            self.released = True

    class Client:
        def heartbeat(self, *_args):
            return {'lease_expire_time': iso(90), 'server_time': iso()}

        def submit(self, *_args):
            pytest.fail('control-flow error must not submit a failure manifest')

    runner = FailingRunner()
    agent = WorkerAgent(config(tmp_path), client=Client(), runner=runner,
                       download_transport=httpx.MockTransport(
                           lambda _r: httpx.Response(200, content=b'synthetic input')))
    with caplog.at_level('ERROR', logger='epilocate.worker'):
        with pytest.raises(type(error)) as caught:
            agent.process_claim(claim(b'synthetic input'))
    assert caught.value is error
    assert not [record for record in caplog.records if record.name == 'epilocate.worker']
    assert runner.released and list(agent.temp_root.iterdir()) == []
    assert agent._active is None and agent._lease_deadline == 0.0
