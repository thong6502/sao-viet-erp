"""Enabling-point tests for the cross-module seams of màn "Đơn hàng bán" (spec-10).

Nguồn sự thật của seam = **marker `SEAM-NN` trong code** + **test skip/xfail mang đúng ID** (xem
`docs/CROSS_MODULE_LINKS.md`). Sổ CROSS_MODULE_LINKS.md chỉ là index.

Màn Đơn hàng bán (bước ④, DOMAIN_NHA_MAY_IN.md §8) là **downstream sở hữu port** (DIP): Kinh doanh
định nghĩa interface; các phân hệ upstream (Báo giá/Payment, Chế bản, Kho, Sản xuất, Giao hàng)
implement sau. Placeholder = stub raise NotImplementedError("SEAM-NN chưa back-fill") — KHÔNG số giả.

Back-fill xong: (a) test skip → xanh, (b) xoá stub, (c) đổi ⏳→✅ trong CROSS_MODULE_LINKS.md.

SEAM-01 (order_progress → Sản xuất) và SEAM-02 (delivery_status → Giao hàng) đã đăng ký từ trước
(P0 biết trước, dùng ở màn này qua F7) — enabling point của chúng nằm ở test_seam_01/02 riêng.
SEAM-03 đã do Sản phẩm dùng (SP→Giấy) — không tái dùng. Màn này cấp SEAM-04..06.
"""
from __future__ import annotations

import pytest

from app.services import order_ports


@pytest.mark.skip(
    reason="SEAM-04 chờ Báo giá + Tài chính(Payment): Order tham chiếu quotation "
    "approved (id+version+effective_from) và ghi cọc deposit — port quotation_ref/deposit_payment"
)
def test_seam_04_quotation_ref_and_deposit():
    """Kinh doanh sở hữu port `quotation_ref(quotation_id) -> {approved, version,
    effective_from, total}` + `record_deposit(order_id, amount) -> Payment(kind=deposit)`.

    Gate ③→④ (§32 dòng 827-828): `quotation.approved AND deposit >= total*min_deposit_pct`.
    Order-line snapshot copy-on-write từ báo giá (P0 §43 #5). Back-fill khi phân hệ Báo giá +
    bảng Payment tồn tại.
    """
    raise NotImplementedError("SEAM-04 chưa back-fill")


@pytest.mark.skip(
    reason="SEAM-05 chờ Chế bản & Duyệt mẫu: cổng ⑤→⑥ chỉ-báo read-only "
    "proof.customer_approved — port proof_gate"
)
def test_seam_05_proof_gate_indicator():
    """Kinh doanh sở hữu port `proof_gate(order_id) -> {customer_approved: bool}` (read-only).

    Màn Đơn KHÔNG sở hữu gate này (thuộc Chế bản ⑤, §32 dòng 828-829) — chỉ hiển thị để KD biết
    đơn đã chốt nhưng còn kẹt duyệt mẫu (F6, P1). Back-fill khi phân hệ Chế bản tồn tại.
    """
    raise NotImplementedError("SEAM-05 chưa back-fill")


@pytest.mark.skip(
    reason="SEAM-06 chờ Kho: liên kết đọc lô giấy khách ownership=customer, cost=0 "
    "(ứng giấy) — port customer_paper_lot"
)
def test_seam_06_customer_paper_lot():
    """Kinh doanh sở hữu port `customer_paper_lot(order_id) -> [StockLot{ownership=customer,
    owner_customer_id, cost=0, actual_sheets}]` (read-only).

    Cờ `has_customer_paper` ở Order; chi tiết lô sống ở Kho (§34 dòng 871-873): giấy khách cost=0
    vẫn trừ tồn. Màn Đơn chỉ liên kết đọc (F4). Back-fill khi phân hệ Kho tồn tại.
    """
    raise NotImplementedError("SEAM-06 chưa back-fill")


# --- Green enabling-point tests: the stubs MUST raise (no silent fake value) ---
# These stay XANH (the seam is *consumed*): they assert the placeholder raises the exact
# marker message. When a seam back-fills, its raising half is replaced by a real adapter and
# these switch to asserting the live behaviour (the module-level convenience keeps raising for
# a mis-wired caller).

def test_seam_04_deposit_payment_stub_raises():
    """SEAM-04 (deposit half): ghi/đọc cọc = Payment(kind=deposit) — Payment chưa build
    (feat-048). The stub must raise, never fabricate a paid amount."""
    with pytest.raises(NotImplementedError, match="SEAM-04 .deposit_payment. chưa back-fill"):
        order_ports.record_deposit(order_id=1, amount=100)
    with pytest.raises(NotImplementedError, match="SEAM-04 .deposit_payment. chưa back-fill"):
        order_ports.deposit_total(order_id=1)


def test_seam_04_quotation_ref_needs_repo():
    """SEAM-04 (quotation_ref half, Báo giá LIVE): the module-level convenience raises when a
    caller forgot to wire the Báo giá repo — no fake quotation slips through."""
    with pytest.raises(NotImplementedError, match="SEAM-04 .quotation_ref. cần repository"):
        order_ports.get_quotation_ref(quotation_id=1)


def test_seam_05_proof_gate_stub_raises():
    with pytest.raises(NotImplementedError, match="SEAM-05 chưa back-fill"):
        order_ports.proof_gate(order_id=1)


def test_seam_06_customer_paper_lot_stub_raises():
    with pytest.raises(NotImplementedError, match="SEAM-06 chưa back-fill"):
        order_ports.customer_paper_lot(order_id=1)


def test_seam_01_02_progress_delivery_stub_raise():
    """F7 tiến độ SX (SEAM-01) + trạng thái giao (SEAM-02) — Sản xuất/Giao hàng chưa build."""
    with pytest.raises(NotImplementedError, match="SEAM-01 chưa back-fill"):
        order_ports.get_production_progress(order_id=1)
    with pytest.raises(NotImplementedError, match="SEAM-02 chưa back-fill"):
        order_ports.get_delivery_status(order_id=1)
