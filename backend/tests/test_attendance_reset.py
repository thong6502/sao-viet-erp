"""VÀO/RA tự luân phiên THEO NGÀY CÔNG (Pha 2 — reset mỗi ngày, không kéo trạng thái xuyên ngày).

Bug cũ: quên chấm RA hôm qua → hôm nay lượt đầu bị hiểu là RA. Fix: reset theo ngày công.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db import SessionLocal
from app.repositories.attendance_repo import AttendanceRepository
from app.repositories.employee_repo import EmployeeRepository
from app.repositories.rbac_repo import DepartmentRepository
from app.repositories.user_repo import UserRepository
from app.services.attendance_service import CHECK_OUT_GRACE_HOURS, VN_TZ

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


def _assign_shift(employee_id: int) -> None:
    """Gán 1 ca hành chính cho NV. Chưa gán ca → next_action = None (chặn chấm) → phải gán trước khi
    test luồng VÀO/RA. Test mode KHÔNG seed work_shifts (SEED_DEMO=false) nên tự tạo ca + gán mặc định."""
    db = SessionLocal()
    try:
        shift = AttendanceRepository(db).create_shift(
            name="Hành chính", start_minute=480, end_minute=1020, is_overnight=False, grace_minutes=5,
        )
        emp = EmployeeRepository(db).get_by_id(employee_id)
        emp.default_shift_id = shift.id
        db.commit()
    finally:
        db.close()


def _emp_linked(client, token) -> dict:
    """Hồ sơ SẴN CÓ của admin (mọi tài khoản đều có hồ sơ — `backfill_employee_profiles`), nắn lại
    tên/phòng ban + GÁN CA (bắt buộc để có next_action); KHÔNG tạo hồ sơ thứ 2 rồi gán (link 1–1 sẽ chối)."""
    emp = client.get("/api/employees/me", headers=_h(token)).json()["employee"]
    client.put(
        f"/api/employees/{emp['id']}",
        json={"full_name": "NV Reset", "department_id": _dept_id("Hành chính nhân sự"),
              "hire_date": "2020-01-01"},
        headers=_h(token),
    )
    _assign_shift(emp["id"])
    return emp


def _insert_log(employee_id: int, check_type: str, checked_at: datetime) -> None:
    db = SessionLocal()
    try:
        AttendanceRepository(db).create_log(
            employee_id=employee_id, check_type=check_type, checked_at=checked_at, within_range=True,
        )
    finally:
        db.close()


def _vao_cua_ngay_cong_da_dong(shift_end_minute: int = 1020) -> datetime:
    """Mốc UTC cho một lượt VÀO thuộc NGÀY CÔNG đã ĐÓNG HẲN cửa sổ nhận-RA.

    `now() - 1 ngày` KHÔNG dựng được cảnh này: cửa sổ nhận RA của ngày công N kéo tới
    `hết ca + CHECK_OUT_GRACE_HOURS` = 17:00 + 8h = 01:00 ngày N+1 (tăng ca vượt nửa đêm).
    Chạy bộ test trong khung 00:00–01:00 giờ VN thì lượt "hôm qua" VẪN trong hạn ⇒ máy chủ trả
    `out` và bài đỏ — đúng như run 34506129364 (khởi 00:06 giờ VN). Đó là bài phụ thuộc đồng hồ
    thật, không phải sản phẩm sai.

    Nên lùi tới ngày công đầu tiên mà cửa sổ ấy đã đóng, rồi chấm VÀO lúc 08:30 — giờ trong ca,
    giống lượt thật, thay vì một mốc trôi theo giờ chạy máy."""
    now_local = datetime.now(timezone.utc).astimezone(VN_TZ)
    ngay = now_local.date() - timedelta(days=1)
    while (datetime(ngay.year, ngay.month, ngay.day, tzinfo=VN_TZ)
           + timedelta(minutes=shift_end_minute, hours=CHECK_OUT_GRACE_HOURS)) >= now_local:
        ngay -= timedelta(days=1)
    return datetime(ngay.year, ngay.month, ngay.day, 8, 30, tzinfo=VN_TZ).astimezone(timezone.utc)


def test_next_action_resets_next_day(client):
    """Lượt VÀO ngày công trước (quên RA) → hôm nay next_action vẫn là VÀO (reset), không phải RA."""
    t = _token(client)
    emp = _emp_linked(client, t)
    _insert_log(emp["id"], "in", _vao_cua_ngay_cong_da_dong())
    st = client.get("/api/attendance/me/status", headers=_h(t)).json()
    assert st["next_action"] == "in"


def test_next_action_out_after_in_same_day(client):
    """Đã VÀO trong NGÀY CÔNG hôm nay → next_action là RA."""
    t = _token(client)
    emp = _emp_linked(client, t)
    _insert_log(emp["id"], "in", datetime.now(timezone.utc))
    st = client.get("/api/attendance/me/status", headers=_h(t)).json()
    assert st["next_action"] == "out"
