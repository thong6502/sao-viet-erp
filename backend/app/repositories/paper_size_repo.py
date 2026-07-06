"""Paper Size Repository — master data access.

Version-chain (spec E, mirror `imposition_types`): a `code` identifies a FAMILY of paper
sizes; editing the DIMENSIONS of a size already used (used_count>0) creates a new row with the
same `code` and a higher `version`. Unique is (code, version). The "current" row of a family is
the highest version whose effective window covers the lookup date (effective_to NULL = open),
resolved via :meth:`resolve_active`.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import and_, asc, desc, func, or_, select
from sqlalchemy.orm import Session
from ..models.machine import Machine
from ..models.paper_size import PaperSize

_SORTABLE = {
    "code": PaperSize.code,
    "name": PaperSize.name,
    "size_type": PaperSize.size_type,
    "size_group": PaperSize.size_group,
    "width_cm": PaperSize.width_cm,
    "created_at": PaperSize.created_at,
}


def _effective_at(at_date: date):
    """Rows whose effective window covers `at_date` (NULL bounds = open)."""
    return and_(
        or_(PaperSize.effective_from.is_(None), PaperSize.effective_from <= at_date),
        or_(PaperSize.effective_to.is_(None), PaperSize.effective_to > at_date),
    )


def _matches_machine(row: PaperSize, machine_id: int) -> bool:
    ids = row.compatible_machine_ids
    if not ids:
        return True  # NULL / [] = mọi máy
    return machine_id in ids


class PaperSizeRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # -- reads -------------------------------------------------------------
    def get_by_id(self, item_id: int) -> PaperSize | None:
        return self.db.execute(
            select(PaperSize).where(PaperSize.id == item_id)
        ).scalars().first()

    def find_by_code_any_version(self, code: str) -> PaperSize | None:
        """Highest-version row of a code family — for duplicate check on create."""
        code = (code or "").strip()
        if not code:
            return None
        return self.db.execute(
            select(PaperSize)
            .where(func.upper(PaperSize.code) == code.upper())
            .order_by(PaperSize.version.desc())
        ).scalars().first()

    def max_version_for_code(self, code: str) -> int:
        val = self.db.execute(
            select(func.max(PaperSize.version)).where(
                func.upper(PaperSize.code) == (code or "").strip().upper()
            )
        ).scalar()
        return int(val or 0)

    def find_by_name(self, name: str) -> PaperSize | None:
        name = (name or "").strip()
        if not name:
            return None
        return self.db.execute(
            select(PaperSize)
            .where(func.lower(PaperSize.name) == name.lower())
            .order_by(PaperSize.version.desc())
        ).scalars().first()

    def resolve_active(self, *, code: str, at_date: date) -> PaperSize | None:
        """Current row for a code, effective at `at_date`, highest version."""
        if not (code and code.strip()):
            return None
        return self.db.execute(
            select(PaperSize)
            .where(func.upper(PaperSize.code) == code.strip().upper())
            .where(_effective_at(at_date))
            .order_by(PaperSize.version.desc())
        ).scalars().first()

    def list_versions(self, code: str) -> list[PaperSize]:
        """All versions of a code family, newest first (lịch sử)."""
        return list(self.db.execute(
            select(PaperSize)
            .where(func.upper(PaperSize.code) == (code or "").strip().upper())
            .order_by(PaperSize.version.desc())
        ).scalars())

    def get_children(self, parent_id: int) -> list[PaperSize]:
        """Khổ cắt trỏ về khổ cha này (chặn xóa khi còn con)."""
        return list(self.db.execute(
            select(PaperSize).where(PaperSize.parent_size_id == parent_id)
        ).scalars())

    def count_costing_refs(self, paper_size_id: int) -> int:
        """Số phương án giấy (phiếu tính giá) đang tham chiếu khổ này — 'đã dùng'."""
        from ..models.costing import CostingPaperOption
        return int(self.db.execute(
            select(func.count()).select_from(CostingPaperOption).where(
                or_(
                    CostingPaperOption.print_sheet_size_id == paper_size_id,
                    CostingPaperOption.purchase_size_id == paper_size_id,
                )
            )
        ).scalar_one())

    def costing_ref_counts(self, ids: list[int]) -> dict[int, int]:
        """{paper_size_id: số phiếu tính giá (costing DISTINCT) dùng khổ} — cột 'Đang dùng trong'.
        Một lượt quét cho cả trang danh sách (tránh N+1). Đếm phiếu, không đếm dòng phương án."""
        from ..models.costing import CostingPaperOption
        if not ids:
            return {}
        id_set = set(ids)
        buckets: dict[int, set[int]] = {i: set() for i in ids}
        rows = self.db.execute(
            select(
                CostingPaperOption.costing_id,
                CostingPaperOption.print_sheet_size_id,
                CostingPaperOption.purchase_size_id,
            ).where(
                or_(
                    CostingPaperOption.print_sheet_size_id.in_(ids),
                    CostingPaperOption.purchase_size_id.in_(ids),
                )
            )
        )
        for costing_id, psid, purid in rows:
            if psid in id_set:
                buckets[psid].add(costing_id)
            if purid in id_set:
                buckets[purid].add(costing_id)
        return {i: len(s) for i, s in buckets.items()}

    def find_by_dimensions(
        self, *, width_cm: float, height_cm: float, exclude_code: str | None = None,
        at_date: date | None = None,
    ) -> PaperSize | None:
        """Khổ đang hiệu lực trùng kích thước (khớp CẢ 2 CHIỀU, kể cả xoay) — cảnh báo trùng khổ
        (§13). Bỏ qua mọi phiên bản cùng `exclude_code` (đang sửa chính nó)."""
        at_date = at_date or date.today()
        w, h = float(width_cm), float(height_cm)
        excl = (exclude_code or "").strip().upper()
        rows = self.db.execute(
            select(PaperSize).where(_effective_at(at_date)).order_by(PaperSize.version.desc())
        ).scalars()
        for r in rows:
            if excl and (r.code or "").upper() == excl:
                continue
            rw, rh = float(r.width_cm), float(r.height_cm)
            same = (abs(rw - w) < 0.01 and abs(rh - h) < 0.01) or (
                abs(rw - h) < 0.01 and abs(rh - w) < 0.01
            )
            if same:
                return r
        return None

    def list_costings_by_size(self, paper_size_id: int, *, limit: int = 100) -> list:
        """Phiếu tính giá (costings) DISTINCT đang dùng khổ này, mới nhất trước — cho drill-down
        'Xem nơi đang dùng'. Trả list (Costing, product_name|None)."""
        from ..models.costing import Costing, CostingPaperOption
        from ..models.product import Product

        costing_ids = list(self.db.execute(
            select(CostingPaperOption.costing_id).where(
                or_(
                    CostingPaperOption.print_sheet_size_id == paper_size_id,
                    CostingPaperOption.purchase_size_id == paper_size_id,
                )
            )
        ).scalars())
        uniq = list(dict.fromkeys(costing_ids))  # distinct, giữ thứ tự lần đầu gặp
        if not uniq:
            return []
        costings = list(self.db.execute(
            select(Costing)
            .where(Costing.id.in_(uniq))
            .order_by(Costing.created_at.desc(), Costing.id.desc())
        ).scalars())[:limit]
        prod_ids = {c.product_id for c in costings if c.product_id is not None}
        names: dict[int, str] = {}
        if prod_ids:
            names = dict(self.db.execute(
                select(Product.id, Product.name).where(Product.id.in_(prod_ids))
            ))
        return [(c, names.get(c.product_id)) for c in costings]

    def machines_too_small(
        self, *, width_cm: float, height_cm: float, machine_ids: list[int] | None,
        allow_rotation: bool,
    ) -> list[str]:
        """Trả về mã các máy (trong danh sách) mà khổ này KHÔNG lọt (vượt khổ máy)."""
        if not machine_ids:
            return []
        rows = list(self.db.execute(
            select(Machine).where(Machine.id.in_(machine_ids))
        ).scalars())
        bad: list[str] = []
        for m in rows:
            mw, mh = m.max_width_cm, m.max_height_cm
            if mw is None or mh is None:
                continue  # khổ máy chưa khai → bỏ qua
            mw, mh = float(mw), float(mh)
            w, h = float(width_cm), float(height_cm)
            fits = (w <= mw and h <= mh) or (allow_rotation and h <= mw and w <= mh)
            if not fits:
                bad.append(m.code)
        return bad

    def list(
        self,
        *,
        q: str | None = None,
        size_type: str | None = None,
        size_group: str | None = None,
        machine_id: int | None = None,
        is_active: bool | None = None,
        current_only: bool = False,
        sort: str = "code",
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[PaperSize], int]:
        conditions = []
        if q:
            like = f"%{q.strip().lower()}%"
            conditions.append(
                or_(
                    func.lower(PaperSize.name).like(like),
                    func.lower(PaperSize.code).like(like),
                )
            )
        if size_type:
            conditions.append(PaperSize.size_type == size_type)
        if size_group:
            conditions.append(PaperSize.size_group == size_group)
        if is_active is not None:
            conditions.append(PaperSize.is_active == is_active)
        if current_only:
            conditions.append(_effective_at(date.today()))

        direction = asc
        key = sort or "code"
        if key.startswith("-"):
            direction = desc
            key = key[1:]
        col = _SORTABLE.get(key, PaperSize.code)

        # Machine filter lives in a JSON column → portable Python-side filter over the small
        # catalog (paginate in Python). Otherwise use SQL count + limit/offset.
        if machine_id is not None:
            base = select(PaperSize)
            for c in conditions:
                base = base.where(c)
            base = base.order_by(direction(col), PaperSize.code.asc(), PaperSize.id.asc())
            all_rows = [r for r in self.db.execute(base).scalars() if _matches_machine(r, machine_id)]
            total = len(all_rows)
            page = max(1, page)
            size = max(1, min(size, 200))
            start = (page - 1) * size
            return all_rows[start:start + size], total

        base = select(PaperSize)
        count_stmt = select(func.count()).select_from(PaperSize)
        for c in conditions:
            base = base.where(c)
            count_stmt = count_stmt.where(c)
        total = self.db.execute(count_stmt).scalar_one()
        base = base.order_by(direction(col), PaperSize.code.asc(), PaperSize.id.asc())
        page = max(1, page)
        size = max(1, min(size, 200))
        base = base.offset((page - 1) * size).limit(size)
        rows = list(self.db.execute(base).scalars())
        return rows, total

    # -- code generation ---------------------------------------------------
    def _next_code(self) -> str:
        max_n = 0
        for code in self.db.execute(
            select(PaperSize.code).where(PaperSize.code.like("KG%"))
        ).scalars():
            try:
                max_n = max(max_n, int(code[2:]))
            except (ValueError, TypeError):
                continue
        return f"KG{max_n + 1:03d}"

    # -- writes ------------------------------------------------------------
    def create(self, *, code: str, version: int = 1, **fields) -> PaperSize:
        item = PaperSize(code=code.strip(), version=version, **fields)
        self.db.add(item)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return item

    def update(self, item: PaperSize, **fields) -> PaperSize:
        for k, v in fields.items():
            setattr(item, k, v)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return item

    def supersede_and_create_version(
        self, base_item: PaperSize, *, effective_from: date, **fields
    ) -> PaperSize:
        """Version-chain: close the current row (effective_to = date, deactivate) and insert a
        new row with the same code, version+1, effective_from = date, carrying `fields`."""
        new_version = self.max_version_for_code(base_item.code) + 1
        base_item.effective_to = effective_from
        base_item.is_active = False
        new_item = PaperSize(
            code=base_item.code,
            version=new_version,
            effective_from=effective_from,
            **fields,
        )
        self.db.add(new_item)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return new_item

    def increment_used_count(self, item: PaperSize, by: int = 1, commit: bool = True) -> None:
        item.used_count = int(item.used_count or 0) + by
        if commit:
            self.db.commit()

    def delete(self, item: PaperSize) -> None:
        self.db.delete(item)
        self.db.commit()
