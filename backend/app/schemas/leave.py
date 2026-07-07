"""Pydantic models for the Nghỉ phép API (module `nhan_su`)."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


# --- leave types ------------------------------------------------------------


class LeaveTypeIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    is_paid: bool = True
    annual_quota: int = Field(default=0, ge=0, le=365)
    note: str | None = Field(default=None, max_length=500)
    is_active: bool = True


class LeaveTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    is_paid: bool
    annual_quota: int
    is_active: bool
    note: str | None = None


class LeaveTypesOut(BaseModel):
    items: list[LeaveTypeOut]


# --- requests ---------------------------------------------------------------


class LeaveRequestIn(BaseModel):
    leave_type_id: int
    start_date: date
    end_date: date
    reason: str | None = Field(default=None, max_length=500)


class LeaveDecisionIn(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class LeaveRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    employee_name: str | None = None       # filled by the router
    leave_type_id: int | None = None
    leave_type_name: str | None = None      # filled by the router
    is_paid: bool | None = None             # filled by the router
    start_date: date
    end_date: date
    days: int
    reason: str | None = None
    status: str
    decided_by: int | None = None
    decided_at: datetime | None = None
    decision_note: str | None = None
    created_at: datetime | None = None


class LeaveRequestsOut(BaseModel):
    items: list[LeaveRequestOut]


class LeaveQuotaOut(BaseModel):
    leave_type_id: int
    name: str
    annual_quota: int
    used: int          # ngày làm việc đã dùng + đang chờ (năm dương lịch)
    remaining: int


class MyLeaveOut(BaseModel):
    has_employee: bool
    employee_name: str | None = None
    items: list[LeaveRequestOut]
    quotas: list[LeaveQuotaOut] = []


class LeaveBulkIn(BaseModel):
    ids: list[int] = Field(min_length=1)


class LeaveBulkRejectIn(BaseModel):
    ids: list[int] = Field(min_length=1)
    note: str = Field(min_length=1, max_length=500)


class LeaveBulkResultOut(BaseModel):
    done: list[int]
    skipped: list[int]


class LeaveSummaryOut(BaseModel):
    # Số đơn CHỜ DUYỆT trong scope người gọi (nuôi badge sidebar). None nếu người gọi
    # KHÔNG có quyền duyệt → client ẩn badge (chống lộ số cho người không phận sự).
    pending_in_scope: int | None = None
    # Số đơn CỦA TÔI vừa được quyết (duyệt/từ chối) mà tôi chưa xem → chuông Topbar (mọi NV).
    my_decided_unseen: int = 0


# --- lịch nghỉ (toàn công ty) -----------------------------------------------


class LeaveCalendarDayOut(BaseModel):
    status: str
    leave_type_name: str
    is_paid: bool


class LeaveCalendarEmpOut(BaseModel):
    employee_id: int
    employee_name: str
    days: dict[str, LeaveCalendarDayOut]   # "12" → ô ngày 12


class LeaveCalendarOut(BaseModel):
    year: int
    month: int
    days_in_month: int
    employees: list[LeaveCalendarEmpOut]
