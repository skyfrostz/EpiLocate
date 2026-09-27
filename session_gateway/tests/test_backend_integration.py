"""Browser gateway against the actual Backend v2 auth and ownership paths."""
from __future__ import annotations

import json
import os

import httpx
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from backend_v2.api.app import app as backend_app
from backend_v2.tests.test_auth_security import security_ctx, seed_owned_case
from session_gateway.app import Settings, create_app


def secret(path, data: bytes):
    path.write_bytes(data)
    os.chmod(path, 0o600)
    return path


def test_gateway_preserves_real_backend_ownership(security_ctx, tmp_path):
    factory, store, ids, token_a, token_b, _ = security_ctx
    case_id, _, job_id, result_id, asset_id = seed_owned_case(factory, store, ids)
    a = secret(tmp_path / "a.env", f"export EPILOCATE_USER_TOKEN={token_a}\n".encode())
    b = secret(tmp_path / "b.env", f"export EPILOCATE_USER_TOKEN={token_b}\n".encode())
    accounts = secret(tmp_path / "accounts.json", json.dumps({
        "alice": {"password_hash": PasswordHasher().hash("alice-password-123"), "token_file": str(a), "enabled": True},
        "bob": {"password_hash": PasswordHasher().hash("bob-password-12345"), "token_file": str(b), "enabled": True},
    }).encode())
    key = secret(tmp_path / "key", os.urandom(32))
    origin = "https://demo.example.test"
    app = create_app(Settings(origin, "http://127.0.0.1:8890", accounts, tmp_path / "sessions.db", key),
                     backend_transport=httpx.ASGITransport(app=backend_app))
    with TestClient(app, base_url=origin) as alice, TestClient(app, base_url=origin) as bob:
        for client, name, password in ((alice, "alice", "alice-password-123"), (bob, "bob", "bob-password-12345")):
            assert client.post("/auth/login", json={"username": name, "password": password},
                               headers={"Origin": origin}).status_code == 200
        assert alice.get(f"/api/v2/cases/{case_id}").status_code == 200
        assert alice.get(f"/api/v2/results/{result_id}/assets/{asset_id}").status_code == 200
        for path in (f"/cases/{case_id}", f"/cases/{case_id}/dicom", f"/jobs/{job_id}",
                     f"/results/{result_id}", f"/results/{result_id}/assets/{asset_id}"):
            assert bob.get("/api/v2" + path).status_code == 404
        assert alice.get("/api/v2/cases").json()["items"]
        assert bob.get("/api/v2/cases").json()["items"] == []
