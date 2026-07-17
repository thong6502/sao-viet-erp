"""Đơn hàng bán — service-level tests (redesign-don-hang-ban.md P1–P5).

Dựng DB in-memory + seed, rồi chạy OrderService end-to-end: 2 nguồn (báo giá/nhập tay),
snapshot NET sau chiết khấu, cọc đa hình thức, duyệt, cổng chốt + khóa báo giá, hủy + seam.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.db import Base, SessionLocal, engine
from app.db_migrations import run_migrations
from app.models.customer import Customer
from app.models.quotation import STATUS_ACCEPTED, Quote, QuoteItem, QuoteVersion
from app.models.user import User
from app.repositories.accounting_repo import AccountingRepository
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.document_sequence_repo import DocumentSequenceRepository
from app.repositories.order_repo import OrderRepository
from app.repositories.purchase_repo import PurchaseRequestRepository, SupplierRepository
from app.repositories.quotation_repo import QuotationRepository
from app.repositories.user_repo import UserRepository
from app.schemas.order import (
    OrderCreate,
    OrderDepositReceiptIn,
    OrderLineIn,
    OrderUpdate,
)
from app.seed import seed_all
from app.services.accounting_service import AccountingService
from app.services.order_service import (
    OrderConflict,
    OrderForbidden,
    OrderService,
    OrderValidationError,
)
from app.services.sequence_service import SequenceService


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
    audit = AuditLogRepository(db)
    accounting_repo = AccountingRepository(db)
    # V5: OrderService lập phiếu thu cọc qua AccountingService (chung Session).
    accounting = AccountingService(
        accounting_repo,
        PurchaseRequestRepository(db),
        SupplierRepository(db),
        UserRepository(db),
        audit,
        SequenceService(DocumentSequenceRepository(db)),
    )
    return OrderService(
        OrderRepository(db), audit, QuotationRepository(db), db, accounting_repo, accounting
    )


def _accepted_quote(db, customer, *, selling=1_000_000, discount=100_000, vat=8, qty=1000, cost=600_000):
    # Báo giá KHÔNG còn giữ % cọc (tích hợp accounting-wip) — % cọc đặt trên đơn khi tạo/ghi cọc.
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
    # % cọc đặt trên đơn (báo giá không còn giữ) — truyền qua payload khi tạo đơn.
    d = svc.create(actor=admin, scope="all", payload=OrderCreate(source_type="bao_gia", quotation_id=q.id, deposit_pct=50))
    assert d.cost_basis == "quote"
    assert d.needs_approval is False
    assert d.total == 900_000            # NET (1.000.000 − 100.000), KHÔNG phồng theo unit_price gộp
    assert d.total_with_vat == 972_000
    assert d.deposit_pct == 50
    assert d.deposit_required == 486_000
    assert d.margin_pct == 33            # (900k−600k)/900k


def test_one_quote_one_order_guard(svc, admin, customer, db):
    q = _accepted_quote(db, customer)
    svc.create(actor=admin, scope="all", payload=OrderCreate(source_type="bao_gia", quotation_id=q.id))
    with pytest.raises(OrderConflict):
        svc.create(actor=admin, scope="all", payload=OrderCreate(source_type="bao_gia", quotation_id=q.id))


# --- V5: cọc = PHIẾU THU THẬT (PaymentReceipt nguồn đơn) — cổng đủ cọc lật ----
def test_deposit_receipts_accumulate_and_gate_flips(svc, admin, customer, db):
    q = _accepted_quote(db, customer)
    d = svc.create(actor=admin, scope="all", payload=OrderCreate(source_type="bao_gia", quotation_id=q.id, deposit_pct=50))
    # Kế toán lập phiếu thu cọc = tạo thẳng 'received' → cộng vào cổng đủ cọc.
    d = svc.add_deposit_receipt(order_id=d.id, actor=admin, scope="all",
                                payload=OrderDepositReceiptIn(receipt_method="bank_transfer", amount=300_000))
    assert d.deposit_received == 300_000 and d.deposit_ok is False
    assert len(d.deposits) == 1
    assert d.deposits[0].status == "received" and d.deposits[0].amount == 300_000
    assert d.deposits[0].code.startswith("PT") and d.deposits[0].doc_no is not None
    d = svc.add_deposit_receipt(order_id=d.id, actor=admin, scope="all",
                                payload=OrderDepositReceiptIn(receipt_method="cash", amount=200_000))
    assert d.deposit_received == 500_000 and d.deposit_ok is True   # 500k ≥ 486k
    assert len(d.deposits) == 2


def test_deposit_receipt_rejects_bad_method_and_amount(svc, admin, customer, db):
    q = _accepted_quote(db, customer)
    d = svc.create(actor=admin, scope="all", payload=OrderCreate(source_type="bao_gia", quotation_id=q.id))
    with pytest.raises(OrderValidationError):   # hình thức thu không thuộc {cash, bank_transfer}
        svc.add_deposit_receipt(order_id=d.id, actor=admin, scope="all",
                                payload=OrderDepositReceiptIn(receipt_method="vang", amount=100_000))


def test_stats_money_aggregate_tracks_deposit_shortfall(svc, admin, customer, db):
    """KPI tiền: chờ cọc + Σ cần-thu-còn-thiếu bám phiếu thu THẬT (dùng delta vì seed có sẵn đơn)."""
    base = svc.stats(actor=admin, scope="all")
    q = _accepted_quote(db, customer)  # 50% của total_with_vat 972.000 → cần cọc 486.000
    d = svc.create(actor=admin, scope="all", payload=OrderCreate(source_type="bao_gia", quotation_id=q.id, deposit_pct=50))
    s = svc.stats(actor=admin, scope="all")
    assert s.awaiting_deposit == base.awaiting_deposit + 1
    assert s.deposit_shortfall == base.deposit_shortfall + 486_000
    assert s.ordered_value == base.ordered_value          # còn nháp → giá trị đã chốt không đổi

    d = svc.add_deposit_receipt(order_id=d.id, actor=admin, scope="all",
                                payload=OrderDepositReceiptIn(receipt_method="cash", amount=200_000))
    s = svc.stats(actor=admin, scope="all")
    assert s.awaiting_deposit == base.awaiting_deposit + 1  # thu 200k < 486k, vẫn chờ
    assert s.deposit_shortfall == base.deposit_shortfall + 286_000

    svc.add_deposit_receipt(order_id=d.id, actor=admin, scope="all",
                            payload=OrderDepositReceiptIn(receipt_method="bank_transfer", amount=286_000))
    s = svc.stats(actor=admin, scope="all")
    assert s.awaiting_deposit == base.awaiting_deposit     # đủ cọc → hết chờ
    assert s.deposit_shortfall == base.deposit_shortfall


def test_order_from_quote_pins_phieu_thanh_phan_id(svc, admin, customer, db):
    """Đơn TỪ BÁO GIÁ copy phieu_thanh_phan_id (pin truy vết ấn phẩm) từ dòng báo giá nguồn;
    đơn NHẬP TAY để None (không có ấn phẩm định giá)."""
    q = _accepted_quote(db, customer)
    item = db.query(QuoteItem).join(QuoteVersion).filter(QuoteVersion.quote_id == q.id).first()
    item.phieu_thanh_phan_id = 777   # dòng báo giá trỏ 1 "sản phẩm" của PTG
    db.commit()
    d = svc.create(actor=admin, scope="all", payload=OrderCreate(source_type="bao_gia", quotation_id=q.id))
    assert d.lines[0].phieu_thanh_phan_id == 777

    m = svc.create(actor=admin, scope="all", payload=OrderCreate(
        source_type="nhap_tay", customer_id=customer.id,
        lines=[OrderLineIn(description="Tờ rơi", qty=100, unit_price=1000, vat_pct=8)]))
    assert m.lines[0].phieu_thanh_phan_id is None


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
    svc.add_deposit_receipt(order_id=d.id, actor=admin, scope="all",
                    payload=OrderDepositReceiptIn(receipt_method="bank_transfer", amount=486_000))
    svc.update(order_id=d.id, actor=admin, scope="all",
               payload=OrderUpdate(customer_po_no="PO1", delivery_committed_date=date.today()))
    d = svc.get(order_id=d.id, actor=admin, scope="all")
    assert d.can_confirm is True
    d = svc.confirm(order_id=d.id, actor=admin, scope="all")
    assert d.status == "ordered" and d.ordered_at is not None
    assert db.get(Quote, q.id).status == "converted_to_order"
    with pytest.raises(OrderValidationError):       # re-confirm chặn
        svc.confirm(order_id=d.id, actor=admin, scope="all")


# --- Việc 4: gia hạn báo giá nguồn từ đơn (gỡ blocker "báo giá hết hạn") ------
def test_extend_source_quote_clears_expiry_blocker(svc, admin, customer, db):
    q = _accepted_quote(db, customer)
    d = svc.create(actor=admin, scope="all", payload=OrderCreate(source_type="bao_gia", quotation_id=q.id))
    q.valid_until = date.today() - timedelta(days=1)   # báo giá hết hạn SAU khi đã lập đơn
    db.commit()
    d = svc.get(order_id=d.id, actor=admin, scope="all")
    assert d.quote_expired is True
    assert any("hết hạn" in b.lower() for b in d.confirm_blockers)
    # gia hạn +30 ngày → CHỈ blocker hết-hạn biến mất, cờ tắt, quote.valid_until = hôm nay+30
    d = svc.extend_source_quote(order_id=d.id, actor=admin, scope="all")
    assert d.quote_expired is False
    assert not any("hết hạn" in b.lower() for b in d.confirm_blockers)
    assert db.get(Quote, q.id).valid_until == date.today() + timedelta(days=30)
    with pytest.raises(OrderValidationError):          # còn hạn rồi → gia hạn lần 2 bị chặn
        svc.extend_source_quote(order_id=d.id, actor=admin, scope="all")


def test_extend_source_quote_rejects_manual_order(svc, admin, customer):
    d = svc.create(actor=admin, scope="all", payload=OrderCreate(
        source_type="nhap_tay", customer_id=customer.id,
        lines=[OrderLineIn(description="x", qty=1, unit_price=1000, vat_pct=8)]))
    with pytest.raises(OrderValidationError):          # đơn nhập tay không gắn báo giá để gia hạn
        svc.extend_source_quote(order_id=d.id, actor=admin, scope="all")


# --- P5: hủy + seam -----------------------------------------------------------
def test_cancel_ordered_needs_permission_and_fault(svc, admin, customer, db):
    q = _accepted_quote(db, customer)
    d = svc.create(actor=admin, scope="all", payload=OrderCreate(source_type="bao_gia", quotation_id=q.id))
    svc.add_deposit_receipt(order_id=d.id, actor=admin, scope="all",
                    payload=OrderDepositReceiptIn(receipt_method="bank_transfer", amount=486_000))
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


# V5: minh chứng đã thu cọc chuyển sang PaymentReceiptAttachment (màn Phiếu thu Kế toán) — phủ ở
# test_accounting_api.py, không còn đính ở đơn.


def test_cancel_draft(svc, admin, customer):
    d = svc.create(actor=admin, scope="all", payload=OrderCreate(
        source_type="nhap_tay", customer_id=customer.id,
        lines=[OrderLineIn(description="x", qty=1, unit_price=100, vat_pct=8)]))
    d = svc.cancel(order_id=d.id, actor=admin, scope="all", reason="Đổi ý", fault=None, can_cancel_ordered=False)
    assert d.status == "cancelled"
