"""Ca kíp (module `nhan_su`, lát Chấm công): khai ca + tính CÔNG theo tỷ lệ giờ làm.

- Unit test công thức `compute_day_cong` (đủ giờ = 1,00; đi muộn/về sớm giảm theo tỷ lệ, giữ
  2 chữ số; dung sai; OT tính riêng; thiếu chấm ra = 0).
- API: CRUD ca + validation + RBAC + gán ca mặc định cho NV + timesheet có công theo ca.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password
from app.services.attendance_service import compute_day_cong

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

    listed = client.get("/api/attendance/shifts", headers=_h(token)).json()["items"]
    assert any(s["id"] == sid for s in listed)

    # end ≤ start mà không phải ca đêm → 400
    bad = client.post(
        "/api/attendance/shifts",
        json={"name": "x", "start_time": "17:00", "end_time": "08:00"},
        headers=_h(token),
    )
    assert bad.status_code == 400
    # ca đêm thì chấp nhận end < start
    night = client.post(
        "/api/attendance/shifts",
        json={"name": "Ca 3", "start_time": "22:00", "end_time": "06:00", "is_overnight": True, "night_shift": True},
        headers=_h(token),
    )
    assert night.status_code == 201 and night.json()["is_overnight"] is True

    upd = client.put(
        f"/api/attendance/shifts/{sid}",
        json={"name": "Hành chính (sửa)", "start_time": "08:30", "end_time": "17:30"},
        headers=_h(token),
    )
    assert upd.status_code == 200 and upd.json()["start_time"] == "08:30"

    assert client.delete(f"/api/attendance/shifts/{sid}", headers=_h(token)).status_code == 204


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
        json={"name": "Hành chính", "start_time": "08:00", "end_time": "17:00"},
        headers=_h(token),
    ).json()
    # NV gắn tài khoản admin + gán ca mặc định
    emp = client.post(
        "/api/employees",
        json={"full_name": "NV Ca", "department_id": _dept_id("Hành chính nhân sự"), "hire_date": "2020-01-01"},
        headers=_h(token),
    ).json()["employee"]
    client.post(f"/api/employees/{emp['id']}/account", json={"user_id": _uid("admin")}, headers=_h(token))
    upd = client.put(
        f"/api/employees/{emp['id']}",
        json={"full_name": "NV Ca", "default_shift_id": shift["id"]},
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
