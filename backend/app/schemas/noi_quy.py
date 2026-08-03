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
