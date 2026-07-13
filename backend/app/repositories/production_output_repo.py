"""Phiếu sản lượng công đoạn (Pha 5b) — data access."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.production import ProductionOrder
from ..models.production_output import ProductionOutput


class ProductionOutputRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, output_id: int) -> ProductionOutput | None:
        return self.db.get(ProductionOutput, output_id)

    def list_by_order(self, order_id: int) -> list[ProductionOutput]:
        return list(self.db.execute(
            select(ProductionOutput).where(ProductionOutput.production_order_id == order_id)
            .order_by(ProductionOutput.cong_doan, ProductionOutput.id)
        ).scalars())

    def list_by_month_group(self, year: int, month: int, group_name: str) -> list[ProductionOutput]:
        """Phiếu theo TỔ của 1 kỳ+tổ — nguồn materialize vào sổ khoán."""
        return list(self.db.execute(
            select(ProductionOutput).where(
                ProductionOutput.year == year, ProductionOutput.month == month,
                ProductionOutput.group_name == group_name, ProductionOutput.ghi_theo == "to",
            ).order_by(ProductionOutput.id)
        ).scalars())

    def list_nguoi_by_month_group(self, year: int, month: int, group_name: str) -> list[ProductionOutput]:
        """Phiếu theo NGƯỜI của 1 kỳ+tổ (5b-2) — cộng thẳng vào lương, gate bởi khóa sổ tổ."""
        return list(self.db.execute(
            select(ProductionOutput).where(
                ProductionOutput.year == year, ProductionOutput.month == month,
                ProductionOutput.group_name == group_name, ProductionOutput.ghi_theo == "nguoi",
            ).order_by(ProductionOutput.id)
        ).scalars())

    def list_by_period(self, year: int, month: int) -> list[ProductionOutput]:
        """Mọi phiếu của kỳ — cho report tỉ lệ hỏng."""
        return list(self.db.execute(
            select(ProductionOutput).where(
                ProductionOutput.year == year, ProductionOutput.month == month,
            ).order_by(ProductionOutput.group_name, ProductionOutput.id)
        ).scalars())

    def create(self, **f) -> ProductionOutput:
        o = ProductionOutput(**f); self.db.add(o); self.db.commit(); self.db.refresh(o); return o

    def update(self, o: ProductionOutput, **f) -> ProductionOutput:
        for k, v in f.items():
            setattr(o, k, v)
        self.db.commit(); self.db.refresh(o); return o

    def delete(self, o: ProductionOutput) -> None:
        self.db.delete(o); self.db.commit()

    def get_order(self, order_id: int) -> ProductionOrder | None:
        return self.db.get(ProductionOrder, order_id)
