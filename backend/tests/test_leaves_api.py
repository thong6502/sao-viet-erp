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


def _role_id(name: str, department_id: int) -> int:
    db = SessionLocal()
    try:
        return RoleRepository(db).get_by_name_and_department(name, department_id).id
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
    """Hồ sơ của admin (mọi tài khoản đều có hồ sơ — xem `backfill_employee_profiles`): nắn lại
    tên/phòng ban, KHÔNG tạo hồ sơ thứ 2 (link tài khoản 1–1).

    `hire_date` = 2020-01-01 phải set thẳng ở DB: nó KHÔNG nằm trong `EDITABLE_FIELDS` (ngày vào
    làm là dữ liệu cứng), mà quota phép năm pro-rate theo tháng-vào → hồ sơ backfill có
    hire_date=hôm-nay sẽ méo hạn mức. Đặt về đầu 2020 cho quota đầy đủ như kịch bản test."""
    me = client.get("/api/employees/me", headers=_h(token)).json()
    eid = me["employee"]["id"]
    client.put(
        f"/api/employees/{eid}",
        json={"full_name": "NV Nghỉ", "department_id": _dept_id("Hành chính nhân sự")},
        headers=_h(token),
    )
    _set_hire_date(eid, date(2020, 1, 1))
    return eid


def _set_hire_date(employee_id: int, hire_date: date) -> None:
    from app.models.employee import Employee
    db = SessionLocal()
    try:
        emp = db.get(Employee, employee_id)
        if emp is not None:
            emp.hire_date = hire_date
            db.commit()
    finally:
        db.close()


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
    """Nghỉ rơi trúng ngày nghỉ tuần (Chủ Nhật) → không có ngày làm việc → 400.
    Tuần chuẩn T2–T7 (Thứ 7 LÀ ngày làm), nên chỉ Chủ Nhật là ngày nghỉ."""
    token = _admin_token(client)
    tid = _make_type(client, token)
    _link_admin_employee(client, token)
    # 2026-08-02 là Chủ Nhật (ngày nghỉ tuần duy nhất).
    bad = client.post("/api/leaves", json={"leave_type_id": tid, "start_date": "2026-08-02", "end_date": "2026-08-02"}, headers=_h(token))
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

    # 8–9/9/2026 = T3–T4, hai ngày làm việc liên tiếp (không rơi CN/lễ nên không bị B2 lọc).
    y, m = 2026, 9
    start = date(y, m, 8).isoformat()
    end = date(y, m, 9).isoformat()
    rid = client.post("/api/leaves", json={"leave_type_id": tid, "start_date": start, "end_date": end}, headers=_h(token)).json()["id"]
    client.post(f"/api/leaves/{rid}/approve", json={}, headers=_h(token))

    ts = client.get(f"/api/attendance/timesheet?year={y}&month={m}", headers=_h(token)).json()
    row = next(r for r in ts["rows"] if r["employee_name"] == "NV Nghỉ")
    assert row["total_leave"] >= 2
    d8 = row["days"].get("8")
    assert d8 and d8["leave"] == "Phép năm" and d8["leave_paid"] is True and d8["cong"] == 1.0


def test_paid_holiday_beats_leave_on_timesheet(client):
    """Ngày lễ hưởng lương nằm TRONG đơn phép có lương: hiện là công LỄ (holiday), 1 công,
    KHÔNG tiêu ngày phép (chỉ các ngày làm việc khác trong đơn mới tính phép)."""
    token = _admin_token(client)
    tid = _make_type(client, token, name="Phép năm", is_paid=True)
    _link_admin_employee(client, token)

    # Đơn 1–3/9/2026 phủ lễ 2/9 (Quốc khánh, seed). 1=T3, 2=T4(lễ), 3=T5.
    rid = client.post("/api/leaves", json={"leave_type_id": tid,
        "start_date": "2026-09-01", "end_date": "2026-09-03"}, headers=_h(token)).json()["id"]
    client.post(f"/api/leaves/{rid}/approve", json={}, headers=_h(token))

    ts = client.get("/api/attendance/timesheet?year=2026&month=9", headers=_h(token)).json()
    row = next(r for r in ts["rows"] if r["employee_name"] == "NV Nghỉ")
    assert row["days"]["2"]["holiday"] is True and row["days"]["2"]["cong"] == 1.0
    assert row["total_leave"] == 2  # 1/9 + 3/9; 2/9 là lễ, không tính vào phép
    assert row["days"]["1"]["leave"] == "Phép năm" and row["days"]["3"]["leave"] == "Phép năm"


def test_unpaid_leave_over_holiday_gets_no_pay(client):
    """Nghỉ KHÔNG lương phủ ngày lễ: ngày lễ vẫn hiện holiday nhưng 0 công (đang trong kỳ không
    lương, công ty không trả lương lễ — đúng luật). Vẫn không tiêu ngày phép."""
    token = _admin_token(client)
    unpaid_tid = client.post("/api/leaves/types",
        json={"name": "Không lương", "is_paid": False, "annual_quota": 0},
        headers=_h(token)).json()["id"]
    _link_admin_employee(client, token)

    rid = client.post("/api/leaves", json={"leave_type_id": unpaid_tid,
        "start_date": "2026-09-01", "end_date": "2026-09-03"}, headers=_h(token)).json()["id"]
    client.post(f"/api/leaves/{rid}/approve", json={}, headers=_h(token))

    ts = client.get("/api/attendance/timesheet?year=2026&month=9", headers=_h(token)).json()
    row = next(r for r in ts["rows"] if r["employee_name"] == "NV Nghỉ")
    assert row["days"]["2"]["holiday"] is True and row["days"]["2"]["cong"] == 0.0
    assert row["total_leave"] == 2  # 1/9 + 3/9 (không lương); 2/9 là lễ, không tính phép


def test_sunday_in_leave_not_counted_on_timesheet(client):
    """Đơn phép phủ Chủ Nhật: bảng công KHÔNG đánh dấu phép ngày CN (khớp số ngày trừ quota)."""
    token = _admin_token(client)
    tid = _make_type(client, token, name="Phép năm", is_paid=True)
    _link_admin_employee(client, token)

    # 5–7/9/2026: T7(5) làm, CN(6) nghỉ, T2(7) làm → chỉ 5 và 7 tính phép.
    rid = client.post("/api/leaves", json={"leave_type_id": tid,
        "start_date": "2026-09-05", "end_date": "2026-09-07"}, headers=_h(token)).json()["id"]
    client.post(f"/api/leaves/{rid}/approve", json={}, headers=_h(token))

    ts = client.get("/api/attendance/timesheet?year=2026&month=9", headers=_h(token)).json()
    row = next(r for r in ts["rows"] if r["employee_name"] == "NV Nghỉ")
    assert row["total_leave"] == 2       # 5(T7) + 7(T2), KHÔNG tính 6(CN)
    assert "6" not in row["days"]        # Chủ Nhật không có ô phép
    assert row["days"]["5"]["leave"] == "Phép năm" and row["days"]["7"]["leave"] == "Phép năm"


def test_quota_prorated_for_mid_year_hire(client):
    """Người mới vào giữa năm: hạn mức phép chia tỷ lệ tháng còn lại (Điều 113 BLLĐ)."""
    token = _admin_token(client)
    tid = _make_type(client, token, name="Phép năm", is_paid=True)  # quota 12
    y = date.today().year
    dept_id = _dept_id("Hành chính nhân sự")
    role_id = _role_id("Nhân viên", dept_id)
    emp = client.post("/api/employees",
        json={
            "full_name": "NV Mới",
            "department_id": dept_id,
            "hire_date": f"{y}-07-01",
            "account": {
                "username": "nv-moi-phep",
                "password": "secret1",
                "role_id": role_id,
            },
        },
        headers=_h(token),
    ).json()["employee"]
    employee_token = client.post(
        "/api/auth/login",
        json={"username": "nv-moi-phep", "password": "secret1"},
    ).json()["access_token"]

    me = client.get("/api/leaves/me", headers=_h(employee_token)).json()
    q = next(q for q in me["quotas"] if q["name"] == "Phép năm")
    assert q["annual_quota"] == 6 and q["remaining"] == 6  # 12 × 6 tháng (7..12) / 12

    # Đơn dài (>6 ngày làm việc) → chặn vì vượt hạn mức đã prorate.
    r = client.post("/api/leaves", json={"leave_type_id": tid,
        "start_date": f"{y}-11-02", "end_date": f"{y}-11-16"}, headers=_h(employee_token))
    assert r.status_code == 400 and "Vượt hạn mức" in r.json()["detail"]
