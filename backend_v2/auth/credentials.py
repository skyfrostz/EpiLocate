from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend_v2.models.entities import User, UserCredential
from backend_v2.services.common import aware, fail, now


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _valid_token_format(token: str) -> bool:
    return isinstance(token, str) and 32 <= len(token) <= 256 and not any(char.isspace() for char in token)


def issue_user_credential(
    db: Session,
    user: User,
    *,
    expires_in: timedelta,
    label: str = "user-api",
) -> tuple[UserCredential, str]:
    """Create a one-time-visible opaque bearer credential.

    Only the SHA-256 digest is persisted.  The caller is responsible for
    writing the returned token to a protected secret store or file.
    """
    if expires_in <= timedelta(0) or expires_in > timedelta(days=365):
        raise ValueError("credential lifetime must be between 1 second and 365 days")
    if not 1 <= len(label) <= 96:
        raise ValueError("credential label must be between 1 and 96 characters")
    token = secrets.token_urlsafe(48)
    issued = now()
    row = UserCredential(
        user_id=user.id,
        token_hash=token_hash(token),
        label=label,
        issued_at=issued,
        expires_at=issued + expires_in,
    )
    db.add(row)
    db.flush()
    return row, token


def revoke_user_credential(db: Session, credential_id, *, at: datetime | None = None) -> UserCredential:
    row = db.get(UserCredential, credential_id)
    if row is None:
        fail("CREDENTIAL_NOT_FOUND", 404)
    if row.revoked_at is None:
        row.revoked_at = at or now()
    return row


def authenticate_user(db: Session, token: str) -> User:
    """Resolve a DB-backed bearer token without revealing its state."""
    if not _valid_token_format(token):
        fail("UNAUTHENTICATED", 401)
    digest = token_hash(token)
    credential = db.scalar(select(UserCredential).where(UserCredential.token_hash == digest))
    if credential is None or not hmac.compare_digest(credential.token_hash, digest):
        fail("UNAUTHENTICATED", 401)
    user = db.get(User, credential.user_id)
    current = now()
    if user is None or not user.is_active or credential.revoked_at is not None or aware(credential.expires_at) <= current:
        fail("UNAUTHENTICATED", 401)
    return user
