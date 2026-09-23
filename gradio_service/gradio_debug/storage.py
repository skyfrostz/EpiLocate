from __future__ import annotations

import io
import json
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from .contracts import InferenceResult, JobStatus


class InputError(ValueError):
    def __init__(self, code: str, message: str, http_status: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status


class Storage:
    def __init__(self, root: Path | None = None) -> None:
        project_root = Path(__file__).resolve().parents[1]
        self.root = (root or Path(os.getenv("APP_DATA_ROOT", project_root))).resolve()
        self.uploads = self.root / "storage" / "uploads"
        self.results = self.root / "storage" / "results"
        self.temp = self.root / "storage" / "temp"
        self.data = self.root / "data"
        self.logs = self.root / "logs"
        self.db_path = self.data / "app.db"
        self.max_upload_bytes = int(os.getenv("APP_MAX_UPLOAD_MIB", "20")) * 1024 * 1024
        self.max_image_pixels = int(os.getenv("APP_MAX_IMAGE_PIXELS", "50000000"))
        self.initialize()

    def initialize(self) -> None:
        for path in (self.uploads, self.results, self.temp, self.data, self.logs):
            path.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    progress INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    result_path TEXT,
                    error_code TEXT,
                    error_message TEXT
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def recover_interrupted(self, now: str) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE jobs
                SET status='failed', stage='interrupted', progress=100,
                    finished_at=?, error_code='RESTART_INTERRUPTED',
                    error_message='Service restarted before the job completed.'
                WHERE status IN ('queued', 'running')
                """,
                (now,),
            )
            return cursor.rowcount

    def save_image_bytes(self, data: bytes, case_id: str) -> tuple[str, bytes]:
        if len(data) > self.max_upload_bytes:
            raise InputError("FILE_TOO_LARGE", "Image exceeds the configured upload limit.", 413)
        if not data:
            raise InputError("EMPTY_FILE", "Uploaded image is empty.", 422)
        Image.MAX_IMAGE_PIXELS = self.max_image_pixels
        try:
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in {"PNG", "JPEG"}:
                    raise InputError("UNSUPPORTED_MEDIA_TYPE", "Only PNG and JPEG images are supported.", 415)
                if source.width * source.height > self.max_image_pixels:
                    raise InputError("IMAGE_TOO_LARGE", "Decoded image exceeds the pixel limit.", 413)
                source.load()
                normalized = source.convert("RGB")
        except (UnidentifiedImageError, OSError) as exc:
            raise InputError("INVALID_IMAGE", "The uploaded file is not a valid PNG or JPEG image.", 415) from exc
        except Image.DecompressionBombError as exc:
            raise InputError("IMAGE_TOO_LARGE", "Decoded image exceeds the pixel limit.", 413) from exc

        case_dir = self.uploads / case_id
        case_dir.mkdir(parents=True, exist_ok=False)
        output = case_dir / f"{uuid.uuid4().hex}.png"
        normalized.save(output, format="PNG")
        normalized_bytes = output.read_bytes()
        return output.relative_to(self.root).as_posix(), normalized_bytes

    def absolute_input_path(self, relative_path: str) -> Path:
        path = (self.root / relative_path).resolve()
        if self.uploads not in path.parents:
            raise ValueError("input path escapes uploads directory")
        return path

    def create_job(self, job: JobStatus) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs(job_id, case_id, status, stage, progress, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (job.job_id, job.case_id, job.status, job.stage, job.progress, job.created_at),
            )

    def update_job(self, job_id: str, **fields: Any) -> None:
        allowed = {
            "status", "stage", "progress", "started_at", "finished_at",
            "result_path", "error_code", "error_message",
        }
        if not fields or not set(fields).issubset(allowed):
            raise ValueError("invalid job fields")
        assignments = ", ".join(f"{name}=?" for name in fields)
        values = [fields[name] for name in fields]
        with self._connect() as conn:
            conn.execute(f"UPDATE jobs SET {assignments} WHERE job_id=?", (*values, job_id))

    def get_job(self, job_id: str) -> JobStatus | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT job_id, case_id, status, stage, progress, created_at,
                       started_at, finished_at, error_code, error_message
                FROM jobs WHERE job_id=?
                """,
                (job_id,),
            ).fetchone()
        if row is None:
            return None
        return JobStatus.model_validate(dict(row))

    def result_relative_path(self, case_id: str) -> str:
        return f"storage/results/{case_id}/result.json"

    def write_result(self, result: InferenceResult) -> str:
        result_dir = self.results / result.case_id
        result_dir.mkdir(parents=True, exist_ok=True)
        path = result_dir / "result.json"
        path.write_text(
            json.dumps(result.model_dump(by_alias=True, mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path.relative_to(self.root).as_posix()

    def read_result(self, relative_path: str) -> InferenceResult:
        path = (self.root / relative_path).resolve()
        if self.results not in path.parents:
            raise ValueError("result path escapes results directory")
        return InferenceResult.model_validate_json(path.read_text(encoding="utf-8"))

    def result_file(self, relative_path: str) -> Path:
        path = (self.root / relative_path).resolve()
        if self.results not in path.parents:
            raise ValueError("result path escapes results directory")
        return path
