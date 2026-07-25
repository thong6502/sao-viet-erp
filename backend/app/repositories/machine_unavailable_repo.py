"""Repository vùng máy không khả dụng — truy vấn `machine_unavailable_periods`.

Hai truy vấn đặc thù cho Gantt: theo 1 máy (né khe / CRUD) và theo DẢI ngày mọi máy (vẽ nền overlay).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.machine_unavailable import MachineUnavailablePeriod


def _dau_ngay(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


class MachineUnavailableRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, pid: int) -> MachineUnavailablePeriod | None:
        return self.db.get(MachineUnavailablePeriod, pid)

    def list_by_may(self, may_id: int) -> list[MachineUnavailablePeriod]:
        return list(self.db.execute(
            select(MachineUnavailablePeriod)
            .where(MachineUnavailablePeriod.may_id == may_id)
            .order_by(MachineUnavailablePeriod.unavailable_from)
        ).scalars())

    def list_range(self, *, tu: date, den: date, may_id: int | None = None) -> list[MachineUnavailablePeriod]:
        """Khoảng khóa GIAO với [đầu ngày tu, đầu ngày den+1) — cho Gantt vẽ nền (mọi máy hoặc 1 máy)."""
        lo = _dau_ngay(tu)
        hi = _dau_ngay(den) + timedelta(days=1)
        stmt = select(MachineUnavailablePeriod).where(
            MachineUnavailablePeriod.unavailable_to > lo,
            MachineUnavailablePeriod.unavailable_from < hi,
        )
        if may_id is not None:
            stmt = stmt.where(MachineUnavailablePeriod.may_id == may_id)
        return list(self.db.execute(
            stmt.order_by(MachineUnavailablePeriod.may_id, MachineUnavailablePeriod.unavailable_from)
        ).scalars())

    def add(self, row: MachineUnavailablePeriod) -> MachineUnavailablePeriod:
        self.db.add(row)
        self.db.flush()
        return row

    def delete(self, row: MachineUnavailablePeriod) -> None:
        self.db.delete(row)
        self.db.flush()

    def commit(self) -> None:
        self.db.commit()
