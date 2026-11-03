"""Verify two real local browser sessions against a running Stage 2 stack.

Inputs point to private local QA credentials. This script prints status codes
only and never prints passwords, Bearer tokens, cookies, or signed asset URLs.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import httpx

from session_gateway.app import COOKIE, backend_token
from session_gateway.store import SessionStore


def require(response: httpx.Response, status: int):
    if response.status_code != status:
        raise AssertionError(f"{response.request.method} {response.request.url.path}: {response.status_code}, wanted {status}")
    return response


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--ca-cert", type=Path, required=True)
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--alice-case", required=True)
    parser.add_argument("--alice-result", required=True)
    parser.add_argument("--bob-case", required=True)
    parser.add_argument("--bob-result", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    private = args.private_dir.resolve()
    passwords = json.loads((private / "passwords.json").read_text())
    tokens = {name: backend_token(str(private / f"{name}.env")) for name in ("alice", "bob")}
    checks = {}
    with httpx.Client(base_url=args.origin, verify=str(args.ca_cert), trust_env=False) as anonymous, \
         httpx.Client(base_url=args.origin, verify=str(args.ca_cert), trust_env=False) as alice, \
         httpx.Client(base_url=args.origin, verify=str(args.ca_cert), trust_env=False) as bob:
        require(anonymous.get("/auth/session"), 401)
        require(anonymous.get("/api/v2/cases"), 401)
        require(anonymous.get(f"/api/v2/results/{args.alice_result}"), 401)
        require(anonymous.get("/api/v2/workers/jobs/claim"), 404)
        checks["anonymous_auth_session_cases_result"] = "401"
        checks["browser_worker_route"] = "404"
        sessions = {}
        for name, client in (("alice", alice), ("bob", bob)):
            login = require(client.post("/auth/login", headers={"Origin": args.origin},
                                        json={"username": name, "password": passwords[name]}), 200)
            cookie = login.headers["set-cookie"].lower()
            assert all(flag in cookie for flag in ("httponly", "secure", "samesite=strict"))
            assert tokens[name] not in login.text
            session = require(client.get("/auth/session"), 200).json()
            assert session["username"] == name and tokens[name] not in json.dumps(session)
            sessions[name] = session
        checks["independent_logins_cookie_flags"] = "200; HttpOnly Secure SameSite=Strict"
        assert require(alice.get(f"/api/v2/cases/{args.alice_case}"), 200).json()["case_id"] == args.alice_case
        assert require(bob.get(f"/api/v2/cases/{args.bob_case}"), 200).json()["case_id"] == args.bob_case
        require(alice.get(f"/api/v2/cases/{args.bob_case}"), 404)
        require(alice.get(f"/api/v2/cases/{args.bob_case}/dicom"), 404)
        require(alice.get(f"/api/v2/results/{args.bob_result}"), 404)
        result = require(alice.get(f"/api/v2/results/{args.alice_result}"), 200).json()
        assert result["source"] == "LIVE_CASE" and len(result["assets"]) == 9
        asset_id = result["assets"][0]["asset_id"]
        assert require(alice.get(f"/api/v2/results/{args.alice_result}/assets/{asset_id}"), 200).content.startswith(b"\x89PNG")
        require(bob.get(f"/api/v2/cases/{args.alice_case}"), 404)
        require(bob.get(f"/api/v2/cases/{args.alice_case}/dicom"), 404)
        require(bob.get(f"/api/v2/results/{args.alice_result}"), 404)
        require(bob.get(f"/api/v2/results/{args.alice_result}/assets/{asset_id}"), 404)
        require(bob.get(f"/api/v2/results/{args.alice_result}/positions?scale=16"), 404)
        require(bob.get(f"/api/v2/results/{args.alice_result}", headers={"Authorization": "Bearer " + tokens["alice"]}), 404)
        checks["alice_owner_case_result_asset"] = "200"
        checks["bob_owner_case"] = "200"
        checks["alice_cross_bob_case_dicom_result"] = "404"
        checks["bob_cross_case_dicom_result_asset_positions_bearer_override"] = "404"
        require(bob.post("/api/v2/cases", headers={"Origin": args.origin}, json={"patient_id": None}), 403)
        checks["missing_csrf"] = "403"
        require(bob.post("/auth/logout", headers={"Origin": args.origin,
                         "X-CSRF-Token": sessions["bob"]["csrf_token"]}), 204)
        require(bob.get("/auth/session"), 401)
        checks["logout"] = "204 then 401"
        raw = alice.cookies.get(COOKIE)
        assert raw
        with sqlite3.connect(private / "sessions" / "sessions.sqlite3") as db:
            db.execute("UPDATE sessions SET expires_at=0 WHERE token_hash=?", (SessionStore.digest(raw),))
            assert db.total_changes == 1
        require(alice.get("/auth/session"), 401)
        checks["forced_session_expiry"] = "401"
        require(bob.post("/auth/login", headers={"Origin": args.origin},
                         json={"username": "bob", "password": passwords["bob"]}), 200)
        SessionStore(private / "sessions" / "sessions.sqlite3").revoke_user("bob")
        require(bob.get("/auth/session"), 401)
        checks["administrative_revocation"] = "401"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(checks, indent=2, sort_keys=True) + "\n")
    print(json.dumps(checks, sort_keys=True))


if __name__ == "__main__":
    main()
