"""Pydantic models for the Chấm công GPS API (module `nhan_su`)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# --- work locations ---------------------------------------------------------


class WorkLocationIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius_m: int = Field(default=100, gt=0, le=100000)
    note: str | None = Field(default=None, max_length=500)
    is_active: bool = True


class WorkLocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    latitude: float
    longitude: float
    radius_m: int
    is_active: bool
    note: str | None = None
    created_at: datetime | None = None


class WorkLocationsOut(BaseModel):
    items: list[WorkLocationOut]


# --- attendance logs --------------------------------------------------------


class AttendanceLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    employee_name: str | None = None       # filled by the router (HR table)
    work_location_id: int | None = None
    location_name: str | None = None        # filled by the router
    check_type: str
    checked_at: datetime
    latitude: float | None = None
    longitude: float | None = None
    distance_m: float | None = None
    within_range: bool = True
    note: str | None = None


class AttendanceLogsOut(BaseModel):
    items: list[AttendanceLogOut]


# --- self check-in ----------------------------------------------------------


class CheckIn(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class NearestLocationOut(BaseModel):
    id: int
    name: str
    radius_m: int


class CheckResultOut(BaseModel):
    success: bool
    within_range: bool
    check_type: str | None = None
    distance_m: float | None = None
    nearest_location: NearestLocationOut | None = None
    message: str
    log: AttendanceLogOut | None = None


class MyStatusOut(BaseModel):
    has_employee: bool
    employee_name: str | None = None
    next_action: str | None = None          # "in" | "out"
    last_check: AttendanceLogOut | None = None
    locations_configured: bool = False


# --- bảng công tháng --------------------------------------------------------


class TimesheetDay(BaseModel):
    first_in: str | None = None    # "HH:MM"
    last_out: str | None = None
    hours: float | None = None
    present: bool = True


class TimesheetRow(BaseModel):
    employee_id: int
    employee_code: str
    employee_name: str
    department_id: int | None = None
    department_name: str | None = None
    days: dict[str, TimesheetDay]  # keyed by day-of-month ("1".."31")
    total_days: int
    total_hours: float


class TimesheetOut(BaseModel):
    year: int
    month: int
    days_in_month: int
    rows: list[TimesheetRow]
