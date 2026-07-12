"""Chốt công tháng (kỳ công — Pha 2, module `nhan_su`).

Kiểm: Chốt tạo snapshot + khóa · guard chặn khi còn đơn phép treo · chốt 2 lần bị chặn ·
Mở lại xóa snapshot về draft · mở kỳ chưa chốt bị chặn.
"""
from __future__ import annotations

from app.db import SessionLocal
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


def _emp_with_leave(client, token, *, approve: bool, start: str, end: str):
    """NV gắn tài khoản admin + 1 đơn nghỉ phép có lương (approved/pending) trong kỳ."""
    emp = client.post(
        "/api/employees",
        json={"full_name": "NV Kỳ", "department_id": _dept_id("Hành chính nhân sự"), "hire_date": "2020-01-01"},
        headers=_h(token),
    ).json()["employee"]
    client.post(f"/api/employees/{emp['id']}/account", json={"user_id": _uid("admin")}, headers=_h(token))
    tid = client.post("/api/leaves/types", json={"name": "Phép năm", "is_paid": True, "annual_quota": 12},
                      headers=_h(token)).json()["id"]
    req = client.post("/api/leaves", json={"leave_type_id": tid, "start_date": start, "end_date": end},
                      headers=_h(token))
    assert req.status_code == 201
    if approve:
        client.post(f"/api/leaves/{req.json()['id']}/approve", json={}, headers=_h(token))
    return emp


def test_lock_creates_snapshot_and_status(client):
    t = _token(client)
    _emp_with_leave(client, t, approve=True, start="2026-05-11", end="2026-05-11")  # Thứ 2
    r = client.post("/api/attendance/period/lock", json={"year": 2026, "month": 5}, headers=_h(t))
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "locked" and d["line_count"] >= 1 and d["hanging_days"] == 0
    g = client.get("/api/attendance/period", params={"year": 2026, "month": 5}, headers=_h(t)).json()
    assert g["status"] == "locked" and g["locked_at"] is not None


def test_lock_blocked_by_pending_leave(client):
    t = _token(client)
    _emp_with_leave(client, t, approve=False, start="2026-05-12", end="2026-05-12")  # pending
    r = client.post("/api/attendance/period/lock", json={"year": 2026, "month": 5}, headers=_h(t))
    assert r.status_code == 400  # còn đơn phép chưa duyệt → chặn chốt


def test_lock_twice_rejected(client):
    t = _token(client)
    _emp_with_leave(client, t, approve=True, start="2026-05-11", end="2026-05-11")
    assert client.post("/api/attendance/period/lock", json={"year": 2026, "month": 5}, headers=_h(t)).status_code == 200
    assert client.post("/api/attendance/period/lock", json={"year": 2026, "month": 5}, headers=_h(t)).status_code == 400


def test_reopen_clears_snapshot(client):
    t = _token(client)
    _emp_with_leave(client, t, approve=True, start="2026-05-11", end="2026-05-11")
    client.post("/api/attendance/period/lock", json={"year": 2026, "month": 5}, headers=_h(t))
    r = client.post("/api/attendance/period/reopen", json={"year": 2026, "month": 5}, headers=_h(t))
    assert r.status_code == 200 and r.json()["status"] == "draft" and r.json()["line_count"] == 0


def test_reopen_when_not_locked_rejected(client):
    t = _token(client)
    r = client.post("/api/attendance/period/reopen", json={"year": 2026, "month": 7}, headers=_h(t))
    assert r.status_code == 400
