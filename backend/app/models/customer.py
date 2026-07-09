"""Customer ORM model (Khách hàng / CRM contact) — spec-06-khach-hang.

One row per customer in the sales contact book. "Mở rộng từ nền RBAC" (DOMAIN §23
L528): a customer is owned by a Sale (`sale_user_id → users.id`) so RBAC data-scope
(own/department/all) can narrow the list. `tax_code` (MST) is optional (khách lẻ có
thể không có MST) and only *soft*-checked for duplicates — the domain is explicit that
this is a warning, NOT a hard block (§34 L885, §41 L1133), so it is indexed but NOT
unique. `credit_limit` is a plain VND integer here; the live receivable balance lives
in Công nợ and is read через SEAM-16 — never stored on this row. Portable across
SQLite and Postgres.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# Allowed values for `status`. `lead` = khách tiềm năng (đang chào hàng, chưa phát sinh
# giao dịch — khảo sát #22: lưu cả khách chưa có đơn để sale chăm sóc trên phần mềm).
STATUS_LEAD = "lead"
STATUS_ACTIVE = "active"
STATUS_INACTIVE = "inactive"
CUSTOMER_STATUSES = (STATUS_LEAD, STATUS_ACTIVE, STATUS_INACTIVE)

# Kiểu mốc điều khoản thanh toán (khảo sát #12 — "mỗi khách một đặc thù, không cố định"):
#   prepay        — trả trước X% khi đặt hàng
#   net_delivery  — X ngày kể từ ngày nhận hàng
#   net_eom       — đối chiếu cuối tháng, X ngày sau đối chiếu
#   custom        — đặc thù khác, mô tả ở payment_term_note
PAYMENT_TERM_TYPES = ("prepay", "net_delivery", "net_eom", "custom")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # System-generated sequential code (KH001, KH002…). Unique + read-only; never entered
    # by the user (spec-06 KH-02, following the PB### pattern of feat-023).
    code: Mapped[str] = mapped_column(
        String(20), unique=True, index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # MST (mã số thuế). Optional; indexed for the duplicate-check but NOT unique — a
    # duplicate MST is a soft warning, not a block (§34 L885, §41 L1133).
    tax_code: Mapped[str | None] = mapped_column(
        String(20), index=True, nullable=True
    )
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Contact person at the customer (suy luận CRM — not in the domain but standard).
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Credit limit in VND (integer đồng), default 0. This is the LIMIT only; the live
    # outstanding balance is read from Công nợ via SEAM-16, never stored here.
    credit_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # Owning Sale (RBAC scope owner). Nullable so a customer can exist unassigned;
    # indexed because every scoped list query filters on it.
    sale_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), index=True, nullable=True
    )
    # lead = tiềm năng (chưa giao dịch), active = đang giao dịch, inactive = ngừng.
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=STATUS_ACTIVE, server_default=STATUS_ACTIVE
    )
    # --- Điều khoản thanh toán riêng theo KH (khảo sát #12) — DỮ LIỆU CHỜ: chỉ nhập +
    # hiển thị; engine tính hạn nợ thuộc Công nợ (sẽ đọc cấu trúc này khi back-fill
    # SEAM-16). type ∈ PAYMENT_TERM_TYPES; None = chưa khai điều khoản.
    payment_term_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    payment_term_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prepay_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    payment_term_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # --- Chiết khấu mặc định theo KH (khảo sát #14). Chỉ là GIÁ TRỊ MẶC ĐỊNH điền sẵn
    # ở tầng Báo giá (cho sửa từng báo giá) — KHÔNG nằm trong engine tính giá.
    # `discount_buyer_pct` (CK cho người mua hàng của khách) là dữ liệu nhạy cảm — API
    # ẩn cả hai trường sau quyền chi tiết `view_discount` (pattern view_debt/view_salary).
    discount_trade_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    discount_buyer_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class CustomerContact(Base):
    """Một người liên hệ của khách hàng (khảo sát #10–#11: khách luôn có nhiều người —
    mua hàng, kho, kế toán, kỹ thuật… — cần ghi chức vụ + nhiệm vụ để các bộ phận tự
    liên hệ). `customers.contact_name` vẫn giữ làm "liên hệ nhanh" trên form."""

    __tablename__ = "customer_contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)   # chức vụ
    duty: Mapped[str | None] = mapped_column(String(255), nullable=True)    # nhiệm vụ
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Liên hệ chính (khảo sát #11) — service giữ bất biến: tối đa MỘT is_primary/khách.
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class CustomerAddress(Base):
    """Một địa điểm giao hàng của khách (khảo sát #9: "khách hàng luôn có nhiều vị trí
    giao hàng"). CHỖ NỐI Tính giá: khi báo giá cần phí giao hàng, Tính giá sẽ đọc danh
    sách này để chọn điểm giao — chưa wire ở đợt này."""

    __tablename__ = "customer_addresses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    label: Mapped[str] = mapped_column(String(120), nullable=False)  # "Nhà máy Bắc Ninh"
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Địa chỉ giao mặc định — service giữ bất biến: tối đa MỘT is_default/khách.
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


# Loại tài liệu đính kèm hồ sơ KH (khảo sát #21: hợp đồng, GPKD, file thiết kế, khác).
DOC_HOP_DONG = "hop_dong"
DOC_GPKD = "gpkd"
DOC_THIET_KE = "thiet_ke"
DOC_KHAC = "khac"
CUSTOMER_DOC_KINDS = (DOC_HOP_DONG, DOC_GPKD, DOC_THIET_KE, DOC_KHAC)


class CustomerAttachment(Base):
    """File đính kèm hồ sơ khách hàng. Bytes nằm dưới <backend>/static/crm và được serve
    read-only tại /static; chỉ lưu path ở đây (mirror employee_attachments)."""

    __tablename__ = "customer_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    doc_kind: Mapped[str] = mapped_column(
        String(24), nullable=False, default=DOC_KHAC, server_default=DOC_KHAC
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
