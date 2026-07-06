"""Norm Repository — data access for loss and waste norms.
"""
from __future__ import annotations

from datetime import date
from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.orm import Session
from ..models.norm import Norm

# Các khóa chứa norm_id trong calculation_snapshot_json của một dòng chi phí.
_SNAPSHOT_NORM_KEYS = (
    "print_yield_norm_id",
    "makeready_norm_id",
    "print_waste_norm_id",
    "paper_extra_norm_id",
)


def _norm_ids_in_snapshot(snap) -> set[int]:
    """Rút mọi norm_id mà một calculation_snapshot_json tham chiếu (kể cả chuỗi hao ngược)."""
    ids: set[int] = set()
    if not isinstance(snap, dict):
        return ids
    for key in _SNAPSHOT_NORM_KEYS:
        v = snap.get(key)
        if isinstance(v, int):
            ids.add(v)
    for step in snap.get("reverse_waste_chain") or []:
        if isinstance(step, dict):
            for k in ("norm_id", "setup_norm_id"):
                v = step.get(k)
                if isinstance(v, int):
                    ids.add(v)
    return ids


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
        q: str | None = None,
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
        if q and q.strip():
            like = f"%{q.strip()}%"
            conditions.append(
                or_(
                    Norm.code.ilike(like),
                    Norm.name.ilike(like),
                    Norm.norm_key.ilike(like),
                )
            )
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

    def list_open_norms(self) -> list[Norm]:
        """Mọi bản đang mở (effective_to IS NULL) — dùng để dò xung đột phạm vi."""
        return list(self.db.execute(select(Norm).where(Norm.effective_to.is_(None))).scalars())

    def list_history(self, norm: Norm) -> list[Norm]:
        """Chuỗi version của cùng một cấu hình (mọi bản, gồm đã đóng) — cho 'Xem lịch sử'."""
        stmt = (
            select(Norm)
            .where(Norm.norm_key == norm.norm_key)
            .where(Norm.context_key == norm.context_key)
            .where(Norm.product_type == norm.product_type)
            .where(Norm.machine_id == norm.machine_id)
            .where(Norm.operation_id == norm.operation_id)
            .where(Norm.operation_key == norm.operation_key)
            .where(Norm.qty_min == norm.qty_min)
            .where(Norm.qty_max == norm.qty_max)
            .order_by(Norm.effective_from.asc(), Norm.id.asc())
        )
        return list(self.db.execute(stmt).scalars())

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
        **extra,
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
        version = 1
        if current:
            # Close old norm: effective_to = new_effective_from (exclusive) + bump version chain.
            current.effective_to = effective_from
            self.db.add(current)
            version = int(current.version or 1) + 1

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
            version=version,
            **extra,
        )
        self.db.add(new_norm)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return new_norm

    # --- "Đang dùng trong" — quét snapshot tính giá tìm định mức đã dùng (chỉ đọc) --------
    # Định mức chỉ được ghi trong EstimateCostLine.calculation_snapshot_json (không có cột FK),
    # nên đếm bằng cách quét Python-side như Kiểu bình bài — tránh JSON query khác nhau giữa
    # SQLite (dev) và Postgres (prod). Không đụng engine/QuotationService.
    def _scan_norm_usage(self, *, include_cancelled: bool = False) -> dict[int, set[int]]:
        from ..models.estimate import Estimate, EstimateOption, EstimateCostLine

        stmt = (
            select(EstimateCostLine.calculation_snapshot_json, EstimateOption.estimate_id)
            .join(EstimateOption, EstimateCostLine.estimate_option_id == EstimateOption.id)
            .join(Estimate, EstimateOption.estimate_id == Estimate.id)
        )
        if not include_cancelled:
            stmt = stmt.where(Estimate.status != "cancelled")
        by_norm: dict[int, set[int]] = {}
        for snap, est_id in self.db.execute(stmt):
            for nid in _norm_ids_in_snapshot(snap):
                by_norm.setdefault(nid, set()).add(est_id)
        return by_norm

    def estimate_norm_counts(self, *, include_cancelled: bool = False) -> dict[int, int]:
        """{norm_id: số phiếu tính giá (distinct) đang dùng} cho cột 'Đang dùng trong'."""
        return {nid: len(ids) for nid, ids in self._scan_norm_usage(include_cancelled=include_cancelled).items()}

    def list_estimates_by_norm(
        self, norm_id: int, *, include_cancelled: bool = False, limit: int = 100
    ) -> list:
        """Liệt kê phiếu tính giá dùng một định mức (mới nhất trước) — cho drill-down."""
        from ..models.estimate import Estimate

        est_ids = self._scan_norm_usage(include_cancelled=include_cancelled).get(norm_id, set())
        if not est_ids:
            return []
        stmt = (
            select(Estimate)
            .where(Estimate.id.in_(est_ids))
            .order_by(Estimate.created_at.desc(), Estimate.id.desc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars())
