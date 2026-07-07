"""Material Repository — master data access.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Sequence
from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.orm import Session, selectinload
from ..models.material import Material, MaterialCost

_SORTABLE = {
    "code": Material.code,
    "name": Material.name,
    "material_type": Material.material_type,
    "created_at": Material.created_at,
}

class MaterialRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- reads --------------------------------------------------------------

    def get_by_id(self, material_id: int) -> Material | None:
        return self.db.execute(
            select(Material)
            .options(selectinload(Material.costs))
            .where(Material.id == material_id)
        ).scalars().first()

    def get_by_code(self, code: str) -> Material | None:
        return self.db.execute(
            select(Material)
            .options(selectinload(Material.costs))
            .where(Material.code == code)
        ).scalars().first()

    def find_by_name(self, name: str) -> Material | None:
        name = (name or "").strip()
        if not name:
            return None
        return self.db.execute(
            select(Material)
            .where(func.lower(Material.name) == name.lower())
        ).scalars().first()

    def list(
        self,
        *,
        q: str | None = None,
        material_type: str | None = None,
        is_active: bool | None = None,
        sort: str = "code",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Material], int]:
        conditions = []
        if q:
            like = f"%{q.strip().lower()}%"
            conditions.append(
                or_(
                    func.lower(Material.name).like(like),
                    func.lower(Material.code).like(like),
                )
            )
        if material_type:
            conditions.append(Material.material_type == material_type)
        if is_active is not None:
            conditions.append(Material.is_active == is_active)

        base = select(Material)
        count_stmt = select(func.count()).select_from(Material)
        for c in conditions:
            base = base.where(c)
            count_stmt = count_stmt.where(c)

        total = self.db.execute(count_stmt).scalar_one()

        direction = asc
        key = sort or "code"
        if key.startswith("-"):
            direction = desc
            key = key[1:]
        col = _SORTABLE.get(key, Material.code)
        base = base.order_by(direction(col), Material.id.asc())

        page = max(1, page)
        size = max(1, min(size, 200))
        base = base.offset((page - 1) * size).limit(size)

        rows = list(self.db.execute(base).scalars())
        return rows, total

    # --- writes -------------------------------------------------------------

    def _next_code(self, material_type: str) -> str:
        prefix = "GY" if material_type == "paper" else "VT"
        max_n = 0
        for code in self.db.execute(
            select(Material.code).where(Material.code.like(f"{prefix}%"))
        ).scalars():
            try:
                max_n = max(max_n, int(code[2:]))
            except ValueError:
                continue
        return f"{prefix}{max_n + 1:03d}"

    def create(
        self,
        *,
        name: str,
        material_type: str,
        unit: str,
        min_fee: int = 0,
        width_cm: float | None = None,
        height_cm: float | None = None,
        gsm: int | None = None,
        thickness_mm: float | None = None,
        default_waste_pct: float = 0.0,
        min_purchase_qty: float = 0.0,
        paper_family: str | None = None,
        surface: str | None = None,
        is_active: bool = True,
        **extra,
    ) -> Material:
        material = Material(
            code=self._next_code(material_type),
            name=name,
            material_type=material_type,
            unit=unit,
            min_fee=min_fee,
            width_cm=width_cm,
            height_cm=height_cm,
            gsm=gsm,
            thickness_mm=thickness_mm,
            default_waste_pct=default_waste_pct,
            min_purchase_qty=min_purchase_qty,
            paper_family=paper_family,
            surface=surface,
            is_active=is_active,
            **extra,
        )
        self.db.add(material)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return material

    def update(
        self,
        material: Material,
        *,
        name: str,
        material_type: str,
        unit: str,
        min_fee: int,
        width_cm: float | None = None,
        height_cm: float | None = None,
        gsm: int | None = None,
        thickness_mm: float | None = None,
        default_waste_pct: float = 0.0,
        min_purchase_qty: float = 0.0,
        paper_family: str | None = None,
        surface: str | None = None,
        is_active: bool | None = None,
        **extra,
    ) -> Material:
        material.name = name
        # Do not change code. If material_type changes, prefix code is kept or regenerated?
        # Standard: keep existing code to preserve reference stability.
        material.material_type = material_type
        material.unit = unit
        material.min_fee = min_fee
        material.width_cm = width_cm
        material.height_cm = height_cm
        material.gsm = gsm
        material.thickness_mm = thickness_mm
        material.default_waste_pct = default_waste_pct
        material.min_purchase_qty = min_purchase_qty
        material.paper_family = paper_family
        material.surface = surface
        for k, v in extra.items():
            setattr(material, k, v)
        if is_active is not None:
            material.is_active = is_active
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return material

    def delete(self, material: Material) -> None:
        self.db.delete(material)
        self.db.commit()

    # --- cost pricing versioning writes -------------------------------------

    def get_current_cost(self, material_id: int, price_unit: str) -> MaterialCost | None:
        return self.db.execute(
            select(MaterialCost)
            .where(MaterialCost.material_id == material_id)
            .where(MaterialCost.price_unit == price_unit)
            .where(MaterialCost.effective_to.is_(None))
        ).scalars().first()

    def get_cost_at_date(self, material_id: int, price_unit: str, at_date: date) -> MaterialCost | None:
        return self.db.execute(
            select(MaterialCost)
            .where(MaterialCost.material_id == material_id)
            .where(MaterialCost.price_unit == price_unit)
            .where(MaterialCost.effective_from <= at_date)
            .where(
                or_(
                    MaterialCost.effective_to.is_(None),
                    # nửa-mở [from, to): cận trên LOẠI TRỪ, khớp cách đóng giá mới (#5).
                    MaterialCost.effective_to > at_date,
                )
            )
        ).scalars().first()

    def get_current_cost_variant(
        self, material_id: int, price_unit: str, *,
        quantity_from=None, quantity_to=None, supplier=None,
    ) -> MaterialCost | None:
        """Dòng giá hiện hành đúng biến thể (bậc + NCC) — cho versioning nhiều bậc/NCC."""
        stmt = (
            select(MaterialCost)
            .where(MaterialCost.material_id == material_id)
            .where(MaterialCost.price_unit == price_unit)
            .where(MaterialCost.effective_to.is_(None))
            .where(MaterialCost.quantity_from.is_(None) if quantity_from is None else MaterialCost.quantity_from == quantity_from)
            .where(MaterialCost.quantity_to.is_(None) if quantity_to is None else MaterialCost.quantity_to == quantity_to)
            .where(MaterialCost.supplier.is_(None) if supplier is None else MaterialCost.supplier == supplier)
        )
        return self.db.execute(stmt).scalars().first()

    def add_cost_price(
        self,
        *,
        material_id: int,
        price_unit: str,
        unit_price: int,
        effective_from: date,
        **extra,
    ) -> MaterialCost:
        """Add a cost price version for a material (cùng biến thể bậc/NCC thì đóng bản cũ).

        Nửa-mở [from, to): đóng bản hiện hành bằng effective_to = effective_from mới.
        """
        variant = dict(
            quantity_from=extra.get("quantity_from"),
            quantity_to=extra.get("quantity_to"),
            supplier=extra.get("supplier"),
        )
        current = self.get_current_cost_variant(material_id, price_unit, **variant)
        if current:
            current.effective_to = effective_from
            self.db.add(current)
            extra.setdefault("version", int(current.version or 1) + 1)

        new_cost = MaterialCost(
            material_id=material_id,
            price_unit=price_unit,
            unit_price=unit_price,
            effective_from=effective_from,
            effective_to=None,
            **extra,
        )
        self.db.add(new_cost)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return new_cost
