"""Plate/Die Rate Repository — data access for plate and die rates.
"""
from __future__ import annotations

from datetime import date
from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.orm import Session
from ..models.plate_die_rate import PlateDieRate

class PlateDieRateRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, rate_id: int) -> PlateDieRate | None:
        return self.db.get(PlateDieRate, rate_id)

    def get_current_rate(
        self,
        plate_type: str,
        technology: str,
        unit: str,
    ) -> PlateDieRate | None:
        stmt = (
            select(PlateDieRate)
            .where(PlateDieRate.plate_type == plate_type)
            .where(PlateDieRate.technology == technology)
            .where(PlateDieRate.unit == unit)
            .where(PlateDieRate.effective_to.is_(None))
        )
        return self.db.execute(stmt).scalars().first()

    def get_rate_at_date(
        self,
        plate_type: str,
        technology: str,
        unit: str,
        at_date: date,
    ) -> PlateDieRate | None:
        stmt = (
            select(PlateDieRate)
            .where(PlateDieRate.plate_type == plate_type)
            .where(PlateDieRate.technology == technology)
            .where(PlateDieRate.unit == unit)
            .where(PlateDieRate.effective_from <= at_date)
            .where(
                or_(
                    PlateDieRate.effective_to.is_(None),
                    PlateDieRate.effective_to > at_date,
                )
            )
        )
        # #16 — ORDER BY để nếu có nhiều version chồng lấn thì trả version bắt đầu MUỘN nhất.
        stmt = stmt.order_by(PlateDieRate.effective_from.desc(), PlateDieRate.id.desc())
        return self.db.execute(stmt).scalars().first()

    def get_closed_rate_covering(
        self,
        plate_type: str,
        technology: str,
        unit: str,
        at_date: date,
    ) -> PlateDieRate | None:
        """Một đơn giá ĐÃ ĐÓNG mà khoảng [from, to) chứa at_date — chặn chồng lấn (#14)."""
        stmt = (
            select(PlateDieRate)
            .where(PlateDieRate.plate_type == plate_type)
            .where(PlateDieRate.technology == technology)
            .where(PlateDieRate.unit == unit)
            .where(PlateDieRate.effective_to.isnot(None))
            .where(PlateDieRate.effective_from <= at_date)
            .where(PlateDieRate.effective_to > at_date)
        )
        return self.db.execute(stmt).scalars().first()

    def find_predecessor(self, rate: PlateDieRate) -> PlateDieRate | None:
        """Đơn giá (cùng cấu hình) mà `rate` đã đóng — effective_to == rate.effective_from (#4)."""
        stmt = (
            select(PlateDieRate)
            .where(PlateDieRate.id != rate.id)
            .where(PlateDieRate.plate_type == rate.plate_type)
            .where(PlateDieRate.technology == rate.technology)
            .where(PlateDieRate.unit == rate.unit)
            .where(PlateDieRate.effective_to == rate.effective_from)
        )
        return self.db.execute(stmt).scalars().first()

    def list_rates(
        self,
        *,
        plate_type: str | None = None,
        technology: str | None = None,
        is_active: bool | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[PlateDieRate], int]:
        conditions = []
        if plate_type:
            conditions.append(PlateDieRate.plate_type == plate_type)
        if technology:
            conditions.append(PlateDieRate.technology == technology)
        if is_active is not None:
            conditions.append(PlateDieRate.is_active == is_active)

        stmt = select(PlateDieRate)
        count_stmt = select(func.count()).select_from(PlateDieRate)
        for c in conditions:
            stmt = stmt.where(c)
            count_stmt = count_stmt.where(c)

        total = self.db.execute(count_stmt).scalar_one()

        # clamp: page>=1 tránh OFFSET âm (Postgres 500); size 1..200 (đồng bộ với click/norm).
        page = max(1, page)
        size = max(1, min(size, 200))

        stmt = stmt.order_by(
            PlateDieRate.plate_type.asc(),
            PlateDieRate.technology.asc(),
            PlateDieRate.effective_from.desc(),
        )
        stmt = stmt.offset((page - 1) * size).limit(size)
        rows = list(self.db.execute(stmt).scalars())
        return rows, total

    def add_rate(
        self,
        *,
        plate_type: str,
        technology: str,
        unit: str,
        unit_price: int,
        setup_fee: int = 0,
        min_charge: int = 0,
        reusable: bool = False,
        effective_from: date,
    ) -> PlateDieRate:
        # Find current active rate
        current = self.get_current_rate(plate_type, technology, unit)
        if current:
            # Close old price rate: effective_to = new_effective_from (exclusive)
            current.effective_to = effective_from
            self.db.add(current)

        new_rate = PlateDieRate(
            plate_type=plate_type,
            technology=technology,
            unit=unit,
            unit_price=unit_price,
            setup_fee=setup_fee,
            min_charge=min_charge,
            reusable=reusable,
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
