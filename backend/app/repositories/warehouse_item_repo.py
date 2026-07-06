"""Warehouse item repository — module Kho hàng vận hành."""
from __future__ import annotations

from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from ..models.warehouse_item import WarehouseItem


class WarehouseItemRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- reads --------------------------------------------------------------

    def get_by_id(self, item_id: int) -> WarehouseItem | None:
        return self.db.get(WarehouseItem, item_id)

    def list(
        self,
        *,
        warehouse_id: int | None = None,
        q: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[WarehouseItem], int]:
        conditions = []
        if warehouse_id is not None:
            conditions.append(WarehouseItem.warehouse_id == warehouse_id)
        if q:
            like = f"%{q.strip().lower()}%"
            conditions.append(or_(func.lower(WarehouseItem.name).like(like)))

        base = select(WarehouseItem)
        count_stmt = select(func.count()).select_from(WarehouseItem)
        for c in conditions:
            base = base.where(c)
            count_stmt = count_stmt.where(c)

        total = self.db.execute(count_stmt).scalar_one()

        # Mới nhất trước (theo thứ tự nhập).
        base = base.order_by(desc(WarehouseItem.created_at), desc(WarehouseItem.id))
        page = max(1, page)
        size = max(1, min(size, 200))
        base = base.offset((page - 1) * size).limit(size)

        rows = list(self.db.execute(base).scalars())
        return rows, total

    # --- writes -------------------------------------------------------------

    def create(
        self,
        *,
        warehouse_id: int,
        name: str,
        quantity: float,
        unit: str,
        notes: str | None,
        created_by_user_id: int | None,
    ) -> WarehouseItem:
        item = WarehouseItem(
            warehouse_id=warehouse_id,
            name=name,
            quantity=quantity,
            unit=unit,
            notes=notes,
            created_by_user_id=created_by_user_id,
        )
        self.db.add(item)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.db.refresh(item)
        return item

    def update(
        self,
        item: WarehouseItem,
        *,
        warehouse_id: int,
        name: str,
        quantity: float,
        unit: str,
        notes: str | None,
    ) -> WarehouseItem:
        item.warehouse_id = warehouse_id
        item.name = name
        item.quantity = quantity
        item.unit = unit
        item.notes = notes
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.db.refresh(item)
        return item

    def delete(self, item: WarehouseItem) -> None:
        self.db.delete(item)
        self.db.commit()
