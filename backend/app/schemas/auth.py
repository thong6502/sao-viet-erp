"""Auth schemas — the shapes routes parse and return (no business logic here)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoginRequest(BaseModel):
    # Login is by username (spec-0001). min_length=1 rejects a blank submit (422).
    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    name: str
    avatar_url: str | None = None


class ProfileOut(UserOut):
    """Read-only profile for the account panel (spec-04): the lean UserOut enriched with
    the resolved department/role names and the account creation date."""

    department_name: str | None = None
    role_name: str | None = None
    created_at: datetime


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    # New password strength (spec-04): ≥ 8 chars with at least one letter and one digit.
    new_password: str = Field(min_length=8, max_length=256)

    @field_validator("new_password")
    @classmethod
    def _strength(cls, v: str) -> str:
        if not any(c.isalpha() for c in v) or not any(c.isdigit() for c in v):
            raise ValueError("Mật khẩu mới phải gồm cả chữ và số")
        return v


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ModuleCapability(BaseModel):
    """The current user's CRUD flags on one module (spec-09 — frontend action gating)."""

    module_key: str
    can_read: bool = False
    can_create: bool = False
    can_update: bool = False
    can_delete: bool = False
    # Data scope (own|department|all) — dùng để bật/tắt hành động phạm-vi-rộng ở UI
    # (vd nút/checkbox "Điều chuyển khách hàng" chỉ hiện với scope department/all).
    scope: str = "own"
    # Quyền chi tiết (Cách B) — hành động đặc thù ngoài CRUD.
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
    can_edit_salary: bool = False
    can_adjust: bool = False
    can_approve_exception: bool = False   # A2: don_hang_ban — GĐ duyệt "đơn đặc thù"


class PermissionsOut(BaseModel):
    """Current user's permissions for the frontend: `modules` = readable keys (menu/route
    gating, spec-02); `permissions` = full CRUD matrix per module (action gating, spec-09)."""

    modules: list[str]
    permissions: list[ModuleCapability] = []
