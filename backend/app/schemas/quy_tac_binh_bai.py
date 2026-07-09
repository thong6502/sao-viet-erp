"""Pydantic schemas — Quy tắc bình bài (spec §3/§6/§8)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# --- Cấu hình 1 version (dùng lại cho Create/Row/Preview) ------------------
class VersionConfig(BaseModel):
    layout_mode: str = "step_repeat"
    # hình học chung
    side_margin_mm: float = 5
    tail_colorbar_mm: float = 8
    gutter_mm: float = 4
    allow_rotate: bool = True
    grain_constraint: str = "none"
    bleed_default_mm: float = 3
    # step_repeat
    allow_gang: bool = False
    min_gutter_mm: float = 4
    # signature (None = auto)
    pages_per_sig: int | None = None
    work_style: str = "sheetwise"
    # nesting
    matrix_allowance_mm: float = 5
    # guardrails
    min_pages: int | None = None
    max_pages: int | None = None
    min_spine_mm: float | None = None
    warn_on_grain_violation: bool = True


class RuleCreate(BaseModel):
    ma: str = Field(min_length=1, max_length=30)
    ten: str = Field(min_length=1, max_length=150)
    mo_ta: str | None = None
    config: VersionConfig = Field(default_factory=VersionConfig)  # v1


class RuleHeaderUpdate(BaseModel):
    ten: str = Field(min_length=1, max_length=150)
    mo_ta: str | None = None
    trang_thai: str | None = None  # active | inactive


class VersionCreate(BaseModel):
    """Sửa cấu hình = đẻ version mới (§12.6)."""
    config: VersionConfig
    ghi_chu_version: str | None = None


class VersionRow(VersionConfig):
    model_config = ConfigDict(from_attributes=True)
    id: int
    rule_id: int
    version_no: int
    is_current: bool
    ghi_chu_version: str | None = None
    created_at: datetime


class RuleRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ma: str
    ten: str
    mo_ta: str | None = None
    trang_thai: str
    created_at: datetime
    updated_at: datetime | None = None
    current_version: VersionRow | None = None
    version_count: int = 0


class RuleListOut(BaseModel):
    items: list[RuleRow]
    total: int
    page: int
    size: int


class RuleDetailOut(RuleRow):
    versions: list[VersionRow] = []


# --- Bảng thử + preview (§8/§9) -------------------------------------------
class TestBench(BaseModel):
    # con mẫu (Sản phẩm)
    rong_tp: float = 0
    dai_tp: float = 0
    bleed_mm: float | None = None
    so_trang: int | None = None
    binding: str | None = None
    cover_separate: bool = False
    blank_w: float | None = None
    blank_h: float | None = None
    caliper_mm: float | None = None
    # tờ nguyên
    rong_ng: float = 0
    dai_ng: float = 0
    gsm: float = 0
    gia_kg: float = 0
    tho: str = "none"
    # máy in
    gripper_mm: float = 12
    max_w: float = 0
    max_h: float = 0
    min_w: float = 0
    min_h: float = 0
    # số lượng + màu
    so_luong: int = 0
    so_mau_truoc: int = 4
    so_mau_sau: int = 0


class PreviewRequest(BaseModel):
    config: VersionConfig
    bench: TestBench = Field(default_factory=TestBench)


class WarningOut(BaseModel):
    code: str
    message: str
    severity: str


class PrintSheetOut(BaseModel):
    rong: float
    dai: float
    kieu_cat: str
    per_nguyen: int


class PreviewOut(BaseModel):
    layout_mode: str
    kho_to_in: PrintSheetOut | None = None
    don_vi_per_to_in: int
    to_in_per_nguyen: int
    tong_don_vi_per_nguyen: int
    so_kem: int
    hao_hinh_hoc_pct: float
    so_to_in: int | None = None
    so_to_nguyen: int | None = None
    so_tay: int | None = None
    danh_sach_tay: list | None = None
    spine_mm: float | None = None
    creep_mm: float | None = None
    warnings: list[WarningOut] = []
