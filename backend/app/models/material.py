"""Material master models — spec-20 master data.

Unified catalog for raw materials and consumables (Paper, Decal, PP, Lamination, etc.)
and their corresponding cost rates over time.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..db import Base

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

# Nhóm vật tư (trục UI). material_type (trục engine) map về group qua GROUP_FROM_TYPE.
MATERIAL_GROUPS = ("paper", "ink", "film", "glue", "packaging", "auxiliary")
GROUP_FROM_TYPE = {
    "paper": "paper", "carton": "paper",
    "lamination": "film", "film": "film",
    "glue": "glue",
    "decal": "auxiliary", "pp": "auxiliary", "canvas": "auxiliary",
    "formex": "auxiliary", "chemical": "auxiliary",
}

class Material(Base):
    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # GY### for papers, VT### for other consumables
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # paper, decal, pp, canvas, carton, film, lamination, glue, chemical...
    material_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    min_fee: Mapped[int] = mapped_column(
        BigInteger, CheckConstraint("min_fee >= 0"), nullable=False, default=0
    )
    
    # Unified physical dimensions
    width_cm: Mapped[float | None] = mapped_column(
        Numeric(10, 2), CheckConstraint("width_cm >= 0"), nullable=True
    )
    height_cm: Mapped[float | None] = mapped_column(
        Numeric(10, 2), CheckConstraint("height_cm >= 0"), nullable=True
    )
    gsm: Mapped[int | None] = mapped_column(
        Integer, CheckConstraint("gsm >= 0"), nullable=True
    )
    thickness_mm: Mapped[float | None] = mapped_column(
        Numeric(10, 2), CheckConstraint("thickness_mm >= 0"), nullable=True
    )
    default_waste_pct: Mapped[float] = mapped_column(
        Numeric(5, 2), CheckConstraint("default_waste_pct >= 0"), nullable=False, default=0.0
    )
    min_purchase_qty: Mapped[float] = mapped_column(
        Numeric(10, 2), CheckConstraint("min_purchase_qty >= 0"), nullable=False, default=0.0
    )
    
    # Paper-specific attributes
    paper_family: Mapped[str | None] = mapped_column(String(32), nullable=True)
    surface: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # ---- Tái thiết kế danh mục #2: nhóm + NCC + UoM/quy đổi + field theo nhóm ----
    # Trục UI (paper/ink/film/glue/packaging/auxiliary). material_type vẫn là trục ENGINE.
    material_group: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)
    default_supplier: Mapped[str | None] = mapped_column(String(150), nullable=True)
    base_uom: Mapped[str | None] = mapped_column(String(16), nullable=True)
    purchase_uom: Mapped[str | None] = mapped_column(String(16), nullable=True)
    consumption_uom: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # gsm_area | ream_500 | area_m2 | fixed_factor | none
    conversion_method: Mapped[str | None] = mapped_column(String(24), nullable=True)
    conversion_factor: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    # Nhóm ink
    ink_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ink_color_system: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ink_color_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Nhóm film
    film_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1", default=1
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
    
    costs: Mapped[list[MaterialCost]] = relationship(
        "MaterialCost",
        back_populates="material",
        cascade="all, delete-orphan",
        order_by="MaterialCost.effective_from.desc()",
    )

class MaterialCost(Base):
    __tablename__ = "material_costs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    material_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("materials.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # unit name this price is set for (e.g., to, ram, kg, m2, nghin_luot)
    price_unit: Mapped[str] = mapped_column(String(16), nullable=False)
    unit_price: Mapped[int] = mapped_column(
        BigInteger, CheckConstraint("unit_price >= 0"), nullable=False, default=0
    )

    # ---- Tái thiết kế #2: NCC + khổ + loại giá + bậc số lượng + phí ----
    supplier: Mapped[str | None] = mapped_column(String(150), nullable=True)
    paper_size_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("paper_sizes.id", ondelete="SET NULL"), nullable=True
    )
    price_type: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="standard", default="standard"
    )
    vat_included: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    transport_fee: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0", default=0
    )
    moq: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, server_default="0", default=0.0
    )
    lead_time_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )
    quantity_from: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    quantity_to: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1", default=1
    )

    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
    
    material: Mapped[Material] = relationship("Material", back_populates="costs")
    
    __table_args__ = (
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="chk_material_effective_dates"
        ),
        # Chỉ 1 dòng "hiện hành" cho mỗi (vật tư + đơn vị giá + bậc SL + NCC + khổ) — cho phép
        # nhiều bậc/NCC/khổ cùng lúc (tái thiết kế #2). Migration 0005 thay index cũ (chỉ material+unit).
        Index(
            "uix_material_costs_current",
            "material_id",
            "price_unit",
            text("coalesce(quantity_from, -1)"),
            text("coalesce(quantity_to, -1)"),
            text("coalesce(supplier, '')"),
            text("coalesce(paper_size_id, 0)"),
            unique=True,
            sqlite_where=text("effective_to IS NULL"),
            postgresql_where=text("effective_to IS NULL")
        )
    )
