"""feat-043 — Báo giá (Quotation) data model + lifecycle/version + snapshot (spec-09).

Service/repo level (no HTTP): sequential BG### codes, giá bán = giá vốn + lãi − chiết khấu,
snapshot copy-on-write freezes BOTH unit_price_snapshot AND norm_snapshot (P0), the state
machine allows/blocks the right transitions, change_order creates a new version keeping the
old one, and row_version optimistic locking clashes → conflict.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.db import SessionLocal, init_db
from app.models.quotation import (
    STATUS_APPROVED,
    STATUS_CHANGE_ORDER,
    STATUS_DRAFT,
    STATUS_REJECTED,
    STATUS_SENT,
)
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.customer_repo import CustomerRepository
from app.repositories.quotation_repo import QuotationRepository
from app.seed import seed_all
from app.services.quotation_service import (
    QuotationConflict,
    QuotationForbidden,
    QuotationLocked,
    QuotationService,
    QuotationValidationError,
)


@pytest.fixture
def db():
    init_db()
    session = SessionLocal()
    try:
        seed_all(session)
        yield session
    finally:
        session.close()


class _Actor:
    def __init__(self, id: int, department_id: int | None = 1) -> None:
        self.id = id
        self.department_id = department_id


def _svc(db) -> QuotationService:
    return QuotationService(
        QuotationRepository(db),
        AuditLogRepository(db),
        customers=CustomerRepository(db),
    )


TOMORROW = date.today() + timedelta(days=30)
YESTERDAY = date.today() - timedelta(days=1)


# --- create + giá bán ----------------------------------------------------------

def test_create_generates_sequential_bg_code_and_computes_total(db):
    svc = _svc(db)
    actor = _Actor(1)
    a = svc.create_quotation(
        customer_id=None, costing_id=None, cost_von_total=1_000_000,
        margin=200_000, discount=50_000, valid_until=TOMORROW, actor=actor,
    )
    b = svc.create_quotation(
        customer_id=None, costing_id=None, cost_von_total=500_000,
        margin=0, discount=0, valid_until=TOMORROW, actor=actor,
    )
    assert a.code.startswith("BG") and b.code.startswith("BG")
    assert a.code != b.code
    assert int(b.code[2:]) == int(a.code[2:]) + 1
    # giá bán = giá vốn + lãi − chiết khấu
    assert a.total == 1_000_000 + 200_000 - 50_000
    assert a.status == STATUS_DRAFT and a.version == 1


def test_total_is_none_when_cost_unknown(db):
    svc = _svc(db)
    q = svc.create_quotation(
        customer_id=None, costing_id=None, cost_von_total=None,
        margin=100_000, discount=0, valid_until=None, actor=_Actor(1),
    )
    assert q.total is None  # no fabricated number when giá vốn chưa nạp


def test_negative_amount_and_over_discount_and_past_date_blocked(db):
    svc = _svc(db)
    actor = _Actor(1)
    with pytest.raises(QuotationValidationError):
        svc.create_quotation(
            customer_id=None, costing_id=None, cost_von_total=-1,
            margin=0, discount=0, valid_until=None, actor=actor,
        )
    with pytest.raises(QuotationValidationError):
        svc.create_quotation(
            customer_id=None, costing_id=None, cost_von_total=100,
            margin=0, discount=200, valid_until=None, actor=actor,  # discount > cost+margin
        )
    with pytest.raises(QuotationValidationError):
        svc.create_quotation(
            customer_id=None, costing_id=None, cost_von_total=100,
            margin=0, discount=0, valid_until=YESTERDAY, actor=actor,  # past hạn
        )


# --- edit (draft only) + optimistic lock --------------------------------------

def test_edit_only_when_draft(db):
    svc = _svc(db)
    actor = _Actor(1)
    q = svc.create_quotation(
        customer_id=None, costing_id=None, cost_von_total=100,
        margin=10, discount=0, valid_until=TOMORROW, actor=actor,
    )
    svc.transition(quotation_id=q.id, to_status=STATUS_SENT, scope="all", actor=actor)
    with pytest.raises(QuotationLocked):
        svc.update_quotation(
            quotation_id=q.id, scope="all", actor=actor,
            customer_id=None, costing_id=None, cost_von_total=200,
            margin=10, discount=0, valid_until=TOMORROW, row_version=q.row_version,
        )


def test_stale_row_version_conflicts(db):
    svc = _svc(db)
    actor = _Actor(1)
    q = svc.create_quotation(
        customer_id=None, costing_id=None, cost_von_total=100,
        margin=10, discount=0, valid_until=TOMORROW, actor=actor,
    )
    with pytest.raises(QuotationConflict):
        svc.update_quotation(
            quotation_id=q.id, scope="all", actor=actor,
            customer_id=None, costing_id=None, cost_von_total=200,
            margin=10, discount=0, valid_until=TOMORROW, row_version=q.row_version + 5,
        )


# --- P0 snapshot copy-on-write -------------------------------------------------

def test_send_freezes_both_snapshots(db):
    svc = _svc(db)
    actor = _Actor(1)
    q = svc.create_quotation(
        customer_id=None, costing_id=None, cost_von_total=1_000_000,
        margin=300_000, discount=100_000, valid_until=TOMORROW, actor=actor,
    )
    sent = svc.transition(quotation_id=q.id, to_status=STATUS_SENT, scope="all", actor=actor)
    # P0: BOTH vế must be frozen together — a half-frozen snapshot is the same bug as a live FK.
    assert sent.unit_price_snapshot is not None
    assert sent.norm_snapshot is not None
    assert sent.price_effective_from is not None
    assert sent.unit_price_snapshot["total"] == 1_200_000


def test_snapshot_survives_source_change(db):
    """P0 observable: editing is blocked after send, and the frozen number is what's kept."""
    svc = _svc(db)
    actor = _Actor(1)
    q = svc.create_quotation(
        customer_id=None, costing_id=None, cost_von_total=1_000_000,
        margin=0, discount=0, valid_until=TOMORROW, actor=actor,
    )
    sent = svc.transition(quotation_id=q.id, to_status=STATUS_SENT, scope="all", actor=actor)
    frozen = sent.unit_price_snapshot["total"]
    # Even a re-quote (new version) carries forward the same snapshot origin; the SENT phiếu
    # keeps its frozen number regardless.
    assert frozen == 1_000_000
    assert sent.total == 1_000_000


# --- state machine -------------------------------------------------------------

def test_illegal_transition_blocked(db):
    svc = _svc(db)
    actor = _Actor(1)
    q = svc.create_quotation(
        customer_id=None, costing_id=None, cost_von_total=100,
        margin=0, discount=0, valid_until=TOMORROW, actor=actor,
    )
    # draft → approved is illegal (must go through sent first).
    with pytest.raises(QuotationConflict):
        svc.transition(quotation_id=q.id, to_status=STATUS_APPROVED, scope="all", actor=actor)


def test_approve_requires_approver_permission(db):
    svc = _svc(db)
    actor = _Actor(1)
    q = svc.create_quotation(
        customer_id=None, costing_id=None, cost_von_total=100,
        margin=0, discount=0, valid_until=TOMORROW, actor=actor,
    )
    svc.transition(quotation_id=q.id, to_status=STATUS_SENT, scope="all", actor=actor)
    # A Sale (scope=own) cannot approve → forbidden.
    with pytest.raises(QuotationForbidden):
        svc.transition(quotation_id=q.id, to_status=STATUS_APPROVED, scope="own", actor=actor)
    # A manager (scope=all|department) can.
    approved = svc.transition(
        quotation_id=q.id, to_status=STATUS_APPROVED, scope="all", actor=actor
    )
    assert approved.status == STATUS_APPROVED


def test_reject_from_sent(db):
    svc = _svc(db)
    actor = _Actor(1)
    q = svc.create_quotation(
        customer_id=None, costing_id=None, cost_von_total=100,
        margin=0, discount=0, valid_until=TOMORROW, actor=actor,
    )
    svc.transition(quotation_id=q.id, to_status=STATUS_SENT, scope="all", actor=actor)
    rejected = svc.transition(
        quotation_id=q.id, to_status=STATUS_REJECTED, scope="department", actor=actor
    )
    assert rejected.status == STATUS_REJECTED


def test_cancel_requires_reason_and_records_state(db):
    svc = _svc(db)
    actor = _Actor(1)
    q = svc.create_quotation(
        customer_id=None, costing_id=None, cost_von_total=100,
        margin=0, discount=0, valid_until=TOMORROW, actor=actor,
    )
    with pytest.raises(QuotationValidationError):
        svc.transition(quotation_id=q.id, to_status="cancelled", scope="all", actor=actor)
    cancelled = svc.transition(
        quotation_id=q.id, to_status="cancelled", scope="all", actor=actor,
        cancel_reason="khách đổi ý",
    )
    assert cancelled.status == "cancelled"
    assert cancelled.cancel_reason == "khách đổi ý"
    assert cancelled.cancelled_at_state == STATUS_DRAFT


def test_expired_blocks_approval(db):
    svc = _svc(db)
    actor = _Actor(1)
    # valid_until today is fine at create; force a past date on the row to simulate expiry.
    q = svc.create_quotation(
        customer_id=None, costing_id=None, cost_von_total=100,
        margin=0, discount=0, valid_until=date.today(), actor=actor,
    )
    svc.transition(quotation_id=q.id, to_status=STATUS_SENT, scope="all", actor=actor)
    # Backdate valid_until directly (repo update bypasses the create-time guard).
    QuotationRepository(db).update(q, valid_until=YESTERDAY)
    # Next transition sees the time guard → expired, so approve is illegal.
    with pytest.raises(QuotationConflict):
        svc.transition(quotation_id=q.id, to_status=STATUS_APPROVED, scope="all", actor=actor)


# --- version / change_order ----------------------------------------------------

def test_requote_creates_new_version_keeping_old(db):
    svc = _svc(db)
    actor = _Actor(1)
    q = svc.create_quotation(
        customer_id=None, costing_id=None, cost_von_total=100,
        margin=10, discount=0, valid_until=TOMORROW, actor=actor,
    )
    svc.transition(quotation_id=q.id, to_status=STATUS_SENT, scope="all", actor=actor)
    new_v = svc.requote(quotation_id=q.id, scope="all", actor=actor)
    assert new_v.code == q.code
    assert new_v.version == q.version + 1
    assert new_v.status == STATUS_DRAFT
    # The old phiếu is superseded but still retrievable (history kept).
    old = svc.get_quotation(quotation_id=q.id, scope="all", actor=actor)
    assert old.status == STATUS_CHANGE_ORDER
    chain = svc.version_history(new_v)
    assert len(chain) == 2
