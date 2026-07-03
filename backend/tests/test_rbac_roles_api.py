"""feat-007 — Vai trò admin API.

Admin can list modules/departments/roles, create a role (with per-department name
dedup), and read/save a role's permission matrix; a non-admin (NV Sales, no vai_tro
permission) is forbidden.
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


def _kd_id() -> int:
    db = SessionLocal()
    try:
        return DepartmentRepository(db).get_by_name("Kinh doanh").id
    finally:
        db.close()


def _sales_token() -> str:
    """A non-admin: NV Sales role has no vai_tro permission."""
    db = SessionLocal()
    try:
        users = UserRepository(db)
        existing = users.get_by_username("sales")
        if existing is not None:
            return create_access_token(str(existing.id))
        kd = DepartmentRepository(db).get_by_name("Kinh doanh")
        sales_role = RoleRepository(db).get_by_name_and_department("NV Sales", kd.id)
        user = users.create(
            username="sales", name="S", password_hash=hash_password("x")
        )
        users.set_assignment(
            user, department_id=kd.id, role_id=sales_role.id, is_active=True
        )
        return create_access_token(str(user.id))
    finally:
        db.close()


def test_admin_lists_modules(client):
    resp = client.get("/api/rbac/modules", headers=_h(_admin_token(client)))
    assert resp.status_code == 200
    keys = {m["key"] for m in resp.json()}
    assert {"khach_hang", "vai_tro", "nguoi_dung"} <= keys


def test_admin_lists_departments(client):
    resp = client.get("/api/departments", headers=_h(_admin_token(client)))
    assert resp.status_code == 200
    assert "Kinh doanh" in {d["name"] for d in resp.json()}


def test_create_role_with_dedup_and_validation(client):
    token = _admin_token(client)
    kd_id = _kd_id()

    created = client.post(
        "/api/roles", json={"name": "Telesales", "department_id": kd_id}, headers=_h(token)
    )
    assert created.status_code == 201
    role_id = created.json()["id"]

    # Duplicate name in the same department -> 409.
    dup = client.post(
        "/api/roles", json={"name": "Telesales", "department_id": kd_id}, headers=_h(token)
    )
    assert dup.status_code == 409

    # Empty name -> 422 (schema validation).
    empty = client.post(
        "/api/roles", json={"name": "", "department_id": kd_id}, headers=_h(token)
    )
    assert empty.status_code == 422

    listed = client.get(f"/api/roles?department_id={kd_id}", headers=_h(token))
    assert any(r["id"] == role_id for r in listed.json())


def test_matrix_get_defaults_and_save_persists(client):
    token = _admin_token(client)
    kd_id = _kd_id()
    role_id = client.post(
        "/api/roles", json={"name": "MatrixTest", "department_id": kd_id}, headers=_h(token)
    ).json()["id"]

    rows = client.get(f"/api/roles/{role_id}/permissions", headers=_h(token)).json()
    # One row per module; a brand-new role starts all-false / own.
    assert len(rows) >= 11
    assert all(not r["can_read"] and r["scope"] == "own" for r in rows)

    for row in rows:
        if row["module_key"] == "khach_hang":
            row["can_read"] = True
            row["can_update"] = True
            row["scope"] = "department"
    saved = client.put(
        f"/api/roles/{role_id}/permissions", json={"permissions": rows}, headers=_h(token)
    )
    assert saved.status_code == 200

    again = client.get(f"/api/roles/{role_id}/permissions", headers=_h(token)).json()
    kh = next(r for r in again if r["module_key"] == "khach_hang")
    assert kh["can_read"] and kh["can_update"] and kh["scope"] == "department"
    assert not kh["can_delete"]


def test_rename_role(client):
    token = _admin_token(client)
    kd_id = _kd_id()
    role_id = client.post(
        "/api/roles", json={"name": "RenameMe", "department_id": kd_id}, headers=_h(token)
    ).json()["id"]

    renamed = client.put(
        f"/api/roles/{role_id}", json={"name": "Renamed"}, headers=_h(token)
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Renamed"

    names = {r["name"] for r in client.get(f"/api/roles?department_id={kd_id}", headers=_h(token)).json()}
    assert "Renamed" in names and "RenameMe" not in names

    # Rename onto an existing name in the same department -> 409.
    clash = client.put(f"/api/roles/{role_id}", json={"name": "NV Sales"}, headers=_h(token))
    assert clash.status_code == 409


def test_delete_role_not_in_use(client):
    token = _admin_token(client)
    kd_id = _kd_id()
    role_id = client.post(
        "/api/roles", json={"name": "TempRole", "department_id": kd_id}, headers=_h(token)
    ).json()["id"]

    deleted = client.delete(f"/api/roles/{role_id}", headers=_h(token))
    assert deleted.status_code == 204

    ids = {r["id"] for r in client.get(f"/api/roles?department_id={kd_id}", headers=_h(token)).json()}
    assert role_id not in ids


def test_delete_role_in_use_is_blocked(client):
    token = _admin_token(client)
    kd_id = _kd_id()
    role_id = client.post(
        "/api/roles", json={"name": "BusyRole", "department_id": kd_id}, headers=_h(token)
    ).json()["id"]

    db = SessionLocal()
    try:
        users = UserRepository(db)
        user = users.create(
            username="busy", name="B", password_hash=hash_password("x")
        )
        users.set_assignment(user, department_id=kd_id, role_id=role_id, is_active=True)
    finally:
        db.close()

    blocked = client.delete(f"/api/roles/{role_id}", headers=_h(token))
    assert blocked.status_code == 409
    # Still present (not deleted).
    ids = {r["id"] for r in client.get(f"/api/roles?department_id={kd_id}", headers=_h(token)).json()}
    assert role_id in ids


def test_non_admin_forbidden(client):
    token = _sales_token()
    assert client.get("/api/rbac/modules", headers=_h(token)).status_code == 403
    assert (
        client.post(
            "/api/roles", json={"name": "X", "department_id": _kd_id()}, headers=_h(token)
        ).status_code
        == 403
    )
    # No phong_ban NOR vai_tro read → cannot even list role names.
    assert (
        client.get(f"/api/roles?department_id={_kd_id()}", headers=_h(token)).status_code
        == 403
    )


def _dept_viewer_token() -> str:
    """A user whose role grants ONLY phong_ban:read (no vai_tro permission) — the
    view-only employee looking at the department screen (spec-09)."""
    db = SessionLocal()
    try:
        users = UserRepository(db)
        existing = users.get_by_username("pb-viewer")
        if existing is not None:
            return create_access_token(str(existing.id))
        kd = DepartmentRepository(db).get_by_name("Kinh doanh")
        roles = RoleRepository(db)
        role = roles.create(name="PB Viewer", department_id=kd.id)
        roles.set_permission(
            role_id=role.id, module_key="phong_ban", can_read=True, scope="all"
        )
        u = users.create(username="pb-viewer", name="V", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=kd.id, role_id=role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def test_dept_viewer_can_list_role_names_but_not_matrix(client):
    """Role NAMES inside a department are part of viewing the department
    (phong_ban:read); the permission matrix stays behind vai_tro:read."""
    token = _dept_viewer_token()
    kd_id = _kd_id()

    listed = client.get(f"/api/roles?department_id={kd_id}", headers=_h(token))
    assert listed.status_code == 200
    roles = listed.json()
    assert {"NV Sales", "Trưởng phòng KD"} <= {r["name"] for r in roles}

    # …but the detailed permission matrix of any role stays forbidden.
    role_id = roles[0]["id"]
    assert (
        client.get(f"/api/roles/{role_id}/permissions", headers=_h(token)).status_code
        == 403
    )
