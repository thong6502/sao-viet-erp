"""Schema nhật ký của một bản ghi danh mục (xem `routers/nhat_ky_danh_muc.py`)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class NhatKyItem(BaseModel):
    at: datetime
    # "Phòng ban · Chức vụ · Tên" (actor_labels). None khi thao tác do hệ thống/seed sinh ra.
    actor_name: str | None = None
    action: str
    # Các thay đổi trong CÙNG một lần lưu, nối bằng " · ": "Đơn giá 27.800 → 29.000 đ/kg · ...".
    detail: str


class NhatKyOut(BaseModel):
    items: list[NhatKyItem]
