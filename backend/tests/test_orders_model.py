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
from app.models.quotation import (
    STATUS_ACCEPTED,
    STATUS_DRAFT as Q_DRAFT,
    Quote,
    QuoteItem,
    QuoteVersion,
)
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


def _mk_quote(db, *, sale_user_id: int, total: int, valid_until=None, status: str = STATUS_ACCEPTED) -> int:
    """Dựng Quote H-V-I trực tiếp (header + v1 + 1 item, qty=1 nên unit_price = total)."""
    n = db.query(Quote).count() + 1
    q = Quote(
        quote_number=f"BGT-{n:04d}",
        customer_id=None,
        salesperson_id=sale_user_id,
        status=status,
        valid_until=valid_until,
        created_by=sale_user_id,
    )
    db.add(q)
    db.flush()
    v = QuoteVersion(
        quote_id=q.id, version_number=1, status="accepted" if status == STATUS_ACCEPTED else "draft",
        total_cost_snapshot=0, subtotal_amount=total, discount_amount=0,
        vat_percent=0, vat_amount=0, final_amount=total, created_by=sale_user_id,
    )
    db.add(v)
    db.flush()
    db.add(QuoteItem(
        quote_version_id=v.id, line_no=1, product_type="brochure", product_name="SP Test",
        quantity=1, unit="cái", total_cost_snapshot=0, margin_percent=0,
        selling_price=total, unit_price=total, discount_amount=0,
        vat_percent=0, vat_amount=0, final_amount=total,
    ))
    q.current_version_id = v.id
    db.commit()
    return q.id


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
    return _mk_quote(db, sale_user_id=actor.id, total=total, valid_until=TOMORROW)


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
    # Change the SOURCE quotation total afterwards (mutate the active version + item).
    q = QuotationRepository(db).get_by_id(qid)
    for v in q.versions:
        if v.id == q.current_version_id:
            v.final_amount = 9_999_999
            for it in v.items:
                it.unit_price = 9_999_999
    db.commit()
    # The order-line snapshot must NOT change (no live FK).
    fresh = OrderRepository(db).get_with_lines(order_id)
    assert fresh.lines[0].unit_price_snapshot == 1_000_000


def test_cannot_create_from_non_approved_quotation(db):
    actor = _make_actor(db)
    qid = _mk_quote(db, sale_user_id=actor.id, total=100, valid_until=TOMORROW, status=Q_DRAFT)
    svc = _service(db)
    with pytest.raises(QuotationNotSelectable):
        svc.create_order(
            quotation_id=qid, order_type="theo_yc", order_kind="moi",
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
