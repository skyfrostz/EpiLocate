from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
import base64
from collections.abc import Iterator
from functools import lru_cache

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend_v2.db.base import make_engine, make_session_factory
from backend_v2.models.entities import Asset, Case, InferenceJob, InferenceResult, JobAttempt, ModelVersion, Slice, User, WorkerNode
from backend_v2.services import cases as case_service
from backend_v2.services import jobs as job_service
from backend_v2.services.common import aware, fail, iso, now, valid_key
from backend_v2.services.storage import ObjectStore


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CaseCreate(Strict):
    patient_id: str | None = None


class JobCreate(Strict):
    case_id: str
    slice_id: str
    model_id: str


class OcclusionCreate(JobCreate):
    protocol_id: str
    scales: list[int]


class ModelCapability(Strict):
    model_id: str
    checkpoint_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class Register(Strict):
    worker_id: str
    worker_version: str
    hardware: dict
    supported_model_versions: list[ModelCapability]
    max_concurrent_jobs: int = Field(ge=1, le=1)


class ActiveAttempt(Strict):
    job_id: str
    attempt_id: uuid.UUID
    lease_token: str


class Heartbeat(Strict):
    worker_id: str
    activity_state: str
    active_attempt: ActiveAttempt | None = None


class Claim(Strict):
    worker_id: str
    available_capacity: int = Field(ge=0, le=1)
    supported_model_versions: list[ModelCapability]


@lru_cache(maxsize=1)
def database_engine():
    return make_engine()


def get_db() -> Iterator[Session]:
    engine = database_engine()
    with Session(engine) as db:
        try:
            yield db
        finally:
            db.rollback()


def bearer(authorization: str | None):
    if not authorization or not authorization.startswith("Bearer ") or len(authorization) < 16:
        fail("UNAUTHENTICATED", 401)
    return authorization[7:]


def current_user(db: Session = Depends(get_db), authorization: str | None = Header(None)) -> User:
    token = bearer(authorization)
    lookup = hashlib.sha256(token.encode()).hexdigest()
    configured = json.loads(os.environ.get("EPILOCATE_V2_USER_TOKEN_HASHES", "{}"))
    subject = next((subject for subject, token_hash in configured.items() if hmac.compare_digest(lookup, token_hash)), None)
    if subject is None:
        fail("UNAUTHENTICATED", 401)
    user = db.scalar(select(User).where(User.auth_subject == subject, User.is_active.is_(True)))
    if not user:
        fail("UNAUTHENTICATED", 401)
    return user


def current_worker(db: Session = Depends(get_db), authorization: str | None = Header(None), x_request_id: str | None = Header(None)) -> WorkerNode:
    try:
        uuid.UUID(x_request_id or "")
    except ValueError:
        fail("INVALID_REQUEST_ID")
    token = bearer(authorization)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    worker = db.scalar(select(WorkerNode).where(WorkerNode.token_hash == token_hash))
    if not worker or not hmac.compare_digest(worker.token_hash, token_hash):
        fail("WORKER_UNAUTHENTICATED", 401)
    if worker.disabled_at:
        fail("WORKER_DISABLED", 403)
    return worker


def assert_worker_id(worker: WorkerNode, requested: str):
    if requested != worker.node_id:
        fail("WORKER_ID_MISMATCH", 403)


def encode_cursor(user_id: uuid.UUID, when, case_id: str) -> str:
    secret = os.environ.get("EPILOCATE_V2_LEASE_SECRET")
    if not secret:
        fail("CURSOR_SECRET_NOT_CONFIGURED", 503)
    payload = json.dumps([str(user_id), when.isoformat(), case_id], separators=(",", ":")).encode()
    signature = hmac.new(secret.encode(), payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(payload + signature).decode().rstrip("=")


def decode_cursor(user_id: uuid.UUID, value: str):
    secret = os.environ.get("EPILOCATE_V2_LEASE_SECRET")
    if not secret:
        fail("CURSOR_SECRET_NOT_CONFIGURED", 503)
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        payload, signature = raw[:-32], raw[-32:]
        if not hmac.compare_digest(signature, hmac.new(secret.encode(), payload, hashlib.sha256).digest()):
            fail("INVALID_CURSOR")
        actor, when, case_id = json.loads(payload)
        if actor != str(user_id):
            fail("INVALID_CURSOR")
        from datetime import datetime
        return datetime.fromisoformat(when), case_id
    except (ValueError, TypeError, IndexError, json.JSONDecodeError):
        fail("INVALID_CURSOR")


app = FastAPI(title="EpiLocate Backend v2", version="2.0")


@app.exception_handler(HTTPException)
async def http_error(_request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"code": "HTTP_ERROR", "message": "Request failed.", "retryable": False, "request_id": str(uuid.uuid4()), "details": {}})


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, _exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"code": "INVALID_REQUEST", "message": "Request does not match the v2 contract.", "retryable": False, "request_id": str(uuid.uuid4()), "details": {}})


@app.post("/api/v2/cases", status_code=201)
def create_case(body: CaseCreate, idempotency_key: str | None = Header(None), db: Session = Depends(get_db), user: User = Depends(current_user)):
    key = valid_key(idempotency_key)
    try:
        response = case_service.create_case(db, user.id, body.patient_id, key)
        db.commit()
    except IntegrityError:
        db.rollback()
        response = case_service.create_case(db, user.id, body.patient_id, key)
        db.commit()
    return response


@app.get("/api/v2/cases")
def list_cases(cursor: str | None = None, limit: int = 20, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not 1 <= limit <= 100:
        fail("INVALID_PAGINATION")
    query = select(Case).where(Case.owner_user_id == user.id, Case.status != "DELETING").order_by(Case.created_at.desc(), Case.anonymous_id.desc())
    if cursor:
        at, case_id = decode_cursor(user.id, cursor)
        from sqlalchemy import or_, and_
        query = query.where(or_(Case.created_at < at, and_(Case.created_at == at, Case.anonymous_id < case_id)))
    rows = db.scalars(query.limit(limit + 1)).all()
    visible = rows[:limit]
    next_cursor = encode_cursor(user.id, visible[-1].created_at, visible[-1].anonymous_id) if len(rows) > limit else None
    return {"items": [case_service.case_payload(db, x) for x in visible], "next_cursor": next_cursor}


@app.get("/api/v2/cases/{case_id}")
def case_detail(case_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return case_service.case_payload(db, case_service.get_case(db, user.id, case_id))


@app.get("/api/v2/cases/{case_id}/dicom")
def case_dicom(case_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Read the still-retained original DICOM for an owned Case."""
    case = case_service.get_case(db, user.id, case_id)
    sl = db.scalar(select(Slice).where(Slice.case_id == case.id).order_by(Slice.ordinal))
    if not sl or not sl.staging_object_key or not sl.staging_expires_at or aware(sl.staging_expires_at) <= now():
        fail("INPUT_EXPIRED", 410)
    data, media = ObjectStore().read(sl.staging_object_key)
    if media != "application/dicom" or not hmac.compare_digest(hashlib.sha256(data).hexdigest(), sl.source_sha256):
        fail("INPUT_INTEGRITY_FAILURE", 503)
    return Response(data, media_type="application/dicom", headers={"Cache-Control": "private,no-store", "X-Content-Type-Options": "nosniff"})


@app.post("/api/v2/cases/{case_id}/upload", status_code=201)
async def case_upload(case_id: str, input_kind: str = Form(...), file: UploadFile = File(...), idempotency_key: str | None = Header(None), db: Session = Depends(get_db), user: User = Depends(current_user)):
    if input_kind != "dicom_series":
        fail("UNSUPPORTED_INPUT_KIND", 415)
    raw = await file.read(20 * 1024 * 1024 + 1)
    response = case_service.upload_case(db, ObjectStore(), user.id, case_id, raw, valid_key(idempotency_key))
    db.commit()
    return response


def _create_job(body: JobCreate, kind: str, key: str | None, db: Session, user: User, protocol_id=None, scales=None):
    key = valid_key(key)
    try:
        job, _ = job_service.create_job(db, user.id, case_public_id=body.case_id, slice_public_id=body.slice_id, model_id=body.model_id, kind=kind, protocol_id=protocol_id, scales=scales, key=key)
        db.commit()
    except IntegrityError:
        db.rollback()
        job, _ = job_service.create_job(db, user.id, case_public_id=body.case_id, slice_public_id=body.slice_id, model_id=body.model_id, kind=kind, protocol_id=protocol_id, scales=scales, key=key)
        db.commit()
    response = {"job_id": job.public_id, "case_id": body.case_id, "status": "CREATED", "status_url": f"/api/v2/jobs/{job.public_id}"}
    if kind == "PREDICTION":
        response["prediction_id"] = job.public_id
    return response


@app.post("/api/v2/predictions", status_code=202)
def create_prediction(body: JobCreate, idempotency_key: str | None = Header(None), db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _create_job(body, "PREDICTION", idempotency_key, db, user)


@app.post("/api/v2/jobs/occlusion", status_code=202)
def create_occlusion(body: OcclusionCreate, idempotency_key: str | None = Header(None), db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _create_job(body, "OCCLUSION", idempotency_key, db, user, body.protocol_id, body.scales)


def _owned_job(db: Session, user: User, job_id: str):
    job = db.scalar(select(InferenceJob).where(InferenceJob.public_id == job_id, InferenceJob.requested_by_user_id == user.id))
    if not job:
        fail("JOB_NOT_FOUND", 404)
    return job


@app.get("/api/v2/jobs/{job_id}")
def job_detail(job_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return job_service.job_payload(db, _owned_job(db, user, job_id))


@app.get("/api/v2/predictions/{prediction_id}")
def prediction_detail(prediction_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    job = _owned_job(db, user, prediction_id)
    if job.kind != "PREDICTION":
        fail("PREDICTION_NOT_FOUND", 404)
    summary = job_service.job_payload(db, job)
    result = db.scalar(select(InferenceResult).where(InferenceResult.job_id == job.id)) if job.status == "COMPLETED" else None
    prediction = {**result.result_json["prediction"], "model_version": result.result_json["model_version"], "preprocessing_version": result.result_json["preprocessing_version"], "source": "LIVE_CASE"} if result else None
    return {"prediction_id": job.public_id, "job_id": job.public_id, "status": job.status, "result_id": summary["result_id"], "prediction": prediction, "error": summary["error"]}


def _owned_result(db: Session, user: User, result_id: str):
    try:
        internal_id = uuid.UUID(hex=result_id.removeprefix("result_")) if result_id.startswith("result_") else None
    except ValueError:
        internal_id = None
    result = db.get(InferenceResult, internal_id) if internal_id else None
    job = db.get(InferenceJob, result.job_id) if result else None
    if not result or not job or job.requested_by_user_id != user.id or job.status != "COMPLETED":
        fail("RESULT_NOT_FOUND", 404)
    return result, job


@app.get("/api/v2/results/{result_id}")
def result_detail(result_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    result, job = _owned_result(db, user, result_id)
    body = {k: v for k, v in result.result_json.items() if k != "positions"}
    sl = db.get(Slice, job.slice_id)
    asset_rows = db.scalars(select(Asset).where(Asset.result_id == result.id).order_by(Asset.asset_id)).all()
    store = ObjectStore() if asset_rows else None
    body.update({"result_id": result_id, "job_id": job.public_id, "status": "COMPLETED", "created_at": iso(result.created_at), "provenance": {"input_sha256": sl.source_sha256, "checkpoint_sha256": result.result_json["model_version"], "preprocessing_version": result.result_json["preprocessing_version"], "protocol_id": result.result_json["protocol_id"]}, "scale_summaries": result.result_json.get("scale_summaries", []), "cross_scale": result.result_json.get("cross_scale", []), "assets": [{"asset_id": x.asset_id, "layer_kind": x.layer_kind, "width": x.width, "height": x.height, "coordinate_space": x.coordinate_space, "media_type": x.media_type, "asset_url": store.signed_asset_get(x)} for x in asset_rows]})
    return body


@app.get("/api/v2/results/{result_id}/positions")
def result_positions(result_id: str, scale: int, cursor: int = 0, limit: int = 100, db: Session = Depends(get_db), user: User = Depends(current_user)):
    result, job = _owned_result(db, user, result_id)
    if job.kind != "OCCLUSION" or scale not in {16, 32, 64} or cursor < 0 or not 1 <= limit <= 1000:
        fail("INVALID_RESULT_QUERY")
    positions = [x for x in result.result_json.get("positions", []) if x.get("block_size") == scale]
    return {"result_id": result_id, "scale": scale, "positions": positions[cursor:cursor + limit], "next_cursor": str(cursor + limit) if cursor + limit < len(positions) else None}


@app.get("/api/v2/results/{result_id}/assets/{asset_id}")
def result_asset(result_id: str, asset_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    result, _ = _owned_result(db, user, result_id)
    asset = db.scalar(select(Asset).where(Asset.result_id == result.id, Asset.asset_id == asset_id))
    if not asset:
        fail("ASSET_NOT_FOUND", 404)
    data, media = ObjectStore().read(asset.object_key)
    if media != "image/png":
        fail("ASSET_TYPE_INVALID", 503)
    if len(data) != asset.size_bytes or not hmac.compare_digest(hashlib.sha256(data).hexdigest(), asset.sha256):
        fail("ASSET_INTEGRITY_FAILURE", 503)
    return Response(data, media_type="image/png", headers={"Cache-Control": "private,no-store", "X-Content-Type-Options": "nosniff"})


@app.post("/api/v2/workers/register")
def register(body: Register, db: Session = Depends(get_db), worker: WorkerNode = Depends(current_worker)):
    assert_worker_id(worker, body.worker_id)
    models = [x.model_dump() for x in body.supported_model_versions]
    if len(models) != len({(x["model_id"], x["checkpoint_sha256"]) for x in models}):
        fail("INVALID_WORKER_CAPABILITIES")
    worker.supported_models = models; worker.registered_at = worker.registered_at or now(); worker.updated_at = now()
    db.commit()
    return {"worker_id": worker.node_id, "registered": True, "heartbeat_interval_seconds": 15, "offline_after_seconds": 45, "lease_seconds": 90, "max_concurrent_jobs": 1, "server_time": iso(now())}


@app.post("/api/v2/workers/heartbeat")
def worker_heartbeat(body: Heartbeat, db: Session = Depends(get_db), worker: WorkerNode = Depends(current_worker)):
    assert_worker_id(worker, body.worker_id)
    if body.activity_state not in {"IDLE", "RUNNING", "ERROR"} or (body.activity_state == "RUNNING") != bool(body.active_attempt):
        fail("INVALID_HEARTBEAT")
    response = job_service.heartbeat(db, worker, body.activity_state, body.active_attempt.model_dump(mode="json") if body.active_attempt else None)
    db.commit()
    return response


@app.post("/api/v2/workers/jobs/claim")
def worker_claim(body: Claim, idempotency_key: str | None = Header(None), db: Session = Depends(get_db), worker: WorkerNode = Depends(current_worker)):
    assert_worker_id(worker, body.worker_id)
    try:
        key = uuid.UUID(idempotency_key or "")
    except ValueError:
        fail("INVALID_CLAIM")
    response = job_service.claim_job(db, worker, key, body.available_capacity, [x.model_dump() for x in body.supported_model_versions], ObjectStore().signed_get)
    db.commit()
    return response if response else Response(status_code=204)


async def _submit(manifest: str, assets: list[UploadFile] | None, db: Session, worker: WorkerNode, path_job_id: str | None = None):
    if len(manifest.encode()) > 64 * 1024 * 1024:
        fail("RESULT_TOO_LARGE", 413)
    try:
        data = json.loads(manifest)
    except (ValueError, TypeError):
        fail("RESULT_SCHEMA_INVALID")
    if not isinstance(data, dict) or (path_job_id is not None and data.get("job_id") != path_job_id):
        fail("RESULT_SCHEMA_INVALID")
    parts = {}
    total = len(manifest.encode())
    for part in assets or []:
        if not part.filename or part.filename in parts:
            fail("RESULT_SCHEMA_INVALID")
        content = await part.read(64 * 1024 * 1024 + 1)
        total += len(content)
        if total > 64 * 1024 * 1024:
            fail("RESULT_TOO_LARGE", 413)
        parts[part.filename] = content
    response = job_service.submit_result(db, ObjectStore(), worker, data, parts)
    db.commit()
    return response


@app.post("/api/v2/workers/results")
async def worker_result(manifest: str = Form(...), assets: list[UploadFile] | None = File(None, alias="assets[]"), db: Session = Depends(get_db), worker: WorkerNode = Depends(current_worker)):
    return await _submit(manifest, assets, db, worker)


@app.post("/api/v2/workers/jobs/{job_id}/result")
async def worker_result_by_job(job_id: str, manifest: str = Form(...), assets: list[UploadFile] | None = File(None, alias="assets[]"), db: Session = Depends(get_db), worker: WorkerNode = Depends(current_worker)):
    return await _submit(manifest, assets, db, worker, job_id)
