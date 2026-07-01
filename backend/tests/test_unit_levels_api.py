"""spec-06 — Unit-level catalog (PBI-4009) + head-by-subtree (PBI-4004).

Admin declares org tiers (name + unique rank + head title), tags a department with a
level (its head-title label surfaces on the department summary), and cannot delete a
level still in use. Heads may now be chosen from the unit's whole subtree. A non-admin
without `phong_ban` permission is forbidden.
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
        existing = users.get_by_username("sales-lvl")
        if existing is not None:
            return create_access_token(str(existing.id))
        kd = DepartmentRepository(db).get_by_name("Kinh doanh")
        sales_role = RoleRepository(db).get_by_name_and_department("NV Sales", kd.id)
        user = users.create(username="sales-lvl", name="S", password_hash=hash_password("x"))
        users.set_assignment(user, department_id=kd.id, role_id=sales_role.id, is_active=True)
        return create_access_token(str(user.id))
    finally:
        db.close()


def test_default_levels_seeded(client):
    levels = client.get("/api/unit-levels", headers=_h(_admin_token(client))).json()
    names = {lv["name"] for lv in levels}
    assert {"Khối", "Phòng", "Tổ"} <= names
    # Ordered high→low by rank.
    ranks = [lv["rank"] for lv in levels]
    assert ranks == sorted(ranks)


def test_create_level_dedup_name_and_rank(client):
    token = _admin_token(client)
    created = client.post(
        "/api/unit-levels",
        json={"name": "Ban", "rank": 90, "head_title": "Trưởng ban"},
        headers=_h(token),
    )
    assert created.status_code == 201
    assert created.json()["head_title"] == "Trưởng ban"

    dup_name = client.post(
        "/api/unit-levels", json={"name": "Ban", "rank": 91, "head_title": "x"}, headers=_h(token)
    )
    assert dup_name.status_code == 409

    dup_rank = client.post(
        "/api/unit-levels", json={"name": "Ban khác", "rank": 90, "head_title": "x"}, headers=_h(token)
    )
    assert dup_rank.status_code == 409


def test_update_level(client):
    token = _admin_token(client)
    lv = client.post(
        "/api/unit-levels", json={"name": "Cụm", "rank": 80, "head_title": "Cụm trưởng"}, headers=_h(token)
    ).json()
    edited = client.put(
        f"/api/unit-levels/{lv['id']}",
        json={"name": "Cụm SX", "rank": 80, "head_title": "Trưởng cụm"},
        headers=_h(token),
    )
    assert edited.status_code == 200
    assert edited.json()["name"] == "Cụm SX"
    assert edited.json()["head_title"] == "Trưởng cụm"


def test_tag_department_with_level_surfaces_head_title(client):
    token = _admin_token(client)
    lv = client.post(
        "/api/unit-levels", json={"name": "Chi nhánh", "rank": 70, "head_title": "Giám đốc CN"}, headers=_h(token)
    ).json()
    dept = client.post(
        "/api/departments", json={"name": "CN Hà Nội", "level_id": lv["id"]}, headers=_h(token)
    ).json()
    assert dept["level_id"] == lv["id"]
    assert dept["head_title"] == "Giám đốc CN"

    # It also shows up in the list summary.
    listing = client.get("/api/departments", headers=_h(token)).json()
    row = next(d for d in listing if d["id"] == dept["id"])
    assert row["head_title"] == "Giám đốc CN"


def test_delete_level_blocked_when_in_use(client):
    token = _admin_token(client)
    lv = client.post(
        "/api/unit-levels", json={"name": "Đội", "rank": 60, "head_title": "Đội trưởng"}, headers=_h(token)
    ).json()
    client.post("/api/departments", json={"name": "Đội 1", "level_id": lv["id"]}, headers=_h(token))

    blocked = client.delete(f"/api/unit-levels/{lv['id']}", headers=_h(token))
    assert blocked.status_code == 409

    # A brand-new unused level deletes fine.
    unused = client.post(
        "/api/unit-levels", json={"name": "Nhóm", "rank": 61, "head_title": "Nhóm trưởng"}, headers=_h(token)
    ).json()
    assert client.delete(f"/api/unit-levels/{unused['id']}", headers=_h(token)).status_code == 204


def test_head_candidates_span_subtree_and_can_be_set(client):
    """PBI-4004: a parent unit's head may be a person from a CHILD unit."""
    token = _admin_token(client)
    parent = client.post("/api/departments", json={"name": "Khối KT"}, headers=_h(token)).json()
    child = client.post(
        "/api/departments", json={"name": "Phòng KT · Tổ 1", "parent_id": parent["id"]}, headers=_h(token)
    ).json()

    db = SessionLocal()
    try:
        users = UserRepository(db)
        u = users.create(username="kt-1", name="KT Một", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=child["id"], role_id=None, is_active=True)
        uid = u.id
    finally:
        db.close()

    cands = client.get(f"/api/departments/{parent['id']}/head-candidates", headers=_h(token)).json()
    assert any(c["id"] == uid for c in cands)

    ok = client.put(
        f"/api/departments/{parent['id']}",
        json={"name": parent["name"], "head_user_id": uid},
        headers=_h(token),
    )
    assert ok.status_code == 200
    assert ok.json()["head_user_id"] == uid


def test_non_admin_forbidden(client):
    token = _sales_token()
    assert client.get("/api/unit-levels", headers=_h(token)).status_code == 403
    assert client.post(
        "/api/unit-levels", json={"name": "Z", "rank": 999, "head_title": "z"}, headers=_h(token)
    ).status_code == 403
