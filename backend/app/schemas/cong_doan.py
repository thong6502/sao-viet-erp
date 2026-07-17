"""Pydantic schemas — Công đoạn (danh mục)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CongDoanIn(BaseModel):
    ma: str = Field(min_length=1, max_length=30)
    ten: str = Field(min_length=1, max_length=150)
    ten_hien_thi: str | None = None
    kieu_bu_hao: str = "khong"
    bu_hao_id: int | None = None
    so_to_bu_hao: int = Field(default=50, ge=0)
    nhom: str
    may_id: int | None = None
    khoan_ghi_theo: str = "khong"
    allowed_defect_pct: float = Field(default=0, ge=0, le=1)
    allowed_defect_abs: float = Field(default=0, ge=0)
    che_do_tinh: str = "theo_san_luong"
    pricing_basis: str | None = None
    setup_cost: float = Field(default=0, ge=0)
    setup_time: float = Field(default=0, ge=0)
    run_rate: float | None = None
    rate_tiers: list | None = None
    size_tiers: list | None = None
    first_unit_floor: float | None = None
    min_charge: float | None = None
    requires_tooling: bool = False
    tooling_type: str | None = None
    spoilage_pct: float = Field(default=0, ge=0, le=100)
    inline_flag: bool = False
    ghi_chu: str | None = None
    cong_thuc_gia: str | None = None
    active: bool = True


class CongDoanRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ma: str
    ten: str
    ten_hien_thi: str | None = None
    kieu_bu_hao: str = "khong"
    bu_hao_id: int | None = None
    so_to_bu_hao: int = 50
    nhom: str
    may_id: int | None = None
    khoan_ghi_theo: str = "khong"
    allowed_defect_pct: float = 0
    allowed_defect_abs: float = 0
    che_do_tinh: str
    pricing_basis: str | None = None
    setup_cost: float
    setup_time: float
    run_rate: float | None = None
    rate_tiers: list | None = None
    size_tiers: list | None = None
    first_unit_floor: float | None = None
    min_charge: float | None = None
    requires_tooling: bool
    tooling_type: str | None = None
    spoilage_pct: float
    inline_flag: bool
    ghi_chu: str | None = None
    cong_thuc_gia: str | None = None
    active: bool
    updated_at: datetime | None = None


class CongDoanListOut(BaseModel):
    items: list[CongDoanRow]
    total: int
    page: int
    size: int
