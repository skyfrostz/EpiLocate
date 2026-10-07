"""Small persistent store for revocable browser sessions and login throttling."""
from __future__ import annotations

import hashlib
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


class SessionStore:
    def __init__(self, path: Path):
        self.path = path
        if not path.is_absolute() or path.is_symlink():
            raise ValueError("Gateway session database must use an absolute, non-symlink path")
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path.parent.stat().st_mode & 0o077:
            raise ValueError("Gateway session directory must be owner-only")
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        if path.stat().st_mode & 0o077:
            raise ValueError("Gateway session database must be owner-only")
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, username TEXT NOT NULL,
                    expires_at INTEGER NOT NULL, revoked_at INTEGER
                );
                CREATE INDEX IF NOT EXISTS ix_sessions_user ON sessions(username);
                CREATE TABLE IF NOT EXISTS login_attempts (
                    rate_key TEXT NOT NULL, at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_login_attempts ON login_attempts(rate_key, at);
            """)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute("PRAGMA busy_timeout=10000")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def digest(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def create(self, token: str, username: str, expires_at: int):
        with self._connect() as db:
            db.execute("INSERT INTO sessions VALUES (?, ?, ?, NULL)", (self.digest(token), username, expires_at))

    def find(self, token: str) -> str | None:
        with self._connect() as db:
            row = db.execute("SELECT username FROM sessions WHERE token_hash=? AND revoked_at IS NULL AND expires_at>?",
                             (self.digest(token), int(time.time()))).fetchone()
        return row[0] if row else None

    def revoke(self, token: str):
        with self._connect() as db:
            db.execute("UPDATE sessions SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL",
                       (int(time.time()), self.digest(token)))

    def revoke_user(self, username: str):
        with self._connect() as db:
            db.execute("UPDATE sessions SET revoked_at=? WHERE username=? AND revoked_at IS NULL",
                       (int(time.time()), username))

    def allow_login(self, ip: str, username: str, *, now: int | None = None) -> bool:
        """Bound failed guesses by both source IP and account, across processes."""
        at = int(time.time()) if now is None else now
        keys = ("ip:" + self.digest(ip), "user:" + self.digest(username))
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM login_attempts WHERE at <= ?", (at - 600,))
            for key in keys:
                count = db.execute("SELECT COUNT(*) FROM login_attempts WHERE rate_key=? AND at>?", (key, at - 600)).fetchone()[0]
                if count >= 5:
                    return False
            for key in keys:
                db.execute("INSERT INTO login_attempts VALUES (?, ?)", (key, at))
        return True

    def clear_login(self, ip: str, username: str):
        keys = ("ip:" + self.digest(ip), "user:" + self.digest(username))
        with self._connect() as db:
            db.execute("DELETE FROM login_attempts WHERE rate_key IN (?, ?)", keys)
