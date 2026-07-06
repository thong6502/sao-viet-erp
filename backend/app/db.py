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

    Spec-01 uses create_all (+ seed) instead of Alembic migrations; migrations
    are an explicit follow-up (see docs/product-specs/spec-01-auth.md).
    """
    # Import models so they register on Base.metadata before create_all.
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_role_permission_columns()


def _ensure_role_permission_columns() -> None:
    """Micro-migration: thêm các cột quyền chi tiết mới vào `role_permissions` nếu thiếu.

    `create_all` KHÔNG ALTER bảng đã tồn tại; hàm này ADD COLUMN cho DB cũ nên KHÔNG cần
    xóa/seed lại (giữ nguyên dữ liệu). Idempotent — chỉ thêm cột còn thiếu.
    """
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if "role_permissions" not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns("role_permissions")}
    default = "0" if engine.dialect.name == "sqlite" else "false"
    for col in (
        "can_reassign",
        "can_export",
        "can_view_debt",
        "can_approve",
        "can_manage_status",
        "can_reset_password",
        "can_lock",
        "can_revoke_sessions",
        "can_assign_role",
        "can_transfer",
        "can_set_head",
        "can_requote",
        "can_manage_price",
        "can_cancel",
        "can_manage_permissions",
        "can_clone",
        "can_toggle_active",
        "can_reparent",
    ):
        if col not in existing:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        f"ALTER TABLE role_permissions "
                        f"ADD COLUMN {col} BOOLEAN NOT NULL DEFAULT {default}"
                    )
                )
