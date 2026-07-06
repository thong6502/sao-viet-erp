"""Leave (Nghỉ phép) data access — the ONLY layer touching the DB for leave_types +
leave_requests. No business rules (those live in LeaveService)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.leave import STATUS_APPROVED, LeaveRequest, LeaveType


class LeaveRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- leave_types --------------------------------------------------------

    def list_types(self, *, active_only: bool = False) -> list[LeaveType]:
        stmt = select(LeaveType)
        if active_only:
            stmt = stmt.where(LeaveType.is_active.is_(True))
        return list(self.db.execute(stmt.order_by(LeaveType.id)).scalars())

    def get_type(self, type_id: int) -> LeaveType | None:
        return self.db.get(LeaveType, type_id)

    def create_type(self, **fields) -> LeaveType:
        t = LeaveType(**fields)
        self.db.add(t)
        self.db.commit()
        self.db.refresh(t)
        return t

    def update_type(self, t: LeaveType, **fields) -> LeaveType:
        for key, value in fields.items():
            setattr(t, key, value)
        self.db.commit()
        self.db.refresh(t)
        return t

    def delete_type(self, t: LeaveType) -> None:
        self.db.delete(t)
        self.db.commit()

    # --- leave_requests -----------------------------------------------------

    def create_request(self, **fields) -> LeaveRequest:
        r = LeaveRequest(**fields)
        self.db.add(r)
        self.db.commit()
        self.db.refresh(r)
        return r

    def get_request(self, request_id: int) -> LeaveRequest | None:
        return self.db.get(LeaveRequest, request_id)

    def update_request(self, r: LeaveRequest, **fields) -> LeaveRequest:
        for key, value in fields.items():
            setattr(r, key, value)
        self.db.commit()
        self.db.refresh(r)
        return r

    def list_by_employee(self, employee_id: int, *, limit: int = 100) -> list[LeaveRequest]:
        return list(
            self.db.execute(
                select(LeaveRequest)
                .where(LeaveRequest.employee_id == employee_id)
                .order_by(LeaveRequest.start_date.desc(), LeaveRequest.id.desc())
                .limit(limit)
            ).scalars()
        )

    def list_all(self, *, status: str | None = None, limit: int = 200) -> list[LeaveRequest]:
        stmt = select(LeaveRequest)
        if status is not None:
            stmt = stmt.where(LeaveRequest.status == status)
        stmt = stmt.order_by(LeaveRequest.status.asc(), LeaveRequest.start_date.desc(), LeaveRequest.id.desc()).limit(limit)
        return list(self.db.execute(stmt).scalars())

    def approved_in_range(self, start: date, end: date) -> list[LeaveRequest]:
        """Approved leave requests whose date range overlaps [start, end] — for the
        monthly timesheet (mark P/KL on covered days)."""
        return list(
            self.db.execute(
                select(LeaveRequest).where(
                    LeaveRequest.status == STATUS_APPROVED,
                    LeaveRequest.start_date <= end,
                    LeaveRequest.end_date >= start,
                )
            ).scalars()
        )
