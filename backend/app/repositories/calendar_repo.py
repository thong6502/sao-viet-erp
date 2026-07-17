"""Lịch làm việc & Ngày lễ — data access (lớp DUY NHẤT chạm DB cho lịch).
Không luật nghiệp vụ (ở CalendarService)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.work_calendar import SpecialDay, WorkCalendarConfig


class CalendarRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- config (singleton) -------------------------------------------------

    def get_config(self) -> WorkCalendarConfig | None:
        return self.db.execute(
            select(WorkCalendarConfig).order_by(WorkCalendarConfig.id).limit(1)
        ).scalars().first()

    def create_config(self, **fields) -> WorkCalendarConfig:
        c = WorkCalendarConfig(**fields)
        self.db.add(c)
        self.db.commit()
        self.db.refresh(c)
        return c

    def update_config(self, c: WorkCalendarConfig, **fields) -> WorkCalendarConfig:
        for k, v in fields.items():
            setattr(c, k, v)
        self.db.commit()
        self.db.refresh(c)
        return c

    # --- special days -------------------------------------------------------

    def list_in_range(self, start: date, end: date) -> list[SpecialDay]:
        return list(self.db.execute(
            select(SpecialDay)
            .where(SpecialDay.day >= start, SpecialDay.day <= end)
            .order_by(SpecialDay.day)
        ).scalars())

    def list_by_year(self, year: int) -> list[SpecialDay]:
        return self.list_in_range(date(year, 1, 1), date(year, 12, 31))

    def get(self, special_id: int) -> SpecialDay | None:
        return self.db.get(SpecialDay, special_id)

    def get_by_day(self, day: date) -> SpecialDay | None:
        return self.db.execute(
            select(SpecialDay).where(SpecialDay.day == day)
        ).scalars().first()

    def count(self) -> int:
        return len(list(self.db.execute(select(SpecialDay.id)).scalars()))

    def create(self, **fields) -> SpecialDay:
        s = SpecialDay(**fields)
        self.db.add(s)
        self.db.commit()
        self.db.refresh(s)
        return s

    def update(self, s: SpecialDay, **fields) -> SpecialDay:
        for k, v in fields.items():
            setattr(s, k, v)
        self.db.commit()
        self.db.refresh(s)
        return s

    def delete(self, s: SpecialDay) -> None:
        self.db.delete(s)
        self.db.commit()
