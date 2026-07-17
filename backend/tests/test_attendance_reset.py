"""VÀO/RA tự luân phiên THEO NGÀY CÔNG (Pha 2 — reset mỗi ngày, không kéo trạng thái xuyên ngày).

Bug cũ: quên chấm RA hôm qua → hôm nay lượt đầu bị hiểu là RA. Fix: reset theo ngày công.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db import SessionLocal
from app.repositories.attendance_repo import AttendanceRepository
from app.repositories.rbac_repo import DepartmentRepository
from app.repositories.user_repo import UserRepository

ADMIN = {"username": "admin", "password": "admin123"}


def _token(client) -> str:
    return client.post("/api/auth/login", json=ADMIN).json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _dept_id(name: str) -> int:
    db = SessionLocal()
    try:
        return DepartmentRepository(db).get_by_name(name).id
    finally:
        db.close()


def _uid(username: str) -> int:
    db = SessionLocal()
    try:
        return UserRepository(db).get_by_username(username).id
    finally:
        db.close()


def _emp_linked(client, token) -> dict:
    """Hồ sơ SẴN CÓ của admin (mọi tài khoản đều có hồ sơ — `backfill_employee_profiles`), nắn lại
    tên/phòng ban; KHÔNG tạo hồ sơ thứ 2 rồi gán (link tài khoản 1–1 sẽ chối)."""
    emp = client.get("/api/employees/me", headers=_h(token)).json()["employee"]
    client.put(
        f"/api/employees/{emp['id']}",
        json={"full_name": "NV Reset", "department_id": _dept_id("Hành chính nhân sự"),
              "hire_date": "2020-01-01"},
        headers=_h(token),
    )
    return emp


def _insert_log(employee_id: int, check_type: str, checked_at: datetime) -> None:
    db = SessionLocal()
    try:
        AttendanceRepository(db).create_log(
            employee_id=employee_id, check_type=check_type, checked_at=checked_at, within_range=True,
        )
    finally:
        db.close()


def test_next_action_resets_next_day(client):
    """Lượt VÀO hôm qua (quên RA) → hôm nay next_action vẫn là VÀO (reset), không phải RA."""
    t = _token(client)
    emp = _emp_linked(client, t)
    _insert_log(emp["id"], "in", datetime.now(timezone.utc) - timedelta(days=1))
    st = client.get("/api/attendance/me/status", headers=_h(t)).json()
    assert st["next_action"] == "in"


def test_next_action_out_after_in_same_day(client):
    """Đã VÀO trong NGÀY CÔNG hôm nay → next_action là RA."""
    t = _token(client)
    emp = _emp_linked(client, t)
    _insert_log(emp["id"], "in", datetime.now(timezone.utc))
    st = client.get("/api/attendance/me/status", headers=_h(t)).json()
    assert st["next_action"] == "out"
