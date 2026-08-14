"""Data access cho badge thông báo chưa đọc theo màn."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.module_notification import ModuleNotification, ModuleNotificationRead


CHANNEL_THU_MUA = "thu_mua"
CHANNEL_KE_TOAN = "ke_toan"
CHANNELS = (CHANNEL_THU_MUA, CHANNEL_KE_TOAN)


class ModuleNotificationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        channel: str,
        event_type: str,
        actor_user_id: int | None,
        recipient_user_id: int | None = None,
        source_code: str | None = None,
    ) -> ModuleNotification:
        if channel not in CHANNELS:
            raise ValueError("Kênh thông báo không hợp lệ.")
        row = ModuleNotification(
            channel=channel,
            event_type=event_type,
            actor_user_id=actor_user_id,
            recipient_user_id=recipient_user_id,
            source_code=(source_code or "").strip() or None,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def unread_counts(self, user_id: int) -> dict[str, int]:
        out = {channel: 0 for channel in CHANNELS}
        for channel in CHANNELS:
            read = self.db.execute(
                select(ModuleNotificationRead).where(
                    ModuleNotificationRead.user_id == user_id,
                    ModuleNotificationRead.channel == channel,
                )
            ).scalar_one_or_none()
            last_id = read.last_read_notification_id if read is not None else 0
            out[channel] = int(
                self.db.execute(
                    select(func.count())
                    .select_from(ModuleNotification)
                    .where(
                        ModuleNotification.channel == channel,
                        ModuleNotification.id > last_id,
                        # Người vừa thao tác không nhận badge do chính mình tạo.
                        (ModuleNotification.actor_user_id.is_(None))
                        | (ModuleNotification.actor_user_id != user_id),
                        (ModuleNotification.recipient_user_id.is_(None))
                        | (ModuleNotification.recipient_user_id == user_id),
                    )
                ).scalar_one()
            )
        return out

    def mark_read(self, *, user_id: int, channel: str) -> None:
        if channel not in CHANNELS:
            raise ValueError("Kênh thông báo không hợp lệ.")
        latest_id = self.db.execute(
            select(func.max(ModuleNotification.id)).where(ModuleNotification.channel == channel)
        ).scalar_one()
        row = self.db.execute(
            select(ModuleNotificationRead).where(
                ModuleNotificationRead.user_id == user_id,
                ModuleNotificationRead.channel == channel,
            )
        ).scalar_one_or_none()
        if row is None:
            row = ModuleNotificationRead(
                user_id=user_id,
                channel=channel,
                last_read_notification_id=int(latest_id or 0),
            )
            self.db.add(row)
        else:
            row.last_read_notification_id = int(latest_id or 0)
        self.db.commit()
