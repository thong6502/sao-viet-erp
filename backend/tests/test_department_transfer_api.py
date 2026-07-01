"""spec-06 / PBI-4008 — bulk transfer of personnel between departments.

Moving people drops their old role (role_id=None), clears the head of the old unit if a
moved user headed it, writes one audit row per person, and is gated on `nguoi_dung` update.
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


def _sales_token() -> str:
    db = SessionLocal()
    try:
        users = UserRepository(db)
        existing = users.get_by_username("sales-xfer")
        if existing is not None:
            return create_access_token(str(existing.id))
        kd = DepartmentRepository(db).get_by_name("Kinh doanh")
        sales_role = RoleRepository(db).get_by_name_and_department("NV Sales", kd.id)
        u = users.create(username="sales-xfer", name="S", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=kd.id, role_id=sales_role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def _make_user(username: str, dept_id: int, role_id: int | None) -> int:
    db = SessionLocal()
    try:
        users = UserRepository(db)
        u = users.create(username=username, name=username, password_hash=hash_password("x"))
        users.set_assignment(u, department_id=dept_id, role_id=role_id, is_active=True)
        return u.id
    finally:
        db.close()


def test_bulk_transfer_moves_drops_role_clears_head_and_audits(client):
    token = _admin_token(client)
    source = client.post("/api/departments", json={"name": "Nguồn"}, headers=_h(token)).json()
    target = client.post("/api/departments", json={"name": "Đích"}, headers=_h(token)).json()
    role = client.post(
        "/api/roles", json={"name": "NV Nguồn", "department_id": source["id"]}, headers=_h(token)
    ).json()

    u1 = _make_user("xfer-1", source["id"], role["id"])
    u2 = _make_user("xfer-2", source["id"], role["id"])
    # u1 heads the source department.
    client.put(
        f"/api/departments/{source['id']}",
        json={"name": source["name"], "head_user_id": u1},
        headers=_h(token),
    )

    resp = client.post(
        "/api/departments/transfer",
        json={"user_ids": [u1, u2], "target_department_id": target["id"]},
        headers=_h(token),
    )
    assert resp.status_code == 200
    assert resp.json()["transferred"] == 2

    # Both users now belong to the target with no role.
    users = client.get("/api/users", headers=_h(token)).json()
    for uid in (u1, u2):
        row = next(r for r in users if r["id"] == uid)
        assert row["department_id"] == target["id"]
        assert row["role_id"] is None

    # The source department's head was cleared (its head moved away).
    depts = client.get("/api/departments", headers=_h(token)).json()
    src = next(d for d in depts if d["id"] == source["id"])
    assert src["head_user_id"] is None

    # One audit row per moved person.
    audit = client.get("/api/audit", headers=_h(token)).json()
    moved = [a for a in audit if a["action"] == "transfer_user"]
    assert len({a["target"] for a in moved}) >= 2


def test_transfer_validation(client):
    token = _admin_token(client)
    target = client.post("/api/departments", json={"name": "Đích 2"}, headers=_h(token)).json()

    # Empty selection -> 422 (schema min_length).
    empty = client.post(
        "/api/departments/transfer",
        json={"user_ids": [], "target_department_id": target["id"]},
        headers=_h(token),
    )
    assert empty.status_code == 422

    # Unknown target -> 404.
    bad_target = client.post(
        "/api/departments/transfer",
        json={"user_ids": [1], "target_department_id": 999999},
        headers=_h(token),
    )
    assert bad_target.status_code == 404


def test_transfer_forbidden_without_permission(client):
    token = _sales_token()
    resp = client.post(
        "/api/departments/transfer",
        json={"user_ids": [1], "target_department_id": 1},
        headers=_h(token),
    )
    assert resp.status_code == 403
