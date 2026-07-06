"""Chấm công GPS (module `nhan_su`, lát Chấm công).

Work-location config (HR-gated), Haversine geofence with hard block outside the radius,
auto VÀO/RA toggling, self check-in gated on a linked employee, and the RBAC boundary.
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
        existing = users.get_by_username("sales-att")
        if existing is not None:
            return create_access_token(str(existing.id))
        kd = DepartmentRepository(db).get_by_name("Kinh doanh")
        role = RoleRepository(db).get_by_name_and_department("NV Sales", kd.id)
        u = users.create(username="sales-att", name="S", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=kd.id, role_id=role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def _make_location(client, token, *, lat=10.0, lng=106.0, radius=200) -> int:
    return client.post(
        "/api/attendance/locations",
        json={"name": "Xưởng demo", "latitude": lat, "longitude": lng, "radius_m": radius},
        headers=_h(token),
    ).json()["id"]


def _link_admin_employee(client, token) -> int:
    """Create an employee and link it to the admin account so admin can self check-in."""
    emp = client.post(
        "/api/employees",
        json={"full_name": "NV Admin", "department_id": _dept_id("Hành chính nhân sự"), "hire_date": "2020-01-01"},
        headers=_h(token),
    ).json()["employee"]
    client.post(f"/api/employees/{emp['id']}/account", json={"user_id": _uid("admin")}, headers=_h(token))
    return emp["id"]


# --- work locations ---------------------------------------------------------


def test_location_crud_and_validation(client):
    token = _admin_token(client)
    lid = _make_location(client, token)
    assert lid > 0
    listed = client.get("/api/attendance/locations", headers=_h(token)).json()["items"]
    assert any(l["id"] == lid for l in listed)

    # invalid latitude → 422 (schema)
    bad = client.post(
        "/api/attendance/locations",
        json={"name": "x", "latitude": 999, "longitude": 10, "radius_m": 100},
        headers=_h(token),
    )
    assert bad.status_code == 422
    # zero radius → 422
    bad2 = client.post(
        "/api/attendance/locations",
        json={"name": "x", "latitude": 10, "longitude": 10, "radius_m": 0},
        headers=_h(token),
    )
    assert bad2.status_code == 422


# --- geofenced self check-in ------------------------------------------------


def test_check_in_out_toggle_and_hard_block(client):
    token = _admin_token(client)
    _make_location(client, token, lat=10.0, lng=106.0, radius=200)
    _link_admin_employee(client, token)

    status = client.get("/api/attendance/me/status", headers=_h(token)).json()
    assert status["has_employee"] is True
    assert status["next_action"] == "in"

    # AT the location → check VÀO
    r1 = client.post("/api/attendance/check", json={"latitude": 10.0, "longitude": 106.0}, headers=_h(token)).json()
    assert r1["success"] is True and r1["within_range"] is True and r1["check_type"] == "in"
    assert r1["log"] is not None

    # again → auto toggle to RA
    r2 = client.post("/api/attendance/check", json={"latitude": 10.0, "longitude": 106.0}, headers=_h(token)).json()
    assert r2["success"] is True and r2["check_type"] == "out"

    # far away (~150km) → hard block, no log
    r3 = client.post("/api/attendance/check", json={"latitude": 11.0, "longitude": 107.0}, headers=_h(token)).json()
    assert r3["success"] is False and r3["within_range"] is False
    assert r3["log"] is None and r3["distance_m"] > 200

    logs = client.get("/api/attendance/me/logs", headers=_h(token)).json()["items"]
    assert len(logs) == 2  # only the two in-range checks were recorded
    assert {l["check_type"] for l in logs} == {"in", "out"}


def test_check_without_linked_employee_is_400(client):
    token = _admin_token(client)
    _make_location(client, token)
    # admin has no linked employee in this test → check is rejected
    r = client.post("/api/attendance/check", json={"latitude": 10.0, "longitude": 106.0}, headers=_h(token))
    assert r.status_code == 400
    assert client.get("/api/attendance/me/status", headers=_h(token)).json()["has_employee"] is False


def test_check_with_no_location_configured(client):
    token = _admin_token(client)
    _link_admin_employee(client, token)
    r = client.post("/api/attendance/check", json={"latitude": 10.0, "longitude": 106.0}, headers=_h(token)).json()
    assert r["success"] is False and "Chưa cấu hình" in r["message"]


def test_hr_logs_list_shows_employee_name(client):
    token = _admin_token(client)
    _make_location(client, token, lat=10.0, lng=106.0, radius=200)
    _link_admin_employee(client, token)
    client.post("/api/attendance/check", json={"latitude": 10.0, "longitude": 106.0}, headers=_h(token))

    logs = client.get("/api/attendance/logs", headers=_h(token)).json()["items"]
    assert len(logs) == 1
    assert logs[0]["employee_name"] == "NV Admin"
    assert logs[0]["location_name"] == "Xưởng demo"


# --- bảng công tháng --------------------------------------------------------


def _vn_year_month() -> tuple[int, int]:
    from datetime import datetime, timedelta, timezone

    vn = datetime.now(timezone(timedelta(hours=7)))
    return vn.year, vn.month


def test_monthly_timesheet_and_csv(client):
    token = _admin_token(client)
    _make_location(client, token, lat=10.0, lng=106.0, radius=200)
    _link_admin_employee(client, token)
    # VÀO rồi RA cùng ngày (VN) → 1 ngày công có đủ giờ vào/ra
    client.post("/api/attendance/check", json={"latitude": 10.0, "longitude": 106.0}, headers=_h(token))
    client.post("/api/attendance/check", json={"latitude": 10.0, "longitude": 106.0}, headers=_h(token))

    year, month = _vn_year_month()
    ts = client.get(f"/api/attendance/timesheet?year={year}&month={month}", headers=_h(token)).json()
    assert ts["year"] == year and ts["month"] == month
    assert ts["days_in_month"] in (28, 29, 30, 31)
    row = next(r for r in ts["rows"] if r["employee_name"] == "NV Admin")
    assert row["total_days"] == 1
    # đúng 1 ô ngày có giờ vào + giờ ra
    day = next(iter(row["days"].values()))
    assert day["first_in"] and day["last_out"] and day["hours"] is not None

    # CSV: 200 + text/csv + có tên nhân viên
    csv_resp = client.get(f"/api/attendance/timesheet.csv?year={year}&month={month}", headers=_h(token))
    assert csv_resp.status_code == 200
    assert "text/csv" in csv_resp.headers["content-type"]
    assert "NV Admin" in csv_resp.text


def test_timesheet_forbidden_without_permission(client):
    token = _sales_token()
    year, month = _vn_year_month()
    assert client.get(f"/api/attendance/timesheet?year={year}&month={month}", headers=_h(token)).status_code == 403


# --- RBAC -------------------------------------------------------------------


def test_locations_config_forbidden_without_permission(client):
    token = _sales_token()
    assert client.get("/api/attendance/locations", headers=_h(token)).status_code == 403
    assert client.post(
        "/api/attendance/locations",
        json={"name": "x", "latitude": 10, "longitude": 10, "radius_m": 100},
        headers=_h(token),
    ).status_code == 403
