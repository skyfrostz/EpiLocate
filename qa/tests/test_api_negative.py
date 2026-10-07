"""QA-only failure-path checks against the fixed P0 API implementation."""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from gradio_service.gradio_debug.app import app, storage
from gradio_service.gradio_debug.contracts import JobStatus
from gradio_service.gradio_debug.jobs import utc_now


FIXTURE = Path(__file__).resolve().parents[2] / "docs/interfaces/fixtures/p0_synthetic_ct.dcm"


def test_oversize_upload_is_rejected_without_case_creation():
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/cases", headers={"Idempotency-Key": uuid.uuid4().hex},
            data={"input_kind": "dicom_series"},
            files={"files": ("synthetic.dcm", FIXTURE.read_bytes() + b"0" * (storage.max_upload_bytes + 1),
                             "application/dicom")},
        )
    assert response.status_code == 413
    assert response.json()["code"] == "INVALID_REQUEST"


def test_failed_job_returns_failed_status_and_no_mock_result():
    job_id = str(uuid.uuid4())
    storage.create_job(JobStatus(job_id=job_id, case_id="CASE-SYNTHETIC-QA", status="queued",
                                 stage="queued", progress=0, created_at=utc_now()))
    storage.update_job(job_id, status="failed", stage="failed", progress=100, finished_at=utc_now(),
                       error_code="INFERENCE_FAILED",
                       error_message="Analysis failed; inspect protected server logs.")
    storage.mark_analysis_job(job_id, "PREDICTION")
    with TestClient(app) as client:
        status = client.get(f"/api/v1/jobs/{job_id}")
        result = client.get(f"/api/v1/jobs/{job_id}/result")
    assert status.status_code == 200
    assert status.json()["status"] == "FAILED"
    assert status.json()["error_code"] == "INFERENCE_FAILED"
    assert result.status_code == 500
    assert result.json()["code"] == "INFERENCE_FAILED"
    assert "prediction" not in result.json()
