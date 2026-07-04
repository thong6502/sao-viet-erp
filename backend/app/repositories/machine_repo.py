"""Machine Repository — master data access.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.orm import Session, selectinload
from ..models.machine import Machine, MachineRate

_SORTABLE = {
    "code": Machine.code,
    "name": Machine.name,
    "machine_type": Machine.machine_type,
    "created_at": Machine.created_at,
}

class MachineRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- reads --------------------------------------------------------------

    def get_by_id(self, machine_id: int) -> Machine | None:
        return self.db.execute(
            select(Machine)
            .options(selectinload(Machine.rates))
            .where(Machine.id == machine_id)
        ).scalars().first()

    def get_by_code(self, code: str) -> Machine | None:
        return self.db.execute(
            select(Machine)
            .options(selectinload(Machine.rates))
            .where(Machine.code == code)
        ).scalars().first()

    def find_by_name(self, name: str) -> Machine | None:
        name = (name or "").strip()
        if not name:
            return None
        return self.db.execute(
            select(Machine)
            .where(func.lower(Machine.name) == name.lower())
        ).scalars().first()

    def list(
        self,
        *,
        q: str | None = None,
        machine_type: str | None = None,
        machine_group: str | None = None,
        is_active: bool | None = None,
        sort: str = "code",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Machine], int]:
        conditions = []
        if q:
            like = f"%{q.strip().lower()}%"
            conditions.append(
                or_(
                    func.lower(Machine.name).like(like),
                    func.lower(Machine.code).like(like),
                )
            )
        if machine_type:
            conditions.append(Machine.machine_type == machine_type)
        if machine_group:
            conditions.append(Machine.machine_group == machine_group)
        if is_active is not None:
            conditions.append(Machine.is_active == is_active)

        base = select(Machine)
        count_stmt = select(func.count()).select_from(Machine)
        for c in conditions:
            base = base.where(c)
            count_stmt = count_stmt.where(c)

        total = self.db.execute(count_stmt).scalar_one()

        direction = asc
        key = sort or "code"
        if key.startswith("-"):
            direction = desc
            key = key[1:]
        col = _SORTABLE.get(key, Machine.code)
        base = base.order_by(direction(col), Machine.id.asc())

        page = max(1, page)
        size = max(1, min(size, 200))
        base = base.offset((page - 1) * size).limit(size)

        rows = list(self.db.execute(base).scalars())
        return rows, total

    # --- writes -------------------------------------------------------------

    def _next_code(self) -> str:
        max_n = 0
        for code in self.db.execute(
            select(Machine.code).where(Machine.code.like("MY%"))
        ).scalars():
            try:
                max_n = max(max_n, int(code[2:]))
            except ValueError:
                continue
        return f"MY{max_n + 1:03d}"

    def create(self, **fields) -> Machine:
        code = (fields.pop("code", None) or "").strip().upper() or self._next_code()
        machine = Machine(code=code, **fields)
        self.db.add(machine)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return machine

    def update(self, machine: Machine, **fields) -> Machine:
        for k, v in fields.items():
            if k == "is_active" and v is None:
                continue
            setattr(machine, k, v)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return machine

    def delete(self, machine: Machine) -> None:
        self.db.delete(machine)
        self.db.commit()

    # --- rates writes -------------------------------------------------------

    def get_current_rate(self, machine_id: int) -> MachineRate | None:
        return self.db.execute(
            select(MachineRate)
            .where(MachineRate.machine_id == machine_id)
            .where(MachineRate.effective_to.is_(None))
        ).scalars().first()

    def add_machine_rate(
        self,
        *,
        machine_id: int,
        hourly_rate: int,
        min_charge: int = 0,
        min_run_time_mins: int = 0,
        rate_depreciation: int = 0,
        rate_energy: int = 0,
        rate_maintenance: int = 0,
        rate_labor: int = 0,
        rate_overhead: int = 0,
        effective_from: date,
    ) -> MachineRate:
        current = self.get_current_rate(machine_id)
        if current:
            # #7 — đóng nửa-mở effective_to = effective_from (KHÔNG -1 ngày): tránh vi phạm CHECK
            # (effective_to > effective_from) khi rate mới cách rate cũ đúng 1 ngày → crash 500.
            # Khớp truy vấn của pricing_engine (effective_to > at_date).
            current.effective_to = effective_from
            self.db.add(current)

        new_rate = MachineRate(
            machine_id=machine_id,
            hourly_rate=hourly_rate,
            min_charge=min_charge,
            min_run_time_mins=min_run_time_mins,
            rate_depreciation=rate_depreciation,
            rate_energy=rate_energy,
            rate_maintenance=rate_maintenance,
            rate_labor=rate_labor,
            rate_overhead=rate_overhead,
            effective_from=effective_from,
            effective_to=None,
        )
        self.db.add(new_rate)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return new_rate
