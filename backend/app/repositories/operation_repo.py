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
    "sequence": Operation.default_sequence,
    "created_at": Operation.created_at,
}

# Config fields carried on the Operation row (spec §A–§G), shared by create/update.
_OP_CONFIG_FIELDS = (
    "basis_quantity",
    "pricing_method",
    "process_group",
    "process_type",
    "default_sequence",
    "quantity_formula_type",
    "allow_manual_quantity",
    "internal_pricing_method",
    "labor_people_count",
    "has_tooling",
    "tooling_type",
    "tooling_rate_id",
    "has_yield_loss",
    "default_yield_rate",
    "default_yield_rule",
    "allow_outsource",
)

# Price fields carried on each OperationRate version (spec §C–§F).
_RATE_PRICE_FIELDS = (
    "setup_fee",
    "run_rate",
    "labor_rate",
    "min_charge",
    "speed",
    "setup_time_mins",
    "hourly_rate",
    "labor_shift_rate",
    "labor_fixed",
    "labor_min",
    "tooling_unit_price",
    "outsource_supplier",
    "outsource_unit_price",
    "outsource_setup_fee",
    "outsource_min_charge",
    "outsource_transport_fee",
    "outsource_moq",
    "outsource_lead_time_days",
)

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
        is_active: bool = True,
        **config,
    ) -> Operation:
        operation = Operation(
            code=self._next_code(),
            name=name,
            operation_type=operation_type,
            unit=unit,
            is_active=is_active,
            **{k: v for k, v in config.items() if k in _OP_CONFIG_FIELDS},
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
        is_active: bool | None = None,
        **config,
    ) -> Operation:
        operation.name = name
        operation.operation_type = operation_type
        operation.unit = unit
        for field in _OP_CONFIG_FIELDS:
            if field in config:
                setattr(operation, field, config[field])
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
        effective_from: date,
        **prices,
    ) -> OperationRate:
        current = self.get_current_rate(operation_id)
        if current:
            # #8 — đóng nửa-mở effective_to = effective_from (KHÔNG -1 ngày): tránh vi phạm CHECK
            # (effective_to > effective_from) khi rate mới cách rate cũ đúng 1 ngày → crash 500.
            current.effective_to = effective_from
            self.db.add(current)

        new_rate = OperationRate(
            operation_id=operation_id,
            effective_from=effective_from,
            effective_to=None,
            **{k: v for k, v in prices.items() if k in _RATE_PRICE_FIELDS},
        )
        self.db.add(new_rate)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return new_rate
