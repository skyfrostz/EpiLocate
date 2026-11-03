from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException


def now() -> datetime:
    return datetime.now(timezone.utc)


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def public_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(16)}"


def fail(code: str, status: int = 422, message: str | None = None):
    raise HTTPException(status_code=status, detail={"code": code, "message": message or code.replace("_", " ").capitalize(), "retryable": status >= 500, "request_id": str(uuid.uuid4()), "details": {}})


def aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def iso(value: datetime | None) -> str | None:
    return aware(value).isoformat().replace("+00:00", "Z") if value else None


def valid_key(value: str | None):
    if value is None or not 8 <= len(value) <= 128:
        fail("INVALID_IDEMPOTENCY_KEY")
    return value
