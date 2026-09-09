"""Pydantic schemas — Danh mục HẠNG MỤC KIỂM KCS (mg `0285`: thuộc ĐÚNG MỘT công đoạn).

Màn khai báo đi ba tầng Giai đoạn → Công đoạn → hạng mục, nên ngoài CRUD phẳng còn một hình
dạng ĐỌC gom nhóm (`KcsKhaiBaoOut`) để màn không phải tự ghép từ hai lời gọi.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SanXuatKcsTieuChiIn(BaseModel):
    # `ma` sinh ngầm ở service (tiền tố `KM`) — người khai chỉ gõ câu chữ hạng mục.
    ma: str | None = None
    cong_doan_id: int
    ten: str = Field(min_length=1, max_length=200)
    huong_dan: str | None = None
    bat_buoc: bool = True
    thu_tu: int = 0
    active: bool = True


class SanXuatKcsTieuChiRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ma: str
    cong_doan_id: int
    ten: str
    huong_dan: str | None = None
    bat_buoc: bool
    thu_tu: int
    active: bool
    updated_at: datetime | None = None


class SanXuatKcsTieuChiListOut(BaseModel):
    items: list[SanXuatKcsTieuChiRow]
    total: int
    page: int
    size: int


# --- Hình dạng ĐỌC ba tầng cho màn khai báo ---------------------------------------------------

class KcsKhaiBaoCongDoanOut(BaseModel):
    """Một CÔNG ĐOẠN có khai hạng mục kiểm, kèm trọn danh sách hạng mục của nó."""
    cong_doan_id: int
    ma: str
    ten: str
    hang_muc: list[SanXuatKcsTieuChiRow]


class KcsKhaiBaoGiaiDoanOut(BaseModel):
    """Một GIAI ĐOẠN (`cong_doan.nhom`) — tầng ngoài cùng của màn khai báo."""
    nhom: str
    cong_doan: list[KcsKhaiBaoCongDoanOut]


class KcsKhaiBaoOut(BaseModel):
    giai_doan: list[KcsKhaiBaoGiaiDoanOut]
