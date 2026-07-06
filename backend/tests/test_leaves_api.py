"""Nghỉ phép (module `nhan_su`): loại nghỉ (HR khai) + đơn nghỉ (workflow duyệt) +
tích hợp Bảng công tháng (ngày nghỉ đã duyệt hiện P/KL)."""
from __future__ import annotations

from datetime import date

from app.db import SessionLocal
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password

ADMIN = {"username": "admin", "password": "admin123"}


def _admin_token(client) -> str:
    return client.post("/api/auth/login", json=ADMIN).json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _uid(username: str) -> int:
    db = SessionLocal()
    try:
        return UserRepository(db).get_by_username(username).id
    finally:
        db.close()


def _dept_id(name: str) -> int:
    db = SessionLocal()
    try:
        return DepartmentRepository(db).get_by_name(name).id
    finally:
        db.close()


def _sales_token() -> str:
    db = SessionLocal()
    try:
        users = UserRepository(db)
        existing = users.get_by_username("sales-leave")
        if existing is not None:
            return create_access_token(str(existing.id))
        kd = DepartmentRepository(db).get_by_name("Kinh doanh")
        role = RoleRepository(db).get_by_name_and_department("NV Sales", kd.id)
        u = users.create(username="sales-leave", name="S", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=kd.id, role_id=role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def _make_type(client, token, *, name="Phép năm", is_paid=True) -> int:
    return client.post(
        "/api/leaves/types",
        json={"name": name, "is_paid": is_paid, "annual_quota": 12},
        headers=_h(token),
    ).json()["id"]


def _link_admin_employee(client, token) -> int:
    emp = client.post(
        "/api/employees",
        json={"full_name": "NV Nghỉ", "department_id": _dept_id("Hành chính nhân sự"), "hire_date": "2020-01-01"},
        headers=_h(token),
    ).json()["employee"]
    client.post(f"/api/employees/{emp['id']}/account", json={"user_id": _uid("admin")}, headers=_h(token))
    return emp["id"]


# --- leave types ------------------------------------------------------------


def test_leave_type_crud_and_rbac(client):
    token = _admin_token(client)
    tid = _make_type(client, token, name="Nghỉ ốm")
    assert tid > 0
    listed = client.get("/api/leaves/types", headers=_h(token)).json()["items"]
    assert any(t["id"] == tid for t in listed)
    # tên rỗng → 422 (schema)
    assert client.post("/api/leaves/types", json={"name": ""}, headers=_h(token)).status_code == 422

    # NV Sales không có quyền
    stoken = _sales_token()
    assert client.get("/api/leaves/types", headers=_h(stoken)).status_code == 403
    assert client.post("/api/leaves/types", json={"name": "x"}, headers=_h(stoken)).status_code == 403


# --- request workflow -------------------------------------------------------


def test_request_create_approve_and_state_machine(client):
    token = _admin_token(client)
    tid = _make_type(client, token)
    _link_admin_employee(client, token)

    me0 = client.get("/api/leaves/me", headers=_h(token)).json()
    assert me0["has_employee"] is True

    created = client.post(
        "/api/leaves",
        json={"leave_type_id": tid, "start_date": "2026-08-10", "end_date": "2026-08-12", "reason": "Về quê"},
        headers=_h(token),
    )
    assert created.status_code == 201
    r = created.json()
    assert r["status"] == "pending" and r["days"] == 3 and r["leave_type_name"] == "Phép năm"
    rid = r["id"]

    # HR thấy đơn kèm tên NV
    allr = client.get("/api/leaves", headers=_h(token)).json()["items"]
    assert any(x["id"] == rid and x["employee_name"] == "NV Nghỉ" for x in allr)

    # duyệt
    ap = client.post(f"/api/leaves/{rid}/approve", json={}, headers=_h(token))
    assert ap.status_code == 200 and ap.json()["status"] == "approved"
    # duyệt lại đơn không-chờ → 400
    assert client.post(f"/api/leaves/{rid}/approve", json={}, headers=_h(token)).status_code == 400


def test_reject_requires_note_and_cancel(client):
    token = _admin_token(client)
    tid = _make_type(client, token)
    _link_admin_employee(client, token)

    rid = client.post("/api/leaves", json={"leave_type_id": tid, "start_date": "2026-08-01", "end_date": "2026-08-01"}, headers=_h(token)).json()["id"]
    # từ chối thiếu lý do → 400
    assert client.post(f"/api/leaves/{rid}/reject", json={}, headers=_h(token)).status_code == 400
    ok = client.post(f"/api/leaves/{rid}/reject", json={"note": "Bận việc gấp"}, headers=_h(token))
    assert ok.status_code == 200 and ok.json()["status"] == "rejected"

    # đơn khác → tự hủy
    rid2 = client.post("/api/leaves", json={"leave_type_id": tid, "start_date": "2026-08-05", "end_date": "2026-08-05"}, headers=_h(token)).json()["id"]
    cx = client.post(f"/api/leaves/{rid2}/cancel", headers=_h(token))
    assert cx.status_code == 200 and cx.json()["status"] == "cancelled"


def test_start_after_end_rejected(client):
    token = _admin_token(client)
    tid = _make_type(client, token)
    _link_admin_employee(client, token)
    bad = client.post("/api/leaves", json={"leave_type_id": tid, "start_date": "2026-08-10", "end_date": "2026-08-05"}, headers=_h(token))
    assert bad.status_code == 400


# --- tích hợp Bảng công tháng ----------------------------------------------


def test_approved_leave_shows_on_timesheet(client):
    token = _admin_token(client)
    tid = _make_type(client, token, name="Phép năm", is_paid=True)
    _link_admin_employee(client, token)

    today = date.today()
    y, m = today.year, today.month
    start = date(y, m, 5).isoformat()
    end = date(y, m, 6).isoformat()
    rid = client.post("/api/leaves", json={"leave_type_id": tid, "start_date": start, "end_date": end}, headers=_h(token)).json()["id"]
    client.post(f"/api/leaves/{rid}/approve", json={}, headers=_h(token))

    ts = client.get(f"/api/attendance/timesheet?year={y}&month={m}", headers=_h(token)).json()
    row = next(r for r in ts["rows"] if r["employee_name"] == "NV Nghỉ")
    assert row["total_leave"] >= 2
    d5 = row["days"].get("5")
    assert d5 and d5["leave"] == "Phép năm" and d5["leave_paid"] is True and d5["cong"] == 1.0
