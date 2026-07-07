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

    # NV Sales (self-service): ĐỌC được loại nghỉ (đổ dropdown tạo đơn) nhưng KHÔNG quản (tạo).
    stoken = _sales_token()
    assert client.get("/api/leaves/types", headers=_h(stoken)).status_code == 200
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

    # Thứ Hai 2026-08-03 (ngày làm việc — tránh cuối tuần bị chặn).
    rid = client.post("/api/leaves", json={"leave_type_id": tid, "start_date": "2026-08-03", "end_date": "2026-08-03"}, headers=_h(token)).json()["id"]
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


def test_weekend_only_request_rejected(client):
    """Khoảng nghỉ rơi hết vào cuối tuần (không ngày làm việc) → 400."""
    token = _admin_token(client)
    tid = _make_type(client, token)
    _link_admin_employee(client, token)
    # 2026-08-01 T7, 2026-08-02 CN.
    bad = client.post("/api/leaves", json={"leave_type_id": tid, "start_date": "2026-08-01", "end_date": "2026-08-02"}, headers=_h(token))
    assert bad.status_code == 400


def test_quota_block_when_exceeding(client):
    """Hạn mức phép năm chặn theo NGÀY LÀM VIỆC (loại T7/CN), reset dương lịch."""
    token = _admin_token(client)
    tid = client.post(
        "/api/leaves/types",
        json={"name": "Phép ít", "is_paid": True, "annual_quota": 2},
        headers=_h(token),
    ).json()["id"]
    _link_admin_employee(client, token)
    # Thứ Hai→Thứ Tư 2026-08-03..05 = 3 ngày làm việc > hạn mức 2 → 400.
    bad = client.post("/api/leaves", json={"leave_type_id": tid, "start_date": "2026-08-03", "end_date": "2026-08-05"}, headers=_h(token))
    assert bad.status_code == 400
    # Thứ Hai→Thứ Ba 2026-08-10..11 = 2 ngày = hạn mức → 201.
    ok = client.post("/api/leaves", json={"leave_type_id": tid, "start_date": "2026-08-10", "end_date": "2026-08-11"}, headers=_h(token))
    assert ok.status_code == 201
    # Còn lại 0 → thêm 1 ngày làm việc nữa (Thứ Tư 2026-08-12) phải bị chặn.
    more = client.post("/api/leaves", json={"leave_type_id": tid, "start_date": "2026-08-12", "end_date": "2026-08-12"}, headers=_h(token))
    assert more.status_code == 400
    # /me phản ánh hạn mức: đã dùng 2 / còn 0.
    me = client.get("/api/leaves/me", headers=_h(token)).json()
    q = next(x for x in me["quotas"] if x["leave_type_id"] == tid)
    assert q["used"] == 2 and q["remaining"] == 0


def test_bulk_approve_and_reject(client):
    """Duyệt/từ chối hàng loạt: bỏ qua đơn không-chờ; từ chối bulk bắt lý do."""
    token = _admin_token(client)
    tid = _make_type(client, token, name="Nghỉ ốm")  # quota 12 nhưng ốm ít ngày → không chạm hạn mức
    _link_admin_employee(client, token)
    mk = lambda s, e: client.post("/api/leaves", json={"leave_type_id": tid, "start_date": s, "end_date": e}, headers=_h(token)).json()["id"]
    a, b = mk("2026-09-07", "2026-09-07"), mk("2026-09-08", "2026-09-08")  # T2, T3
    res = client.post("/api/leaves/bulk-approve", json={"ids": [a, b]}, headers=_h(token)).json()
    assert set(res["done"]) == {a, b} and res["skipped"] == []
    # duyệt lại (đã duyệt) → skip, không vỡ
    assert client.post("/api/leaves/bulk-approve", json={"ids": [a, b]}, headers=_h(token)).json()["skipped"] == [a, b]
    c = mk("2026-09-09", "2026-09-09")
    assert client.post("/api/leaves/bulk-reject", json={"ids": [c]}, headers=_h(token)).status_code == 422  # thiếu note
    rej = client.post("/api/leaves/bulk-reject", json={"ids": [c], "note": "Thiếu người trực"}, headers=_h(token)).json()
    assert rej["done"] == [c]


def test_bell_unseen_and_mark_seen(client):
    """Chuông Topbar: đơn được quyết → my_decided_unseen tăng; mark-seen → về 0."""
    token = _admin_token(client)
    tid = _make_type(client, token)
    _link_admin_employee(client, token)
    rid = client.post("/api/leaves", json={"leave_type_id": tid, "start_date": "2026-08-10", "end_date": "2026-08-11"}, headers=_h(token)).json()["id"]
    assert client.get("/api/leaves/summary", headers=_h(token)).json()["my_decided_unseen"] == 0  # còn pending
    client.post(f"/api/leaves/{rid}/approve", json={}, headers=_h(token))
    assert client.get("/api/leaves/summary", headers=_h(token)).json()["my_decided_unseen"] == 1  # đã quyết, chưa xem
    assert client.post("/api/leaves/mark-seen", headers=_h(token)).status_code == 204
    assert client.get("/api/leaves/summary", headers=_h(token)).json()["my_decided_unseen"] == 0  # đã xem


def test_calendar_shows_approved_and_pending(client):
    token = _admin_token(client)
    tid = _make_type(client, token)
    _link_admin_employee(client, token)
    rid = client.post("/api/leaves", json={"leave_type_id": tid, "start_date": "2026-09-07", "end_date": "2026-09-09"}, headers=_h(token)).json()["id"]
    client.post(f"/api/leaves/{rid}/approve", json={}, headers=_h(token))
    # thêm 1 đơn CHỜ để lịch có cả amber
    client.post("/api/leaves", json={"leave_type_id": tid, "start_date": "2026-09-14", "end_date": "2026-09-14"}, headers=_h(token))
    cal = client.get("/api/leaves/calendar?year=2026&month=9", headers=_h(token)).json()
    assert cal["days_in_month"] == 30
    emp = next(e for e in cal["employees"] if e["employee_name"] == "NV Nghỉ")
    assert emp["days"]["7"]["status"] == "approved" and emp["days"]["9"]["status"] == "approved"
    assert emp["days"]["14"]["status"] == "pending"
    # NV Sales (không quyền duyệt) → 403
    assert client.get("/api/leaves/calendar?year=2026&month=9", headers=_h(_sales_token())).status_code == 403


def test_summary_badge_gating_and_scope(client):
    """Badge = số đơn chờ trong scope; None nếu không có quyền duyệt; NV thấy theo scope own."""
    token = _admin_token(client)
    tid = _make_type(client, token)
    _link_admin_employee(client, token)
    # Thứ Hai 2026-08-17.
    client.post("/api/leaves", json={"leave_type_id": tid, "start_date": "2026-08-17", "end_date": "2026-08-17"}, headers=_h(token))
    # Admin (có approve, scope all) → con số.
    s = client.get("/api/leaves/summary", headers=_h(token)).json()
    assert isinstance(s["pending_in_scope"], int) and s["pending_in_scope"] >= 1
    # NV Sales (không có approve) → None (ẩn badge, chống lộ số).
    stoken = _sales_token()
    assert client.get("/api/leaves/summary", headers=_h(stoken)).json()["pending_in_scope"] is None
    # NV Sales scope own (không hồ sơ NV) → danh sách rỗng, không thấy đơn người khác.
    assert client.get("/api/leaves", headers=_h(stoken)).json()["items"] == []


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
