"""feat-009 — Người dùng admin API.

HR creates accounts (+ department), a head assigns a role from the user's department,
accounts lock/unlock, and a locked account can neither log in nor use /me.
A non-admin (NV Sales, no nguoi_dung permission) is forbidden.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password

ADMIN = {"username": "admin", "password": "admin123"}
DEFAULT_PW = "password123"


def _admin_token(client) -> str:
    return client.post("/api/auth/login", json=ADMIN).json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _dept_id(name: str) -> int:
    db = SessionLocal()
    try:
        return DepartmentRepository(db).get_by_name(name).id
    finally:
        db.close()


def _role_id(name: str, dept_name: str) -> int:
    db = SessionLocal()
    try:
        dept = DepartmentRepository(db).get_by_name(dept_name)
        return RoleRepository(db).get_by_name_and_department(name, dept.id).id
    finally:
        db.close()


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
        existing = users.get_by_username("sales-users")
        if existing is not None:
            return create_access_token(str(existing.id))
        kd = DepartmentRepository(db).get_by_name("Kinh doanh")
        sales_role = RoleRepository(db).get_by_name_and_department("NV Sales", kd.id)
        u = users.create(
            username="sales-users", name="S", password_hash=hash_password("x")
        )
        users.set_assignment(u, department_id=kd.id, role_id=sales_role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def test_list_users_includes_admin(client):
    rows = client.get("/api/users", headers=_h(_admin_token(client))).json()
    assert any(u["username"] == "admin" for u in rows)


def test_create_user_starts_with_no_role(client):
    token = _admin_token(client)
    kd_id = _dept_id("Kinh doanh")
    resp = client.post(
        "/api/users",
        json={"name": "Nguyễn A", "username": "nguyena", "department_id": kd_id},
        headers=_h(token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["department_id"] == kd_id
    assert body["role_id"] is None  # most-minimal default until a head assigns
    assert body["is_active"] is True
    # every user gets a system-generated TKxxx account code (Đ1: tách khỏi NV của hồ sơ).
    import re

    assert re.fullmatch(r"TK\d{3,}", body["code"]), body["code"]


def test_user_codes_are_unique_and_listed(client):
    token = _admin_token(client)
    kd_id = _dept_id("Kinh doanh")
    for uname in ("code1", "code2"):
        client.post(
            "/api/users",
            json={"name": uname, "username": uname, "department_id": kd_id},
            headers=_h(token),
        )
    rows = client.get("/api/users", headers=_h(token)).json()
    codes = [u["code"] for u in rows if u["code"]]
    assert all(c.startswith("TK") for c in codes)  # mã tài khoản đổi NV→TK (Đ1, migration 0042)
    assert len(codes) == len(set(codes))  # no duplicates


def test_create_user_validation(client):
    token = _admin_token(client)
    kd_id = _dept_id("Kinh doanh")
    client.post(
        "/api/users", json={"name": "Dup", "username": "dup", "department_id": kd_id}, headers=_h(token)
    )
    dup = client.post(
        "/api/users", json={"name": "Dup2", "username": "dup", "department_id": kd_id}, headers=_h(token)
    )
    assert dup.status_code == 409  # username taken

    blank_username = client.post(
        "/api/users", json={"name": "X", "username": "", "department_id": kd_id}, headers=_h(token)
    )
    assert blank_username.status_code == 422

    no_name = client.post(
        "/api/users", json={"name": "", "username": "y", "department_id": kd_id}, headers=_h(token)
    )
    assert no_name.status_code == 422

    bad_dept = client.post(
        "/api/users", json={"name": "Z", "username": "z", "department_id": 99999}, headers=_h(token)
    )
    assert bad_dept.status_code == 404


def test_assign_role_must_match_department(client):
    token = _admin_token(client)
    kd_id = _dept_id("Kinh doanh")
    uid = client.post(
        "/api/users", json={"name": "B", "username": "userb", "department_id": kd_id}, headers=_h(token)
    ).json()["id"]

    # A KD role -> ok.
    sales = _role_id("NV Sales", "Kinh doanh")
    ok = client.put(f"/api/users/{uid}/role", json={"role_id": sales}, headers=_h(token))
    assert ok.status_code == 200
    assert ok.json()["role_id"] == sales

    # A role from another department -> 400.
    giam_doc = _role_id("Giám đốc", "Ban giám đốc")
    bad = client.put(f"/api/users/{uid}/role", json={"role_id": giam_doc}, headers=_h(token))
    assert bad.status_code == 400


def test_lock_blocks_login_and_me(client):
    token = _admin_token(client)
    kd_id = _dept_id("Kinh doanh")
    uid = client.post(
        "/api/users", json={"name": "C", "username": "cuser", "department_id": kd_id}, headers=_h(token)
    ).json()["id"]
    creds = {"username": "cuser", "password": DEFAULT_PW}

    # The new user can log in with the default password and use /me.
    login = client.post("/api/auth/login", json=creds)
    assert login.status_code == 200
    u_token = login.json()["access_token"]
    assert client.get("/api/auth/me", headers=_h(u_token)).status_code == 200

    # Admin locks the account.
    locked = client.put(f"/api/users/{uid}/active", json={"is_active": False}, headers=_h(token))
    assert locked.status_code == 200 and locked.json()["is_active"] is False

    # The still-valid token is now rejected, and a fresh login is refused.
    assert client.get("/api/auth/me", headers=_h(u_token)).status_code == 403
    assert client.post("/api/auth/login", json=creds).status_code == 401


def test_cannot_lock_self(client):
    token = _admin_token(client)
    resp = client.put(f"/api/users/{_admin_id()}/active", json={"is_active": False}, headers=_h(token))
    assert resp.status_code == 400


def test_cannot_revoke_own_sessions(client):
    token = _admin_token(client)
    resp = client.post(f"/api/users/{_admin_id()}/revoke-sessions", headers=_h(token))
    assert resp.status_code == 400


def test_non_admin_forbidden(client):
    token = _sales_token()
    assert client.get("/api/users", headers=_h(token)).status_code == 403
    assert (
        client.post(
            "/api/users",
            json={"name": "X", "username": "userx", "department_id": _dept_id("Kinh doanh")},
            headers=_h(token),
        ).status_code
        == 403
    )
