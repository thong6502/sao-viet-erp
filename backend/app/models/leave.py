"""Leave management models (Nghỉ phép — module `nhan_su`).

Two tables:
  - `leave_types`    — catalog loại nghỉ do HR khai: tên + cờ có-lương + hạn mức/năm.
  - `leave_requests` — đơn xin nghỉ của 1 NV (từ ngày–đến ngày, nguyên ngày) qua workflow
                       chờ duyệt → duyệt / từ chối / hủy. Đơn ĐÃ DUYỆT được Bảng công tháng
                       đọc để đánh dấu ngày nghỉ (P/KL).
Portable across SQLite/Postgres.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_CANCELLED = "cancelled"
LEAVE_STATUSES = (STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED, STATUS_CANCELLED)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LeaveType(Base):
    """Loại nghỉ (HR khai): Phép năm / Ốm / Không lương / Việc riêng…"""

    __tablename__ = "leave_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Có lương hay không → tác động "công" trên Bảng công tháng (có lương = 1 công "P").
    is_paid: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    # Hạn mức ngày/năm (thông tin; trừ dần để module Lương xử lý sau). 0 = không giới hạn.
    annual_quota: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class LeaveRequest(Base):
    """Đơn xin nghỉ của 1 NV (nguyên ngày, từ start_date đến end_date bao gồm)."""

    __tablename__ = "leave_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Loại nghỉ (SET NULL nếu loại bị xoá sau). Nullable để tránh vỡ khi loại mất.
    leave_type_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("leave_types.id", ondelete="SET NULL"), index=True, nullable=True
    )
    start_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Số ngày nghỉ = số ngày lịch bao gồm 2 đầu (nguyên ngày; nghỉ nửa ngày ngoài phạm vi).
    days: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=STATUS_PENDING, server_default=STATUS_PENDING, index=True
    )
    decided_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
