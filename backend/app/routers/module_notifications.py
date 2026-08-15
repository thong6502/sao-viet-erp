"""Badge thông báo chưa đọc dùng chung cho Thu mua và Kế toán."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from ..deps import (
    CurrentUser,
    get_authorization_service,
    get_module_notification_repository,
)
from ..repositories.module_notification_repo import CHANNELS, ModuleNotificationRepository
from ..schemas.module_notification import ModuleNotificationSummaryOut
from ..services.rbac_service import AuthorizationService


router = APIRouter(prefix="/api/module-notifications", tags=["module-notifications"])
Repo = Annotated[ModuleNotificationRepository, Depends(get_module_notification_repository)]
Authz = Annotated[AuthorizationService, Depends(get_authorization_service)]


@router.get("/summary", response_model=ModuleNotificationSummaryOut)
def summary(repo: Repo, authz: Authz, user: CurrentUser) -> ModuleNotificationSummaryOut:
    counts = repo.unread_counts(user.id)
    # Không rò cả số lượng sự kiện của màn mà người gọi không được xem.
    if not authz.can(user, "thu_mua", "read"):
        counts["thu_mua"] = 0
    if not authz.can(user, "ke_toan", "read"):
        counts["ke_toan"] = 0
    return ModuleNotificationSummaryOut(**counts)


@router.post("/{channel}/mark-read", status_code=status.HTTP_204_NO_CONTENT)
def mark_read(channel: str, repo: Repo, authz: Authz, user: CurrentUser) -> Response:
    if channel not in CHANNELS:
        raise HTTPException(status_code=404, detail="Không tìm thấy kênh thông báo.")
    if not authz.can(user, channel, "read"):
        raise HTTPException(status_code=403, detail="Bạn không có quyền xem màn này.")
    repo.mark_read(user_id=user.id, channel=channel)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
