"""Ports (interfaces) the Báo giá (Quotation) screen DEPENDS ON — owned by the
consumer (Kinh doanh · Báo giá) per DIP. Upstream modules implement these later;
until then each is an explicit NotImplementedError stub (no silent fake values).

Seam registry (source of truth = these markers + the matching skip-tests in
``backend/tests/test_seam_quotation.py``; ``docs/CROSS_MODULE_LINKS.md`` is only an index):

- SEAM-13 (⏳ TREO): Báo giá ← Tính giá (costing engine). Báo giá references a Tính giá
  result to snapshot ``unit_price_snapshot`` + ``norm_snapshot`` copy-on-write. STILL a
  seam: the Tính giá *screen* exists (feat-038/039) but the frozen giá-vốn RESULT
  (``cost_von_total``/snapshots) is TREO behind SEAM-07..12 (feat-040..042 blocked), so the
  costing engine cannot yet return a real result — the stub must keep raising.
- SEAM-14 (✅ ĐÃ ĐÓNG): Báo giá ← Khách hàng (CRM). Resolve the customer (name / tax_code /
  credit status) a quotation is addressed to. CRM (``customers``) IS built (feat-027..030),
  so this seam is back-filled by a real adapter (``CustomerRefAdapter``); the default
  factory reads the live customer via the injected repository.

The Báo giá.approve → Đơn hàng handoff is NOT owned here: to avoid an ADP cycle
between Báo giá and Đơn hàng bán, the pull-side port lives on the Đơn hàng bán
side (spec-10, SEAM-04 ``quotation_ref(quotation_id) -> {approved, version,
effective_from, total}``). Báo giá only flips ``status=approved``; Đơn hàng bán
reads the approved quotation via that port — so no order-creation port lives here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


# --- SEAM-13: chờ Tính giá (costing engine) — ⏳ STILL TREO ------------------
@runtime_checkable
class CostingResultPort(Protocol):
    """Downstream (Báo giá) port. Tính giá implements this later.

    A Báo giá line is built ON TOP of a frozen Tính giá result: the quotation
    must snapshot the unit price AND the norms (copy-on-write, P0 §34 L877-878)
    — never a live FK to the price/norm tables.
    """

    def get_costing_result(self, costing_id: int) -> "CostingResult":  # pragma: no cover
        ...


@dataclass
class CostingResult:  # contract shape only, filled by Tính giá when SEAM-13 closes
    """Frozen cost-of-goods result Báo giá snapshots. Shape (owned by consumer):
    ``{ costing_id, cost_von_total, unit_price_snapshot, norm_snapshot,
        price_effective_from, price_effective_to }``.
    """

    costing_id: int
    cost_von_total: int
    unit_price_snapshot: dict
    norm_snapshot: dict
    price_effective_from: object | None = None
    price_effective_to: object | None = None


def get_costing_result(costing_id: int) -> CostingResult:
    # SEAM-13: chờ Tính giá (costing engine — giá vốn TREO sau SEAM-07..12, chưa build)
    raise NotImplementedError("SEAM-13 chưa back-fill")


# NOTE: Báo giá → Đơn hàng handoff is owned by the pull side (spec-10 SEAM-04
# ``quotation_ref``) to avoid an ADP cycle; there is deliberately no order-creation
# port here. Báo giá only sets status=approved; Đơn hàng bán reads it.


# --- SEAM-14: Khách hàng (CRM) — ✅ ĐÃ ĐÓNG (CRM đã build) --------------------
@runtime_checkable
class CustomerLookupPort(Protocol):
    """Downstream (Báo giá) port. Khách hàng (CRM) implements this (back-filled).

    Read-only: name + display credit status shown on the quotation. Báo giá does
    NOT block on credit limit (that is Đơn hàng bán via CreditOverride, §34 L885).
    """

    def get_customer(self, customer_id: int) -> "CustomerRef | None":  # pragma: no cover
        ...


@dataclass
class CustomerRef:
    """``{ customer_id, name, tax_code, credit_status_display }`` (read-only)."""

    customer_id: int
    name: str
    tax_code: str | None
    credit_status_display: str


class CustomerRefAdapter:
    """SEAM-14 back-fill: resolve a customer via the live CRM repository. Read-only —
    Báo giá never mutates the customer, and never blocks on credit limit here."""

    def __init__(self, customers) -> None:
        self._customers = customers

    def get_customer(self, customer_id: int) -> CustomerRef | None:
        customer = self._customers.get_by_id(customer_id)
        if customer is None:
            return None
        # Display-only credit status. The live AR balance lives in Công nợ (SEAM-16);
        # Báo giá shows the LIMIT side only and never fabricates a balance.
        if customer.credit_limit and customer.credit_limit > 0:
            credit_status = f"Hạn mức {customer.credit_limit:,} đ".replace(",", ".")
        else:
            credit_status = "Chưa đặt hạn mức"
        return CustomerRef(
            customer_id=customer.id,
            name=customer.name,
            tax_code=customer.tax_code,
            credit_status_display=credit_status,
        )


def get_customer(customer_id: int, *, customers=None) -> CustomerRef | None:
    """Module-level convenience used by the enabling-point test. When a repository is
    supplied it delegates to the real adapter (SEAM-14 closed); with none it raises the
    historical stub so a caller that forgot to wire the adapter fails loudly."""
    if customers is None:
        # SEAM-14 has no live repo here — a mis-wired caller must not get a fake value.
        raise NotImplementedError("SEAM-14 cần repository khách hàng (CRM)")
    return CustomerRefAdapter(customers).get_customer(customer_id)
