"""Customer data access (Khách hàng / CRM) — the ONLY layer that touches the DB for
customers. SQL goes through SQLAlchemy bound parameters (no string-formatted input).
No business rules here (those live in CustomerService).

Scope note: a customer's "department" is the department of its owning Sale
(`sale_user_id → users.department_id`), so the `department` data-scope filters on the
set of Sale ids in the actor's department rather than on a column of `customers`.
"""
from __future__ import annotations

from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.orm import Session

from ..models.customer import Customer
from ..models.role import SCOPE_ALL, SCOPE_DEPARTMENT, SCOPE_OWN
from ..models.user import User

# Columns a caller may sort by (whitelist — never interpolate a raw sort key).
_SORTABLE = {
    "code": Customer.code,
    "name": Customer.name,
    "tax_code": Customer.tax_code,
    "credit_limit": Customer.credit_limit,
    "created_at": Customer.created_at,
}


class CustomerRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- reads --------------------------------------------------------------

    def get_by_id(self, customer_id: int) -> Customer | None:
        return self.db.get(Customer, customer_id)

    def find_by_tax_code(self, tax_code: str) -> Customer | None:
        """First customer carrying this MST, for the soft duplicate warning. Returns
        None for an empty MST (khách lẻ). Does NOT enforce uniqueness — that is a
        deliberate soft check, not a DB constraint (§34 L885)."""
        if not tax_code:
            return None
        return self.db.execute(
            select(Customer).where(Customer.tax_code == tax_code).order_by(Customer.id)
        ).scalars().first()

    def _scope_condition(self, *, scope: str, actor):
        """The WHERE expression narrowing customers to a data scope, or None for `all`.

        `own`        → customers whose owning Sale is the actor.
        `department` → customers whose owning Sale sits in the actor's department.
        """
        if scope == SCOPE_ALL:
            return None
        if scope == SCOPE_OWN:
            return Customer.sale_user_id == actor.id
        if scope == SCOPE_DEPARTMENT:
            if actor.department_id is None:
                # No department → can only see own (avoids leaking the whole table).
                return Customer.sale_user_id == actor.id
            dept_sales = select(User.id).where(User.department_id == actor.department_id)
            return Customer.sale_user_id.in_(dept_sales)
        raise ValueError(f"Unknown scope: {scope!r}")

    def can_access(self, *, customer: Customer, scope: str, actor) -> bool:
        """Whether `actor` may see this one customer under `scope` (detail/edit guard)."""
        if scope == SCOPE_ALL:
            return True
        if scope == SCOPE_OWN:
            return customer.sale_user_id == actor.id
        if scope == SCOPE_DEPARTMENT:
            if customer.sale_user_id is None:
                return False
            if customer.sale_user_id == actor.id:
                return True
            owner = self.db.get(User, customer.sale_user_id)
            return owner is not None and owner.department_id == actor.department_id
        raise ValueError(f"Unknown scope: {scope!r}")

    def list(
        self,
        *,
        scope: str,
        actor,
        q: str | None = None,
        sale_user_id: int | None = None,
        sort: str = "code",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Customer], int]:
        """Return (rows, total) for the scoped, filtered, sorted, paginated list.

        `q` matches name / tax_code / phone (case-insensitive substring). `sale_user_id`
        is an optional additional filter (the "lọc theo Sale" control). `total` is the
        count BEFORE pagination so the UI can render page counts.
        """
        conditions = []
        scope_cond = self._scope_condition(scope=scope, actor=actor)
        if scope_cond is not None:
            conditions.append(scope_cond)

        if q:
            like = f"%{q.strip().lower()}%"
            conditions.append(
                or_(
                    func.lower(Customer.name).like(like),
                    func.lower(func.coalesce(Customer.tax_code, "")).like(like),
                    func.lower(func.coalesce(Customer.phone, "")).like(like),
                )
            )
        if sale_user_id is not None:
            conditions.append(Customer.sale_user_id == sale_user_id)

        base = select(Customer)
        count_stmt = select(func.count()).select_from(Customer)
        for c in conditions:
            base = base.where(c)
            count_stmt = count_stmt.where(c)

        total = self.db.execute(count_stmt).scalar_one()

        # Sort: "-field" for descending; unknown/blank falls back to code asc.
        direction = asc
        key = sort or "code"
        if key.startswith("-"):
            direction = desc
            key = key[1:]
        col = _SORTABLE.get(key, Customer.code)
        # Tie-break on id so pagination is stable.
        base = base.order_by(direction(col), Customer.id.asc())

        page = max(1, page)
        size = max(1, min(size, 200))
        base = base.offset((page - 1) * size).limit(size)

        rows = list(self.db.execute(base).scalars())
        return rows, total

    def list_scoped_all(self, *, scope: str, actor) -> list[Customer]:
        """Every customer visible under the caller's scope (no pagination) — for the KPI
        header roll-up which must reflect the whole book, not just the current page."""
        stmt = select(Customer)
        cond = self._scope_condition(scope=scope, actor=actor)
        if cond is not None:
            stmt = stmt.where(cond)
        return list(self.db.execute(stmt).scalars())

    # --- writes -------------------------------------------------------------

    def _next_code(self) -> str:
        """Next sequential customer code: 'KH' + zero-padded number (KH001, KH002…).

        Based on the max existing KH-number so codes stay unique even after deletions
        (no reuse), following the PB### pattern of feat-023.
        """
        max_n = 0
        for code in self.db.execute(select(Customer.code)).scalars():
            if code and code.startswith("KH"):
                try:
                    max_n = max(max_n, int(code[2:]))
                except ValueError:
                    continue
        return f"KH{max_n + 1:03d}"

    def create(
        self,
        *,
        name: str,
        tax_code: str | None,
        phone: str | None,
        email: str | None,
        address: str | None,
        contact_name: str | None,
        credit_limit: int,
        sale_user_id: int | None,
        status: str,
    ) -> Customer:
        customer = Customer(
            code=self._next_code(),
            name=name,
            tax_code=tax_code,
            phone=phone,
            email=email,
            address=address,
            contact_name=contact_name,
            credit_limit=credit_limit,
            sale_user_id=sale_user_id,
            status=status,
        )
        self.db.add(customer)
        self.db.commit()
        self.db.refresh(customer)
        return customer

    def update(self, customer: Customer, **fields) -> Customer:
        """Assign the given attributes (code is never among them) and persist."""
        for key, value in fields.items():
            setattr(customer, key, value)
        self.db.commit()
        self.db.refresh(customer)
        return customer
