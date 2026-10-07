"""Offline account provisioning and session revocation for the browser gateway."""
from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import secrets
from pathlib import Path

from argon2 import PasswordHasher

from session_gateway.app import accounts, backend_token
from session_gateway.store import SessionStore


def private_write(path: Path, data: bytes):
    if not path.is_absolute() or path.is_symlink():
        raise ValueError("Secret path must be absolute and not a symlink")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + "." + secrets.token_hex(8) + ".tmp")
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Manage EpiLocate browser accounts and sessions")
    sub = parser.add_subparsers(dest="action", required=True)
    add = sub.add_parser("set-account")
    add.add_argument("--accounts", type=Path, required=True)
    add.add_argument("--sessions", type=Path, required=True)
    add.add_argument("--username", required=True)
    add.add_argument("--token-file", type=Path, required=True)
    disable = sub.add_parser("disable-account")
    disable.add_argument("--accounts", type=Path, required=True)
    disable.add_argument("--sessions", type=Path, required=True)
    disable.add_argument("--username", required=True)
    revoke = sub.add_parser("revoke-sessions")
    revoke.add_argument("--sessions", type=Path, required=True)
    revoke.add_argument("--username", required=True)
    key = sub.add_parser("create-key")
    key.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "create-key":
        if args.output.exists() or args.output.is_symlink():
            parser.error("Key path already exists")
        private_write(args.output, secrets.token_bytes(32))
        print(f"key_file={args.output}")
        return
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,96}", args.username):
        parser.error("Invalid username")
    if args.action == "revoke-sessions":
        SessionStore(args.sessions).revoke_user(args.username)
        print(f"sessions_revoked_for={args.username}")
        return
    records = accounts(args.accounts) if args.accounts.exists() else {}
    if args.action == "disable-account":
        if args.username not in records:
            parser.error("Account not found")
        records[args.username]["enabled"] = False
    else:
        backend_token(str(args.token_file))
        password = getpass.getpass("Browser password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm or len(password) < 12:
            parser.error("Passwords must match and contain at least 12 characters")
        records[args.username] = {"password_hash": PasswordHasher().hash(password),
                                  "token_file": str(args.token_file), "enabled": True}
    private_write(args.accounts, (json.dumps(records, indent=2) + "\n").encode())
    SessionStore(args.sessions).revoke_user(args.username)
    print(f"account_updated={args.username}; previous sessions revoked")


if __name__ == "__main__":
    main()
