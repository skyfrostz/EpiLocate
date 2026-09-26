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
    return create_engine(url, pool_pre_ping=True)


def make_session_factory(engine):
    return sessionmaker(engine, expire_on_commit=False)


def session_dependency() -> Iterator[Session]:
    engine = make_engine()
    with Session(engine) as session:
        yield session
