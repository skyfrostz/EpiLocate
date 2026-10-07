"""Provision a Backend v2 user and write one bearer token to a 0600 file."""
from __future__ import annotations

import argparse
import os
import shlex
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend_v2.auth.credentials import issue_user_credential
from backend_v2.db.base import make_engine
from backend_v2.models.entities import User


def write_user_env(path: Path, token: str):
    if path.exists() or path.is_symlink():
        raise FileExistsError(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(f"export EPILOCATE_USER_TOKEN={shlex.quote(token)}\n")
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision one EpiLocate user bearer credential")
    parser.add_argument("--auth-subject", required=True)
    parser.add_argument("--expires-in-days", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--label", default="user-api")
    parser.add_argument("--role", choices=("USER", "ADMIN"), default="USER")
    args = parser.parse_args()
    if not args.auth_subject or len(args.auth_subject) > 255 or any(char.isspace() for char in args.auth_subject):
        parser.error("auth-subject must be a non-empty value without whitespace")
    if not 0 < args.expires_in_days <= 365:
        parser.error("expires-in-days must be greater than 0 and at most 365")
    engine = make_engine()
    with Session(engine) as db:
        with db.begin():
            user = db.scalar(select(User).where(User.auth_subject == args.auth_subject))
            if user is None:
                user = User(auth_subject=args.auth_subject, role=args.role)
                db.add(user)
                db.flush()
            elif user.role != args.role and args.role != "USER":
                parser.error("existing user role differs; refusing implicit role change")
            if not user.is_active:
                parser.error("user is inactive; refusing to issue a credential")
            credential, token = issue_user_credential(db, user, expires_in=timedelta(days=args.expires_in_days), label=args.label)
            write_user_env(args.output, token)
            print(f"user_id={user.id}")
            print(f"credential_id={credential.id}")
            print(f"auth_subject={user.auth_subject}")
            print(f"token_file={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
