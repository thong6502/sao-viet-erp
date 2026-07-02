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

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# Allowed values for `status` (đang giao dịch / ngừng giao dịch).
STATUS_ACTIVE = "active"
STATUS_INACTIVE = "inactive"
CUSTOMER_STATUSES = (STATUS_ACTIVE, STATUS_INACTIVE)


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
    # active = đang giao dịch, inactive = ngừng giao dịch.
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=STATUS_ACTIVE, server_default=STATUS_ACTIVE
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
