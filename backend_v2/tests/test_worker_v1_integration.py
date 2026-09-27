"""Backend v2 against the pinned, unchanged Worker v1 client and real frozen runner."""
from __future__ import annotations

import hashlib
import base64
import importlib
import json
import os
import subprocess
import sys
import uuid
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend_v2.api.app import app, get_db
from backend_v2.auth.credentials import issue_user_credential
from backend_v2.db.base import Base
from backend_v2.models.entities import Asset, InferenceJob, InferenceResult, Slice, User
from backend_v2.services.retention import expire_inputs
from backend_v2.workers.provision import provision, write_worker_env


WORKER_SHA = "24d4fbf8674ce4f34070daebe006ea31ab13f647"
MODEL_SHA = "548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734"
PREPROCESSING = "formal-resnet18-baseline-rule-b-v1"
PROTOCOL = "stage1-occlusion-instability-v1"


class MemoryStore:
    def __init__(self):
        self.items = {}

    def put(self, body, media, prefix):
        key = f"{prefix}/{uuid.uuid4().hex}"
        self.items[key] = (body, media)
        return key

    def delete(self, key):
        self.items.pop(key, None)

    def signed_get(self, sl):
        return f"https://objects.example/{sl.staging_object_key}"

    def signed_asset_get(self, asset):
        return f"https://objects.example/{asset.object_key}?signature=test"

    def read(self, key):
        return self.items[key]


def worker_root_or_skip():
    raw = os.environ.get("EPILOCATE_WORKER_ROOT")
    worker_python = os.environ.get("EPILOCATE_WORKER_PYTHON")
    frozen_root = os.environ.get("EPILOCATE_FROZEN_ROOT")
    if not all((raw, worker_python, frozen_root)):
        pytest.skip("Set EPILOCATE_WORKER_ROOT, EPILOCATE_WORKER_PYTHON and EPILOCATE_FROZEN_ROOT for real Worker integration")
    root = Path(raw).resolve()
    actual_sha = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    baseline = subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", WORKER_SHA, actual_sha], check=False)
    if baseline.returncode != 0:
        pytest.skip(f"Worker HEAD {actual_sha} does not descend from pinned baseline {WORKER_SHA}")
    return root, Path(worker_python), Path(frozen_root)


def run_worker_runner(worker_python, worker_root, frozen_root, input_path, claim, worker_id, output_dir):
    script = Path(__file__).with_name("worker_frozen_result.py")
    env = {**os.environ, "PYTHONPATH": str(worker_root), "PYTHONDONTWRITEBYTECODE": "1"}
    completed = subprocess.run([str(worker_python), str(script), "--input", str(input_path),
                    "--output", str(output_dir), "--worker-id", worker_id,
                    "--frozen-root", str(frozen_root)], check=True, env=env, timeout=180,
                    input=json.dumps(claim), text=True, capture_output=True)
    envelope = json.loads(completed.stdout)
    manifest = envelope["manifest"]
    assets = {name: (base64.b64decode(value["data"]), value["media_type"])
              for name, value in envelope["assets"].items()}
    return manifest, assets


def test_backend_worker_frozen_prediction_and_occlusion(monkeypatch, tmp_path):
    worker_root, worker_python, frozen_root = worker_root_or_skip()
    fixture = worker_root / "docs/interfaces/fixtures/p0_synthetic_ct.dcm"
    raw = fixture.read_bytes()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setenv("EPILOCATE_V2_ALLOW_ENV_TOKENS", "false")
    monkeypatch.setenv("EPILOCATE_V2_LEASE_SECRET", "integration-test-lease-secret-0123456789")
    store = MemoryStore()
    api_module = importlib.import_module("backend_v2.api.app")
    monkeypatch.setattr(api_module, "ObjectStore", lambda: store)

    def override():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override
    try:
        with factory.begin() as db:
            user = User(auth_subject="integration-user")
            db.add(user)
            db.flush()
            _, user_token = issue_user_credential(db, user, expires_in=timedelta(hours=1), label="worker-integration")
            worker_id, worker_token = provision(db, model_id="baseline_resnet18", model_hash=MODEL_SHA,
                preprocessing_version=PREPROCESSING, protocol_id=PROTOCOL,
                display_name="Pinned Worker v1 integration")
        credential_file = tmp_path / "worker.env"
        write_worker_env(credential_file, worker_id=worker_id, token=worker_token, model_hash=MODEL_SHA,
            backend_url="https://backend.example", frozen_root=frozen_root, data_root=tmp_path / "worker-data")
        assert credential_file.stat().st_mode & 0o777 == 0o600
        assert worker_token not in credential_file.name

        client = TestClient(app)
        user_headers = {"Authorization": f"Bearer {user_token}"}

        def backend(request):
            response = client.request(request.method, request.url.raw_path.decode(),
                                      content=request.content, headers=dict(request.headers))
            return httpx.Response(response.status_code, content=response.content, headers=dict(response.headers))

        sys.path.insert(0, str(worker_root))
        try:
            from worker.client import WorkerClient
            worker = WorkerClient("https://backend.example", worker_token, httpx.MockTransport(backend))
            registered = worker.register(worker_id, MODEL_SHA, {"accelerator": "CPU"})
            assert registered["registered"] is True
            worker.heartbeat(worker_id, "IDLE", None)
            created = client.post("/api/v2/cases", json={"patient_id": None},
                                  headers={**user_headers, "Idempotency-Key": "integration-case-01"})
            assert created.status_code == 201, created.text
            case_id = created.json()["case_id"]
            uploaded = client.post(f"/api/v2/cases/{case_id}/upload", data={"input_kind": "dicom_series"},
                files={"file": ("synthetic.dcm", raw, "application/dicom")},
                headers={**user_headers, "Idempotency-Key": "integration-upload-01"})
            assert uploaded.status_code == 201, uploaded.text
            slice_id = uploaded.json()["slice_id"]
            with factory() as db:
                sl = db.scalar(select(Slice).where(Slice.slice_ref == slice_id))
                assert store.items[sl.staging_object_key][0] == raw

            for kind in ("PREDICTION", "OCCLUSION"):
                path = "/api/v2/predictions" if kind == "PREDICTION" else "/api/v2/jobs/occlusion"
                body = {"case_id": case_id, "slice_id": slice_id, "model_id": "baseline_resnet18"}
                if kind == "OCCLUSION":
                    body.update(protocol_id=PROTOCOL, scales=[16])
                created_job = client.post(path, json=body,
                    headers={**user_headers, "Idempotency-Key": f"integration-{kind.lower()}-01"})
                assert created_job.status_code == 202, created_job.text
                job_id = created_job.json()["job_id"]
                assert client.get(f"/api/v2/jobs/{job_id}", headers=user_headers).json()["status"] == "CREATED"
                assignment = worker.claim(worker_id, MODEL_SHA, str(uuid.uuid4()), 1)
                assert assignment["job_id"] == job_id
                assert assignment["input_reference"]["sha256"] == hashlib.sha256(raw).hexdigest()
                assert client.get(f"/api/v2/jobs/{job_id}", headers=user_headers).json()["status"] == "RUNNING"
                beat = worker.heartbeat(worker_id, "RUNNING", {"job_id": job_id,
                    "attempt_id": assignment["attempt_id"], "lease_token": assignment["lease_token"]})
                assert beat["lease_expire_time"]
                output_dir = tmp_path / kind.lower()
                output_dir.mkdir()
                manifest, assets = run_worker_runner(worker_python, worker_root, frozen_root,
                    fixture, assignment, worker_id, output_dir)
                accepted = worker.submit(job_id, manifest, assets)
                assert accepted["accepted"] is True and accepted["job_status"] == "COMPLETED"
                repeated = worker.submit(job_id, manifest, assets)
                assert repeated == accepted
                result_id = accepted["result_id"]
                with factory() as db:
                    job = db.scalar(select(InferenceJob).where(InferenceJob.public_id == job_id))
                    result = db.scalar(select(InferenceResult).where(InferenceResult.job_id == job.id))
                    assert result.result_json["source"] == "LIVE_CASE"
                    assert result.result_json["model_version"] == MODEL_SHA
                    assert result.metadata_json["protocol_id"] == PROTOCOL
                    assert result.result_json["prediction"]["positive_probability"] >= 0
                    if kind == "OCCLUSION":
                        assert len(result.result_json["positions"]) == 729
                        assert result.result_json["scale_summaries"][0]["response_layer"]
                        assert len(result.asset_manifest) == 3
                        assert len(db.scalars(select(Asset).where(Asset.result_id == result.id)).all()) == 3
                detail = client.get(f"/api/v2/results/{result_id}", headers=user_headers)
                assert detail.status_code == 200 and detail.json()["provenance"]["checkpoint_sha256"] == MODEL_SHA
                if kind == "OCCLUSION":
                    assert all(item["asset_url"].startswith("/api/v2/results/") for item in detail.json()["assets"])
                    assert all("objects.example" not in item["asset_url"] for item in detail.json()["assets"])
                    positions = client.get(f"/api/v2/results/{result_id}/positions",
                        params={"scale": 16, "limit": 1000}, headers=user_headers)
                    assert positions.status_code == 200 and len(positions.json()["positions"]) == 729
                    for asset in detail.json()["assets"]:
                        image = client.get(f"/api/v2/results/{result_id}/assets/{asset['asset_id']}", headers=user_headers)
                        assert image.status_code == 200 and image.content.startswith(b"\x89PNG\r\n\x1a\n")
                    with factory() as db:
                        stored = db.scalar(select(InferenceResult).where(InferenceResult.job_id == job.id))
                        object_key = stored.asset_manifest[0]["object_key"]
                    original = store.items[object_key]
                    store.items[object_key] = (original[0] + b"corrupt", original[1])
                    corrupt = client.get(f"/api/v2/results/{result_id}/assets/{detail.json()['assets'][0]['asset_id']}", headers=user_headers)
                    assert corrupt.status_code == 503 and corrupt.json()["code"] == "ASSET_INTEGRITY_FAILURE"
                    store.items[object_key] = original
                worker.heartbeat(worker_id, "IDLE", None)

            with factory.begin() as db:
                sl = db.scalar(select(Slice).where(Slice.slice_ref == slice_id))
                from backend_v2.services.common import now
                sl.staging_expires_at = now() - timedelta(seconds=1)
            with factory.begin() as db:
                assert expire_inputs(db, store) == 1
            retained = client.get(f"/api/v2/results/{result_id}", headers=user_headers)
            assert retained.status_code == 200 and len(retained.json()["assets"]) == 3
            retained_positions = client.get(f"/api/v2/results/{result_id}/positions",
                params={"scale": 16, "limit": 1000}, headers=user_headers)
            assert retained_positions.status_code == 200 and len(retained_positions.json()["positions"]) == 729
        finally:
            sys.path.remove(str(worker_root))
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
