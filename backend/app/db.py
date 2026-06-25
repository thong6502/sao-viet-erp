"""Database engine + session wiring (the ONLY module that builds the engine).

Repositories receive a Session and own all SQL; services/routes never touch the
engine directly. SQL stays portable across SQLite (local/test) and Postgres
(Docker/prod) — see docs/ARCHITECTURE.md.
"""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import settings


def _make_engine():
    url = settings.database_url
    connect_args: dict = {}
    engine_kwargs: dict = {}

    if url.startswith("sqlite"):
        # SQLite needs this to be used across FastAPI's threadpool.
        connect_args["check_same_thread"] = False
        if ":memory:" in url:
            # Keep a single shared connection so an in-memory DB (tests) survives
            # across requests/threads.
            engine_kwargs["poolclass"] = StaticPool

    return create_engine(url, connect_args=connect_args, **engine_kwargs)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


def get_db() -> Iterator[Session]:
    """FastAPI dependency: yield a request-scoped session, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables for models registered on Base.

    Sprint-01 uses create_all (+ seed) instead of Alembic migrations; migrations
    are an explicit follow-up (see docs/product-specs/sprint-01-auth.md).
    """
    # Import models so they register on Base.metadata before create_all.
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
