"""Attendance / chấm công GPS models (module `nhan_su`, lát Chấm công).

Two tables:
  - `work_locations`  — điểm chấm công (geofence): toạ độ + bán kính cho phép. HR tạo nhiều
                        điểm (xưởng/kho/VP); nhân viên chấm khi ở gần BẤT KỲ điểm active nào.
  - `attendance_logs` — bản ghi chấm công của 1 nhân viên: thời điểm, toạ độ lúc chấm, điểm
                        khớp gần nhất, khoảng cách, VÀO/RA. Chốt "trong phạm vi" kiểm ở server.

Người chấm = user đăng nhập → hồ sơ NV qua `employees.user_id` (nên NV phải có tài khoản).
Portable across SQLite/Postgres (Numeric cho toạ độ; timestamp DB-agnostic).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# Trạng thái yêu cầu chỉnh công (NV gửi → HCNS duyệt):
REQ_PENDING = "pending"
REQ_APPROVED = "approved"
REQ_REJECTED = "rejected"
REQ_CANCELLED = "cancelled"

CHECK_IN = "in"
CHECK_OUT = "out"
CHECK_TYPES = (CHECK_IN, CHECK_OUT)

# fault_party cho punch điều chỉnh tay (ai chịu / vì sao bù công):
FAULT_NV_QUEN = "nv_quen"      # NV quên chấm
FAULT_MAY_HONG = "may_hong"    # máy chấm hỏng / mất điện / sự cố kỹ thuật
FAULT_DUYET = "duyet"          # được duyệt (công tác / họp / lý do chính đáng) — coi đủ công
FAULT_KHAC = "khac"            # khác (ghi rõ ở lý do)
FAULT_PARTIES = (FAULT_NV_QUEN, FAULT_MAY_HONG, FAULT_DUYET, FAULT_KHAC)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WorkLocation(Base):
    __tablename__ = "work_locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # WGS-84 decimal degrees. Numeric(10,7) ~ 1cm precision, portable + exact (no float drift).
    latitude: Mapped[float] = mapped_column(Numeric(10, 7), nullable=False)
    longitude: Mapped[float] = mapped_column(Numeric(10, 7), nullable=False)
    # Bán kính cho phép chấm công quanh điểm (mét).
    radius_m: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100, server_default="100"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class WorkShift(Base):
    """Ca làm việc (module `nhan_su`, lát Ca kíp). Giờ vào/ra lưu bằng PHÚT-từ-nửa-đêm
    (0..1439) cho dễ tính công; API phơi "HH:MM". Ca qua đêm (ca 3) đặt is_overnight."""

    __tablename__ = "work_shifts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # "Hành chính", "Ca 1"…
    start_minute: Mapped[int] = mapped_column(Integer, nullable=False)  # 8:00 = 480
    end_minute: Mapped[int] = mapped_column(Integer, nullable=False)    # 17:00 = 1020
    # Ca qua ngày (ra hôm sau, vd 22:00→06:00): cửa sổ ca = (1440−start)+end.
    is_overnight: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Ca đêm — cờ phụ cấp (engine đánh dấu; quy tiền để module Lương).
    night_shift: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Dung sai đi muộn (phút): vào trễ ≤ giá trị này vẫn coi đúng giờ.
    grace_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5, server_default="5"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class AttendanceLog(Base):
    __tablename__ = "attendance_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Điểm khớp gần nhất lúc chấm; SET NULL nếu điểm bị xoá sau này.
    work_location_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("work_locations.id", ondelete="SET NULL"), index=True, nullable=True
    )
    check_type: Mapped[str] = mapped_column(String(8), nullable=False)  # in / out
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True, nullable=False
    )
    # Toạ độ trình duyệt gửi lúc chấm (lưu để đối soát/audit).
    latitude: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    # Khoảng cách (mét) tới điểm khớp lúc chấm.
    distance_m: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    within_range: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Punch ĐIỀU CHỈNH TAY (HCNS chấm bù/sửa qua quyền nhan_su.adjust) — công tự tính lại từ đây.
    is_manual: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    adjust_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)   # lý do (bắt buộc khi manual)
    fault_party: Mapped[str | None] = mapped_column(String(20), nullable=True)      # nv_quen/may_hong/duyet/khac
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # HCNS thực hiện
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class AttendanceAdjustRequest(Base):
    """Yêu cầu chỉnh công: NV tự gửi (giải trình 1 ngày công) → HCNS duyệt/từ chối.
    Duyệt ⇒ sinh 1 punch điều chỉnh tay (AttendanceLog.is_manual) → công tự tính lại."""

    __tablename__ = "attendance_adjust_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    work_date: Mapped[date] = mapped_column(Date, nullable=False)     # ngày công cần chỉnh (giờ VN)
    check_type: Mapped[str] = mapped_column(String(8), nullable=False)  # in/out — punch NV đề nghị bù
    suggested_time: Mapped[str | None] = mapped_column(String(5), nullable=True)  # "HH:MM" gợi ý
    reason: Mapped[str] = mapped_column(String(500), nullable=False)  # NV giải trình
    fault_party: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=REQ_PENDING, server_default=REQ_PENDING, index=True
    )
    decided_by: Mapped[int | None] = mapped_column(Integer, nullable=True)       # HCNS
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    resulting_log_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # punch sinh khi duyệt
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


# --- Chốt công tháng (Pha 2) ------------------------------------------------

APERIOD_DRAFT = "draft"
APERIOD_LOCKED = "locked"
APERIOD_STATUSES = (APERIOD_DRAFT, APERIOD_LOCKED)


class AttendancePeriod(Base):
    """Kỳ CÔNG tháng (Chốt công). 1 dòng/(year,month): draft → locked = đóng băng Bảng công
    để Lương đọc bản đã khóa (không tính lại). Mirror payroll_periods."""

    __tablename__ = "attendance_periods"
    __table_args__ = (UniqueConstraint("year", "month", name="uq_attendance_period_ym"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    year: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    month: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, default=APERIOD_DRAFT, server_default=APERIOD_DRAFT, index=True
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class AttendancePeriodLine(Base):
    """Snapshot CÔNG của 1 NV trong 1 kỳ, đóng băng lúc Chốt. Lương đọc `total_cong` từ đây."""

    __tablename__ = "attendance_period_lines"
    __table_args__ = (UniqueConstraint("period_id", "employee_id", name="uq_attendance_period_line_pe"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    period_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("attendance_periods.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    total_cong: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0, server_default="0")
    total_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")      # ngày có chấm
    total_leave: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")     # tổng ngày nghỉ phép
    paid_leave_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0") # nghỉ phép CÓ lương
    unpaid_leave_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")  # nghỉ KHÔNG lương
    holiday_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")    # ngày nghỉ lễ hưởng công
    total_hours: Mapped[float] = mapped_column(Numeric(7, 2), nullable=False, default=0, server_default="0")
    ot_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")      # tổng phút vượt ca (chờ duyệt OT — Pha 4)
    night_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")      # số ngày làm ca đêm
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
