"""Click/Ink Rate Repository — data access for click/ink rates.
"""
from __future__ import annotations

from datetime import date
from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.orm import Session
from ..models.click_ink_rate import ClickInkRate

class ClickInkRateRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, rate_id: int) -> ClickInkRate | None:
        return self.db.get(ClickInkRate, rate_id)

    def get_current_rate(
        self,
        technology: str,
        color_type: str,
        machine_id: int | None,
        unit: str,
    ) -> ClickInkRate | None:
        stmt = (
            select(ClickInkRate)
            .where(ClickInkRate.technology == technology)
            .where(ClickInkRate.color_type == color_type)
            .where(ClickInkRate.unit == unit)
            .where(ClickInkRate.effective_to.is_(None))
        )
        if machine_id is not None:
            stmt = stmt.where(ClickInkRate.machine_id == machine_id)
        else:
            stmt = stmt.where(ClickInkRate.machine_id.is_(None))
        return self.db.execute(stmt).scalars().first()

    def get_rate_at_date(
        self,
        technology: str,
        color_type: str,
        machine_id: int | None,
        unit: str,
        at_date: date,
    ) -> ClickInkRate | None:
        stmt = (
            select(ClickInkRate)
            .where(ClickInkRate.technology == technology)
            .where(ClickInkRate.color_type == color_type)
            .where(ClickInkRate.unit == unit)
            .where(ClickInkRate.effective_from <= at_date)
            .where(
                or_(
                    ClickInkRate.effective_to.is_(None),
                    ClickInkRate.effective_to > at_date,
                )
            )
        )
        if machine_id is not None:
            stmt = stmt.where(ClickInkRate.machine_id == machine_id)
        else:
            stmt = stmt.where(ClickInkRate.machine_id.is_(None))
        # #15 — ORDER BY để nếu có nhiều version chồng lấn thì trả version bắt đầu MUỘN nhất
        # (bản đang hiệu lực đúng), không phụ thuộc thứ tự trả về của DB.
        stmt = stmt.order_by(ClickInkRate.effective_from.desc(), ClickInkRate.id.desc())
        return self.db.execute(stmt).scalars().first()

    def get_closed_rate_covering(
        self,
        technology: str,
        color_type: str,
        machine_id: int | None,
        unit: str,
        at_date: date,
    ) -> ClickInkRate | None:
        """Một đơn giá ĐÃ ĐÓNG (effective_to != NULL) mà khoảng [from, to) chứa at_date.
        Dùng để chặn tạo version chồng lấn sau khi close_rate/backdate (#2)."""
        stmt = (
            select(ClickInkRate)
            .where(ClickInkRate.technology == technology)
            .where(ClickInkRate.color_type == color_type)
            .where(ClickInkRate.unit == unit)
            .where(ClickInkRate.effective_to.isnot(None))
            .where(ClickInkRate.effective_from <= at_date)
            .where(ClickInkRate.effective_to > at_date)
        )
        if machine_id is not None:
            stmt = stmt.where(ClickInkRate.machine_id == machine_id)
        else:
            stmt = stmt.where(ClickInkRate.machine_id.is_(None))
        return self.db.execute(stmt).scalars().first()

    def find_predecessor(self, rate: ClickInkRate) -> ClickInkRate | None:
        """Đơn giá (cùng cấu hình) mà `rate` đã đóng — effective_to == rate.effective_from.
        Dùng mở lại khi xóa cứng một đơn giá tương lai (tránh khoảng trống — #3)."""
        stmt = (
            select(ClickInkRate)
            .where(ClickInkRate.id != rate.id)
            .where(ClickInkRate.technology == rate.technology)
            .where(ClickInkRate.color_type == rate.color_type)
            .where(ClickInkRate.unit == rate.unit)
            .where(ClickInkRate.machine_id == rate.machine_id)
            .where(ClickInkRate.effective_to == rate.effective_from)
        )
        return self.db.execute(stmt).scalars().first()

    def list_rates(
        self,
        *,
        technology: str | None = None,
        machine_id: int | None = None,
        is_active: bool | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[ClickInkRate], int]:
        conditions = []
        if technology:
            conditions.append(ClickInkRate.technology == technology)
        if machine_id is not None:
            conditions.append(ClickInkRate.machine_id == machine_id)
        if is_active is not None:
            conditions.append(ClickInkRate.is_active == is_active)

        stmt = select(ClickInkRate)
        count_stmt = select(func.count()).select_from(ClickInkRate)
        for c in conditions:
            stmt = stmt.where(c)
            count_stmt = count_stmt.where(c)

        total = self.db.execute(count_stmt).scalar_one()

        # #23 — clamp: page>=1 tránh OFFSET âm (Postgres 500); size 1..200.
        page = max(1, page)
        size = max(1, min(size, 200))

        stmt = stmt.order_by(
            ClickInkRate.technology.asc(),
            ClickInkRate.color_type.asc(),
            ClickInkRate.effective_from.desc(),
        )
        stmt = stmt.offset((page - 1) * size).limit(size)
        rows = list(self.db.execute(stmt).scalars())
        return rows, total

    def add_rate(
        self,
        *,
        technology: str,
        color_type: str,
        machine_id: int | None,
        unit: str,
        unit_price: int,
        setup_fee: int = 0,
        min_charge: int = 0,
        effective_from: date,
    ) -> ClickInkRate:
        # Find current active rate
        current = self.get_current_rate(technology, color_type, machine_id, unit)
        if current:
            # Close old price rate: effective_to = new_effective_from (exclusive)
            current.effective_to = effective_from
            self.db.add(current)

        new_rate = ClickInkRate(
            technology=technology,
            color_type=color_type,
            machine_id=machine_id,
            unit=unit,
            unit_price=unit_price,
            setup_fee=setup_fee,
            min_charge=min_charge,
            effective_from=effective_from,
            effective_to=None,
            is_active=True,
        )
        self.db.add(new_rate)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return new_rate
