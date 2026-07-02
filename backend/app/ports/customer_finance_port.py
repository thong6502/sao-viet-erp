"""Ports the Khách hàng (CRM) screen needs from modules that are NOT built yet.

Per DIP: the *consumer* (Kinh doanh · Khách hàng) OWNS these interfaces; the
*provider* (Tài chính–Kế toán / Cung ứng) implements them later. Until then each
default implementation is an explicit stub that raises — never a silent fake value
(a fake 0-balance would let a customer look debt-free and silently blow past the
credit limit). See docs/CROSS_MODULE_LINKS.md.

Seams parked here (SEAM-03..14 were claimed by Sản phẩm, Đơn hàng bán, Tính giá &
Báo giá, so the CRM seams take a clear block, 16..18):
  - SEAM-16  công nợ AR (receivable balance / credit usage)  → Tài chính–Kế toán (`cong_no`)
  - SEAM-17  CreditOverride (duyệt vượt hạn mức)             → Kế toán (`credit_override`)
  - SEAM-18  netting AR↔AP (khách cũng là NCC) — P1          → Cung ứng / AP
"""
from __future__ import annotations

from typing import Protocol


class CustomerReceivablePort(Protocol):
    """AR side of a customer's credit picture. Owned by Khách hàng, implemented by
    Tài chính–Kế toán (module `cong_no`) once that module exists."""

    def get_ar_balance(self, customer_id: int) -> int:
        """Outstanding receivable (VND, integer) for the customer. Used to render
        credit usage vs limit on the Customer screen."""
        ...


class CreditOverridePort(Protocol):
    """Records an approved over-limit override. Owned by Khách hàng/Đơn hàng,
    implemented by Kế toán (action `credit_override`) once Công nợ exists."""

    def record_override(
        self, customer_id: int, over_amount: int, reason: str, approver_user_id: int
    ) -> int:
        """Persist a CreditOverride{over_amount, reason, approver, audit} and return
        its id. Domain §34: over-limit is NOT a hard block — it is an audited override."""
        ...


# --- Default stubs (SEAM placeholders) --------------------------------------
# These are the "chỗ nối". They MUST raise, not return a fake value.

class _UnimplementedReceivable:
    def get_ar_balance(self, customer_id: int) -> int:  # noqa: ARG002
        # SEAM-16: chờ Tài chính–Kế toán (cong_no)
        raise NotImplementedError("SEAM-16 chưa back-fill")


class _UnimplementedCreditOverride:
    def record_override(  # noqa: ARG002
        self, customer_id: int, over_amount: int, reason: str, approver_user_id: int
    ) -> int:
        # SEAM-17: chờ Kế toán (credit_override)
        raise NotImplementedError("SEAM-17 chưa back-fill")


def default_receivable_port() -> CustomerReceivablePort:
    """Wired-in default until Công nợ back-fills SEAM-16."""
    return _UnimplementedReceivable()


def default_credit_override_port() -> CreditOverridePort:
    """Wired-in default until Kế toán back-fills SEAM-17."""
    return _UnimplementedCreditOverride()
