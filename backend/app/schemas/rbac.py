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
    """Department list row: identity + code + tree + head + role/user counts for the screen."""

    id: int
    name: str
    code: str
    description: str | None = None
    parent_id: int | None = None
    head_user_id: int | None = None
    head_name: str | None = None
    role_count: int = 0
    user_count: int = 0


class DepartmentCreate(BaseModel):
    # Code is system-generated (spec-05) — never accepted from the client.
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=500)
    parent_id: int | None = None


class DepartmentUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=500)
    head_user_id: int | None = None


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
