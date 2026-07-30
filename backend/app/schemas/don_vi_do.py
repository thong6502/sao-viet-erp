"""Pydantic schemas — Danh mục Đơn vị đo & quy đổi."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class DonViDoIn(BaseModel):
    ma: str = Field(min_length=1, max_length=24)
    ten: str = Field(min_length=1, max_length=60)
    # Họ gõ TỰ DO (gợi ý ở `GET /api/don-vi/ho`) — chỉ đơn vị cùng họ đổi được cho nhau.
    ho: str = Field(default="khac", max_length=24)
    he_so_goc: float = Field(default=1, gt=0)
    hieu_luc_tu: date | None = None
    ghi_chu: str | None = Field(default=None, max_length=500)
    active: bool = True


class DonViDoRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ma: str
    ten: str
    ho: str
    he_so_goc: float
    hieu_luc_tu: date | None = None
    ghi_chu: str | None = None
    active: bool
    updated_at: datetime | None = None
    # Cảnh báo mềm (hệ số lệch chuẩn · họ chưa có đơn vị gốc) — hiện ở màn khai, không chặn lưu.
    canh_bao: list[str] = Field(default_factory=list)


class DonViDoListOut(BaseModel):
    items: list[DonViDoRow]
    total: int
    page: int
    size: int


class HoListOut(BaseModel):
    """Gợi ý cho ô "Họ" — KHÔNG phải whitelist, gõ họ mới vẫn lưu được."""

    items: list[str]


class QuyDoiIn(BaseModel):
    """Thử một phép đổi (dùng cho ô xem trước ở màn khai + kiểm tra tay)."""

    gia_tri: float = 0
    tu: str = Field(min_length=1, max_length=24)
    den: str = Field(min_length=1, max_length=24)
    # Quy cách lệnh khi đổi qua họ khác: kho_in_dai · kho_in_rong (mm) · gsm · so_con · so_to_per_sp.
    quy_cach: dict | None = None


class QuyDoiOut(BaseModel):
    gia_tri: float | None = None
    don_vi: str | None = None
    dien_giai: str | None = None
    thieu: list[str] = Field(default_factory=list)
    ly_do: str | None = None
