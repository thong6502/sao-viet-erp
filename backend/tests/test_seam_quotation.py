"""Enabling-point tests for the Báo giá (Quotation) cross-module seams.

These are the SOURCE OF TRUTH for the seams (together with the ``# SEAM-NN``
markers in ``app/services/quotation_ports.py``). ``docs/CROSS_MODULE_LINKS.md``
is only an index.

- SEAM-13 (Báo giá ← Tính giá) is CLOSED: the Tính giá engine (Phase 2A) produces frozen
  EstimateOption results, back-filled by ``EstimateCostingAdapter``. The test drives the
  adapter with a fake estimate repo (no DB coupling); the bare module call (no repo) must
  STILL raise so a mis-wired caller never gets a fake cost.
- SEAM-14 (Báo giá ← Khách hàng/CRM) is CLOSED: CRM (`customers`) is built, so the adapter
  reads a live customer. The test drives the adapter with a fake repo (no DB coupling).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pytest

from app.services import quotation_ports


# --- SEAM-13 fakes (no DB coupling) --------------------------------------------


@dataclass
class _FakeCostLine:
    category: str = "material"
    description: str = "Giấy in: Couche 150gsm (390 tờ)"
    quantity: float = 390.0
    unit: str = "to"
    unit_cost: float = 1500.0
    setup_cost: float = 0.0
    total_cost: float = 585_000.0
    source_type: str = "material_costs"
    source_id: int = 1
    source_snapshot_json: dict | None = None
    calculation_snapshot_json: dict | None = None


@dataclass
class _FakeOption:
    quantity: int
    total_cost: float
    warnings_json: list = field(default_factory=list)
    cost_lines: list = field(default_factory=lambda: [_FakeCostLine()])


@dataclass
class _FakeEstimate:
    id: int = 1
    estimate_number: str = "TG26-0001"
    product_type: str = "brochure"
    product_name: str = "Brochure A4"
    status: str = "calculated"
    input_spec_json: dict = field(default_factory=lambda: {"colors": 4, "sides": 2})
    options: list = field(default_factory=list)
    updated_at: datetime = field(default_factory=lambda: datetime(2026, 7, 1, 8, 0, 0))


class _FakeEstimateRepo:
    def __init__(self, estimate):
        self._estimate = estimate

    def get_by_id(self, estimate_id: int):
        return self._estimate if estimate_id == self._estimate.id else None


def _fake_estimate(**over) -> _FakeEstimate:
    est = _FakeEstimate(
        options=[
            _FakeOption(quantity=500, total_cost=1_200_000.4),
            _FakeOption(quantity=1000, total_cost=1_900_000.0),
        ]
    )
    for k, v in over.items():
        setattr(est, k, v)
    return est


def test_seam_13_costing_result():
    """SEAM-13 CLOSED: a calculated estimate yields a frozen CostingResult with
    cost_von_total + BOTH snapshot vế (unit price AND norms) so Báo giá copy-on-writes."""
    adapter = quotation_ports.EstimateCostingAdapter(_FakeEstimateRepo(_fake_estimate()))
    result = adapter.get_costing_result(1)
    # Default = first (lowest) quantity point; cost rounded to int VND.
    assert result.quantity == 500
    assert result.cost_von_total == 1_200_000
    assert result.unit_price_snapshot["cost_lines"][0]["category"] == "material"
    assert result.norm_snapshot["input_spec"] == {"colors": 4, "sides": 2}
    assert [o["quantity"] for o in result.quantity_options] == [500, 1000]

    # Explicit quantity point (bậc SL) — and an unknown one fails loudly.
    assert adapter.get_costing_result(1, quantity=1000).cost_von_total == 1_900_000
    with pytest.raises(quotation_ports.CostingLookupError, match="mức số lượng"):
        adapter.get_costing_result(1, quantity=750)

    # cost_hint (giá vốn phiếu đang giữ) picks the matching point for the freeze.
    assert adapter.get_costing_result(1, cost_hint=1_900_000).quantity == 1000

    # Non-calculated / missing / blocked estimates never yield a fabricated cost.
    with pytest.raises(quotation_ports.CostingLookupError, match="Không tìm thấy"):
        adapter.get_costing_result(99)
    draft_repo = _FakeEstimateRepo(_fake_estimate(status="draft"))
    with pytest.raises(quotation_ports.CostingLookupError, match="chưa ở trạng thái"):
        quotation_ports.EstimateCostingAdapter(draft_repo).get_costing_result(1)
    blocked = _fake_estimate()
    for o in blocked.options:
        o.warnings_json = [{"severity": "blocking_error", "code": "X"}]
    with pytest.raises(quotation_ports.CostingLookupError, match="lỗi chặn"):
        quotation_ports.EstimateCostingAdapter(_FakeEstimateRepo(blocked)).get_costing_result(1)


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


def test_seam_13_without_repo_raises():
    """A caller that forgot to wire the estimates repo must fail loudly (mirror of
    SEAM-14's convention) — never a silent fake cost."""
    with pytest.raises(NotImplementedError, match="SEAM-13"):
        quotation_ports.get_costing_result(costing_id=1)
