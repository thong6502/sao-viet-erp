"""feat-008 — Phòng ban admin API.

Admin can list department summaries, create (with name dedup), rename, set a head
(must belong to the department), and delete (blocked when roles/users remain);
a non-admin (NV Sales, no phong_ban permission) is forbidden.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password

ADMIN = {"username": "admin", "password": "admin123"}


def _admin_token(client) -> str:
    return client.post("/api/auth/login", json=ADMIN).json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _admin_id() -> int:
    db = SessionLocal()
    try:
        return UserRepository(db).get_by_username("admin").id
    finally:
        db.close()


def _sales_token() -> str:
    db = SessionLocal()
    try:
        users = UserRepository(db)
        existing = users.get_by_username("sales-dept")
        if existing is not None:
            return create_access_token(str(existing.id))
        kd = DepartmentRepository(db).get_by_name("Kinh doanh")
        sales_role = RoleRepository(db).get_by_name_and_department("NV Sales", kd.id)
        user = users.create(
            username="sales-dept", name="S", password_hash=hash_password("x")
        )
        users.set_assignment(user, department_id=kd.id, role_id=sales_role.id, is_active=True)
        return create_access_token(str(user.id))
    finally:
        db.close()


def test_list_departments_has_summary_fields(client):
    resp = client.get("/api/departments", headers=_h(_admin_token(client)))
    assert resp.status_code == 200
    kd = next(d for d in resp.json() if d["name"] == "Kinh doanh")
    assert kd["role_count"] >= 2  # Trưởng phòng KD + NV Sales (at least)
    assert "user_count" in kd and "head_user_id" in kd and "head_name" in kd


def test_create_department_dedup_and_validation(client):
    token = _admin_token(client)
    created = client.post("/api/departments", json={"name": "Thiết kế"}, headers=_h(token))
    assert created.status_code == 201

    dup = client.post("/api/departments", json={"name": "Thiết kế"}, headers=_h(token))
    assert dup.status_code == 409

    empty = client.post("/api/departments", json={"name": ""}, headers=_h(token))
    assert empty.status_code == 422


def test_rename_department(client):
    token = _admin_token(client)
    dept_id = client.post("/api/departments", json={"name": "Tạm A"}, headers=_h(token)).json()["id"]

    renamed = client.put(f"/api/departments/{dept_id}", json={"name": "Tạm B"}, headers=_h(token))
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Tạm B"

    clash = client.put(f"/api/departments/{dept_id}", json={"name": "Kinh doanh"}, headers=_h(token))
    assert clash.status_code == 409


def test_set_head_must_belong_to_department(client):
    token = _admin_token(client)
    dept_id = client.post("/api/departments", json={"name": "Phòng Head Test"}, headers=_h(token)).json()["id"]

    # Admin belongs to Ban giám đốc, not this department -> 400.
    bad = client.put(
        f"/api/departments/{dept_id}",
        json={"name": "Phòng Head Test", "head_user_id": _admin_id()},
        headers=_h(token),
    )
    assert bad.status_code == 400

    # Create a user IN this department, then set them as head -> ok.
    db = SessionLocal()
    try:
        user = UserRepository(db).create(
            username="head", name="H", password_hash=hash_password("x")
        )
        UserRepository(db).set_assignment(user, department_id=dept_id, role_id=None, is_active=True)
        uid = user.id
    finally:
        db.close()

    ok = client.put(
        f"/api/departments/{dept_id}",
        json={"name": "Phòng Head Test", "head_user_id": uid},
        headers=_h(token),
    )
    assert ok.status_code == 200
    assert ok.json()["head_user_id"] == uid

    members = client.get(f"/api/departments/{dept_id}/users", headers=_h(token)).json()
    assert any(m["id"] == uid for m in members)


def test_delete_department_blocked_then_ok(client):
    token = _admin_token(client)

    db = SessionLocal()
    try:
        kd_id = DepartmentRepository(db).get_by_name("Kinh doanh").id
    finally:
        db.close()
    blocked = client.delete(f"/api/departments/{kd_id}", headers=_h(token))
    assert blocked.status_code == 409  # has roles

    empty_id = client.post("/api/departments", json={"name": "Phòng Rỗng"}, headers=_h(token)).json()["id"]
    ok = client.delete(f"/api/departments/{empty_id}", headers=_h(token))
    assert ok.status_code == 204


def test_non_admin_forbidden(client):
    token = _sales_token()
    assert client.post("/api/departments", json={"name": "X"}, headers=_h(token)).status_code == 403
    assert client.get("/api/departments", headers=_h(token)).status_code == 403
