"""Chốt công tháng (kỳ công — Pha 2, module `nhan_su`).

Kiểm: Chốt tạo snapshot + khóa · guard chặn khi còn đơn phép treo · chốt 2 lần bị chặn ·
Mở lại xóa snapshot về draft · mở kỳ chưa chốt bị chặn.
"""
from __future__ import annotations

from datetime import date

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
        json={"probation_end_date": "2025-12-31", "full_name": "NV Kỳ", "department_id": _dept_id("Hành chính nhân sự"), "hire_date": "2020-01-01"},
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


def test_metrics_map_live_bang_snapshot(client):
    """Mặt phân giới sang Lương phải GIỐNG HỆT trước và sau khi chốt công.

    Nối thêm chỉ số vào một nhánh mà quên nhánh kia là bom hẹn giờ: lương chạy đúng lúc còn
    nháp, rồi ĐỔI SỐ ngay khi HCNS bấm Chốt công."""
    from app.repositories.attendance_repo import AttendanceRepository
    from app.repositories.audit_repo import AuditLogRepository
    from app.repositories.employee_repo import EmployeeRepository
    from app.repositories.leave_repo import LeaveRepository
    from app.repositories.payroll_repo import PayrollRepository
    from app.repositories.calendar_repo import CalendarRepository
    from app.services.attendance_service import AttendanceService
    from app.services.calendar_service import CalendarService

    t = _token(client)
    _emp_with_leave(client, t, approve=True, start="2026-05-11", end="2026-05-11")

    def _metrics():
        db = SessionLocal()
        try:
            svc = AttendanceService(
                AttendanceRepository(db), EmployeeRepository(db), AuditLogRepository(db),
                leaves=LeaveRepository(db),
                calendar=CalendarService(CalendarRepository(db), AuditLogRepository(db)),
                payroll=PayrollRepository(db),
            )
            return svc.metrics_map(2026, 5)
        finally:
            db.close()

    live = _metrics()
    assert live, "bảng công tháng không có NV nào — kịch bản test hỏng, không phải engine"
    assert client.post("/api/attendance/period/lock", json={"year": 2026, "month": 5},
                       headers=_h(t)).status_code == 200
    snap = _metrics()

    assert set(live) == set(snap), f"lệch DANH SÁCH NV: {set(live) ^ set(snap)}"
    for eid in live:
        assert set(live[eid]) == set(snap[eid]), (
            f"NV {eid} lệch KEY live↔snapshot: {set(live[eid]) ^ set(snap[eid])}")
        for k in live[eid]:
            assert live[eid][k] == snap[eid][k], (
                f"NV {eid} lệch '{k}': live={live[eid][k]} snapshot={snap[eid][k]}")
    # Chỉ số mới phải THỰC SỰ có mặt (không phải cả hai cùng thiếu nên vô tình "bằng nhau")
    any_row = next(iter(live.values()))
    assert "excused_cong" in any_row and "paid_leave_days" in any_row
    # Đơn phép có lương 11/05 đã duyệt phải được đếm ở đâu đó
    assert sum(m["paid_leave_days"] for m in snap.values()) >= 1


# --- kỳ đã CHỐT phải khoá luôn đường sửa punch (chủ 27/07/2026) --------------


def _shift_for(client, token, eid, *, effective_from="2020-01-01") -> int:
    # Mốc ca KHÔNG được trước ngày vào làm; hồ sơ do `backfill_employee_profiles` sinh ra có
    # ngày vào làm là HÔM NAY, nên phải nắn trước khi gán.
    from app.repositories.employee_repo import EmployeeRepository
    db = SessionLocal()
    try:
        repo = EmployeeRepository(db)
        repo.update(repo.get_by_id(eid), hire_date=date.fromisoformat(effective_from))
    finally:
        db.close()
    sid = client.post("/api/attendance/shifts",
                      json={"name": f"Ca kỳ {eid}", "start_time": "08:00", "end_time": "17:00"},
                      headers=_h(token)).json()["id"]
    assert client.put(f"/api/employees/{eid}/shift",
                      json={"default_shift_id": sid, "effective_from": effective_from},
                      headers=_h(token)).status_code == 200
    return sid


def test_ky_da_chot_chan_cham_bu_va_yeu_cau_chinh_cong(client):
    """Chốt công = ĐÓNG BĂNG snapshot; Lương đọc snapshot chứ không đọc bảng công live.

    Cho chấm bù vào tháng đã chốt thì màn Chấm công đổi số mà phiếu lương KHÔNG đổi — hai bên
    lệch nhau âm thầm. `set_shift_plan` đã có guard này cho đường sửa CA; đường sửa PUNCH bị bỏ sót.
    """
    t = _token(client)
    emp = _emp_with_leave(client, t, approve=True, start="2026-05-11", end="2026-05-11")
    _shift_for(client, t, emp["id"])
    assert client.post("/api/attendance/period/lock", json={"year": 2026, "month": 5},
                       headers=_h(t)).status_code == 200

    manual = client.post("/api/attendance/adjust",
                         json={"employee_id": emp["id"], "date": "2026-05-12", "check_type": "in",
                               "time": "08:00", "reason": "bù sau khi đã chốt"},
                         headers=_h(t))
    assert manual.status_code == 400 and "đã chốt" in manual.json()["detail"]

    req = client.post("/api/attendance/me/adjust-request",
                      json={"date": "2026-05-12", "check_type": "in",
                            "suggested_time": "08:00", "reason": "quên chấm"},
                      headers=_h(t))
    assert req.status_code == 400 and "đã chốt" in req.json()["detail"]

    # Mở lại kỳ thì chấm bù được ngay.
    assert client.post("/api/attendance/period/reopen", json={"year": 2026, "month": 5},
                       headers=_h(t)).status_code == 200
    assert client.post("/api/attendance/adjust",
                       json={"employee_id": emp["id"], "date": "2026-05-12", "check_type": "in",
                             "time": "08:00", "reason": "bù sau khi mở lại"},
                       headers=_h(t)).status_code == 200


def test_don_treo_thang_khac_khong_chan_chot_thang_nay(client):
    """Đơn chỉnh công treo của THÁNG KHÁC không được chặn chốt tháng này — HCNS mở tháng này ra
    chẳng thấy nó đâu mà duyệt."""
    t = _token(client)
    _emp_with_leave(client, t, approve=True, start="2026-05-11", end="2026-05-11")
    # `/me/adjust-request` luôn tạo cho hồ sơ GẮN VỚI TÀI KHOẢN đăng nhập — không phải hồ sơ
    # vừa tạo ở trên. Gán ca cho đúng hồ sơ đó, nếu không sẽ rớt ở "chưa được gán ca".
    me_eid = client.get("/api/employees/me", headers=_h(t)).json()["employee"]["id"]
    _shift_for(client, t, me_eid)

    # Đơn treo thuộc THÁNG 7, trong khi ta chốt tháng 5.
    rr = client.post("/api/attendance/me/adjust-request",
                     json={"date": "2026-07-15", "check_type": "in",
                           "suggested_time": "08:00", "reason": "quên chấm"},
                     headers=_h(t))
    assert rr.status_code == 200, rr.text

    st = client.get("/api/attendance/period?year=2026&month=5", headers=_h(t)).json()
    assert st["pending_adjusts"] == 0, "đơn tháng 7 không được tính vào kỳ tháng 5"
    assert client.post("/api/attendance/period/lock", json={"year": 2026, "month": 5},
                       headers=_h(t)).status_code == 200
