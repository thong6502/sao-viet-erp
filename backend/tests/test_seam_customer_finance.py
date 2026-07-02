"""Enabling points for the Khách hàng (CRM) cross-module seams (spec-06-khach-hang).

Source of truth for each seam = the `# SEAM-NN` marker in app/ports/customer_finance_port.py
+ the matching skip test here. docs/CROSS_MODULE_LINKS.md is only an index.

NOTE: SEAM-03..14 were already claimed by other Kinh doanh specs (Sản phẩm, Đơn hàng
bán, Tính giá, Báo giá), so these CRM seams take a clear block, 16..18.

Back-fill DoD (per seam): make the skip test pass against the real provider, DELETE the
stub, flip ⏳→✅ in the registry, then remove the skip marker below.
"""
from __future__ import annotations

import pytest

from app.ports.customer_finance_port import (
    default_credit_override_port,
    default_receivable_port,
)


@pytest.mark.skip(reason="SEAM-16 Khách hàng cần AR balance từ Tài chính–Kế toán (cong_no) — chưa build")
def test_seam_16_receivable_balance():
    port = default_receivable_port()
    # After back-fill: a customer with an issued invoice must report its outstanding AR.
    assert port.get_ar_balance(customer_id=1) >= 0


@pytest.mark.skip(reason="SEAM-17 Khách hàng cần CreditOverride (duyệt vượt hạn mức) từ Kế toán — chưa build")
def test_seam_17_credit_override():
    port = default_credit_override_port()
    # After back-fill: recording an audited over-limit override returns its id.
    override_id = port.record_override(
        customer_id=1, over_amount=5_000_000, reason="đơn gấp", approver_user_id=1
    )
    assert override_id > 0


@pytest.mark.skip(reason="SEAM-18 Netting AR↔AP (khách cũng là NCC) — P1, chờ Cung ứng/AP — chưa build")
def test_seam_18_netting_ar_ap():
    # P1 per domain §35 (line 912): netting is NOT a P0 capability of the CRM screen.
    # Placeholder enabling point so the seam is discoverable; no port wired at P0.
    raise NotImplementedError("SEAM-18 chưa back-fill")


def test_seam_16_stub_raises():
    """The stub must raise, not silently return a fake balance (would hide over-limit)."""
    with pytest.raises(NotImplementedError, match="SEAM-16"):
        default_receivable_port().get_ar_balance(customer_id=1)


def test_seam_17_stub_raises():
    with pytest.raises(NotImplementedError, match="SEAM-17"):
        default_credit_override_port().record_override(
            customer_id=1, over_amount=1, reason="x", approver_user_id=1
        )
