"""Real frozen P0 integration on a deterministic synthetic CT DICOM."""
import hashlib
import io
import json
import time
import uuid
from pathlib import Path

import pydicom
import pytest
import yaml
import jsonschema
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient
from PIL import Image

from algorithm.service import FrozenBaseline, validate_dicom
from scripts.occlusion_runner import rasterize_block_scores, project_area_average
from gradio_service.gradio_debug.app import app, storage
from gradio_service.gradio_debug.inference import InferenceAdapter
from gradio_service.gradio_debug.contracts import CaseInput

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "docs/interfaces/fixtures/p0_synthetic_ct.dcm"
VECTOR = json.loads((ROOT / "docs/interfaces/fixtures/p0_http_vector.json").read_text())
SPEC = yaml.safe_load((ROOT / "docs/interfaces/algorithm_api_contract.yaml").read_text())


def check_schema(name, value):
    resolver = jsonschema.RefResolver.from_schema(SPEC)
    jsonschema.validate(value, SPEC["components"]["schemas"][name], resolver=resolver)


def completed(client, job_id):
    for _ in range(200):
        status = client.get(f"/api/v1/jobs/{job_id}").json()
        if status["status"] in {"COMPLETED", "FAILED"}:
            return status
        time.sleep(.1)
    pytest.fail("job timeout")


def test_synthetic_fixture_and_deidentification():
    data = FIXTURE.read_bytes()
    assert hashlib.sha256(data).hexdigest() == VECTOR["dicom_sha256"]
    assert validate_dicom(data, 1_000_000) == (80, 112)
    ds = pydicom.dcmread(io.BytesIO(data))
    ds.PatientID = "NOT_ALLOWED"
    stream = io.BytesIO()
    ds.save_as(stream, enforce_file_format=True)
    with pytest.raises(ValueError):
        validate_dicom(stream.getvalue(), 1_000_000)


def test_wrong_frozen_root_unavailable(tmp_path):
    assert not FrozenBaseline(tmp_path).ready()


def test_runtime_storage_cannot_target_frozen_outputs(tmp_path, monkeypatch):
    from gradio_service.gradio_debug.storage import Storage
    monkeypatch.setenv("EPILOCATE_FROZEN_ROOT", str(tmp_path / "frozen"))
    with pytest.raises(ValueError, match="frozen experiment outputs"):
        Storage(tmp_path / "frozen/outputs/experiments/FORMAL-BL-R18-V1/occlusion_stage1/validation")


def test_mock_source_is_explicit(tmp_path, monkeypatch):
    from gradio_service.gradio_debug.storage import Storage
    monkeypatch.setenv("APP_MODE", "mock")
    store = Storage(tmp_path)
    image = Image.new("RGB", (8, 8), (12, 34, 56))
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    relative, _ = store.save_image_bytes(stream.getvalue(), "TEMP-TEST")
    result = InferenceAdapter(store).run_case(CaseInput(case_id="CASE-TEST", input_kind="image", files=[relative]))
    assert result.mode == "mock" and result.source == "MOCK"
    assert "MOCK RESULT" in result.warnings[0]


def test_real_dicom_http_prediction_occlusion_geometry_and_idempotency():
    key = uuid.uuid4().hex
    with TestClient(app) as client:
        capabilities = client.get("/api/v1/capabilities").json()
        check_schema("CapabilityReport", capabilities)
        assert capabilities["capabilities"]["baseline_slice_prediction"]["state"] == "available"
        for name in ("nifti", "multi_slice", "patient_summary", "frozen_validation_summary",
                     "robust", "coarse_localization", "lime", "doctor_feedback"):
            assert capabilities["capabilities"][name]["state"] == "planned"
        files = {"files": ("synthetic.dcm", FIXTURE.read_bytes(), "application/dicom")}
        upload = client.post("/api/v1/cases", headers={"Idempotency-Key": key},
                             data={"input_kind": "dicom_series"}, files=files)
        assert upload.status_code == 202
        case_id = upload.json()["case_id"]
        duplicate = client.post("/api/v1/cases", headers={"Idempotency-Key": key},
                                data={"input_kind": "dicom_series"}, files=files)
        assert duplicate.json() == upload.json()
        slices = client.get(f"/api/v1/cases/{case_id}/slices").json()["slices"]
        assert len(slices) == 1
        slice_id = slices[0]["slice_id"]
        geometry = slices[0]["geometry"]
        check_schema("Slice", slices[0])
        assert geometry["raw_to_algorithm_edge_affine"] == [2, 0, 0, 0, 2.8, 0, 0, 0, 1]
        preview = Image.open(io.BytesIO(client.get(f"/api/v1/slices/{slice_id}/preview").content))
        assert preview.size == (112, 80)
        stages = FrozenBaseline().stages(FIXTURE)
        assert np.array_equal(np.asarray(preview), np.rint(stages.normalized * 255).astype("uint8"))
        assert np.allclose(np.array([112, 80, 1]) @ np.asarray(geometry["raw_to_algorithm_edge_affine"]).reshape(3, 3).T,
                           [224, 224, 1])
        pred_body = {"case_id": case_id, "slice_id": slice_id, "unit": "slice", "model_id": "baseline_resnet18"}
        pred_key = uuid.uuid4().hex
        accepted = client.post("/api/v1/predictions", headers={"Idempotency-Key": pred_key}, json=pred_body)
        assert accepted.status_code == 202
        assert client.post("/api/v1/predictions", headers={"Idempotency-Key": pred_key}, json=pred_body).json() == accepted.json()
        conflict = client.post("/api/v1/predictions", headers={"Idempotency-Key": pred_key},
                               json={**pred_body, "slice_id": "OTHER"})
        assert conflict.status_code == 409 and conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
        check_schema("JobAccepted", accepted.json())
        prediction_job = completed(client, accepted.json()["job_id"])
        assert prediction_job["status"] == "COMPLETED"
        check_schema("Job", prediction_job)
        prediction_result = client.get(f"/api/v1/jobs/{accepted.json()['job_id']}/result").json()
        check_schema("AnalysisResult", prediction_result)
        prediction = prediction_result["prediction"]
        assert prediction["source"] == "LIVE_CASE" and prediction["predicted_class"] == 0
        assert abs(prediction["positive_probability"] - VECTOR["expected"]["positive_probability"]) < 1e-6
        assert abs(prediction["predicted_class_confidence"] - (1 - prediction["positive_probability"])) < 1e-8
        occ = client.post("/api/v1/jobs/occlusion", headers={"Idempotency-Key": uuid.uuid4().hex},
                          json={"case_id": case_id, "slice_id": slice_id, "model_id": "baseline_resnet18",
                                "scales": [16], "protocol_id": "stage1-occlusion-instability-v1"})
        assert occ.status_code == 202
        assert completed(client, occ.json()["job_id"])["status"] == "COMPLETED"
        result = client.get(f"/api/v1/jobs/{occ.json()['job_id']}/result").json()
        check_schema("AnalysisResult", result)
        assert "positions" not in result and result["source"] == "LIVE_CASE"
        assert result["coarse_localization"]["status"] == "NOT_IMPLEMENTED"
        assert result["lime"]["status"] == "NOT_IMPLEMENTED"
        positions = client.get(f"/api/v1/occlusion-results/{result['result_id']}/positions",
                               params={"scale": 16, "limit": 1000}).json()["positions"]
        assert len(positions) == 729 and positions[0]["x"] == positions[0]["y"] == 0
        assert positions[0]["candidate_response"] == max(positions[0]["decision_confidence_drop"], 0)
        image = client.get("/api/v1/assets/response-16.png", params={"result_id": result["result_id"]})
        assert image.status_code == 200 and Image.open(io.BytesIO(image.content)).size == (224, 224)
        assert client.get("/api/v1/assets/response-16.png", params={"result_id": "RESULT-unknown"}).status_code == 404
        assert client.get("/api/v1/assets/comparison-32.json", params={"result_id": result["result_id"]}).status_code == 404
        response_map = rasterize_block_scores(pd.DataFrame(positions).rename(columns={"candidate_response": "score"}), "score")
        display = np.asarray(Image.open(io.BytesIO(image.content)), dtype=float)
        expected_display = np.rint(response_map / max(float(response_map.max()), 1e-6) * 255)
        assert np.array_equal(display, expected_display)
        grid = client.get("/api/v1/assets/comparison-16.json", params={"result_id": result["result_id"]}).json()
        assert len(grid) == len(grid[0]) == 14
        assert np.allclose(grid, project_area_average(response_map))
