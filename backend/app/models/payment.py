"""Payment (thu tiền bán) — Pha A "Lát Tài chính". Ghi CỌC + các đợt thu của một Đơn hàng bán.

Đóng **SEAM-04 (deposit_payment)**: ``deposit_total(order) = Σ amount WHERE kind=deposit`` là
điều kiện CỨNG để chốt đơn (③→④, §32 L827-828). Cọc **KHÔNG sinh hóa đơn** (NĐ123/2020 — chỉ treo
Nợ 111/112 / Có 131); chân lý hóa đơn/doanh thu ở ⑬ (MISA), KHÔNG ở đây. HYBRID → MISA: bảng này
là chi tiết THU của ERP, kết xuất bút toán tổng hợp sang MISA sau (docs §4.9).

Khác hẳn ``payment_vouchers`` (models.accounting) = Phiếu CHI mua hàng (AP). Đây là chiều THU bán (AR).
Portable across SQLite (dev) và Postgres (prod).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# --- kind: cọc (mở cổng chốt) vs đợt thu sau (§4.6/§4.2) -----------------------
PAYMENT_KIND_DEPOSIT = "deposit"   # cọc — điều kiện chốt đơn (③→④)
PAYMENT_KIND_PARTIAL = "partial"   # thu từng đợt (sau chốt/giao)
PAYMENT_KIND_FINAL = "final"       # thu nốt phần còn lại
PAYMENT_KINDS = (PAYMENT_KIND_DEPOSIT, PAYMENT_KIND_PARTIAL, PAYMENT_KIND_FINAL)

# --- method: định khoản Nợ 111 (mặt) / 112 (chuyển khoản) ----------------------
PAYMENT_METHOD_CASH = "cash"
PAYMENT_METHOD_BANK = "bank"
PAYMENT_METHODS = (PAYMENT_METHOD_CASH, PAYMENT_METHOD_BANK)

# --- direction: thu (tiền vào) vs hoàn (trả cọc khi hủy đơn theo mốc §32) -------
PAYMENT_DIRECTION_IN = "thu"
PAYMENT_DIRECTION_REFUND = "hoan"
PAYMENT_DIRECTIONS = (PAYMENT_DIRECTION_IN, PAYMENT_DIRECTION_REFUND)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("orders.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Khách kéo từ đơn (để cộng dồn công nợ/đối chiếu theo khách). Nullable + SET NULL như
    # order.customer_id (CRM cùng app).
    customer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="SET NULL"), index=True, nullable=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default=PAYMENT_KIND_DEPOSIT)
    # thu / hoàn — hoàn dùng khi hủy đơn (§32 hoàn cọc theo mốc). deposit_total tính NET thu−hoàn.
    direction: Mapped[str] = mapped_column(String(8), nullable=False, default=PAYMENT_DIRECTION_IN)
    # VND nguyên. BigInteger vì đơn in giá trị lớn (vượt Int 2^31). Luôn > 0.
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    method: Mapped[str] = mapped_column(String(16), nullable=False, default=PAYMENT_METHOD_BANK)
    paid_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    # Số phiếu thu (đối chiếu MISA — §4.9). Nullable (có thể để hệ sinh sau).
    voucher_no: Mapped[str | None] = mapped_column(String(40), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
