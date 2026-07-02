"""Norm Repository — data access for loss and waste norms.
"""
from __future__ import annotations

from datetime import date
from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.orm import Session
from ..models.norm import Norm

class NormRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, norm_id: int) -> Norm | None:
        return self.db.get(Norm, norm_id)

    def get_active_norm_matching_config(
        self,
        *,
        norm_key: str,
        product_type: str | None = None,
        machine_id: int | None = None,
        operation_id: int | None = None,
        operation_key: str | None = None,
        qty_min: int | None = None,
        qty_max: int | None = None,
        context_key: str = "{}",
    ) -> Norm | None:
        stmt = (
            select(Norm)
            .where(Norm.norm_key == norm_key)
            .where(Norm.context_key == context_key)
            .where(Norm.effective_to.is_(None))
        )
        # Handle product_type nullable checks
        if product_type is not None:
            stmt = stmt.where(Norm.product_type == product_type)
        else:
            stmt = stmt.where(Norm.product_type.is_(None))

        # Handle machine_id nullable checks
        if machine_id is not None:
            stmt = stmt.where(Norm.machine_id == machine_id)
        else:
            stmt = stmt.where(Norm.machine_id.is_(None))

        # Handle operation_id nullable checks
        if operation_id is not None:
            stmt = stmt.where(Norm.operation_id == operation_id)
        else:
            stmt = stmt.where(Norm.operation_id.is_(None))

        # Handle operation_key nullable checks
        if operation_key is not None:
            stmt = stmt.where(Norm.operation_key == operation_key)
        else:
            stmt = stmt.where(Norm.operation_key.is_(None))

        # Handle qty_min/qty_max nullable checks
        if qty_min is not None:
            stmt = stmt.where(Norm.qty_min == qty_min)
        else:
            stmt = stmt.where(Norm.qty_min.is_(None))

        if qty_max is not None:
            stmt = stmt.where(Norm.qty_max == qty_max)
        else:
            stmt = stmt.where(Norm.qty_max.is_(None))

        return self.db.execute(stmt).scalars().first()

    def find_predecessor(self, norm: Norm) -> Norm | None:
        """Norm (cùng cấu hình) mà `norm` đã đóng — tức effective_to == norm.effective_from.
        Dùng để mở lại khi xóa cứng một norm tương lai (tránh khoảng trống định mức — #1).
        (SQLAlchemy: `== None` sinh IS NULL, nên khớp đúng các chiều nullable.)"""
        stmt = (
            select(Norm)
            .where(Norm.id != norm.id)
            .where(Norm.norm_key == norm.norm_key)
            .where(Norm.context_key == norm.context_key)
            .where(Norm.effective_to == norm.effective_from)
            .where(Norm.product_type == norm.product_type)
            .where(Norm.machine_id == norm.machine_id)
            .where(Norm.operation_id == norm.operation_id)
            .where(Norm.operation_key == norm.operation_key)
            .where(Norm.qty_min == norm.qty_min)
            .where(Norm.qty_max == norm.qty_max)
        )
        return self.db.execute(stmt).scalars().first()

    def get_candidates(
        self,
        *,
        norm_key: str,
        product_type: str | None = None,
        machine_id: int | None = None,
        operation_id: int | None = None,
        operation_key: str | None = None,
        quantity: int | None = None,
        at_date: date,
    ) -> list[Norm]:
        stmt = (
            select(Norm)
            .where(Norm.norm_key == norm_key)
            .where(Norm.effective_from <= at_date)
            .where(
                or_(
                    Norm.effective_to.is_(None),
                    Norm.effective_to > at_date,
                )
            )
        )

        # Filters: must be null or match the input value
        if product_type is not None:
            stmt = stmt.where(or_(Norm.product_type.is_(None), Norm.product_type == product_type))
        else:
            stmt = stmt.where(Norm.product_type.is_(None))

        if machine_id is not None:
            stmt = stmt.where(or_(Norm.machine_id.is_(None), Norm.machine_id == machine_id))
        else:
            stmt = stmt.where(Norm.machine_id.is_(None))

        # Handle operation_id / operation_key
        # Check rule: CHECK (operation_id IS NULL OR operation_key IS NULL)
        # So we check both.
        if operation_id is not None:
            stmt = stmt.where(or_(Norm.operation_id.is_(None), Norm.operation_id == operation_id))
        else:
            stmt = stmt.where(Norm.operation_id.is_(None))

        if operation_key is not None:
            stmt = stmt.where(or_(Norm.operation_key.is_(None), Norm.operation_key == operation_key))
        else:
            stmt = stmt.where(Norm.operation_key.is_(None))

        # Quantity range logic (dải NỬA-MỞ [qty_min, qty_max) — #13):
        # - quantity None: chỉ khớp hàng qty_min IS NULL AND qty_max IS NULL.
        # - quantity != None: (qty_min IS NULL OR qty_min <= quantity) AND (qty_max IS NULL OR qty_max > quantity).
        #   Cận trên LOẠI TRỪ để 2 dải kề nhau ([1000,5000] & [5000,10000]) không cùng khớp mốc biên 5000.
        #   TODO(SVN): xác nhận quy ước nửa-mở cho dải số lượng định mức.
        if quantity is None:
            stmt = stmt.where(Norm.qty_min.is_(None)).where(Norm.qty_max.is_(None))
        else:
            stmt = stmt.where(
                or_(Norm.qty_min.is_(None), Norm.qty_min <= quantity)
            ).where(
                or_(Norm.qty_max.is_(None), Norm.qty_max > quantity)
            )

        return list(self.db.execute(stmt).scalars())

    def list_norms(
        self,
        *,
        norm_key: str | None = None,
        product_type: str | None = None,
        machine_id: int | None = None,
        operation_id: int | None = None,
        only_current: bool = False,
        at_date: date | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[Norm], int]:
        conditions = []
        if norm_key:
            conditions.append(Norm.norm_key == norm_key)
        if product_type:
            conditions.append(Norm.product_type == product_type)
        if machine_id is not None:
            conditions.append(Norm.machine_id == machine_id)
        if operation_id is not None:
            conditions.append(Norm.operation_id == operation_id)
        
        if only_current:
            ref_date = at_date or date.today()
            conditions.append(Norm.effective_from <= ref_date)
            conditions.append(
                or_(
                    Norm.effective_to.is_(None),
                    Norm.effective_to > ref_date,
                )
            )

        stmt = select(Norm)
        count_stmt = select(func.count()).select_from(Norm)
        for c in conditions:
            stmt = stmt.where(c)
            count_stmt = count_stmt.where(c)

        total = self.db.execute(count_stmt).scalar_one()

        # #22 — clamp (như các repo khác): page>=1 tránh OFFSET âm (Postgres 500); size 1..200.
        page = max(1, page)
        size = max(1, min(size, 200))

        stmt = stmt.order_by(
            Norm.norm_key.asc(),
            Norm.effective_from.desc(),
            Norm.id.desc(),
        )
        stmt = stmt.offset((page - 1) * size).limit(size)
        rows = list(self.db.execute(stmt).scalars())
        return rows, total

    def add_norm(
        self,
        *,
        norm_key: str,
        value: float,
        product_type: str | None = None,
        machine_id: int | None = None,
        operation_id: int | None = None,
        operation_key: str | None = None,
        qty_min: int | None = None,
        qty_max: int | None = None,
        context: dict | None = None,
        context_key: str = "{}",
        effective_from: date,
        note: str | None = None,
    ) -> Norm:
        # Find current active norm for the exact same dimensions
        current = self.get_active_norm_matching_config(
            norm_key=norm_key,
            product_type=product_type,
            machine_id=machine_id,
            operation_id=operation_id,
            operation_key=operation_key,
            qty_min=qty_min,
            qty_max=qty_max,
            context_key=context_key,
        )
        if current:
            # Close old norm: effective_to = new_effective_from (exclusive)
            current.effective_to = effective_from
            self.db.add(current)

        new_norm = Norm(
            norm_key=norm_key,
            value=value,
            product_type=product_type,
            machine_id=machine_id,
            operation_id=operation_id,
            operation_key=operation_key,
            qty_min=qty_min,
            qty_max=qty_max,
            context=context,
            context_key=context_key,
            effective_from=effective_from,
            effective_to=None,
            note=note,
        )
        self.db.add(new_norm)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return new_norm
