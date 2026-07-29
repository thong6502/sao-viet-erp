"""Pydantic schemas — Máy thiết bị. Create/Update permissive (extra allow → engine field
theo loai_may đi thẳng vào fields_theo_loai/ASSIGNABLE); Row đầy đủ; BHR breakdown."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class MayThietBiIn(BaseModel):
    # Cho phép field phụ (theo loai_may) đi kèm — service/repo lọc theo ASSIGNABLE.
    model_config = ConfigDict(extra="allow")

    ma: str = Field(min_length=1, max_length=30)
    ten: str = Field(min_length=1, max_length=150)
    loai_may: str = Field(min_length=1, max_length=24)
    trang_thai: str = "active"
    khoa_class: str | None = None
    # Khổ + nhíp + units (engine bình bài) — khai rõ để validate chặt.
    kho_max_dai: int | None = None
    kho_max_rong: int | None = None
    kho_min_dai: int | None = None
    kho_min_rong: int | None = None
    kho_kem_dai: int | None = None
    kho_kem_rong: int | None = None
    vung_in_dai: int | None = None
    vung_in_rong: int | None = None
    gripper_mm: int | None = None
    nhip_giay_mm: int | None = None
    le_hong_mm: int | None = None
    duoi_thang_mau_mm: int | None = None
    so_units: int | None = None
    # BHR nguồn — validate ở service.
    nguon_bhr: str | None = None
    don_gia_gio_BHR: float | None = None
    toc_do: float | None = None
    don_vi_toc_do: str | None = None
    fields_theo_loai: dict | None = None


class MayThietBiRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ma: str
    ten: str
    loai_may: str
    finishing_subtype: str | None = None
    nhom_cost_center: str | None = None
    hang_san_xuat: str | None = None
    model: str | None = None
    nha_cung_cap: str | None = None
    trang_thai: str
    active: bool = True
    # BHR inputs (đủ để sửa lại + tính)
    nguon_bhr: str = "dung_tu_von"
    don_gia_gio_BHR: float | None = None
    von_dau_tu: float | None = None
    gia_tri_thu_hoi: float = 0
    nam_khau_hao: int = 8
    lai_von_pct: float | None = None
    gio_lam_nam: int = 2000
    availability_pct: float = 85
    productivity_pct: float = 85
    efficiency_pct: float = 80
    so_nhan_cong: float = 1
    luong_gio: float | None = None
    luong_burden_pct: float = 30
    cong_suat_kW: float | None = None
    he_so_tai_dien: float = 0.65
    don_gia_dien: float | None = None
    bao_hiem_nam: float = 0
    dien_tich_san_m2: float | None = None
    don_gia_thue_m2_nam: float | None = None
    bao_tri_gio: float | None = None
    overhead_gio: float | None = None
    markup_pct: float | None = None
    so_may_song_song: int = 1
    ngay_cap_nhat_bhr: date | None = None
    # Năng lực
    toc_do: float | None = None
    don_vi_toc_do: str | None = None
    makeready_time_default: float | None = None
    thoi_gian_rua_muc: float | None = None
    min_stock_gsm: int | None = None
    max_stock_gsm: int | None = None
    # Engine bình bài (offset)
    kho_max_dai: int | None = None
    kho_max_rong: int | None = None
    kho_min_dai: int | None = None
    kho_min_rong: int | None = None
    kho_kem_dai: int | None = None
    kho_kem_rong: int | None = None
    vung_in_dai: int | None = None
    vung_in_rong: int | None = None
    gripper_mm: int | None = None
    nhip_giay_mm: int | None = None
    le_hong_mm: int | None = None
    duoi_thang_mau_mm: int | None = None
    so_units: int | None = None
    units_truoc: int | None = None
    units_sau: int | None = None
    khoa_class: str | None = None
    co_tro_mat: bool | None = None
    cho_phep_tu_tro: bool | None = None
    cho_phep_tro_dau_duoi: bool | None = None
    bu_hao_canh_may_per_mau: int | None = None
    bu_hao_chay_pct: float | None = None
    ho_tro_cip3: bool | None = None
    fields_theo_loai: dict | None = None
    ghi_chu: str | None = None
    ghi_chu_2: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MayThietBiListOut(BaseModel):
    items: list[MayThietBiRow]
    total: int
    page: int
    size: int


class BhrBreakdownOut(BaseModel):
    gio_tinh_phi: float | None = None
    breakdown: dict
    BHR: float
    don_gia_ban_gio: float
