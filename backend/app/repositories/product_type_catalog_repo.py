"""Product Type Catalog Repository — master data access.
"""
from __future__ import annotations

from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.orm import Session
from ..models.product_type_catalog import ProductTypeCatalog

_SORTABLE = {
    "product_type": ProductTypeCatalog.product_type,
    "name": ProductTypeCatalog.name,
    "calculation_strategy": ProductTypeCatalog.calculation_strategy,
    "created_at": ProductTypeCatalog.created_at,
}

class ProductTypeCatalogRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, item_id: int) -> ProductTypeCatalog | None:
        return self.db.execute(
            select(ProductTypeCatalog).where(ProductTypeCatalog.id == item_id)
        ).scalars().first()

    def get_by_type(self, product_type: str) -> ProductTypeCatalog | None:
        return self.db.execute(
            select(ProductTypeCatalog).where(ProductTypeCatalog.product_type == product_type)
        ).scalars().first()

    def find_by_name(self, name: str) -> ProductTypeCatalog | None:
        name = (name or "").strip()
        if not name:
            return None
        return self.db.execute(
            select(ProductTypeCatalog)
            .where(func.lower(ProductTypeCatalog.name) == name.lower())
        ).scalars().first()

    def list(
        self,
        *,
        q: str | None = None,
        is_active: bool | None = None,
        sort: str = "product_type",
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[ProductTypeCatalog], int]:
        conditions = []
        if q:
            like = f"%{q.strip().lower()}%"
            conditions.append(
                or_(
                    func.lower(ProductTypeCatalog.name).like(like),
                    func.lower(ProductTypeCatalog.product_type).like(like),
                )
            )
        if is_active is not None:
            conditions.append(ProductTypeCatalog.is_active == is_active)

        base = select(ProductTypeCatalog)
        count_stmt = select(func.count()).select_from(ProductTypeCatalog)
        
        for c in conditions:
            base = base.where(c)
            count_stmt = count_stmt.where(c)

        total = self.db.execute(count_stmt).scalar_one()

        direction = asc
        key = sort or "product_type"
        if key.startswith("-"):
            direction = desc
            key = key[1:]
        col = _SORTABLE.get(key, ProductTypeCatalog.product_type)
        base = base.order_by(direction(col), ProductTypeCatalog.id.asc())

        page = max(1, page)
        size = max(1, min(size, 200))
        base = base.offset((page - 1) * size).limit(size)

        rows = list(self.db.execute(base).scalars())
        return rows, total

    def create(
        self,
        *,
        product_type: str,
        name: str,
        calculation_strategy: str,
        required_fields: list[str] | None = None,
        default_operations: list[str] | None = None,
        allowed_materials: list[str] | None = None,
        compatible_technologies: list[str] | None = None,
        is_active: bool = True,
    ) -> ProductTypeCatalog:
        item = ProductTypeCatalog(
            product_type=product_type,
            name=name,
            calculation_strategy=calculation_strategy,
            required_fields=required_fields,
            default_operations=default_operations,
            allowed_materials=allowed_materials,
            compatible_technologies=compatible_technologies,
            is_active=is_active,
        )
        self.db.add(item)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return item

    def update(
        self,
        item: ProductTypeCatalog,
        *,
        name: str,
        calculation_strategy: str,
        required_fields: list[str] | None = None,
        default_operations: list[str] | None = None,
        allowed_materials: list[str] | None = None,
        compatible_technologies: list[str] | None = None,
        is_active: bool | None = None,
    ) -> ProductTypeCatalog:
        item.name = name
        item.calculation_strategy = calculation_strategy
        item.required_fields = required_fields
        item.default_operations = default_operations
        item.allowed_materials = allowed_materials
        item.compatible_technologies = compatible_technologies
        if is_active is not None:
            item.is_active = is_active
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return item

    def delete(self, item: ProductTypeCatalog) -> None:
        self.db.delete(item)
        self.db.commit()
