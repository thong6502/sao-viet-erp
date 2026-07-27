"""Self-service profile routes (spec-04): the current user edits their OWN profile.

No RBAC permission is required — a user always owns their profile; `CurrentUser`
(a valid, unlocked token) is the only gate. Display-name edit + avatar upload/remove.
Avatar bytes go through the shared file store (`app/storage.py`); only the served path
is stored in `users.avatar_url`.
"""
from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status

from ..deps import CurrentUser, get_profile_service
from ..schemas.auth import UserOut
from ..schemas.profile import AvatarOut, UpdateNameRequest
from ..services.profile_service import ProfileError, ProfileService
from ..storage import get_storage, key_from_url, url_from_key

router = APIRouter(prefix="/api/users", tags=["profile"])

# Avatar nằm trong kho file dùng chung; đọc lại qua /api/files (cần đăng nhập).
AVATAR_SUBDIR = "avatars"
MAX_AVATAR_BYTES = 2 * 1024 * 1024  # 2 MB (spec-04)
# Accepted image types -> file extension.
ALLOWED_AVATAR_TYPES = {"image/jpeg": ".jpg", "image/png": ".png"}

Profiles = Annotated[ProfileService, Depends(get_profile_service)]


@router.patch("/me", response_model=UserOut)
def update_my_name(payload: UpdateNameRequest, user: CurrentUser, profiles: Profiles) -> UserOut:
    """Change the current user's display name (spec-04). Schema enforces 1..100 chars.
    Chặn nếu user có hồ sơ nhân sự (tên do hồ sơ quyết — Đ1)."""
    try:
        updated = profiles.update_name(user, payload.name)
    except ProfileError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
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

    key = f"{AVATAR_SUBDIR}/user_{user.id}_{secrets.token_hex(8)}{ext}"
    get_storage().save(key, data, file.content_type)

    _remove_avatar_file(user.avatar_url)  # delete the previous file, if any
    avatar_url = url_from_key(key)
    profiles.set_avatar(user, avatar_url)
    return AvatarOut(avatar_url=avatar_url)


@router.delete("/me/avatar", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def remove_my_avatar(user: CurrentUser, profiles: Profiles) -> Response:
    """Remove the avatar → fall back to initials (spec-04). Idempotent."""
    _remove_avatar_file(user.avatar_url)
    profiles.clear_avatar(user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _remove_avatar_file(avatar_url: str | None) -> None:
    """Delete a previously-stored avatar file (best effort). Only touches keys inside our
    avatars prefix, so a hand-edited `avatar_url` can't point the delete elsewhere."""
    key = key_from_url(avatar_url)
    if not key or not key.startswith(f"{AVATAR_SUBDIR}/"):
        return
    get_storage().delete(key)  # best effort — a stale file must not fail the request
