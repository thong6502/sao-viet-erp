"""Auth schemas — the shapes routes parse and return (no business logic here)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    # Login is by username (spec-0001). min_length=1 rejects a blank submit (422).
    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    name: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class PermissionsOut(BaseModel):
    """Module keys the current user can Read (for frontend menu/route gating)."""

    modules: list[str]
