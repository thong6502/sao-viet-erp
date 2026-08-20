"""Schema nhãn công đoạn — bản sao của schema nhãn khách hàng (`schemas/customer.py`)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TagIn(BaseModel):
    label: str = Field(min_length=1, max_length=50)


class TagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str


class TagsOut(BaseModel):
    items: list[TagOut]


# --- Kho nhãn dùng chung (thêm / xoá nhãn) -------------------------------------


class KhoNhanRow(BaseModel):
    """Một nhãn trong kho + số BƯỚC đang mang nó (để hỏi kèm số thật trước khi xoá)."""

    id: int
    label: str
    so_buoc: int = 0


class KhoNhanOut(BaseModel):
    items: list[KhoNhanRow]


class KhoNhanXoaOut(BaseModel):
    so_buoc_da_go: int
