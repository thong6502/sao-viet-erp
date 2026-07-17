"""User ORM model.

Portable across SQLite and Postgres: integer PK, string columns, timezone-aware
timestamp via a DB-agnostic default.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # System-generated ACCOUNT code: "TK" + zero-padded sequence (TK001, TK002, …). Tiền tố
    # "TK" tách khỏi employees.code ("NV###") để không nhầm tài khoản với hồ sơ (Đ1).
    # Read-only, assigned by the repository on create; distinct from the DB primary key `id`.
    # Nullable so legacy rows can be backfilled at startup (migration 0042 đổi NV→TK, giữ số).
    code: Mapped[str | None] = mapped_column(String(20), unique=True, index=True, nullable=True)
    # The sole account identity + login credential (spec-0001): users sign in with this.
    # Email was removed entirely; username is required and unique.
    username: Mapped[str] = mapped_column(
        String(150), unique=True, index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # RBAC (spec-02): a user belongs to one department and holds one role. Both are
    # nullable so a freshly-created account can exist before HR/head assignment.
    department_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("departments.id"), index=True, nullable=True
    )
    role_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("roles.id"), index=True, nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Xóa mềm (spec phân quyền): giữ lại bản ghi cho lịch sử/kiểm toán, ẩn khỏi danh sách,
    # chặn đăng nhập. Null = chưa xóa. Set kèm is_active=False + bump token_version.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Optional profile picture (spec-04). Stores the server-relative path of the
    # uploaded file (e.g. `/static/avatars/<file>`); null means "use the initials
    # fallback". The frontend prefixes it with the API origin to render the <img>.
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Bumping this invalidates every previously-issued access token for the user
    # (logout-all / lock). Access tokens carry the value as a `tv` claim; a token whose
    # `tv` no longer matches this column is rejected (spec-03 hard-revoke).
    token_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
