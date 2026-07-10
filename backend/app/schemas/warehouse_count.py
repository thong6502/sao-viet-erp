"""Pydantic schemas — Đợt kiểm kê (spec-13 C)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CountCreateIn(BaseModel):
    warehouse_id: int
    participants: str | None = None  # người/ban tham gia
    material_group: str | None = None  # phạm vi: chỉ chốt vật tư thuộc nhóm này (tùy chọn)
    note: str | None = None


class CountLineUpdateIn(BaseModel):
    line_id: int | None = None
    material_id: int | None = None
    lot_id: int | None = None
    counted_qty: float | None = None
    defective_qty: float | None = None  # kém phẩm chất (trong số đếm)
    damaged_qty: float | None = None  # mất phẩm chất (trong số đếm)
    note: str | None = None  # lý do chênh lệch


class CountSetIn(BaseModel):
    lines: list[CountLineUpdateIn] = Field(default_factory=list)


class CountLineRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    material_id: int
    lot_id: int | None = None
    system_qty: float
    counted_qty: float | None = None
    defective_qty: float | None = None
    damaged_qty: float | None = None
    unit: str | None = None
    note: str | None = None
    diff: float | None = None  # counted − system (None nếu chưa đếm)


class CountRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    warehouse_id: int
    status: str
    participants: str | None = None
    note: str | None = None
    created_by_user_id: int | None = None
    created_by_name: str | None = None  # resolve ở router (cho biên bản)
    posted_by_user_id: int | None = None
    posted_by_name: str | None = None
    posted_at: datetime | None = None
    created_at: datetime
    lines: list[CountLineRow] = Field(default_factory=list)


class CountListOut(BaseModel):
    items: list[CountRow]
    total: int
    page: int
    size: int
