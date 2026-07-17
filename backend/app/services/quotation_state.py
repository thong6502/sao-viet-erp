"""Báo giá lifecycle state machine — H-V-I (Quote → QuoteVersion → QuoteItem).

The transition table mirrors the legality rules implemented in
``QuotationService.transition`` / ``requote`` — it is the DISPLAY source of truth the
router uses to compute ``allowed_transitions`` (which action buttons the UI shows).
If the service rules change, change this table with them.

- ``snapshots`` marks the transition that freezes the internal cost snapshot
  copy-on-write (draft→sent = Chốt giá / Gửi khách, P0 §34 L877-879).
- ``requires_reason`` (cancel) needs a cancel_reason.
- ``expired`` is reached from a time guard (past valid_until) inside the service,
  listed here so the UI can render the "Đánh dấu hết hạn" state.
- Re-quote (new version) is NOT a status transition — it is ``POST /requote``
  (legal from sent/accepted/rejected, see service).
"""
from __future__ import annotations

from dataclasses import dataclass

from ..models.quotation import (
    STATUS_ACCEPTED,
    STATUS_APPROVED,
    STATUS_CANCELLED,
    STATUS_CONVERTED_TO_ORDER,
    STATUS_DRAFT,
    STATUS_EXPIRED,
    STATUS_PENDING_APPROVAL,
    STATUS_REJECTED,
    STATUS_SENT,
)


@dataclass(frozen=True)
class Transition:
    action: str                 # audit action verb
    requires_approval: bool = False
    requires_reason: bool = False
    snapshots: bool = False


# (from, to) → Transition. Only these are legal (mirror of QuotationService.transition).
# LƯU Ý: cửa DUYỆT đặc thù (pending_approval → sent / → draft) do endpoint POST /approval
# (record_approval) lái, KHÔNG qua /transition — nên KHÔNG liệt kê ở đây (xem redesign-bao-gia §3).
TRANSITIONS: dict[tuple[str, str], Transition] = {
    # Gửi khách: khóa phiên bản + freeze snapshot. draft → sent (báo giá THƯỜNG; đặc thù phải qua duyệt).
    (STATUS_DRAFT, STATUS_SENT): Transition(action="send_quote", snapshots=True),
    # Đặc thù ĐÃ ĐƯỢC GĐ DUYỆT (approved) → SALE tự gửi khách (approved → sent), freeze tại mốc gửi.
    (STATUS_APPROVED, STATUS_SENT): Transition(action="send_quote", snapshots=True),
    # Trình duyệt: draft → pending_approval (CHỈ báo giá đặc thù) → chờ Giám đốc Kinh doanh.
    (STATUS_DRAFT, STATUS_PENDING_APPROVAL): Transition(action="submit_approval"),
    # Khách chốt: sent → accepted (service cũng cho draft → accepted khi chốt trực tiếp, báo giá thường).
    (STATUS_SENT, STATUS_ACCEPTED): Transition(action="accept_quote"),
    (STATUS_DRAFT, STATUS_ACCEPTED): Transition(action="accept_quote"),
    # Khách từ chối: sent → rejected.
    (STATUS_SENT, STATUS_REJECTED): Transition(action="reject_quote"),
    # Hết hạn: time guard trong service (valid_until đã qua) — hiển thị, không phải nút bấm tùy ý.
    (STATUS_SENT, STATUS_EXPIRED): Transition(action="expire_quote"),
    # Lên đơn hàng: accepted → converted_to_order (đặt bởi module Đơn hàng bán khi tạo đơn — khóa 1BG=1đơn).
    (STATUS_ACCEPTED, STATUS_CONVERTED_TO_ORDER): Transition(action="convert_to_order"),
    # Hủy (cần lý do) từ các trạng thái đang làm việc (trước khi lên đơn).
    (STATUS_DRAFT, STATUS_CANCELLED): Transition(action="cancel_quote", requires_reason=True),
    (STATUS_PENDING_APPROVAL, STATUS_CANCELLED): Transition(action="cancel_quote", requires_reason=True),
    (STATUS_APPROVED, STATUS_CANCELLED): Transition(action="cancel_quote", requires_reason=True),
    (STATUS_SENT, STATUS_CANCELLED): Transition(action="cancel_quote", requires_reason=True),
    (STATUS_ACCEPTED, STATUS_CANCELLED): Transition(action="cancel_quote", requires_reason=True),
    (STATUS_REJECTED, STATUS_CANCELLED): Transition(action="cancel_quote", requires_reason=True),
}


def transition_for(from_status: str, to_status: str) -> Transition | None:
    """The Transition for a (from, to) pair, or None if it is illegal."""
    return TRANSITIONS.get((from_status, to_status))
