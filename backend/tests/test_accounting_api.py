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
    assert voucher["purchase_created_by_name"] == "Admin"
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
    body = found.json()
    assert body["total"] == 1
    # Tổng API-level: cộng trên toàn bộ kết quả khớp bộ lọc, không phải trang hiện tại.
    assert body["total_paid_amount"] == 1_000_000
    assert body["total_waiting_amount"] == 0
    assert body["total_receipt_received_amount"] == 0
    # Dải nhóm PMH: "Đã chi" của cả PMH nằm trên từng phiếu chi.
    assert body["items"][0]["purchase_paid_amount"] == 1_000_000


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


def test_final_payment_allowed_before_received_purchase(client):
    headers = _headers(client)
    supplier = _supplier(client, headers)
    purchase, _ = _purchase(client, headers, supplier["id"])
    assert client.post(f"/api/purchase-requests/{purchase['id']}/approve", headers=headers).status_code == 200
    payload = {
        "purchase_request_id": purchase["id"],
        **_cash_payload(2_200_000),
        "payment_stage": "final",
    }
    created = client.post("/api/accounting/payment-vouchers", json=payload, headers=headers)
    assert created.status_code == 201, created.text
    assert created.json()["payment_stage"] == "final"


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


def test_doc_no_shared_counter_across_voucher_types(client):
    """Số IN trên mẫu: PC00001, PC00002… — tiền mặt và UNC dùng CHUNG một bộ đếm
    (cùng quyển phiếu chi), trong khi mã nội bộ vẫn PC-…/UNC-…"""
    headers = _headers(client)
    supplier = _supplier(client, headers)
    purchase, _ = _purchase(client, headers, supplier["id"])
    company, beneficiary = _bank_accounts(client, headers, supplier["id"])

    cash = client.post(
        f"/api/accounting/purchase-requests/{purchase['id']}/approve-and-create-voucher",
        json=_cash_payload(500_000),
        headers=headers,
    )
    assert cash.status_code == 201, cash.text
    assert cash.json()["doc_no"] == "PC00001"
    assert cash.json()["code"].startswith("PC-")

    bank = client.post(
        "/api/accounting/payment-vouchers",
        json={
            "purchase_request_id": purchase["id"],
            "voucher_type": "bank_transfer",
            "payment_stage": "partial",
            "voucher_date": "2026-07-10",
            "amount": 400_000,
            "currency": "VND",
            "exchange_rate": 1,
            "content": "Chuyển khoản đợt 2",
            "company_bank_account_id": company["id"],
            "supplier_bank_account_id": beneficiary["id"],
            "bank_fee_bearer": "payer",
        },
        headers=headers,
    )
    assert bank.status_code == 201, bank.text
    # Chung bộ đếm → PC00002 dù mã nội bộ là UNC-…
    assert bank.json()["doc_no"] == "PC00002"
    assert bank.json()["code"].startswith("UNC-")


def test_receipt_doc_no_has_own_counter(client):
    headers = _headers(client)
    supplier = _supplier(client, headers)
    purchase, _ = _purchase(client, headers, supplier["id"])
    voucher = _paid_cash_voucher(client, headers, purchase["id"], 2_200_000)
    assert voucher["doc_no"] == "PC00001"

    receipt = client.post(
        f"/api/accounting/payment-vouchers/{voucher['id']}/receipts",
        json=_receipt_payload(300_000),
        headers=headers,
    )
    assert receipt.status_code == 201, receipt.text
    assert receipt.json()["doc_no"] == "PT00001"  # bộ đếm riêng, không nối tiếp PC


def test_approve_and_create_voucher_failure_leaves_purchase_pending(client, monkeypatch):
    """Khóa hazard: cấp số (tự commit) phải xảy ra TRƯỚC khi đổi trạng thái PMH —
    nếu lưu phiếu lỗi thì PMH không được kẹt ở 'đã duyệt' mà không có phiếu chi."""
    from app.repositories.accounting_repo import AccountingRepository

    headers = _headers(client)
    supplier = _supplier(client, headers)
    purchase, _ = _purchase(client, headers, supplier["id"])

    def boom(self, voucher):
        raise RuntimeError("DB nổ giữa chừng")

    monkeypatch.setattr(AccountingRepository, "save_voucher", boom)
    try:
        client.post(
            f"/api/accounting/purchase-requests/{purchase['id']}/approve-and-create-voucher",
            json=_cash_payload(500_000),
            headers=headers,
        )
    except RuntimeError:
        pass  # TestClient dội lỗi ra — đúng kỳ vọng
    monkeypatch.undo()

    refreshed = client.get(f"/api/purchase-requests/{purchase['id']}", headers=headers)
    assert refreshed.json()["status"] == "pending_approval"  # KHÔNG bị duyệt oan


def test_search_by_doc_no_and_debit_credit_roundtrip(client):
    headers = _headers(client)
    supplier = _supplier(client, headers)
    purchase, _ = _purchase(client, headers, supplier["id"])
    created = client.post(
        f"/api/accounting/purchase-requests/{purchase['id']}/approve-and-create-voucher",
        json={**_cash_payload(500_000), "debit_account": "242, 1331", "credit_account": "1111"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    voucher = created.json()
    assert voucher["debit_account"] == "242, 1331"
    assert voucher["credit_account"] == "1111"

    # Tra cứu theo số in trên phiếu (kể cả gõ chữ thường).
    for term in (voucher["doc_no"], voucher["doc_no"].lower()):
        found = client.get(f"/api/accounting/payment-vouchers?q={term}", headers=headers)
        assert found.status_code == 200
        assert [row["id"] for row in found.json()["items"]] == [voucher["id"]]

    # Sửa phiếu: đổi được định khoản, GIỮ NGUYÊN số phiếu.
    updated = client.put(
        f"/api/accounting/payment-vouchers/{voucher['id']}",
        json={
            "purchase_request_id": purchase["id"],
            **_cash_payload(500_000),
            "debit_account": "156",
            "credit_account": "1111",
        },
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["doc_no"] == voucher["doc_no"]
    assert updated.json()["debit_account"] == "156"


def test_voucher_accepts_payload_without_accounts_and_rejects_too_long(client):
    headers = _headers(client)
    supplier = _supplier(client, headers)
    purchase, _ = _purchase(client, headers, supplier["id"])

    # Payload cũ (không có debit/credit) vẫn phải chạy.
    ok = client.post(
        f"/api/accounting/purchase-requests/{purchase['id']}/approve-and-create-voucher",
        json=_cash_payload(500_000),
        headers=headers,
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["debit_account"] is None

    too_long = client.post(
        "/api/accounting/payment-vouchers",
        json={
            "purchase_request_id": purchase["id"],
            **_cash_payload(100_000),
            "debit_account": "x" * 65,
        },
        headers=headers,
    )
    assert too_long.status_code == 422


def test_receipt_payer_address_and_accounts_roundtrip(client):
    headers = _headers(client)
    supplier = _supplier(client, headers)
    purchase, _ = _purchase(client, headers, supplier["id"])
    voucher = _paid_cash_voucher(client, headers, purchase["id"], 2_200_000)

    created = client.post(
        f"/api/accounting/payment-vouchers/{voucher['id']}/receipts",
        json={
            **_receipt_payload(300_000),
            "payer_address": "36/30/27 Bùi Tư Toàn, Phường An Lạc, TP Hồ Chí Minh",
            "debit_account": "1111",
            "credit_account": "141",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["payer_address"].startswith("36/30/27 Bùi Tư Toàn")
    assert body["debit_account"] == "1111"
    assert body["credit_account"] == "141"

    # Payload không có 3 trường mới vẫn hợp lệ.
    plain = client.post(
        f"/api/accounting/payment-vouchers/{voucher['id']}/receipts",
        json=_receipt_payload(100_000),
        headers=headers,
    )
    assert plain.status_code == 201, plain.text
    assert plain.json()["payer_address"] is None


def test_cancelled_voucher_keeps_doc_no(client):
    headers = _headers(client)
    supplier = _supplier(client, headers)
    purchase, _ = _purchase(client, headers, supplier["id"])
    created = client.post(
        f"/api/accounting/purchase-requests/{purchase['id']}/approve-and-create-voucher",
        json=_cash_payload(500_000),
        headers=headers,
    ).json()
    cancelled = client.post(
        f"/api/accounting/payment-vouchers/{created['id']}/cancel",
        json={"reason": "Lập nhầm"},
        headers=headers,
    )
    assert cancelled.status_code == 200
    # Phiếu hủy vẫn giữ số trong quyển (chuẩn kế toán VN).
    assert cancelled.json()["doc_no"] == created["doc_no"]


def _receipt_payload(amount: int, **overrides) -> dict:
    payload = {
        "payer_name": "Nguyễn Văn Mua",
        "receipt_method": "cash",
        "receipt_date": "2026-07-13",
        "amount": amount,
        "content": "Thu hồi tiền thừa mua giấy",
    }
    payload.update(overrides)
    return payload


def _paid_cash_voucher(client, headers, purchase_id: int, amount: int) -> dict:
    created = client.post(
        f"/api/accounting/purchase-requests/{purchase_id}/approve-and-create-voucher",
        json=_cash_payload(amount),
        headers=headers,
    )
    assert created.status_code == 201, created.text
    voucher = created.json()
    paid = client.post(
        f"/api/accounting/payment-vouchers/{voucher['id']}/mark-paid",
        json={"bank_reference": None},
        headers=headers,
    )
    assert paid.status_code == 200, paid.text
    return paid.json()


def test_receipt_requires_paid_voucher(client):
    headers = _headers(client)
    supplier = _supplier(client, headers)
    purchase, _ = _purchase(client, headers, supplier["id"])
    waiting = client.post(
        f"/api/accounting/purchase-requests/{purchase['id']}/approve-and-create-voucher",
        json=_cash_payload(1_000_000),
        headers=headers,
    )
    assert waiting.status_code == 201, waiting.text
    blocked = client.post(
        f"/api/accounting/payment-vouchers/{waiting.json()['id']}/receipts",
        json=_receipt_payload(100_000),
        headers=headers,
    )
    assert blocked.status_code == 409
    assert "đã chi" in blocked.json()["detail"]


def test_receipt_cannot_exceed_voucher_amount(client):
    headers = _headers(client)
    supplier = _supplier(client, headers)
    purchase, _ = _purchase(client, headers, supplier["id"])
    voucher = _paid_cash_voucher(client, headers, purchase["id"], 2_200_000)

    over = client.post(
        f"/api/accounting/payment-vouchers/{voucher['id']}/receipts",
        json=_receipt_payload(2_300_000),
        headers=headers,
    )
    assert over.status_code == 422
    assert "vượt quá" in over.json()["detail"]

    first = client.post(
        f"/api/accounting/payment-vouchers/{voucher['id']}/receipts",
        json=_receipt_payload(300_000),
        headers=headers,
    )
    assert first.status_code == 201, first.text
    receipt = first.json()
    assert receipt["code"].startswith("PT-")
    assert receipt["status"] == "waiting_receipt"
    assert receipt["payment_voucher_code"] == voucher["code"]
    assert receipt["payer_name"] == "Nguyễn Văn Mua"

    # Phiếu thu đang chờ vẫn chiếm chỗ trong hạn mức thu.
    second_over = client.post(
        f"/api/accounting/payment-vouchers/{voucher['id']}/receipts",
        json=_receipt_payload(2_000_000),
        headers=headers,
    )
    assert second_over.status_code == 422

    # Update chính phiếu đó lên full số đã chi được (exclude self).
    full = client.put(
        f"/api/accounting/payment-receipts/{receipt['id']}",
        json=_receipt_payload(2_200_000),
        headers=headers,
    )
    assert full.status_code == 200, full.text
    assert full.json()["amount_vnd"] == 2_200_000


def test_receipt_received_reopens_purchase_available(client):
    headers = _headers(client)
    supplier = _supplier(client, headers)
    purchase, _ = _purchase(client, headers, supplier["id"])
    voucher = _paid_cash_voucher(client, headers, purchase["id"], 2_200_000)

    before = client.get(f"/api/purchase-requests/{purchase['id']}", headers=headers).json()
    assert before["payment_status"] == "paid"
    assert before["available_amount"] == 0

    receipt = client.post(
        f"/api/accounting/payment-vouchers/{voucher['id']}/receipts",
        json=_receipt_payload(300_000),
        headers=headers,
    ).json()

    waiting_state = client.get(f"/api/purchase-requests/{purchase['id']}", headers=headers).json()
    assert waiting_state["available_amount"] == 0  # chờ thu: tiền chưa về
    assert waiting_state["receipt_received_amount"] == 0

    received = client.post(
        f"/api/accounting/payment-receipts/{receipt['id']}/mark-received",
        json={"bank_reference": None},
        headers=headers,
    )
    assert received.status_code == 200, received.text
    assert received.json()["status"] == "received"

    after = client.get(f"/api/purchase-requests/{purchase['id']}", headers=headers).json()
    assert after["paid_amount"] == 2_200_000  # số thô giữ nguyên
    assert after["receipt_received_amount"] == 300_000
    assert after["available_amount"] == 300_000
    assert after["outstanding_amount"] == 300_000
    assert after["payment_status"] == "partial"

    voucher_after = client.get(
        f"/api/accounting/payment-vouchers/{voucher['id']}", headers=headers
    ).json()
    assert voucher_after["receipt_received_amount"] == 300_000
    assert voucher_after["receipt_pending_amount"] == 0

    listed = client.get(
        f"/api/accounting/payment-vouchers?q={voucher['code']}", headers=headers
    ).json()
    assert listed["total_paid_amount"] == 2_200_000
    assert listed["total_receipt_received_amount"] == 300_000

    # Phần được cộng lại cho phép chi bổ sung đúng 300k, thêm 1đ thì chặn.
    topup = client.post(
        "/api/accounting/payment-vouchers",
        json={"purchase_request_id": purchase["id"], **_cash_payload(300_000)},
        headers=headers,
    )
    assert topup.status_code == 201, topup.text
    over = client.post(
        "/api/accounting/payment-vouchers",
        json={"purchase_request_id": purchase["id"], **_cash_payload(1)},
        headers=headers,
    )
    assert over.status_code == 422


def test_receipt_payer_and_method_validation(client):
    headers = _headers(client)
    supplier = _supplier(client, headers)
    purchase, _ = _purchase(client, headers, supplier["id"])
    voucher = _paid_cash_voucher(client, headers, purchase["id"], 2_200_000)
    receipts_url = f"/api/accounting/payment-vouchers/{voucher['id']}/receipts"

    missing_payer = client.post(
        receipts_url, json=_receipt_payload(100_000, payer_name=" "), headers=headers
    )
    assert missing_payer.status_code == 422

    bank_missing_account = client.post(
        receipts_url,
        json=_receipt_payload(100_000, receipt_method="bank_transfer"),
        headers=headers,
    )
    assert bank_missing_account.status_code == 422

    company, _beneficiary = _bank_accounts(client, headers, supplier["id"])
    bank_ok = client.post(
        receipts_url,
        json=_receipt_payload(
            100_000, receipt_method="bank_transfer", company_bank_account_id=company["id"]
        ),
        headers=headers,
    )
    assert bank_ok.status_code == 201, bank_ok.text
    body = bank_ok.json()
    assert body["company_account_number"] == "123456789"

    missing_reference = client.post(
        f"/api/accounting/payment-receipts/{body['id']}/mark-received",
        json={"bank_reference": None},
        headers=headers,
    )
    assert missing_reference.status_code == 422
    received = client.post(
        f"/api/accounting/payment-receipts/{body['id']}/mark-received",
        json={"bank_reference": "VCB-BAOCO-001"},
        headers=headers,
    )
    assert received.status_code == 200, received.text
    assert received.json()["bank_reference"] == "VCB-BAOCO-001"


def test_receipt_update_cancel_lifecycle_and_listing(client):
    headers = _headers(client)
    supplier = _supplier(client, headers)
    purchase, _ = _purchase(client, headers, supplier["id"])
    voucher = _paid_cash_voucher(client, headers, purchase["id"], 2_200_000)
    receipts_url = f"/api/accounting/payment-vouchers/{voucher['id']}/receipts"

    receipt = client.post(receipts_url, json=_receipt_payload(500_000), headers=headers).json()
    updated = client.put(
        f"/api/accounting/payment-receipts/{receipt['id']}",
        json=_receipt_payload(700_000, payer_name="Trần Thị Nộp"),
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["amount_vnd"] == 700_000
    assert updated.json()["payer_name"] == "Trần Thị Nộp"

    cancelled = client.post(
        f"/api/accounting/payment-receipts/{receipt['id']}/cancel",
        json={"reason": "Lập nhầm số tiền"},
        headers=headers,
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"

    # Hủy xong thì hạn mức thu được trả lại — lập full số đã chi được.
    fresh = client.post(receipts_url, json=_receipt_payload(2_200_000), headers=headers)
    assert fresh.status_code == 201, fresh.text
    received = client.post(
        f"/api/accounting/payment-receipts/{fresh.json()['id']}/mark-received",
        json={"bank_reference": None},
        headers=headers,
    )
    assert received.status_code == 200

    # Đã thu rồi thì không sửa/hủy được nữa.
    assert (
        client.put(
            f"/api/accounting/payment-receipts/{fresh.json()['id']}",
            json=_receipt_payload(1_000_000),
            headers=headers,
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/accounting/payment-receipts/{fresh.json()['id']}/cancel",
            json={"reason": "thử hủy"},
            headers=headers,
        ).status_code
        == 409
    )

    # Danh sách: lọc theo mã PC nguồn + trạng thái.
    listed = client.get(
        f"/api/accounting/payment-receipts?q={voucher['code']}&status=received",
        headers=headers,
    )
    assert listed.status_code == 200
    codes = [row["code"] for row in listed.json()["items"]]
    assert codes == [fresh.json()["code"]]


def test_receipt_permissions(client):
    admin_headers = _headers(client)
    supplier = _supplier(client, admin_headers)
    purchase, _ = _purchase(client, admin_headers, supplier["id"])
    voucher = _paid_cash_voucher(client, admin_headers, purchase["id"], 2_200_000)

    reader_headers = {"Authorization": f"Bearer {_accounting_user_token(approve=False)}"}
    approver_headers = {"Authorization": f"Bearer {_accounting_user_token(approve=True)}"}

    assert (
        client.get("/api/accounting/payment-receipts", headers=reader_headers).status_code == 200
    )
    assert (
        client.post(
            f"/api/accounting/payment-vouchers/{voucher['id']}/receipts",
            json=_receipt_payload(100_000),
            headers=reader_headers,
        ).status_code
        == 403
    )
    created = client.post(
        f"/api/accounting/payment-vouchers/{voucher['id']}/receipts",
        json=_receipt_payload(100_000),
        headers=approver_headers,
    )
    assert created.status_code == 201, created.text
    # approve nhưng không có manage_status thì không xác nhận đã thu được.
    assert (
        client.post(
            f"/api/accounting/payment-receipts/{created.json()['id']}/mark-received",
            json={"bank_reference": None},
            headers=approver_headers,
        ).status_code
        == 403
    )


def test_vouchers_group_sort_keeps_same_pmh_adjacent(client):
    """sort=-group: phiếu cùng PMH đứng liền nhau, nhóm có phiếu mới nhất lên đầu."""
    headers = _headers(client)
    supplier = _supplier(client, headers)
    purchase_a, _ = _purchase(client, headers, supplier["id"])
    purchase_b, _ = _purchase(client, headers, supplier["id"])

    a1 = client.post(
        f"/api/accounting/purchase-requests/{purchase_a['id']}/approve-and-create-voucher",
        json=_cash_payload(500_000),
        headers=headers,
    )
    assert a1.status_code == 201, a1.text
    b1 = client.post(
        f"/api/accounting/purchase-requests/{purchase_b['id']}/approve-and-create-voucher",
        json=_cash_payload(400_000),
        headers=headers,
    )
    assert b1.status_code == 201, b1.text
    # Chi bổ sung cho PMH A SAU CÙNG — nhóm A phải nổi lên đầu, A1+A2 liền nhau.
    a2 = client.post(
        "/api/accounting/payment-vouchers",
        json={"purchase_request_id": purchase_a["id"], **_cash_payload(300_000)},
        headers=headers,
    )
    assert a2.status_code == 201, a2.text

    listed = client.get(
        "/api/accounting/payment-vouchers?sort=-group&size=50", headers=headers
    )
    assert listed.status_code == 200, listed.text
    codes = [row["code"] for row in listed.json()["items"]]
    expected = [a1.json()["code"], a2.json()["code"], b1.json()["code"]]
    assert codes == expected, codes
    assert all("T" in row["created_at"] for row in listed.json()["items"])

    filtered = client.get(
        "/api/accounting/payment-vouchers?sort=-group&status=waiting_payment&size=50",
        headers=headers,
    )
    assert filtered.status_code == 200
    assert [row["code"] for row in filtered.json()["items"]] == expected


def test_accounting_read_can_trace_department_requests(client):
    """Kế toán (chỉ ke_toan:read) truy vết được YCMH nguồn từ PMH/Phiếu chi."""
    admin_headers = _headers(client)
    supplier = _supplier(client, admin_headers)
    _, source = _purchase(client, admin_headers, supplier["id"])
    reader_headers = {"Authorization": f"Bearer {_accounting_user_token(approve=False)}"}

    listed = client.get(
        f"/api/department-purchase-requests?q={source['code']}", headers=reader_headers
    )
    assert listed.status_code == 200, listed.text
    assert [row["code"] for row in listed.json()["items"]] == [source["code"]]
    detail = client.get(
        f"/api/department-purchase-requests/{source['id']}", headers=reader_headers
    )
    assert detail.status_code == 200, detail.text


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
