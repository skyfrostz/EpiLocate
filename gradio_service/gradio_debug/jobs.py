from __future__ import annotations

import logging
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from .contracts import CaseInput, JobStatus
from .inference import InferenceAdapter
from .storage import Storage


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class QueueFullError(RuntimeError):
    pass


class JobManager:
    def __init__(self, storage: Storage, adapter: InferenceAdapter, queue_limit: int = 8) -> None:
        self.storage = storage
        self.adapter = adapter
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="inference")
        # ponytail: one process and one worker are deliberate; replace with an external queue only when measured demand requires it.
        self.capacity = threading.BoundedSemaphore(queue_limit + 1)
        self.log = logging.getLogger("inference")
        self.error_log = logging.getLogger("errors")
        self.storage.recover_interrupted(utc_now())

    def submit(self, relative_input_path: str, input_kind: str = "image") -> JobStatus:
        if not self.capacity.acquire(blocking=False):
            raise QueueFullError("Inference queue is full.")
        case_id = f"CASE-{uuid.uuid4().hex[:12].upper()}"
        job_id = str(uuid.uuid4())
        job = JobStatus(
            job_id=job_id,
            case_id=case_id,
            status="queued",
            stage="queued",
            progress=0,
            created_at=utc_now(),
        )
        try:
            source_path = self.storage.absolute_input_path(relative_input_path)
            target_dir = self.storage.uploads / case_id
            target_dir.mkdir(parents=True, exist_ok=False)
            target = target_dir / source_path.name
            source_path.replace(target)
            source_path.parent.rmdir()
            case_input = CaseInput(
                case_id=case_id,
                input_kind=input_kind,
                files=[target.relative_to(self.storage.root).as_posix()],
            )
            self.storage.create_job(job)
            self.executor.submit(self._run, job, case_input)
            return job
        except Exception:
            self.capacity.release()
            raise

    def _run(self, job: JobStatus, case_input: CaseInput) -> None:
        started_at = utc_now()
        self.storage.update_job(
            job.job_id, status="running", stage="inference", progress=25, started_at=started_at
        )
        self.log.info("job_started case_id=%s job_id=%s", job.case_id, job.job_id)
        try:
            result = self.adapter.run_case(case_input)
            result_path = self.storage.write_result(result)
            self.storage.update_job(
                job.job_id,
                status=result.status,
                stage="complete" if result.status == "success" else "failed",
                progress=100,
                finished_at=utc_now(),
                result_path=result_path,
                error_code=result.error.code if result.error else None,
                error_message=result.error.message if result.error else None,
            )
            self.log.info("job_finished case_id=%s job_id=%s status=%s", job.case_id, job.job_id, result.status)
        except Exception as exc:
            code = "REAL_PIPELINE_ERROR" if self.adapter.mode == "real" else "INFERENCE_ERROR"
            result = self.adapter.failed_result(job.case_id, code, "Inference failed. See error log.", "inference")
            result_path = self.storage.write_result(result)
            self.storage.update_job(
                job.job_id,
                status="failed",
                stage="failed",
                progress=100,
                finished_at=utc_now(),
                result_path=result_path,
                error_code=code,
                error_message=result.error.message if result.error else str(exc),
            )
            self.error_log.error(
                "job_failed case_id=%s job_id=%s\n%s", job.case_id, job.job_id, traceback.format_exc()
            )
        finally:
            self.capacity.release()

    def get(self, job_id: str) -> JobStatus | None:
        return self.storage.get_job(job_id)

    def result(self, job_id: str):
        job = self.storage.get_job(job_id)
        if job is None:
            return None, None
        with self.storage._connect() as conn:
            row = conn.execute("SELECT result_path FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if row is None or not row["result_path"]:
            return job, None
        return job, self.storage.read_result(row["result_path"])

    def result_file(self, job_id: str):
        with self.storage._connect() as conn:
            row = conn.execute("SELECT result_path FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if row is None or not row["result_path"]:
            return None
        return self.storage.result_file(row["result_path"])

    def close(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)

