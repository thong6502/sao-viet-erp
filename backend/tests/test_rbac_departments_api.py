"""feat-008 — Phòng ban admin API (delete semantics updated by spec-05 / feat-026).

Admin can list department summaries, create (with name dedup), rename, set a head
(must belong to the department), and delete (blocked only when the branch still has
PERSONNEL — roles cascade); a non-admin (NV Sales, no phong_ban permission) is forbidden.
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
    created = client.post(
        "/api/departments",
        json={"name": "Thiết kế", "description": "Phòng thiết kế"},
        headers=_h(token),
    )
    assert created.status_code == 201
    body = created.json()
    # spec-05: system-generated code (PB###) + description echoed back.
    assert body["code"].startswith("PB")
    assert body["description"] == "Phòng thiết kế"
    assert body["parent_id"] is None

    dup = client.post("/api/departments", json={"name": "Thiết kế"}, headers=_h(token))
    assert dup.status_code == 409

    empty = client.post("/api/departments", json={"name": ""}, headers=_h(token))
    assert empty.status_code == 422


def test_create_child_and_edit_description(client):
    """spec-05: create under a parent, then edit name + description (code unchanged)."""
    token = _admin_token(client)
    parent = client.post("/api/departments", json={"name": "Phòng cha"}, headers=_h(token)).json()
    child = client.post(
        "/api/departments",
        json={"name": "Phòng con", "parent_id": parent["id"]},
        headers=_h(token),
    ).json()
    assert child["parent_id"] == parent["id"]

    edited = client.put(
        f"/api/departments/{child['id']}",
        json={"name": "Phòng con đổi tên", "description": "mô tả mới"},
        headers=_h(token),
    )
    assert edited.status_code == 200
    body = edited.json()
    assert body["name"] == "Phòng con đổi tên"
    assert body["description"] == "mô tả mới"
    assert body["code"] == child["code"]  # code never changes on edit


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


def test_delete_department_blocked_by_personnel_then_ok(client):
    """spec-05 / PBI-4005: deletion is blocked only when the branch still has people;
    a department with roles but no users CAN be deleted (its roles cascade)."""
    token = _admin_token(client)

    # A department with a user in it -> blocked (409).
    with_people = client.post(
        "/api/departments", json={"name": "Phòng có người"}, headers=_h(token)
    ).json()
    db = SessionLocal()
    try:
        u = UserRepository(db).create(
            username="dept-member", name="M", password_hash=hash_password("x")
        )
        UserRepository(db).set_assignment(
            u, department_id=with_people["id"], role_id=None, is_active=True
        )
    finally:
        db.close()
    blocked = client.delete(f"/api/departments/{with_people['id']}", headers=_h(token))
    assert blocked.status_code == 409  # has personnel

    # "Kinh doanh" has roles but no users -> now deletable (roles cascade with it).
    db = SessionLocal()
    try:
        kd_id = DepartmentRepository(db).get_by_name("Kinh doanh").id
    finally:
        db.close()
    ok = client.delete(f"/api/departments/{kd_id}", headers=_h(token))
    assert ok.status_code == 204


def test_rolled_up_counts_and_member_detail(client):
    """spec-05 / PBI-4001: a parent's total_* counts aggregate its whole sub-tree, and the
    members endpoint carries role name + active status + head flag."""
    token = _admin_token(client)
    parent = client.post("/api/departments", json={"name": "Khối A"}, headers=_h(token)).json()
    child = client.post(
        "/api/departments",
        json={"name": "Khối A · Tổ 1", "parent_id": parent["id"]},
        headers=_h(token),
    ).json()

    # A role + a user placed in the CHILD; the user is the child's head.
    role = client.post(
        "/api/roles",
        json={"name": "Tổ trưởng", "department_id": child["id"]},
        headers=_h(token),
    ).json()
    db = SessionLocal()
    try:
        users = UserRepository(db)
        u = users.create(username="khoia-1", name="Người A", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=child["id"], role_id=role["id"], is_active=True)
        uid = u.id
    finally:
        db.close()
    client.put(
        f"/api/departments/{child['id']}",
        json={"name": child["name"], "head_user_id": uid},
        headers=_h(token),
    )

    listing = client.get("/api/departments", headers=_h(token)).json()
    p = next(d for d in listing if d["id"] == parent["id"])
    c = next(d for d in listing if d["id"] == child["id"])
    # Parent owns nothing but rolls up the child's 1 user + 1 role.
    assert p["user_count"] == 0 and p["role_count"] == 0
    assert p["total_user_count"] == 1 and p["total_role_count"] == 1
    # The leaf child's own counts equal its totals.
    assert c["user_count"] == 1 and c["total_user_count"] == 1

    members = client.get(f"/api/departments/{child['id']}/users", headers=_h(token)).json()
    me = next(m for m in members if m["id"] == uid)
    assert me["role_name"] == "Tổ trưởng"
    assert me["is_active"] is True
    assert me["is_head"] is True


def test_non_admin_forbidden(client):
    token = _sales_token()
    assert client.post("/api/departments", json={"name": "X"}, headers=_h(token)).status_code == 403
    assert client.get("/api/departments", headers=_h(token)).status_code == 403


def test_employee_count_and_delete_blocked_by_employees(client):
    """Đ2: 'số nhân sự' đếm theo HỒ SƠ (tách khỏi tài khoản); xóa phòng còn hồ sơ — kể cả khi
    phòng KHÔNG có tài khoản nào — bị chặn (không để employees.department_id mồ côi)."""
    token = _admin_token(client)
    did = client.post("/api/departments", json={"name": "Tổ Test EC"}, headers=_h(token)).json()["id"]
    # 1 hồ sơ nhân sự thuộc phòng, KHÔNG tạo tài khoản
    r = client.post(
        "/api/employees",
        json={"full_name": "NV EC", "department_id": did, "hire_date": "2024-01-01"},
        headers=_h(token),
    )
    assert r.status_code == 201
    row = next(x for x in client.get("/api/departments", headers=_h(token)).json() if x["id"] == did)
    assert row["employee_count"] == 1   # đếm theo hồ sơ
    assert row["user_count"] == 0       # phòng không có tài khoản
    # xóa phòng còn hồ sơ (dù 0 tài khoản) → chặn theo hồ-sơ ∪ tài-khoản
    assert client.delete(f"/api/departments/{did}", headers=_h(token)).status_code >= 400
