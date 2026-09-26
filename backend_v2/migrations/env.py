from __future__ import annotations

import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from backend_v2.db.base import Base
import backend_v2.models.entities  # noqa: F401

config = context.config
target_metadata = Base.metadata


def url():
    value = os.environ.get("EPILOCATE_V2_DATABASE_URL")
    if not value:
        raise RuntimeError("EPILOCATE_V2_DATABASE_URL is required")
    return value


def run_migrations_offline():
    context.configure(url=url(), target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    section = config.get_section(config.config_ini_section)
    section["sqlalchemy.url"] = url()
    engine = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
