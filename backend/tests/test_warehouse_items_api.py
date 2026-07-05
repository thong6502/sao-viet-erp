"""Tests for the Kho hàng vận hành (warehouse items) API — module `kho`."""
from __future__ import annotations

import pytest

from app.db import SessionLocal
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


@pytest.fixture
def warehouse_id(client, auth_headers) -> int:
    r = client.post("/api/warehouses", json={"name": "Kho vận hành"}, headers=auth_headers)
    assert r.status_code == 201
    return r.json()["id"]


def _sales_token() -> str:
    db = SessionLocal()
    try:
        users = UserRepository(db)
        existing = users.get_by_username("wh-item-sales")
        if existing is not None:
            return create_access_token(str(existing.id))
        kd = DepartmentRepository(db).get_by_name("Kinh doanh")
        sales_role = RoleRepository(db).get_by_name_and_department("NV Sales", kd.id)
        u = users.create(username="wh-item-sales", name="S", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=kd.id, role_id=sales_role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def test_warehouse_item_crud(client, auth_headers, warehouse_id):
    # Create — records the actor as người nhập.
    resp = client.post(
        "/api/warehouse-items",
        json={"warehouse_id": warehouse_id, "name": "Giấy A4", "quantity": 100, "unit": "ram"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["warehouse_id"] == warehouse_id
    assert body["name"] == "Giấy A4"
    assert body["quantity"] == 100
    assert body["unit"] == "ram"
    assert body["created_by_name"] == "Admin"
    item_id = body["id"]

    # List (filtered by warehouse).
    listed = client.get(
        f"/api/warehouse-items?warehouse_id={warehouse_id}", headers=auth_headers
    ).json()
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == item_id

    # Update.
    upd = client.put(
        f"/api/warehouse-items/{item_id}",
        json={"warehouse_id": warehouse_id, "name": "Giấy A4 80", "quantity": 50, "unit": "ram"},
        headers=auth_headers,
    )
    assert upd.status_code == 200
    assert upd.json()["quantity"] == 50

    # Delete.
    assert client.delete(f"/api/warehouse-items/{item_id}", headers=auth_headers).status_code == 204


def test_warehouse_options_lists_active_warehouses(client, auth_headers, warehouse_id):
    opts = client.get("/api/warehouse-items/warehouse-options", headers=auth_headers).json()
    assert any(o["id"] == warehouse_id for o in opts)
    assert all({"id", "code", "name"} <= set(o) for o in opts)


def test_item_rejects_unconfigured_warehouse(client, auth_headers):
    r = client.post(
        "/api/warehouse-items",
        json={"warehouse_id": 999999, "name": "X", "quantity": 1, "unit": "cái"},
        headers=auth_headers,
    )
    assert r.status_code == 400


def test_item_rejects_inactive_warehouse(client, auth_headers):
    wid = client.post(
        "/api/warehouses", json={"name": "Kho ẩn", "is_active": False}, headers=auth_headers
    ).json()["id"]
    r = client.post(
        "/api/warehouse-items",
        json={"warehouse_id": wid, "name": "X", "quantity": 1, "unit": "cái"},
        headers=auth_headers,
    )
    assert r.status_code == 400


def test_item_blank_name_and_negative_qty_rejected(client, auth_headers, warehouse_id):
    assert (
        client.post(
            "/api/warehouse-items",
            json={"warehouse_id": warehouse_id, "name": " ", "quantity": 1, "unit": "cái"},
            headers=auth_headers,
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/warehouse-items",
            json={"warehouse_id": warehouse_id, "name": "X", "quantity": -5, "unit": "cái"},
            headers=auth_headers,
        ).status_code
        == 422
    )


def test_warehouse_items_forbidden_without_kho_permission(client, warehouse_id):
    headers = {"Authorization": f"Bearer {_sales_token()}"}
    assert client.get("/api/warehouse-items", headers=headers).status_code == 403
    assert (
        client.get("/api/warehouse-items/warehouse-options", headers=headers).status_code == 403
    )
    assert (
        client.post(
            "/api/warehouse-items",
            json={"warehouse_id": warehouse_id, "name": "X", "quantity": 1, "unit": "cái"},
            headers=headers,
        ).status_code
        == 403
    )
