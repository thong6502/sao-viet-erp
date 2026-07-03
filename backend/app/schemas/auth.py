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


class PermissionsOut(BaseModel):
    """Current user's permissions for the frontend: `modules` = readable keys (menu/route
    gating, spec-02); `permissions` = full CRUD matrix per module (action gating, spec-09)."""

    modules: list[str]
    permissions: list[ModuleCapability] = []
