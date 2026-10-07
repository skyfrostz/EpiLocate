"""Check real-stack authorization for a completed synthetic Worker result.

Reads temporary credentials; the JSON evidence contains no bearer tokens.
"""
from __future__ import annotations

import argparse
import json
import os
import uuid
from datetime import timedelta
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend_v2.auth.credentials import issue_user_credential
from backend_v2.db.base import make_engine
from backend_v2.models.entities import Asset, Case, InferenceResult, User
from backend_v2.services.common import now


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-url", required=True)
    parser.add_argument("--ca-cert", type=Path, required=True)
    parser.add_argument("--e2e-record", type=Path, required=True)
    parser.add_argument("--user-token-file", type=Path, required=True)
    parser.add_argument("--worker-token-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    record = json.loads(args.e2e_record.read_text(encoding="utf-8"))
    token_a = args.user_token_file.read_text(encoding="utf-8").strip()
    worker_token = args.worker_token_file.read_text(encoding="utf-8").strip()
    engine = make_engine(os.environ["EPILOCATE_V2_DATABASE_URL"])
    with Session(engine) as db:
        case = db.scalar(select(Case).where(Case.anonymous_id == record["case_id"]))
        if case is None:
            raise AssertionError("Synthetic case missing")
        result_id = record["jobs"]["OCCLUSION"]["result_id"]
        result = db.get(InferenceResult, uuid.UUID(result_id.removeprefix("result_")))
        if result is None:
            raise AssertionError("Completed occlusion result missing")
        asset = db.scalar(select(Asset).where(Asset.result_id == result.id))
        if asset is None:
            raise AssertionError("Heatmap asset missing")
        asset_id = asset.asset_id
        owner = db.get(User, case.owner_user_id)
        if owner is None:
            raise AssertionError("Case owner missing")
        with db.begin_nested():
            other = User(auth_subject="p135-cross-user-" + uuid.uuid4().hex)
            db.add(other)
            db.flush()
            _, token_b = issue_user_credential(db, other, expires_in=timedelta(hours=1), label="p135-cross-user")
            expired, expired_token = issue_user_credential(db, owner, expires_in=timedelta(hours=1), label="p135-expired")
            expired.expires_at = now() - timedelta(seconds=1)
            revoked, revoked_token = issue_user_credential(db, owner, expires_in=timedelta(hours=1), label="p135-revoked")
            revoked.revoked_at = now()
        db.commit()
    user_a = {"Authorization": f"Bearer {token_a}"}
    user_b = {"Authorization": f"Bearer {token_b}"}
    worker = {"Authorization": f"Bearer {worker_token}", "X-Request-ID": str(uuid.uuid4())}
    job_id = record["jobs"]["OCCLUSION"]["job_id"]
    prediction_job_id = record["jobs"]["PREDICTION"]["job_id"]
    routes = {
        "case": f"/api/v2/cases/{record['case_id']}",
        "dicom": f"/api/v2/cases/{record['case_id']}/dicom",
        "job": f"/api/v2/jobs/{job_id}",
        "prediction_alias": f"/api/v2/predictions/{prediction_job_id}",
        "result": f"/api/v2/results/{result_id}",
        "positions": f"/api/v2/results/{result_id}/positions?scale=16",
        "asset": f"/api/v2/results/{result_id}/assets/{asset_id}",
    }
    checks: list[dict] = []
    with httpx.Client(base_url=args.backend_url, verify=str(args.ca_cert), trust_env=False, timeout=30) as client:
        def check(name: str, response: httpx.Response, status: int, error: str | None = None) -> None:
            code = response.json().get("code") if response.status_code >= 400 and "json" in response.headers.get("content-type", "") else None
            checks.append({"name": name, "status": response.status_code, "code": code})
            if response.status_code != status or (error is not None and code != error):
                raise AssertionError(f"{name}: {response.status_code}/{code}, expected {status}/{error}")

        for name, path in routes.items():
            check("owner_" + name, client.get(path, headers=user_a), 200)
            check("other_" + name, client.get(path, headers=user_b), 404)
            check("anonymous_" + name, client.get(path), 401, "UNAUTHENTICATED")
        for name, token in (("invalid", "invalid-token-0123456789"), ("expired", expired_token), ("revoked", revoked_token)):
            check(name + "_credential", client.get("/api/v2/cases", headers={"Authorization": f"Bearer {token}"}), 401, "UNAUTHENTICATED")
        check("worker_credential_on_user_route", client.get("/api/v2/cases", headers=worker), 401, "UNAUTHENTICATED")
        check("user_credential_on_worker_route", client.post("/api/v2/workers/heartbeat", headers={**user_a, "X-Request-ID": str(uuid.uuid4())}, json={"worker_id": "node_invalid", "activity_state": "IDLE", "active_attempt": None}), 401, "WORKER_UNAUTHENTICATED")
        check("other_user_prediction_create", client.post("/api/v2/predictions", headers={**user_b, "Idempotency-Key": str(uuid.uuid4())}, json={"case_id": record["case_id"], "slice_id": record["slice_id"], "model_id": "baseline_resnet18"}), 404)
    payload = {"case_id": record["case_id"], "result_id": result_id, "passed": len(checks), "checks": checks}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(f"real-stack authorization checks passed: {len(checks)}")


if __name__ == "__main__":
    main()
