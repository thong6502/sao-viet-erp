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
    code: str | None = None
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
    code: str | None = None
    name: str
    username: str
    department_id: int | None = None
    department_name: str | None = None
    role_id: int | None = None
    role_name: str | None = None
    is_active: bool = True
    deleted_at: datetime | None = None


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    username: str = Field(min_length=1, max_length=150)
    department_id: int
    # Tùy chọn: để trống → dùng mật khẩu mặc định (settings.default_user_password).
    password: str | None = Field(default=None, min_length=6, max_length=128)
    # Tùy chọn: gắn chức vụ (vai trò) ngay khi tạo — vai trò phải thuộc phòng ban trên.
    role_id: int | None = None


class UserCreatedOut(UserRow):
    """Response khi tạo tài khoản — kèm mật khẩu ban đầu để admin bàn giao."""

    initial_password: str


class UserUpdate(BaseModel):
    """Admin edit of a user (spec-08 / PBI-2003): name + department. Username is not editable."""

    name: str = Field(min_length=1, max_length=255)
    department_id: int


class SessionOut(BaseModel):
    """A live login session (active refresh token) — read-only in the user detail (spec-08)."""

    id: int
    user_agent: str | None = None
    created_at: datetime
    expires_at: datetime


class ResetPasswordOut(BaseModel):
    """The one-time temporary password returned after an admin reset (spec-08 / PBI-2006)."""

    temporary_password: str


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


class RoleBulkAssignIn(BaseModel):
    """Gán một vai trò cho nhiều người cùng lúc từ màn Phòng ban (bulk)."""

    user_ids: list[int] = Field(min_length=1)
    role_id: int


class RoleAssignResult(BaseModel):
    assigned: int


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
    # Quyền chi tiết (Cách B).
    can_reassign: bool = False
    can_export: bool = False
    can_view_debt: bool = False
    can_view_discount: bool = False
    can_approve: bool = False
    can_manage_status: bool = False
    can_reset_password: bool = False
    can_lock: bool = False
    can_revoke_sessions: bool = False
    can_assign_role: bool = False
    can_transfer: bool = False
    can_set_head: bool = False
    can_requote: bool = False
    can_manage_price: bool = False
    can_cancel: bool = False
    can_manage_permissions: bool = False
    can_clone: bool = False
    can_toggle_active: bool = False
    can_reparent: bool = False
    can_view_salary: bool = False
    can_adjust: bool = False


class PermissionMatrixIn(BaseModel):
    permissions: list[PermissionRow]
