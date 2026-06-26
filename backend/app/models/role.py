"""Role + RolePermission ORM models.

A Role is a named permission bundle that belongs to exactly ONE department
(vai trò riêng cho từng phòng); a user holds exactly one role. Each Role carries
one RolePermission row per module: the CRUD flags (được làm gì) plus the data
`scope` (được thấy dữ liệu của ai).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# Allowed data-scope values for a RolePermission.scope.
SCOPE_OWN = "own"
SCOPE_DEPARTMENT = "department"
SCOPE_ALL = "all"
SCOPES = (SCOPE_OWN, SCOPE_DEPARTMENT, SCOPE_ALL)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("name", "department_id", name="uq_roles_name_department"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    department_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("departments.id"), index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "module_key", name="uq_role_permissions_role_module"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("roles.id"), index=True, nullable=False
    )
    module_key: Mapped[str] = mapped_column(
        String(64), ForeignKey("modules.key"), nullable=False
    )
    can_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_create: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_update: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_delete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False, default=SCOPE_OWN)
