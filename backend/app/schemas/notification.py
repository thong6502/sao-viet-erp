"""Schema — Thông báo (chuông)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, computed_field


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    loai: str
    tieu_de: str
    noi_dung: str | None = None
    link_loai: str | None = None
    link_id: int | None = None
    read_at: datetime | None = None
    created_at: datetime

    @computed_field  # type: ignore[misc]
    @property
    def da_doc(self) -> bool:
        return self.read_at is not None


class NotificationListOut(BaseModel):
    items: list[NotificationOut] = []
    unread: int = 0
