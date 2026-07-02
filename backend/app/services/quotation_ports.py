"""Ports (interfaces) the Báo giá (Quotation) screen DEPENDS ON — owned by the
consumer (Kinh doanh · Báo giá) per DIP. Upstream modules implement these later;
until then each is an explicit NotImplementedError stub (no silent fake values).

Seam registry (source of truth = these markers + the matching skip-tests in
``backend/tests/test_seam_quotation.py``; ``docs/CROSS_MODULE_LINKS.md`` is only an index):

- SEAM-13 (✅ ĐÃ ĐÓNG): Báo giá ← Tính giá (costing engine). Back-filled by
  ``EstimateCostingAdapter``: the Tính giá engine (Phase 2A) now produces frozen
  ``EstimateOption`` results (total + cost lines with per-line price/norm snapshots), so a
  quotation referencing a *calculated* estimate pulls ``cost_von_total`` + copy-on-write
  ``unit_price_snapshot``/``norm_snapshot`` for the chosen quantity point. The bare module
  call (no repo) still raises so a mis-wired caller fails loudly — never a fabricated cost.
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


# --- SEAM-13: Tính giá (costing engine) — ✅ ĐÃ ĐÓNG (Estimate engine đã build) -
@runtime_checkable
class CostingResultPort(Protocol):
    """Downstream (Báo giá) port. Tính giá implements this (back-filled).

    A Báo giá line is built ON TOP of a frozen Tính giá result: the quotation
    must snapshot the unit price AND the norms (copy-on-write, P0 §34 L877-878)
    — never a live FK to the price/norm tables.
    """

    def get_costing_result(self, costing_id: int) -> "CostingResult":  # pragma: no cover
        ...


class CostingLookupError(LookupError):
    """SEAM-13 is back-filled but the referenced Tính giá cannot yield a frozen result
    (not found / not calculated / blocking errors / unknown quantity point). Message is
    user-facing — the UI shows it verbatim instead of a fabricated cost."""


@dataclass
class CostingResult:
    """Frozen cost-of-goods result Báo giá snapshots. Shape (owned by consumer):
    ``{ costing_id, cost_von_total, unit_price_snapshot, norm_snapshot,
        price_effective_from, price_effective_to }`` + the quantity point the cost
    belongs to and the other quantity points available on the same estimate (bậc SL).
    """

    costing_id: int
    cost_von_total: int
    unit_price_snapshot: dict
    norm_snapshot: dict
    price_effective_from: object | None = None
    price_effective_to: object | None = None
    quantity: int | None = None
    quantity_options: list | None = None


def _blocking(option) -> bool:
    return any(
        w.get("severity") == "blocking_error" for w in (option.warnings_json or [])
    )


class EstimateCostingAdapter:
    """SEAM-13 back-fill: pull the frozen giá-vốn result off a *calculated* Tính giá
    (Estimate). Read-only — Báo giá never mutates the estimate, and the numbers come from
    the stored ``EstimateOption``/``EstimateCostLine`` rows (already frozen at calc time),
    NOT from the live price/norm tables."""

    def __init__(self, estimates) -> None:
        # Anything with ``get_by_id(id) -> Estimate | None`` (EstimateRepository in prod).
        self._estimates = estimates

    def get_costing_result(
        self,
        costing_id: int,
        quantity: int | None = None,
        cost_hint: int | None = None,
    ) -> CostingResult:
        est = self._estimates.get_by_id(costing_id)
        if est is None:
            raise CostingLookupError(f"Không tìm thấy Tính giá #{costing_id}.")
        if est.status != "calculated":
            raise CostingLookupError(
                f"Tính giá {est.estimate_number} chưa ở trạng thái 'Đã tính toán' — tính lại trước khi tham chiếu."
            )
        options = [o for o in est.options if not _blocking(o)]
        if not options:
            raise CostingLookupError(
                f"Tính giá {est.estimate_number} không có phương án hợp lệ (còn lỗi chặn)."
            )

        # Chọn mức số lượng (bậc SL): theo quantity nếu chỉ định; theo cost_hint (giá vốn
        # phiếu đang giữ — để snapshot đúng mức KD đã chọn); mặc định mức đầu (SL thấp nhất).
        chosen = None
        if quantity is not None:
            chosen = next((o for o in options if o.quantity == quantity), None)
            if chosen is None:
                have = ", ".join(str(o.quantity) for o in options)
                raise CostingLookupError(
                    f"Tính giá {est.estimate_number} không có mức số lượng {quantity} (có: {have})."
                )
        elif cost_hint is not None:
            chosen = next(
                (o for o in options if int(round(float(o.total_cost))) == cost_hint), None
            )
        if chosen is None:
            chosen = options[0]

        cost = int(round(float(chosen.total_cost)))
        qty_points = [
            {"quantity": o.quantity, "total_cost": int(round(float(o.total_cost)))}
            for o in options
        ]

        unit_price_snapshot = {
            "source": "estimate",
            "estimate_id": est.id,
            "estimate_number": est.estimate_number,
            "product_type": est.product_type,
            "product_name": est.product_name,
            "quantity": chosen.quantity,
            "cost_von_total": cost,
            "quantity_options": qty_points,
            # Per-line frozen prices (source_snapshot = giá nguồn đã đóng băng lúc tính).
            "cost_lines": [
                {
                    "category": line.category,
                    "description": line.description,
                    "quantity": float(line.quantity),
                    "unit": line.unit,
                    "unit_cost": float(line.unit_cost),
                    "setup_cost": float(line.setup_cost or 0),
                    "total_cost": float(line.total_cost),
                    "source_type": line.source_type,
                    "source_id": line.source_id,
                    "source_snapshot": line.source_snapshot_json,
                }
                for line in chosen.cost_lines
            ],
        }
        norm_snapshot = {
            "source": "estimate",
            "estimate_id": est.id,
            "estimate_number": est.estimate_number,
            "quantity": chosen.quantity,
            # Spec đầu vào + vế định mức: calc snapshot từng dòng (bù hao/định mức đã áp).
            "input_spec": est.input_spec_json,
            "calc_lines": [
                {
                    "category": line.category,
                    "source_type": line.source_type,
                    "source_id": line.source_id,
                    "calculation_snapshot": line.calculation_snapshot_json,
                }
                for line in chosen.cost_lines
            ],
        }
        calculated_at = est.updated_at.date() if est.updated_at else None
        return CostingResult(
            costing_id=est.id,
            cost_von_total=cost,
            unit_price_snapshot=unit_price_snapshot,
            norm_snapshot=norm_snapshot,
            price_effective_from=calculated_at,
            price_effective_to=None,
            quantity=chosen.quantity,
            quantity_options=qty_points,
        )


def get_costing_result(
    costing_id: int,
    quantity: int | None = None,
    cost_hint: int | None = None,
    *,
    estimates=None,
) -> CostingResult:
    """Module-level convenience (mirror of ``get_customer``). With a repository it
    delegates to the real adapter (SEAM-13 closed); with none it raises the historical
    stub so a caller that forgot to wire the adapter fails loudly — never a fake cost."""
    if estimates is None:
        # SEAM-13 has no live repo here — a mis-wired caller must not get a fake value.
        raise NotImplementedError("SEAM-13 cần repository Tính giá (Estimate)")
    return EstimateCostingAdapter(estimates).get_costing_result(
        costing_id, quantity=quantity, cost_hint=cost_hint
    )


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
