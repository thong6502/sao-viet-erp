"""Self-service profile routes (spec-04): the current user edits their OWN profile.

No RBAC permission is required — a user always owns their profile; `CurrentUser`
(a valid, unlocked token) is the only gate. Display-name edit + avatar upload/remove.
Avatar files are written under the backend `static/avatars/` dir; only the relative
path is stored in `users.avatar_url`.
"""
from __future__ import annotations

import secrets
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status

from ..deps import CurrentUser, get_profile_service
from ..schemas.auth import UserOut
from ..schemas.profile import AvatarOut, UpdateNameRequest
from ..services.profile_service import ProfileService

router = APIRouter(prefix="/api/users", tags=["profile"])

# Avatar storage: <backend>/static/avatars (served at /static/avatars by main.py).
AVATAR_DIR = Path(__file__).resolve().parents[2] / "static" / "avatars"
AVATAR_URL_PREFIX = "/static/avatars"
MAX_AVATAR_BYTES = 2 * 1024 * 1024  # 2 MB (spec-04)
# Accepted image types -> file extension.
ALLOWED_AVATAR_TYPES = {"image/jpeg": ".jpg", "image/png": ".png"}

Profiles = Annotated[ProfileService, Depends(get_profile_service)]


@router.patch("/me", response_model=UserOut)
def update_my_name(payload: UpdateNameRequest, user: CurrentUser, profiles: Profiles) -> UserOut:
    """Change the current user's display name (spec-04). Schema enforces 1..100 chars."""
    updated = profiles.update_name(user, payload.name)
    return UserOut.model_validate(updated)


@router.post("/me/avatar", response_model=AvatarOut)
async def upload_my_avatar(
    user: CurrentUser,
    profiles: Profiles,
    file: Annotated[UploadFile, File()],
) -> AvatarOut:
    """Upload a new avatar (JPG/PNG ≤ 2 MB). Validates type + size server-side (defense in
    depth — the client checks first), stores the file, and points the user at it."""
    ext = ALLOWED_AVATAR_TYPES.get((file.content_type or "").lower())
    if ext is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ảnh phải là JPG hoặc PNG",
        )
    data = await file.read()
    if len(data) > MAX_AVATAR_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ảnh vượt quá 2 MB",
        )
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tệp ảnh rỗng")

    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"user_{user.id}_{secrets.token_hex(8)}{ext}"
    (AVATAR_DIR / filename).write_bytes(data)

    _remove_avatar_file(user.avatar_url)  # delete the previous file, if any
    avatar_url = f"{AVATAR_URL_PREFIX}/{filename}"
    profiles.set_avatar(user, avatar_url)
    return AvatarOut(avatar_url=avatar_url)


@router.delete("/me/avatar", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def remove_my_avatar(user: CurrentUser, profiles: Profiles) -> Response:
    """Remove the avatar → fall back to initials (spec-04). Idempotent."""
    _remove_avatar_file(user.avatar_url)
    profiles.clear_avatar(user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _remove_avatar_file(avatar_url: str | None) -> None:
    """Delete a previously-stored avatar file (best effort). Only touches files inside our
    avatars dir, identified by the stored URL prefix."""
    if not avatar_url or not avatar_url.startswith(f"{AVATAR_URL_PREFIX}/"):
        return
    name = avatar_url.rsplit("/", 1)[-1]
    target = AVATAR_DIR / name
    try:
        target.unlink(missing_ok=True)
    except OSError:
        pass  # a stale file is harmless; don't fail the request over cleanup
