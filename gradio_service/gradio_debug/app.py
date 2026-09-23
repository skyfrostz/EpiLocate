from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Keep Gradio's transient copies inside the project so the user home can remain blocked.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("GRADIO_TEMP_DIR", str(PROJECT_ROOT / "storage" / "temp"))

import gradio as gr
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import RedirectResponse

from .contracts import InferenceResult
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
jobs = JobManager(storage, adapter)


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


@api.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/gradio")


@api.get("/api/health")
def health():
    real_ready = adapter.real_ready if adapter.mode == "real" else False
    healthy = adapter.mode == "mock" or real_ready
    return {
        "status": "ok" if healthy else "degraded",
        "mode": adapter.mode,
        "contract_version": "0.1",
        "real_ready": real_ready,
    }


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
        raise HTTPException(status_code=404, detail={"code": "JOB_NOT_FOUND", "message": "Job not found."})
    return job


@api.get("/api/v1/jobs/{job_id}/result")
def get_job_result(job_id: str):
    job, result = jobs.result(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail={"code": "JOB_NOT_FOUND", "message": "Job not found."})
    if result is None:
        raise HTTPException(status_code=409, detail={"code": "JOB_NOT_FINISHED", "message": "Job is not finished."})
    return result


ui = build_ui(storage, adapter, jobs)
blocked = [
    str(Path.home()),
    str(Path.home() / "Desktop"),
    str(Path.home() / "Documents"),
    str(Path.home() / "Downloads"),
    str(Path(__file__).resolve().parents[1] / ".git"),
    str(Path(__file__).resolve().parents[1] / ".env"),
]
app = gr.mount_gradio_app(
    api,
    ui,
    path="/gradio",
    allowed_paths=[str(storage.results)],
    blocked_paths=blocked,
    max_file_size=f"{os.getenv('APP_MAX_UPLOAD_MIB', '20')}mb",
)
