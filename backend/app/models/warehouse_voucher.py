"""Kho — cỗ máy chứng từ: phiếu (Header) + dòng (Lines) (spec-13, DacTa ch.4).

Một khung phiếu cho mọi nghiệp vụ; hành vi lấy từ `WhVoucherType`. Ghi `StockMove` khi
GHI SỔ (post). Bảng mới → create_all tự dựng.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StockVoucher(Base):
    """Header phiếu (DacTa Table 2)."""

    __tablename__ = "stock_vouchers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    voucher_type_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("wh_voucher_types.id"), index=True, nullable=False
    )
    doc_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Đối tượng: ncc / khach / bo_phan / may (text ref cho P1 — chưa FK cứng).
    partner_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    partner_ref: Mapped[str | None] = mapped_column(String(150), nullable=True)
    src_warehouse_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("warehouses.id"), index=True, nullable=True
    )
    dst_warehouse_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("warehouses.id"), nullable=True
    )
    ref_type: Mapped[str | None] = mapped_column(String(24), nullable=True)  # lsx/order/po
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # draft / pending / posted / cancelled
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    approved_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    misa_ref: Mapped[str | None] = mapped_column(String(40), nullable=True)  # mã đối chiếu (P1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    lines: Mapped[list["StockVoucherLine"]] = relationship(
        back_populates="voucher", cascade="all, delete-orphan"
    )


class StockVoucherLine(Base):
    """Dòng phiếu (DacTa Table 3)."""

    __tablename__ = "stock_voucher_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    voucher_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stock_vouchers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    material_id: Mapped[int] = mapped_column(Integer, ForeignKey("materials.id"), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False)
    uom: Mapped[str | None] = mapped_column(String(16), nullable=True)  # đơn vị nhập (quy đổi khi post)
    lot_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("stock_lots.id"), nullable=True)
    location: Mapped[str | None] = mapped_column(String(60), nullable=True)
    dest_location: Mapped[str | None] = mapped_column(String(60), nullable=True)
    status_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("wh_item_statuses.id"), nullable=True
    )
    unit_cost: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    voucher: Mapped["StockVoucher"] = relationship(back_populates="lines")


class StockVoucherAttachment(Base):
    """File đính kèm phiếu (chứng từ scan: hóa đơn/PO/phiếu giao). Bytes nằm dưới
    <backend>/static/kho/<voucher_id>/ và phục vụ read-only qua /static; chỉ lưu path ở đây
    (mirror employee_attachments). Bảng mới → create_all tự dựng."""

    __tablename__ = "stock_voucher_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    voucher_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stock_vouchers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str | None] = mapped_column(String(100), nullable=True)  # MIME
    uploaded_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
