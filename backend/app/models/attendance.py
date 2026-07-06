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

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

CHECK_IN = "in"
CHECK_OUT = "out"
CHECK_TYPES = (CHECK_IN, CHECK_OUT)


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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
