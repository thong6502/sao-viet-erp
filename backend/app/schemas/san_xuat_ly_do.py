"""Pydantic schemas — Danh mục "Lý do & lỗi SX" (bảng `san_xuat_ly_do`, §15).

Cùng hình dạng với 11 màn danh mục kia (In · Row · ListOut + `facets`), nên `make_catalog_router`
dùng được không cần vá gì.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SanXuatLyDoIn(BaseModel):
    """Thân POST/PUT. `ma` bỏ trống ⇒ server cấp `LD-####` (màn không có ô Mã lúc tạo).

    `nhom` là khoá phân loại dùng-vào-việc-gì; ô chọn ở FE lọc theo cột này. Service kiểm giá trị
    thuộc `NHOM_LY_DO` — KHÔNG enum cứng ở đây để câu báo lỗi tiếng Việt đi qua một cửa.
    """

    ma: str | None = Field(default=None, max_length=30)
    nhom: str = Field(min_length=1, max_length=24)
    ten: str = Field(min_length=1, max_length=150)
    mo_ta: str | None = Field(default=None, max_length=500)
    thu_tu: int = Field(default=0, ge=0)
    active: bool = True


class SanXuatLyDoRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ma: str
    nhom: str
    ten: str
    mo_ta: str | None = None
    thu_tu: int
    active: bool


class SanXuatLyDoListOut(BaseModel):
    items: list[SanXuatLyDoRow]
    total: int
    page: int
    size: int
    #: Số dòng theo TỪNG nhóm — nuôi số trên tab lọc (màn chỉ cầm một trang, không tự đếm được).
    facets: dict[str, int] = {}
