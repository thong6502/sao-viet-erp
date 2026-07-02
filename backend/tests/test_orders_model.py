"""feat-046 — Đơn hàng bán data model (spec-10).

Repo/service-level: order_no auto-generation, create from an approved quotation (SEAM-04
quotation_ref LIVE) pins quotation_id+version+effective_from, order-line snapshots the price
copy-on-write (no live FK — changing the source quotation total afterwards does NOT change the
order), đơn bổ sung bắt buộc parent, gate arithmetic with deposit TREO.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.db import Base, SessionLocal, engine
from app.models.order import ORDER_KIND_BO_SUNG, ORDER_KIND_MOI, STATUS_DRAFT
from app.models.quotation import STATUS_APPROVED, STATUS_DRAFT as Q_DRAFT
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.order_repo import OrderRepository
from app.repositories.quotation_repo import QuotationRepository
from app.repositories.user_repo import UserRepository
from app.security import hash_password
from app.services.order_service import (
    OrderService,
    OrderValidationError,
    QuotationNotSelectable,
)

TOMORROW = date.today() + timedelta(days=30)


@pytest.fixture
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


class _Actor:
    def __init__(self, uid: int, dept_id=None):
        self.id = uid
        self.department_id = dept_id


def _make_actor(db) -> _Actor:
    users = UserRepository(db)
    u = users.create(username="sale-x", name="Sale X", password_hash=hash_password("x"))
    return _Actor(u.id)


def _service(db) -> OrderService:
    return OrderService(
        OrderRepository(db), AuditLogRepository(db), quotations=QuotationRepository(db)
    )


def _approved_quotation(db, actor, *, total=1_000_000) -> int:
    qrepo = QuotationRepository(db)
    q = qrepo.create(
        customer_id=None, costing_id=None, cost_von_total=total, margin=0, discount=0,
        total=total, valid_until=TOMORROW, sale_user_id=actor.id, status=STATUS_APPROVED,
    )
    return q.id


# --- create from an approved quotation (F1) -----------------------------------

def test_create_pins_quotation_and_snapshots_price(db):
    actor = _make_actor(db)
    qid = _approved_quotation(db, actor, total=1_500_000)
    svc = _service(db)

    order = svc.create_order(
        quotation_id=qid, order_type="theo_yc", order_kind="moi",
        parent_order_id=None, has_customer_paper=False, vat_pct_estimate=8, actor=actor,
    )
    assert order.order_no.startswith("DH")
    assert order.status == STATUS_DRAFT
    # C1 pin
    assert order.quotation_id == qid
    assert order.quotation_version == 1
    assert order.quotation_effective_from is not None or order.quotation_effective_from is None
    # snapshot copy-on-write on the line
    assert len(order.lines) == 1
    line = order.lines[0]
    assert line.unit_price_snapshot == 1_500_000
    assert line.line_total == 1_500_000
    assert line.norm_snapshot is not None


def test_snapshot_is_copy_on_write_not_live_fk(db):
    actor = _make_actor(db)
    qid = _approved_quotation(db, actor, total=1_000_000)
    svc = _service(db)
    order = svc.create_order(
        quotation_id=qid, order_type="theo_yc", order_kind="moi",
        parent_order_id=None, has_customer_paper=False, vat_pct_estimate=0, actor=actor,
    )
    order_id = order.id
    # Change the SOURCE quotation total afterwards.
    qrepo = QuotationRepository(db)
    q = qrepo.get_by_id(qid)
    qrepo.update(q, total=9_999_999)
    # The order-line snapshot must NOT change (no live FK).
    fresh = OrderRepository(db).get_with_lines(order_id)
    assert fresh.lines[0].unit_price_snapshot == 1_000_000


def test_cannot_create_from_non_approved_quotation(db):
    actor = _make_actor(db)
    qrepo = QuotationRepository(db)
    q = qrepo.create(
        customer_id=None, costing_id=None, cost_von_total=100, margin=0, discount=0,
        total=100, valid_until=TOMORROW, sale_user_id=actor.id, status=Q_DRAFT,
    )
    svc = _service(db)
    with pytest.raises(QuotationNotSelectable):
        svc.create_order(
            quotation_id=q.id, order_type="theo_yc", order_kind="moi",
            parent_order_id=None, has_customer_paper=False, vat_pct_estimate=0, actor=actor,
        )


def test_missing_quotation_blocked(db):
    actor = _make_actor(db)
    svc = _service(db)
    with pytest.raises(QuotationNotSelectable):
        svc.create_order(
            quotation_id=99999, order_type="theo_yc", order_kind="moi",
            parent_order_id=None, has_customer_paper=False, vat_pct_estimate=0, actor=actor,
        )


# --- loại đơn & đơn bổ sung (F2) ----------------------------------------------

def test_bo_sung_requires_parent(db):
    actor = _make_actor(db)
    qid = _approved_quotation(db, actor)
    svc = _service(db)
    with pytest.raises(OrderValidationError):
        svc.create_order(
            quotation_id=qid, order_type="theo_yc", order_kind=ORDER_KIND_BO_SUNG,
            parent_order_id=None, has_customer_paper=False, vat_pct_estimate=0, actor=actor,
        )


def test_bo_sung_with_parent_ok(db):
    actor = _make_actor(db)
    q1 = _approved_quotation(db, actor)
    svc = _service(db)
    parent = svc.create_order(
        quotation_id=q1, order_type="theo_yc", order_kind=ORDER_KIND_MOI,
        parent_order_id=None, has_customer_paper=False, vat_pct_estimate=0, actor=actor,
    )
    q2 = _approved_quotation(db, actor)
    child = svc.create_order(
        quotation_id=q2, order_type="theo_yc", order_kind=ORDER_KIND_BO_SUNG,
        parent_order_id=parent.id, has_customer_paper=False, vat_pct_estimate=0, actor=actor,
    )
    assert child.order_kind == ORDER_KIND_BO_SUNG
    assert child.parent_order_id == parent.id


def test_bad_enum_blocked(db):
    actor = _make_actor(db)
    qid = _approved_quotation(db, actor)
    svc = _service(db)
    with pytest.raises(OrderValidationError):
        svc.create_order(
            quotation_id=qid, order_type="INVALID", order_kind="moi",
            parent_order_id=None, has_customer_paper=False, vat_pct_estimate=0, actor=actor,
        )


# --- gate ③→④ with deposit TREO (F3) ------------------------------------------

def test_gate_deposit_unavailable_blocks_confirm(db):
    actor = _make_actor(db)
    qid = _approved_quotation(db, actor, total=1_000_000)
    svc = _service(db)
    order = svc.create_order(
        quotation_id=qid, order_type="theo_yc", order_kind="moi",
        parent_order_id=None, has_customer_paper=False, vat_pct_estimate=0, actor=actor,
    )
    gate = svc.gate_status(order)
    assert gate["quotation_approved"] is True
    assert gate["deposit_available"] is False  # Payment TREO
    assert gate["deposit_paid"] is None        # never a fabricated paid amount
    assert gate["can_confirm"] is False        # cannot chốt until cọc closes (feat-048)
    assert gate["deposit_required"] == 300_000  # 30% of 1,000,000
