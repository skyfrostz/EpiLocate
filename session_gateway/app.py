"""Same-origin browser session gateway; Backend v2 remains the authority."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import shlex
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse, Response

from session_gateway.store import SessionStore

COOKIE = "__Host-epilocate_demo"
SESSION_SECONDS = 8 * 3600
MAX_REQUEST_BYTES = 21 * 1024 * 1024
USER_API = re.compile(r"^(cases|predictions|jobs|results)(?:/|$)")
HASHER = PasswordHasher()


@dataclass(frozen=True)
class Settings:
    public_origin: str
    backend_origin: str
    accounts_file: Path
    sessions_file: Path
    session_key_file: Path

    @classmethod
    def from_env(cls):
        return cls(
            os.environ["EPILOCATE_GATEWAY_PUBLIC_ORIGIN"],
            os.environ["EPILOCATE_GATEWAY_BACKEND_ORIGIN"],
            Path(os.environ["EPILOCATE_GATEWAY_ACCOUNTS_FILE"]),
            Path(os.environ["EPILOCATE_GATEWAY_SESSIONS_FILE"]),
            Path(os.environ["EPILOCATE_GATEWAY_SESSION_KEY_FILE"]),
        )

    def validate(self):
        public = urlsplit(self.public_origin)
        backend = urlsplit(self.backend_origin)
        if (public.scheme != "https" or not public.hostname or public.path or public.query or public.fragment
                or public.username or public.password):
            raise ValueError("Gateway public origin must be a bare HTTPS origin")
        if (backend.scheme != "http" or backend.hostname not in {"127.0.0.1", "localhost"}
                or not backend.port or backend.path or backend.query or backend.fragment):
            raise ValueError("Gateway Backend origin must be a loopback HTTP origin")


def private_bytes(path: Path) -> bytes:
    if not path.is_absolute() or path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError("Gateway secret file must be an absolute, owner-only regular file")
    return path.read_bytes()


def accounts(path: Path) -> dict:
    raw = json.loads(private_bytes(path))
    if not isinstance(raw, dict):
        raise ValueError("Gateway accounts file must be an object")
    return raw


def backend_token(path: str) -> str:
    """Read the existing provision_user output without executing its shell text."""
    lines = private_bytes(Path(path)).decode().splitlines()
    if len(lines) != 1:
        raise ValueError("Expected one Backend user credential export")
    words = shlex.split(lines[0])
    if len(words) != 2 or words[0] != "export" or not words[1].startswith("EPILOCATE_USER_TOKEN="):
        raise ValueError("Invalid Backend user credential file")
    token = words[1].split("=", 1)[1]
    if not 32 <= len(token) <= 256 or any(char.isspace() for char in token):
        raise ValueError("Invalid Backend user credential")
    return token


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=96)
    password: str = Field(min_length=1, max_length=1024)


def create_app(settings: Settings | None = None, *, backend_transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.validate()
    key = private_bytes(settings.session_key_file)
    if len(key) < 32:
        raise ValueError("Gateway session key must contain at least 32 random bytes")
    accounts(settings.accounts_file)
    store = SessionStore(settings.sessions_file)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    def csrf(raw: str) -> str:
        return hmac.new(key, ("csrf:" + raw).encode(), hashlib.sha256).hexdigest()

    def error(code: str, status: int):
        raise HTTPException(status, detail={"code": code})

    def same_origin(request: Request):
        if request.headers.get("origin") != settings.public_origin:
            error("ORIGIN_REJECTED", 403)

    def member(request: Request) -> tuple[str, str, str]:
        raw = request.cookies.get(COOKIE, "")
        if not 32 <= len(raw) <= 256:
            error("UNAUTHENTICATED", 401)
        username = store.find(raw)
        record = accounts(settings.accounts_file).get(username) if username else None
        if not isinstance(record, dict) or record.get("enabled") is not True:
            error("UNAUTHENTICATED", 401)
        try:
            token = backend_token(record["token_file"])
        except (KeyError, TypeError, ValueError):
            error("ACCOUNT_UNAVAILABLE", 503)
        return username, raw, token

    def check_csrf(request: Request, raw: str):
        same_origin(request)
        supplied = request.headers.get("x-csrf-token", "")
        if not hmac.compare_digest(supplied, csrf(raw)):
            error("CSRF_REJECTED", 403)

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException):
        return JSONResponse(exc.detail, status_code=exc.status_code, headers={"Cache-Control": "no-store"})

    @app.middleware("http")
    async def no_store(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.post("/auth/login")
    async def login(body: LoginBody, request: Request):
        same_origin(request)
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,96}", body.username):
            error("INVALID_CREDENTIALS", 401)
        ip = request.client.host if request.client else "unknown"
        if ip in {"127.0.0.1", "::1"} and request.headers.get("x-real-ip"):
            ip = request.headers["x-real-ip"]
        if not store.allow_login(ip, body.username):
            error("LOGIN_RATE_LIMITED", 429)
        record = accounts(settings.accounts_file).get(body.username)
        if not isinstance(record, dict) or record.get("enabled") is not True:
            error("INVALID_CREDENTIALS", 401)
        try:
            HASHER.verify(record["password_hash"], body.password)
        except (KeyError, TypeError, VerifyMismatchError, VerificationError):
            error("INVALID_CREDENTIALS", 401)
        try:
            token = backend_token(record["token_file"])
        except (KeyError, TypeError, ValueError):
            error("ACCOUNT_UNAVAILABLE", 503)
        try:
            async with httpx.AsyncClient(base_url=settings.backend_origin, transport=backend_transport,
                                         trust_env=False, follow_redirects=False, timeout=10) as client:
                probe = await client.get("/api/v2/cases?limit=1", headers={"Authorization": "Bearer " + token})
        except httpx.RequestError:
            error("BACKEND_UNAVAILABLE", 503)
        if probe.status_code != 200:
            error("ACCOUNT_UNAVAILABLE", 503)
        store.clear_login(ip, body.username)
        previous = request.cookies.get(COOKIE)
        if previous:
            store.revoke(previous)
        raw = secrets.token_urlsafe(48)
        store.create(raw, body.username, int(time.time()) + SESSION_SECONDS)
        response = JSONResponse({"username": body.username, "csrf_token": csrf(raw)})
        response.set_cookie(COOKIE, raw, max_age=SESSION_SECONDS, secure=True, httponly=True,
                            samesite="strict", path="/")
        return response

    @app.get("/auth/session")
    async def session(request: Request):
        username, raw, _ = member(request)
        return {"username": username, "csrf_token": csrf(raw)}

    @app.post("/auth/logout")
    async def logout(request: Request):
        _, raw, _ = member(request)
        check_csrf(request, raw)
        store.revoke(raw)
        response = Response(status_code=204)
        response.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="strict")
        return response

    @app.api_route("/api/v2/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def proxy(path: str, request: Request):
        if not USER_API.match(path) or "//" in path or ".." in path or request.method not in {"GET", "POST"}:
            error("NOT_FOUND", 404)
        _, raw, token = member(request)
        if request.method != "GET":
            check_csrf(request, raw)
        length = request.headers.get("content-length")
        if length and (not length.isdigit() or int(length) > MAX_REQUEST_BYTES):
            error("REQUEST_TOO_LARGE", 413)
        body = await request.body()
        if len(body) > MAX_REQUEST_BYTES:
            error("REQUEST_TOO_LARGE", 413)
        headers = {"Authorization": "Bearer " + token, "Accept": request.headers.get("accept", "application/json")}
        for name in ("content-type", "idempotency-key"):
            if name in request.headers:
                headers[name] = request.headers[name]
        try:
            async with httpx.AsyncClient(base_url=settings.backend_origin, transport=backend_transport,
                                         trust_env=False, follow_redirects=False, timeout=60) as client:
                upstream = await client.request(request.method, "/api/v2/" + path,
                    params=request.query_params, content=body, headers=headers)
        except httpx.RequestError:
            error("BACKEND_UNAVAILABLE", 503)
        outgoing = {"Content-Type": upstream.headers.get("content-type", "application/octet-stream")}
        return Response(content=upstream.content, status_code=upstream.status_code, headers=outgoing)

    return app
