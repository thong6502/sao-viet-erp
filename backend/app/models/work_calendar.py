"""Lịch làm việc & Ngày lễ (module `nhan_su`, Pha 1 — nền dùng chung).

Hai bảng:
  - `work_calendar_config` — CẤU HÌNH tuần làm việc (7 thứ bật/tắt). 1 dòng active (id nhỏ
                             nhất), get-or-create như `payroll_params`. Không hardcode T7/CN.
  - `special_days`         — NGÀY ĐẶC BIỆT: nghỉ lễ (`off`) hoặc làm bù/hoán đổi (`work`),
                             theo ngày DƯƠNG cụ thể. Nguồn sự thật cho Chấm công / Nghỉ phép
                             / Lương hỏi chung ("ngày này có làm việc không / có phải lễ không").
Portable across SQLite/Postgres (Boolean `server_default` = true/false — né gotcha Postgres,
xem [[postgres-boolean-server-default]]).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# Loại ngày đặc biệt.
KIND_OFF = "off"    # nghỉ lễ / nghỉ hoán đổi (ngày lẽ ra làm nhưng nghỉ)
KIND_WORK = "work"  # làm bù (ngày lẽ ra nghỉ — T7/CN — nhưng đi làm để bù kỳ nghỉ dài)
SPECIAL_KINDS = (KIND_OFF, KIND_WORK)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WorkCalendarConfig(Base):
    """Cấu hình tuần làm việc — 1 dòng active (id nhỏ nhất). Mặc định T2–T7 làm, CN nghỉ."""

    __tablename__ = "work_calendar_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    works_mon: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    works_tue: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    works_wed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    works_thu: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    works_fri: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    works_sat: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    works_sun: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class SpecialDay(Base):
    """Một ngày đặc biệt (lễ/làm bù) theo ngày dương. `day` là KHÓA (1 ngày 1 bản ghi)."""

    __tablename__ = "special_days"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Ngày dương cụ thể — unique để lookup nhanh và tránh khai trùng.
    day: Mapped[date] = mapped_column(Date, unique=True, index=True, nullable=False)
    # 'off' = nghỉ lễ (mặc định); 'work' = làm bù (đảo trạng thái ngày theo tuần).
    kind: Mapped[str] = mapped_column(
        String(8), nullable=False, default=KIND_OFF, server_default=KIND_OFF
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # CHỈ có nghĩa với kind='off': lễ hưởng nguyên lương (điều 112 BLLĐ) → Bảng công cộng 1 công.
    # Giả định: is_paid = CÔNG TY trả 100%. Nghỉ nguồn BHXH (ốm/thai sản) KHÔNG khai vào đây.
    is_paid: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
