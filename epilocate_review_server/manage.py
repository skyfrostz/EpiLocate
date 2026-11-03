from __future__ import annotations

import argparse
from datetime import datetime, timezone
import getpass
from pathlib import Path
import sqlite3

from .app.bundle import ReviewBundle
from .app.config import Settings
from .app.db import Database
from .app.security import hash_password


def init_db(settings: Settings) -> None:
    Database(settings.database_path).initialize()
    print(f"initialized {settings.database_path}")


def create_user(settings: Settings, username: str, role: str) -> None:
    database = Database(settings.database_path)
    database.initialize()
    bundle = ReviewBundle.load(settings.bundle_path, verify_files=True)
    password = getpass.getpass("Password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("passwords do not match")
    user_id = database.create_user(username, hash_password(password), role, bundle)
    print(f"created {role} user {username!r} (id={user_id})")


def snapshot_db(settings: Settings, output: Path) -> None:
    source_path = settings.database_path.resolve()
    output = output.expanduser().resolve()
    if output.exists():
        raise SystemExit(f"refusing to overwrite existing snapshot: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    destination = sqlite3.connect(output)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    print(f"snapshot created: {output}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Manage the EpiLocate review server")
    subcommands = result.add_subparsers(dest="command", required=True)
    subcommands.add_parser("init-db", help="initialize or migrate the SQLite database")
    create = subcommands.add_parser("create-user", help="interactively create an account")
    create.add_argument("username")
    create.add_argument("--role", choices=("reviewer", "admin"), required=True)
    snapshot = subcommands.add_parser("snapshot-db", help="create a consistent manual SQLite snapshot")
    snapshot.add_argument("output", type=Path)
    return result


def main() -> int:
    args = parser().parse_args()
    settings = Settings.from_env()
    if args.command == "init-db":
        init_db(settings)
    elif args.command == "create-user":
        create_user(settings, args.username, args.role)
    elif args.command == "snapshot-db":
        snapshot_db(settings, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
