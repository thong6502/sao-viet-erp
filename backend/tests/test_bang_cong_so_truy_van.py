"""Bảng công tháng: số truy vấn KHÔNG được chạy theo đầu người (11/09/2026).

Đây là bài canh một lỗi ĐÃ TRÔI NGƯỢC một lần. `monthly_timesheet` dựng `emp_cache` để khỏi hỏi
DB từng người, kèm hẳn ghi chú "bảng 100 NV bắn 100 query lẻ mỗi lần mở màn" — nhưng cache lại
nằm SAU vòng ghép lượt bấm, mà chính vòng đó mới là chỗ gọi `get_by_id`. Kết quả: đo ra đúng
N + 15 truy vấn cho N nhân viên, tuyến tính theo quân số, y như chưa từng có cache.

Kiểu lỗi này không làm đỏ bài nào và không sai một con số nào trên màn — chỉ chậm dần theo đà
tuyển người. Vì vậy phải khoá bằng SỐ ĐO, không phải bằng mắt.

Hai thứ file này khoá:
  1. Số truy vấn là HẰNG SỐ — thêm người không làm nó tăng.
  2. Lọc theo tổ phải làm NHẸ đi. Trước 11/09/2026 nó còn NẶNG GẤP ĐÔI xem cả xưởng:
     `emp_cache` chỉ có người của tổ, còn lượt bấm thì nạp cả xưởng ⇒ vòng ghép hỏi DB một lần
     cho mỗi người ngoài tổ, rồi vòng dựng hàng hỏi lại lần nữa.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import event

from app.db import SessionLocal, engine
from app.models.attendance import AttendanceLog
from app.models.department import Department
from app.models.employee import Employee
from app.repositories.attendance_repo import AttendanceRepository
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.calendar_repo import CalendarRepository
from app.repositories.employee_repo import EmployeeRepository
from app.repositories.leave_repo import LeaveRepository
from app.services.attendance_service import AttendanceService
from app.services.calendar_service import CalendarService

from .test_work_shifts_api import _admin_token, _mk_shift

VN = timezone(timedelta(hours=7))
NAM, THANG = 2026, 9

# Mỗi lượt dựng một tiền tố mã riêng — một bài có thể dựng người làm hai đợt, mà `code` là DUY NHẤT.
_dot = iter(range(1, 100))


def _dem_truy_van(fn):
    """Chạy `fn()` và đếm số câu SQL nó bắn ra."""
    dem = {"n": 0}

    def _ghi(conn, cursor, statement, parameters, context, executemany):
        dem["n"] += 1

    event.listen(engine, "before_cursor_execute", _ghi)
    try:
        kq = fn()
    finally:
        event.remove(engine, "before_cursor_execute", _ghi)
    return kq, dem["n"]


def _dung_nhan_su(so_nv: int, so_to: int = 4) -> list[int]:
    """`so_nv` nhân viên rải đều vào `so_to` tổ, mỗi người 2 lượt bấm/ngày làm việc.

    Trả về id các tổ (theo thứ tự tạo). Ghi thẳng qua ORM chứ không qua API: bài này đo TẢI, mà
    dựng 120 hồ sơ bằng 120 lượt POST thì mất vài phút và chẳng khoá thêm điều gì.
    """
    dot = next(_dot)
    db = SessionLocal()
    try:
        tos = []
        for i in range(so_to):
            t = Department(name=f"To do tai {dot}-{i + 1}", code=f"TDT{dot}{i + 1:02d}")
            db.add(t)
            tos.append(t)
        db.flush()

        nvs = []
        for i in range(so_nv):
            e = Employee(code=f"DT{dot}-{i + 1:04d}", full_name=f"Do Tai {dot}-{i + 1}",
                         department_id=tos[i % so_to].id, status="active",
                         hire_date=date(2024, 1, 1))
            db.add(e)
            nvs.append(e)
        db.flush()

        logs = []
        for e in nvs:
            for d in range(1, 29):
                if date(NAM, THANG, d).weekday() == 6:      # Chủ nhật: nghỉ
                    continue
                for gio, loai in ((8, "in"), (17, "out")):
                    logs.append(AttendanceLog(
                        employee_id=e.id, check_type=loai,
                        checked_at=datetime(NAM, THANG, d, gio, 0, tzinfo=VN)
                        .astimezone(timezone.utc)))
        db.bulk_save_objects(logs)
        db.commit()
        return [t.id for t in tos]
    finally:
        db.close()


def _svc(db):
    return AttendanceService(
        AttendanceRepository(db), EmployeeRepository(db), AuditLogRepository(db),
        leaves=LeaveRepository(db),
        calendar=CalendarService(CalendarRepository(db), AuditLogRepository(db)),
    )


def _bang_cong(department_id: int | None = None):
    """Gọi `monthly_timesheet` trên một phiên MỚI — phiên cũ còn identity map thì số đo là số giả."""
    db = SessionLocal()
    try:
        svc = _svc(db)
        kq, so = _dem_truy_van(
            lambda: svc.monthly_timesheet(year=NAM, month=THANG,
                                          department_id=department_id))
        return kq, so
    finally:
        db.close()


def test_so_truy_van_khong_chay_theo_dau_nguoi(client):
    """20 người và 120 người phải tốn CÙNG một số truy vấn."""
    token = _admin_token(client)
    _mk_shift(client, token, "Do tai HC", "08:00", "17:00")

    _dung_nhan_su(20)
    _bang_cong()                                # lượt nháp: cấu hình lịch được tạo lười ở lần đọc đầu
    nho, q_nho = _bang_cong()
    _dung_nhan_su(100, so_to=4)                 # cộng thêm 100 người nữa
    to, q_to = _bang_cong()

    assert len(to["rows"]) - len(nho["rows"]) == 100, "chưa dựng đủ người để bài đo có nghĩa"
    # Nới 2 câu cho biến động lặt vặt (seed lười, cấu hình đọc lần đầu); điều phải chặn là
    # chênh lệch TỈ LỆ THUẬN với 100 người vừa thêm.
    assert abs(q_to - q_nho) <= 2, (
        f"thêm 100 NV mà số truy vấn nhảy {q_nho} → {q_to}: N+1 đã quay lại "
        f"(xem `emp_cache` trong monthly_timesheet — nó phải nằm TRƯỚC vòng ghép lượt bấm)")


def test_loc_to_thi_nhe_di_chu_khong_nang_them(client):
    """Xem một tổ phải tốn ÍT HƠN xem cả xưởng — trước 11/09/2026 nó tốn gấp đôi."""
    token = _admin_token(client)
    _mk_shift(client, token, "Do tai HC2", "08:00", "17:00")
    tos = _dung_nhan_su(120, so_to=4)

    _bang_cong()                                # lượt nháp, xem bài trên
    ca_xuong, q_xuong = _bang_cong()
    mot_to, q_to = _bang_cong(department_id=tos[0])

    assert len(mot_to["rows"]) == 30, "120 người chia 4 tổ ⇒ mỗi tổ 30"
    assert len(ca_xuong["rows"]) >= 120
    # Lọc tổ tốn THÊM ĐÚNG MỘT câu (hỏi id nhân viên của tổ) rồi thôi. Nới 2 cho chắc, vẫn bắt
    # được bệnh cũ một cách dứt khoát: hồi đó lọc tổ tốn 964 truy vấn còn cả xưởng 515.
    assert q_to <= q_xuong + 2, (
        f"lọc tổ tốn {q_to} truy vấn trong khi xem cả xưởng chỉ tốn {q_xuong} — "
        f"`department_id` chưa đi vào `allowed`, nên vẫn nạp dữ liệu cả xưởng rồi vứt đi")


def test_loc_to_ra_dung_nguoi_cua_to(client):
    """Đi kèm bài trên: nhanh hơn mà trả sai người thì vô nghĩa."""
    token = _admin_token(client)
    _mk_shift(client, token, "Do tai HC3", "08:00", "17:00")
    tos = _dung_nhan_su(40, so_to=4)

    mot_to, _ = _bang_cong(department_id=tos[1])
    assert {r["department_id"] for r in mot_to["rows"]} == {tos[1]}
    assert len(mot_to["rows"]) == 10
    # Mỗi người vẫn phải có đủ ngày công như khi xem cả xưởng — `allowed` hẹp lại KHÔNG được
    # làm rơi lượt bấm của chính người trong tổ.
    ca_xuong, _ = _bang_cong()
    theo_id = {r["employee_id"]: r for r in ca_xuong["rows"]}
    for r in mot_to["rows"]:
        assert r["total_cong"] == theo_id[r["employee_id"]]["total_cong"]
        assert r["days"] == theo_id[r["employee_id"]]["days"]
