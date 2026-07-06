"""Attendance / chấm công data access (module `nhan_su`). The ONLY layer touching the DB
for work_locations + attendance_logs. No business rules (those live in AttendanceService)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.attendance import AttendanceLog, WorkLocation, WorkShift


class AttendanceRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- work_shifts --------------------------------------------------------

    def list_shifts(self, *, active_only: bool = False) -> list[WorkShift]:
        stmt = select(WorkShift)
        if active_only:
            stmt = stmt.where(WorkShift.is_active.is_(True))
        return list(self.db.execute(stmt.order_by(WorkShift.start_minute, WorkShift.id)).scalars())

    def get_shift(self, shift_id: int) -> WorkShift | None:
        return self.db.get(WorkShift, shift_id)

    def create_shift(self, **fields) -> WorkShift:
        s = WorkShift(**fields)
        self.db.add(s)
        self.db.commit()
        self.db.refresh(s)
        return s

    def update_shift(self, shift: WorkShift, **fields) -> WorkShift:
        for key, value in fields.items():
            setattr(shift, key, value)
        self.db.commit()
        self.db.refresh(shift)
        return shift

    def delete_shift(self, shift: WorkShift) -> None:
        self.db.delete(shift)
        self.db.commit()

    # --- work_locations -----------------------------------------------------

    def list_locations(self, *, active_only: bool = False) -> list[WorkLocation]:
        stmt = select(WorkLocation)
        if active_only:
            stmt = stmt.where(WorkLocation.is_active.is_(True))
        return list(self.db.execute(stmt.order_by(WorkLocation.id)).scalars())

    def get_location(self, location_id: int) -> WorkLocation | None:
        return self.db.get(WorkLocation, location_id)

    def create_location(self, **fields) -> WorkLocation:
        loc = WorkLocation(**fields)
        self.db.add(loc)
        self.db.commit()
        self.db.refresh(loc)
        return loc

    def update_location(self, loc: WorkLocation, **fields) -> WorkLocation:
        for key, value in fields.items():
            setattr(loc, key, value)
        self.db.commit()
        self.db.refresh(loc)
        return loc

    def delete_location(self, loc: WorkLocation) -> None:
        self.db.delete(loc)
        self.db.commit()

    # --- attendance_logs ----------------------------------------------------

    def create_log(self, **fields) -> AttendanceLog:
        log = AttendanceLog(**fields)
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        return log

    def last_log(self, employee_id: int) -> AttendanceLog | None:
        """Most recent log for the employee (drives auto VÀO/RA toggling)."""
        return self.db.execute(
            select(AttendanceLog)
            .where(AttendanceLog.employee_id == employee_id)
            .order_by(AttendanceLog.checked_at.desc(), AttendanceLog.id.desc())
        ).scalars().first()

    def list_by_employee(self, employee_id: int, *, limit: int = 30) -> list[AttendanceLog]:
        return list(
            self.db.execute(
                select(AttendanceLog)
                .where(AttendanceLog.employee_id == employee_id)
                .order_by(AttendanceLog.checked_at.desc(), AttendanceLog.id.desc())
                .limit(limit)
            ).scalars()
        )

    def logs_in_range(self, start, end) -> list[AttendanceLog]:
        """All logs with checked_at in [start, end) (UTC), oldest first — for the monthly
        timesheet aggregation."""
        return list(
            self.db.execute(
                select(AttendanceLog)
                .where(AttendanceLog.checked_at >= start, AttendanceLog.checked_at < end)
                .order_by(AttendanceLog.checked_at.asc(), AttendanceLog.id.asc())
            ).scalars()
        )

    def list_all(self, *, employee_id: int | None = None, limit: int = 100) -> list[AttendanceLog]:
        stmt = select(AttendanceLog)
        if employee_id is not None:
            stmt = stmt.where(AttendanceLog.employee_id == employee_id)
        stmt = stmt.order_by(AttendanceLog.checked_at.desc(), AttendanceLog.id.desc()).limit(limit)
        return list(self.db.execute(stmt).scalars())
