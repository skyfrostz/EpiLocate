import io
import time

from PIL import Image

from gradio_debug.inference import InferenceAdapter
from gradio_debug.jobs import JobManager, utc_now
from gradio_debug.storage import Storage


def image_bytes() -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(stream, "PNG")
    return stream.getvalue()


def test_job_lifecycle_and_restart_recovery(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_MODE", "mock")
    storage = Storage(tmp_path)
    relative, _ = storage.save_image_bytes(image_bytes(), "TEMP-1")
    manager = JobManager(storage, InferenceAdapter(storage))
    job = manager.submit(relative)
    for _ in range(100):
        current = manager.get(job.job_id)
        if current and current.status in {"success", "failed"}:
            break
        time.sleep(0.02)
    assert current is not None and current.status == "success"
    stored_job, result = manager.result(job.job_id)
    assert stored_job is not None and result is not None and result.status == "success"
    manager.close()

    with storage._connect() as conn:
        conn.execute(
            "INSERT INTO jobs(job_id, case_id, status, stage, progress, created_at) VALUES(?,?,?,?,?,?)",
            ("interrupted", "CASE-X", "running", "inference", 20, utc_now()),
        )
    assert storage.recover_interrupted(utc_now()) == 1
    assert storage.get_job("interrupted").error_code == "RESTART_INTERRUPTED"

