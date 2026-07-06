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


class MyLeaveOut(BaseModel):
    has_employee: bool
    employee_name: str | None = None
    items: list[LeaveRequestOut]
