"""Trung tâm thông báo (chuông ở Topbar).

Mọi người dùng đăng nhập đều có hộp thông báo RIÊNG — không gắn quyền module nào. Thông báo được
service nghiệp vụ (vd `stock_request_service`) ghi vào khi có sự kiện; ở đây chỉ đọc + đánh dấu đã đọc.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..deps import CurrentUser, get_db
from ..repositories.notification_repo import NotificationRepository
from ..schemas.notification import NotificationListOut, NotificationOut

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

Db = Annotated[Session, Depends(get_db)]


@router.get("", response_model=NotificationListOut)
def list_notifications(db: Db, user: CurrentUser, limit: int = 30) -> NotificationListOut:
    """Danh sách thông báo của TÔI (mới nhất trước) + số CHƯA ĐỌC cho badge chuông."""
    repo = NotificationRepository(db)
    items = [NotificationOut.model_validate(n) for n in repo.list_for(user.id, limit=limit)]
    return NotificationListOut(items=items, unread=repo.count_unread(user.id))


@router.post("/{notif_id}/read", status_code=204)
def mark_read(notif_id: int, db: Db, user: CurrentUser):
    """Bấm 1 thông báo → đánh dấu đã đọc (chỉ thông báo của chính mình) → badge giảm."""
    NotificationRepository(db).mark_read(notif_id, user.id)


@router.post("/read-all", status_code=204)
def mark_all_read(db: Db, user: CurrentUser):
    """Đánh dấu đã đọc HẾT."""
    NotificationRepository(db).mark_all_read(user.id)
