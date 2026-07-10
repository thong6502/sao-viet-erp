"""Sản xuất — Lệnh sản xuất (LSX) P1/MVP.

LSX là thực thể ĐỘC LẬP, được nhiều phân hệ tham chiếu (kho xuất NVL/nhập thành phẩm theo
LSX, tính giá thành, theo dõi SX). Kho trỏ vào đây qua `ref_type='lsx' + ref_id`, KHÔNG lưu
bản sao. Bảng mới → create_all tự dựng.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProductionOrder(Base):
    """Lệnh sản xuất (LSX). MVP: mã + đơn hàng + sản phẩm + số lượng + ngày + trạng thái.
    Định mức NVL / công đoạn / tiến độ là P2 (chưa mô hình hóa ở đây)."""

    __tablename__ = "production_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    # Đơn hàng + khách + sản phẩm: FK mềm (nullable) — LSX có thể lập trước khi chốt đơn/sản phẩm.
    order_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("orders.id"), index=True, nullable=True
    )
    contract_no: Mapped[str | None] = mapped_column(String(60), nullable=True)  # theo hợp đồng số
    customer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("customers.id"), index=True, nullable=True
    )
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)  # fallback khi chưa có customer_id
    product_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("products.id"), nullable=True
    )
    product_name: Mapped[str | None] = mapped_column(String(255), nullable=True)  # khi chưa có product_id
    quantity: Mapped[float | None] = mapped_column(Numeric(18, 3), nullable=True)
    order_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # ngày đặt
    delivery_request_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # yêu cầu nhận hàng vào
    doc_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # ngày lập phiếu SX
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # ngày hoàn thành
    # open / done / cancelled
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", index=True)
    # Loại lệnh: thuong (thường) / bu (lệnh sản xuất bù — làm lại hàng lỗi/thiếu, BRD §2.13).
    order_kind: Mapped[str] = mapped_column(String(10), nullable=False, default="thuong", index=True)
    parent_order_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("production_orders.id"), nullable=True
    )  # LSX gốc khi là lệnh bù
    bu_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)  # lý do bù (hàng trả/lỗi/hao hụt)
    tech_note_print: Mapped[str | None] = mapped_column(Text, nullable=True)  # lưu ý kỹ thuật khi in
    tech_note_finishing: Mapped[str | None] = mapped_column(Text, nullable=True)  # lưu ý đóng xén
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class ProductionOrderAttachment(Base):
    """Tập tin đính kèm LSX (file thiết kế, mẫu, chứng từ). Bytes dưới static/san-xuat/<id>/,
    phục vụ read-only ở /static (mirror stock_voucher_attachments). Bảng mới → create_all tự dựng."""

    __tablename__ = "production_order_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("production_orders.id", ondelete="CASCADE"), index=True, nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    uploaded_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
