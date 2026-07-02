"""Enabling-point tests for the Báo giá (Quotation) cross-module seams.

These are the SOURCE OF TRUTH for the seams (together with the ``# SEAM-NN``
markers in ``app/services/quotation_ports.py``). ``docs/CROSS_MODULE_LINKS.md``
is only an index.

- SEAM-13 (Báo giá ← Tính giá) stays SKIPPED: the Tính giá screen exists but the frozen
  giá-vốn RESULT is still TREO behind SEAM-07..12, so the costing engine cannot return a
  real result yet — the stub must keep raising.
- SEAM-14 (Báo giá ← Khách hàng/CRM) is CLOSED: CRM (`customers`) is built, so the adapter
  reads a live customer. The test drives the adapter with a fake repo (no DB coupling).
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.services import quotation_ports


@pytest.mark.skip(reason="SEAM-13 Báo giá ← Tính giá (costing engine — giá vốn TREO sau SEAM-07..12) chưa build")
def test_seam_13_costing_result():
    # Back-fill: Tính giá returns a frozen CostingResult with cost_von_total +
    # unit_price_snapshot + norm_snapshot so Báo giá can copy-on-write it.
    result = quotation_ports.get_costing_result(costing_id=1)
    assert result.cost_von_total is not None
    assert result.unit_price_snapshot is not None
    assert result.norm_snapshot is not None


# The Báo giá → Đơn hàng handoff is owned by the pull side (spec-10 SEAM-04
# quotation_ref) to avoid an ADP cycle — no order-creation port/test lives here.


@dataclass
class _FakeCustomer:
    id: int
    name: str
    tax_code: str | None
    credit_limit: int


class _FakeCustomerRepo:
    def __init__(self, customer):
        self._customer = customer

    def get_by_id(self, customer_id: int):
        return self._customer if customer_id == self._customer.id else None


def test_seam_14_customer_lookup():
    """SEAM-14 CLOSED: the CRM adapter resolves a live customer (read-only)."""
    repo = _FakeCustomerRepo(
        _FakeCustomer(id=7, name="Công ty ABC", tax_code="0101234567", credit_limit=50_000_000)
    )
    adapter = quotation_ports.CustomerRefAdapter(repo)
    ref = adapter.get_customer(7)
    assert ref is not None
    assert ref.name == "Công ty ABC"
    assert ref.tax_code == "0101234567"
    assert "50.000.000" in ref.credit_status_display  # limit shown, no fabricated balance
    # Unknown customer → None (never a fabricated ref).
    assert adapter.get_customer(999) is None


def test_seam_13_stub_raises_until_backfilled():
    """SEAM-13 must fail loudly (never return a silent fake) while pending."""
    with pytest.raises(NotImplementedError, match="SEAM-13"):
        quotation_ports.get_costing_result(costing_id=1)
