"""Báo giá lifecycle state machine — spec-09 F4/F5 (§9 L280-298, §32 L825-827).

The transition table is the single source of truth for which status changes are legal:
``(from, to) -> Transition(action, requires_approval, requires_reason, snapshots)``.

- ``requires_approval`` transitions (approve/reject) need the approver permission (ngưỡng
  X/Y — values are SVN-input, versioned, ⚠️ chưa xác nhận; at P0 mapped to the manager
  scope of ``bao_gia`` in the service, not a fabricated number).
- ``requires_reason`` (cancel) needs a cancel_reason (+ cancelled_at_state captured).
- ``snapshots`` marks the transition that freezes unit_price_snapshot + norm_snapshot
  copy-on-write (draft→sent = Chốt giá / Gửi, P0 §34 L877-879).

An unlisted ``(from, to)`` is an illegal transition → the service raises (router → 409/422).
``expired`` is reached from a time guard (past valid_until), not a user click.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..models.quotation import (
    STATUS_APPROVED,
    STATUS_CANCELLED,
    STATUS_CHANGE_ORDER,
    STATUS_DRAFT,
    STATUS_EXPIRED,
    STATUS_ON_HOLD,
    STATUS_REJECTED,
    STATUS_SENT,
)


@dataclass(frozen=True)
class Transition:
    action: str                 # audit action verb
    requires_approval: bool = False
    requires_reason: bool = False
    snapshots: bool = False


# (from, to) → Transition. Only these are legal.
TRANSITIONS: dict[tuple[str, str], Transition] = {
    # Chốt giá / Gửi khách: freeze the snapshot (P0). draft → sent.
    (STATUS_DRAFT, STATUS_SENT): Transition(action="send_quote", snapshots=True),
    # Duyệt / Từ chối (approver only). sent → approved | rejected.
    (STATUS_SENT, STATUS_APPROVED): Transition(
        action="approve_quote", requires_approval=True
    ),
    (STATUS_SENT, STATUS_REJECTED): Transition(
        action="reject_quote", requires_approval=True
    ),
    # Hết hạn: sent → expired (time guard; chặn duyệt afterwards).
    (STATUS_SENT, STATUS_EXPIRED): Transition(action="expire_quote"),
    # Tạm giữ / bỏ tạm giữ. sent ↔ on_hold.
    (STATUS_SENT, STATUS_ON_HOLD): Transition(action="hold_quote"),
    (STATUS_ON_HOLD, STATUS_SENT): Transition(action="resume_quote"),
    (STATUS_ON_HOLD, STATUS_EXPIRED): Transition(action="expire_quote"),
    # Re-quote (change_order): supersede the current phiếu (a new version is created
    # separately). sent | approved | rejected → change_order.
    (STATUS_SENT, STATUS_CHANGE_ORDER): Transition(action="change_order"),
    (STATUS_APPROVED, STATUS_CHANGE_ORDER): Transition(action="change_order"),
    (STATUS_REJECTED, STATUS_CHANGE_ORDER): Transition(action="change_order"),
    # Hủy from any non-terminal working state (needs a reason).
    (STATUS_DRAFT, STATUS_CANCELLED): Transition(
        action="cancel_quote", requires_reason=True
    ),
    (STATUS_SENT, STATUS_CANCELLED): Transition(
        action="cancel_quote", requires_reason=True
    ),
    (STATUS_ON_HOLD, STATUS_CANCELLED): Transition(
        action="cancel_quote", requires_reason=True
    ),
    (STATUS_APPROVED, STATUS_CANCELLED): Transition(
        action="cancel_quote", requires_reason=True
    ),
    (STATUS_REJECTED, STATUS_CANCELLED): Transition(
        action="cancel_quote", requires_reason=True
    ),
}


def transition_for(from_status: str, to_status: str) -> Transition | None:
    """The Transition for a (from, to) pair, or None if it is illegal."""
    return TRANSITIONS.get((from_status, to_status))
