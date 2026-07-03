"""Estimate Repository — data access for Estimates, options, and cost lines.
"""
from __future__ import annotations

from sqlalchemy import String, select, func, asc, desc
from sqlalchemy.orm import Session, selectinload
from ..models.estimate import Estimate, EstimateOption, EstimateCostLine

_SORTABLE = {
    "estimate_number": Estimate.estimate_number,
    "product_name": Estimate.product_name,
    "product_type": Estimate.product_type,
    "status": Estimate.status,
    "created_at": Estimate.created_at,
}

class EstimateRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, estimate_id: int) -> Estimate | None:
        return self.db.execute(
            select(Estimate)
            .options(
                selectinload(Estimate.options).selectinload(EstimateOption.cost_lines)
            )
            .where(Estimate.id == estimate_id)
        ).scalars().first()

    def get_by_number(self, estimate_number: str) -> Estimate | None:
        return self.db.execute(
            select(Estimate)
            .options(
                selectinload(Estimate.options).selectinload(EstimateOption.cost_lines)
            )
            .where(Estimate.estimate_number == estimate_number)
        ).scalars().first()

    def list_estimates(
        self,
        *,
        q: str | None = None,
        product_type: str | None = None,
        status: str | None = None,
        has_blocking: bool | None = None,
        sort: str = "estimate_number",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Estimate], int]:
        conditions = []
        if q:
            like = f"%{q.strip().lower()}%"
            conditions.append(
                (func.lower(Estimate.estimate_number).like(like)) |
                (func.lower(Estimate.product_name).like(like))
            )
        if product_type:
            conditions.append(Estimate.product_type == product_type)
        if status:
            conditions.append(Estimate.status == status)
        if has_blocking:
            # Lọc phiếu có lỗi chặn: dò chuỗi "blocking_error" trong JSON warnings của option.
            # LIKE trên JSON-as-text đủ cho tab lọc (severity chỉ xuất hiện ở field này).
            sub = select(EstimateOption.id).where(
                EstimateOption.estimate_id == Estimate.id,
                func.cast(EstimateOption.warnings_json, String).like("%blocking_error%"),
            )
            conditions.append(sub.exists())

        base = select(Estimate)
        count_stmt = select(func.count()).select_from(Estimate)
        for c in conditions:
            base = base.where(c)
            count_stmt = count_stmt.where(c)

        total = self.db.execute(count_stmt).scalar_one()

        direction = asc
        key = sort or "estimate_number"
        if key.startswith("-"):
            direction = desc
            key = key[1:]
        col = _SORTABLE.get(key, Estimate.estimate_number)
        base = base.order_by(direction(col), Estimate.id.asc())

        page = max(1, page)
        size = max(1, min(size, 200))
        base = base.offset((page - 1) * size).limit(size)

        rows = list(
            self.db.execute(
                base.options(
                    selectinload(Estimate.options).selectinload(EstimateOption.cost_lines)
                )
            ).scalars()
        )
        return rows, total

    def stats(self) -> dict:
        """Đếm nhanh cho thanh tab list: tổng / theo trạng thái / số phiếu có lỗi chặn."""
        total = self.db.execute(select(func.count()).select_from(Estimate)).scalar_one()
        by_status = dict(
            self.db.execute(select(Estimate.status, func.count()).group_by(Estimate.status)).all()
        )
        blocking_ids: set[int] = set()
        for est_id, warnings in self.db.execute(
            select(EstimateOption.estimate_id, EstimateOption.warnings_json)
        ).all():
            if warnings and any(w.get("severity") == "blocking_error" for w in warnings):
                blocking_ids.add(est_id)
        return {
            "total": total,
            "draft": int(by_status.get("draft", 0)),
            "calculated": int(by_status.get("calculated", 0)),
            "blocking": len(blocking_ids),
        }

    def save(self, estimate: Estimate) -> Estimate:
        self.db.add(estimate)
        self.db.commit()
        return estimate

    def delete(self, estimate: Estimate) -> None:
        self.db.delete(estimate)
        self.db.commit()
