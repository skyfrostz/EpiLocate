from __future__ import annotations

import json
import os
import sqlite3
import time

import httpx
import pytest
from argon2 import PasswordHasher
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from session_gateway.app import COOKIE, Settings, create_app
from session_gateway.store import SessionStore

ORIGIN = "https://demo.example.test"


def private(path, content: bytes):
    path.write_bytes(content)
    os.chmod(path, 0o600)
    return path


@pytest.fixture
def gateway(tmp_path):
    token_a = "backend-token-a-0123456789-0123456789"
    token_b = "backend-token-b-0123456789-0123456789"
    a = private(tmp_path / "a.env", f"export EPILOCATE_USER_TOKEN={token_a}\n".encode())
    b = private(tmp_path / "b.env", f"export EPILOCATE_USER_TOKEN={token_b}\n".encode())
    accounts_path = private(tmp_path / "accounts.json", json.dumps({
        "alice": {"password_hash": PasswordHasher().hash("alice-password-123"), "token_file": str(a), "enabled": True},
        "bob": {"password_hash": PasswordHasher().hash("bob-password-12345"), "token_file": str(b), "enabled": True},
    }).encode())
    key = private(tmp_path / "key", os.urandom(32))
    backend = FastAPI()

    def actor(authorization: str = Header("")):
        if authorization == "Bearer " + token_a:
            return "alice"
        if authorization == "Bearer " + token_b:
            return "bob"
        raise HTTPException(401)

    @backend.get("/api/v2/cases")
    def cases(authorization: str = Header("")):
        return {"items": [{"case_id": "case_" + actor(authorization)}], "next_cursor": None}

    @backend.get("/api/v2/cases/{case_id}")
    def case(case_id: str, authorization: str = Header("")):
        if case_id != "case_" + actor(authorization):
            raise HTTPException(404)
        return {"case_id": case_id}

    @backend.post("/api/v2/cases")
    def create(authorization: str = Header("")):
        return {"owner": actor(authorization)}

    settings = Settings(ORIGIN, "http://127.0.0.1:8890", accounts_path, tmp_path / "sessions.sqlite3", key)
    app = create_app(settings, backend_transport=httpx.ASGITransport(app=backend))
    return app, settings, accounts_path


def login(client, name, password):
    return client.post("/auth/login", json={"username": name, "password": password}, headers={"Origin": ORIGIN})


def test_two_accounts_are_isolated_and_no_browser_bearer(gateway):
    app, _, _ = gateway
    with TestClient(app, base_url=ORIGIN) as alice, TestClient(app, base_url=ORIGIN) as bob:
        assert alice.get("/api/v2/cases").status_code == 401
        a = login(alice, "alice", "alice-password-123")
        b = login(bob, "bob", "bob-password-12345")
        assert a.status_code == b.status_code == 200
        assert "HttpOnly" in a.headers["set-cookie"]
        assert "Secure" in a.headers["set-cookie"]
        assert "SameSite=strict" in a.headers["set-cookie"]
        assert "backend-token" not in a.text + b.text + str(alice.cookies) + str(bob.cookies)
        assert alice.get("/api/v2/cases").json()["items"][0]["case_id"] == "case_alice"
        assert bob.get("/api/v2/cases").json()["items"][0]["case_id"] == "case_bob"
        assert bob.get("/api/v2/cases/case_alice").status_code == 404
        assert alice.get("/api/v2/cases/case_bob").status_code == 404
        assert alice.get("/api/v2/cases", headers={"Authorization": "Bearer " + "x" * 40}).status_code == 200
        assert alice.get("/api/v2/workers/jobs/claim").status_code == 404


def test_csrf_origin_logout_and_revoke(gateway):
    app, settings, _ = gateway
    with TestClient(app, base_url=ORIGIN) as client:
        payload = login(client, "alice", "alice-password-123").json()
        token = payload["csrf_token"]
        assert client.post("/api/v2/cases").status_code == 403
        assert client.post("/api/v2/cases", headers={"Origin": ORIGIN}).status_code == 403
        assert client.post("/api/v2/cases", headers={"Origin": "https://evil.example", "X-CSRF-Token": token}).status_code == 403
        assert client.post("/api/v2/cases", headers={"Origin": ORIGIN, "X-CSRF-Token": token}).json() == {"owner": "alice"}
        assert client.post("/auth/logout", headers={"Origin": ORIGIN, "X-CSRF-Token": token}).status_code == 204
        assert client.get("/auth/session").status_code == 401
        login(client, "alice", "alice-password-123")
        SessionStore(settings.sessions_file).revoke_user("alice")
        assert client.get("/api/v2/cases").status_code == 401


def test_expiry_disabled_account_and_rate_limit(gateway):
    app, settings, accounts_file = gateway
    with TestClient(app, base_url=ORIGIN) as client:
        assert login(client, "alice", "alice-password-123").status_code == 200
        with sqlite3.connect(settings.sessions_file) as db:
            db.execute("UPDATE sessions SET expires_at=?", (int(time.time()) - 1,))
        assert client.get("/auth/session").status_code == 401
        records = json.loads(accounts_file.read_text())
        records["alice"]["enabled"] = False
        private(accounts_file, json.dumps(records).encode())
        assert login(client, "alice", "alice-password-123").status_code == 401
        assert client.get("/api/v2/cases").status_code == 401
    with TestClient(app, base_url=ORIGIN) as other:
        for _ in range(4):
            assert login(other, "bob", "wrong-password").status_code == 401
        assert login(other, "bob", "wrong-password").status_code == 429


def test_invalid_origin_and_secret_permissions(gateway):
    app, settings, _ = gateway
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.post("/auth/login", json={"username": "alice", "password": "alice-password-123"}).status_code == 403
    os.chmod(settings.session_key_file, 0o644)
    with pytest.raises(ValueError, match="owner-only"):
        create_app(settings)
