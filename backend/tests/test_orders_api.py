"""Đơn hàng bán — service-level tests (redesign-don-hang-ban.md P1–P5).

Dựng DB in-memory + seed, rồi chạy OrderService end-to-end: 2 nguồn (báo giá/nhập tay),
snapshot NET sau chiết khấu, cọc đa hình thức, duyệt, cổng chốt + khóa báo giá, hủy + seam.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.db import Base, SessionLocal, engine
from app.db_migrations import run_migrations
from app.models.customer import Customer
from app.models.quotation import STATUS_ACCEPTED, Quote, QuoteItem, QuoteVersion
from app.models.user import User
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.order_repo import OrderRepository
from app.repositories.quotation_repo import QuotationRepository
from app.schemas.order import (
    OrderCreate,
    OrderDepositIn,
    OrderLineIn,
    OrderUpdate,
)
from app.seed import seed_all
from app.services.order_service import (
    OrderConflict,
    OrderForbidden,
    OrderService,
    OrderValidationError,
)


@pytest.fixture
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    s = SessionLocal()
    run_migrations(s)
    seed_all(s)
    yield s
    s.close()


@pytest.fixture
def admin(db):
    return db.query(User).filter(User.username == "admin").first()


@pytest.fixture
def customer(db):
    c = Customer(code="KH-T", name="KH Test")
    db.add(c)
    db.commit()
    return c


@pytest.fixture
def svc(db):
    return OrderService(OrderRepository(db), AuditLogRepository(db), QuotationRepository(db), db)


def _accepted_quote(db, customer, *, selling=1_000_000, discount=100_000, vat=8, qty=1000, cost=600_000):
    q = Quote(quote_number="BG-T", customer_id=customer.id, status=STATUS_ACCEPTED)
    db.add(q)
    db.flush()
    v = QuoteVersion(quote_id=q.id, version_number=1, vat_percent=vat)
    db.add(v)
    db.flush()
    q.current_version_id = v.id
    net = selling - discount
    db.add(QuoteItem(
        quote_version_id=v.id, line_no=1, product_type="tr", product_name="SP",
        quantity=qty, unit="cái", selling_price=selling, discount_amount=discount,
        unit_price=selling / qty, vat_percent=vat, vat_amount=net * vat / 100,
        final_amount=net + net * vat / 100, total_cost_snapshot=cost, margin_percent=20,
    ))
    db.commit()
    return q


# --- P1: nguồn nhập tay -------------------------------------------------------
def test_create_manual_no_cost_needs_approval(svc, admin, customer):
    d = svc.create(actor=admin, scope="all", payload=OrderCreate(
        source_type="nhap_tay", customer_id=customer.id,
        lines=[OrderLineIn(description="Danh thiếp", qty=1000, unit_price=500, vat_pct=8)],
        vat_pct_estimate=8,
    ))
    assert d.cost_basis == "none"
    assert d.needs_approval is True
    assert d.margin_pct is None          # biên "không xác định", KHÔNG 0/100
    assert d.total == 500_000
    assert d.total_with_vat == 540_000


def test_manual_requires_customer_and_lines(svc, admin):
    with pytest.raises(OrderValidationError):
        svc.create(actor=admin, scope="all", payload=OrderCreate(source_type="nhap_tay", lines=[]))


# --- P1: nguồn báo giá — snapshot NET sau chiết khấu --------------------------
def test_create_from_quote_line_total_is_net_after_discount(svc, admin, customer, db):
    q = _accepted_quote(db, customer)
    d = svc.create(actor=admin, scope="all", payload=OrderCreate(source_type="bao_gia", quotation_id=q.id))
    assert d.cost_basis == "quote"
    assert d.needs_approval is False
    assert d.total == 900_000            # NET (1.000.000 − 100.000), KHÔNG phồng theo unit_price gộp
    assert d.total_with_vat == 972_000
    assert d.deposit_pct is None         # % cọc KHÔNG còn ghim từ báo giá — thỏa thuận lúc chốt đơn
    assert d.deposit_required == 0
    assert d.margin_pct == 33            # (900k−600k)/900k


def test_one_quote_one_order_guard(svc, admin, customer, db):
    q = _accepted_quote(db, customer)
    svc.create(actor=admin, scope="all", payload=OrderCreate(source_type="bao_gia", quotation_id=q.id))
    with pytest.raises(OrderConflict):
        svc.create(actor=admin, scope="all", payload=OrderCreate(source_type="bao_gia", quotation_id=q.id))


# --- P2: cọc đa hình thức + đối chiếu CK --------------------------------------
def test_deposit_reconcile_only_for_ck_and_gate_flips(svc, admin, customer, db):
    q = _accepted_quote(db, customer)
    d = svc.create(actor=admin, scope="all", payload=OrderCreate(source_type="bao_gia", quotation_id=q.id))
    # % cọc đặt TẠI ĐƠN (Kế toán), không còn ghim từ báo giá → 50% × 972.000 = 486.000.
    d = svc.update(order_id=d.id, actor=admin, scope="all", can_set_deposit_pct=True,
                   payload=OrderUpdate(deposit_pct=50))
    assert d.deposit_pct == 50 and d.deposit_required == 486_000
    d = svc.add_deposit(order_id=d.id, actor=admin, scope="all",
                        payload=OrderDepositIn(deposit_kind="ck", amount_received=300_000, reconciled=True))
    assert d.deposit_received == 300_000 and d.deposit_ok is False
    assert d.deposits[0].reconciled is True
    d = svc.add_deposit(order_id=d.id, actor=admin, scope="all",
                        payload=OrderDepositIn(deposit_kind="tien_mat", amount_received=200_000, reconciled=True))
    assert d.deposit_received == 500_000 and d.deposit_ok is True   # 500k ≥ 486k
    assert d.deposits[1].reconciled is False                        # tiền mặt: ép False


def test_deposit_pct_locked_from_sale(svc, admin, customer, db):
    """% cọc khóa khỏi Sale: chỉ quyền `record_deposit` (Kế toán) đặt được; ngoài khoảng 0–100 = 422."""
    q = _accepted_quote(db, customer)
    d = svc.create(actor=admin, scope="all", payload=OrderCreate(source_type="bao_gia", quotation_id=q.id))
    with pytest.raises(OrderForbidden):
        svc.update(order_id=d.id, actor=admin, scope="all", can_set_deposit_pct=False,
                   payload=OrderUpdate(deposit_pct=30))
    with pytest.raises(OrderValidationError):
        svc.update(order_id=d.id, actor=admin, scope="all", can_set_deposit_pct=True,
                   payload=OrderUpdate(deposit_pct=150))


# --- P3: duyệt đơn đặc thù ----------------------------------------------------
def test_submit_reject_then_approve(svc, admin, customer):
    d = svc.create(actor=admin, scope="all", payload=OrderCreate(
        source_type="nhap_tay", customer_id=customer.id,
        lines=[OrderLineIn(description="x", qty=1, unit_price=100, vat_pct=8)]))
    d = svc.submit_for_approval(order_id=d.id, actor=admin, scope="all")
    assert d.approval_state == "pending"
    d = svc.reject(order_id=d.id, actor=admin, scope="all", note="Giá thấp")
    assert d.approval_state == "rejected" and d.approvals[0].decision == "rejected"
    with pytest.raises(OrderValidationError):
        svc.reject(order_id=d.id, actor=admin, scope="all", note="")
    svc.submit_for_approval(order_id=d.id, actor=admin, scope="all")
    d = svc.approve(order_id=d.id, actor=admin, scope="all", note="OK")
    assert d.approval_state == "approved" and d.approvals[0].triggers_json == ["no_cost"]


def test_quote_order_does_not_need_approval(svc, admin, customer, db):
    q = _accepted_quote(db, customer)
    d = svc.create(actor=admin, scope="all", payload=OrderCreate(source_type="bao_gia", quotation_id=q.id))
    with pytest.raises(OrderValidationError):
        svc.submit_for_approval(order_id=d.id, actor=admin, scope="all")


# --- P4: cổng chốt + khóa báo giá ---------------------------------------------
def test_confirm_gate_blocks_then_locks_quote(svc, admin, customer, db):
    q = _accepted_quote(db, customer)
    d = svc.create(actor=admin, scope="all", payload=OrderCreate(source_type="bao_gia", quotation_id=q.id))
    assert d.can_confirm is False
    with pytest.raises(OrderValidationError):
        svc.confirm(order_id=d.id, actor=admin, scope="all")
    svc.add_deposit(order_id=d.id, actor=admin, scope="all",
                    payload=OrderDepositIn(deposit_kind="ck", amount_received=486_000, reconciled=True))
    svc.update(order_id=d.id, actor=admin, scope="all",
               payload=OrderUpdate(customer_po_no="PO1", delivery_committed_date=date.today()))
    d = svc.get(order_id=d.id, actor=admin, scope="all")
    assert d.can_confirm is True
    d = svc.confirm(order_id=d.id, actor=admin, scope="all")
    assert d.status == "ordered" and d.ordered_at is not None
    assert db.get(Quote, q.id).status == "converted_to_order"
    with pytest.raises(OrderValidationError):       # re-confirm chặn
        svc.confirm(order_id=d.id, actor=admin, scope="all")


# --- P5: hủy + seam -----------------------------------------------------------
def test_cancel_ordered_needs_permission_and_fault(svc, admin, customer, db):
    q = _accepted_quote(db, customer)
    d = svc.create(actor=admin, scope="all", payload=OrderCreate(source_type="bao_gia", quotation_id=q.id))
    svc.add_deposit(order_id=d.id, actor=admin, scope="all",
                    payload=OrderDepositIn(deposit_kind="ck", amount_received=486_000, reconciled=True))
    svc.update(order_id=d.id, actor=admin, scope="all",
               payload=OrderUpdate(customer_po_no="PO1", delivery_committed_date=date.today()))
    svc.confirm(order_id=d.id, actor=admin, scope="all")
    with pytest.raises(OrderForbidden):
        svc.cancel(order_id=d.id, actor=admin, scope="all", reason="x", fault=None, can_cancel_ordered=False)
    with pytest.raises(OrderValidationError):
        svc.cancel(order_id=d.id, actor=admin, scope="all", reason="Khách bỏ", fault=None, can_cancel_ordered=True)
    d = svc.cancel(order_id=d.id, actor=admin, scope="all", reason="Khách bỏ", fault="xuong", can_cancel_ordered=True)
    assert d.status == "cancelled" and d.cancel_fault == "xuong"
    assert len(d.deposits) >= 1  # cọc KHÔNG xóa khi hủy (hoàn/quyết toán ngoài hệ thống)


def test_manual_confirm_requires_consent_evidence(svc, admin, customer):
    d = svc.create(actor=admin, scope="all", payload=OrderCreate(
        source_type="nhap_tay", customer_id=customer.id,
        lines=[OrderLineIn(description="x", qty=1, unit_price=1000, vat_pct=8)]))
    svc.submit_for_approval(order_id=d.id, actor=admin, scope="all")
    svc.approve(order_id=d.id, actor=admin, scope="all", note="OK")
    svc.update(order_id=d.id, actor=admin, scope="all",
               payload=OrderUpdate(customer_po_no="PO1", delivery_committed_date=date.today()))
    d = svc.get(order_id=d.id, actor=admin, scope="all")
    assert d.can_confirm is False
    assert any("chứng cứ" in b.lower() for b in d.confirm_blockers)   # thiếu chứng cứ đồng ý
    d = svc.add_consent_attachment(order_id=d.id, actor=admin, scope="all",
        file_name="po.png", content_type="image/png", data=b"\x89PNG\r\n\x1a\n fake")
    assert len(d.consent_attachments) == 1
    assert d.can_confirm is True
    d = svc.confirm(order_id=d.id, actor=admin, scope="all")
    assert d.status == "ordered"


def test_deposit_attachment_upload(svc, admin, customer, db):
    q = _accepted_quote(db, customer)
    d = svc.create(actor=admin, scope="all", payload=OrderCreate(source_type="bao_gia", quotation_id=q.id))
    d = svc.add_deposit(order_id=d.id, actor=admin, scope="all",
                        payload=OrderDepositIn(deposit_kind="ck", amount_received=486_000, reconciled=True))
    did = d.deposits[0].id
    d = svc.add_deposit_attachment(order_id=d.id, deposit_id=did, actor=admin, scope="all",
        file_name="uy-nhiem-chi.pdf", content_type="application/pdf", data=b"%PDF-1.4 fake")
    assert len(d.deposits[0].attachments) == 1
    assert d.deposits[0].attachments[0].url.startswith("/static/don-hang-coc/")


def test_cancel_draft(svc, admin, customer):
    d = svc.create(actor=admin, scope="all", payload=OrderCreate(
        source_type="nhap_tay", customer_id=customer.id,
        lines=[OrderLineIn(description="x", qty=1, unit_price=100, vat_pct=8)]))
    d = svc.cancel(order_id=d.id, actor=admin, scope="all", reason="Đổi ý", fault=None, can_cancel_ordered=False)
    assert d.status == "cancelled"


# --- Người nhận hàng + lưu ý tách đích + ai/khi hủy (migration 0071) ----------
def test_delivery_contact_notes_and_cancel_actor(svc, admin, customer):
    d = svc.create(actor=admin, scope="all", payload=OrderCreate(
        source_type="nhap_tay", customer_id=customer.id,
        lines=[OrderLineIn(description="x", qty=1, unit_price=100, vat_pct=8)]))
    # Sale điền người nhận + 2 lưu ý tách đích khi nháp.
    d = svc.update(order_id=d.id, actor=admin, scope="all", payload=OrderUpdate(
        delivery_contact_name="Chị Kho", delivery_contact_phone="0900000001",
        delivery_note="Giao giờ hành chính, gọi trước 30 phút",
        production_note="In đúng màu mẫu lần trước",
    ))
    assert d.delivery_contact_name == "Chị Kho"
    assert d.delivery_contact_phone == "0900000001"
    assert "gọi trước" in d.delivery_note
    assert "màu mẫu" in d.production_note
    # Đọc lại từ detail (đi qua _detail build) — field không rớt.
    d2 = svc.get(order_id=d.id, actor=admin, scope="all")
    assert d2.production_note == "In đúng màu mẫu lần trước"
    # Hủy → ai/khi hủy đọc ra được (cột cancel_by/at đã ghi, nay expose).
    d3 = svc.cancel(order_id=d.id, actor=admin, scope="all", reason="Đổi ý", fault=None, can_cancel_ordered=False)
    assert d3.cancel_by_name == admin.name
    assert d3.cancel_at is not None
