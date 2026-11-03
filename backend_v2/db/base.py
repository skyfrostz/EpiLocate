from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


def make_engine(url: str | None = None):
    url = url or os.environ["EPILOCATE_V2_DATABASE_URL"]
    if not (url.startswith("postgresql+psycopg://") or url.startswith("sqlite://")):
        raise ValueError("Unsupported database URL")
    kwargs = {"pool_pre_ping": True, "future": True}
    if url.startswith("postgresql+"):
        kwargs.update(pool_size=int(os.environ.get("EPILOCATE_V2_DB_POOL_SIZE", "5")), max_overflow=int(os.environ.get("EPILOCATE_V2_DB_MAX_OVERFLOW", "10")), pool_recycle=int(os.environ.get("EPILOCATE_V2_DB_POOL_RECYCLE_SECONDS", "1800")))
    return create_engine(url, **kwargs)


def make_session_factory(engine):
    return sessionmaker(engine, expire_on_commit=False)


def session_dependency() -> Iterator[Session]:
    engine = make_engine()
    with Session(engine) as session:
        yield session
