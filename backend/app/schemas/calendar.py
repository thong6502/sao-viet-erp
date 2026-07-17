"""Pydantic models cho API Lịch làm việc & Ngày lễ (module `nhan_su`, Pha 1)."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


# --- cấu hình tuần làm việc --------------------------------------------------


class ConfigIn(BaseModel):
    """PUT một phần: chỉ gửi các thứ muốn đổi (None = giữ nguyên)."""
    works_mon: bool | None = None
    works_tue: bool | None = None
    works_wed: bool | None = None
    works_thu: bool | None = None
    works_fri: bool | None = None
    works_sat: bool | None = None
    works_sun: bool | None = None


class ConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    works_mon: bool
    works_tue: bool
    works_wed: bool
    works_thu: bool
    works_fri: bool
    works_sat: bool
    works_sun: bool
    updated_at: datetime


# --- ngày đặc biệt (lễ / làm bù) --------------------------------------------


class SpecialDayIn(BaseModel):
    day: date
    kind: str = Field(default="off")  # 'off' | 'work' (service validate)
    name: str = Field(min_length=1, max_length=200)
    is_paid: bool = True
    note: str | None = Field(default=None, max_length=500)


class SpecialDayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    day: date
    kind: str
    name: str
    is_paid: bool
    note: str | None = None


class SpecialDaysOut(BaseModel):
    year: int
    items: list[SpecialDayOut]
    paid_off_count: int          # số ngày nghỉ lễ hưởng lương đã khai trong năm
    statutory_paid: int          # mức luật (11) — FE cảnh báo nếu paid_off_count < mức này


# --- lịch tháng (xem trước) --------------------------------------------------


class DayCell(BaseModel):
    day: int
    date: date
    weekday: int                 # Mon=0..Sun=6
    kind: str                    # work | weekend | holiday | makeup
    name: str | None = None
    is_working: bool


class HolidayItem(BaseModel):
    date: date
    name: str | None = None
    is_paid: bool


class MonthCalendarOut(BaseModel):
    year: int
    month: int
    working_days: int            # công chuẩn động (số ngày làm việc thực của tháng)
    paid_holiday_count: int
    days: list[DayCell]
    holidays: list[HolidayItem]
