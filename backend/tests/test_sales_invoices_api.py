"""Sales invoice is the only event that creates accounts receivable."""
from __future__ import annotations

from datetime import timedelta

from app.db import SessionLocal
# "Hôm nay" phải là ĐỒNG HỒ CỦA SERVER (`Asia/Bangkok`), không phải của runner.
#
# `_hom_nay()` đọc giờ máy chạy test; GitHub Actions chạy UTC. Trong khoảng 17–24h UTC (tức
# 0–7h giờ VN) hai đồng hồ lệch NGÀY, nên "ngày mai" mà test dựng lại đúng bằng "hôm nay" của
# server ⇒ ca "hoá đơn đề ngày tương lai phải bị chặn" nhận 201 thay vì 422. Đã đỏ CI thật
# 15/08/2026 21:28 UTC. Dùng chung seam với service thì hai bên không thể lệch, bất kể chạy giờ nào.
from app.services.accounting_service import _business_today as _hom_nay
from app.models.accounting import (
    PAYMENT_RECEIPT_RECEIVED,
    RECEIPT_SOURCE_ORDER,
    PaymentReceipt,
)
from app.models.customer import Customer
from app.models.order import Order, OrderLine, STATUS_ORDERED
from app.models.user import User


def _headers(client) -> dict[str, str]:
    response = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin123"}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _sales_order(
    *, total: int = 1_000_000, term_days: int | None = 30, suffix: str = "01"
) -> tuple[int, int]:
    db = SessionLocal()
    try:
        customer = Customer(
            code=f"KH-HD-{suffix}",
            name="Customer invoice test" if suffix == "01" else f"Customer invoice test {suffix}",
            payment_term_days=term_days,
            credit_limit=500_000,
        )
        db.add(customer)
        db.flush()
        order = Order(
            order_no=f"DH-HD-{suffix}",
            customer_id=customer.id,
            status=STATUS_ORDERED,
            ordered_at=None,
        )
        order.lines.append(
            OrderLine(
                description="Printed boxes",
                qty=100,
                don_vi_tinh="box",
                line_total=total,
                vat_pct_estimate=0,
            )
        )
        db.add(order)
        db.commit()
        return order.id, customer.id
    finally:
        db.close()


def _invoice_payload(order_id: int, *, number: str, amount: int | None = None) -> dict:
    payload = {
        "order_id": order_id,
        "invoice_symbol": "1C26TSV",
        "invoice_number": number,
        "invoice_date": _hom_nay().isoformat(),
    }
    if amount is not None:
        payload["amount_vnd"] = amount
    return payload


def _add_deposit(order_id: int, amount: int) -> None:
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == "admin").one()
        db.add(
            PaymentReceipt(
                code=f"PT-DEPOSIT-{order_id}-{amount}",
                source_type=RECEIPT_SOURCE_ORDER,
                order_id=order_id,
                order_no_snapshot="DH-HD-01",
                customer_name_snapshot="Customer invoice test",
                payer_name="Customer invoice test",
                receipt_method="cash",
                status=PAYMENT_RECEIPT_RECEIVED,
                receipt_date=_hom_nay(),
                amount=amount,
                amount_vnd=amount,
                currency="VND",
                exchange_rate=1,
                content="Order deposit",
                created_by_user_id=admin.id,
                received_by_user_id=admin.id,
            )
        )
        db.commit()
    finally:
        db.close()


def test_confirmed_order_does_not_create_receivable_until_invoice(client):
    headers = _headers(client)
    order_id, customer_id = _sales_order()

    before = client.get("/api/accounting/receivables", headers=headers)
    assert before.status_code == 200, before.text
    assert before.json()["total_due"] == 0
    assert all(row["customer_id"] != customer_id for row in before.json()["items"])

    created = client.post(
        "/api/accounting/sales-invoices",
        json=_invoice_payload(order_id, number="00000001", amount=400_000),
        headers=headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["remaining_amount"] == 400_000
    assert body["due_date"] == (_hom_nay() + timedelta(days=30)).isoformat()

    after = client.get("/api/accounting/receivables", headers=headers).json()
    customer = next(row for row in after["items"] if row["customer_id"] == customer_id)
    assert customer["invoice_count"] == 1
    assert customer["invoiced_amount"] == 400_000
    assert customer["total_due"] == 400_000


def test_cong_no_phai_thu_phan_trang_nhung_tong_tien_khong_doi(client):
    headers = _headers(client)
    order_a, customer_a = _sales_order(total=300_000, suffix="P1")
    order_b, customer_b = _sales_order(total=700_000, suffix="P2")
    assert client.post(
        "/api/accounting/sales-invoices",
        json=_invoice_payload(order_a, number="PAG-0001"),
        headers=headers,
    ).status_code == 201
    assert client.post(
        "/api/accounting/sales-invoices",
        json=_invoice_payload(order_b, number="PAG-0002"),
        headers=headers,
    ).status_code == 201

    trang_1 = client.get("/api/accounting/receivables?page=1&size=1", headers=headers)
    trang_2 = client.get("/api/accounting/receivables?page=2&size=1", headers=headers)
    assert trang_1.status_code == 200 and trang_2.status_code == 200
    mot, hai = trang_1.json(), trang_2.json()
    assert mot["total"] == 2 and mot["pages"] == 2
    assert mot["page"] == 1 and hai["page"] == 2
    assert mot["total_due"] == hai["total_due"] == 1_000_000
    assert {mot["items"][0]["customer_id"], hai["items"][0]["customer_id"]} == {
        customer_a,
        customer_b,
    }


def test_partial_invoices_are_capped_by_order_total(client):
    headers = _headers(client)
    order_id, _ = _sales_order()

    first = client.post(
        "/api/accounting/sales-invoices",
        json=_invoice_payload(order_id, number="00000002", amount=400_000),
        headers=headers,
    )
    assert first.status_code == 201, first.text
    second = client.post(
        "/api/accounting/sales-invoices",
        json=_invoice_payload(order_id, number="00000003"),
        headers=headers,
    )
    assert second.status_code == 201, second.text
    assert second.json()["amount_vnd"] == 600_000

    too_much = client.post(
        "/api/accounting/sales-invoices",
        json=_invoice_payload(order_id, number="00000004", amount=1),
        headers=headers,
    )
    assert too_much.status_code == 422, too_much.text


def test_deposit_offsets_issued_invoices_fifo_without_creating_early_debt(client):
    headers = _headers(client)
    order_id, customer_id = _sales_order()
    _add_deposit(order_id, 300_000)

    before = client.get(
        f"/api/accounting/receivables/{customer_id}", headers=headers
    ).json()
    assert before["total_due"] == 0

    first = client.post(
        "/api/accounting/sales-invoices",
        json=_invoice_payload(order_id, number="00000005", amount=200_000),
        headers=headers,
    )
    assert first.status_code == 201, first.text
    assert first.json()["deposit_offset_amount"] == 200_000
    assert first.json()["remaining_amount"] == 0

    second = client.post(
        "/api/accounting/sales-invoices",
        json=_invoice_payload(order_id, number="00000006", amount=300_000),
        headers=headers,
    )
    assert second.status_code == 201, second.text
    assert second.json()["deposit_offset_amount"] == 100_000
    assert second.json()["remaining_amount"] == 200_000


def test_invoice_receipt_reduces_debt_and_guards_cancellation(client):
    headers = _headers(client)
    order_id, customer_id = _sales_order()
    invoice = client.post(
        "/api/accounting/sales-invoices",
        json=_invoice_payload(order_id, number="00000007", amount=500_000),
        headers=headers,
    ).json()

    receipt = client.post(
        f"/api/accounting/sales-invoices/{invoice['id']}/receipts",
        json={
            "payer_name": "Customer invoice test",
            "receipt_method": "cash",
            "receipt_date": _hom_nay().isoformat(),
            "amount": 200_000,
            "content": "Partial invoice payment",
        },
        headers=headers,
    )
    assert receipt.status_code == 201, receipt.text
    assert receipt.json()["source_type"] == "sales_invoice"
    assert receipt.json()["status"] == "received"
    assert receipt.json()["sales_invoice_id"] == invoice["id"]

    detail = client.get(
        f"/api/accounting/receivables/{customer_id}", headers=headers
    ).json()
    assert detail["total_due"] == 300_000
    assert detail["items"][0]["direct_received_amount"] == 200_000

    overpay = client.post(
        f"/api/accounting/sales-invoices/{invoice['id']}/receipts",
        json={
            "payer_name": "Customer invoice test",
            "receipt_method": "cash",
            "receipt_date": _hom_nay().isoformat(),
            "amount": 300_001,
            "content": "Overpay",
        },
        headers=headers,
    )
    assert overpay.status_code == 422, overpay.text

    blocked = client.post(
        f"/api/accounting/sales-invoices/{invoice['id']}/cancel",
        json={"reason": "Incorrect invoice"},
        headers=headers,
    )
    assert blocked.status_code == 409, blocked.text

    cancelled_receipt = client.post(
        f"/api/accounting/payment-receipts/{receipt.json()['id']}/cancel",
        json={"reason": "Receipt entered twice"},
        headers=headers,
    )
    assert cancelled_receipt.status_code == 200, cancelled_receipt.text
    cancelled_invoice = client.post(
        f"/api/accounting/sales-invoices/{invoice['id']}/cancel",
        json={"reason": "Incorrect invoice"},
        headers=headers,
    )
    assert cancelled_invoice.status_code == 200, cancelled_invoice.text
    assert cancelled_invoice.json()["status"] == "cancelled"
    assert client.get(
        f"/api/accounting/receivables/{customer_id}", headers=headers
    ).json()["total_due"] == 0


def test_overdue_and_credit_limit_use_invoice_date_and_snapshot(client):
    headers = _headers(client)
    order_id, customer_id = _sales_order(term_days=1)
    payload = _invoice_payload(order_id, number="00000012")
    payload["invoice_date"] = (_hom_nay() - timedelta(days=3)).isoformat()
    created = client.post(
        "/api/accounting/sales-invoices", json=payload, headers=headers
    )
    assert created.status_code == 201, created.text

    summary = client.get("/api/accounting/receivables", headers=headers).json()
    row = next(item for item in summary["items"] if item["customer_id"] == customer_id)
    assert row["overdue_amount"] == 1_000_000
    assert row["vuot_han_muc"] is True
    assert row["vuot_bao_nhieu"] == 500_000


def test_invoice_without_payment_terms_is_due_but_not_overdue(client):
    headers = _headers(client)
    order_id, customer_id = _sales_order(term_days=None)
    created = client.post(
        "/api/accounting/sales-invoices",
        json=_invoice_payload(order_id, number="00000013"),
        headers=headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["due_date"] is None

    detail = client.get(
        f"/api/accounting/receivables/{customer_id}", headers=headers
    ).json()
    assert detail["items"][0]["chua_dat_han"] is True
    assert detail["items"][0]["overdue_days"] == 0
    assert detail["overdue_amount"] == 0


def test_invoice_validation_requires_traceable_identity_and_valid_date(client):
    headers = _headers(client)
    order_id, _ = _sales_order()

    missing_symbol = _invoice_payload(order_id, number="00000008")
    missing_symbol.pop("invoice_symbol")
    response = client.post(
        "/api/accounting/sales-invoices", json=missing_symbol, headers=headers
    )
    assert response.status_code == 422, response.text

    future = _invoice_payload(order_id, number="00000009")
    future["invoice_date"] = (_hom_nay() + timedelta(days=1)).isoformat()
    response = client.post(
        "/api/accounting/sales-invoices", json=future, headers=headers
    )
    assert response.status_code == 422, response.text


def test_order_with_issued_invoice_cannot_be_cancelled(client):
    headers = _headers(client)
    order_id, _ = _sales_order()
    created = client.post(
        "/api/accounting/sales-invoices",
        json=_invoice_payload(order_id, number="00000011"),
        headers=headers,
    )
    assert created.status_code == 201, created.text

    response = client.post(
        f"/api/orders/{order_id}/cancel",
        json={"reason": "Customer stopped order", "fault": "khach"},
        headers=headers,
    )
    assert response.status_code == 409, response.text

def test_man_khach_hang_va_man_cong_no_khong_duoc_lech(client):
    headers = _headers(client)
    order_id, customer_id = _sales_order()
    created = client.post(
        "/api/accounting/sales-invoices",
        json=_invoice_payload(order_id, number="00000010", amount=650_000),
        headers=headers,
    )
    assert created.status_code == 201, created.text

    ar = client.get(
        f"/api/accounting/receivables/{customer_id}", headers=headers
    )
    crm = client.get(f"/api/customers/{customer_id}", headers=headers)
    assert ar.status_code == 200, ar.text
    assert crm.status_code == 200, crm.text
    assert crm.json()["receivable"]["balance"] == ar.json()["total_due"] == 650_000
