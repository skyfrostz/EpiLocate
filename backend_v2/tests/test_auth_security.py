from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend_v2.api.app import app, get_db
from backend_v2.auth.credentials import issue_user_credential
from backend_v2.db.base import Base
from backend_v2.models.entities import Asset, Case, InferenceJob, InferenceResult, JobAttempt, ModelVersion, Patient, Series, Slice, Study, User, UserCredential, WorkerNode
from backend_v2.scripts.provision_user import write_user_env
from backend_v2.services.common import digest, now, public_id


RAW = b"synthetic-dicom-for-auth"
MODEL_SHA = "a" * 64
INPUT_SHA = hashlib.sha256(RAW).hexdigest()
USER_AGENT = {"User-Agent": "security-test"}


class MemoryStore:
    def __init__(self):
        self.objects: dict[str, tuple[bytes, str]] = {}

    def put(self, body: bytes, media: str, prefix: str):
        key = f"{prefix}/{uuid.uuid4().hex}"
        self.objects[key] = (body, media)
        return key

    def delete(self, key: str):
        self.objects.pop(key, None)

    def read(self, key: str):
        return self.objects[key]

    def signed_get(self, _slice):
        return "https://objects.example/input/signed"


@pytest.fixture
def security_ctx(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    store = MemoryStore()
    api_module = __import__("backend_v2.api.app", fromlist=["ObjectStore"])
    monkeypatch.setattr(api_module, "ObjectStore", lambda: store)
    monkeypatch.setenv("EPILOCATE_V2_ALLOW_ENV_TOKENS", "false")
    monkeypatch.setenv("EPILOCATE_V2_LEASE_SECRET", "0123456789abcdef0123456789abcdef")

    with factory.begin() as db:
        user_a = User(auth_subject="subject-a")
        user_b = User(auth_subject="subject-b")
        model = ModelVersion(model_id="baseline_resnet18", version="v1", checkpoint_sha256=MODEL_SHA, preprocessing_version="prep-v1", protocol_id="stage1-occlusion-instability-v1")
        worker = WorkerNode(node_id=public_id("node"), token_hash=hashlib.sha256(b"worker-secret-0123456789").hexdigest(), display_name="security-worker", supported_models=[{"model_id": "baseline_resnet18", "checkpoint_sha256": MODEL_SHA}], registered_at=now(), last_heartbeat_at=now())
        db.add_all([user_a, user_b, model, worker])
        db.flush()
        _, token_a = issue_user_credential(db, user_a, expires_in=timedelta(days=1), label="test-a")
        _, token_b = issue_user_credential(db, user_b, expires_in=timedelta(days=1), label="test-b")
        ids = {"a": user_a.id, "b": user_b.id, "model": model.id, "worker": worker.id, "worker_id": worker.node_id}

    def override():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override
    yield factory, store, ids, token_a, token_b, "worker-secret-0123456789"
    app.dependency_overrides.clear()
    engine.dispose()


def user_headers(token: str):
    return {**USER_AGENT, "Authorization": f"Bearer {token}"}


def seed_owned_case(factory, store: MemoryStore, ids):
    with factory.begin() as db:
        patient = Patient(owner_user_id=ids["a"], anonymous_id=public_id("pat"))
        db.add(patient)
        db.flush()
        case = Case(owner_user_id=ids["a"], patient_id=patient.id, anonymous_id=public_id("case"), status="READY")
        db.add(case)
        db.flush()
        study = Study(case_id=case.id, study_ref=public_id("study"))
        db.add(study)
        db.flush()
        series = Series(study_id=study.id, case_id=case.id, series_ref=public_id("series"))
        db.add(series)
        db.flush()
        input_key = "input/security-test"
        sl = Slice(series_id=series.id, case_id=case.id, slice_ref=public_id("slice"), ordinal=0, width_px=32, height_px=32, source_sha256=INPUT_SHA, staging_object_key=input_key, staging_expires_at=now() + timedelta(days=7))
        db.add(sl)
        db.flush()
        store.objects[input_key] = (RAW, "application/dicom")

        job = InferenceJob(public_id=public_id("job"), case_id=case.id, slice_id=sl.id, requested_by_user_id=ids["a"], model_version_id=ids["model"], kind="PREDICTION", status="COMPLETED", request_json={"kind": "PREDICTION", "case_id": case.anonymous_id, "slice_id": sl.slice_ref, "model_id": "baseline_resnet18", "protocol_id": "stage1-occlusion-instability-v1", "scales": []}, request_digest=digest({"case": case.anonymous_id}), idempotency_key="security-job-01", attempt_no=1, retry_count=0, finished_at=now())
        db.add(job)
        db.flush()
        attempt = JobAttempt(job_id=job.id, attempt_no=1, worker_node_id=ids["worker"], claim_key=uuid.uuid4(), claim_request_digest="b" * 64, lease_token_hash="c" * 64, outcome="SUCCEEDED", finished_at=now(), lease_expire_time=now())
        db.add(attempt)
        db.flush()
        result_json = {"contract_version": "2.0", "source": "LIVE_CASE", "case_id": case.anonymous_id, "slice_id": sl.slice_ref, "kind": "PREDICTION", "model_id": "baseline_resnet18", "model_version": MODEL_SHA, "preprocessing_version": "prep-v1", "protocol_id": "stage1-occlusion-instability-v1", "prediction": {"predicted_class": 0, "class_label": "negative", "positive_probability": 0.1, "predicted_class_confidence": 0.9, "inference_time_ms": 12}, "scale_summaries": [], "cross_scale": [], "positions": []}
        result = InferenceResult(job_id=job.id, case_id=case.id, accepted_attempt_id=attempt.id, model_version_id=ids["model"], result_json=result_json, metadata_json={"source": "LIVE_CASE"}, asset_manifest=[])
        db.add(result)
        db.flush()
        asset_key = "results/private-object-key"
        store.objects[asset_key] = (b"PNG-bytes", "image/png")
        asset = Asset(result_id=result.id, asset_id="response-test.png", object_key=asset_key, layer_kind="CANDIDATE_RESPONSE", width=2, height=2, coordinate_space="ALGORITHM_224", media_type="image/png", size_bytes=9, sha256=hashlib.sha256(b"PNG-bytes").hexdigest())
        db.add(asset)
        return case.anonymous_id, sl.slice_ref, job.public_id, f"result_{result.id.hex}", asset.asset_id


def test_credential_lifecycle_and_missing_invalid_expired_revoked(security_ctx):
    factory, _, ids, token_a, _, _ = security_ctx
    client = TestClient(app)
    assert client.get("/api/v2/cases", headers=USER_AGENT).status_code == 401
    assert client.get("/api/v2/cases", headers=user_headers("invalid-credential-0123456789")).status_code == 401
    with factory.begin() as db:
        user = db.get(User, ids["a"])
        expired_row, expired_token = issue_user_credential(db, user, expires_in=timedelta(days=1), label="expired")
        expired_row.expires_at = now() - timedelta(seconds=1)
        revoked_row, revoked_token = issue_user_credential(db, user, expires_in=timedelta(days=1), label="revoked")
        revoked_row.revoked_at = now()
    assert client.get("/api/v2/cases", headers=user_headers(expired_token)).status_code == 401
    assert client.get("/api/v2/cases", headers=user_headers(revoked_token)).status_code == 401
    assert client.get("/api/v2/cases", headers=user_headers(token_a)).status_code == 200


def test_two_users_cannot_cross_case_job_result_dicom_or_asset(security_ctx):
    factory, store, ids, token_a, token_b, _ = security_ctx
    case_id, slice_id, job_id, result_id, asset_id = seed_owned_case(factory, store, ids)
    client = TestClient(app)
    assert client.get("/api/v2/cases", headers=user_headers(token_b)).json()["items"] == []
    for path in (
        f"/api/v2/cases/{case_id}",
        f"/api/v2/cases/{case_id}/dicom",
        f"/api/v2/jobs/{job_id}",
        f"/api/v2/predictions/{job_id}",
        f"/api/v2/results/{result_id}",
        f"/api/v2/results/{result_id}/positions?scale=16",
        f"/api/v2/results/{result_id}/assets/{asset_id}",
    ):
        response = client.get(path, headers=user_headers(token_b))
        assert response.status_code == 404, (path, response.text)
    create = client.post("/api/v2/predictions", json={"case_id": case_id, "slice_id": slice_id, "model_id": "baseline_resnet18"}, headers={**user_headers(token_b), "Idempotency-Key": "cross-owner-01"})
    assert create.status_code == 404
    assert client.get(f"/api/v2/results/{result_id}", headers=user_headers(token_a)).status_code == 200


def test_worker_and_user_credentials_are_not_interchangeable(security_ctx):
    factory, _, ids, token_a, _, worker_token = security_ctx
    client = TestClient(app)
    worker_headers = {"Authorization": f"Bearer {worker_token}", "X-Request-ID": str(uuid.uuid4())}
    assert client.get("/api/v2/cases", headers=worker_headers).status_code == 401
    user_worker_headers = {**user_headers(token_a), "X-Request-ID": str(uuid.uuid4())}
    rejected = client.post("/api/v2/workers/heartbeat", json={"worker_id": ids["worker_id"], "activity_state": "IDLE", "active_attempt": None}, headers=user_worker_headers)
    assert rejected.status_code == 401
    assert rejected.headers["cache-control"] == "no-store"
    with factory.begin() as db:
        db.get(WorkerNode, ids["worker"]).disabled_at = now()
    disabled = client.post("/api/v2/workers/heartbeat", json={"worker_id": ids["worker_id"], "activity_state": "IDLE", "active_attempt": None}, headers=worker_headers)
    assert disabled.status_code == 403
    with factory.begin() as db:
        db.get(WorkerNode, ids["worker"]).disabled_at = None
    mismatch = client.post("/api/v2/workers/heartbeat", json={"worker_id": "node_wrong", "activity_state": "IDLE", "active_attempt": None}, headers=worker_headers)
    assert mismatch.status_code == 403


def test_asset_route_hides_object_key_and_signed_url_has_ttl(monkeypatch, security_ctx):
    factory, store, ids, token_a, _, _ = security_ctx
    _, _, _, result_id, asset_id = seed_owned_case(factory, store, ids)
    client = TestClient(app)
    detail = client.get(f"/api/v2/results/{result_id}", headers=user_headers(token_a))
    assert detail.status_code == 200
    public_asset_url = detail.json()["assets"][0]["asset_url"]
    assert public_asset_url == f"/api/v2/results/{result_id}/assets/{asset_id}"
    assert "private-object-key" not in detail.text
    with factory.begin() as db:
        asset = db.scalar(select(Asset).where(Asset.asset_id == asset_id))
        asset.retention_until = now() - timedelta(seconds=1)
    assert client.get(public_asset_url, headers=user_headers(token_a)).status_code == 410

    monkeypatch.setenv("EPILOCATE_V2_S3_ENDPOINT", "https://s3.example")
    monkeypatch.setenv("EPILOCATE_V2_S3_PUBLIC_ENDPOINT", "https://s3.example")
    monkeypatch.setenv("EPILOCATE_V2_S3_BUCKET", "private")
    monkeypatch.setenv("EPILOCATE_V2_S3_ACCESS_KEY", "access")
    monkeypatch.setenv("EPILOCATE_V2_S3_SECRET_KEY", "secret")
    from backend_v2.services.storage import ObjectStore
    signed = ObjectStore().signed_key_get("input/private-object-key")
    assert "X-Amz-Expires=300" in signed
    with pytest.raises(Exception) as too_long:
        ObjectStore().signed_key_get("input/private-object-key", 301)
    assert "INVALID_SIGNED_URL_REQUEST" in str(too_long.value)
    expired_asset = Asset(result_id=uuid.uuid4(), asset_id="expired", object_key="results/expired", layer_kind="CANDIDATE_RESPONSE", width=2, height=2, coordinate_space="ALGORITHM_224", media_type="image/png", size_bytes=1, sha256="d" * 64, retention_until=now() - timedelta(seconds=1))
    with pytest.raises(Exception) as expired:
        ObjectStore().signed_asset_get(expired_asset)
    assert "ASSET_EXPIRED" in str(expired.value)


def test_user_credential_file_is_mode_0600(tmp_path: Path):
    path = tmp_path / "secure" / "user.env"
    write_user_env(path, "credential-value-that-is-long-enough-0123456789")
    assert path.stat().st_mode & 0o777 == 0o600
