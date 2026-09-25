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
        frozen_root = os.getenv("EPILOCATE_FROZEN_ROOT")
        if frozen_root and self.root.is_relative_to((Path(frozen_root).resolve() / "outputs/experiments")):
            raise ValueError("APP_DATA_ROOT cannot be inside frozen experiment outputs")
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
            conn.execute("""CREATE TABLE IF NOT EXISTS cases (
                case_id TEXT PRIMARY KEY, slice_id TEXT UNIQUE NOT NULL,
                input_path TEXT NOT NULL, raw_height INTEGER NOT NULL,
                raw_width INTEGER NOT NULL, created_at TEXT NOT NULL
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS analysis_results (
                result_id TEXT PRIMARY KEY, case_id TEXT NOT NULL,
                job_id TEXT NOT NULL, result_path TEXT NOT NULL
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS analysis_jobs (
                job_id TEXT PRIMARY KEY, job_type TEXT NOT NULL
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS idempotency (
                key TEXT PRIMARY KEY, request_digest TEXT NOT NULL,
                response_json TEXT NOT NULL
            )""")

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

    def save_dicom_bytes(self, data: bytes, case_id: str, slice_id: str, rows: int, columns: int, created_at: str) -> None:
        case_dir = self.uploads / case_id
        case_dir.mkdir(parents=True, exist_ok=False)
        path = case_dir / "slice.dcm"
        try:
            with path.open("xb") as stream:
                stream.write(data)
            relative = path.relative_to(self.root).as_posix()
            with self._connect() as conn:
                conn.execute("INSERT INTO cases VALUES (?,?,?,?,?,?)",
                             (case_id, slice_id, relative, rows, columns, created_at))
        except Exception:
            path.unlink(missing_ok=True)
            case_dir.rmdir()
            raise

    def get_case(self, case_id: str | None = None, slice_id: str | None = None):
        with self._connect() as conn:
            if case_id is not None:
                row = conn.execute("SELECT * FROM cases WHERE case_id=?", (case_id,)).fetchone()
            else:
                row = conn.execute("SELECT * FROM cases WHERE slice_id=?", (slice_id,)).fetchone()
        return dict(row) if row else None

    def delete_case(self, case_id: str) -> None:
        record = self.get_case(case_id=case_id)
        if record is None:
            return
        with self._connect() as conn:
            conn.execute("DELETE FROM cases WHERE case_id=?", (case_id,))
        path = self.absolute_input_path(record["input_path"])
        path.unlink(missing_ok=True)
        path.parent.rmdir()

    def mark_analysis_job(self, job_id: str, job_type: str) -> None:
        with self._connect() as conn:
            conn.execute("INSERT INTO analysis_jobs VALUES (?,?)", (job_id, job_type))

    def analysis_job_type(self, job_id: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute("SELECT job_type FROM analysis_jobs WHERE job_id=?", (job_id,)).fetchone()
        return row["job_type"] if row else None

    def idempotent_response(self, key: str, digest: str):
        with self._connect() as conn:
            row = conn.execute("SELECT request_digest,response_json FROM idempotency WHERE key=?", (key,)).fetchone()
        if row is None:
            return None
        if row["request_digest"] != digest:
            raise InputError("IDEMPOTENCY_CONFLICT", "Idempotency key was used for another request.", 409)
        response = json.loads(row["response_json"])
        if response == {"_pending": True}:
            raise InputError("IDEMPOTENCY_CONFLICT", "The same request is still being submitted.", 409)
        return response

    def reserve_idempotency(self, key: str, digest: str):
        """Claim a key before creating a case or job, including across processes."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT request_digest,response_json FROM idempotency WHERE key=?", (key,)).fetchone()
            if row is None:
                conn.execute("INSERT INTO idempotency VALUES (?,?,?)",
                             (key, digest, '{"_pending": true}'))
                return None
            if row["request_digest"] != digest or row["response_json"] == '{"_pending": true}':
                raise InputError("IDEMPOTENCY_CONFLICT", "Idempotency key is occupied by another or pending request.", 409)
            return json.loads(row["response_json"])

    def store_idempotent_response(self, key: str, digest: str, response: dict) -> None:
        with self._connect() as conn:
            cursor = conn.execute("UPDATE idempotency SET response_json=? WHERE key=? AND request_digest=? AND response_json=?",
                                  (json.dumps(response, sort_keys=True), key, digest, '{"_pending": true}'))
            if cursor.rowcount != 1:
                raise ValueError("idempotency reservation was lost")

    def release_idempotency(self, key: str, digest: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM idempotency WHERE key=? AND request_digest=? AND response_json=?",
                         (key, digest, '{"_pending": true}'))

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

    def write_analysis_result(self, job_id: str, result: dict) -> str:
        result_dir = self.results / result["case_id"]
        result_dir.mkdir(parents=True, exist_ok=True)
        path = result_dir / f"{job_id}.json"
        temporary = path.with_suffix(".partial")
        temporary.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        os.replace(temporary, path)
        relative = path.relative_to(self.root).as_posix()
        with self._connect() as conn:
            conn.execute("INSERT INTO analysis_results VALUES (?,?,?,?)",
                         (result["result_id"], result["case_id"], job_id, relative))
        return relative

    def get_analysis_result(self, result_id: str):
        with self._connect() as conn:
            row = conn.execute("""SELECT r.case_id, r.job_id, r.result_path, j.status
                                  FROM analysis_results r JOIN jobs j ON j.job_id=r.job_id
                                  WHERE r.result_id=?""", (result_id,)).fetchone()
        if row is None:
            return None
        if row["status"] != "success":
            return None
        path = (self.root / row["result_path"]).resolve()
        if self.results not in path.parents or not path.is_file():
            return None
        result = json.loads(path.read_text(encoding="utf-8"))
        case = self.get_case(case_id=row["case_id"])
        if (case is None or result.get("result_id") != result_id or
                result.get("case_id") != row["case_id"] or
                result.get("slice_id") != case["slice_id"]):
            return None
        return result

    def read_result(self, relative_path: str) -> InferenceResult:
        path = (self.root / relative_path).resolve()
        if self.results not in path.parents:
            raise ValueError("result path escapes results directory")
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if payload.get("contract_version") == "1.0" else InferenceResult.model_validate(payload)

    def result_file(self, relative_path: str) -> Path:
        path = (self.root / relative_path).resolve()
        if self.results not in path.parents:
            raise ValueError("result path escapes results directory")
        return path
