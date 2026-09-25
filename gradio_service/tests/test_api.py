import importlib
import io
import time

from fastapi.testclient import TestClient
from PIL import Image


def image_bytes() -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", (6, 6), "gray").save(stream, "PNG")
    return stream.getvalue()


def test_health_contract_and_job_api(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_MODE", "mock")
    monkeypatch.setenv("APP_DATA_ROOT", str(tmp_path))
    import gradio_debug.app as app_module

    app_module = importlib.reload(app_module)
    with TestClient(app_module.app) as client:
        assert client.get("/api/health").json()["status"] == "ok"
        assert client.get("/api/v1/contract").json()["contract_version"] == "0.1"
        response = client.post(
            "/api/v1/jobs/inference",
            files={"files": ("patient-name.png", image_bytes(), "image/png")},
            data={"input_kind": "image"},
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        for _ in range(100):
            status = client.get(f"/api/v1/jobs/{job_id}").json()
            if status["status"] in {"success", "failed"}:
                break
            time.sleep(0.02)
        result_response = client.get(f"/api/v1/jobs/{job_id}/result")
        assert result_response.status_code == 200
        result = result_response.json()
        assert result["mode"] == "mock"
        assert "patient-name" not in str(result)
        assert "D:\\" not in str(result)


def test_invalid_upload_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_MODE", "mock")
    monkeypatch.setenv("APP_DATA_ROOT", str(tmp_path))
    import gradio_debug.app as app_module

    app_module = importlib.reload(app_module)
    with TestClient(app_module.app) as client:
        response = client.post(
            "/api/v1/jobs/inference",
            files={"files": ("fake.png", b"not-an-image", "image/png")},
            data={"input_kind": "image"},
        )
        assert response.status_code == 415


def test_real_mode_missing_checkpoint_is_degraded(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_MODE", "real")
    monkeypatch.setenv("APP_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("REAL_PIPELINE_MODULE", "missing_algorithm.inference_pipeline")
    monkeypatch.setenv("EPILOCATE_FROZEN_ROOT", str(tmp_path / "missing-frozen-baseline"))
    import gradio_debug.app as app_module

    app_module = importlib.reload(app_module)
    with TestClient(app_module.app) as client:
        health = client.get("/api/health").json()
        assert health["status"] == "degraded"
        assert health["real_ready"] is False
        assert client.get("/api/v1/capabilities").json()["capabilities"]["baseline_slice_prediction"]["state"] == "unavailable"
        response = client.post(
            "/api/v1/jobs/inference",
            files={"files": ("image.png", image_bytes(), "image/png")},
            data={"input_kind": "image"},
        )
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "REAL_PIPELINE_UNAVAILABLE"
