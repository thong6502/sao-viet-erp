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


def test_co_kcs_dat_va_giu_nguyen_khi_khong_gui(client):
    """Cờ tổ KCS (module Thực hiện SX §3.1): mặc định False; đặt True qua PUT; và KHÔNG gửi cờ khi
    sửa tên phải GIỮ NGUYÊN (như `la_kinh_doanh`) — ghi đè mặc định là âm thầm gỡ cờ KCS."""
    token = _admin_token(client)
    made = client.post("/api/departments", json={"name": "Tổ soi lỗi"}, headers=_h(token)).json()
    assert made["is_kcs"] is False, "mặc định không phải KCS"

    on = client.put(f"/api/departments/{made['id']}",
                    json={"name": "Tổ soi lỗi", "is_kcs": True}, headers=_h(token))
    assert on.status_code == 200 and on.json()["is_kcs"] is True, on.text

    # Sửa mỗi tên (không kèm is_kcs) ⇒ cờ KCS phải còn.
    kept = client.put(f"/api/departments/{made['id']}",
                      json={"name": "Tổ soi lỗi 2"}, headers=_h(token))
    assert kept.json()["is_kcs"] is True, "không gửi is_kcs = giữ nguyên, không được gỡ"


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

    # Create a person IN this department (hồ sơ + tài khoản), then set them as head -> ok.
    emp = client.post(
        "/api/employees",
        json={
            "full_name": "Người Đứng Đầu", "department_id": dept_id, "hire_date": "2024-01-15",
            "account": {"username": "head", "password": "password123"},
        },
        headers=_h(token),
    ).json()["employee"]
    uid = emp["user_id"]

    ok = client.put(
        f"/api/departments/{dept_id}",
        json={"name": "Phòng Head Test", "head_user_id": uid},
        headers=_h(token),
    )
    assert ok.status_code == 200
    assert ok.json()["head_user_id"] == uid

    # Danh sách nhân sự của phòng liệt kê theo HỒ SƠ (Đ2) — một dòng = một hồ sơ.
    members = client.get(f"/api/departments/{dept_id}/users", headers=_h(token)).json()
    me = next(m for m in members if m["employee_id"] == emp["id"])
    assert me["user_id"] == uid and me["is_head"] is True


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

    # A role + a person (hồ sơ + tài khoản) placed in the CHILD; they head the child.
    role = client.post(
        "/api/roles",
        json={"name": "Tổ trưởng", "department_id": child["id"]},
        headers=_h(token),
    ).json()
    emp = client.post(
        "/api/employees",
        json={
            "full_name": "Người A", "department_id": child["id"], "hire_date": "2024-01-15",
            "account": {"username": "khoia-1", "password": "password123", "role_id": role["id"]},
        },
        headers=_h(token),
    ).json()["employee"]
    uid = emp["user_id"]
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
    me = next(m for m in members if m["employee_id"] == emp["id"])
    assert me["role_name"] == "Tổ trưởng"
    assert me["is_active"] is True
    assert me["is_head"] is True


def test_members_list_includes_staff_without_account(client):
    """Đ2: danh sách nhân sự của phòng liệt kê theo HỒ SƠ → công nhân chưa có tài khoản VẪN
    hiện (bản cũ liệt kê theo tài khoản nên bỏ sót họ, khiến số 'Nhân sự' ở danh sách lệch
    với số người thấy trong chi tiết)."""
    token = _admin_token(client)
    did = client.post("/api/departments", json={"name": "Tổ Không TK"}, headers=_h(token)).json()["id"]
    emp = client.post(
        "/api/employees",
        json={"full_name": "Thợ Không TK", "department_id": did, "hire_date": "2024-01-01"},
        headers=_h(token),
    ).json()["employee"]

    members = client.get(f"/api/departments/{did}/users", headers=_h(token)).json()
    me = next(m for m in members if m["employee_id"] == emp["id"])
    assert me["user_id"] is None and me["username"] is None  # chưa có tài khoản
    assert me["name"] == "Thợ Không TK"


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
