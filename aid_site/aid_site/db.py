"""Site-local account and session storage only."""

import hashlib
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from argon2 import PasswordHasher, Type

DATABASE_PATH = Path(os.environ.get("AID_DATABASE_PATH", "./data/aid-site.sqlite3"))
PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16, type=Type.ID)
DUMMY_HASH = PASSWORD_HASHER.hash("dummy-password-never-valid")
SESSION_SECONDS = 60 * 60 * 12


@contextmanager
def connection():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATABASE_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
        db.commit()
    finally:
        db.close()


def initialize():
    with connection() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY,
              username TEXT NOT NULL UNIQUE,
              password_hash TEXT NOT NULL,
              created_at INTEGER NOT NULL,
              enabled INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS sessions (
              token_hash TEXT PRIMARY KEY,
              user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              csrf_token TEXT NOT NULL,
              created_at INTEGER NOT NULL,
              expires_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
        """)
    try:
        os.chmod(DATABASE_PATH, 0o600)
    except OSError:
        pass


def create_or_reset_user(username: str, password: str):
    if not username or len(username) > 64 or not all(c.isascii() and (c.isalnum() or c in "._-") for c in username):
        raise ValueError("Username must contain 1-64 ASCII letters, digits, dot, underscore, or hyphen")
    if len(password) < 16:
        raise ValueError("Password must contain at least 16 characters")
    password_hash = PASSWORD_HASHER.hash(password)
    with connection() as db:
        row = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if row:
            db.execute("UPDATE users SET password_hash=?, enabled=1 WHERE id=?", (password_hash, row["id"]))
            db.execute("DELETE FROM sessions WHERE user_id=?", (row["id"],))
        else:
            db.execute("INSERT INTO users(username,password_hash,created_at) VALUES(?,?,?)", (username, password_hash, int(time.time())))


def verify_user(username: str, password: str):
    with connection() as db:
        row = db.execute("SELECT id,username,password_hash FROM users WHERE username=? AND enabled=1", (username,)).fetchone()
    # Keep response cost similar for unknown users.
    check_hash = row["password_hash"] if row else DUMMY_HASH
    try:
        valid = PASSWORD_HASHER.verify(check_hash, password)
    except Exception:
        valid = False
    return row if row and valid else None


def new_session(user_id: int):
    token = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    now = int(time.time())
    with connection() as db:
        db.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
        db.execute("INSERT INTO sessions(token_hash,user_id,csrf_token,created_at,expires_at) VALUES(?,?,?,?,?)",
                   (hashlib.sha256(token.encode()).hexdigest(), user_id, csrf_token, now, now + SESSION_SECONDS))
    return token, csrf_token


def find_session(token: str | None):
    if not token:
        return None
    digest = hashlib.sha256(token.encode()).hexdigest()
    with connection() as db:
        return db.execute("""SELECT s.token_hash,s.csrf_token,s.expires_at,u.id AS user_id,u.username
            FROM sessions s JOIN users u ON u.id=s.user_id
            WHERE s.token_hash=? AND s.expires_at>? AND u.enabled=1""", (digest, int(time.time()))).fetchone()


def delete_session(token: str | None):
    if token:
        with connection() as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))
