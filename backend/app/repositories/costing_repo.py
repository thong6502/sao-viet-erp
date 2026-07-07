"""Tính giá (Costing) data access — spec-08-tinh-gia. The ONLY layer that touches the DB
for costings. SQL goes through SQLAlchemy bound parameters (no string-formatted input). No
business rules here (those live in CostingService).

Costings are a global working master (không phạm vi own/department at P0 — estimator dùng
chung), filtered by q (mã) + product_id + status.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import Session, selectinload

from ..models.costing import Costing, CostingOperation, CostingPaperOption

# Columns a caller may sort by (whitelist — never interpolate a raw sort key).
_SORTABLE = {
    "code": Costing.code,
    "qty_final": Costing.qty_final,
    "status": Costing.status,
    "created_at": Costing.created_at,
}


@dataclass
class PaperOptionInput:
    """A single phương án giấy to persist (validated already by the service)."""

    sheet_paper_master_id: int | None
    sheet_w: float
    sheet_h: float
    pieces_per_sheet: int
    grain_locked: bool
    selected: bool = False


@dataclass
class OperationInput:
    """A single công đoạn gia công to persist (validated already by the service)."""

    name: str
    execution_mode: str
    sequence: int = 0


@dataclass
class CostingInput:
    """The costing header fields to persist (validated already by the service)."""

    product_id: int | None
    qty_final: int
    status: str
    note: str | None
    paper_options: list[PaperOptionInput] = field(default_factory=list)
    operations: list[OperationInput] = field(default_factory=list)


class CostingRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- reads --------------------------------------------------------------

    def get_by_id(self, costing_id: int) -> Costing | None:
        """Load a costing with its paper options + operations eagerly."""
        return self.db.execute(
            select(Costing)
            .options(
                selectinload(Costing.paper_options),
                selectinload(Costing.operations),
            )
            .where(Costing.id == costing_id)
        ).scalars().first()

    def list(
        self,
        *,
        q: str | None = None,
        product_id: int | None = None,
        status: str | None = None,
        sort: str = "code",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Costing], int, dict[int, int]]:
        """Return (rows, total, paper_option_counts). `q` matches code (case-insensitive
        substring); `product_id` / `status` are exact filters. `total` is the count BEFORE
        pagination. `paper_option_counts` maps costing_id → số phương án giấy for the page
        (one grouped query, no N+1)."""
        conditions = []
        if q:
            like = f"%{q.strip().lower()}%"
            conditions.append(func.lower(Costing.code).like(like))
        if product_id is not None:
            conditions.append(Costing.product_id == product_id)
        if status:
            conditions.append(Costing.status == status)

        base = select(Costing)
        count_stmt = select(func.count()).select_from(Costing)
        for c in conditions:
            base = base.where(c)
            count_stmt = count_stmt.where(c)

        total = self.db.execute(count_stmt).scalar_one()

        direction = asc
        key = sort or "code"
        if key.startswith("-"):
            direction = desc
            key = key[1:]
        col = _SORTABLE.get(key, Costing.code)
        base = base.order_by(direction(col), Costing.id.asc())

        page = max(1, page)
        size = max(1, min(size, 200))
        base = base.offset((page - 1) * size).limit(size)

        rows = list(
            self.db.execute(
                base.options(selectinload(Costing.paper_options))
            ).scalars()
        )

        counts: dict[int, int] = {}
        if rows:
            ids = [c.id for c in rows]
            for cid, n in self.db.execute(
                select(CostingPaperOption.costing_id, func.count())
                .where(CostingPaperOption.costing_id.in_(ids))
                .group_by(CostingPaperOption.costing_id)
            ):
                counts[cid] = n
        return rows, total, counts

    def count_for_product(self, product_id: int) -> int:
        return self.db.execute(
            select(func.count())
            .select_from(Costing)
            .where(Costing.product_id == product_id)
        ).scalar_one()

    # --- writes -------------------------------------------------------------

    def _next_code(self) -> str:
        """Next sequential costing code: 'CG' + zero-padded number (CG001, CG002…).

        Based on the max existing CG-number so codes stay unique even after deletions
        (no reuse), following the SP###/KH###/PB### pattern."""
        max_n = 0
        for code in self.db.execute(select(Costing.code)).scalars():
            if code and code.startswith("CG"):
                try:
                    max_n = max(max_n, int(code[2:]))
                except ValueError:
                    continue
        return f"CG{max_n + 1:03d}"

    def create(self, data: CostingInput) -> Costing:
        """Create a costing header + its paper options + operations in ONE transaction. If
        any part fails the whole thing rolls back — no orphan header without its children."""
        costing = Costing(
            code=self._next_code(),
            product_id=data.product_id,
            qty_final=data.qty_final,
            status=data.status,
            note=data.note,
        )
        for p in data.paper_options:
            costing.paper_options.append(self._to_paper(p))
        for o in data.operations:
            costing.operations.append(self._to_operation(o))
        self.db.add(costing)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return self.get_by_id(costing.id)

    def update(self, costing: Costing, data: CostingInput) -> Costing:
        """Replace the header fields + the whole child set (delete-orphan removes rows no
        longer present) in one transaction. Mã is never touched."""
        costing.product_id = data.product_id
        costing.qty_final = data.qty_final
        costing.status = data.status
        costing.note = data.note
        costing.paper_options.clear()
        for p in data.paper_options:
            costing.paper_options.append(self._to_paper(p))
        costing.operations.clear()
        for o in data.operations:
            costing.operations.append(self._to_operation(o))
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return self.get_by_id(costing.id)

    def delete(self, costing: Costing) -> None:
        """Delete the costing; its children cascade (delete-orphan / FK ON DELETE)."""
        self.db.delete(costing)
        self.db.commit()

    @staticmethod
    def _to_paper(p: PaperOptionInput) -> CostingPaperOption:
        return CostingPaperOption(
            sheet_paper_master_id=p.sheet_paper_master_id,
            sheet_w=p.sheet_w,
            sheet_h=p.sheet_h,
            pieces_per_sheet=p.pieces_per_sheet,
            grain_locked=p.grain_locked,
            selected=p.selected,
        )

    @staticmethod
    def _to_operation(o: OperationInput) -> CostingOperation:
        return CostingOperation(
            name=o.name,
            execution_mode=o.execution_mode,
            sequence=o.sequence,
        )
