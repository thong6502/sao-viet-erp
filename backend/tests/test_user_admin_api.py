"""spec-08 — Quản trị tài khoản: sửa thông tin, đặt lại mật khẩu, phiên & hoạt động.

Admin can edit a user's name + department (role drops on dept change), reset the password
(temp shown once + all sessions revoked), list/revoke live sessions, and read a user's
activity. Everything is gated on `nguoi_dung`.
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


def _dept_id(name: str) -> int:
    db = SessionLocal()
    try:
        return DepartmentRepository(db).get_by_name(name).id
    finally:
        db.close()


def _role_id(dept_name: str, role_name: str) -> int:
    db = SessionLocal()
    try:
        d = DepartmentRepository(db).get_by_name(dept_name)
        return RoleRepository(db).get_by_name_and_department(role_name, d.id).id
    finally:
        db.close()


def _sales_token() -> str:
    db = SessionLocal()
    try:
        users = UserRepository(db)
        existing = users.get_by_username("sales-ua")
        if existing is not None:
            return create_access_token(str(existing.id))
        kd = DepartmentRepository(db).get_by_name("Kinh doanh")
        role = RoleRepository(db).get_by_name_and_department("NV Sales", kd.id)
        u = users.create(username="sales-ua", name="S", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=kd.id, role_id=role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def test_create_user_default_password(client):
    token = _admin_token(client)
    kd = _dept_id("Kinh doanh")
    res = client.post(
        "/api/users",
        json={"name": "U mặc định", "username": "u-default-pw", "department_id": kd},
        headers=_h(token),
    ).json()
    assert res["initial_password"] == "password123"  # mật khẩu mặc định
    login = client.post("/api/auth/login", json={"username": "u-default-pw", "password": "password123"})
    assert login.status_code == 200


def test_create_user_custom_password(client):
    token = _admin_token(client)
    kd = _dept_id("Kinh doanh")
    res = client.post(
        "/api/users",
        json={"name": "U tự đặt", "username": "u-custom-pw", "department_id": kd, "password": "MyPass2026"},
        headers=_h(token),
    ).json()
    assert res["initial_password"] == "MyPass2026"
    login = client.post("/api/auth/login", json={"username": "u-custom-pw", "password": "MyPass2026"})
    assert login.status_code == 200


def test_create_user_short_password_rejected(client):
    token = _admin_token(client)
    kd = _dept_id("Kinh doanh")
    r = client.post(
        "/api/users",
        json={"name": "U ngắn", "username": "u-short-pw", "department_id": kd, "password": "123"},
        headers=_h(token),
    )
    assert r.status_code == 422


def _make_target(client, token, username="target-1") -> int:
    kd = _dept_id("Kinh doanh")
    created = client.post(
        "/api/users",
        json={"name": "Người Mục Tiêu", "username": username, "department_id": kd},
        headers=_h(token),
    ).json()
    # give them a role in Kinh doanh so the dept-change drop is observable
    client.put(
        f"/api/users/{created['id']}/role",
        json={"role_id": _role_id("Kinh doanh", "NV Sales")},
        headers=_h(token),
    )
    return created["id"]


def test_update_user_name_and_department_drops_role(client):
    token = _admin_token(client)
    uid = _make_target(client, token, "upd-user")
    hcns = _dept_id("Hành chính nhân sự")

    resp = client.put(
        f"/api/users/{uid}",
        json={"name": "Tên Mới", "department_id": hcns},
        headers=_h(token),
    )
    assert resp.status_code == 200

    row = next(u for u in client.get("/api/users", headers=_h(token)).json() if u["id"] == uid)
    assert row["name"] == "Tên Mới"
    assert row["department_id"] == hcns
    assert row["role_id"] is None  # role dropped on department change
    assert row["username"] == "upd-user"  # username never changes


def test_reset_password_returns_temp_and_revokes_sessions(client):
    token = _admin_token(client)
    uid = _make_target(client, token, "reset-user")

    temp1 = client.post(f"/api/users/{uid}/reset-password", headers=_h(token)).json()[
        "temporary_password"
    ]
    assert temp1

    # The user can log in with the temp password.
    login = client.post("/api/auth/login", json={"username": "reset-user", "password": temp1})
    assert login.status_code == 200
    user_access = login.json()["access_token"]
    assert client.get("/api/auth/me", headers=_h(user_access)).status_code == 200

    # A second reset invalidates the old temp password AND the old access token (session revoke).
    temp2 = client.post(f"/api/users/{uid}/reset-password", headers=_h(token)).json()[
        "temporary_password"
    ]
    assert temp2 != temp1
    assert client.get("/api/auth/me", headers=_h(user_access)).status_code == 401
    assert (
        client.post("/api/auth/login", json={"username": "reset-user", "password": temp1}).status_code
        == 401
    )
    assert (
        client.post("/api/auth/login", json={"username": "reset-user", "password": temp2}).status_code
        == 200
    )


def test_sessions_list_and_revoke(client):
    token = _admin_token(client)
    uid = _make_target(client, token, "sess-user")
    temp = client.post(f"/api/users/{uid}/reset-password", headers=_h(token)).json()[
        "temporary_password"
    ]

    # Logging in creates a live session (a refresh token with the client's user-agent).
    client.post("/api/auth/login", json={"username": "sess-user", "password": temp})
    sessions = client.get(f"/api/users/{uid}/sessions", headers=_h(token)).json()
    assert len(sessions) >= 1
    assert "user_agent" in sessions[0] and "created_at" in sessions[0]

    # Revoke everything → no live sessions left.
    revoked = client.post(f"/api/users/{uid}/revoke-sessions", headers=_h(token))
    assert revoked.status_code == 204
    assert client.get(f"/api/users/{uid}/sessions", headers=_h(token)).json() == []


def test_activity_lists_actions_on_user(client):
    token = _admin_token(client)
    uid = _make_target(client, token, "act-user")
    client.post(f"/api/users/{uid}/reset-password", headers=_h(token))

    activity = client.get(f"/api/users/{uid}/activity", headers=_h(token)).json()
    actions = {a["action"] for a in activity}
    # create_user + assign_role + reset_password all target this user
    assert {"create_user", "assign_role", "reset_password"} <= actions
    assert all(a["target"] == f"user:{uid}" for a in activity)


def test_endpoints_forbidden_without_permission(client):
    token = _sales_token()
    hcns = _dept_id("Hành chính nhân sự")
    assert client.put("/api/users/1", json={"name": "x", "department_id": hcns}, headers=_h(token)).status_code == 403
    assert client.post("/api/users/1/reset-password", headers=_h(token)).status_code == 403
    assert client.post("/api/users/1/revoke-sessions", headers=_h(token)).status_code == 403
    assert client.get("/api/users/1/sessions", headers=_h(token)).status_code == 403
    assert client.get("/api/users/1/activity", headers=_h(token)).status_code == 403
