"""Schema cho danh mục tài liệu nội quy."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NoiQuyRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    file_name: str
    file_url: str
    file_type: str
    file_size: int
    note: str | None = None
    uploaded_by_user_id: int
    uploaded_by_name: str
    uploaded_at: datetime


class NoiQuyRecordsOut(BaseModel):
    items: list[NoiQuyRecordOut]
    # Ba ô phân trang THÊM VÀO (09/08/2026), có mặc định nên mọi nơi dựng `NoiQuyRecordsOut(items=…)`
    # kiểu cũ vẫn chạy — thêm trường là tương thích ngược, ĐỔI/BỎ `items` thì không.
    total: int = 0     # tổng bản ghi khớp bộ lọc trên TOÀN BẢNG (không phải số dòng của trang)
    page: int = 1
    size: int = 20
