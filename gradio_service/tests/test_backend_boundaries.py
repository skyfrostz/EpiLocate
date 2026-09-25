"""Backend concurrency, cancellation, and access boundaries (no model inference)."""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from gradio_debug.inference import InferenceAdapter
from gradio_debug.jobs import JobManager, utc_now
from gradio_debug.storage import InputError, Storage


def test_idempotency_reservation_is_atomic_across_storage_instances(tmp_path):
    first, second = Storage(tmp_path), Storage(tmp_path)
    gate = threading.Barrier(2)

    def claim(store):
        gate.wait()
        try:
            return store.reserve_idempotency("same-key-001", "same-digest")
        except InputError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(claim, (first, second)))
    assert outcomes.count(None) == 1
    assert outcomes.count("IDEMPOTENCY_CONFLICT") == 1
    first.store_idempotent_response("same-key-001", "same-digest", {"job_id": "one"})
    assert second.reserve_idempotency("same-key-001", "same-digest") == {"job_id": "one"}
    with pytest.raises(InputError) as conflict:
        second.reserve_idempotency("same-key-001", "different-digest")
    assert conflict.value.code == "IDEMPOTENCY_CONFLICT"


def test_queued_job_cancel_and_failed_job_are_distinct(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_MODE", "mock")
    store = Storage(tmp_path)
    store.save_dicom_bytes(b"synthetic unit data", "CASE-test", "SLICE-test", 2, 2, utc_now())
    entered, release = threading.Event(), threading.Event()

    class FailingBaseline:
        def ready(self):
            return True

        def predict(self, *_args):
            entered.set()
            assert release.wait(5)
            raise RuntimeError("private diagnostic details")

    manager = JobManager(store, InferenceAdapter(store), baseline=FailingBaseline())
    try:
        running = manager.submit_analysis("CASE-test", "SLICE-test", "prediction")
        assert entered.wait(5)
        queued = manager.submit_analysis("CASE-test", "SLICE-test", "prediction")
        assert manager.cancel_analysis(queued.job_id) == "cancelled"
        assert manager.get(queued.job_id).status == "cancelled"
        assert manager.get(queued.job_id).error_code == "JOB_CANCELLED"
        assert manager.cancel_analysis(running.job_id) == "not_queued"
        release.set()
        for _ in range(100):
            failed = manager.get(running.job_id)
            if failed.status == "failed":
                break
            time.sleep(.02)
        assert failed.status == "failed"
        assert failed.error_code == "INFERENCE_FAILED"
        assert "private diagnostic" not in failed.error_message
    finally:
        release.set()
        manager.close()


def test_imaging_api_requires_configured_token(monkeypatch):
    from gradio_debug.app import app

    monkeypatch.setenv("EPILOCATE_API_TOKEN", "test-local-token")
    with TestClient(app) as client:
        assert client.get("/api/v1/cases/unknown").status_code == 401
        assert client.get("/api/v1/assets/unknown", params={"result_id": "unknown"}).json()["code"] == "UNAUTHENTICATED"
        assert client.get("/gradio").status_code == 401
        authorized = client.get("/api/v1/cases/unknown", headers={"Authorization": "Bearer test-local-token"})
        assert authorized.status_code == 404
        assert authorized.json()["code"] == "RESULT_NOT_FOUND"


def test_result_ownership_mismatch_is_rejected(tmp_path):
    from gradio_debug.contracts import JobStatus

    store = Storage(tmp_path)
    store.save_dicom_bytes(b"synthetic unit data", "CASE-owner", "SLICE-owner", 2, 2, utc_now())
    store.create_job(JobStatus(job_id="job-owner", case_id="CASE-owner", status="success",
                               stage="complete", progress=100, created_at=utc_now()))
    store.write_analysis_result("job-owner", {"result_id": "RESULT-owner", "case_id": "CASE-owner",
                                               "slice_id": "SLICE-other"})
    assert store.get_analysis_result("RESULT-owner") is None
