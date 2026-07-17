"""Kho P0 — tồn kho dựa trên Material (spec: thiết kế tối ưu).

Nguyên tắc: `Material` là item master (giấy/mực/film); Kho chỉ thêm 2 bảng trỏ về nó:
- `StockLot`  : lô tồn thật của 1 vật tư trong 1 kho (sở hữu cty/khách, giá vốn, date).
- `StockMove` : sổ cái +/− (append-only). Tồn = SUM(qty_delta).

Back-fill SEAM-22 (is_paper_referenced_in_stock) + SEAM-06 (customer_paper_lot).
Bảng mới → create_all tự dựng.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StockLot(Base):
    """Lô tồn: 1 vật tư (Material) trong 1 kho. Số lượng còn lại tính động từ StockMove."""

    __tablename__ = "stock_lots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    # Item master = Material (giấy/mực/film). KHÔNG tạo master trùng.
    material_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("materials.id"), index=True, nullable=False
    )
    warehouse_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("warehouses.id"), index=True, nullable=False
    )
    location: Mapped[str | None] = mapped_column(String(60), nullable=True)
    # company = hàng công ty; customer = giấy khách gửi (cost=0 nhưng vẫn trừ tồn).
    ownership: Mapped[str] = mapped_column(String(16), nullable=False, default="company")
    owner_customer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("customers.id"), nullable=True
    )
    # Gắn đơn hàng (SEAM-06 ứng giấy khách theo đơn) — nullable.
    order_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    unit_cost: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # đồng/đơn-vị-tồn
    supplier: Mapped[str | None] = mapped_column(String(150), nullable=True)
    received_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class StockMove(Base):
    """Sổ cái tồn (append-only). qty_delta CÓ DẤU: + tăng, − giảm. Tồn = SUM(qty_delta)."""

    __tablename__ = "stock_moves"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    material_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("materials.id"), index=True, nullable=False
    )
    warehouse_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("warehouses.id"), index=True, nullable=False
    )
    lot_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("stock_lots.id"), index=True, nullable=True
    )
    qty_delta: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    # Giá vốn / đơn vị tồn (spec-13 E). Giá trị = qty_delta × unit_cost. Null = 0.
    unit_cost: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # ton_dau_ky / nhap / xuat / dieu_chinh / dieu_chuyen_in / dieu_chuyen_out
    move_type: Mapped[str] = mapped_column(String(24), nullable=False, default="dieu_chinh")
    # Trạng thái hàng (spec-13): quyết định tồn khả dụng. Null = coi như khả dụng.
    status_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("wh_item_statuses.id"), nullable=True
    )
    # Truy nguồn phiếu (spec-13). Null = ghi trực tiếp (tồn đầu kỳ/điều chỉnh nhanh).
    voucher_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("stock_vouchers.id"), index=True, nullable=True
    )
    reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    ref_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )


class StockMinLevel(Base):
    """Ngưỡng tồn tối thiểu theo (vật tư × kho). Tồn thực tế < min_qty → cảnh báo bổ sung.
    Bảng mới → create_all tự dựng. UNIQUE(material_id, warehouse_id)."""

    __tablename__ = "stock_min_levels"
    __table_args__ = (
        UniqueConstraint("material_id", "warehouse_id", name="uq_min_level_material_wh"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    material_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("materials.id"), index=True, nullable=False
    )
    warehouse_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("warehouses.id"), index=True, nullable=False
    )
    min_qty: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False, default=0)
    # Cận min: tồn < near_min_qty (mà vẫn ≥ min) → cảnh báo "sắp min" (vàng). 0 = không dùng.
    near_min_qty: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False, default=0)
    note: Mapped[str | None] = mapped_column(String(120), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
