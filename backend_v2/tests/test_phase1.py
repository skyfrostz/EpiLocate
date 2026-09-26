from __future__ import annotations

import hashlib
import json
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend_v2.api.app import app, get_db
from backend_v2.db.base import Base
from backend_v2.models.entities import Case, InferenceJob, InferenceResult, ModelVersion, Patient, Series, Slice, Study, User, WorkerNode
from backend_v2.services.common import aware, now, public_id
from backend_v2.services import jobs


HASH = "a" * 64
INPUT = "b" * 64
USER_TOKEN = "test-user-token-0123456789"
WORKER_TOKEN = "test-worker-token-0123456789"


class FakeStore:
    def __init__(self):
        self.objects = {}

    def put(self, body, _media, prefix):
        key = f"{prefix}/{uuid.uuid4()}"
        self.objects[key] = body
        return key

    def delete(self, key):
        self.objects.pop(key, None)

    def signed_get(self, _slice):
        return "https://private.invalid/test-signed-url"


@pytest.fixture
def ctx(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setenv("EPILOCATE_V2_USER_TOKEN_HASHES", json.dumps({"test-subject": hashlib.sha256(USER_TOKEN.encode()).hexdigest()}))
    monkeypatch.setenv("EPILOCATE_V2_LEASE_SECRET", "0123456789abcdef0123456789abcdef")
    store = FakeStore()
    import backend_v2.api.app as api_module
    monkeypatch.setattr(api_module, "ObjectStore", lambda: store)

    def override():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override
    with factory.begin() as db:
        user = User(auth_subject="test-subject")
        other = User(auth_subject="other")
        model = ModelVersion(model_id="baseline_resnet18", version="v1", checkpoint_sha256=HASH, preprocessing_version="prep-v1", protocol_id="stage1-occlusion-instability-v1")
        worker = WorkerNode(node_id=public_id("node"), token_hash=hashlib.sha256(WORKER_TOKEN.encode()).hexdigest(), display_name="test", supported_models=[{"model_id": "baseline_resnet18", "checkpoint_sha256": HASH}], registered_at=now(), last_heartbeat_at=now())
        db.add_all([user, other, model, worker])
        db.flush()
        ids = (user.id, other.id, model.id, worker.id, worker.node_id)
    yield factory, store, ids
    app.dependency_overrides.clear()
    engine.dispose()


def seeded_case(factory, ids):
    user_id, _, _, _, _ = ids
    with factory.begin() as db:
        patient = Patient(owner_user_id=user_id, anonymous_id=public_id("pat")); db.add(patient); db.flush()
        case = Case(owner_user_id=user_id, patient_id=patient.id, anonymous_id=public_id("case"), status="READY"); db.add(case); db.flush()
        study = Study(case_id=case.id, study_ref=public_id("study")); db.add(study); db.flush()
        series = Series(study_id=study.id, case_id=case.id, series_ref=public_id("series")); db.add(series); db.flush()
        sl = Slice(series_id=series.id, case_id=case.id, slice_ref=public_id("slice"), ordinal=0, width_px=32, height_px=32, source_sha256=INPUT, staging_object_key="input/test", staging_expires_at=now() + timedelta(days=7)); db.add(sl)
        return case.anonymous_id, sl.slice_ref


def create_job(factory, ids, case_id, slice_id, key="12345678"):
    with factory.begin() as db:
        job, _ = jobs.create_job(db, ids[0], case_public_id=case_id, slice_public_id=slice_id, model_id="baseline_resnet18", kind="PREDICTION", protocol_id=None, scales=None, key=key)
        return job.public_id


def claim(factory, store, ids, key=None):
    with factory.begin() as db:
        worker = db.get(WorkerNode, ids[3])
        return jobs.claim_job(db, worker, key or uuid.uuid4(), 1, worker.supported_models, store.signed_get)


def manifest_for(payload):
    return {"worker_id": payload["model_version"].get("worker_id", ""), "job_id": payload["job_id"], "attempt_id": payload["attempt_id"], "lease_token": payload["lease_token"], "outcome": "SUCCEEDED", "model_id": "baseline_resnet18", "checkpoint_sha256": HASH, "input_sha256": INPUT, "result": {"contract_version": "2.0", "source": "LIVE_CASE", "case_id": payload["case_id"], "slice_id": payload["job_parameters"]["slice_id"], "kind": "PREDICTION", "model_id": "baseline_resnet18", "model_version": HASH, "preprocessing_version": "prep-v1", "protocol_id": "stage1-occlusion-instability-v1", "prediction": {"predicted_class": 0, "class_label": "negative", "positive_probability": 0.1, "predicted_class_confidence": 0.9, "inference_time_ms": 25}}, "assets": []}


def test_case_create_and_idempotency(ctx):
    factory, _, ids = ctx
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {USER_TOKEN}", "Idempotency-Key": "case-create-01"}
    first = client.post("/api/v2/cases", json={"patient_id": None}, headers=headers)
    assert first.status_code == 201, first.text
    second = client.post("/api/v2/cases", json={"patient_id": None}, headers=headers)
    assert second.json() == first.json()
    assert client.get("/api/v2/cases", headers=headers).json()["items"][0]["case_id"] == first.json()["case_id"]
    with factory() as db:
        assert db.scalar(select(Case).where(Case.anonymous_id == first.json()["case_id"])).owner_user_id == ids[0]


def test_case_cursor_and_owner_scope(ctx):
    factory, _, ids = ctx
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {USER_TOKEN}"}
    for suffix in ("01", "02"):
        response = client.post("/api/v2/cases", json={"patient_id": None}, headers={**headers, "Idempotency-Key": f"case-cursor-{suffix}"})
        assert response.status_code == 201
    first_page = client.get("/api/v2/cases?limit=1", headers=headers)
    assert first_page.status_code == 200
    cursor = first_page.json()["next_cursor"]
    assert cursor and "case_" not in cursor
    second_page = client.get("/api/v2/cases", params={"limit": 1, "cursor": cursor}, headers=headers)
    assert second_page.status_code == 200
    assert first_page.json()["items"][0]["case_id"] != second_page.json()["items"][0]["case_id"]
    assert client.get("/api/v2/cases", params={"cursor": cursor + "x"}, headers=headers).status_code == 422
    with factory.begin() as db:
        patient = Patient(owner_user_id=ids[1], anonymous_id=public_id("pat")); db.add(patient); db.flush()
        foreign = Case(owner_user_id=ids[1], patient_id=patient.id, anonymous_id=public_id("case")); db.add(foreign); db.flush()
        foreign_id = foreign.anonymous_id
    assert client.get(f"/api/v2/cases/{foreign_id}", headers=headers).status_code == 404


def test_job_transitions_claim_heartbeat_duplicate_result(ctx):
    factory, store, ids = ctx
    case_id, slice_id = seeded_case(factory, ids)
    job_id = create_job(factory, ids, case_id, slice_id)
    with factory() as db:
        assert db.scalar(select(InferenceJob).where(InferenceJob.public_id == job_id)).status == "CREATED"
    payload = claim(factory, store, ids)
    assert payload["job_id"] == job_id and payload["attempt_no"] == 1
    with factory.begin() as db:
        worker = db.get(WorkerNode, ids[3])
        reply = jobs.heartbeat(db, worker, "RUNNING", {"job_id": job_id, "attempt_id": payload["attempt_id"], "lease_token": payload["lease_token"]})
        assert reply["lease_expire_time"]
    body = manifest_for(payload); body["worker_id"] = ids[4]
    with factory.begin() as db:
        first = jobs.submit_result(db, store, db.get(WorkerNode, ids[3]), body, {})
        assert first["job_status"] == "COMPLETED"
    with factory.begin() as db:
        second = jobs.submit_result(db, store, db.get(WorkerNode, ids[3]), body, {})
        assert second == first
        job = db.scalar(select(InferenceJob).where(InferenceJob.public_id == job_id))
        assert job.status == "COMPLETED" and job.retry_count == 0
        assert db.scalar(select(InferenceResult).where(InferenceResult.job_id == job.id))
    changed = json.loads(json.dumps(body))
    changed["result"]["prediction"]["positive_probability"] = 0.2
    with factory() as db:
        with pytest.raises(Exception) as exc:
            jobs.submit_result(db, store, db.get(WorkerNode, ids[3]), changed, {})
        assert "RESULT_CONFLICT" in str(exc.value)


def test_lease_expiry_retry_and_stale_submit(ctx):
    factory, store, ids = ctx
    case_id, slice_id = seeded_case(factory, ids)
    job_id = create_job(factory, ids, case_id, slice_id)
    payload = claim(factory, store, ids)
    with factory.begin() as db:
        job = db.scalar(select(InferenceJob).where(InferenceJob.public_id == job_id))
        job.lease_expire_time = now() - timedelta(seconds=1)
        attempt = db.get(jobs.JobAttempt, uuid.UUID(payload["attempt_id"]))
        attempt.lease_expire_time = job.lease_expire_time
    with factory.begin() as db:
        assert jobs.recover_expired(db) == 1
        job = db.scalar(select(InferenceJob).where(InferenceJob.public_id == job_id))
        assert job.status == "QUEUED" and job.attempt_no == 1 and job.retry_count == 0
        job.next_attempt_at = now() - timedelta(seconds=1)
    with factory.begin() as db:
        stale = manifest_for(payload); stale["worker_id"] = ids[4]
        with pytest.raises(Exception) as exc:
            jobs.submit_result(db, store, db.get(WorkerNode, ids[3]), stale, {})
        assert "STALE_ATTEMPT" in str(exc.value)
    new = claim(factory, store, ids)
    assert new["attempt_no"] == 2
    with factory() as db:
        job = db.scalar(select(InferenceJob).where(InferenceJob.public_id == job_id))
        assert job.status == "RUNNING" and job.retry_count == 1


def test_claim_idempotency_and_failure_retry(ctx):
    factory, store, ids = ctx
    case_id, slice_id = seeded_case(factory, ids)
    create_job(factory, ids, case_id, slice_id)
    key = uuid.uuid4()
    first = claim(factory, store, ids, key)
    with factory.begin() as db:
        worker = db.get(WorkerNode, ids[3])
        replay = jobs.claim_job(db, worker, key, 0, worker.supported_models, store.signed_get)
        assert replay["attempt_id"] == first["attempt_id"]
        failed = manifest_for(first); failed["worker_id"] = ids[4]
        failed.update(outcome="FAILED", result=None, assets=[], error={"code": "TEMPORARY_GPU_UNAVAILABLE", "message": "GPU unavailable."})
        accepted = jobs.submit_result(db, store, worker, failed, {})
        assert accepted["job_status"] == "QUEUED"
    with factory() as db:
        job = db.scalar(select(InferenceJob).where(InferenceJob.public_id == first["job_id"]))
        assert job.attempt_no == 1 and job.retry_count == 0 and aware(job.next_attempt_at) > now()


def test_worker_http_contract_and_result_alias(ctx):
    factory, _, ids = ctx
    case_id, slice_id = seeded_case(factory, ids)
    job_id = create_job(factory, ids, case_id, slice_id)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {WORKER_TOKEN}", "X-Request-ID": str(uuid.uuid4())}
    cap = {"model_id": "baseline_resnet18", "checkpoint_sha256": HASH}
    register = client.post("/api/v2/workers/register", headers=headers, json={"worker_id": ids[4], "worker_version": "1.0.0", "hardware": {"accelerator": "CPU"}, "supported_model_versions": [cap], "max_concurrent_jobs": 1})
    assert register.status_code == 200, register.text
    hb = client.post("/api/v2/workers/heartbeat", headers=headers, json={"worker_id": ids[4], "activity_state": "IDLE", "active_attempt": None})
    assert hb.status_code == 200, hb.text
    claim_headers = {**headers, "Idempotency-Key": str(uuid.uuid4())}
    claimed = client.post("/api/v2/workers/jobs/claim", headers=claim_headers, json={"worker_id": ids[4], "available_capacity": 1, "supported_model_versions": [cap]})
    assert claimed.status_code == 200, claimed.text
    payload = claimed.json()
    assert payload["job_id"] == job_id and payload["input_reference"]["sha256"] == INPUT
    replay = client.post("/api/v2/workers/jobs/claim", headers=claim_headers, json={"worker_id": ids[4], "available_capacity": 0, "supported_model_versions": [cap]})
    assert replay.status_code == 200 and replay.json()["attempt_id"] == payload["attempt_id"]
    body = manifest_for(payload); body["worker_id"] = ids[4]
    completed = client.post(f"/api/v2/workers/jobs/{job_id}/result", headers=headers, data={"manifest": json.dumps(body)})
    assert completed.status_code == 200 and completed.json()["job_status"] == "COMPLETED", completed.text
    duplicate = client.post("/api/v2/workers/results", headers=headers, data={"manifest": json.dumps(body)})
    assert duplicate.status_code == 200 and duplicate.json() == completed.json()
    user_headers = {"Authorization": f"Bearer {USER_TOKEN}"}
    result = client.get(f"/api/v2/results/{completed.json()['result_id']}", headers=user_headers)
    assert result.status_code == 200 and result.json()["source"] == "LIVE_CASE"


def test_retry_exhaustion(ctx):
    factory, store, ids = ctx
    case_id, slice_id = seeded_case(factory, ids)
    job_id = create_job(factory, ids, case_id, slice_id)
    for number in (1, 2, 3):
        payload = claim(factory, store, ids)
        assert payload["attempt_no"] == number
        with factory.begin() as db:
            job = db.scalar(select(InferenceJob).where(InferenceJob.public_id == job_id))
            attempt = db.get(jobs.JobAttempt, uuid.UUID(payload["attempt_id"]))
            jobs.expire_and_retry(db, job, attempt, "TEMPORARY_GPU_UNAVAILABLE")
            if number < 3:
                job.next_attempt_at = now() - timedelta(seconds=1)
            else:
                assert job.status == "FAILED" and job.retry_count == 2 and job.failure_reason == "TEMPORARY_GPU_UNAVAILABLE"


def test_result_rejects_extra_patient_data(ctx):
    factory, store, ids = ctx
    case_id, slice_id = seeded_case(factory, ids)
    create_job(factory, ids, case_id, slice_id)
    payload = claim(factory, store, ids)
    manifest = manifest_for(payload); manifest["worker_id"] = ids[4]
    manifest["result"]["patient_name"] = "forbidden"
    with factory() as db:
        with pytest.raises(Exception) as exc:
            jobs.submit_result(db, store, db.get(WorkerNode, ids[3]), manifest, {})
        assert "RESULT_SCHEMA_INVALID" in str(exc.value)
