from __future__ import annotations

import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from backend_v2.db.base import make_engine

REQUIRED_TABLES = {
    "users", "patients", "cases", "studies", "series", "slices", "inference_jobs",
    "job_attempts", "inference_results", "assets", "worker_nodes", "model_versions", "api_idempotency",
}


def main() -> int:
    database_url = os.environ.get("EPILOCATE_V2_DATABASE_URL")
    if not database_url:
        print("EPILOCATE_V2_DATABASE_URL is required", file=sys.stderr)
        return 2
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    engine = make_engine(database_url)
    with engine.connect() as connection:
        tables = set(inspect(connection).get_table_names())
    missing = REQUIRED_TABLES - tables
    if missing:
        print(f"migration incomplete; missing={sorted(missing)}", file=sys.stderr)
        return 1
    print(f"migration head validated; required_tables={len(REQUIRED_TABLES)}; actual_tables={len(tables)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
