"""Ca kíp (module `nhan_su`, lát Chấm công): khai ca + tính CÔNG theo tỷ lệ giờ làm.

- Unit test công thức `compute_day_cong` (đủ giờ = 1,00; đi muộn/về sớm giảm theo tỷ lệ, giữ
  2 chữ số; dung sai; OT tính riêng; thiếu chấm ra = 0).
- API: CRUD ca + validation + RBAC + gán ca mặc định cho NV + timesheet có công theo ca.
"""
from __future__ import annotations

from datetime import date, datetime

from app.db import SessionLocal
from app.repositories.employee_repo import EmployeeRepository
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password
from app.services.attendance_service import VN_TZ, check_in_block_reason, compute_day_cong

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
        existing = users.get_by_username("sales-shift")
        if existing is not None:
            return create_access_token(str(existing.id))
        kd = DepartmentRepository(db).get_by_name("Kinh doanh")
        role = RoleRepository(db).get_by_name_and_department("NV Sales", kd.id)
        u = users.create(username="sales-shift", name="S", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=kd.id, role_id=role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


# --- công formula (pure) — ca Hành chính 8:00–17:00 (window 540'), grace 5' -----


def _cong(first_in_min, last_out_min):
    return compute_day_cong(
        start_min=8 * 60, end_min=17 * 60, is_overnight=False, grace_min=5,
        first_in_min=first_in_min, last_out_min=last_out_min,
    )


def test_compute_day_cong_examples():
    # Đúng đủ → 1,00
    r = _cong(8 * 60, 17 * 60)
    assert r["cong"] == 1.0 and not r["late"] and not r["early"] and r["ot_minutes"] == 0
    # Đi muộn 30' → 0,94
    r = _cong(8 * 60 + 30, 17 * 60)
    assert r["cong"] == 0.94 and r["late"] is True
    # Về sớm 1h → 0,89
    r = _cong(8 * 60, 16 * 60)
    assert r["cong"] == 0.89 and r["early"] is True
    # Đi muộn 2h → 0,78
    r = _cong(10 * 60, 17 * 60)
    assert r["cong"] == 0.78
    # Trong dung sai (muộn 4') → vẫn 1,00, không tính đi muộn
    r = _cong(8 * 60 + 4, 17 * 60)
    assert r["cong"] == 1.0 and r["late"] is False
    # Ra muộn 1h → công vẫn tối đa 1,00 nhưng OT = 60'
    r = _cong(8 * 60, 18 * 60)
    assert r["cong"] == 1.0 and r["ot_minutes"] == 60
    # Thiếu chấm ra → 0 công, đánh dấu incomplete
    r = _cong(8 * 60, None)
    assert r["cong"] == 0.0 and r["incomplete"] is True


def test_check_in_window_blocks_morning_for_evening_shift():
    shift = type("Shift", (), {
        "name": "Ca tối", "start_minute": 18 * 60, "end_minute": 23 * 60,
        "is_overnight": False,
    })()
    work_day = date(2026, 7, 21)

    too_early = check_in_block_reason(
        shift=shift, work_day=work_day,
        now_local=datetime(2026, 7, 21, 7, 0, tzinfo=VN_TZ),
    )
    assert too_early is not None and "17:00" in too_early
    assert check_in_block_reason(
        shift=shift, work_day=work_day,
        now_local=datetime(2026, 7, 21, 17, 0, tzinfo=VN_TZ),
    ) is None
    ended = check_in_block_reason(
        shift=shift, work_day=work_day,
        now_local=datetime(2026, 7, 21, 23, 0, tzinfo=VN_TZ),
    )
    assert ended is not None and "đã kết thúc" in ended


def test_compute_day_cong_overnight():
    """Ca đêm 22:00→06:00: giờ RA rạng sáng ánh xạ lên trục ca (theo ngày VÀO)."""
    def night(fin, fout):
        return compute_day_cong(start_min=22 * 60, end_min=6 * 60, is_overnight=True, grace_min=5,
                                first_in_min=fin, last_out_min=fout)
    # VÀO 22:00, RA 06:00 → đủ ca = 1,00
    r = night(22 * 60, 6 * 60)
    assert r["cong"] == 1.0 and not r["late"] and not r["early"] and not r["incomplete"]
    # vào trễ 30' (22:30) → 0,94
    r = night(22 * 60 + 30, 6 * 60)
    assert r["cong"] == 0.94 and r["late"] is True
    # về sớm (RA 05:00) → early, công < 1,00
    r = night(22 * 60, 5 * 60)
    assert r["early"] is True and 0 < r["cong"] < 1.0
    # thiếu chấm RA → 0 công, incomplete
    r = night(22 * 60, None)
    assert r["cong"] == 0.0 and r["incomplete"] is True


# --- shift CRUD + validation + RBAC -----------------------------------------


def test_shift_crud_and_validation(client):
    token = _admin_token(client)
    created = client.post(
        "/api/attendance/shifts",
        json={"name": "Hành chính", "start_time": "08:00", "end_time": "17:00", "grace_minutes": 5},
        headers=_h(token),
    )
    assert created.status_code == 201
    sid = created.json()["id"]
    assert created.json()["start_time"] == "08:00" and created.json()["end_time"] == "17:00"

    compact = client.post(
        "/api/attendance/shifts",
        json={"name": "Ca nhập nhanh", "start_time": "7", "end_time": "1200"},
        headers=_h(token),
    )
    assert compact.status_code == 201
    assert compact.json()["start_time"] == "07:00"
    assert compact.json()["end_time"] == "12:00"

    listed = client.get("/api/attendance/shifts", headers=_h(token)).json()["items"]
    assert any(s["id"] == sid for s in listed)

    # end ≤ start mà không phải ca đêm → 400
    bad = client.post(
        "/api/attendance/shifts",
        json={"name": "x", "start_time": "17:00", "end_time": "08:00"},
        headers=_h(token),
    )
    assert bad.status_code == 400
    invalid_time = client.post(
        "/api/attendance/shifts",
        json={"name": "x", "start_time": "1260", "end_time": "17"},
        headers=_h(token),
    )
    assert invalid_time.status_code == 400
    # ca qua đêm thì chấp nhận end < start
    night = client.post(
        "/api/attendance/shifts",
        json={"name": "Ca 3", "start_time": "1900", "end_time": "0", "is_overnight": True},
        headers=_h(token),
    )
    assert night.status_code == 201
    assert night.json()["is_overnight"] is True
    assert "night_shift" not in night.json()  # cờ ca đêm đã gỡ hẳn
    assert night.json()["start_time"] == "19:00" and night.json()["end_time"] == "00:00"

    upd = client.put(
        f"/api/attendance/shifts/{sid}",
        json={"name": "Hành chính (sửa)", "start_time": "08:30", "end_time": "17:30"},
        headers=_h(token),
    )
    assert upd.status_code == 200 and upd.json()["start_time"] == "08:30"

    assert client.delete(f"/api/attendance/shifts/{sid}", headers=_h(token)).status_code == 204


def test_shift_meal_shift_allowance_roundtrip(client):
    """Phụ cấp cơm/ca khai theo CA: mặc định 25k/50k, tạo có khai thì lưu + đọc lại đúng,
    sửa được. Đợt 1 CHỈ lưu/phơi — engine `_compute` CHƯA cộng (nối ở Đợt 2)."""
    token = _admin_token(client)
    # Không khai → nhận mặc định 25k/50k.
    d = client.post(
        "/api/attendance/shifts",
        json={"name": "Ca mặc định PC", "start_time": "08:00", "end_time": "17:00"},
        headers=_h(token),
    ).json()
    assert d["meal_allowance"] == 25000 and d["shift_allowance"] == 50000

    # Khai tay lúc tạo → lưu đúng số.
    created = client.post(
        "/api/attendance/shifts",
        json={"name": "Ca tối PC", "start_time": "18:00", "end_time": "22:00",
              "meal_allowance": 30000, "shift_allowance": 70000},
        headers=_h(token),
    )
    assert created.status_code == 201
    sid = created.json()["id"]
    assert created.json()["meal_allowance"] == 30000 and created.json()["shift_allowance"] == 70000

    # Đọc lại qua list → giữ nguyên.
    listed = client.get("/api/attendance/shifts", headers=_h(token)).json()["items"]
    got = next(s for s in listed if s["id"] == sid)
    assert got["meal_allowance"] == 30000 and got["shift_allowance"] == 70000

    # Sửa → cập nhật đúng.
    upd = client.put(
        f"/api/attendance/shifts/{sid}",
        json={"name": "Ca tối PC", "start_time": "18:00", "end_time": "22:00",
              "meal_allowance": 40000, "shift_allowance": 80000},
        headers=_h(token),
    )
    assert upd.status_code == 200
    assert upd.json()["meal_allowance"] == 40000 and upd.json()["shift_allowance"] == 80000


def test_shift_forbidden_without_permission(client):
    token = _sales_token()
    assert client.get("/api/attendance/shifts", headers=_h(token)).status_code == 403
    assert client.post(
        "/api/attendance/shifts",
        json={"name": "x", "start_time": "08:00", "end_time": "17:00"},
        headers=_h(token),
    ).status_code == 403


# --- assign default shift + timesheet có công theo ca ------------------------


def test_assign_shift_and_timesheet_cong(client):
    token = _admin_token(client)
    shift = client.post(
        "/api/attendance/shifts",
        json={"name": "Hành chính", "start_time": "00:00", "end_time": "23:59"},
        headers=_h(token),
    ).json()
    # Hồ sơ SẴN CÓ của admin (mọi tài khoản đều có hồ sơ — `backfill_employee_profiles`; tạo hồ sơ
    # thứ 2 rồi gán sẽ vỡ link 1–1) + gán ca mặc định
    emp = client.get("/api/employees/me", headers=_h(token)).json()["employee"]
    upd = client.put(
        f"/api/employees/{emp['id']}",
        json={"full_name": "NV Ca", "department_id": _dept_id("Hành chính nhân sự"),
              "hire_date": "2020-01-01", "default_shift_id": shift["id"]},
        headers=_h(token),
    )
    assert upd.status_code == 200 and upd.json()["employee"]["default_shift_id"] == shift["id"]

    # 1 điểm + chấm VÀO/RA → có ngày công
    client.post(
        "/api/attendance/locations",
        json={"name": "X", "latitude": 10.0, "longitude": 106.0, "radius_m": 300},
        headers=_h(token),
    )
    client.post("/api/attendance/check", json={"latitude": 10.0, "longitude": 106.0}, headers=_h(token))
    client.post("/api/attendance/check", json={"latitude": 10.0, "longitude": 106.0}, headers=_h(token))

    from datetime import datetime, timedelta, timezone
    vn = datetime.now(timezone(timedelta(hours=7)))
    ts = client.get(f"/api/attendance/timesheet?year={vn.year}&month={vn.month}", headers=_h(token)).json()
    row = next(r for r in ts["rows"] if r["employee_name"] == "NV Ca")
    assert row["shift_name"] == "Hành chính"
    assert row["total_cong"] is not None
    day = next(iter(row["days"].values()))
    assert "cong" in day  # ô ngày có trường công theo ca


def test_assign_shift_endpoint_does_not_clobber(client):
    """PUT /employees/{id}/shift chỉ đụng default_shift_id — KHÔNG xóa field khác."""
    token = _admin_token(client)
    shift = client.post(
        "/api/attendance/shifts",
        json={"name": "Ca 1", "start_time": "06:00", "end_time": "14:00"},
        headers=_h(token),
    ).json()
    emp = client.post(
        "/api/employees",
        json={"full_name": "NV X", "department_id": _dept_id("Hành chính nhân sự"),
              "hire_date": "2020-01-01", "position": "Thợ in"},
        headers=_h(token),
    ).json()["employee"]

    r = client.put(f"/api/employees/{emp['id']}/shift", json={"default_shift_id": shift["id"]}, headers=_h(token))
    assert r.status_code == 200 and r.json()["default_shift_id"] == shift["id"]
    detail = client.get(f"/api/employees/{emp['id']}", headers=_h(token)).json()
    assert detail["default_shift_id"] == shift["id"] and detail["position"] == "Thợ in"  # không bị clobber

    r2 = client.put(f"/api/employees/{emp['id']}/shift", json={"default_shift_id": None}, headers=_h(token))
    assert r2.status_code == 200 and r2.json()["default_shift_id"] is None


def test_shift_history_resolves_the_shift_on_each_effective_date(client):
    token = _admin_token(client)
    shift_1 = client.post(
        "/api/attendance/shifts",
        json={"name": "Ca lịch sử 1", "start_time": "06:00", "end_time": "14:00"},
        headers=_h(token),
    ).json()
    shift_2 = client.post(
        "/api/attendance/shifts",
        json={"name": "Ca lịch sử 2", "start_time": "14:00", "end_time": "22:00"},
        headers=_h(token),
    ).json()
    emp = client.post(
        "/api/employees",
        json={"full_name": "NV Đổi Ca", "department_id": _dept_id("Hành chính nhân sự"),
              "hire_date": "2026-01-01"},
        headers=_h(token),
    ).json()["employee"]

    first = client.put(
        f"/api/employees/{emp['id']}/shift",
        json={"default_shift_id": shift_1["id"], "effective_from": "2026-01-01"},
        headers=_h(token),
    )
    second = client.put(
        f"/api/employees/{emp['id']}/shift",
        json={"default_shift_id": shift_2["id"], "effective_from": "2026-07-01"},
        headers=_h(token),
    )
    assert first.status_code == 200 and second.status_code == 200

    history = client.get(
        f"/api/employees/{emp['id']}/shift-history", headers=_h(token)
    ).json()["items"]
    assert len(history) == 2
    assert history[0]["shift_id"] == shift_2["id"] and history[0]["effective_to"] is None
    assert history[1]["shift_id"] == shift_1["id"] and history[1]["effective_to"] == "2026-06-30"

    db = SessionLocal()
    try:
        repo = EmployeeRepository(db)
        employee = repo.get_by_id(emp["id"])
        assert repo.shift_id_on(employee, date(2026, 6, 30)) == shift_1["id"]
        assert repo.shift_id_on(employee, date(2026, 7, 1)) == shift_2["id"]
    finally:
        db.close()

    blocked = client.delete(f"/api/attendance/shifts/{shift_1['id']}", headers=_h(token))
    assert blocked.status_code == 400


def test_timesheet_credits_paid_holiday(client):
    """PP-B (nền lịch Pha 1): ngày nghỉ lễ hưởng lương được cộng 1 công vào Bảng công (tử số),
    công chuẩn tháng loại lễ. NV 'xuất hiện' trong tháng 9 qua 1 đơn nghỉ đã duyệt → được cộng
    công lễ 2/9 (lễ seed)."""
    token = _admin_token(client)
    # Hồ sơ SẴN CÓ của admin (mọi tài khoản đều có hồ sơ), nắn tên/phòng ban cho khớp kịch bản.
    emp = client.get("/api/employees/me", headers=_h(token)).json()["employee"]
    client.put(
        f"/api/employees/{emp['id']}",
        json={"full_name": "NV Lễ", "department_id": _dept_id("Hành chính nhân sự"),
              "hire_date": "2020-01-01"},
        headers=_h(token),
    )

    # Đơn nghỉ có lương 2026-09-10 (Thứ 5) đã duyệt → NV có mặt trong bảng công tháng 9.
    tid = client.post("/api/leaves/types", json={"name": "Phép năm", "is_paid": True, "annual_quota": 12},
                      headers=_h(token)).json()["id"]
    req = client.post("/api/leaves",
                      json={"leave_type_id": tid, "start_date": "2026-09-10", "end_date": "2026-09-10"},
                      headers=_h(token))
    assert req.status_code == 201
    client.post(f"/api/leaves/{req.json()['id']}/approve", json={}, headers=_h(token))

    ts = client.get("/api/attendance/timesheet?year=2026&month=9", headers=_h(token)).json()
    assert ts["standard_cong"] == 25  # 26 ngày làm − lễ 2/9
    assert any(h["date"] == "2026-09-02" for h in ts["holidays"])
    row = next(r for r in ts["rows"] if r["employee_name"] == "NV Lễ")
    holiday_cell = row["days"]["2"]
    assert holiday_cell["holiday"] is True and holiday_cell["cong"] == 1.0
    assert row["total_cong"] >= 2.0  # công lễ 2/9 (1) + nghỉ phép 10/9 (1)
