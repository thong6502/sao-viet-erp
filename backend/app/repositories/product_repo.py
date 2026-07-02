"""Product (Sản phẩm in) data access — spec-07-san-pham. The ONLY layer that touches
the DB for products. SQL goes through SQLAlchemy bound parameters (no string-formatted
input). No business rules here (those live in ProductService).

Products are a global reusable master (không phạm vi own/department — SP dùng lại chung),
so the list is not scoped by owner the way customers are; it is filtered by q (name/code)
and product_type only (§34 L898).
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..models.product import Product, ProductComponent

# Columns a caller may sort by (whitelist — never interpolate a raw sort key).
_SORTABLE = {
    "code": Product.code,
    "name": Product.name,
    "product_type": Product.product_type,
    "created_at": Product.created_at,
}


@dataclass
class ComponentInput:
    """A single component row to persist (validated already by the service)."""

    component_type: str
    paper_master_id: int | None
    colors_front: int
    colors_back: int
    page_count: int
    finished_w: float
    finished_h: float
    bleed: float
    grain_direction: str | None
    sequence: int


class ProductRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- reads --------------------------------------------------------------

    def get_by_id(self, product_id: int) -> Product | None:
        """Load a product with its components eagerly (ordered by sequence)."""
        return self.db.execute(
            select(Product)
            .options(selectinload(Product.components))
            .where(Product.id == product_id)
        ).scalars().first()

    def find_by_name(self, name: str) -> Product | None:
        """First product with this exact name (case-insensitive) — for the duplicate
        check. Returns None for a blank name."""
        name = (name or "").strip()
        if not name:
            return None
        return self.db.execute(
            select(Product)
            .where(func.lower(Product.name) == name.lower())
            .order_by(Product.id)
        ).scalars().first()

    def list(
        self,
        *,
        q: str | None = None,
        product_type: str | None = None,
        sort: str = "code",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Product], int, dict[int, int]]:
        """Return (rows, total, component_counts). `q` matches name / code
        (case-insensitive substring); `product_type` is an exact filter. `total` is the
        count BEFORE pagination. `component_counts` maps product_id → số cấu phần for the
        page (one grouped query, no N+1)."""
        conditions = []
        if q:
            like = f"%{q.strip().lower()}%"
            conditions.append(
                or_(
                    func.lower(Product.name).like(like),
                    func.lower(Product.code).like(like),
                )
            )
        if product_type:
            conditions.append(Product.product_type == product_type)

        base = select(Product)
        count_stmt = select(func.count()).select_from(Product)
        for c in conditions:
            base = base.where(c)
            count_stmt = count_stmt.where(c)

        total = self.db.execute(count_stmt).scalar_one()

        direction = asc
        key = sort or "code"
        if key.startswith("-"):
            direction = desc
            key = key[1:]
        col = _SORTABLE.get(key, Product.code)
        base = base.order_by(direction(col), Product.id.asc())

        page = max(1, page)
        size = max(1, min(size, 200))
        base = base.offset((page - 1) * size).limit(size)

        rows = list(self.db.execute(base).scalars())

        counts: dict[int, int] = {}
        if rows:
            ids = [p.id for p in rows]
            for pid, n in self.db.execute(
                select(ProductComponent.product_id, func.count())
                .where(ProductComponent.product_id.in_(ids))
                .group_by(ProductComponent.product_id)
            ):
                counts[pid] = n
        return rows, total, counts

    def component_count(self, product_id: int) -> int:
        return self.db.execute(
            select(func.count())
            .select_from(ProductComponent)
            .where(ProductComponent.product_id == product_id)
        ).scalar_one()

    # --- writes -------------------------------------------------------------

    def _next_code(self) -> str:
        """Next sequential product code: 'SP' + zero-padded number (SP001, SP002…).

        Based on the max existing SP-number so codes stay unique even after deletions
        (no reuse), following the KH###/PB### pattern."""
        max_n = 0
        for code in self.db.execute(select(Product.code)).scalars():
            if code and code.startswith("SP"):
                try:
                    max_n = max(max_n, int(code[2:]))
                except ValueError:
                    continue
        return f"SP{max_n + 1:03d}"

    def create(
        self,
        *,
        name: str,
        product_type: str,
        binding_type: str | None,
        note: str | None,
        components: list[ComponentInput],
    ) -> Product:
        """Create a product + its components in ONE transaction. If any part fails the
        whole thing rolls back — no orphan product without its components."""
        product = Product(
            code=self._next_code(),
            name=name,
            product_type=product_type,
            binding_type=binding_type,
            note=note,
        )
        for c in components:
            product.components.append(self._to_row(c))
        self.db.add(product)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        # Reload with components eagerly for the response.
        return self.get_by_id(product.id)

    def update(
        self,
        product: Product,
        *,
        name: str,
        product_type: str,
        binding_type: str | None,
        note: str | None,
        components: list[ComponentInput],
    ) -> Product:
        """Replace the head fields + the whole component set (delete-orphan removes rows
        no longer present) in one transaction. Mã is never touched."""
        product.name = name
        product.product_type = product_type
        product.binding_type = binding_type
        product.note = note
        # Full-replace the children: clearing the collection deletes the old rows
        # (cascade delete-orphan), then re-append the new set.
        product.components.clear()
        for c in components:
            product.components.append(self._to_row(c))
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return self.get_by_id(product.id)

    def delete(self, product: Product) -> None:
        """Delete the product; its components cascade (delete-orphan / FK ON DELETE)."""
        self.db.delete(product)
        self.db.commit()

    @staticmethod
    def _to_row(c: ComponentInput) -> ProductComponent:
        return ProductComponent(
            sequence=c.sequence,
            component_type=c.component_type,
            paper_master_id=c.paper_master_id,
            colors_front=c.colors_front,
            colors_back=c.colors_back,
            page_count=c.page_count,
            finished_w=c.finished_w,
            finished_h=c.finished_h,
            bleed=c.bleed,
            grain_direction=c.grain_direction,
        )
