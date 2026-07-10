"""Accounting purchase inbox, Phiếu chi and UNC integration tests."""
from __future__ import annotations

import re

from app.db import SessionLocal
from app.models.role import SCOPE_ALL
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password


def _headers(client) -> dict[str, str]:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _supplier(client, headers) -> dict:
    response = client.post(
        "/api/suppliers",
        json={
            "name": "Công ty Giấy Kế Toán",
            "tax_code": "0108888888",
            "phone": "0901888888",
            "email": "accounting-supplier@example.com",
            "address": "18 Nguyễn Trãi, Hà Nội",
            "contact_name": "Nguyễn Lan",
            "supplier_group": "paper",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _purchase(client, headers, supplier_id: int) -> tuple[dict, dict]:
    source = client.post(
        "/api/department-purchase-requests",
        json={
            "source_type": "kinh_doanh",
            "purpose": "Mua giấy cho đơn in",
            "needed_date": "2026-07-20",
            "lines": [{"item_name": "Giấy Duplex", "unit": "tờ", "quantity": 1000}],
        },
        headers=headers,
    )
    assert source.status_code == 201, source.text
    source_body = source.json()
    purchase = client.post(
        "/api/purchase-requests",
        json={
            "supplier_id": supplier_id,
            "source_request_ids": [source_body["id"]],
            "purpose": "Mua giấy cho đơn in",
            "needed_date": "2026-07-20",
            "lines": [
                {
                    "item_name": "Giấy Duplex",
                    "unit": "tờ",
                    "quantity": 1000,
                    "expected_unit_price": 2200,
                    "discount_percent": 0,
                    "vat_percent": 0,
                }
            ],
        },
        headers=headers,
    )
    assert purchase.status_code == 201, purchase.text
    body = purchase.json()
    submitted = client.post(f"/api/purchase-requests/{body['id']}/submit", headers=headers)
    assert submitted.status_code == 200, submitted.text
    return submitted.json(), source_body


def _cash_payload(amount: int) -> dict:
    return {
        "voucher_type": "cash",
        "payment_stage": "advance",
        "voucher_date": "2026-07-10",
        "planned_payment_date": "2026-07-11",
        "amount": amount,
        "currency": "VND",
        "exchange_rate": 1,
        "content": "Tạm ứng mua giấy",
        "cash_recipient_name": "Nguyễn Lan",
        "cash_recipient_address": "18 Nguyễn Trãi, Hà Nội",
    }


def _bank_accounts(client, headers, supplier_id: int) -> tuple[dict, dict]:
    company = client.post(
        "/api/accounting/company-bank-accounts",
        json={
            "account_holder": "CÔNG TY SAO VIỆT NHẬT",
            "account_number": "123456789",
            "bank_name": "Vietcombank",
            "bank_branch": "Hà Nội",
            "currency": "VND",
            "is_default": True,
        },
        headers=headers,
    )
    assert company.status_code == 201, company.text
    beneficiary = client.post(
        "/api/accounting/supplier-bank-accounts",
        json={
            "supplier_id": supplier_id,
            "account_holder": "CÔNG TY GIẤY KẾ TOÁN",
            "account_number": "987654321",
            "bank_name": "BIDV",
            "bank_branch": "Hà Nội",
            "currency": "VND",
            "is_default": True,
        },
        headers=headers,
    )
    assert beneficiary.status_code == 201, beneficiary.text
    return company.json(), beneficiary.json()


def test_approve_and_create_cash_voucher_tracks_partial_payment(client):
    headers = _headers(client)
    supplier = _supplier(client, headers)
    purchase, source = _purchase(client, headers, supplier["id"])

    created = client.post(
        f"/api/accounting/purchase-requests/{purchase['id']}/approve-and-create-voucher",
        json=_cash_payload(1_000_000),
        headers=headers,
    )
    assert created.status_code == 201, created.text
    voucher = created.json()
    assert re.fullmatch(r"PC-\d{6}-[A-Z0-9]{4}", voucher["code"])
    assert voucher["status"] == "waiting_payment"
    assert voucher["amount_vnd"] == 1_000_000
    assert voucher["purchase_request_code"] == purchase["code"]
    assert voucher["source_request_codes"] == [source["code"]]

    refreshed = client.get(f"/api/purchase-requests/{purchase['id']}", headers=headers).json()
    assert refreshed["status"] == "approved"
    assert refreshed["pending_amount"] == 1_000_000
    assert refreshed["paid_amount"] == 0
    assert refreshed["available_amount"] == 1_200_000
    assert refreshed["payment_status"] == "partial"

    paid = client.post(
        f"/api/accounting/payment-vouchers/{voucher['id']}/mark-paid",
        json={"bank_reference": None},
        headers=headers,
    )
    assert paid.status_code == 200, paid.text
    assert paid.json()["status"] == "paid"
    refreshed = client.get(f"/api/purchase-requests/{purchase['id']}", headers=headers).json()
    assert refreshed["pending_amount"] == 0
    assert refreshed["paid_amount"] == 1_000_000
    assert refreshed["outstanding_amount"] == 1_200_000

    found = client.get(f"/api/accounting/payment-vouchers?q={source['code']}", headers=headers)
    assert found.status_code == 200
    assert found.json()["total"] == 1


def test_unc_requires_bank_accounts_reference_and_blocks_overpayment(client):
    headers = _headers(client)
    supplier = _supplier(client, headers)
    purchase, _ = _purchase(client, headers, supplier["id"])
    assert client.post(f"/api/purchase-requests/{purchase['id']}/approve", headers=headers).status_code == 200
    company, beneficiary = _bank_accounts(client, headers, supplier["id"])

    payload = {
        "purchase_request_id": purchase["id"],
        "voucher_type": "bank_transfer",
        "payment_stage": "advance",
        "voucher_date": "2026-07-10",
        "amount": 1_500_000,
        "currency": "VND",
        "exchange_rate": 1,
        "content": "Chuyển khoản mua giấy",
        "company_bank_account_id": company["id"],
        "supplier_bank_account_id": beneficiary["id"],
        "bank_fee_bearer": "payer",
    }
    created = client.post("/api/accounting/payment-vouchers", json=payload, headers=headers)
    assert created.status_code == 201, created.text
    voucher = created.json()
    assert re.fullmatch(r"UNC-\d{6}-[A-Z0-9]{4}", voucher["code"])
    assert voucher["company_account_number"] == "123456789"
    assert voucher["beneficiary_account_number"] == "987654321"

    missing_reference = client.post(
        f"/api/accounting/payment-vouchers/{voucher['id']}/mark-paid",
        json={"bank_reference": None},
        headers=headers,
    )
    assert missing_reference.status_code == 422
    paid = client.post(
        f"/api/accounting/payment-vouchers/{voucher['id']}/mark-paid",
        json={"bank_reference": "VCB-20260710-001"},
        headers=headers,
    )
    assert paid.status_code == 200, paid.text

    too_much = {**payload, "amount": 700_001}
    over = client.post("/api/accounting/payment-vouchers", json=too_much, headers=headers)
    assert over.status_code == 422
    assert "vượt quá" in over.json()["detail"]


def test_final_payment_requires_received_purchase(client):
    headers = _headers(client)
    supplier = _supplier(client, headers)
    purchase, _ = _purchase(client, headers, supplier["id"])
    assert client.post(f"/api/purchase-requests/{purchase['id']}/approve", headers=headers).status_code == 200
    payload = {
        "purchase_request_id": purchase["id"],
        **_cash_payload(2_200_000),
        "payment_stage": "final",
    }
    blocked = client.post("/api/accounting/payment-vouchers", json=payload, headers=headers)
    assert blocked.status_code == 409
    assert client.post(f"/api/purchase-requests/{purchase['id']}/mark-purchased", headers=headers).status_code == 200
    assert client.post(f"/api/purchase-requests/{purchase['id']}/mark-received", headers=headers).status_code == 200
    created = client.post("/api/accounting/payment-vouchers", json=payload, headers=headers)
    assert created.status_code == 201, created.text


def test_foreign_currency_reserves_vnd_and_blocks_purchase_cancellation(client):
    headers = _headers(client)
    supplier = _supplier(client, headers)
    purchase, _ = _purchase(client, headers, supplier["id"])
    assert client.post(f"/api/purchase-requests/{purchase['id']}/approve", headers=headers).status_code == 200

    payload = {
        "purchase_request_id": purchase["id"],
        **_cash_payload(100),
        "currency": "USD",
        "exchange_rate": 20_000,
    }
    created = client.post("/api/accounting/payment-vouchers", json=payload, headers=headers)
    assert created.status_code == 201, created.text
    voucher = created.json()
    assert voucher["amount"] == 100
    assert voucher["amount_vnd"] == 2_000_000

    refreshed = client.get(f"/api/purchase-requests/{purchase['id']}", headers=headers).json()
    assert refreshed["pending_amount"] == 2_000_000
    assert refreshed["available_amount"] == 200_000

    blocked = client.post(
        f"/api/purchase-requests/{purchase['id']}/cancel",
        json={"reason": "Không mua nữa"},
        headers=headers,
    )
    assert blocked.status_code == 409
    assert "chứng từ thanh toán" in blocked.json()["detail"]

    cancelled_voucher = client.post(
        f"/api/accounting/payment-vouchers/{voucher['id']}/cancel",
        json={"reason": "Lập nhầm tỷ giá"},
        headers=headers,
    )
    assert cancelled_voucher.status_code == 200, cancelled_voucher.text
    cancelled_purchase = client.post(
        f"/api/purchase-requests/{purchase['id']}/cancel",
        json={"reason": "Không mua nữa"},
        headers=headers,
    )
    assert cancelled_purchase.status_code == 200, cancelled_purchase.text


def _accounting_user_token(*, approve: bool, manage_status: bool = False) -> str:
    db = SessionLocal()
    try:
        departments = DepartmentRepository(db)
        department = departments.get_by_name("Kế toán")
        roles = RoleRepository(db)
        role = roles.create(
            name="Kế toán duyệt" if approve else "Kế toán chỉ xem",
            department_id=department.id,
        )
        roles.set_permission(
            role_id=role.id,
            module_key="ke_toan",
            can_read=True,
            can_approve=approve,
            can_manage_status=manage_status,
            scope=SCOPE_ALL,
        )
        users = UserRepository(db)
        user = users.create(
            username="accounting-approver" if approve else "accounting-reader",
            name="Kế toán duyệt" if approve else "Kế toán xem",
            password_hash=hash_password("x"),
        )
        users.set_assignment(
            user, department_id=department.id, role_id=role.id, is_active=True
        )
        return create_access_token(str(user.id))
    finally:
        db.close()


def test_accounting_approve_permission_also_allows_voucher_creation(client):
    admin_headers = _headers(client)
    supplier = _supplier(client, admin_headers)
    purchase, _ = _purchase(client, admin_headers, supplier["id"])
    reader_headers = {"Authorization": f"Bearer {_accounting_user_token(approve=False)}"}
    approver_headers = {"Authorization": f"Bearer {_accounting_user_token(approve=True)}"}

    assert client.get("/api/accounting/inbox", headers=reader_headers).status_code == 200
    assert (
        client.post(
            f"/api/accounting/purchase-requests/{purchase['id']}/approve-and-create-voucher",
            json=_cash_payload(500_000),
            headers=reader_headers,
        ).status_code
        == 403
    )
    allowed = client.post(
        f"/api/accounting/purchase-requests/{purchase['id']}/approve-and-create-voucher",
        json=_cash_payload(500_000),
        headers=approver_headers,
    )
    assert allowed.status_code == 201, allowed.text
    assert allowed.json()["created_by_name"] == "Kế toán duyệt"
    assert (
        client.post(
            f"/api/accounting/payment-vouchers/{allowed.json()['id']}/mark-paid",
            json={"bank_reference": None},
            headers=approver_headers,
        ).status_code
        == 403
    )
