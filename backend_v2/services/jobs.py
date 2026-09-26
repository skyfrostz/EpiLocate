from __future__ import annotations

import hashlib
import hmac
import os
import re
import struct
import math
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend_v2.models.entities import Case, InferenceJob, InferenceResult, JobAttempt, ModelVersion, Slice, WorkerNode
from backend_v2.services.common import aware, digest, fail, iso, now, public_id, valid_key

LEASE_SECONDS = 90
OFFLINE_SECONDS = 45
RETRY_DELAYS = {1: 30, 2: 120}
RETRYABLE_FAILURES = {"INPUT_DOWNLOAD_FAILED", "TEMPORARY_GPU_UNAVAILABLE", "TEMPORARY_TRANSPORT_FAILURE", "LEASE_EXPIRED"}


def lease_token(attempt_id: uuid.UUID) -> str:
    secret = os.environ.get("EPILOCATE_V2_LEASE_SECRET")
    if not secret or len(secret) < 32:
        fail("LEASE_SECRET_NOT_CONFIGURED", 503)
    return hmac.new(secret.encode(), attempt_id.bytes, hashlib.sha256).hexdigest()


def model_for_request(db: Session, model_id: str) -> ModelVersion:
    models = db.scalars(select(ModelVersion).where(ModelVersion.model_id == model_id, ModelVersion.lifecycle_state == "ACTIVE")).all()
    if len(models) != 1:
        fail("MODEL_UNAVAILABLE", 422)
    return models[0]


def create_job(db: Session, user_id, *, case_public_id: str, slice_public_id: str, model_id: str, kind: str, protocol_id: str | None, scales: list[int] | None, key: str):
    valid_key(key)
    case = db.scalar(select(Case).where(Case.anonymous_id == case_public_id, Case.owner_user_id == user_id, Case.status != "DELETING"))
    if case is None:
        fail("CASE_NOT_FOUND", 404)
    sl = db.scalar(select(Slice).where(Slice.slice_ref == slice_public_id, Slice.case_id == case.id))
    if sl is None:
        fail("SLICE_NOT_FOUND", 404)
    if not sl.staging_object_key or not sl.staging_expires_at or aware(sl.staging_expires_at) <= now():
        fail("INPUT_EXPIRED", 410)
    model = model_for_request(db, model_id)
    if kind == "OCCLUSION" and (protocol_id != model.protocol_id or not scales or len(scales) != len(set(scales)) or not set(scales).issubset({16, 32, 64})):
        fail("INVALID_OCCLUSION_PARAMETERS")
    params = {"kind": kind, "case_id": case_public_id, "slice_id": slice_public_id, "model_id": model_id, "protocol_id": protocol_id or model.protocol_id, "scales": scales or []}
    request_digest = digest({**params, "checkpoint_sha256": model.checkpoint_sha256, "preprocessing_version": model.preprocessing_version, "input_sha256": sl.source_sha256})
    old = db.scalar(select(InferenceJob).where(InferenceJob.requested_by_user_id == user_id, InferenceJob.idempotency_key == key))
    if old:
        if old.request_digest != request_digest:
            fail("IDEMPOTENCY_CONFLICT", 409)
        return old, False
    job = InferenceJob(public_id=public_id("job"), case_id=case.id, slice_id=sl.id, requested_by_user_id=user_id, model_version_id=model.id, kind=kind, status="CREATED", request_json=params, request_digest=request_digest, idempotency_key=key)
    db.add(job)
    db.flush()
    return job, True


def queue_job(db: Session, job: InferenceJob):
    if job.status != "CREATED":
        fail("INVALID_JOB_TRANSITION", 409)
    job.status = "QUEUED"
    job.queued_at = now()
    job.next_attempt_at = now()
    job.updated_at = now()
    db.flush()


def queue_created(db: Session):
    """Validator pass. Called before matching claims and by the periodic sweeper."""
    jobs = db.scalars(select(InferenceJob).where(InferenceJob.status == "CREATED").with_for_update(skip_locked=True)).all()
    for job in jobs:
        sl = db.get(Slice, job.slice_id)
        model = db.get(ModelVersion, job.model_version_id)
        if not sl or not sl.staging_object_key or not sl.staging_expires_at or aware(sl.staging_expires_at) <= now():
            job.status = "FAILED"; job.failure_reason = "INPUT_EXPIRED"; job.error_message = "Input expired."; job.finished_at = now()
        elif not model or model.lifecycle_state != "ACTIVE":
            job.status = "FAILED"; job.failure_reason = "MODEL_UNAVAILABLE"; job.error_message = "Model unavailable."; job.finished_at = now()
        else:
            queue_job(db, job)
    return len(jobs)


def job_payload(db: Session, job: InferenceJob):
    result = db.scalar(select(InferenceResult).where(InferenceResult.job_id == job.id)) if job.status == "COMPLETED" else None
    return {"job_id": job.public_id, "kind": job.kind, "case_id": job.request_json["case_id"], "status": job.status, "attempt_no": job.attempt_no, "retry_count": job.retry_count, "lease_expire_time": iso(job.lease_expire_time), "last_heartbeat": iso(job.last_heartbeat), "failure_reason": job.failure_reason, "progress": None, "estimated_remaining_time_ms": None, "result_id": f"result_{result.id.hex}" if result else None, "error": {"code": job.failure_reason, "message": job.error_message or "Job failed."} if job.status == "FAILED" else None, "created_at": iso(job.created_at), "finished_at": iso(job.finished_at)}


def current_attempt(db: Session, worker: WorkerNode, attempt_id: uuid.UUID, job_public_id: str, token: str):
    job = db.scalar(select(InferenceJob).where(InferenceJob.public_id == job_public_id).with_for_update())
    attempt = db.get(JobAttempt, attempt_id)
    if not job or not attempt or attempt.job_id != job.id or attempt.worker_node_id != worker.id:
        fail("STALE_ATTEMPT", 409)
    expected = hashlib.sha256(lease_token(attempt.id).encode()).hexdigest()
    if not hmac.compare_digest(expected, attempt.lease_token_hash) or not hmac.compare_digest(lease_token(attempt.id), token):
        fail("STALE_ATTEMPT", 409)
    return job, attempt


def expire_and_retry(db: Session, job: InferenceJob, attempt: JobAttempt, code: str, *, at=None):
    at = at or now()
    if job.status != "RUNNING" or attempt.outcome != "CLAIMED":
        fail("INVALID_JOB_TRANSITION", 409)
    attempt.outcome = "EXPIRED" if code == "LEASE_EXPIRED" else "FAILED"
    attempt.failure_reason = code
    attempt.finished_at = at
    job.worker_node_id = None
    job.lease_expire_time = None
    job.last_heartbeat = None
    job.updated_at = at
    sl = db.get(Slice, job.slice_id)
    input_available = bool(sl and sl.staging_object_key and sl.staging_expires_at and aware(sl.staging_expires_at) > at)
    if code in RETRYABLE_FAILURES and job.retry_count < 2 and input_available:
        job.status = "QUEUED"
        job.next_attempt_at = at + timedelta(seconds=RETRY_DELAYS[job.attempt_no])
        job.queued_at = at
    else:
        job.status = "FAILED"
        job.failure_reason = "INPUT_EXPIRED" if not input_available else code
        job.error_message = "Input expired." if not input_available else "Job failed."
        job.finished_at = at


def recover_expired(db: Session, *, at=None):
    at = at or now()
    jobs = db.scalars(select(InferenceJob).where(InferenceJob.status == "RUNNING", InferenceJob.lease_expire_time <= at).with_for_update(skip_locked=True)).all()
    for job in jobs:
        attempt = db.scalar(select(JobAttempt).where(JobAttempt.job_id == job.id, JobAttempt.outcome == "CLAIMED"))
        if attempt:
            expire_and_retry(db, job, attempt, "LEASE_EXPIRED", at=at)
    return len(jobs)


def claim_job(db: Session, worker: WorkerNode, key: uuid.UUID, capacity: int, supported: list[dict], input_url):
    db.refresh(worker, with_for_update=True)
    normalized = sorted(supported, key=lambda x: (x["model_id"], x["checkpoint_sha256"]))
    request_digest = digest({"worker_id": worker.node_id, "supported_model_versions": normalized})
    old = db.scalar(select(JobAttempt).where(JobAttempt.worker_node_id == worker.id, JobAttempt.claim_key == key))
    if old:
        if old.claim_request_digest != request_digest:
            fail("CLAIM_KEY_CONFLICT", 409)
        if old.outcome != "CLAIMED" or aware(old.lease_expire_time) <= now():
            fail("CLAIM_ALREADY_FINISHED", 409)
        job = db.get(InferenceJob, old.job_id)
        return _claim_payload(db, job, old, input_url)
    if capacity == 0:
        return None
    if worker.disabled_at or not worker.registered_at or not worker.last_heartbeat_at or aware(worker.last_heartbeat_at) <= now() - timedelta(seconds=OFFLINE_SECONDS):
        fail("WORKER_OFFLINE", 409)
    if db.scalar(select(JobAttempt).where(JobAttempt.worker_node_id == worker.id, JobAttempt.outcome == "CLAIMED")):
        fail("WORKER_BUSY", 409)
    queue_created(db)
    registered = {(x["model_id"], x["checkpoint_sha256"]) for x in worker.supported_models}
    offered = {(x["model_id"], x["checkpoint_sha256"]) for x in normalized} & registered
    candidates = db.scalars(select(InferenceJob).where(InferenceJob.status == "QUEUED", InferenceJob.next_attempt_at <= now()).order_by(InferenceJob.created_at, InferenceJob.id).with_for_update(skip_locked=True)).all()
    for job in candidates:
        model = db.get(ModelVersion, job.model_version_id)
        sl = db.get(Slice, job.slice_id)
        if not sl or not sl.staging_object_key or not sl.staging_expires_at or aware(sl.staging_expires_at) <= now():
            job.status = "FAILED"; job.failure_reason = "INPUT_EXPIRED"; job.error_message = "Input expired."; job.finished_at = now()
            continue
        if model.lifecycle_state != "ACTIVE" or (model.model_id, model.checkpoint_sha256) not in offered:
            continue
        if job.attempt_no >= job.max_attempts:
            job.status = "FAILED"; job.failure_reason = "RETRY_EXHAUSTED"; job.error_message = "Job failed."; job.finished_at = now()
            continue
        at = now()
        attempt = JobAttempt(job_id=job.id, attempt_no=job.attempt_no + 1, worker_node_id=worker.id, claim_key=key, claim_request_digest=request_digest, lease_token_hash="", lease_expire_time=at + timedelta(seconds=LEASE_SECONDS))
        db.add(attempt); db.flush()
        attempt.lease_token_hash = hashlib.sha256(lease_token(attempt.id).encode()).hexdigest()
        job.status = "RUNNING"; job.attempt_no = attempt.attempt_no; job.retry_count = attempt.attempt_no - 1
        job.worker_node_id = worker.id; job.lease_expire_time = attempt.lease_expire_time; job.last_heartbeat = None; job.started_at = job.started_at or at; job.updated_at = at
        worker.activity_state = "RUNNING"
        db.flush()
        return _claim_payload(db, job, attempt, input_url)
    return None


def _claim_payload(db, job, attempt, input_url):
    sl = db.get(Slice, job.slice_id)
    model = db.get(ModelVersion, job.model_version_id)
    return {"job_id": job.public_id, "case_id": job.request_json["case_id"], "input_reference": {"url": input_url(sl), "sha256": sl.source_sha256, "expires_at": iso(min(aware(sl.staging_expires_at), now() + timedelta(minutes=5)))}, "model_version": {"model_id": model.model_id, "checkpoint_sha256": model.checkpoint_sha256, "preprocessing_version": model.preprocessing_version, "protocol_id": model.protocol_id}, "lease_expire_time": iso(attempt.lease_expire_time), "job_parameters": {"kind": job.kind, "slice_id": job.request_json["slice_id"], "scales": job.request_json["scales"]}, "attempt_id": str(attempt.id), "attempt_no": attempt.attempt_no, "lease_token": lease_token(attempt.id)}


def _probability(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1


def _layer(value):
    if value is None:
        return True
    fields = {"asset_id", "layer_kind", "width", "height", "coordinate_space", "value_min", "value_max", "origin", "x_axis", "y_axis", "display_interpolation_only"}
    return isinstance(value, dict) and set(value) == fields and isinstance(value["asset_id"], str) and value["layer_kind"] in {"CANDIDATE_RESPONSE", "CANDIDATE_TOP10", "COMPARISON_GRID"} and type(value["width"]) is int and type(value["height"]) is int and value["width"] > 0 and value["height"] > 0 and value["coordinate_space"] in {"ALGORITHM_224", "COMPARISON_14", "RAW_PIXEL_EDGE"} and value["origin"] == "TOP_LEFT_PIXEL_EDGE" and value["x_axis"] == "RIGHT" and value["y_axis"] == "DOWN" and type(value["display_interpolation_only"]) is bool and type(value["value_min"]) in (int, float) and type(value["value_max"]) in (int, float) and math.isfinite(value["value_min"]) and math.isfinite(value["value_max"])


def _validate_occlusion(result, scales):
    summaries = result.get("scale_summaries")
    positions = result.get("positions")
    cross = result.get("cross_scale")
    if not isinstance(summaries, list) or not isinstance(positions, list) or not isinstance(cross, list) or len(summaries) != len(scales):
        fail("RESULT_SCHEMA_INVALID")
    required_summary = {"block_size", "stride", "fill", "baseline_positive_probability", "median_absolute_probability_change", "flip_rate", "candidate_status", "candidate_area_fraction", "response_layer", "candidate_layer", "comparison_grid_layer"}
    seen = set()
    for summary in summaries:
        if not isinstance(summary, dict) or set(summary) != required_summary:
            fail("RESULT_SCHEMA_INVALID")
        scale = summary["block_size"]
        if scale not in scales or scale in seen or summary["stride"] != scale // 2 or summary["fill"] != 0.5:
            fail("RESULT_SCHEMA_INVALID")
        seen.add(scale)
        if not all(_probability(summary[k]) for k in ("baseline_positive_probability", "median_absolute_probability_change", "flip_rate")):
            fail("RESULT_SCHEMA_INVALID")
        if summary["candidate_status"] not in {"valid", "insufficient_positive_response"} or (summary["candidate_area_fraction"] is not None and not _probability(summary["candidate_area_fraction"])):
            fail("RESULT_SCHEMA_INVALID")
        if any(not _layer(summary[k]) for k in ("response_layer", "candidate_layer", "comparison_grid_layer")):
            fail("RESULT_SCHEMA_INVALID")
        if summary["candidate_status"] == "insufficient_positive_response" and (summary["candidate_layer"] is not None or summary["candidate_area_fraction"] is not None):
            fail("RESULT_SCHEMA_INVALID")
    required_position = {"x", "y", "block_size", "baseline_positive_probability", "masked_positive_probability", "prediction_flip", "decision_confidence_drop", "candidate_response"}
    for position in positions:
        if not isinstance(position, dict) or set(position) != required_position or position["block_size"] not in scales or type(position["x"]) is not int or type(position["y"]) is not int or not 0 <= position["x"] <= 223 or not 0 <= position["y"] <= 223 or type(position["prediction_flip"]) is not bool:
            fail("RESULT_SCHEMA_INVALID")
        if not all(_probability(position[k]) for k in ("baseline_positive_probability", "masked_positive_probability", "candidate_response")) or type(position["decision_confidence_drop"]) not in (int, float) or not math.isfinite(position["decision_confidence_drop"]) or not -1 <= position["decision_confidence_drop"] <= 1:
            fail("RESULT_SCHEMA_INVALID")
    cross_fields = {"scale_a", "scale_b", "spearman", "top10_iou", "dice", "normalized_center_distance", "normalized_l1", "pearson"}
    for item in cross:
        if not isinstance(item, dict) or set(item) != cross_fields or item["scale_a"] not in scales or item["scale_b"] not in scales or item["scale_a"] >= item["scale_b"]:
            fail("RESULT_SCHEMA_INVALID")
        for name in ("spearman", "top10_iou", "dice", "normalized_center_distance", "normalized_l1", "pearson"):
            value = item[name]
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or (name in {"spearman", "pearson"} and not -1 <= value <= 1) or (name in {"top10_iou", "dice", "normalized_center_distance"} and not 0 <= value <= 1) or (name == "normalized_l1" and value < 0)):
                fail("RESULT_SCHEMA_INVALID")


def heartbeat(db: Session, worker: WorkerNode, activity: str, active: dict | None):
    at = now()
    if not worker.registered_at:
        fail("WORKER_NOT_REGISTERED", 403)
    worker.last_heartbeat_at = at
    worker.activity_state = activity
    expire = None
    if active:
        job, attempt = current_attempt(db, worker, uuid.UUID(active["attempt_id"]), active["job_id"], active["lease_token"])
        if job.status != "RUNNING" or attempt.outcome != "CLAIMED" or aware(attempt.lease_expire_time) <= at:
            fail("STALE_ATTEMPT", 409)
        expire = at + timedelta(seconds=LEASE_SECONDS)
        job.lease_expire_time = expire; job.last_heartbeat = at; job.updated_at = at
        attempt.lease_expire_time = expire; attempt.last_heartbeat = at
    return {"worker_id": worker.node_id, "connectivity": "ONLINE", "activity_state": activity, "lease_expire_time": iso(expire), "server_time": iso(at), "drain": False}


def submit_result(db: Session, store, worker: WorkerNode, manifest: dict, assets: dict[str, bytes]):
    required = {"worker_id", "job_id", "attempt_id", "lease_token", "outcome", "model_id", "checkpoint_sha256", "input_sha256", "result", "assets"}
    if not required.issubset(manifest) or manifest["worker_id"] != worker.node_id or manifest["outcome"] not in {"SUCCEEDED", "FAILED"}:
        fail("RESULT_SCHEMA_INVALID")
    try:
        attempt_id = uuid.UUID(manifest["attempt_id"])
    except (ValueError, TypeError):
        fail("RESULT_SCHEMA_INVALID")
    job, attempt = current_attempt(db, worker, attempt_id, manifest["job_id"], manifest["lease_token"])
    submission_digest = digest({"manifest": {k: v for k, v in manifest.items() if k != "lease_token"}, "assets": {k: hashlib.sha256(v).hexdigest() for k, v in sorted(assets.items())}})
    if attempt.submission_digest is not None:
        if attempt.submission_digest != submission_digest:
            fail("RESULT_CONFLICT", 409)
        return attempt.accepted_response_json
    if job.status != "RUNNING" or attempt.outcome != "CLAIMED" or aware(attempt.lease_expire_time) <= now():
        fail("STALE_ATTEMPT", 409)
    model = db.get(ModelVersion, job.model_version_id)
    sl = db.get(Slice, job.slice_id)
    if manifest["model_id"] != model.model_id or manifest["checkpoint_sha256"] != model.checkpoint_sha256:
        fail("MODEL_HASH_MISMATCH")
    if manifest["input_sha256"] != sl.source_sha256:
        fail("INPUT_HASH_MISMATCH")
    at = now()
    result_id = None
    if manifest["outcome"] == "SUCCEEDED":
        result = manifest["result"]
        permitted_keys = {"contract_version", "source", "case_id", "slice_id", "kind", "model_id", "model_version", "preprocessing_version", "protocol_id", "prediction", "scale_summaries", "cross_scale", "positions"}
        if not isinstance(result, dict) or set(result) - permitted_keys:
            fail("RESULT_SCHEMA_INVALID")
        if not isinstance(result, dict) or any(result.get(k) != v for k, v in {"contract_version": "2.0", "source": "LIVE_CASE", "case_id": job.request_json["case_id"], "slice_id": job.request_json["slice_id"], "kind": job.kind, "model_id": model.model_id, "model_version": model.checkpoint_sha256, "preprocessing_version": model.preprocessing_version, "protocol_id": model.protocol_id}.items()):
            fail("RESULT_SCHEMA_INVALID")
        prediction = result.get("prediction")
        if not isinstance(prediction, dict) or set(prediction) != {"predicted_class", "class_label", "positive_probability", "predicted_class_confidence", "inference_time_ms"}:
            fail("RESULT_SCHEMA_INVALID")
        if prediction["predicted_class"] not in (0, 1) or prediction["class_label"] not in {"negative", "positive"} or not all(isinstance(prediction[k], (float, int)) and 0 <= prediction[k] <= 1 for k in ("positive_probability", "predicted_class_confidence")) or not isinstance(prediction["inference_time_ms"], int) or prediction["inference_time_ms"] < 0:
            fail("RESULT_SCHEMA_INVALID")
        if (prediction["predicted_class"] == 1) != (prediction["class_label"] == "positive"):
            fail("RESULT_SCHEMA_INVALID")
        if job.kind == "OCCLUSION":
            _validate_occlusion(result, job.request_json["scales"])
        elif result.get("scale_summaries", []) or result.get("cross_scale", []) or result.get("positions", []):
            fail("RESULT_SCHEMA_INVALID")
        descriptors = manifest["assets"]
        if not isinstance(descriptors, list) or any(not isinstance(x, dict) for x in descriptors) or {x.get("part_name") for x in descriptors} != set(assets) or len(descriptors) != len(assets):
            fail("RESULT_SCHEMA_INVALID")
        stored = []
        try:
            layer_refs = {}
            for summary in result.get("scale_summaries", []):
                for field in ("response_layer", "candidate_layer", "comparison_grid_layer"):
                    layer = summary.get(field)
                    if isinstance(layer, dict) and layer.get("asset_id"):
                        layer_refs[layer["asset_id"]] = layer
            if set(layer_refs) != {x.get("asset_id") for x in descriptors}:
                fail("RESULT_SCHEMA_INVALID")
            for x in descriptors:
                data = assets[x["part_name"]]
                if set(x) != {"asset_id", "part_name", "layer_kind", "media_type", "size_bytes", "sha256"} or x.get("media_type") != "image/png" or x.get("size_bytes") != len(data) or x.get("sha256") != hashlib.sha256(data).hexdigest() or len(data) < 24 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
                    fail("ASSET_HASH_MISMATCH")
                layer = layer_refs.get(x["asset_id"])
                if not layer or layer.get("layer_kind") != x["layer_kind"] or layer.get("coordinate_space") not in {"ALGORITHM_224", "COMPARISON_14", "RAW_PIXEL_EDGE"} or not isinstance(layer.get("width"), int) or not isinstance(layer.get("height"), int) or layer["width"] <= 0 or layer["height"] <= 0:
                    fail("RESULT_SCHEMA_INVALID")
                if struct.unpack(">II", data[16:24]) != (layer["width"], layer["height"]):
                    fail("RESULT_SCHEMA_INVALID")
                key = store.put(data, "image/png", "results")
                stored.append({**x, "width": layer["width"], "height": layer["height"], "coordinate_space": layer["coordinate_space"], "object_key": key})
            row = InferenceResult(job_id=job.id, case_id=job.case_id, accepted_attempt_id=attempt.id, model_version_id=model.id, result_json=result, asset_manifest=stored)
            db.add(row); db.flush()
            result_id = f"result_{row.id.hex}"
            job.status = "COMPLETED"; job.finished_at = at; job.worker_node_id = None; job.lease_expire_time = None; job.last_heartbeat = None
            attempt.outcome = "SUCCEEDED"; attempt.finished_at = at
        except Exception:
            for x in stored:
                store.delete(x["object_key"])
            raise
    else:
        if manifest["result"] is not None or manifest["assets"] or assets or not isinstance(manifest.get("error"), dict):
            fail("RESULT_SCHEMA_INVALID")
        code = manifest["error"].get("code")
        if not isinstance(code, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", code):
            fail("RESULT_SCHEMA_INVALID")
        expire_and_retry(db, job, attempt, code, at=at)
    worker.activity_state = "IDLE"
    response = {"job_id": job.public_id, "attempt_id": str(attempt.id), "accepted": True, "job_status": job.status, "result_id": result_id, "server_time": iso(at)}
    attempt.submission_digest = submission_digest
    attempt.accepted_response_json = response
    return response
