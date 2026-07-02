"""Product (Sản phẩm in) ORM models — spec-07-san-pham.

A **product** is the reusable commercial master ("cái khách mua"): đơn hàng / job
reference it, never the reverse (DOMAIN §29 L701, §34 L865). One `products` row per
catalogue item; a product with a spine (sách/hộp) breaks into ordered
**`product_components`** — each carrying its OWN khổ thành phẩm, giấy, số màu 2 mặt, số
trang, bleed, canh thớ (§34 L893–894) so báo giá / job / bình bản read them back exactly,
without re-entry and without mixing specs between components.

DELIBERATELY NOT modeled here (out-of-scope, spec-07):
  - price / snapshot giá — snapshotted at order-close copy-on-write (P0 #5, §34 L877);
  - PrintForm fields (pieces_per_sheet, planned_sheets, plates_count, makeready, gutter…)
    — physical/costing layer, hidden from Sale (§40 D2 L1108);
  - khổ/bleed at the Product HEAD — those live ONLY on the component (§34 L894); a
    multi-component product has no single trim size.

`paper_master_id` is an FK-nullable seam (SEAM-03) to PaperMaster (module
`dm_giay_vat_tu`, Danh mục Giấy). It is a plain nullable Integer here (no FK constraint)
until that catalog exists — the component editor may save paper_master_id=null meanwhile,
and the live paper list is looked up via the raising port stub (no fake list). Portable
across SQLite and Postgres.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base

# --- Enums (domain vocab; validated in the service, stored as plain strings) ----

# Loại SP (§7 L251: catalogue, brochure, tem/nhãn, hộp giấy, sách, tờ rơi, name card…).
PRODUCT_TYPES = (
    "catalogue",
    "brochure",
    "tem_nhan",   # tem / nhãn
    "hop",        # hộp giấy
    "sach",       # sách
    "to_roi",     # tờ rơi
    "name_card",
)

# Kiểu đóng (§5 L177–179). `none` = SP không gáy (name card / tờ rơi); the others are
# the three binding styles that require ≥1 component (perfect/saddle/sewn).
BINDING_NONE = "none"
BINDING_TYPES = (BINDING_NONE, "perfect", "saddle", "sewn")

# component_type (§34 L893): bìa / ruột / tay đệm.
COMPONENT_TYPES = ("cover", "body", "insert")

# canh thớ (grain direction).
GRAIN_DIRECTIONS = ("long", "short")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # System-generated sequential code (SP001, SP002…). Unique + read-only; never entered
    # by the user (spec-07 §34 L865 — SP dùng lại nhiều lần; PB###/KH### pattern).
    code: Mapped[str] = mapped_column(
        String(20), unique=True, index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Loại SP (enum §7). Stored as string; validated in the service.
    product_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # Kiểu đóng (nullable — chỉ SP có gáy). None = không gáy; stored as string.
    binding_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    components: Mapped[list["ProductComponent"]] = relationship(
        "ProductComponent",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductComponent.sequence",
    )


class ProductComponent(Base):
    __tablename__ = "product_components"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Display / print order (bìa trước ruột…). Low-risk sort key.
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # cover / body / insert (§34 L893).
    component_type: Mapped[str] = mapped_column(String(16), nullable=False)
    # SEAM-03: FK-nullable to PaperMaster (Danh mục Giấy · dm_giay_vat_tu). Plain nullable
    # Integer (no FK constraint) until that catalog is built — never a fabricated paper.
    paper_master_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Số màu mỗi mặt (0..8) — validated in the service (§23 L532, số bản = màu×mặt).
    colors_front: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    colors_back: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Số trang. body of a bound product must be % 4 == 0 (tay sách 4/8/16/32, §31);
    # rule applied in the service, not the column.
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Khổ thành phẩm (finished size). Numeric so mm/cm decimals survive SQLite + Postgres.
    finished_w: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    finished_h: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    # Bleed (mm). Numeric; may be 0.
    bleed: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    # Canh thớ: long / short.
    grain_direction: Mapped[str | None] = mapped_column(String(8), nullable=True)

    product: Mapped["Product"] = relationship("Product", back_populates="components")
