"""Cọc đơn bán = Phiếu thu 01-TT dùng chung quyển sổ PT (redesign-don-hang-ban.md đợt 2).

Khác test_orders_api (OrderService trần, cọc đọc order_deposits): ở đây inject AccountingService
→ nút "Tạo phiếu thu" sinh PT thật (source=order_deposit, dãy số chung), đơn đọc NGƯỢC Σ phiếu
thu ĐÃ THU để tính cọc + cổng chốt.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.db import Base, SessionLocal, engine
from app.db_migrations import run_migrations
from app.models.customer import Customer
from app.models.user import User
from app.repositories.accounting_repo import AccountingRepository
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.document_sequence_repo import DocumentSequenceRepository
from app.repositories.order_repo import OrderRepository
from app.repositories.purchase_repo import PurchaseRequestRepository, SupplierRepository
from app.repositories.quotation_repo import QuotationRepository
from app.repositories.user_repo import UserRepository
from app.schemas.order import OrderCreate, OrderLineIn, OrderReceiptIn, OrderUpdate
from app.seed import seed_all
from app.services.accounting_service import AccountingService
from app.services.order_service import OrderConflict, OrderService
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
    c = Customer(code="KH-R", name="KH Receipt")
    db.add(c)
    db.commit()
    return c


@pytest.fixture
def svc(db):
    acc = AccountingService(
        AccountingRepository(db), PurchaseRequestRepository(db), SupplierRepository(db),
        UserRepository(db), AuditLogRepository(db), SequenceService(DocumentSequenceRepository(db)),
    )
    return OrderService(OrderRepository(db), AuditLogRepository(db), QuotationRepository(db), db, acc)


def _draft_with_pct(svc, admin, customer, pct=30):
    d = svc.create(actor=admin, scope="all", payload=OrderCreate(
        source_type="nhap_tay", customer_id=customer.id,
        lines=[OrderLineIn(description="Tem", qty=10, unit_price=100_000, vat_pct=8)]))
    d = svc.update(order_id=d.id, actor=admin, scope="all", can_set_deposit_pct=True,
                   payload=OrderUpdate(deposit_pct=pct))
    return d


def _make_confirmable(svc, admin, customer, pct=30):
    """Đơn nhập tay đủ điều kiện chốt: cọc đủ (phiếu thu) + PO + ngày giao + duyệt + chứng cứ."""
    d = _draft_with_pct(svc, admin, customer, pct=pct)
    svc.create_deposit_receipt(order_id=d.id, actor=admin, scope="all",
        payload=OrderReceiptIn(receipt_method="cash", amount=d.deposit_required, receipt_date=date.today()))
    svc.update(order_id=d.id, actor=admin, scope="all",
               payload=OrderUpdate(customer_po_no="PO-1", delivery_committed_date=date.today()))
    svc.submit_for_approval(order_id=d.id, actor=admin, scope="all")
    svc.approve(order_id=d.id, actor=admin, scope="all", note="OK")
    svc.add_consent_attachment(order_id=d.id, actor=admin, scope="all",
        file_name="po.png", content_type="image/png", data=b"\x89PNG\r\n\x1a\n x")
    return svc.confirm(order_id=d.id, actor=admin, scope="all")


def test_receipt_flips_gate_and_uses_shared_pt_series(svc, admin, customer):
    d = _draft_with_pct(svc, admin, customer, pct=30)
    assert d.deposit_required == 324_000 and d.deposit_received == 0 and d.deposit_ok is False
    d = svc.create_deposit_receipt(order_id=d.id, actor=admin, scope="all",
        payload=OrderReceiptIn(receipt_method="cash", amount=324_000, receipt_date=date.today()))
    # Cọc đọc NGƯỢC Σ phiếu thu → gate bật.
    assert d.deposit_received == 324_000 and d.deposit_ok is True
    assert len(d.receipts) == 1
    r = d.receipts[0]
    assert r.status == "received" and r.amount == 324_000
    assert r.doc_no and r.doc_no.startswith("PT")        # dãy số 01-TT chung
    assert r.credit_account == "131"                     # Có 131 (phải thu khách)


def test_cancelled_receipt_not_counted(svc, admin, customer):
    d = _draft_with_pct(svc, admin, customer, pct=30)
    d = svc.create_deposit_receipt(order_id=d.id, actor=admin, scope="all",
        payload=OrderReceiptIn(receipt_method="bank_transfer", amount=324_000,
                               receipt_date=date.today(), bank_reference="FT123"))
    rid = d.receipts[0].id
    assert d.deposit_ok is True
    d = svc.cancel_deposit_receipt(order_id=d.id, receipt_id=rid, actor=admin, scope="all", reason="ghi nhầm")
    # Hủy phiếu → không tính vào cọc nữa.
    assert d.deposit_received == 0 and d.deposit_ok is False
    assert d.receipts[0].status == "cancelled"


def test_receipt_locked_after_confirm(svc, admin, customer):
    d = _make_confirmable(svc, admin, customer)
    assert d.status == "ordered"
    with pytest.raises(OrderConflict):
        svc.create_deposit_receipt(order_id=d.id, actor=admin, scope="all",
            payload=OrderReceiptIn(receipt_method="cash", amount=1000, receipt_date=date.today()))


def test_edit_logistics_after_confirm_but_not_commercial(svc, admin, customer):
    d = _make_confirmable(svc, admin, customer)
    # Sau chốt: sửa được hậu cần (địa chỉ, gấp).
    d = svc.update(order_id=d.id, actor=admin, scope="all",
                   payload=OrderUpdate(delivery_address="Kho mới", is_rush=True))
    assert d.delivery_address == "Kho mới" and d.is_rush is True
    # Nhưng KHÔNG sửa được nhóm thương mại.
    with pytest.raises(OrderConflict):
        svc.update(order_id=d.id, actor=admin, scope="all", payload=OrderUpdate(order_nature="gia_cong"))
