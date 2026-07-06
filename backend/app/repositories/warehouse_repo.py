"""Warehouse Repository — cấu hình kho hàng (admin master data)."""
from __future__ import annotations

from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.orm import Session

from ..models.warehouse import Warehouse

_SORTABLE = {
    "code": Warehouse.code,
    "name": Warehouse.name,
    "created_at": Warehouse.created_at,
}


class WarehouseRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- reads --------------------------------------------------------------

    def get_by_id(self, warehouse_id: int) -> Warehouse | None:
        return self.db.get(Warehouse, warehouse_id)

    def get_by_code(self, code: str) -> Warehouse | None:
        return self.db.execute(
            select(Warehouse).where(Warehouse.code == code)
        ).scalars().first()

    def find_by_name(self, name: str) -> Warehouse | None:
        name = (name or "").strip()
        if not name:
            return None
        return self.db.execute(
            select(Warehouse).where(func.lower(Warehouse.name) == name.lower())
        ).scalars().first()

    def list(
        self,
        *,
        q: str | None = None,
        is_active: bool | None = None,
        sort: str = "code",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Warehouse], int]:
        conditions = []
        if q:
            like = f"%{q.strip().lower()}%"
            conditions.append(
                or_(
                    func.lower(Warehouse.name).like(like),
                    func.lower(Warehouse.code).like(like),
                )
            )
        if is_active is not None:
            conditions.append(Warehouse.is_active == is_active)

        base = select(Warehouse)
        count_stmt = select(func.count()).select_from(Warehouse)
        for c in conditions:
            base = base.where(c)
            count_stmt = count_stmt.where(c)

        total = self.db.execute(count_stmt).scalar_one()

        direction = asc
        key = sort or "code"
        if key.startswith("-"):
            direction = desc
            key = key[1:]
        col = _SORTABLE.get(key, Warehouse.code)
        base = base.order_by(direction(col), Warehouse.id.asc())

        page = max(1, page)
        size = max(1, min(size, 200))
        base = base.offset((page - 1) * size).limit(size)

        rows = list(self.db.execute(base).scalars())
        return rows, total

    # --- writes -------------------------------------------------------------

    def _next_code(self) -> str:
        """Next sequential warehouse code: 'KHO' + zero-padded number. Based on the max
        existing KHO-number so codes stay unique even after deletions (no reuse)."""
        max_n = 0
        for code in self.db.execute(
            select(Warehouse.code).where(Warehouse.code.like("KHO%"))
        ).scalars():
            try:
                max_n = max(max_n, int(code[3:]))
            except ValueError:
                continue
        return f"KHO{max_n + 1:03d}"

    def create(
        self,
        *,
        name: str,
        description: str | None = None,
        notes: str | None = None,
        is_active: bool = True,
    ) -> Warehouse:
        warehouse = Warehouse(
            code=self._next_code(),
            name=name,
            description=description,
            notes=notes,
            is_active=is_active,
        )
        self.db.add(warehouse)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.db.refresh(warehouse)
        return warehouse

    def update(
        self,
        warehouse: Warehouse,
        *,
        name: str,
        description: str | None = None,
        notes: str | None = None,
        is_active: bool | None = None,
    ) -> Warehouse:
        warehouse.name = name
        warehouse.description = description
        warehouse.notes = notes
        if is_active is not None:
            warehouse.is_active = is_active
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.db.refresh(warehouse)
        return warehouse

    def delete(self, warehouse: Warehouse) -> None:
        self.db.delete(warehouse)
        self.db.commit()
