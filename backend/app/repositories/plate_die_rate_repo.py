"""Plate/Die Rate Repository — Đơn giá kẽm & khuôn.

Family key = `code` (một bản MỞ duy nhất mỗi mã). Versioning hiệu lực-theo-ngày: tạo bản mới
tự đóng bản đang mở của cùng mã. Kẽm chọn theo MÁY qua :meth:`resolve_plate_for_machine`.
"""
from __future__ import annotations

from datetime import date
from sqlalchemy import asc, func, or_, select
from sqlalchemy.orm import Session
from ..models.plate_die_rate import PLATE_KEM, PlateDieRate

# Field client được phép gán khi tạo/version (audit/effective/used_count do server quản).
ASSIGNABLE = (
    "name", "plate_type", "technology", "unit", "plate_kind",
    "plate_width_mm", "plate_height_mm", "machine_ids", "paper_size_ids",
    "unit_price", "setup_fee", "min_charge",
    "pricing_method", "unit_price_area", "unit_price_perimeter", "max_charge", "allow_manual_price",
    "reusable", "reuse_price_method", "maintenance_fee",
    "supplier", "lead_time_days", "transport_fee", "moq", "is_active",
)


class PlateDieRateRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, rate_id: int) -> PlateDieRate | None:
        return self.db.get(PlateDieRate, rate_id)

    def get_open_for_code(self, code: str) -> PlateDieRate | None:
        return self.db.execute(
            select(PlateDieRate)
            .where(func.upper(PlateDieRate.code) == (code or "").strip().upper())
            .where(PlateDieRate.effective_to.is_(None))
        ).scalars().first()

    def find_by_code_any(self, code: str) -> PlateDieRate | None:
        return self.db.execute(
            select(PlateDieRate)
            .where(func.upper(PlateDieRate.code) == (code or "").strip().upper())
            .order_by(PlateDieRate.effective_from.desc(), PlateDieRate.id.desc())
        ).scalars().first()

    def get_rate_at_date(self, code: str, at_date: date) -> PlateDieRate | None:
        return self.db.execute(
            select(PlateDieRate)
            .where(func.upper(PlateDieRate.code) == (code or "").strip().upper())
            .where(PlateDieRate.effective_from <= at_date)
            .where(or_(PlateDieRate.effective_to.is_(None), PlateDieRate.effective_to > at_date))
            .order_by(PlateDieRate.effective_from.desc(), PlateDieRate.id.desc())
        ).scalars().first()

    def get_closed_rate_covering(self, code: str, at_date: date) -> PlateDieRate | None:
        """Bản ĐÃ ĐÓNG (cùng mã) mà [from,to) chứa at_date — chặn chồng lấn."""
        return self.db.execute(
            select(PlateDieRate)
            .where(func.upper(PlateDieRate.code) == (code or "").strip().upper())
            .where(PlateDieRate.effective_to.isnot(None))
            .where(PlateDieRate.effective_from <= at_date)
            .where(PlateDieRate.effective_to > at_date)
        ).scalars().first()

    def find_predecessor(self, rate: PlateDieRate) -> PlateDieRate | None:
        """Bản (cùng mã) mà `rate` đã đóng — effective_to == rate.effective_from."""
        return self.db.execute(
            select(PlateDieRate)
            .where(PlateDieRate.id != rate.id)
            .where(func.upper(PlateDieRate.code) == rate.code.upper())
            .where(PlateDieRate.effective_to == rate.effective_from)
        ).scalars().first()

    def list_versions(self, code: str) -> list[PlateDieRate]:
        return list(self.db.execute(
            select(PlateDieRate)
            .where(func.upper(PlateDieRate.code) == (code or "").strip().upper())
            .order_by(PlateDieRate.effective_from.desc(), PlateDieRate.id.desc())
        ).scalars())

    def resolve_plate_for_machine(self, machine_id: int | None, at_date: date) -> PlateDieRate | None:
        """Chọn giá KẼM offset hiệu lực cho máy: ưu tiên bản khai đúng máy, sau đó bản mọi-máy
        (machine_ids NULL/[]). KHÔNG có fallback ẩn nào khác."""
        rows = list(self.db.execute(
            select(PlateDieRate)
            .where(PlateDieRate.plate_type == PLATE_KEM)
            .where(PlateDieRate.effective_from <= at_date)
            .where(or_(PlateDieRate.effective_to.is_(None), PlateDieRate.effective_to > at_date))
            .order_by(PlateDieRate.effective_from.desc(), PlateDieRate.id.desc())
        ).scalars())
        specific, generic = None, None
        for r in rows:
            ids = r.machine_ids
            if ids and machine_id is not None and machine_id in ids:
                specific = specific or r
            elif not ids:
                generic = generic or r
        return specific or generic

    def count_operation_refs(self, rate_id: int) -> int:
        """Số công đoạn (Operation.tooling_rate_id) đang trỏ tới khổ/khuôn này — 'đã dùng'."""
        from ..models.operation import Operation
        return int(self.db.execute(
            select(func.count()).select_from(Operation).where(Operation.tooling_rate_id == rate_id)
        ).scalar_one())

    # -- "Đang dùng trong" (2 cơ chế) -------------------------------------
    def operation_ref_counts(self, ids: list[int]) -> dict[int, int]:
        """{rate_id: số công đoạn dùng KHUÔN} — bulk cho cột 'Đang dùng trong' tab khuôn."""
        from ..models.operation import Operation
        if not ids:
            return {}
        out = {i: 0 for i in ids}
        rows = self.db.execute(
            select(Operation.tooling_rate_id, func.count())
            .where(Operation.tooling_rate_id.in_(ids))
            .group_by(Operation.tooling_rate_id)
        )
        for rate_id, n in rows:
            if rate_id in out:
                out[rate_id] = int(n)
        return out

    def estimate_ref_counts(self, ids: list[int]) -> dict[int, int]:
        """{rate_id: số phiếu tính giá DISTINCT dùng KẼM} — engine ghi cost-line
        source_type='plate_die_rates' + source_id=rate.id (kẽm chọn động theo máy)."""
        from ..models.estimate import EstimateCostLine, EstimateOption
        if not ids:
            return {}
        buckets: dict[int, set[int]] = {i: set() for i in ids}
        rows = self.db.execute(
            select(EstimateCostLine.source_id, EstimateOption.estimate_id)
            .join(EstimateOption, EstimateCostLine.estimate_option_id == EstimateOption.id)
            .where(EstimateCostLine.source_type == "plate_die_rates")
            .where(EstimateCostLine.source_id.in_(ids))
        )
        for rate_id, est_id in rows:
            if rate_id in buckets:
                buckets[rate_id].add(est_id)
        return {i: len(s) for i, s in buckets.items()}

    def list_estimates_by_rate(self, rate_id: int, *, limit: int = 100) -> list:
        """Phiếu tính giá DISTINCT dùng kẽm này, mới nhất trước — drill-down 'Xem nơi đang dùng'."""
        from ..models.estimate import Estimate, EstimateCostLine, EstimateOption
        est_ids = list(self.db.execute(
            select(EstimateOption.estimate_id)
            .join(EstimateCostLine, EstimateCostLine.estimate_option_id == EstimateOption.id)
            .where(EstimateCostLine.source_type == "plate_die_rates")
            .where(EstimateCostLine.source_id == rate_id)
        ).scalars())
        uniq = list(dict.fromkeys(est_ids))
        if not uniq:
            return []
        return list(self.db.execute(
            select(Estimate).where(Estimate.id.in_(uniq))
            .order_by(Estimate.created_at.desc(), Estimate.id.desc())
        ).scalars())[:limit]

    def list_operations_by_rate(self, rate_id: int, *, limit: int = 100) -> list:
        """Công đoạn dùng khuôn này — drill-down 'Xem nơi đang dùng'."""
        from ..models.operation import Operation
        return list(self.db.execute(
            select(Operation).where(Operation.tooling_rate_id == rate_id).order_by(Operation.name)
        ).scalars())[:limit]

    def list_rates(
        self,
        *,
        q: str | None = None,
        plate_type: str | None = None,
        technology: str | None = None,
        machine_id: int | None = None,
        is_active: bool | None = None,
        current_only: bool = False,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[PlateDieRate], int]:
        conditions = []
        if q:
            like = f"%{q.strip().lower()}%"
            conditions.append(or_(
                func.lower(PlateDieRate.code).like(like),
                func.lower(PlateDieRate.name).like(like),
            ))
        if plate_type:
            conditions.append(PlateDieRate.plate_type == plate_type)
        if technology:
            conditions.append(PlateDieRate.technology == technology)
        if is_active is not None:
            conditions.append(PlateDieRate.is_active == is_active)
        if current_only:
            conditions.append(PlateDieRate.effective_to.is_(None))

        order = (
            asc(PlateDieRate.plate_type), asc(PlateDieRate.code),
            PlateDieRate.effective_from.desc(),
        )
        page = max(1, page)
        size = max(1, min(size, 200))

        if machine_id is not None:
            stmt = select(PlateDieRate)
            for c in conditions:
                stmt = stmt.where(c)
            stmt = stmt.order_by(*order)
            allrows = [r for r in self.db.execute(stmt).scalars()
                       if not r.machine_ids or machine_id in r.machine_ids]
            total = len(allrows)
            start = (page - 1) * size
            return allrows[start:start + size], total

        stmt = select(PlateDieRate)
        count_stmt = select(func.count()).select_from(PlateDieRate)
        for c in conditions:
            stmt = stmt.where(c)
            count_stmt = count_stmt.where(c)
        total = self.db.execute(count_stmt).scalar_one()
        stmt = stmt.order_by(*order).offset((page - 1) * size).limit(size)
        return list(self.db.execute(stmt).scalars()), total

    def add_rate(self, *, code: str, effective_from: date, **fields) -> PlateDieRate:
        """Tạo bản mới; tự đóng bản đang mở của cùng mã (effective_to = effective_from)."""
        current = self.get_open_for_code(code)
        if current:
            current.effective_to = effective_from
            self.db.add(current)
        new_rate = PlateDieRate(
            code=code.strip(), effective_from=effective_from, effective_to=None, **fields
        )
        self.db.add(new_rate)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return new_rate

    def increment_used_count(self, rate: PlateDieRate, by: int = 1, commit: bool = True) -> None:
        rate.used_count = int(rate.used_count or 0) + by
        if commit:
            self.db.commit()
