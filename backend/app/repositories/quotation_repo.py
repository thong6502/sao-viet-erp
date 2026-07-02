"""Báo giá (Quotation) data access — spec-09-bao-gia. The ONLY layer that touches the DB
for quotations. SQL goes through SQLAlchemy bound parameters (no string-formatted input).
No business rules here (those live in QuotationService).

Scope note: a quotation is owned by its Sale (`sale_user_id → users.department_id`), so the
`department` data-scope filters on the set of Sale ids in the actor's department, mirroring
the Customer repository (feat-006 apply_scope pattern).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.orm import Session

from ..models.customer import Customer
from ..models.quotation import Quotation
from ..models.role import SCOPE_ALL, SCOPE_DEPARTMENT, SCOPE_OWN
from ..models.user import User

# Columns a caller may sort by (whitelist — never interpolate a raw sort key).
_SORTABLE = {
    "code": Quotation.code,
    "total": Quotation.total,
    "status": Quotation.status,
    "valid_until": Quotation.valid_until,
    "created_at": Quotation.created_at,
}


class QuotationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- reads --------------------------------------------------------------

    def get_by_id(self, quotation_id: int) -> Quotation | None:
        return self.db.get(Quotation, quotation_id)

    def list_approved_selectable(
        self, *, scope: str, actor, today: date, limit: int = 50
    ) -> tuple[list[Quotation], dict[int, str]]:
        """Approved quotations còn hạn (valid_until >= today or null) choosable for an order
        (spec-10 F1). Scoped like `list`. Returns (rows, customer_names). Used by the Đơn
        hàng bán picker via SEAM-04 (quotation_ref reads the live Báo giá)."""
        from ..models.quotation import STATUS_APPROVED

        stmt = select(Quotation).where(Quotation.status == STATUS_APPROVED)
        scope_cond = self._scope_condition(scope=scope, actor=actor)
        if scope_cond is not None:
            stmt = stmt.where(scope_cond)
        stmt = stmt.where(
            or_(Quotation.valid_until.is_(None), Quotation.valid_until >= today)
        ).order_by(Quotation.code.asc(), Quotation.version.desc()).limit(limit)
        rows = list(self.db.execute(stmt).scalars())
        names: dict[int, str] = {}
        if rows:
            for qid, name in self.db.execute(
                select(Quotation.id, Customer.name)
                .join(Customer, Customer.id == Quotation.customer_id)
                .where(Quotation.id.in_([r.id for r in rows]))
            ):
                names[qid] = name
        return rows, names

    def versions_of(self, code: str) -> list[Quotation]:
        """The whole version chain for a code (BG001 v1, v2…), oldest first — for the
        version-history panel."""
        return list(
            self.db.execute(
                select(Quotation)
                .where(Quotation.code == code)
                .order_by(Quotation.version.asc(), Quotation.id.asc())
            ).scalars()
        )

    def _scope_condition(self, *, scope: str, actor):
        """WHERE expression narrowing quotations to a data scope, or None for `all`."""
        if scope == SCOPE_ALL:
            return None
        if scope == SCOPE_OWN:
            return Quotation.sale_user_id == actor.id
        if scope == SCOPE_DEPARTMENT:
            if actor.department_id is None:
                return Quotation.sale_user_id == actor.id
            dept_sales = select(User.id).where(User.department_id == actor.department_id)
            return Quotation.sale_user_id.in_(dept_sales)
        raise ValueError(f"Unknown scope: {scope!r}")

    def can_access(self, *, quotation: Quotation, scope: str, actor) -> bool:
        """Whether `actor` may see this one quotation under `scope` (detail/edit guard)."""
        if scope == SCOPE_ALL:
            return True
        if scope == SCOPE_OWN:
            return quotation.sale_user_id == actor.id
        if scope == SCOPE_DEPARTMENT:
            if quotation.sale_user_id is None:
                return False
            if quotation.sale_user_id == actor.id:
                return True
            owner = self.db.get(User, quotation.sale_user_id)
            return owner is not None and owner.department_id == actor.department_id
        raise ValueError(f"Unknown scope: {scope!r}")

    def list(
        self,
        *,
        scope: str,
        actor,
        q: str | None = None,
        status: str | None = None,
        sort: str = "-created_at",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Quotation], int, dict[int, str]]:
        """Return (rows, total, customer_names). `q` matches code + customer name
        (case-insensitive substring). `status` is an exact filter. `total` is the count
        BEFORE pagination. `customer_names` maps quotation_id → customer name for the page
        (one query, no N+1) so the list can show the khách column without a per-row SEAM
        call (a display read is not a fabricated business value)."""
        conditions = []
        scope_cond = self._scope_condition(scope=scope, actor=actor)
        if scope_cond is not None:
            conditions.append(scope_cond)

        base = select(Quotation)
        count_stmt = select(func.count()).select_from(Quotation)
        if q:
            like = f"%{q.strip().lower()}%"
            cust_ids = select(Customer.id).where(
                func.lower(Customer.name).like(like)
            )
            q_cond = or_(
                func.lower(Quotation.code).like(like),
                Quotation.customer_id.in_(cust_ids),
            )
            conditions.append(q_cond)
        if status:
            conditions.append(Quotation.status == status)

        for c in conditions:
            base = base.where(c)
            count_stmt = count_stmt.where(c)

        total = self.db.execute(count_stmt).scalar_one()

        direction = asc
        key = sort or "-created_at"
        if key.startswith("-"):
            direction = desc
            key = key[1:]
        col = _SORTABLE.get(key, Quotation.created_at)
        base = base.order_by(direction(col), Quotation.id.asc())

        page = max(1, page)
        size = max(1, min(size, 200))
        base = base.offset((page - 1) * size).limit(size)

        rows = list(self.db.execute(base).scalars())

        names: dict[int, str] = {}
        cust_ids_on_page = [r.customer_id for r in rows if r.customer_id is not None]
        if cust_ids_on_page:
            for qid, name in self.db.execute(
                select(Quotation.id, Customer.name)
                .join(Customer, Customer.id == Quotation.customer_id)
                .where(Quotation.id.in_([r.id for r in rows]))
            ):
                names[qid] = name
        return rows, total, names

    # --- writes -------------------------------------------------------------

    def _next_code(self) -> str:
        """Next sequential quotation code: 'BG' + zero-padded number (BG001, BG002…). A new
        quotation gets a fresh code; a re-quote (change_order) reuses the code + bumps
        version, so the max is taken over DISTINCT codes (not rows)."""
        max_n = 0
        for code in self.db.execute(select(Quotation.code).distinct()).scalars():
            if code and code.startswith("BG"):
                try:
                    max_n = max(max_n, int(code[2:]))
                except ValueError:
                    continue
        return f"BG{max_n + 1:03d}"

    def create(
        self,
        *,
        customer_id: int | None,
        costing_id: int | None,
        cost_von_total: int | None,
        margin: int,
        discount: int,
        total: int | None,
        valid_until: date | None,
        sale_user_id: int | None,
        code: str | None = None,
        version: int = 1,
        status: str,
    ) -> Quotation:
        quotation = Quotation(
            code=code or self._next_code(),
            version=version,
            customer_id=customer_id,
            costing_id=costing_id,
            cost_von_total=cost_von_total,
            margin=margin,
            discount=discount,
            total=total,
            valid_until=valid_until,
            sale_user_id=sale_user_id,
            status=status,
            row_version=1,
        )
        self.db.add(quotation)
        self.db.commit()
        self.db.refresh(quotation)
        return quotation

    def update(self, quotation: Quotation, **fields) -> Quotation:
        """Assign the given attributes (code/version are never among them for an edit) and
        bump row_version. Callers that already checked the optimistic version pass the new
        field set here."""
        for key, value in fields.items():
            setattr(quotation, key, value)
        quotation.row_version = (quotation.row_version or 0) + 1
        self.db.commit()
        self.db.refresh(quotation)
        return quotation
