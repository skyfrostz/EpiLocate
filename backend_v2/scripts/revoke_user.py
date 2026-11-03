"""Revoke one Backend v2 user credential."""
from __future__ import annotations

import argparse
import uuid

from sqlalchemy.orm import Session

from backend_v2.auth.credentials import revoke_user_credential
from backend_v2.db.base import make_engine


def main() -> int:
    parser = argparse.ArgumentParser(description="Revoke an EpiLocate user bearer credential")
    parser.add_argument("--credential-id", required=True)
    args = parser.parse_args()
    try:
        credential_id = uuid.UUID(args.credential_id)
    except ValueError:
        parser.error("credential-id must be a UUID")
    with Session(make_engine()) as db:
        with db.begin():
            row = revoke_user_credential(db, credential_id)
            print(f"revoked_credential_id={row.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
