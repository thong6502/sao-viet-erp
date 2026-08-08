"""Enabling-point tests for the Báo giá (Quotation) cross-module seams.

These are the SOURCE OF TRUTH for the seams (together with the ``# SEAM-NN``
markers in ``app/services/quotation_ports.py``). ``docs/CROSS_MODULE_LINKS.md``
is only an index.

- SEAM-13 (Báo giá ← Tính giá) is GONE (Đợt 5, 2026-08-08): cụm tính giá đời cũ (Estimate)
  đã xoá hẳn, cổng ``CostingResultPort``/``EstimateCostingAdapter`` theo đó. Nguồn giá vốn giờ
  là Phiếu tính giá, `QuotationService._create_from_ptg` đọc thẳng — không còn seam để test.
- SEAM-14 (Báo giá ← Khách hàng/CRM) is CLOSED: CRM (`customers`) is built, so the adapter
  reads a live customer. The test drives the adapter with a fake repo (no DB coupling).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services import quotation_ports


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
