"""Phiếu tăng ca (module `tang_ca`).

Một bảng:
  - `overtime_requests` — phiếu xin tăng ca của 1 NV cho MỘT ngày công: NV tự gửi rồi tổ trưởng
                          duyệt, HOẶC tổ trưởng tạo thẳng (duyệt luôn).

Nguyên tắc (chốt với chủ 23/07/2026): **lượt bấm RA = SỰ THẬT · phiếu = GIẤY PHÉP + MỨC TRẦN**.
Bảng công chỉ trả tiền phần giờ vượt ca NẰM TRONG phiếu đã duyệt; không có phiếu thì vẫn đủ công
ca chính, chỉ KHÔNG ra tiền tăng ca. Máy KHÔNG tự điền giờ ra từ phiếu (người về sớm phải lộ ra).
Portable across SQLite/Postgres.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_CANCELLED = "cancelled"
OVERTIME_STATUSES = (STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED, STATUS_CANCELLED)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OvertimeRequest(Base):
    """Phiếu tăng ca của 1 NV cho 1 NGÀY CÔNG."""

    __tablename__ = "overtime_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # NGÀY CÔNG của ca gốc (ngày VÀO ca), KHÔNG phải ngày dương lịch lúc tan ca — khớp đúng cách
    # Bảng công tháng gom ca qua đêm.
    work_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    # Khoảng tăng ca tính bằng PHÚT TỪ 00:00 CỦA `work_date`, trên cùng trục tuyến tính mà
    # `compute_day_cong` dùng ⇒ vượt nửa đêm thì > 1440 (vd 03:00 hôm sau = 1620). Dùng số phút
    # thay vì cờ "qua đêm" để né gotcha Boolean server_default vỡ Postgres.
    from_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    to_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=STATUS_PENDING, server_default=STATUS_PENDING, index=True
    )
    decided_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    # Chuông Topbar: thời điểm NGƯỜI NỘP đã xem kết quả (duyệt/từ chối). NULL = chưa xem → đếm vào
    # chuông. Timestamp, KHÔNG Boolean (né gotcha server_default vỡ Postgres).
    seen_by_employee_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
