"""Repository — Thông báo (trung tâm thông báo/chuông).

Chỉ truy vấn/ghi DB. Ai nhận thông báo gì là luật ở service phát sinh sự kiện.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..models.notification import Notification


class NotificationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, *, user_id: int, loai: str, tieu_de: str, noi_dung: str | None = None,
            link_loai: str | None = None, link_id: int | None = None) -> Notification:
        row = Notification(
            user_id=user_id, loai=loai, tieu_de=tieu_de, noi_dung=noi_dung,
            link_loai=link_loai, link_id=link_id,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def add_many(self, user_ids, *, loai: str, tieu_de: str, noi_dung: str | None = None,
                 link_loai: str | None = None, link_id: int | None = None) -> None:
        """Gửi cùng 1 thông báo cho NHIỀU người (vd mọi thủ kho trong phạm vi). 1 commit.

        LUÔN commit, và đó là hợp đồng chứ không phải chi tiết cài đặt: thông báo chỉ được ghi khi
        việc mà nó báo đã chốt xong. Người gọi đang ôm một giao dịch có khoá hàng
        (`SELECT … FOR UPDATE`) thì đừng gọi vào đây giữa chừng — hãy gọi SAU khi commit.
        """
        rows = [
            Notification(user_id=uid, loai=loai, tieu_de=tieu_de, noi_dung=noi_dung,
                         link_loai=link_loai, link_id=link_id)
            for uid in set(user_ids) if uid
        ]
        if not rows:
            return
        self.db.add_all(rows)
        self.db.commit()

    def list_for(self, user_id: int, *, limit: int = 30) -> list[Notification]:
        """Thông báo của user, MỚI NHẤT trước (chưa đọc lẫn đã đọc — FE tự tô)."""
        return list(
            self.db.execute(
                select(Notification)
                .where(Notification.user_id == user_id)
                .order_by(Notification.created_at.desc(), Notification.id.desc())
                .limit(limit)
            ).scalars().all()
        )

    def count_unread(self, user_id: int) -> int:
        stmt = select(func.count()).select_from(Notification).where(
            Notification.user_id == user_id, Notification.read_at.is_(None)
        )
        return int(self.db.execute(stmt).scalar() or 0)

    def mark_read(self, notif_id: int, user_id: int) -> None:
        """Đánh dấu ĐÃ ĐỌC 1 thông báo (chỉ của chính user, và chỉ khi đang chưa đọc)."""
        self.db.execute(
            update(Notification)
            .where(
                Notification.id == notif_id,
                Notification.user_id == user_id,
                Notification.read_at.is_(None),
            )
            .values(read_at=datetime.now(timezone.utc))
        )
        self.db.commit()

    def mark_all_read(self, user_id: int) -> None:
        self.db.execute(
            update(Notification)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
            .values(read_at=datetime.now(timezone.utc))
        )
        self.db.commit()
