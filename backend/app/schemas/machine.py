"""Pydantic schemas for the Machines API — spec-20/21.
"""
from __future__ import annotations

from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field

class MachineRateCreate(BaseModel):
    hourly_rate: int = Field(ge=0)
    min_charge: int = Field(default=0, ge=0)
    min_run_time_mins: int = Field(default=0, ge=0)
    effective_from: date

class MachineRateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hourly_rate: int
    min_charge: int
    min_run_time_mins: int
    effective_from: date
    effective_to: date | None
    created_at: datetime

class MachineCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    # offset, digital, large_format, flexo...
    machine_type: str = Field(min_length=1, max_length=32)
    # in, can_mang, be, gap...
    process_type: str = Field(min_length=1, max_length=32)
    
    speed: float = Field(gt=0)
    speed_unit: str = Field(min_length=1, max_length=32)
    
    max_width_cm: float | None = Field(default=None, ge=0)
    max_height_cm: float | None = Field(default=None, ge=0)
    min_width_cm: float | None = Field(default=None, ge=0)
    min_height_cm: float | None = Field(default=None, ge=0)
    
    setup_time_mins: int = Field(default=0, ge=0)
    changeover_time_mins: int = Field(default=0, ge=0)
    setup_waste_sheets: float = Field(default=0.0, ge=0)

    # #2 số đơn vị màu của máy · #11 in được 2 mặt 1 lượt (trở nhật/lật)
    num_ink_units: int | None = Field(default=None, ge=1)
    supports_perfecting: bool = False

    supported_materials: list[str] | None = Field(default=None)
    is_active: bool = True

class MachineUpdate(MachineCreate):
    """Same as create; code is read-only and is not sent."""

class MachineRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    machine_type: str
    process_type: str
    # List phải trả đủ thông số: (1) bảng hiển thị khổ máy, (2) form Sửa prefill đúng — nếu thiếu,
    # Sửa máy (chỉ đổi tên) sẽ ghi đè null/0 = MẤT khổ máy, thời gian setup, chất liệu hỗ trợ.
    max_width_cm: float | None = None
    max_height_cm: float | None = None
    min_width_cm: float | None = None
    min_height_cm: float | None = None
    speed: float
    speed_unit: str
    setup_time_mins: int = 0
    changeover_time_mins: int = 0
    setup_waste_sheets: float = 0.0
    num_ink_units: int | None = None
    supports_perfecting: bool = False
    supported_materials: list[str] | None = None
    is_active: bool
    rates: list[MachineRateOut] = Field(default_factory=list)

class MachineListOut(BaseModel):
    items: list[MachineRow]
    total: int
    page: int
    size: int

class MachineDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    machine_type: str
    process_type: str
    speed: float
    speed_unit: str
    max_width_cm: float | None
    max_height_cm: float | None
    min_width_cm: float | None
    min_height_cm: float | None
    setup_time_mins: int
    changeover_time_mins: int
    setup_waste_sheets: float
    num_ink_units: int | None
    supports_perfecting: bool
    supported_materials: list[str] | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    rates: list[MachineRateOut] = Field(default_factory=list)
