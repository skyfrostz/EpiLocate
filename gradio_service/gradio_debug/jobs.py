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
from algorithm.service import FrozenBaseline, MODEL_SHA, MODEL_ID, PREPROCESSING_VERSION, PROTOCOL_ID, reserved_module


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class QueueFullError(RuntimeError):
    pass


class JobManager:
    def __init__(self, storage: Storage, adapter: InferenceAdapter, queue_limit: int = 8,
                 baseline: FrozenBaseline | None = None) -> None:
        self.storage = storage
        self.adapter = adapter
        self.baseline = baseline
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

    def submit_analysis(self, case_id: str, slice_id: str, kind: str, scales: list[int] | None = None) -> JobStatus:
        if self.baseline is None or not self.baseline.ready():
            raise RuntimeError("Frozen baseline unavailable.")
        if not self.capacity.acquire(blocking=False):
            raise QueueFullError("Inference queue is full.")
        job = JobStatus(job_id=str(uuid.uuid4()), case_id=case_id, status="queued", stage="queued",
                        progress=0, created_at=utc_now())
        try:
            self.storage.create_job(job)
            self.storage.mark_analysis_job(job.job_id, kind.upper())
            self.executor.submit(self._run_analysis, job, slice_id, kind, scales or [])
            return job
        except Exception:
            self.capacity.release()
            raise

    def _run_analysis(self, job: JobStatus, slice_id: str, kind: str, scales: list[int]) -> None:
        self.storage.update_job(job.job_id, status="running", stage=kind, progress=25, started_at=utc_now())
        try:
            record = self.storage.get_case(case_id=job.case_id)
            if record is None or record["slice_id"] != slice_id:
                raise ValueError("Case or slice unavailable.")
            path = self.storage.absolute_input_path(record["input_path"])
            result_id = "RESULT-" + job.job_id
            if kind == "occlusion":
                asset_dir = self.storage.results / job.case_id / result_id
                result = self.baseline.occlusion(path, job.case_id, slice_id, scales, asset_dir)
                result["result_id"] = result_id
            else:
                prediction, _ = self.baseline.predict(path, job.case_id, slice_id)
                result = {
                    "contract_version": "1.0", "result_id": result_id, "case_id": job.case_id,
                    "slice_id": slice_id, "source": "LIVE_CASE", "status": "COMPLETED",
                    "protocol_id": PROTOCOL_ID, "model_id": MODEL_ID, "model_version": MODEL_SHA,
                    "preprocessing_version": PREPROCESSING_VERSION, "prediction": prediction,
                    "scale_summaries": [], "cross_scale": [],
                    "coarse_localization": reserved_module(), "lime": reserved_module(),
                    "clinical_explanation": {"status": "NOT_IMPLEMENTED", "method_version": None, "summary": None, "evidence_region_ids": []},
                    "paired_model_results": [], "qa_status": "NOT_RUN",
                    "provenance": {"checkpoint_sha256": MODEL_SHA, "checkpoint_epoch": 2},
                }
            relative = self.storage.write_analysis_result(job.job_id, result)
            self.storage.update_job(job.job_id, status="success", stage="complete", progress=100,
                                    finished_at=utc_now(), result_path=relative)
        except Exception:
            # Never put patient metadata, physical paths, or traceback into API-visible job state.
            self.storage.update_job(job.job_id, status="failed", stage="failed", progress=100,
                                    finished_at=utc_now(), error_code="INFERENCE_FAILED",
                                    error_message="Analysis failed; inspect protected server logs.")
            self.error_log.error("analysis_failed case_id=%s job_id=%s\n%s",
                                 job.case_id, job.job_id, traceback.format_exc())
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
