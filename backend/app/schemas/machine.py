"""Pydantic schemas for the Machines API — Máy móc & Đơn giá giờ máy (full spec A–G)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MachineGroup = Literal["may_in", "may_can", "may_be", "may_xen", "khac"]
MachineStatus = Literal["active", "inactive", "maintenance"]
RoundingPolicy = Literal["none", "0.01", "0.25", "0.5"]


class MachineRateCreate(BaseModel):
    hourly_rate: int = Field(ge=0)
    min_charge: int = Field(default=0, ge=0)
    min_run_time_mins: int = Field(default=0, ge=0)
    # Cấu thành tham khảo (đ/giờ) — engine chỉ dùng tổng hourly_rate.
    rate_depreciation: int = Field(default=0, ge=0)
    rate_energy: int = Field(default=0, ge=0)
    rate_maintenance: int = Field(default=0, ge=0)
    rate_labor: int = Field(default=0, ge=0)
    rate_overhead: int = Field(default=0, ge=0)
    effective_from: date


class MachineRateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hourly_rate: int
    min_charge: int
    min_run_time_mins: int
    rate_depreciation: int = 0
    rate_energy: int = 0
    rate_maintenance: int = 0
    rate_labor: int = 0
    rate_overhead: int = 0
    effective_from: date
    effective_to: date | None
    created_at: datetime


# Shared machine spec fields (create/update carry them; code is server-managed).
class _MachineFields(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    machine_type: str = Field(min_length=1, max_length=32)
    process_type: str = Field(min_length=1, max_length=32)
    machine_group: MachineGroup = "may_in"
    status: MachineStatus = "active"
    note: str | None = Field(default=None, max_length=2000)

    speed: float = Field(gt=0)
    speed_unit: str = Field(min_length=1, max_length=32)
    min_speed: float | None = Field(default=None, ge=0)
    max_speed: float | None = Field(default=None, ge=0)

    # B — khổ giấy (nuốt) vs khổ in (vùng in) + bình bản
    max_width_cm: float | None = Field(default=None, ge=0)
    max_height_cm: float | None = Field(default=None, ge=0)
    min_width_cm: float | None = Field(default=None, ge=0)
    min_height_cm: float | None = Field(default=None, ge=0)
    max_print_width_cm: float | None = Field(default=None, ge=0)
    max_print_height_cm: float | None = Field(default=None, ge=0)
    gripper_cm: float = Field(default=0.0, ge=0)
    side_margin_cm: float = Field(default=0.0, ge=0)
    top_bottom_margin_cm: float = Field(default=0.0, ge=0)
    compatible_paper_size_ids: list[int] | None = None

    # D — thời gian (giờ). Cũ (phút) giữ để fallback.
    setup_time_mins: int = Field(default=0, ge=0)
    changeover_time_mins: int = Field(default=0, ge=0)
    setup_waste_sheets: float = Field(default=0.0, ge=0)
    setup_time_base_hour: float = Field(default=0.0, ge=0)
    setup_time_per_color_hour: float = Field(default=0.0, ge=0)
    setup_time_per_side_hour: float = Field(default=0.0, ge=0)
    cleaning_time_hour: float = Field(default=0.0, ge=0)
    color_change_time_hour: float = Field(default=0.0, ge=0)
    plate_change_time_per_plate_hour: float = Field(default=0.0, ge=0)
    color_check_time_hour: float = Field(default=0.0, ge=0)
    min_setup_time_hour: float = Field(default=0.0, ge=0)
    max_setup_time_hour: float | None = Field(default=None, ge=0)

    # E — chính sách giá giờ
    rounding_hour_policy: RoundingPolicy = "none"
    overhead_included: bool = True
    operator_included: bool = True

    num_ink_units: int | None = Field(default=None, ge=1)
    supports_perfecting: bool = False
    supported_materials: list[str] | None = Field(default=None)
    is_active: bool = True


class MachineCreate(_MachineFields):
    # Mã máy ngữ nghĩa do người dùng nhập (OFFSET_102_01…); để trống ⇒ tự sinh MY###.
    code: str | None = Field(default=None, max_length=20)


class MachineUpdate(_MachineFields):
    """Same as create; code is read-only and is not sent."""


class MachineRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    machine_type: str
    process_type: str
    machine_group: str
    status: str
    note: str | None = None
    speed: float
    speed_unit: str
    min_speed: float | None = None
    max_speed: float | None = None
    max_width_cm: float | None = None
    max_height_cm: float | None = None
    min_width_cm: float | None = None
    min_height_cm: float | None = None
    max_print_width_cm: float | None = None
    max_print_height_cm: float | None = None
    gripper_cm: float = 0.0
    side_margin_cm: float = 0.0
    top_bottom_margin_cm: float = 0.0
    compatible_paper_size_ids: list[int] | None = None
    setup_time_mins: int = 0
    changeover_time_mins: int = 0
    setup_waste_sheets: float = 0.0
    setup_time_base_hour: float = 0.0
    setup_time_per_color_hour: float = 0.0
    setup_time_per_side_hour: float = 0.0
    cleaning_time_hour: float = 0.0
    color_change_time_hour: float = 0.0
    plate_change_time_per_plate_hour: float = 0.0
    color_check_time_hour: float = 0.0
    min_setup_time_hour: float = 0.0
    max_setup_time_hour: float | None = None
    rounding_hour_policy: str = "none"
    overhead_included: bool = True
    operator_included: bool = True
    num_ink_units: int | None = None
    supports_perfecting: bool = False
    supported_materials: list[str] | None = None
    used_count: int = 0
    created_by: int | None = None
    updated_by: int | None = None
    is_active: bool
    rates: list[MachineRateOut] = Field(default_factory=list)


class MachineListOut(BaseModel):
    items: list[MachineRow]
    total: int
    page: int
    size: int


class MachineDetailOut(MachineRow):
    created_at: datetime
    updated_at: datetime
