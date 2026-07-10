"""Pydantic schemas — Danh mục Giấy & Vật tư (chủng loại giấy / giấy / vật tư in ấn)."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


# ---- Phiên bản giá giấy (lịch sử) ----
class GiayGiaVersionIn(BaseModel):
    ngay_hieu_luc: date | None = None
    kho_dai: int = Field(default=0, ge=0)
    kho_rong: int = Field(default=0, ge=0)
    gsm: int | None = None
    caliper_micron: int | None = None
    tho: str | None = None
    don_vi_gia: str = "kg"
    don_gia: float = Field(default=0, ge=0)
    gia_thi_truong: float | None = None
    ghi_chu: str | None = None


class GiayGiaVersionRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    giay_id: int
    version_no: int
    ngay_hieu_luc: date | None = None
    is_current: bool
    kho_dai: int
    kho_rong: int
    gsm: int | None = None
    caliper_micron: int | None = None
    tho: str | None = None
    don_vi_gia: str
    don_gia: float
    gia_thi_truong: float | None = None
    ghi_chu: str | None = None
    created_at: datetime | None = None


# ---- Chủng loại giấy ----
class ChungLoaiGiayIn(BaseModel):
    ma: str = Field(min_length=1, max_length=30)
    ten: str = Field(min_length=1, max_length=150)
    be_mat: str | None = None
    tho_mac_dinh: str | None = None
    mo_ta: str | None = None
    active: bool = True


class ChungLoaiGiayRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ma: str
    ten: str
    be_mat: str | None = None
    tho_mac_dinh: str | None = None
    mo_ta: str | None = None
    active: bool
    updated_at: datetime | None = None


# ---- Giấy ----
class GiayIn(BaseModel):
    ma: str = Field(min_length=1, max_length=30)
    ten: str = Field(min_length=1, max_length=150)
    chung_loai_giay_id: int | None = None
    kho_dai: int = Field(default=0, ge=0)   # 0 = cuộn/khổ mở
    kho_rong: int = Field(default=0, ge=0)  # 0 = cuộn/khổ mở
    gsm: int = Field(gt=0)
    caliper_micron: int | None = None
    tho: str | None = None
    don_vi_gia: str = "kg"
    don_gia: float = Field(default=0, ge=0)
    gia_thi_truong: float | None = None
    kho_tinh_gia: bool = True
    ghi_chu: str | None = None
    active: bool = True


class GiayRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ma: str
    ten: str
    chung_loai_giay_id: int | None = None
    kho_dai: int
    kho_rong: int
    gsm: int
    caliper_micron: int | None = None
    tho: str | None = None
    don_vi_gia: str
    don_gia: float
    gia_thi_truong: float | None = None
    kho_tinh_gia: bool
    ghi_chu: str | None = None
    version_no: int = 1
    active: bool
    updated_at: datetime | None = None


# ---- Vật tư in ấn (phẳng: mã · tên · ĐVT · giá · ghi chú) ----
class VatTuIn(BaseModel):
    ma: str = Field(min_length=1, max_length=30)
    ten: str = Field(min_length=1, max_length=150)
    don_vi_gia: str = "cai"
    don_gia: float = Field(default=0, ge=0)
    ghi_chu: str | None = None
    active: bool = True


class VatTuRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ma: str
    ten: str
    don_vi_gia: str
    don_gia: float
    ghi_chu: str | None = None
    active: bool
    updated_at: datetime | None = None


# ---- Khổ giấy chuẩn (mỗi khổ 1 dòng, cm) ----
class KhoGiayChuanIn(BaseModel):
    ma: str = Field(min_length=1, max_length=30)
    ten: str = Field(min_length=1, max_length=150)
    chung_loai_giay_id: int | None = None
    rong: int = Field(gt=0)
    dai: int | None = Field(default=None, gt=0)
    la_hiem: bool = False
    ghi_chu: str | None = None
    active: bool = True


class KhoGiayChuanRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ma: str
    ten: str
    chung_loai_giay_id: int | None = None
    rong: int
    dai: int | None = None
    la_hiem: bool
    ghi_chu: str | None = None
    active: bool
    updated_at: datetime | None = None


class ListOut(BaseModel):
    items: list
    total: int
    page: int
    size: int
