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
    # unit name this price is set for (e.g., to, ram, kg, m2)
    price_unit: Mapped[str] = mapped_column(String(16), nullable=False)
    unit_price: Mapped[int] = mapped_column(
        BigInteger, CheckConstraint("unit_price >= 0"), nullable=False, default=0
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
        Index(
            "uix_material_costs_current",
            "material_id",
            "price_unit",
            unique=True,
            sqlite_where=text("effective_to IS NULL"),
            postgresql_where=text("effective_to IS NULL")
        )
    )
