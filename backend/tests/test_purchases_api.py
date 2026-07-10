"""Tests for the Thu mua API: suppliers + purchase-request approval flow."""
from __future__ import annotations

import re

import pytest

from app.db import SessionLocal
from app.models.role import SCOPE_ALL
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password


@pytest.fixture
def token(client, seed_credentials) -> str:
    resp = client.post("/api/auth/login", json=seed_credentials)
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def auth_headers(token) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _buyer_token() -> str:
    db = SessionLocal()
    try:
        users = UserRepository(db)
        existing = users.get_by_username("buyer-no-approve")
        if existing is not None:
            return create_access_token(str(existing.id))
        kd = DepartmentRepository(db).get_by_name("Kinh doanh")
        roles = RoleRepository(db)
        role = roles.create(name="Nhan vien mua hang", department_id=kd.id)
        roles.set_permission(
            role_id=role.id,
            module_key="thu_mua",
            can_read=True,
            can_create=True,
            can_update=True,
            can_delete=False,
            can_cancel=True,
            scope=SCOPE_ALL,
        )
        u = users.create(username="buyer-no-approve", name="Buyer", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=kd.id, role_id=role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def _sales_token() -> str:
    db = SessionLocal()
    try:
        users = UserRepository(db)
        existing = users.get_by_username("purchase-sales")
        if existing is not None:
            return create_access_token(str(existing.id))
        kd = DepartmentRepository(db).get_by_name("Kinh doanh")
        sales_role = RoleRepository(db).get_by_name_and_department("NV Sales", kd.id)
        u = users.create(username="purchase-sales", name="Sales", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=kd.id, role_id=sales_role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def _sales2_token() -> str:
    db = SessionLocal()
    try:
        users = UserRepository(db)
        existing = users.get_by_username("purchase-sales-2")
        if existing is not None:
            return create_access_token(str(existing.id))
        kd = DepartmentRepository(db).get_by_name("Kinh doanh")
        sales_role = RoleRepository(db).get_by_name_and_department("NV Sales", kd.id)
        u = users.create(username="purchase-sales-2", name="Sales 2", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=kd.id, role_id=sales_role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def _supplier(client, headers, name: str = "Cong ty Giay An Phat") -> dict:
    resp = client.post(
        "/api/suppliers",
        json={
            "name": name,
            "tax_code": "0101234567",
            "phone": "0901000001",
            "email": "ncc@example.com",
            "address": "12 Nguyen Trai, TP.HCM",
            "contact_name": "Ms Lan",
            "supplier_group": "paper",
            "payment_terms": "Cong no 30 ngay",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _request_payload(supplier_id: int | None = None) -> dict:
    return {
        "supplier_id": supplier_id,
        "source_request_ids": [],
        "purpose": "Mua giay cho don hang carton",
        "needed_date": "2026-07-20",
        "note": "Can bao gia truoc khi mua",
        "lines": [
            {
                "item_name": "Giay Duplex 350gsm",
                "unit": "to",
                "quantity": 1000,
                "expected_unit_price": 2200,
            },
            {
                "item_name": "Keo can mang",
                "unit": "kg",
                "quantity": 5,
                "expected_unit_price": 80000,
                "note": "Hang san xuat gap",
            },
        ],
    }


def _department_request_payload() -> dict:
    return {
        "source_type": "kinh_doanh",
        "related_document_type": "sales_order",
        "related_document_code": "DH-260710-001",
        "purpose": "Thieu giay cho don hang carton",
        "needed_date": "2026-07-18",
        "note": "Sale tao yeu cau tu don hang",
        "lines": [
            {
                "item_name": "Giay Duplex 350gsm",
                "unit": "to",
                "quantity": 1000,
            }
        ],
    }


def _create_department_request(client, headers) -> dict:
    resp = client.post(
        "/api/department-purchase-requests",
        json=_department_request_payload(),
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_purchase_request(client, headers, supplier_id: int, source_ids: list[int] | None = None) -> dict:
    if source_ids is None:
        source_ids = [_create_department_request(client, headers)["id"]]
    payload = _request_payload(supplier_id)
    payload["source_request_ids"] = source_ids
    resp = client.post(
        "/api/purchase-requests",
        json=payload,
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_supplier_crud_and_toggle(client, auth_headers):
    supplier = _supplier(client, auth_headers)
    assert supplier["name"] == "Cong ty Giay An Phat"
    assert supplier["status"] == "active"

    listed = client.get("/api/suppliers?q=an phat", headers=auth_headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    updated = client.put(
        f"/api/suppliers/{supplier['id']}",
        json={
            "name": "Cong ty Giay An Phat 2",
            "tax_code": "0101234567",
            "phone": "0901000002",
            "email": "ncc2@example.com",
            "address": "99 Nguyen Trai, TP.HCM",
            "contact_name": "Ms Lan",
            "supplier_group": "paper",
            "status": "active",
        },
        headers=auth_headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["phone"] == "0901000002"

    toggled = client.patch(f"/api/suppliers/{supplier['id']}/toggle-active", headers=auth_headers)
    assert toggled.status_code == 200
    assert toggled.json()["status"] == "inactive"


def test_supplier_required_contact_fields(client, auth_headers):
    missing_email = {
        "name": "NCC Thieu Email",
        "tax_code": "0109999999",
        "phone": "0909999999",
        "address": "1 Le Loi",
        "contact_name": "Anh Nam",
        "supplier_group": "paper",
    }
    resp = client.post("/api/suppliers", json=missing_email, headers=auth_headers)
    assert resp.status_code == 422

    blank_fields = {
        "name": "NCC Blank",
        "tax_code": " ",
        "phone": "0909999999",
        "email": "blank@example.com",
        "address": " ",
        "contact_name": "Anh Nam",
        "supplier_group": "paper",
    }
    resp = client.post("/api/suppliers", json=blank_fields, headers=auth_headers)
    assert resp.status_code == 422
    assert "Mã số thuế" in resp.json()["detail"]
    assert "Địa chỉ" in resp.json()["detail"]


def test_purchase_request_full_lifecycle(client, auth_headers):
    supplier = _supplier(client, auth_headers)
    source = _create_department_request(client, auth_headers)
    assert re.fullmatch(r"YCMH-\d{6}-[A-Z0-9]{4}", source["code"])
    assert source["lines"][0]["expected_unit_price"] == 0

    pr = _create_purchase_request(client, auth_headers, supplier["id"], [source["id"]])

    assert re.fullmatch(r"PMH-\d{6}-[A-Z0-9]{4}", pr["code"])
    assert pr["status"] == "draft"
    assert pr["supplier_name"] == supplier["name"]
    assert pr["sources"][0]["code"] == source["code"]
    assert pr["created_by_name"] == "Admin"
    assert pr["approved_by_name"] is None
    assert pr["total_estimate"] == 2_600_000
    assert [line["line_total"] for line in pr["lines"]] == [2_200_000, 400_000]
    linked_source = client.get(f"/api/department-purchase-requests/{source['id']}", headers=auth_headers)
    assert linked_source.status_code == 200
    assert linked_source.json()["status"] == "pending_approval"

    submitted = client.post(f"/api/purchase-requests/{pr['id']}/submit", headers=auth_headers)
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "pending_approval"
    assert submitted.json()["submitted_at"] is not None
    linked_source = client.get(f"/api/department-purchase-requests/{source['id']}", headers=auth_headers)
    assert linked_source.json()["status"] == "pending_approval"

    approved = client.post(f"/api/purchase-requests/{pr['id']}/approve", headers=auth_headers)
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["status"] == "approved"
    assert body["approved_by_name"] == "Admin"
    assert body["approved_at"] is not None
    linked_source = client.get(f"/api/department-purchase-requests/{source['id']}", headers=auth_headers)
    assert linked_source.json()["status"] == "in_purchase"

    blocked = client.put(
        f"/api/purchase-requests/{pr['id']}",
        json={**_request_payload(supplier["id"]), "source_request_ids": [source["id"]]},
        headers=auth_headers,
    )
    assert blocked.status_code == 409

    purchased = client.post(f"/api/purchase-requests/{pr['id']}/mark-purchased", headers=auth_headers)
    assert purchased.status_code == 200
    assert purchased.json()["status"] == "purchased"

    received = client.post(f"/api/purchase-requests/{pr['id']}/mark-received", headers=auth_headers)
    assert received.status_code == 200
    assert received.json()["status"] == "received"
    done_source = client.get(f"/api/department-purchase-requests/{source['id']}", headers=auth_headers)
    assert done_source.json()["status"] == "done"


def test_purchase_request_line_discount_and_vat(client, auth_headers):
    supplier = _supplier(client, auth_headers)
    source = _create_department_request(client, auth_headers)
    payload = _request_payload(supplier["id"])
    payload["source_request_ids"] = [source["id"]]
    payload["lines"] = [
        {
            "item_name": "Giay Duplex 350gsm",
            "unit": "to",
            "quantity": 1000,
            "expected_unit_price": 2200,
            "discount_percent": 10,
            "vat_percent": 8,
        }
    ]

    resp = client.post("/api/purchase-requests", json=payload, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    line = body["lines"][0]
    assert line["discount_amount"] == 220_000
    assert line["vat_amount"] == 158_400
    assert line["line_total"] == 2_138_400
    assert body["total_estimate"] == 2_138_400


def test_purchase_request_delete_only_draft(client, auth_headers):
    supplier = _supplier(client, auth_headers)
    draft = _create_purchase_request(client, auth_headers, supplier["id"])
    assert client.delete(f"/api/purchase-requests/{draft['id']}", headers=auth_headers).status_code == 204

    pending = _create_purchase_request(client, auth_headers, supplier["id"])
    assert client.post(f"/api/purchase-requests/{pending['id']}/submit", headers=auth_headers).status_code == 200
    assert client.delete(f"/api/purchase-requests/{pending['id']}", headers=auth_headers).status_code == 409


def test_purchase_request_required_header_and_line_fields(client, auth_headers):
    supplier = _supplier(client, auth_headers)
    source = _create_department_request(client, auth_headers)

    missing_supplier = _request_payload(supplier["id"])
    missing_supplier["source_request_ids"] = [source["id"]]
    missing_supplier.pop("supplier_id")
    assert (
        client.post("/api/purchase-requests", json=missing_supplier, headers=auth_headers).status_code
        == 422
    )

    missing_source = _request_payload(supplier["id"])
    resp = client.post("/api/purchase-requests", json=missing_source, headers=auth_headers)
    assert resp.status_code == 422

    blank_purpose = _request_payload(supplier["id"])
    blank_purpose["source_request_ids"] = [source["id"]]
    blank_purpose["purpose"] = " "
    resp = client.post("/api/purchase-requests", json=blank_purpose, headers=auth_headers)
    assert resp.status_code == 422
    assert "Mục đích" in resp.json()["detail"]

    missing_needed_date = _request_payload(supplier["id"])
    missing_needed_date["source_request_ids"] = [source["id"]]
    missing_needed_date.pop("needed_date")
    assert (
        client.post("/api/purchase-requests", json=missing_needed_date, headers=auth_headers).status_code
        == 422
    )

    bad_line = _request_payload(supplier["id"])
    bad_line["source_request_ids"] = [source["id"]]
    bad_line["lines"][0]["unit"] = " "
    resp = client.post("/api/purchase-requests", json=bad_line, headers=auth_headers)
    assert resp.status_code == 422
    assert "Đơn vị tính" in resp.json()["detail"]

    zero_price = _request_payload(supplier["id"])
    zero_price["source_request_ids"] = [source["id"]]
    zero_price["lines"][0]["expected_unit_price"] = 0
    assert (
        client.post("/api/purchase-requests", json=zero_price, headers=auth_headers).status_code
        == 422
    )


def test_purchase_request_validates_active_supplier(client, auth_headers):
    supplier = _supplier(client, auth_headers, name="NCC Tam Ngung")
    source = _create_department_request(client, auth_headers)
    assert client.patch(f"/api/suppliers/{supplier['id']}/toggle-active", headers=auth_headers).status_code == 200

    payload = _request_payload(supplier["id"])
    payload["source_request_ids"] = [source["id"]]
    resp = client.post(
        "/api/purchase-requests",
        json=payload,
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_purchase_permissions(client, auth_headers):
    sales_headers = {"Authorization": f"Bearer {_sales_token()}"}
    sales2_headers = {"Authorization": f"Bearer {_sales2_token()}"}
    buyer_headers = {"Authorization": f"Bearer {_buyer_token()}"}

    assert client.get("/api/suppliers", headers=sales_headers).status_code == 403
    assert client.get("/api/purchase-requests", headers=sales_headers).status_code == 403
    assert client.get("/api/department-purchase-requests", headers=sales_headers).status_code == 200
    sales_source = client.post(
        "/api/department-purchase-requests",
        json=_department_request_payload(),
        headers=sales_headers,
    )
    assert sales_source.status_code == 201, sales_source.text
    source_id = sales_source.json()["id"]
    assert (
        client.post(
            f"/api/department-purchase-requests/{source_id}/cancel",
            json={"reason": "Nguoi khac huy"},
            headers=sales2_headers,
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/department-purchase-requests/{source_id}/cancel",
            json={"reason": "Nguoi tao huy"},
            headers=sales_headers,
        ).status_code
        == 200
    )
    admin_source = client.post(
        "/api/department-purchase-requests",
        json=_department_request_payload(),
        headers=sales_headers,
    ).json()
    assert (
        client.post(
            f"/api/department-purchase-requests/{admin_source['id']}/cancel",
            json={"reason": "Admin huy"},
            headers=auth_headers,
        ).status_code
        == 200
    )

    supplier = _supplier(client, buyer_headers, name="NCC Buyer")
    buyer_pr = _create_purchase_request(client, buyer_headers, supplier["id"])
    assert client.post(f"/api/purchase-requests/{buyer_pr['id']}/submit", headers=buyer_headers).status_code == 200
    assert client.post(f"/api/purchase-requests/{buyer_pr['id']}/approve", headers=buyer_headers).status_code == 403
    assert client.post(f"/api/purchase-requests/{buyer_pr['id']}/approve", headers=auth_headers).status_code == 200
