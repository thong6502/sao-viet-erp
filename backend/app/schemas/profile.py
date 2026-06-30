"""Self-service profile schemas (spec-04): the shapes the /api/users/me routes parse
and return. No business logic here."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class UpdateNameRequest(BaseModel):
    # Display name: required, ≤ 100 chars (spec-04).
    name: str = Field(max_length=100)

    @field_validator("name")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        # Trim first, then reject an empty/whitespace-only name (422).
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Tên hiển thị không được để trống")
        return trimmed


class AvatarOut(BaseModel):
    """Returned after an avatar upload: the new server-relative path the UI renders."""

    avatar_url: str
