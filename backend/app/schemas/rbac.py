"""RBAC admin schemas — shapes the role-management routes parse and return."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ModuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    label: str


class DepartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class DepartmentSummaryOut(BaseModel):
    """Department list row: identity + code + tree + head + role/user counts for the screen.

    `role_count`/`user_count` are this department's OWN counts; `total_role_count`/
    `total_user_count` roll the whole branch up (the department + every descendant), so a
    parent unit shows the aggregate of its sub-tree (spec-05 / PBI-4001).
    """

    id: int
    name: str
    code: str
    description: str | None = None
    parent_id: int | None = None
    head_user_id: int | None = None
    head_name: str | None = None
    # Organizational tier (spec-06 / PBI-4009): the level id + its head-title label, so the
    # UI can show e.g. "Trưởng khối" instead of a generic "Người đứng đầu". Null = untagged.
    level_id: int | None = None
    head_title: str | None = None
    role_count: int = 0
    user_count: int = 0
    total_role_count: int = 0
    total_user_count: int = 0


class DepartmentMemberOut(BaseModel):
    """A staff member of a department (PBI-4001 detail): identity + role + status + head flag."""

    id: int
    name: str
    username: str
    role_name: str | None = None
    is_active: bool = True
    is_head: bool = False


class DepartmentCreate(BaseModel):
    # Code is system-generated (spec-05) — never accepted from the client.
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=500)
    parent_id: int | None = None
    # Optional org tier (spec-06 / PBI-4009).
    level_id: int | None = None


class DepartmentUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=500)
    head_user_id: int | None = None
    level_id: int | None = None
    # Re-parent in the org tree (spec-06 / PBI-4007); null = make it a root unit.
    parent_id: int | None = None


class UnitLevelOut(BaseModel):
    """A tier in the org-level catalog (spec-06 / PBI-4009)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    rank: int
    head_title: str


class UnitLevelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    rank: int = Field(ge=1)
    head_title: str = Field(default="", max_length=100)


class UnitLevelUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    rank: int = Field(ge=1)
    head_title: str = Field(default="", max_length=100)


class DepartmentSubtreeRow(BaseModel):
    """A node in a department's delete-preview subtree (spec-05): identity + code."""

    id: int
    name: str
    code: str


class UserBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    username: str


class UserRow(BaseModel):
    """A row in the Users admin table: identity + department + role + status."""

    id: int
    name: str
    username: str
    department_id: int | None = None
    department_name: str | None = None
    role_id: int | None = None
    role_name: str | None = None
    is_active: bool = True


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    username: str = Field(min_length=1, max_length=150)
    department_id: int


class RoleAssign(BaseModel):
    role_id: int | None = None


class ActiveUpdate(BaseModel):
    is_active: bool


class DepartmentTransferIn(BaseModel):
    """Bulk-move personnel to a target department (spec-06 / PBI-4008)."""

    user_ids: list[int] = Field(min_length=1)
    target_department_id: int


class TransferResult(BaseModel):
    transferred: int


class AuditRow(BaseModel):
    """A row in the Activity Log: who did what, to what, when."""

    id: int
    actor_user_id: int | None = None
    actor_name: str | None = None
    action: str
    target: str
    detail: str
    created_at: datetime


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    department_id: int


class RoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    department_id: int


class RoleRename(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class PermissionRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    module_key: str
    can_read: bool = False
    can_create: bool = False
    can_update: bool = False
    can_delete: bool = False
    scope: Literal["own", "department", "all"] = "own"


class PermissionMatrixIn(BaseModel):
    permissions: list[PermissionRow]
