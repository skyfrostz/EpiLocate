"""Run the P1 Phase 2.5 HTTP authorization matrix against an isolated QA stack.

Credentials are read from operator-owned 0600 files and never written to output.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import uuid
from datetime import timedelta
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend_v2.auth.credentials import issue_user_credential
from backend_v2.db.base import make_engine
from backend_v2.models.entities import Asset, Case, InferenceJob, InferenceResult, User
from backend_v2.services.common import now


def read_env_value(path: Path, key: str) -> str:
    for line in path.read_text().splitlines():
        if line.startswith(f"export {key}="):
            return shlex.split(line.split("=", 1)[1])[0]
    raise ValueError(f"{key} missing from {path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--user-a-file", type=Path, required=True)
    parser.add_argument("--user-b-file", type=Path, required=True)
    parser.add_argument("--worker-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not os.environ.get("EPILOCATE_V2_DATABASE_URL"):
        parser.error("EPILOCATE_V2_DATABASE_URL required")
    token_a = read_env_value(args.user_a_file, "EPILOCATE_USER_TOKEN")
    token_b = read_env_value(args.user_b_file, "EPILOCATE_USER_TOKEN")
    worker_token = read_env_value(args.worker_file, "TOKEN")
    worker_id = read_env_value(args.worker_file, "WORKER_ID")
    engine = make_engine()
    with Session(engine) as db:
        user_a = db.scalar(select(User).where(User.auth_subject == "browser-user-a"))
        user_b = db.scalar(select(User).where(User.auth_subject == "browser-user-b"))
        if not user_a or not user_b or user_a.id == user_b.id:
            raise AssertionError("two distinct QA users required")
        case = db.scalar(select(Case).where(Case.owner_user_id == user_a.id, Case.anonymous_id == "case_88a44291469a56b8deaba7d7032bacf5"))
        if not case:
            raise AssertionError("expected User A's completed synthetic Case")
        jobs = db.scalars(select(InferenceJob).where(InferenceJob.case_id == case.id, InferenceJob.status == "COMPLETED")).all()
        if {job.kind for job in jobs} != {"PREDICTION", "OCCLUSION"}:
            raise AssertionError("expected completed prediction and occlusion")
        occ_job = next(job for job in jobs if job.kind == "OCCLUSION")
        pred_job = next(job for job in jobs if job.kind == "PREDICTION")
        result = db.scalar(select(InferenceResult).where(InferenceResult.job_id == occ_job.id))
        asset = db.scalar(select(Asset).where(Asset.result_id == result.id)) if result else None
        if not asset:
            raise AssertionError("expected heatmap asset")
        ids = {"case_id": case.anonymous_id, "job_id": occ_job.public_id, "prediction_job_id": pred_job.public_id,
               "result_id": f"result_{result.id.hex}", "asset_id": asset.asset_id,
               "user_a_id": str(user_a.id), "user_b_id": str(user_b.id)}
        with db.begin_nested():
            expired_row, expired_token = issue_user_credential(db, user_a, expires_in=timedelta(hours=1), label="qa-expired")
            expired_row.expires_at = now() - timedelta(seconds=1)
            revoked_row, revoked_token = issue_user_credential(db, user_a, expires_in=timedelta(hours=1), label="qa-revoked")
            revoked_row.revoked_at = now()
        db.commit()

    ua = {"Authorization": f"Bearer {token_a}"}
    ub = {"Authorization": f"Bearer {token_b}"}
    wk = {"Authorization": f"Bearer {worker_token}", "X-Request-ID": str(uuid.uuid4())}
    paths = {
        "case_detail": f"/api/v2/cases/{ids['case_id']}",
        "dicom_content": f"/api/v2/cases/{ids['case_id']}/dicom",
        "job_status": f"/api/v2/jobs/{ids['job_id']}",
        "prediction_alias": f"/api/v2/predictions/{ids['prediction_job_id']}",
        "result_detail": f"/api/v2/results/{ids['result_id']}",
        "positions": f"/api/v2/results/{ids['result_id']}/positions?scale=16",
        "heatmap_asset": f"/api/v2/results/{ids['result_id']}/assets/{ids['asset_id']}",
    }
    rows = []
    with httpx.Client(base_url=args.base_url, trust_env=False, timeout=30) as client:
        def record(name: str, response: httpx.Response, status: int, code: str | None = None) -> None:
            actual_code = response.json().get("code") if response.headers.get("content-type", "").startswith("application/json") and response.status_code >= 400 else None
            rows.append({"test": name, "status": response.status_code, "code": actual_code})
            if response.status_code != status or (code is not None and actual_code != code):
                raise AssertionError(f"{name}: got {response.status_code}/{actual_code}, expected {status}/{code}")

        for name, path in paths.items():
            record(f"owner_{name}", client.get(path, headers=ua), 200)
            record(f"cross_user_{name}", client.get(path, headers=ub), 404)
            record(f"missing_{name}", client.get(path), 401, "UNAUTHENTICATED")
        record("valid_token_list", client.get("/api/v2/cases", headers=ua), 200)
        for name, token in (("invalid", "invalid-credential-0123456789"), ("expired", expired_token), ("revoked", revoked_token)):
            record(f"{name}_token", client.get("/api/v2/cases", headers={"Authorization": f"Bearer {token}"}), 401, "UNAUTHENTICATED")
        with Session(engine) as db:
            user = db.get(User, uuid.UUID(ids["user_a_id"]))
            user.is_active = False
            db.commit()
        try:
            record("disabled_user", client.get("/api/v2/cases", headers=ua), 401, "UNAUTHENTICATED")
        finally:
            with Session(engine) as db:
                user = db.get(User, uuid.UUID(ids["user_a_id"]))
                user.is_active = True
                db.commit()
        body = {"worker_id": worker_id, "activity_state": "IDLE", "active_attempt": None}
        record("user_to_worker", client.post("/api/v2/workers/heartbeat", headers={**ua, "X-Request-ID": str(uuid.uuid4())}, json=body), 401, "WORKER_UNAUTHENTICATED")
        record("worker_to_user", client.get("/api/v2/cases", headers=wk), 401, "UNAUTHENTICATED")
        record("cross_user_prediction_create", client.post("/api/v2/predictions", headers={**ub, "Idempotency-Key": str(uuid.uuid4())}, json={"case_id": ids["case_id"], "slice_id": "slice_67377204d574101d1df55cc3c829e969", "model_id": "baseline_resnet18"}), 404)
    payload = {"ids": ids, "checks": rows, "passed": len(rows)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"security HTTP matrix passed: {len(rows)} checks; output={args.output}")


if __name__ == "__main__":
    main()
