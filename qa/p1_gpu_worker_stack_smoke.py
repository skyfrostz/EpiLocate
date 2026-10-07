"""Exercise a running isolated HTTPS Backend, PostgreSQL, MinIO, and real Worker.

Requires EPILOCATE_V2_DATABASE_URL and the normal Backend S3 environment.
The signed object URL must be HTTPS and trusted by --ca-cert. Uses only the
repository's synthetic DICOM; credentials remain in this process environment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from backend_v2.auth.credentials import issue_user_credential
from backend_v2.db.base import make_engine
from backend_v2.models.entities import User
from backend_v2.services.storage import ObjectStore
from backend_v2.workers.provision import provision
from backend_v2.workers.sweeper import sweep_once


ROOT = Path(__file__).resolve().parents[1]
MODEL_SHA = "548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734"
PREPROCESSING = "formal-resnet18-baseline-rule-b-v1"
PROTOCOL = "stage1-occlusion-instability-v1"


def _json(response: httpx.Response, expected: int) -> dict:
    if response.status_code != expected:
        raise RuntimeError(f"Backend returned {response.status_code}: {response.text[:300]}")
    return response.json()


def _write_private_token(path: Path | None, token: str) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(token + "\n")


def run(args) -> dict:
    if not os.environ.get("EPILOCATE_V2_DATABASE_URL"):
        raise ValueError("EPILOCATE_V2_DATABASE_URL is required")
    if args.device == "CUDA":
        subprocess.run([str(args.worker_python), "-c",
                        "from worker.device import select_device; select_device('CUDA')"],
                       env={**os.environ, "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1"},
                       check=True, capture_output=True, text=True, timeout=30)
    raw = args.fixture.read_bytes()
    input_hash = hashlib.sha256(raw).hexdigest()
    engine = make_engine()
    with Session(engine) as db:
        with db.begin():
            user = User(auth_subject="p1gpu-smoke-" + uuid.uuid4().hex)
            db.add(user)
            db.flush()
            _, user_token = issue_user_credential(db, user, expires_in=timedelta(hours=1), label="p1gpu-smoke")
            worker_id, worker_token = provision(
                db, model_id="baseline_resnet18", model_hash=MODEL_SHA,
                preprocessing_version=PREPROCESSING, protocol_id=PROTOCOL,
                display_name="P1 GPU Worker smoke",
            )
    headers = {"Authorization": f"Bearer {user_token}"}
    with httpx.Client(base_url=args.backend_url, verify=str(args.ca_cert), trust_env=False, timeout=60) as client:
        case = _json(client.post("/api/v2/cases", json={"patient_id": None},
                                 headers={**headers, "Idempotency-Key": str(uuid.uuid4())}), 201)
        case_id = case["case_id"]
        uploaded = _json(client.post(f"/api/v2/cases/{case_id}/upload",
                                     data={"input_kind": "dicom_series"},
                                     files={"file": ("synthetic.dcm", raw, "application/dicom")},
                                     headers={**headers, "Idempotency-Key": str(uuid.uuid4())}), 201)
        slice_id = uploaded["slice_id"]
        assert client.get(f"/api/v2/cases/{case_id}/dicom", headers=headers).content == raw
        jobs = {}
        for kind in ("PREDICTION", "OCCLUSION"):
            route = "/api/v2/predictions" if kind == "PREDICTION" else "/api/v2/jobs/occlusion"
            body = {"case_id": case_id, "slice_id": slice_id, "model_id": "baseline_resnet18"}
            if kind == "OCCLUSION":
                body.update(protocol_id=PROTOCOL, scales=[16, 32, 64])
            jobs[kind] = _json(client.post(route, json=body,
                                          headers={**headers, "Idempotency-Key": str(uuid.uuid4())}), 202)["job_id"]
        created, _, _ = sweep_once(engine, ObjectStore())
        if created != 2:
            raise RuntimeError(f"Expected two queued jobs, got {created}")
        with tempfile.TemporaryDirectory(prefix="epilocate-p1gpu-worker-") as worker_data:
            worker_script = """import json
from worker.agent import WorkerAgent
from worker.config import WorkerConfig
agent = WorkerAgent(WorkerConfig.from_env())
try:
    agent.register()
    agent.heartbeat_once()
    agent.start_heartbeats()
    responses = [agent.run_once(), agent.run_once()]
    print(json.dumps({'device': agent.runner.hardware['accelerator'],
                      'accepted': [value['accepted'] for value in responses]}))
finally:
    agent.stop()
"""
            worker_env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1",
                          "WORKER_ID": worker_id, "TOKEN": worker_token, "BACKEND_URL": args.backend_url,
                          "MODEL_VERSION": MODEL_SHA, "MODEL_HASH": MODEL_SHA,
                          "EPILOCATE_FROZEN_ROOT": str(args.frozen_root),
                          "WORKER_DATA_ROOT": worker_data, "WORKER_DEVICE": args.device,
                          "WORKER_CA_CERT": str(args.ca_cert),
                          "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"}
            completed = subprocess.run([str(args.worker_python), "-c", worker_script], env=worker_env,
                                       check=True, capture_output=True, text=True, timeout=300)
            worker_result = json.loads(completed.stdout)
        output = {"requested_device": args.device, "actual_device": worker_result["device"],
                  "case_id": case_id, "slice_id": slice_id,
                  "model_hash": MODEL_SHA, "input_sha256": input_hash,
                  "accepted": worker_result["accepted"], "jobs": {}, "position_count_by_scale": {},
                  "asset_count": 0}
        for kind, job_id in jobs.items():
            job = _json(client.get(f"/api/v2/jobs/{job_id}", headers=headers), 200)
            if job["status"] != "COMPLETED":
                raise RuntimeError(f"{kind} job did not complete: {job['status']}")
            result = _json(client.get(f"/api/v2/results/{job['result_id']}", headers=headers), 200)
            if result["source"] != "LIVE_CASE" or result["model_version"] != MODEL_SHA:
                raise RuntimeError("Result provenance mismatch")
            output["jobs"][kind] = {"job_id": job_id, "status": job["status"],
                                    "result_id": job["result_id"],
                                    "positive_probability": result["prediction"]["positive_probability"]}
            for asset in result["assets"]:
                response = client.get(f"/api/v2/results/{job['result_id']}/assets/{asset['asset_id']}", headers=headers)
                if response.status_code != 200 or not response.content.startswith(b"\x89PNG\r\n\x1a\n"):
                    raise RuntimeError("Heatmap asset could not be read")
                output["asset_count"] += 1
            if kind == "OCCLUSION":
                for scale in (16, 32, 64):
                    page = _json(client.get(f"/api/v2/results/{job['result_id']}/positions",
                                            params={"scale": scale, "limit": 1000}, headers=headers), 200)
                    output["position_count_by_scale"][str(scale)] = len(page["positions"])
        if output["asset_count"] != 9 or output["position_count_by_scale"] != {"16": 729, "32": 169, "64": 36}:
            raise RuntimeError("Occlusion assets or positions differ from the synthetic reference")
        _write_private_token(args.user_token_output, user_token)
        _write_private_token(args.worker_token_output, worker_token)
        return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-url", required=True)
    parser.add_argument("--ca-cert", type=Path, required=True)
    parser.add_argument("--worker-python", type=Path, required=True)
    parser.add_argument("--frozen-root", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, default=ROOT / "docs/interfaces/fixtures/p0_synthetic_ct.dcm")
    parser.add_argument("--device", choices=("CPU", "CUDA"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--user-token-output", type=Path,
                        help="Optional private token file for isolated browser QA (mode 0600)")
    parser.add_argument("--worker-token-output", type=Path,
                        help="Optional private token file for isolated auth QA (mode 0600)")
    args = parser.parse_args()
    result = run(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"actual_device": result["actual_device"], "jobs": len(result["jobs"]),
                      "assets": result["asset_count"], "output": str(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
