"""RBAC admin schemas — shapes the role-management routes parse and return."""
from __future__ import annotations

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
    """Department list row: identity + head + role/user counts for the screen."""

    id: int
    name: str
    head_user_id: int | None = None
    head_name: str | None = None
    role_count: int = 0
    user_count: int = 0


class DepartmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class DepartmentUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    head_user_id: int | None = None


class UserBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str


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
