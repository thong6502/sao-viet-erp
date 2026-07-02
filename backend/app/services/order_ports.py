"""Ports (interfaces) the Đơn hàng bán screen DEPENDS ON — owned by the consumer
(Kinh doanh · Đơn hàng bán, bước ④) per DIP. Upstream modules implement these later;
until then each unresolved half is an explicit NotImplementedError stub (no silent fake
values).

Seam registry (source of truth = these markers + the matching skip-tests in
``backend/tests/test_seam_don_hang_ban.py``; ``docs/CROSS_MODULE_LINKS.md`` is only an index):

- SEAM-04 (⏳ TREO — quotation_ref LIVE, deposit_payment TREO): Đơn hàng bán ← Báo giá +
  Tài chính (Payment). TWO halves under one seam id:
    * ``quotation_ref(quotation_id) -> {approved, version, effective_from, total, customer_id,
      lines}`` — Báo giá IS built (feat-043..045), so this half is back-filled by a real
      adapter (``QuotationRefAdapter``) reading the live quotations repository (read-only).
    * ``record_deposit(order_id, amount) -> Payment(kind=deposit)`` — the Payment table is
      NOT built (feat-048), so this half keeps raising. The seam as a whole stays ⏳ until
      the deposit half closes; the enabling test ``test_seam_04_...`` stays skip.
- SEAM-05 (⏳ TREO): Đơn hàng bán ← Chế bản & Duyệt mẫu. ``proof_gate(order_id) ->
  {customer_approved}`` (read-only cổng ⑤→⑥ chỉ-báo, F6). Màn Đơn KHÔNG sở hữu gate này.
- SEAM-06 (⏳ TREO): Đơn hàng bán ← Kho. ``customer_paper_lot(order_id) -> [StockLot{...}]``
  (read-only ứng giấy khách, F4). Giấy khách cost=0 vẫn trừ tồn (§34 L871-873).

SEAM-01 (order_progress → Sản xuất) and SEAM-02 (delivery_status → Giao hàng) — F7 tiến độ SX
+ giao hàng read-only — are registered from P0; their enabling points live in the P0 seam set.
Both raise here until Sản xuất / Giao hàng are built.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ..models.quotation import STATUS_APPROVED


# --- SEAM-04 (a): quotation_ref — Báo giá (LIVE, back-filled) ------------------
@runtime_checkable
class QuotationRefPort(Protocol):
    """Downstream (Đơn hàng bán) port. Báo giá implements the read side.

    Read-only pull of an **approved** quotation so the order can pin
    ``quotation_id + version + effective_from`` (C1) and snapshot the priced lines
    copy-on-write. Đơn hàng bán reads it; Báo giá only flips ``status=approved`` — so no
    order-creation port lives on the Báo giá side (avoids an ADP cycle)."""

    def get_quotation_ref(self, quotation_id: int) -> "QuotationRef | None":  # pragma: no cover
        ...


@dataclass
class QuotationRefLine:
    """A priced line snapshot pulled from the quotation (copy-on-write source)."""

    description: str
    qty: int
    unit_price_snapshot: int | None
    norm_snapshot: dict = field(default_factory=dict)


@dataclass
class QuotationRef:
    """``{ quotation_id, version, approved, effective_from, total, customer_id, lines }``
    (read-only). ``approved`` gates the ③→④ pull (only an approved quotation is choosable)."""

    quotation_id: int
    version: int
    approved: bool
    effective_from: object | None
    total: int | None
    customer_id: int | None
    lines: list[QuotationRefLine] = field(default_factory=list)


class QuotationRefAdapter:
    """SEAM-04 (quotation_ref half) back-fill: resolve an approved quotation via the live
    Báo giá repository. Read-only — the order never mutates the quotation."""

    def __init__(self, quotations) -> None:
        self._quotations = quotations

    def get_quotation_ref(self, quotation_id: int) -> QuotationRef | None:
        q = self._quotations.get_by_id(quotation_id)
        if q is None:
            return None
        # One order-line snapshotted from the quotation's giá bán (đối ngoại: 1 số, no buildup).
        # The physical layer (khổ/màu/kẽm/imposition) is NEVER read here — ẩn khỏi Sale (§29 P0).
        lines = [
            QuotationRefLine(
                description=f"Báo giá {q.code} v{q.version}",
                qty=1,
                unit_price_snapshot=q.total,
                norm_snapshot={
                    "source": "quotation",
                    "quotation_id": q.id,
                    "quotation_version": q.version,
                    # Copy-on-write của vế định mức đã đóng băng ở báo giá (nếu có).
                    "quotation_norm_snapshot": q.norm_snapshot,
                },
            )
        ]
        return QuotationRef(
            quotation_id=q.id,
            version=q.version,
            approved=q.status == STATUS_APPROVED,
            effective_from=q.price_effective_from,
            total=q.total,
            customer_id=q.customer_id,
            lines=lines,
        )


def get_quotation_ref(quotation_id: int, *, quotations=None) -> QuotationRef | None:
    """Module-level convenience. With a repo it delegates to the real adapter (quotation_ref
    half back-filled); with none it raises so a mis-wired caller fails loudly rather than
    getting a fake value."""
    if quotations is None:
        # SEAM-04: quotation_ref cần repository Báo giá — a mis-wired caller must not fabricate.
        raise NotImplementedError("SEAM-04 (quotation_ref) cần repository Báo giá")
    return QuotationRefAdapter(quotations).get_quotation_ref(quotation_id)


# --- SEAM-04 (b): deposit_payment — Tài chính (Payment) — ⏳ STILL TREO --------
@runtime_checkable
class DepositPaymentPort(Protocol):
    """Downstream (Đơn hàng bán) port. Tài chính (Payment) implements this later.

    Ghi cọc = ``Payment(kind=deposit)``. Gate ③→④: ``deposit >= total*min_deposit_pct``
    (§32 L827-828). The Payment table is TREO (feat-048) — the stub raises so no fake cọc
    is recorded. The gate ARITHMETIC (còn thiếu bao nhiêu) is pure math over total the order
    already holds; only the *write* of a Payment row waits on this seam."""

    def record_deposit(self, order_id: int, amount: int) -> int:  # pragma: no cover
        ...

    def deposit_total(self, order_id: int) -> int:  # pragma: no cover
        ...


def record_deposit(order_id: int, amount: int) -> int:
    # SEAM-04: chờ Tài chính (Payment) — bảng Payment chưa build (feat-048)
    raise NotImplementedError("SEAM-04 (deposit_payment) chưa back-fill")


def deposit_total(order_id: int) -> int:
    # SEAM-04: chờ Tài chính (Payment) — cọc đã thu đọc từ Payment (feat-048)
    raise NotImplementedError("SEAM-04 (deposit_payment) chưa back-fill")


# --- SEAM-05: proof_gate — Chế bản & Duyệt mẫu — ⏳ TREO ----------------------
@runtime_checkable
class ProofGatePort(Protocol):
    """Downstream (Đơn hàng bán) port. Chế bản implements this later.

    Read-only chỉ-báo cổng ⑤→⑥ (``proof.customer_approved``, F6). Màn Đơn KHÔNG sở hữu gate
    này (thuộc Chế bản ⑤, §32 L828-829) — only shows it so KD biết đơn đã chốt nhưng còn kẹt
    duyệt mẫu."""

    def proof_gate(self, order_id: int) -> bool:  # pragma: no cover
        ...


def proof_gate(order_id: int) -> bool:
    # SEAM-05: chờ Chế bản & Duyệt mẫu (proof.customer_approved) — chưa build (feat-049)
    raise NotImplementedError("SEAM-05 chưa back-fill")


# --- SEAM-06: customer_paper_lot — Kho — ⏳ TREO ------------------------------
@runtime_checkable
class CustomerPaperLotPort(Protocol):
    """Downstream (Đơn hàng bán) port. Kho implements this later.

    Read-only liên kết lô giấy khách ``StockLot{ownership=customer, owner_customer_id, cost=0,
    actual_sheets}`` (F4 ứng giấy). Giấy khách cost=0 vẫn trừ tồn (§34 L871-873). Màn Đơn chỉ
    đọc — KHÔNG nhập tồn."""

    def customer_paper_lot(self, order_id: int) -> list:  # pragma: no cover
        ...


def customer_paper_lot(order_id: int) -> list:
    # SEAM-06: chờ Kho (lô giấy ownership=customer) — chưa build (feat-049)
    raise NotImplementedError("SEAM-06 chưa back-fill")


# --- SEAM-01 / SEAM-02: tiến độ SX + trạng thái giao (F7) — ⏳ TREO -----------
def get_production_progress(order_id: int) -> object:
    # SEAM-01: chờ Sản xuất (Job/PrintForm) — tiến độ SX read-only (F7), chưa build (feat-049)
    raise NotImplementedError("SEAM-01 chưa back-fill")


def get_delivery_status(order_id: int) -> object:
    # SEAM-02: chờ Giao hàng — trạng thái giao read-only (F7), chưa build (feat-049)
    raise NotImplementedError("SEAM-02 chưa back-fill")
