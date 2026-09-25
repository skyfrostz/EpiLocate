from __future__ import annotations

import logging
import os
import io
import json
import uuid
import hashlib
from datetime import UTC, datetime
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Keep Gradio's transient copies inside the project so the user home can remain blocked.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(os.getenv("APP_DATA_ROOT", PROJECT_ROOT)).resolve()
os.environ.setdefault("GRADIO_TEMP_DIR", str(DATA_ROOT / "storage" / "temp"))

import gradio as gr
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Header
from fastapi.responses import RedirectResponse, FileResponse, Response, JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from PIL import Image

from algorithm.service import FrozenBaseline, validate_dicom, MODEL_ID, PROTOCOL_ID

from .contracts import InferenceResult, JobStatus
from .inference import InferenceAdapter
from .jobs import JobManager, QueueFullError
from .storage import InputError, Storage
from .ui import build_ui


def configure_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    for logger_name, filename, level in (
        ("app", "app.log", logging.INFO),
        ("inference", "inference.log", logging.INFO),
        ("errors", "error.log", logging.ERROR),
    ):
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)
        if not logger.handlers:
            handler = RotatingFileHandler(log_dir / filename, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
            handler.setFormatter(formatter)
            logger.addHandler(handler)


storage = Storage()
configure_logging(storage.logs)
adapter = InferenceAdapter(storage)
baseline = FrozenBaseline()
jobs = JobManager(storage, adapter, baseline=baseline)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logging.getLogger("app").info("service_started mode=%s", adapter.mode)
    yield
    jobs.close()
    logging.getLogger("app").info("service_stopped")


api = FastAPI(
    title="Infectious Imaging Gradio Debug API",
    version="0.1.0",
    lifespan=lifespan,
)


@api.exception_handler(HTTPException)
async def api_http_error(_request, exc: HTTPException):
    if isinstance(exc.detail, dict) and "request_id" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@api.exception_handler(RequestValidationError)
async def api_validation_error(request, _exc: RequestValidationError):
    if request.url.path.startswith("/api/v1/") and request.url.path != "/api/v1/jobs/inference":
        return JSONResponse(status_code=422, content={"code": "INVALID_REQUEST",
            "message": "Request does not match the P0 contract.", "retryable": False,
            "request_id": uuid.uuid4().hex, "details": {}})
    return JSONResponse(status_code=422, content={"detail": "Invalid request."})


@api.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/gradio")


@api.get("/api/health")
def health():
    real_ready = baseline.ready()
    healthy = adapter.mode == "mock" or real_ready
    return {
        "status": "ok" if healthy else "degraded",
        "mode": adapter.mode,
        "contract_version": "0.1",
        "real_ready": real_ready,
    }


@api.get("/api/v1/capabilities")
def capabilities():
    ready = baseline.ready()
    def item(state, evidence, source=None):
        return {"state": state, "evidence": evidence, "result_source": source}
    return {"contract_version": "1.0", "service_mode": "REAL" if ready else "MOCK",
            "capabilities": {
                "mock_prediction": item("available" if adapter.mode == "mock" else "unavailable", "PNG/JPG mock v0.1; result source=MOCK"),
                "baseline_slice_prediction": item("available" if ready else "unavailable", "frozen checkpoint SHA-256 and epoch verified" if ready else "frozen checkpoint unavailable", "LIVE_CASE" if ready else None),
                "single_slice_occlusion": item("available" if ready else "unavailable", "frozen Stage 1 functions and checkpoint verified" if ready else "frozen checkpoint unavailable", "LIVE_CASE" if ready else None),
                **{name: item("planned", "not connected") for name in ("nifti", "robust", "coarse_localization", "lime", "doctor_feedback")},
            }}


def error(code: str, message: str, status: int):
    raise HTTPException(status_code=status, detail={"code": code, "message": message,
                                                    "retryable": status >= 500,
                                                    "request_id": uuid.uuid4().hex, "details": {}})


def check_idempotency(key: str | None, digest: str):
    if key is None or not 8 <= len(key) <= 128:
        error("INVALID_REQUEST", "Idempotency-Key must contain 8–128 characters.", 422)
    try:
        return storage.idempotent_response(key, digest)
    except InputError:
        error("IDEMPOTENCY_CONFLICT", "Idempotency key was used for another request.", 409)


def public_case(record):
    return {"case_id": record["case_id"], "preprocessing_status": "COMPLETED",
            "quality_checks": [{"code": "CT_SINGLE_SLICE_DEIDENTIFIED", "status": "PASS", "message": None}],
            "slice_count": 1, "source": "LIVE_CASE"}


def public_slice(record):
    width, height = record["raw_width"], record["raw_height"]
    return {"case_id": record["case_id"], "slice_id": record["slice_id"], "index": 0,
            "preview_asset_id": record["slice_id"], "preprocessing_status": "COMPLETED",
            "geometry": {"raw_width": width, "raw_height": height,
                         "algorithm_width": 224, "algorithm_height": 224,
                         "coordinate_origin": "TOP_LEFT_PIXEL_EDGE", "x_axis": "RIGHT", "y_axis": "DOWN",
                         "raw_to_algorithm_edge_affine": [224 / width, 0, 0, 0, 224 / height, 0, 0, 0, 1],
                         "pixel_spacing_mm": None, "image_orientation_patient": None,
                         "image_position_patient": None, "window_center": -600,
                         "window_width": 1500}}


@api.post("/api/v1/cases", status_code=202)
async def create_case(files: list[UploadFile] = File(...), input_kind: str = Form(...),
                      idempotency_key: str | None = Header(None)):
    if input_kind != "dicom_series" or len(files) != 1:
        error("UNSUPPORTED_FORMAT", "P0 accepts one de-identified CT DICOM slice.", 415)
    if not baseline.ready():
        error("MODEL_UNAVAILABLE", "Frozen baseline is unavailable.", 503)
    try:
        data = await read_limited(files[0])
    except HTTPException:
        error("INVALID_REQUEST", "DICOM exceeds the upload limit.", 413)
    digest = hashlib.sha256(b"case:dicom_series:" + data).hexdigest()
    existing = check_idempotency(idempotency_key, digest)
    if existing is not None:
        return existing
    try:
        rows, columns = validate_dicom(data, storage.max_image_pixels)
    except ValueError:
        error("IMAGE_PARSE_FAILED", "Invalid or identifiable CT DICOM slice.", 422)
    case_id, slice_id, job_id = "CASE-" + uuid.uuid4().hex[:16], "SLICE-" + uuid.uuid4().hex[:16], str(uuid.uuid4())
    storage.save_dicom_bytes(data, case_id, slice_id, rows, columns, datetime.now(UTC).isoformat())
    try:
        baseline.stages(storage.absolute_input_path(storage.get_case(case_id=case_id)["input_path"]))
    except Exception:
        # Reject unsupported pixel encodings before exposing a ready case.
        storage.delete_case(case_id)
        error("PREPROCESSING_FAILED", "CT pixel preprocessing failed.", 422)
    from .jobs import utc_now
    job = JobStatus(job_id=job_id, case_id=case_id, status="success", stage="complete",
                    progress=100, created_at=utc_now(), finished_at=utc_now())
    storage.create_job(job)
    storage.mark_analysis_job(job_id, "CASE_PARSE")
    response = {"case_id": case_id, "job_id": job_id, "status": "PENDING"}
    storage.store_idempotent_response(idempotency_key, digest, response)
    return response


@api.get("/api/v1/cases/{case_id}")
def get_case(case_id: str):
    record = storage.get_case(case_id=case_id)
    if record is None:
        error("RESULT_NOT_FOUND", "Case not found.", 404)
    return public_case(record)


@api.get("/api/v1/cases/{case_id}/slices")
def get_slices(case_id: str):
    record = storage.get_case(case_id=case_id)
    if record is None:
        error("RESULT_NOT_FOUND", "Case not found.", 404)
    return {"case_id": case_id, "slices": [public_slice(record)]}


@api.get("/api/v1/slices/{slice_id}/preview")
def preview(slice_id: str):
    record = storage.get_case(slice_id=slice_id)
    if record is None:
        error("RESULT_NOT_FOUND", "Slice not found.", 404)
    stages = baseline.stages(storage.absolute_input_path(record["input_path"]))
    image = Image.fromarray((stages.normalized * 255).round().astype("uint8"))
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return Response(stream.getvalue(), media_type="image/png")


class PredictionRequest(BaseModel):
    case_id: str
    slice_id: str
    unit: str
    model_id: str


class OcclusionRequest(BaseModel):
    case_id: str
    slice_id: str
    model_id: str
    scales: list[int]
    protocol_id: str


def submit_v1(request, kind: str, scales=None, idempotency_key=None):
    digest = hashlib.sha256((kind + ":" + json.dumps(request.model_dump(), sort_keys=True)).encode()).hexdigest()
    existing = check_idempotency(idempotency_key, digest)
    if existing is not None:
        return existing
    record = storage.get_case(case_id=request.case_id)
    if record is None or record["slice_id"] != request.slice_id:
        error("RESULT_NOT_FOUND", "Case or slice not found.", 404)
    if request.model_id != MODEL_ID or (kind == "prediction" and request.unit != "slice"):
        error("INVALID_REQUEST", "Only Baseline single-slice analysis is supported.", 422)
    if kind == "occlusion" and (request.protocol_id != PROTOCOL_ID or not scales or len(set(scales)) != len(scales) or any(scale not in (16, 32, 64) for scale in scales)):
        error("INVALID_REQUEST", "Invalid Stage 1 occlusion settings.", 422)
    if not baseline.ready():
        error("MODEL_UNAVAILABLE", "Frozen baseline is unavailable.", 503)
    try:
        job = jobs.submit_analysis(request.case_id, request.slice_id, kind, scales)
    except QueueFullError:
        error("INVALID_REQUEST", "Analysis queue is full.", 429)
    response = {"job_id": job.job_id, "case_id": job.case_id, "status": "PENDING",
                "status_url": f"/api/v1/jobs/{job.job_id}"}
    storage.store_idempotent_response(idempotency_key, digest, response)
    return response


@api.post("/api/v1/predictions", status_code=202)
def create_prediction(request: PredictionRequest, idempotency_key: str | None = Header(None)):
    return submit_v1(request, "prediction", idempotency_key=idempotency_key)


@api.post("/api/v1/jobs/occlusion", status_code=202)
def create_occlusion(request: OcclusionRequest, idempotency_key: str | None = Header(None)):
    return submit_v1(request, "occlusion", request.scales, idempotency_key)


@api.get("/api/v1/occlusion-results/{result_id}/positions")
def get_positions(result_id: str, scale: int, cursor: int = 0, limit: int = 100):
    result = storage.get_analysis_result(result_id)
    if result is None or "positions" not in result:
        error("RESULT_NOT_FOUND", "Occlusion result not found.", 404)
    if scale not in (16, 32, 64) or cursor < 0 or not 1 <= limit <= 1000:
        error("INVALID_REQUEST", "Invalid position page.", 422)
    positions = result["positions"].get(str(scale), [])
    return {"result_id": result_id, "scale": scale,
            "positions": positions[cursor:cursor + limit],
            "next_cursor": cursor + limit if cursor + limit < len(positions) else None}


@api.get("/api/v1/assets/{asset_id}")
def get_asset(asset_id: str, result_id: str):
    result = storage.get_analysis_result(result_id)
    if result is None or "positions" not in result or asset_id not in {
        layer["asset_id"] for summary in result["scale_summaries"]
        for key in ("response_layer", "candidate_layer", "comparison_grid_layer")
        if (layer := summary.get(key)) is not None
    }:
        error("RESULT_NOT_FOUND", "Asset not found.", 404)
    path = (storage.results / result["case_id"] / result_id / asset_id).resolve()
    if storage.results not in path.parents or not path.is_file():
        error("RESULT_NOT_FOUND", "Asset not found.", 404)
    return FileResponse(path)


@api.post("/api/v1/comparisons")
@api.post("/api/v1/jobs/coarse-localization")
@api.post("/api/v1/jobs/lime")
@api.post("/api/v1/feedback")
def reserved_future_endpoint():
    error("NOT_IMPLEMENTED", "This research module is reserved.", 501)


@api.post("/api/v1/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    error("NOT_IMPLEMENTED", "P0 jobs cannot be cancelled safely.", 501)


@api.get("/api/v1/contract")
def contract():
    return {
        "contract_version": "0.1",
        "schema": InferenceResult.model_json_schema(by_alias=True),
    }


async def read_limited(upload: UploadFile) -> bytes:
    total = bytearray()
    while chunk := await upload.read(64 * 1024):
        total.extend(chunk)
        if len(total) > storage.max_upload_bytes:
            raise HTTPException(status_code=413, detail={"code": "FILE_TOO_LARGE", "message": "Upload exceeds limit."})
    return bytes(total)


@api.post("/api/v1/jobs/inference", status_code=202)
async def create_inference_job(
    files: list[UploadFile] = File(...),
    input_kind: str = Form("image"),
):
    if adapter.mode == "real" and not adapter.real_ready:
        raise HTTPException(
            status_code=503,
            detail={"code": "REAL_PIPELINE_UNAVAILABLE", "message": "Real inference pipeline is not available."},
        )
    if input_kind != "image":
        raise HTTPException(status_code=422, detail={"code": "INPUT_KIND_NOT_SUPPORTED", "message": "P0 accepts image input only."})
    if len(files) != 1:
        raise HTTPException(status_code=422, detail={"code": "INVALID_FILE_COUNT", "message": "P0 accepts exactly one image."})
    temporary_case = f"TEMP-{os.urandom(8).hex().upper()}"
    try:
        relative_path, _ = storage.save_image_bytes(await read_limited(files[0]), temporary_case)
        job = jobs.submit(relative_path, input_kind="image")
    except InputError as exc:
        raise HTTPException(status_code=exc.http_status, detail={"code": exc.code, "message": str(exc)}) from exc
    except QueueFullError as exc:
        raise HTTPException(status_code=429, detail={"code": "QUEUE_FULL", "message": str(exc)}) from exc
    return {
        "job_id": job.job_id,
        "case_id": job.case_id,
        "status": job.status,
        "status_url": f"/api/v1/jobs/{job.job_id}",
    }


@api.get("/api/v1/jobs/{job_id}")
def get_job(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        error("RESULT_NOT_FOUND", "Job not found.", 404)
    kind = storage.analysis_job_type(job_id)
    if kind:
        status = {"queued": "PENDING", "running": "RUNNING", "success": "COMPLETED", "failed": "FAILED"}[job.status]
        start = datetime.fromisoformat(job.started_at or job.created_at)
        end = datetime.fromisoformat(job.finished_at) if job.finished_at else datetime.now(UTC)
        return {"job_id": job_id, "job_type": kind, "case_id": job.case_id,
                "status": status, "progress": job.progress / 100,
                "processed_slices": 1 if status == "COMPLETED" else 0, "total_slices": 1,
                "elapsed_time_ms": max(0, int((end - start).total_seconds() * 1000)),
                "estimated_remaining_time_ms": None,
                "error_code": job.error_code, "error_message": job.error_message,
                "created_at": job.created_at, "finished_at": job.finished_at}
    return job


@api.get("/api/v1/jobs/{job_id}/result")
def get_job_result(job_id: str):
    job, result = jobs.result(job_id)
    if job is None:
        error("RESULT_NOT_FOUND", "Job not found.", 404)
    if storage.analysis_job_type(job_id) == "CASE_PARSE":
        record = storage.get_case(case_id=job.case_id)
        if record is None:
            error("RESULT_NOT_FOUND", "Case not found.", 404)
        return public_case(record)
    if result is None:
        if job.status == "failed" and storage.analysis_job_type(job_id):
            error("INFERENCE_FAILED", "Analysis failed; inspect protected server logs.", 500)
        error("INVALID_REQUEST", "Job is not finished.", 409)
    if isinstance(result, dict) and "positions" in result:
        return {key: value for key, value in result.items() if key != "positions"}
    return result


ui = build_ui(storage, adapter, jobs, baseline)
blocked = [
    str(Path(__file__).resolve().parents[1] / ".git"),
    str(Path(__file__).resolve().parents[1] / ".env"),
    str(storage.uploads),
]
app = gr.mount_gradio_app(
    api,
    ui,
    path="/gradio",
    allowed_paths=[str(storage.results), str(storage.temp)],
    blocked_paths=blocked,
    max_file_size=f"{os.getenv('APP_MAX_UPLOAD_MIB', '20')}mb",
)
