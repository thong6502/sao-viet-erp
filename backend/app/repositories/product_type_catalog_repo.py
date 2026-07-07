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
    "product_group": ProductTypeCatalog.product_group,
    "display_order": ProductTypeCatalog.display_order,
    "created_at": ProductTypeCatalog.created_at,
}

# Mọi field cấu hình (spec §A–§H) mang trên row — dùng chung create/update/clone.
_PT_CONFIG_FIELDS = (
    "calculation_strategy",
    "product_group",
    "technology",
    "description",
    "display_order",
    "required_fields",
    "shown_fields",
    "dimension_rule_type",
    "default_bleed_mm",
    "default_gutter_mm",
    "default_trim_mm",
    "allow_rotation",
    "allow_custom_size",
    "has_page_count",
    "page_multiple",
    "pages_per_signature",
    "has_cover_body_split",
    "allowed_materials",
    "default_paper_material_id",
    "default_cover_material_id",
    "default_body_material_id",
    "default_ink_material_id",
    "has_packaging",
    "default_pack_qty",
    "default_operations",
    "required_operations",
    "allow_extra_operations",
    "compatible_technologies",
    "sheet_count_mode",
    "ink_cost_mode",
    "has_tooling",
    "default_tooling_type",
    "allow_manual_override",
    "waste_pct",
)

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
        is_active: bool = True,
        **config,
    ) -> ProductTypeCatalog:
        item = ProductTypeCatalog(
            product_type=product_type,
            name=name,
            is_active=is_active,
            **{k: v for k, v in config.items() if k in _PT_CONFIG_FIELDS},
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
        is_active: bool | None = None,
        **config,
    ) -> ProductTypeCatalog:
        item.name = name
        for field in _PT_CONFIG_FIELDS:
            if field in config:
                setattr(item, field, config[field])
        if is_active is not None:
            item.is_active = is_active
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return item

    def count_estimate_refs(self, product_type: str) -> int:
        from ..models.estimate import Estimate
        return self.db.execute(
            select(func.count()).select_from(Estimate).where(Estimate.product_type == product_type)
        ).scalar_one()

    def delete(self, item: ProductTypeCatalog) -> None:
        self.db.delete(item)
        self.db.commit()
