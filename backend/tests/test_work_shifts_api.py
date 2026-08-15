"""Ca kíp (module `nhan_su`, lát Chấm công): khai ca + tính CÔNG theo tỷ lệ giờ làm.

- Unit test công thức `compute_day_cong` (đủ giờ = 1,00; đi muộn/về sớm giảm theo tỷ lệ, giữ
  2 chữ số; dung sai; OT tính riêng; thiếu chấm ra = 0).
- API: CRUD ca + validation + RBAC + gán ca mặc định cho NV + timesheet có công theo ca.
"""
from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

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


def _cong(first_in_min, main_out_min, *, ot=None, ot_window=None):
    """Ca Hành chính 08:00–17:00. `ot` = (ot_in_min, ot_out_min) của PHIÊN TĂNG CA (cặp chấm riêng)."""
    kw = dict(start_min=8 * 60, end_min=17 * 60, is_overnight=False, grace_min=5,
              first_in_min=first_in_min, main_out_min=main_out_min)
    if ot is not None:
        kw["ot_in_min"], kw["ot_out_min"] = ot
    if ot_window is not None:
        kw["ot_window"] = ot_window
    return compute_day_cong(**kw)


def test_compute_day_cong_examples():
    # Đúng đủ → 1,00
    r = _cong(8 * 60, 17 * 60)
    assert r["cong"] == 1.0 and not r["late"] and not r["early"] and r["ot_minutes"] == 0
    # Đi muộn 30' → 0,94
    r = _cong(8 * 60 + 30, 17 * 60)
    assert r["cong"] == 0.94 and r["late"] is True
    # Về sớm 1h (ra ca chính 16:00) → 0,89
    r = _cong(8 * 60, 16 * 60)
    assert r["cong"] == 0.89 and r["early"] is True
    # Đi muộn 2h → 0,78
    r = _cong(10 * 60, 17 * 60)
    assert r["cong"] == 0.78
    # Trong dung sai (muộn 4') → vẫn 1,00, không tính đi muộn
    r = _cong(8 * 60 + 4, 17 * 60)
    assert r["cong"] == 1.0 and r["late"] is False
    # Ra ca chính 17:00 + PHIÊN TĂNG CA 17:00–18:00 (phiếu 17:00–20:00) → công 1,00, OT = 60'
    r = _cong(8 * 60, 17 * 60, ot=(17 * 60, 18 * 60), ot_window=(17 * 60, 20 * 60))
    assert r["cong"] == 1.0 and r["ot_minutes"] == 60
    # KHÔNG có cặp chấm tăng ca (chỉ ra ca chính muộn 18:00) → OT = 0 (bắt buộc 2 cặp)
    r = _cong(8 * 60, 18 * 60)
    assert r["cong"] == 1.0 and r["ot_minutes"] == 0
    # Về sớm hơn phiếu: phiên TC 17:00–18:30 nhưng phiếu tới 20:00 → trả THỰC 90'
    r = _cong(8 * 60, 17 * 60, ot=(17 * 60, 18 * 60 + 30), ot_window=(17 * 60, 20 * 60))
    assert r["ot_minutes"] == 90
    # Làm quá phiếu: phiên TC 17:00–22:00 nhưng phiếu chỉ 17:00–19:00 → kẹp 120'
    r = _cong(8 * 60, 17 * 60, ot=(17 * 60, 22 * 60), ot_window=(17 * 60, 19 * 60))
    assert r["ot_minutes"] == 120
    # Thiếu chấm ra ca chính → 0 công, đánh dấu incomplete
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
                                first_in_min=fin, main_out_min=fout)
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


# --- lưới phân ca theo NGÀY (xoay ca linh hoạt) ------------------------------


def _mk_shift(client, token, name, start, end, *, overnight=False) -> dict:
    r = client.post("/api/attendance/shifts",
                    json={"name": name, "start_time": start, "end_time": end,
                          "is_overnight": overnight}, headers=_h(token))
    assert r.status_code == 201, r.text
    return r.json()


def _mk_emp(client, token, name, *, hire="2020-01-01") -> dict:
    r = client.post("/api/employees",
                    json={"full_name": name, "department_id": _dept_id("Hành chính nhân sự"),
                          "hire_date": hire}, headers=_h(token))
    assert r.status_code == 201, r.text
    return r.json()["employee"]


def _save_plan(client, token, cells, *, year=2026, month=6, expect=200):
    r = client.put("/api/attendance/shift-plan",
                   json={"year": year, "month": month, "cells": cells}, headers=_h(token))
    assert r.status_code == expect, r.text
    return r.json()


def _plan_row(client, token, eid, *, year=2026, month=6):
    r = client.get(f"/api/attendance/shift-plan?year={year}&month={month}", headers=_h(token))
    assert r.status_code == 200, r.text
    data = r.json()
    return next(row for row in data["rows"] if row["employee_id"] == eid), data


def test_shift_day_overrides_assignment(client):
    """Ca khai riêng cho MỘT ngày đè lên mốc ca mặc định; ngày khác không đổi."""
    token = _admin_token(client)
    base = _mk_shift(client, token, "Nền ngày", "08:00", "17:00")
    other = _mk_shift(client, token, "Đè chiều", "14:00", "22:00")
    emp = _mk_emp(client, token, "NV Đè Ca")
    client.put(f"/api/employees/{emp['id']}/shift",
               json={"default_shift_id": base["id"], "effective_from": "2026-01-01"},
               headers=_h(token))

    _save_plan(client, token, [{"employee_id": emp["id"], "work_date": "2026-06-15",
                                "action": "set", "shift_id": other["id"]}])

    db = SessionLocal()
    try:
        repo = EmployeeRepository(db)
        e = repo.get_by_id(emp["id"])
        assert repo.shift_id_on(e, date(2026, 6, 15)) == other["id"]   # ô khai tay thắng
        assert repo.shift_id_on(e, date(2026, 6, 14)) == base["id"]    # ngày khác giữ mốc
        assert repo.shift_id_on(e, date(2026, 6, 16)) == base["id"]
    finally:
        db.close()


def test_shift_day_off_does_not_block_resolve(client):
    """Ô 'Nghỉ' chỉ là DẤU KẾ HOẠCH: nó KHÔNG được chặn resolve ca.

    Chủ đã chốt người bị gọi đi làm đúng ngày nghỉ luân phiên vẫn chấm công được và
    hưởng 1× như ngày thường ⇒ ngày đó vẫn phải ra ca nền. Nếu trả None thì
    `_shift_for_check` sẽ ném 'chưa được gán ca' và chặn cứng họ ngoài đời."""
    token = _admin_token(client)
    base = _mk_shift(client, token, "Nền nghỉ", "08:00", "17:00")
    emp = _mk_emp(client, token, "NV Nghỉ Lịch")
    client.put(f"/api/employees/{emp['id']}/shift",
               json={"default_shift_id": base["id"], "effective_from": "2026-01-01"},
               headers=_h(token))

    _save_plan(client, token, [{"employee_id": emp["id"], "work_date": "2026-06-17",
                                "action": "off"}])

    db = SessionLocal()
    try:
        repo = EmployeeRepository(db)
        e = repo.get_by_id(emp["id"])
        assert repo.shift_id_on(e, date(2026, 6, 17)) == base["id"]
    finally:
        db.close()

    row, _ = _plan_row(client, token, emp["id"])
    assert row["days"]["17"]["is_off"] is True and row["days"]["17"]["source"] == "day"


def test_overnight_then_day_shift_rotation(client):
    """Kịch bản chủ nêu: ngày N làm CA KHUYA, ngày N+1 làm CA NGÀY.

    Cả hai ngày phải đủ công; lượt RA 06:00 KHÔNG được hút sang ngày N+1 và cũng
    KHÔNG được hiểu thành tăng ca."""
    from datetime import timezone as _tz

    from app.repositories.attendance_repo import AttendanceRepository

    token = _admin_token(client)
    night = _mk_shift(client, token, "Ca khuya xoay", "22:00", "06:00", overnight=True)
    day = _mk_shift(client, token, "Ca ngày xoay", "08:00", "17:00")
    emp = _mk_emp(client, token, "NV Xoay Ca")
    client.put(f"/api/employees/{emp['id']}/shift",
               json={"default_shift_id": day["id"], "effective_from": "2026-01-01"},
               headers=_h(token))
    # 15/06 khai CA KHUYA (đè ca nền); 16/06 để trống → kế thừa ca ngày.
    _save_plan(client, token, [{"employee_id": emp["id"], "work_date": "2026-06-15",
                                "action": "set", "shift_id": night["id"]}])

    utc = _tz.utc
    db = SessionLocal()
    try:
        arepo = AttendanceRepository(db)
        # Ca khuya 15/06: VÀO 22:00 VN (15:00 UTC), RA 06:00 VN ngày 16 (23:00 UTC ngày 15).
        arepo.create_log(employee_id=emp["id"], check_type="in",
                         checked_at=datetime(2026, 6, 15, 15, 0, tzinfo=utc), within_range=True)
        arepo.create_log(employee_id=emp["id"], check_type="out",
                         checked_at=datetime(2026, 6, 15, 23, 0, tzinfo=utc), within_range=True)
        # Ca ngày 16/06: VÀO 08:00 VN (01:00 UTC), RA 17:00 VN (10:00 UTC).
        arepo.create_log(employee_id=emp["id"], check_type="in",
                         checked_at=datetime(2026, 6, 16, 1, 0, tzinfo=utc), within_range=True)
        arepo.create_log(employee_id=emp["id"], check_type="out",
                         checked_at=datetime(2026, 6, 16, 10, 0, tzinfo=utc), within_range=True)
    finally:
        db.close()

    ts = client.get("/api/attendance/timesheet?year=2026&month=6", headers=_h(token)).json()
    row = next(r for r in ts["rows"] if r["employee_id"] == emp["id"])
    assert row["days"]["15"]["cong"] == 1.0, row["days"]["15"]
    assert row["days"]["16"]["cong"] == 1.0, row["days"]["16"]
    assert row["days"]["15"]["shift_name"] == "Ca khuya xoay"
    assert row["days"]["16"]["shift_name"] == "Ca ngày xoay"
    # Xoay ca KHÔNG được biến thành tăng ca
    assert (row["days"]["15"].get("ot_minutes") or 0) == 0
    assert (row["days"]["16"].get("ot_minutes") or 0) == 0


def test_shift_plan_bulk_set_off_inherit(client):
    """Một request ghi nhiều ô; `inherit` xóa ô để ngày đó về kế thừa ca mặc định."""
    token = _admin_token(client)
    base = _mk_shift(client, token, "Nền bulk", "08:00", "17:00")
    night = _mk_shift(client, token, "Khuya bulk", "22:00", "06:00", overnight=True)
    emp = _mk_emp(client, token, "NV Bulk")
    client.put(f"/api/employees/{emp['id']}/shift",
               json={"default_shift_id": base["id"], "effective_from": "2026-01-01"},
               headers=_h(token))

    res = _save_plan(client, token, [
        {"employee_id": emp["id"], "work_date": "2026-06-01", "action": "set",
         "shift_id": night["id"]},
        {"employee_id": emp["id"], "work_date": "2026-06-02", "action": "off"},
        {"employee_id": emp["id"], "work_date": "2026-06-03", "action": "inherit"},
    ])
    assert res["saved"] == 2 and res["cleared"] == 0 and res["rejected"] == []

    row, data = _plan_row(client, token, emp["id"])
    assert data["locked"] is False
    # So từng khoá thay vì so nguyên dict: ô còn mang lớp phủ nghỉ phép (`leave_name`/`leave_paid`,
    # chỉ để xem) nên so nguyên khối sẽ đỏ mỗi lần thêm một thông tin hiển thị mới.
    assert row["days"]["1"]["shift_id"] == night["id"]
    assert row["days"]["1"]["source"] == "day" and row["days"]["1"]["is_off"] is False
    assert row["days"]["2"]["is_off"] is True
    assert row["days"]["3"]["shift_id"] == base["id"]
    assert row["days"]["3"]["source"] == "assign" and row["days"]["3"]["is_off"] is False
    # Không có phiếu nghỉ nào ⇒ không ô nào mang dấu phép.
    assert all(v["leave_name"] is None for v in row["days"].values())
    assert row["no_default"] is False

    # inherit trên ô ĐANG khai → xóa, quay về mốc
    res2 = _save_plan(client, token, [{"employee_id": emp["id"], "work_date": "2026-06-01",
                                       "action": "inherit"}])
    assert res2["cleared"] == 1
    row2, _ = _plan_row(client, token, emp["id"])
    assert row2["days"]["1"]["source"] == "assign" and row2["days"]["1"]["shift_id"] == base["id"]


def test_shift_plan_rejects_bad_cells_with_reason(client):
    """Ô sai KHÔNG bị nuốt im lặng — trả về kèm lý do."""
    token = _admin_token(client)
    shift = _mk_shift(client, token, "Ca reject", "08:00", "17:00")
    emp = _mk_emp(client, token, "NV Reject")

    res = _save_plan(client, token, [
        {"employee_id": emp["id"], "work_date": "2026-07-01", "action": "set",
         "shift_id": shift["id"]},
        {"employee_id": emp["id"], "work_date": "2026-06-05", "action": "set",
         "shift_id": 999999},
    ])
    assert res["saved"] == 0 and len(res["rejected"]) == 2
    reasons = " ".join(r["reason"] for r in res["rejected"])
    assert "không thuộc tháng" in reasons and "Ca không tồn tại" in reasons


def test_shift_plan_blocked_when_period_locked(client):
    token = _admin_token(client)
    shift = _mk_shift(client, token, "Ca khoá kỳ", "08:00", "17:00")
    emp = _mk_emp(client, token, "NV Khoá Kỳ")
    lock = client.post("/api/attendance/period/lock", json={"year": 2026, "month": 5},
                       headers=_h(token))
    assert lock.status_code == 200, lock.text

    r = client.put("/api/attendance/shift-plan",
                   json={"year": 2026, "month": 5,
                         "cells": [{"employee_id": emp["id"], "work_date": "2026-05-04",
                                    "action": "set", "shift_id": shift["id"]}]},
                   headers=_h(token))
    assert r.status_code == 400 and "đã chốt" in r.json()["detail"]
    assert client.get("/api/attendance/shift-plan?year=2026&month=5",
                      headers=_h(token)).json()["locked"] is True


def test_shift_plan_matches_engine_before_first_milestone(client):
    """Lưới phải nói ĐÚNG những gì engine tính.

    NV có mốc ca từ giữa tháng: những ngày TRƯỚC mốc đầu tiên, `shift_id_on` trả None
    (không có ca). Lưới trước đây rơi về `default_shift_id` nên vẽ ra một ca mà engine
    không công nhận — màn hình báo có ca trong khi NV không chấm công được."""
    token = _admin_token(client)
    shift = _mk_shift(client, token, "Ca giữa tháng", "08:00", "17:00")
    emp = _mk_emp(client, token, "NV Mốc Giữa Tháng", hire="2020-01-01")
    client.put(f"/api/employees/{emp['id']}/shift",
               json={"default_shift_id": shift["id"], "effective_from": "2026-06-15"},
               headers=_h(token))

    row, _ = _plan_row(client, token, emp["id"])
    assert row["days"]["14"]["shift_id"] is None, row["days"]["14"]   # trước mốc → KHÔNG ca
    assert row["days"]["14"]["source"] == "none"
    assert row["days"]["15"]["shift_id"] == shift["id"]               # từ mốc → có ca
    assert row["days"]["15"]["source"] == "assign"

    # Và phải khớp từng ngày với engine thật.
    db = SessionLocal()
    try:
        repo = EmployeeRepository(db)
        e = repo.get_by_id(emp["id"])
        for d in (1, 10, 14, 15, 20, 30):
            assert row["days"][str(d)]["shift_id"] == repo.shift_id_on(e, date(2026, 6, d)), d
    finally:
        db.close()


def test_shift_plan_lists_employee_without_any_punch(client):
    """NV mới chưa chấm công buổi nào VẪN phải có mặt trên lưới — chính họ là người
    cần khai ca. (Bảng công tháng thì ngược lại: chỉ liệt kê ai đã có dữ liệu.)"""
    token = _admin_token(client)
    emp = _mk_emp(client, token, "NV Chưa Chấm", hire="2026-06-01")
    row, _ = _plan_row(client, token, emp["id"])
    assert row["no_default"] is True and row["days"]["10"]["source"] == "none"


def test_delete_shift_blocked_when_used_only_by_shift_plan(client):
    """Ca chỉ dùng trong lưới phân ca vẫn là ĐANG DÙNG — không cho xóa, nếu không
    những ngày đã khai sẽ trỏ vào ca không tồn tại và mất công im lặng."""
    token = _admin_token(client)
    shift = _mk_shift(client, token, "Ca chỉ trong lưới", "13:00", "21:00")
    emp = _mk_emp(client, token, "NV Lưới Only")
    _save_plan(client, token, [{"employee_id": emp["id"], "work_date": "2026-06-20",
                                "action": "set", "shift_id": shift["id"]}])
    assert client.delete(f"/api/attendance/shifts/{shift['id']}",
                         headers=_h(token)).status_code == 400


def test_timesheet_marks_planned_off_without_touching_cong(client):
    """Ngày nghỉ luân phiên hiện 'nghỉ theo lịch' trên bảng công (phân biệt với VẮNG),
    nhưng KHÔNG sinh công và KHÔNG đụng tổng công — chốt 'ô Nghỉ không ra tiền'."""
    from datetime import timezone as _tz

    from app.repositories.attendance_repo import AttendanceRepository

    token = _admin_token(client)
    shift = _mk_shift(client, token, "Ca planned off", "08:00", "17:00")
    emp = _mk_emp(client, token, "NV Nghỉ Luân Phiên")
    client.put(f"/api/employees/{emp['id']}/shift",
               json={"default_shift_id": shift["id"], "effective_from": "2026-01-01"},
               headers=_h(token))
    db = SessionLocal()
    try:
        arepo = AttendanceRepository(db)
        # Làm đủ ngày 08/06 (08:00–17:00 VN = 01:00–10:00 UTC)
        arepo.create_log(employee_id=emp["id"], check_type="in",
                         checked_at=datetime(2026, 6, 8, 1, 0, tzinfo=_tz.utc), within_range=True)
        arepo.create_log(employee_id=emp["id"], check_type="out",
                         checked_at=datetime(2026, 6, 8, 10, 0, tzinfo=_tz.utc), within_range=True)
    finally:
        db.close()
    # 10/06 khai NGHỈ theo lịch (không chấm công ngày này)
    _save_plan(client, token, [{"employee_id": emp["id"], "work_date": "2026-06-10",
                                "action": "off"}])

    ts = client.get("/api/attendance/timesheet?year=2026&month=6", headers=_h(token)).json()
    row = next(r for r in ts["rows"] if r["employee_id"] == emp["id"])
    assert row["days"]["10"]["planned_off"] is True
    assert row["days"]["10"]["cong"] is None          # nghỉ → không công
    assert row["days"]["8"]["planned_off"] is False
    assert row["total_cong"] == 1.0                   # chỉ ngày đã làm, dấu nghỉ không cộng gì


def test_set_base_shift_bulk_creates_history(client):
    """Nút "Đặt ca nền" gán 1 lượt nhiều NV và phải tạo MỐC hiệu lực (không chỉ set
    default_shift_id) — nếu không, lịch sử đổi ca mất dấu và ngày cũ bị tính sai ca."""
    token = _admin_token(client)
    shift = _mk_shift(client, token, "Ca nền bulk", "08:00", "17:00")
    e1 = _mk_emp(client, token, "NV Nền 1")
    e2 = _mk_emp(client, token, "NV Nền 2")

    r = client.put("/api/employees/shift/bulk",
                   json={"employee_ids": [e1["id"], e2["id"]],
                         "default_shift_id": shift["id"], "effective_from": "2026-06-01"},
                   headers=_h(token))
    assert r.status_code == 200, r.text
    assert r.json()["updated"] == 2 and r.json()["failed"] == []

    for e in (e1, e2):
        hist = client.get(f"/api/employees/{e['id']}/shift-history", headers=_h(token)).json()["items"]
        assert any(h["shift_id"] == shift["id"] and h["effective_from"] == "2026-06-01" for h in hist)

    db = SessionLocal()
    try:
        repo = EmployeeRepository(db)
        emp = repo.get_by_id(e1["id"])
        assert repo.shift_id_on(emp, date(2026, 6, 1)) == shift["id"]
        assert repo.shift_id_on(emp, date(2026, 12, 31)) == shift["id"]   # áp dụng cho MỌI tháng sau
    finally:
        db.close()


def test_set_base_shift_bulk_clamps_to_hire_date(client):
    """NV vào làm SAU ngày được chọn thì mốc tự LÙI về ngày vào làm — không loại họ
    ra khỏi lô.

    Người khai ca không có cách nào biết ngày vào làm của từng người; loại họ ra thì
    chỉ cần một người mới là cả lô hỏng (đúng lỗi chủ gặp: 0 NV được đặt, 5 NV bị bỏ
    qua). Ca vẫn không bao giờ có hiệu lực trước khi người ta vào làm."""
    token = _admin_token(client)
    shift = _mk_shift(client, token, "Ca nền lẻ", "08:00", "17:00")
    ok = _mk_emp(client, token, "NV Nền OK", hire="2020-01-01")
    late = _mk_emp(client, token, "NV Vào Sau", hire="2026-08-01")   # vào làm SAU ngày áp dụng

    r = client.put("/api/employees/shift/bulk",
                   json={"employee_ids": [ok["id"], late["id"], 999999],
                         "default_shift_id": shift["id"], "effective_from": "2026-06-01"},
                   headers=_h(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["updated"] == 2 and body["adjusted"] == 1    # cả hai đều được đặt
    assert len(body["failed"]) == 1                          # chỉ NV không tồn tại mới trượt

    db = SessionLocal()
    try:
        repo = EmployeeRepository(db)
        assert repo.shift_id_on(repo.get_by_id(ok["id"]), date(2026, 6, 1)) == shift["id"]
        late_emp = repo.get_by_id(late["id"])
        # Lùi đúng ngày vào làm: trước đó vẫn KHÔNG có ca, từ ngày vào làm thì có.
        assert repo.shift_id_on(late_emp, date(2026, 7, 31)) is None
        assert repo.shift_id_on(late_emp, date(2026, 8, 1)) == shift["id"]
    finally:
        db.close()


def test_delete_shift_assignment_undoes_a_wrong_milestone(client):
    """Gỡ được mốc gán nhầm → resolve quay về mốc TRƯỚC ĐÓ.

    Kịch bản thật của chủ: một cú lỡ tay ghi mốc 'bỏ gán ca' khiến NV mất ca từ ngày
    đó trở đi và KHÔNG CHẤM CÔNG ĐƯỢC; không có đường xóa thì mốc sai là vĩnh viễn."""
    token = _admin_token(client)
    shift = _mk_shift(client, token, "Ca gỡ mốc", "08:00", "17:00")
    emp = _mk_emp(client, token, "NV Gỡ Mốc")
    client.put(f"/api/employees/{emp['id']}/shift",
               json={"default_shift_id": shift["id"], "effective_from": "2026-06-01"},
               headers=_h(token))
    # Lỡ tay: bỏ gán ca từ 2026-06-20
    client.put(f"/api/employees/{emp['id']}/shift",
               json={"default_shift_id": None, "effective_from": "2026-06-20"},
               headers=_h(token))

    db = SessionLocal()
    try:
        repo = EmployeeRepository(db)
        assert repo.shift_id_on(repo.get_by_id(emp["id"]), date(2026, 6, 25)) is None  # đang mất ca
    finally:
        db.close()

    hist = client.get(f"/api/employees/{emp['id']}/shift-history", headers=_h(token)).json()["items"]
    bad = next(h for h in hist if h["effective_from"] == "2026-06-20")
    r = client.delete(f"/api/employees/{emp['id']}/shift-history/{bad['id']}", headers=_h(token))
    assert r.status_code == 204, r.text

    db = SessionLocal()
    try:
        repo = EmployeeRepository(db)
        e = repo.get_by_id(emp["id"])
        assert repo.shift_id_on(e, date(2026, 6, 25)) == shift["id"]   # quay về mốc trước
        assert e.default_shift_id == shift["id"]                       # cache đồng bộ lại
    finally:
        db.close()


def test_delete_shift_assignment_rejects_foreign_milestone(client):
    """Mốc của người khác thì không xóa qua đường của NV này được."""
    token = _admin_token(client)
    shift = _mk_shift(client, token, "Ca mốc lạ", "08:00", "17:00")
    a = _mk_emp(client, token, "NV Mốc A")
    b = _mk_emp(client, token, "NV Mốc B")
    for e in (a, b):
        client.put(f"/api/employees/{e['id']}/shift",
                   json={"default_shift_id": shift["id"], "effective_from": "2026-06-01"},
                   headers=_h(token))
    hist_b = client.get(f"/api/employees/{b['id']}/shift-history", headers=_h(token)).json()["items"]
    r = client.delete(f"/api/employees/{a['id']}/shift-history/{hist_b[0]['id']}", headers=_h(token))
    assert r.status_code in (400, 404)


def test_delete_shift_assignment_forbidden_without_permission(client):
    token = _sales_token()
    assert client.delete("/api/employees/1/shift-history/1",
                         headers=_h(token)).status_code == 403


def test_set_base_shift_bulk_forbidden_without_permission(client):
    token = _sales_token()
    assert client.put("/api/employees/shift/bulk",
                      json={"employee_ids": [1], "default_shift_id": None,
                            "effective_from": "2026-06-01"},
                      headers=_h(token)).status_code == 403


def test_shift_plan_forbidden_without_permission(client):
    token = _sales_token()
    assert client.get("/api/attendance/shift-plan?year=2026&month=6",
                      headers=_h(token)).status_code == 403
    assert client.put("/api/attendance/shift-plan",
                      json={"year": 2026, "month": 6,
                            "cells": [{"employee_id": 1, "work_date": "2026-06-01",
                                       "action": "off"}]},
                      headers=_h(token)).status_code == 403


# --- nghỉ theo GIỜ: trừ công đúng phút, miễn phạt, giữ chuyên cần ------------


def _mk_leave_type(client, token, name="Phép giờ", *, paid=True, quota=0) -> int:
    r = client.post("/api/leaves/types",
                    json={"name": name, "is_paid": paid, "annual_quota": quota}, headers=_h(token))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _setup_gio(client, token, name, *, punch_out_hour, leave_minutes=None,
               punch_out_minute=0, leave_type_id=None, leave_cong=0):
    """NV ca HC 08:00–17:00 (window 540, grace 5), chấm vào 08:00 và ra `punch_out_hour`:MM
    ngày 15/06/2026. `leave_minutes` = số phút xin nghỉ (None = không phiếu)."""
    from datetime import timedelta, timezone as _tz

    from app.repositories.attendance_repo import AttendanceRepository
    shift = _mk_shift(client, token, f"HC {name}", "08:00", "17:00")
    emp = _mk_emp(client, token, name)
    client.put(f"/api/employees/{emp['id']}/shift",
               json={"default_shift_id": shift["id"], "effective_from": "2026-01-01"},
               headers=_h(token))
    vn = _tz(timedelta(hours=7))
    db = SessionLocal()
    try:
        arepo = AttendanceRepository(db)
        arepo.create_log(employee_id=emp["id"], check_type="in", within_range=True,
                         checked_at=datetime(2026, 6, 15, 8, 0, tzinfo=vn).astimezone(_tz.utc))
        arepo.create_log(employee_id=emp["id"], check_type="out", within_range=True,
                         checked_at=datetime(2026, 6, 15, punch_out_hour, punch_out_minute,
                                             tzinfo=vn).astimezone(_tz.utc))
    finally:
        db.close()
    if leave_minutes is not None:
        _approve_hourly_leave(client, token, emp["id"], minutes=leave_minutes, name=name,
                              leave_type_id=leave_type_id, leave_cong=leave_cong)
    return emp


def _approve_hourly_leave(client, token, eid, *, minutes, name, day=15,
                          leave_type_id=None, leave_cong=0):
    """Phiếu ĐI MUỘN / VỀ SỚM ĐÃ DUYỆT cho ĐÚNG nhân viên `eid`, kết thúc lúc 17:00.

    Ghi thẳng qua repo (bảng RIÊNG `late_early_requests`) vì các endpoint tự phục vụ luôn tạo
    phiếu cho hồ sơ của NGƯỜI ĐĂNG NHẬP — không đặt hộ NV khác được. Luật validate giờ / quyền
    có test riêng ở `test_late_early_api.py`.

    `leave_type_id` khác None = nhánh CÓ TRỪ PHÉP (tick trên phiếu): `leave_cong` ngày phép bị
    trừ, phần vắng vẫn được trả theo lương vị trí."""
    from app.repositories.late_early_repo import LateEarlyRepository
    db = SessionLocal()
    try:
        LateEarlyRepository(db).create_request(
            employee_id=eid, work_date=date(2026, 6, day), from_minute=1020 - minutes,
            to_minute=1020, reason="test", status="approved", created_by=None,
            leave_type_id=leave_type_id, leave_cong=leave_cong,
        )
    finally:
        db.close()


def _row(client, token, eid):
    """Row THÔ của engine (có cả `late_off_days` — khoá nội bộ, API không phơi ra)."""
    from app.repositories.attendance_repo import AttendanceRepository
    from app.repositories.audit_repo import AuditLogRepository
    from app.repositories.calendar_repo import CalendarRepository
    from app.repositories.late_early_repo import LateEarlyRepository
    from app.repositories.leave_repo import LeaveRepository
    from app.services.attendance_service import AttendanceService
    from app.services.calendar_service import CalendarService

    db = SessionLocal()
    try:
        svc = AttendanceService(
            AttendanceRepository(db), EmployeeRepository(db), AuditLogRepository(db),
            leaves=LeaveRepository(db),
            calendar=CalendarService(CalendarRepository(db), AuditLogRepository(db)),
            late_early=LateEarlyRepository(db),
        )
        ts = svc.monthly_timesheet(year=2026, month=6)
        return next(r for r in ts["rows"] if r["employee_id"] == eid)
    finally:
        db.close()


def test_nghi_2h_co_don_tru_cong_khong_phat(client):
    """Về sớm 2h CÓ ĐƠN: công vẫn trừ đúng tỷ lệ phút, KHÔNG bị phạt, chuyên cần được bù."""
    token = _admin_token(client)
    emp = _setup_gio(client, token, "NV Có Đơn", punch_out_hour=15, leave_minutes=120)
    row = _row(client, token, emp["id"])
    assert row["days"]["15"]["cong"] == 0.78          # 420/540, mẫu số = KHUNG CA (chốt của chủ)
    assert row["late_off_days"] == []                 # có đơn → không phạt
    assert row["excused_cong"] == 0.22                # 1 − 0,78 → chuyên cần không bị trừ
    assert row["total_leave"] == 0                    # đơn giờ KHÔNG phải ngày nghỉ nguyên ngày


def test_nghi_2h_khong_don_bi_phat(client):
    """Cùng số phút vắng nhưng KHÔNG đơn: tiền công trừ y hệt, nhưng BỊ PHẠT."""
    token = _admin_token(client)
    emp = _setup_gio(client, token, "NV Không Đơn", punch_out_hour=15)
    row = _row(client, token, emp["id"])
    assert row["days"]["15"]["cong"] == 0.78          # tiền công: giống hệt ca có đơn
    assert row["late_off_days"] == [120]              # nhưng bị ghi nhận vi phạm
    assert row["excused_cong"] == 0


def test_xin_it_hon_thuc_te_van_phat_phan_du(client):
    """Xin 1h nhưng vắng 2h → tha đúng 1h, 1h dư vẫn phạt (chốt của chủ)."""
    token = _admin_token(client)
    emp = _setup_gio(client, token, "NV Xin Thiếu", punch_out_hour=15, leave_minutes=60)
    row = _row(client, token, emp["id"])
    assert row["late_off_days"] == [60]               # 120 vắng − 60 đã xin
    assert row["excused_cong"] == round(60 / 540, 2)  # chỉ bù phần đã xin


def test_khai_nghi_4h_roi_van_o_lai_lam_thi_cong_theo_PHIEU(client):
    """⚠️ LUẬT ĐÃ ĐỔI 12/08/2026 — test này trước đây khẳng định điều NGƯỢC LẠI.

    Ca: phiếu xin về sớm 13:00→17:00 (240'), nhưng 17:00 mới bấm ra.

      • Luật CŨ: lấy giờ BẤM ⇒ công 1,0, `excused_cong` = 0 ("làm đủ ca thì khai nghỉ không được
        cộng ảo").
      • Luật MỚI: đơn đã duyệt là CAM KẾT ⇒ công tính đến 13:00 = 300'/540' = 0,56; phần vắng
        240' đã có phép nên miễn phạt chuyên cần (`excused_cong` 0,44), không rơi vào
        `late_off_days`.

    Chủ chốt biết và CHỌN chịu sai ở đúng ca này: *"kệ họ, họ có thể sửa công hoặc là xóa phiếu
    tạo lại"* — hệ thống không phân biệt được "về đúng 13h nhưng quên bấm" với "xin về 13h nhưng ở
    lại làm". Hai đường lui đó có test riêng ở `test_kep_gio_ra_theo_phieu_ve_som.py`.

    Giờ BẤM THẬT vẫn giữ nguyên trên lưới (17:00) — chỉ CÔNG bị kẹp. Xoá luôn giờ bấm thì HCNS
    mất căn cứ để chấm bù, tức là chặn mất đường lui thứ hai."""
    token = _admin_token(client)
    emp = _setup_gio(client, token, "NV Khai Khống", punch_out_hour=17, leave_minutes=240)
    row = _row(client, token, emp["id"])
    assert row["days"]["15"]["cong"] == 0.56
    assert row["days"]["15"]["last_out"] == "17:00", "kẹp CÔNG thôi, đừng nuốt giờ bấm thật"
    assert row["excused_cong"] == 0.44
    assert row["late_off_days"] == []


def test_don_gio_ma_khong_cham_cong_khong_duoc_tinh_cong(client):
    """⭐ Đơn giờ mà hôm đó KHÔNG chấm công buổi nào: KHÔNG được biếu nguyên ngày lương.

    Đây là lý do đơn giờ phải nằm ở map RIÊNG, không nhập chung `leave_map` (nhánh nghỉ
    nguyên ngày cấp thẳng cong = 1.0)."""
    token = _admin_token(client)
    shift = _mk_shift(client, token, "HC vắng", "08:00", "17:00")
    emp = _mk_emp(client, token, "NV Vắng Cả Ngày")
    client.put(f"/api/employees/{emp['id']}/shift",
               json={"default_shift_id": shift["id"], "effective_from": "2026-01-01"},
               headers=_h(token))
    _approve_hourly_leave(client, token, emp["id"], minutes=120, name="vắng")

    row = _row(client, token, emp["id"])
    assert row["days"]["15"]["cong"] is None      # không chấm công → không có công
    assert (row["total_cong"] or 0) == 0
    assert row["total_leave"] == 0
    assert row["excused_cong"] == 0


def test_nghi_nua_buoi_co_tru_phep_hoan_cong_va_tra_luong(client):
    """⭐ NHÁNH RA TIỀN: nghỉ nửa buổi, người tạo TÍCH 'trừ vào phép năm'.

    Vắng đúng NỬA KHUNG CA (12:30→17:00 = 270' / 540'): công ngày đó được HOÀN về đủ 1,0 và
    phần hoàn đi vào `paid_leave_days` để Lương trả theo LƯƠNG VỊ TRÍ (`_luong_cong_split`).
    Không phạt, và KHÔNG sinh `excused_cong` — công đã hoàn thì chuyên cần tự đủ, bù thêm
    là BÙ HAI LẦN."""
    token = _admin_token(client)
    tid = _mk_leave_type(client, token, name="Phép năm nửa buổi", quota=12)
    emp = _setup_gio(client, token, "NV Nửa Buổi", punch_out_hour=12, punch_out_minute=30,
                     leave_minutes=270, leave_type_id=tid, leave_cong=0.5)
    row = _row(client, token, emp["id"])
    assert row["days"]["15"]["cong"] == 1.0          # 0,5 làm thật + 0,5 phép → ô hiện ĐỦ ngày
    assert row["days"]["15"]["leave_cong"] == 0.5    # tách bạch phần do phép, để đối chiếu
    assert row["total_cong"] == 1.0
    assert row["paid_leave_days"] == 0.5             # FLOAT — ép int là NLĐ mất nửa ngày lương
    assert row["late_off_days"] == []                # có phiếu → không phạt
    assert row["excused_cong"] == 0                  # đã hoàn công, không bù chuyên cần nữa


def test_nua_buoi_tru_phep_khong_doi_so_khi_chot_cong(client):
    """⭐ CANH BOM HẸN GIỜ: `metrics_map` có 2 nhánh — LIVE (chưa chốt) và SNAPSHOT (đã chốt).

    Nối một nhánh mà quên nhánh kia thì lương ĐỔI SỐ đúng lúc HCNS bấm Chốt công: nháp một số,
    chốt xong một số. Test này khoá cả hai phải khớp, đặc biệt `paid_leave_days` = 0,5 (cột
    snapshot từng là Integer, ép 0,5 → 0 là NLĐ mất nửa ngày lương)."""
    from app.repositories.attendance_repo import AttendanceRepository
    from app.repositories.audit_repo import AuditLogRepository
    from app.repositories.calendar_repo import CalendarRepository
    from app.repositories.late_early_repo import LateEarlyRepository
    from app.repositories.leave_repo import LeaveRepository
    from app.services.attendance_service import AttendanceService
    from app.services.calendar_service import CalendarService

    token = _admin_token(client)
    tid = _mk_leave_type(client, token, name="Phép năm chốt công", quota=12)
    emp = _setup_gio(client, token, "NV Chốt Công", punch_out_hour=12, punch_out_minute=30,
                     leave_minutes=270, leave_type_id=tid, leave_cong=0.5)

    def _svc(db):
        return AttendanceService(
            AttendanceRepository(db), EmployeeRepository(db), AuditLogRepository(db),
            leaves=LeaveRepository(db),
            calendar=CalendarService(CalendarRepository(db), AuditLogRepository(db)),
            late_early=LateEarlyRepository(db),
        )

    db = SessionLocal()
    try:
        live = _svc(db).metrics_map(2026, 6)[emp["id"]]
        _svc(db).lock_period(year=2026, month=6, actor=SimpleNamespace(id=1))
        snap = _svc(db).metrics_map(2026, 6)[emp["id"]]
    finally:
        db.close()

    assert live["paid_leave_days"] == 0.5
    for k in ("cong", "paid_leave_days", "excused_cong", "holiday_cong", "restday_cong",
              "plain_cong", "ot_minutes"):
        assert snap[k] == live[k], f"'{k}' đổi số khi chốt công: {live[k]} → {snap[k]}"


def test_tru_phep_khong_duoc_duc_ra_cong_ao(client):
    """Quỹ phép làm tròn LÊN 0,5 nhưng TIỀN chỉ trả đúng phần công thiếu THẬT.

    Vắng 240' trên khung 540' = 0,44 công. Phiếu tiêu 0,5 ngày phép (luật làm tròn), nhưng
    nếu trả luôn 0,5 công thì tổng ngày đó thành 1,06 — đúc công từ hư không, và
    `paid_leave_days` sẽ không còn khớp phần phép NẰM TRONG `total_cong` khiến
    `_luong_cong_split` chia sai giá cả hai vế."""
    token = _admin_token(client)
    tid = _mk_leave_type(client, token, name="Phép năm 4h", quota=12)
    emp = _setup_gio(client, token, "NV Bốn Giờ", punch_out_hour=13,
                     leave_minutes=240, leave_type_id=tid, leave_cong=0.5)
    row = _row(client, token, emp["id"])
    assert row["days"]["15"]["cong"] == 1.0          # 0,56 làm thật + 0,44 phép
    assert row["total_cong"] == 1.0                  # KHÔNG vượt 1,0
    assert row["paid_leave_days"] == 0.44            # kẹp theo công thiếu thật, không phải 0,5
    assert row["late_off_days"] == []
    assert row["excused_cong"] == 0


# --- Lớp phủ NGHỈ PHÉP trên lưới Phân ca tháng (chủ 30/07/2026) --------------
# Chủ hỏi: *"nhân viên làm phiếu xin nghỉ thì chỗ phân ca tháng mà ngày nó nghỉ nó có tự nhảy là
# nghỉ không"*. Trước đây: KHÔNG — lưới hoàn toàn mù với nghỉ phép.
#
# Chủ chốt cách vá: **hiện ĐỂ XEM, KHÔNG ghi đè**. Dấu nghỉ phép đọc thẳng từ phiếu, không viết vào
# `employee_shift_days`. Nhờ vậy huỷ phiếu là lưới tự hết dấu, và không đẻ nguồn sự thật thứ hai.
#
# ⚠️ Đừng lẫn với `is_off` ("Nghỉ theo lịch"): đó là dấu KẾ HOẠCH do người dùng tự tô, không trừ
# phép, không ra tiền. Trùng tên "nghỉ" nhưng là hai chuyện khác hẳn.


def _don_nghi(client, token, emp_id, tu, den, *, duyet=True, paid=True):
    """Tạo (và tuỳ chọn duyệt) một phiếu nghỉ nguyên ngày. Trả về id phiếu."""
    tid = client.post("/api/leaves/types",
                      json={"name": f"Phép {'năm' if paid else 'không lương'} {tu}",
                            "is_paid": paid, "annual_quota": 12},
                      headers=_h(token)).json()["id"]
    r = client.post("/api/leaves",
                    json={"employee_id": emp_id, "leave_type_id": tid,
                          "start_date": tu, "end_date": den},
                    headers=_h(token))
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    if duyet:
        assert client.post(f"/api/leaves/{rid}/approve", json={},
                           headers=_h(token)).status_code == 200
    return rid


def _o_luoi(client, token, emp_id, year, month, ngay):
    data = client.get(f"/api/attendance/shift-plan?year={year}&month={month}",
                      headers=_h(token)).json()
    row = next(r for r in data["rows"] if r["employee_id"] == emp_id)
    return row["days"][str(ngay)]


def test_phep_da_duyet_HIEN_tren_luoi_ma_KHONG_doi_o(client):
    """⭐ Cả điểm của "chỉ để xem": ô có dấu phép, nhưng ca/nguồn/`is_off` KHÔNG suy suyển.

    Người nghỉ phép vẫn ĐƯỢC PHÂN ca đó — chỉ là vắng mặt. Ghi đè ô thành "nghỉ" là mất thông tin
    họ thuộc ca nào."""
    token = _admin_token(client)
    emp = client.get("/api/employees/me", headers=_h(token)).json()["employee"]

    truoc = _o_luoi(client, token, emp["id"], 2026, 9, 10)
    _don_nghi(client, token, emp["id"], "2026-09-10", "2026-09-10")
    sau = _o_luoi(client, token, emp["id"], 2026, 9, 10)

    assert sau["leave_name"], "ngày nghỉ phép đã duyệt phải có dấu trên lưới"
    assert sau["leave_paid"] is True
    for k in ("shift_id", "source", "is_off"):
        assert sau[k] == truoc[k], f"lớp phủ KHÔNG được đụng `{k}`"


def test_doc_luoi_KHONG_ghi_gi_xuong_DB(client):
    """⭐ Đọc mà ghi là hỏng đúng thứ chủ chọn tránh.

    Nếu lỡ ghi vào `employee_shift_days` thì huỷ phiếu xong dấu vẫn nằm đó, và không ai biết ô đó
    do người tô hay do máy tô."""
    from app.models.employee import EmployeeShiftDay

    token = _admin_token(client)
    emp = client.get("/api/employees/me", headers=_h(token)).json()["employee"]
    _don_nghi(client, token, emp["id"], "2026-09-14", "2026-09-16")

    db = SessionLocal()
    try:
        truoc = db.query(EmployeeShiftDay).count()
    finally:
        db.close()

    client.get("/api/attendance/shift-plan?year=2026&month=9", headers=_h(token))

    db = SessionLocal()
    try:
        assert db.query(EmployeeShiftDay).count() == truoc, "đọc lưới KHÔNG được ghi dòng nào"
    finally:
        db.close()


def test_TU_CHOI_phieu_thi_dau_TU_BIEN_MAT(client):
    """⭐ Món lợi chính của lớp phủ so với ghi đè — và là lý do KHÔNG được "tối ưu" thành ghi đè.

    Không ai phải đi gỡ dấu tay; sửa phiếu là lưới đúng theo ngay."""
    token = _admin_token(client)
    emp = client.get("/api/employees/me", headers=_h(token)).json()["employee"]
    rid = _don_nghi(client, token, emp["id"], "2026-09-11", "2026-09-11")
    assert _o_luoi(client, token, emp["id"], 2026, 9, 11)["leave_name"]

    # Không từ chối được đơn đã duyệt ⇒ huỷ, đó mới là đường thật của nghiệp vụ.
    assert client.post(f"/api/leaves/{rid}/cancel", json={},
                       headers=_h(token)).status_code in (200, 204)
    assert _o_luoi(client, token, emp["id"], 2026, 9, 11)["leave_name"] is None, \
        "huỷ phiếu rồi mà dấu vẫn còn = lưới nói dối"


def test_phieu_CHO_DUYET_thi_KHONG_co_dau(client):
    """Chỉ `approved` mới hiện. Phiếu chờ duyệt mà đã tô lên lưới là người xếp ca tưởng đã chốt."""
    token = _admin_token(client)
    emp = client.get("/api/employees/me", headers=_h(token)).json()["employee"]
    _don_nghi(client, token, emp["id"], "2026-09-12", "2026-09-12", duyet=False)
    assert _o_luoi(client, token, emp["id"], 2026, 9, 12)["leave_name"] is None


def test_phieu_vat_qua_hai_thang_bi_CAT_dung_bien(client):
    """Phiếu 28/08→02/09: xem tháng 9 chỉ thấy ngày 1–2, không tràn sang ngày khác."""
    token = _admin_token(client)
    emp = client.get("/api/employees/me", headers=_h(token)).json()["employee"]
    _don_nghi(client, token, emp["id"], "2026-08-28", "2026-09-02")

    data = client.get("/api/attendance/shift-plan?year=2026&month=9", headers=_h(token)).json()
    row = next(r for r in data["rows"] if r["employee_id"] == emp["id"])
    co_dau = {int(k) for k, v in row["days"].items() if v["leave_name"]}
    assert co_dau == {1, 2}, f"phải đúng ngày 1–2 của tháng 9: {sorted(co_dau)}"


def test_bang_cong_va_luoi_noi_CUNG_MOT_chuyen(client):
    """Hai màn dùng CHUNG `_leave_map`. Chép ra hai bản là sớm muộn Bảng công bảo "có phép" còn
    lưới bảo "không", mà không ai biết bên nào đúng.

    ⚠️ So cho đúng khái niệm: ô Bảng công dùng CHÍNH field `leave` để hiện cả TÊN NGÀY LỄ
    (`attendance_service.py:1184`), nên phải loại ngày lễ ra trước khi đối chiếu — nếu không thì
    test đỏ vì 2/9, một lý do chẳng liên quan gì tới nghỉ phép."""
    token = _admin_token(client)
    emp = client.get("/api/employees/me", headers=_h(token)).json()["employee"]
    _don_nghi(client, token, emp["id"], "2026-09-17", "2026-09-18")

    luoi = client.get("/api/attendance/shift-plan?year=2026&month=9", headers=_h(token)).json()
    lrow = next(r for r in luoi["rows"] if r["employee_id"] == emp["id"])
    ngay_luoi = {int(k) for k, v in lrow["days"].items() if v["leave_name"]}

    ts = client.get("/api/attendance/timesheet?year=2026&month=9", headers=_h(token)).json()
    trow = next(r for r in ts["rows"] if r["employee_id"] == emp["id"])
    ngay_cong = {int(k) for k, v in trow["days"].items()
                 if v.get("leave") and not v.get("holiday")}

    assert ngay_luoi == ngay_cong == {17, 18}
    # Và ngày LỄ thì lưới KHÔNG gắn dấu phép — lễ không phải nghỉ phép.
    assert lrow["days"]["2"]["leave_name"] is None


def test_nghi_phep_KHONG_ro_sang_to_khac(client):
    """⭐ Ngày nghỉ của người tổ khác không được lọt sang lưới tổ mình.

    Chốt thật KHÔNG phải ở bộ lọc `_leave_map` mà ở `_employees_in_month`: người ngoài tầm nhìn
    không có DÒNG nào trên lưới nên không có chỗ để dán dấu. Test này canh đúng tính chất đó — nếu
    một ngày ai đó nới `_employees_in_month`, đây là thứ đỏ lên."""
    token = _admin_token(client)
    emp = client.get("/api/employees/me", headers=_h(token)).json()["employee"]
    _don_nghi(client, token, emp["id"], "2026-09-21", "2026-09-21")

    # Xem lưới của MỘT TỔ KHÁC với tổ của người vừa nghỉ.
    to_khac = _dept_id("Kho")
    assert to_khac != emp["department_id"], "kịch bản cần hai tổ khác nhau"
    data = client.get(
        f"/api/attendance/shift-plan?year=2026&month=9&department_id={to_khac}",
        headers=_h(token),
    ).json()

    assert all(r["employee_id"] != emp["id"] for r in data["rows"]), \
        "người tổ khác không được xuất hiện trên lưới"
    assert all(v["leave_name"] is None for r in data["rows"] for v in r["days"].values()), \
        "không được dính dấu nghỉ phép của người ngoài tổ"
