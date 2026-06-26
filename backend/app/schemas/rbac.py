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
