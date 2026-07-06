"""Tests for the Cấu hình kho hàng (warehouses) catalog API."""
from __future__ import annotations

import re

import pytest

from app.db import SessionLocal
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password


def _sales_token() -> str:
    """A logged-in NV Sales token — has no dm_kho permission (for 403 checks)."""
    db = SessionLocal()
    try:
        users = UserRepository(db)
        existing = users.get_by_username("wh-sales")
        if existing is not None:
            return create_access_token(str(existing.id))
        kd = DepartmentRepository(db).get_by_name("Kinh doanh")
        sales_role = RoleRepository(db).get_by_name_and_department("NV Sales", kd.id)
        u = users.create(username="wh-sales", name="S", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=kd.id, role_id=sales_role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


@pytest.fixture
def token(client, seed_credentials) -> str:
    resp = client.post("/api/auth/login", json=seed_credentials)
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def auth_headers(token) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_warehouse_crud(client, auth_headers):
    # Create — code is system-generated (KHOxxx), 4 fields.
    resp = client.post(
        "/api/warehouses",
        json={"name": "Kho tổng", "description": "Kho chính", "notes": "ghi chú"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert re.fullmatch(r"KHO\d{3,}", body["code"]), body["code"]
    assert body["name"] == "Kho tổng"
    assert body["description"] == "Kho chính"
    assert body["notes"] == "ghi chú"
    assert body["is_active"] is True
    wid = body["id"]

    # List includes it.
    listed = client.get("/api/warehouses", headers=auth_headers).json()
    assert any(w["id"] == wid for w in listed["items"])

    # Update — code stays read-only.
    upd = client.put(
        f"/api/warehouses/{wid}",
        json={"name": "Kho tổng 1", "description": None, "notes": "sửa", "is_active": False},
        headers=auth_headers,
    )
    assert upd.status_code == 200
    assert upd.json()["name"] == "Kho tổng 1"
    assert upd.json()["description"] is None
    assert upd.json()["is_active"] is False
    assert upd.json()["code"] == body["code"]

    # Delete.
    assert client.delete(f"/api/warehouses/{wid}", headers=auth_headers).status_code == 204
    assert client.get(f"/api/warehouses/{wid}", headers=auth_headers).status_code == 404


def test_warehouse_codes_sequential_and_unique(client, auth_headers):
    codes = []
    for name in ("Kho A", "Kho B", "Kho C"):
        r = client.post("/api/warehouses", json={"name": name}, headers=auth_headers)
        assert r.status_code == 201
        codes.append(r.json()["code"])
    assert all(c.startswith("KHO") for c in codes)
    assert len(codes) == len(set(codes))  # unique


def test_warehouse_duplicate_name_rejected(client, auth_headers):
    client.post("/api/warehouses", json={"name": "Kho trùng"}, headers=auth_headers)
    dup = client.post("/api/warehouses", json={"name": "Kho trùng"}, headers=auth_headers)
    assert dup.status_code == 409


def test_warehouse_blank_name_rejected(client, auth_headers):
    r = client.post("/api/warehouses", json={"name": "  "}, headers=auth_headers)
    assert r.status_code == 422


def test_warehouses_forbidden_without_permission(client):
    # NV Sales has no dm_kho permission.
    headers = {"Authorization": f"Bearer {_sales_token()}"}
    assert client.get("/api/warehouses", headers=headers).status_code == 403
    assert client.post("/api/warehouses", json={"name": "X"}, headers=headers).status_code == 403
