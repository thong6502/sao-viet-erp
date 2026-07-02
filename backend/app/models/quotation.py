"""Báo giá (Quotation) ORM model — spec-09-bao-gia.

A **quotation** (phiếu chào giá đối ngoại) references ONE Tính giá result (giá vốn) and
adds lãi + chiết khấu → **giá bán** shown to the customer, moves through the lifecycle
``draft → sent → approved/rejected/expired`` (+ ``cancelled`` / ``on_hold`` /
``change_order``), and — at chốt-giá — **snapshots** the unit price AND the norms
copy-on-write so a later price-list change never rewrites a phiếu đã gửi.

P0 invariants honoured here (§34 L877-879, §43#5 L1209):
  - **Snapshot copy-on-write**: ``unit_price_snapshot`` (JSON) **and** ``norm_snapshot``
    (JSON) + ``price_effective_from/to`` are stored ON the quotation — there is NO live FK
    to the price/norm tables. ``norm_snapshot`` is ngang hàng ``unit_price_snapshot``
    (bậc SL phụ thuộc bù hao/định mức — snapshot thiếu vế định mức = cùng lỗ như FK sống).
  - **Không phơi giá thành**: the buildup (số con/khổ, số tờ, số bản kẽm, bù hao) is NOT
    stored/shown here — Báo giá references only ``cost_von_total`` (1 số) via SEAM-13.

Cross-module reads are SEAMS (owned by this consumer per DIP; upstream implements later):
  - ``customer_id`` — read via **SEAM-14** (CRM); a plain nullable Integer + FK→customers.id
    (CRM lives in the SAME app), but the display read still goes through the port.
  - ``costing_id`` — read via **SEAM-13** (Tính giá); a plain nullable Integer (no FK —
    the frozen costing *result* / giá vốn engine is still TREO behind SEAM-07..12).

The Báo giá → Đơn hàng handoff is NOT modelled here: Đơn hàng bán pulls the approved
quotation via spec-10 SEAM-04 (avoids an ADP cycle). Portable across SQLite and Postgres.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from ..db import Base

# --- Lifecycle (§9 L280-298, §32 L825-829, §41 L1132) --------------------------
# Stored as plain strings; the state machine + guards live in QuotationService.
STATUS_DRAFT = "draft"          # đang lập (editable)
STATUS_SENT = "sent"           # đã gửi khách (snapshot chốt)
STATUS_APPROVED = "approved"   # đã duyệt (sẵn sàng lên đơn — Đơn hàng bán kéo)
STATUS_REJECTED = "rejected"   # bị từ chối
STATUS_EXPIRED = "expired"     # quá valid_until (chặn duyệt)
STATUS_CANCELLED = "cancelled"  # đã hủy (+cancel_reason, cancelled_at_state)
STATUS_ON_HOLD = "on_hold"     # tạm giữ
STATUS_CHANGE_ORDER = "change_order"  # re-quote đã sinh version mới (phiếu cũ giữ lịch sử)

QUOTATION_STATUSES = (
    STATUS_DRAFT,
    STATUS_SENT,
    STATUS_APPROVED,
    STATUS_REJECTED,
    STATUS_EXPIRED,
    STATUS_CANCELLED,
    STATUS_ON_HOLD,
    STATUS_CHANGE_ORDER,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Quotation(Base):
    __tablename__ = "quotations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # System-generated code (BG001, BG002…). Shared across the version chain of a re-quote:
    # a change_order keeps the SAME code and bumps `version` (BG001 v1 → v2). Not unique on
    # its own (the (code, version) pair is), so it is only indexed here.
    code: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    # Version within a code chain (1, 2, 3…). change_order (re-quote) sinh version mới,
    # giữ phiếu cũ tra được (§34 L826, F4).
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # SEAM-14: the customer this quotation is addressed to. FK→customers.id (CRM is same-app)
    # but the display read (name / công nợ) goes through the CustomerLookup port. Nullable so
    # a draft can start before a customer is picked.
    customer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="SET NULL"), index=True, nullable=True
    )
    # SEAM-13: the Tính giá result this quotation references. Plain nullable Integer (NO FK):
    # the frozen costing *result* / giá vốn engine is still TREO behind SEAM-07..12, so we do
    # not couple to a live costing row for the priced number.
    costing_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)

    # Giá vốn tổng (1 số) pulled from Tính giá via SEAM-13. NOT a buildup — số con/khổ, số
    # tờ, số bản kẽm, bù hao are NEVER stored here (tài liệu đối ngoại, L1132/L1218).
    cost_von_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Lãi (markup) in VND: giá bán = giá vốn + lãi (F2). ≥ 0 (validated in service).
    margin: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Chiết khấu / bậc SL in VND (subtracted). ≥ 0 and ≤ (giá vốn + lãi) (validated).
    discount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Tổng giá bán = cost_von_total + margin − discount. Derived + stored so a list query
    # need not recompute; recomputed on every save.
    total: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Hạn hiệu lực (L258-259). Quá hạn → status=expired (chặn duyệt).
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Lifecycle status (see QUOTATION_STATUSES).
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=STATUS_DRAFT
    )
    # Set only when status=cancelled (F4).
    cancel_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cancelled_at_state: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # --- P0 snapshot copy-on-write (§34 L877-879, §43#5 L1209) ------------------
    # Set at Chốt giá / Gửi. unit_price_snapshot AND norm_snapshot are stored TOGETHER
    # (norm ngang hàng price) so a later price/norm change never rewrites this phiếu.
    unit_price_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    norm_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Effective window of the source price list at snapshot time (copy-on-write, NOT a FK).
    price_effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    price_effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Optimistic-locking version (§34 L898): a concurrent edit with a stale row_version → 409.
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Owning Sale (KD) — RBAC data-scope owner (own/department/all, §41 L1128).
    sale_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
