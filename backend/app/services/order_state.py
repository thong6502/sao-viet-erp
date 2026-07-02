"""Đơn hàng bán lifecycle state machine — spec-10 F8 (§9/§32 L825-829).

The transition table is the single source of truth for which status changes are legal:
``(from, to) -> Transition(action, requires_reason, gated, locks_snapshot)``.

- ``gated`` marks the ③→④ hard gate (draft→ordered): the service additionally requires
  ``quotation.approved AND deposit >= total*min_deposit_pct`` (§32 L827-828). The gate math
  runs now; the *deposit write* is TREO behind SEAM-04 (Payment, feat-048).
- ``requires_reason`` (cancel) needs a cancel_reason (+ cancelled_at_state captured so §32
  L817-825 hoàn/không-hoàn vật tư-cọc can be decided later).
- ``locks_snapshot`` marks draft→ordered: after chốt the order-line snapshot is read-only
  (sửa dòng đơn sau chốt → chặn; đổi phải change_order).

``change_order`` (đổi) giữ lịch sử qua Quotation-version, KHÔNG tạo parent_order_id
(decision #5). An unlisted ``(from, to)`` is illegal → the service raises (router → 409).
"""
from __future__ import annotations

from dataclasses import dataclass

from ..models.order import (
    STATUS_CANCELLED,
    STATUS_CHANGE_ORDER,
    STATUS_DRAFT,
    STATUS_ON_HOLD,
    STATUS_ORDERED,
)


@dataclass(frozen=True)
class Transition:
    action: str                 # audit action verb
    requires_reason: bool = False
    gated: bool = False         # ③→④ hard gate (approved AND deposit ≥ ngưỡng)
    locks_snapshot: bool = False


# (from, to) → Transition. Only these are legal.
TRANSITIONS: dict[tuple[str, str], Transition] = {
    # Chốt đơn: gate ③→④ (approved AND deposit ≥ total·min_deposit_pct) → snapshot khóa.
    (STATUS_DRAFT, STATUS_ORDERED): Transition(
        action="confirm_order", gated=True, locks_snapshot=True
    ),
    # Tạm giữ / bỏ tạm giữ.
    (STATUS_DRAFT, STATUS_ON_HOLD): Transition(action="hold_order"),
    (STATUS_ON_HOLD, STATUS_DRAFT): Transition(action="resume_order"),
    (STATUS_ORDERED, STATUS_ON_HOLD): Transition(action="hold_order"),
    (STATUS_ON_HOLD, STATUS_ORDERED): Transition(action="resume_order"),
    # Đổi đơn (re-quote giữ lịch sử qua Quotation-version). draft | ordered → change_order.
    (STATUS_DRAFT, STATUS_CHANGE_ORDER): Transition(action="change_order"),
    (STATUS_ORDERED, STATUS_CHANGE_ORDER): Transition(action="change_order"),
    # Hủy (needs a reason; captures cancelled_at_state) from any non-terminal working state.
    (STATUS_DRAFT, STATUS_CANCELLED): Transition(action="cancel_job", requires_reason=True),
    (STATUS_ORDERED, STATUS_CANCELLED): Transition(action="cancel_job", requires_reason=True),
    (STATUS_ON_HOLD, STATUS_CANCELLED): Transition(action="cancel_job", requires_reason=True),
}


def transition_for(from_status: str, to_status: str) -> Transition | None:
    """The Transition for a (from, to) pair, or None if it is illegal."""
    return TRANSITIONS.get((from_status, to_status))
