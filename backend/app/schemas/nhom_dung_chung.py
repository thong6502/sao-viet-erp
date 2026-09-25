"""Schema vào/ra của Nhóm dùng chung (khối Kinh doanh)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ThanhVienOut(BaseModel):
    user_id: int
    ho_ten: str
    username: str


class NhomOut(BaseModel):
    id: int
    ten: str
    thanh_viens: list[ThanhVienOut] = Field(default_factory=list)
    created_at: datetime | None = None


class NhomCreate(BaseModel):
    ten: str = Field(min_length=1, max_length=255)
    user_ids: list[int] = Field(default_factory=list)


class NhomUpdate(BaseModel):
    """`user_ids` gửi lên là THAY TOÀN BỘ danh sách thành viên, không phải thêm dồn.

    Bỏ trống (None) = không đụng tới thành viên, chỉ đổi tên.
    """
    ten: str | None = Field(default=None, min_length=1, max_length=255)
    user_ids: list[int] | None = None
