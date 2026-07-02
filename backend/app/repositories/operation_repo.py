"""Operation Repository — master data access.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.orm import Session, selectinload
from ..models.operation import Operation, OperationRate

_SORTABLE = {
    "code": Operation.code,
    "name": Operation.name,
    "operation_type": Operation.operation_type,
    "created_at": Operation.created_at,
}

class OperationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- reads --------------------------------------------------------------

    def get_by_id(self, operation_id: int) -> Operation | None:
        return self.db.execute(
            select(Operation)
            .options(selectinload(Operation.rates))
            .where(Operation.id == operation_id)
        ).scalars().first()

    def get_by_code(self, code: str) -> Operation | None:
        return self.db.execute(
            select(Operation)
            .options(selectinload(Operation.rates))
            .where(Operation.code == code)
        ).scalars().first()

    def find_by_name(self, name: str) -> Operation | None:
        name = (name or "").strip()
        if not name:
            return None
        return self.db.execute(
            select(Operation)
            .where(func.lower(Operation.name) == name.lower())
        ).scalars().first()

    def list(
        self,
        *,
        q: str | None = None,
        operation_type: str | None = None,
        is_active: bool | None = None,
        sort: str = "code",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Operation], int]:
        conditions = []
        if q:
            like = f"%{q.strip().lower()}%"
            conditions.append(
                or_(
                    func.lower(Operation.name).like(like),
                    func.lower(Operation.code).like(like),
                )
            )
        if operation_type:
            conditions.append(Operation.operation_type == operation_type)
        if is_active is not None:
            conditions.append(Operation.is_active == is_active)

        base = select(Operation)
        count_stmt = select(func.count()).select_from(Operation)
        for c in conditions:
            base = base.where(c)
            count_stmt = count_stmt.where(c)

        total = self.db.execute(count_stmt).scalar_one()

        direction = asc
        key = sort or "code"
        if key.startswith("-"):
            direction = desc
            key = key[1:]
        col = _SORTABLE.get(key, Operation.code)
        base = base.order_by(direction(col), Operation.id.asc())

        page = max(1, page)
        size = max(1, min(size, 200))
        base = base.offset((page - 1) * size).limit(size)

        rows = list(self.db.execute(base).scalars())
        return rows, total

    # --- writes -------------------------------------------------------------

    def _next_code(self) -> str:
        max_n = 0
        for code in self.db.execute(
            select(Operation.code).where(Operation.code.like("CD%"))
        ).scalars():
            try:
                max_n = max(max_n, int(code[2:]))
            except ValueError:
                continue
        return f"CD{max_n + 1:03d}"

    def create(
        self,
        *,
        name: str,
        operation_type: str,
        unit: str,
        allow_outsource: bool = False,
        is_active: bool = True,
    ) -> Operation:
        operation = Operation(
            code=self._next_code(),
            name=name,
            operation_type=operation_type,
            unit=unit,
            allow_outsource=allow_outsource,
            is_active=is_active,
        )
        self.db.add(operation)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return operation

    def update(
        self,
        operation: Operation,
        *,
        name: str,
        operation_type: str,
        unit: str,
        allow_outsource: bool,
        is_active: bool | None = None,
    ) -> Operation:
        operation.name = name
        operation.operation_type = operation_type
        operation.unit = unit
        operation.allow_outsource = allow_outsource
        if is_active is not None:
            operation.is_active = is_active
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return operation

    def delete(self, operation: Operation) -> None:
        self.db.delete(operation)
        self.db.commit()

    # --- rates writes -------------------------------------------------------

    def get_current_rate(self, operation_id: int) -> OperationRate | None:
        return self.db.execute(
            select(OperationRate)
            .where(OperationRate.operation_id == operation_id)
            .where(OperationRate.effective_to.is_(None))
        ).scalars().first()

    def add_operation_rate(
        self,
        *,
        operation_id: int,
        setup_fee: int = 0,
        run_rate: int = 0,
        labor_rate: int = 0,
        min_charge: int = 0,
        speed: float = 0.0,
        effective_from: date,
    ) -> OperationRate:
        current = self.get_current_rate(operation_id)
        if current:
            # #8 — đóng nửa-mở effective_to = effective_from (KHÔNG -1 ngày): tránh vi phạm CHECK
            # (effective_to > effective_from) khi rate mới cách rate cũ đúng 1 ngày → crash 500.
            current.effective_to = effective_from
            self.db.add(current)
            
        new_rate = OperationRate(
            operation_id=operation_id,
            setup_fee=setup_fee,
            run_rate=run_rate,
            labor_rate=labor_rate,
            min_charge=min_charge,
            speed=speed,
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
