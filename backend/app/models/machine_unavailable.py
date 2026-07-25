"""Vùng máy KHÔNG khả dụng — khoảng THỜI GIAN 1 máy bị khóa (bảo trì/hỏng/nghỉ/khóa tay).

Xếp lịch (Gantt theo máy) đọc để: (a) engine NÉ khi cộng giờ / tìm khe trống, (b) Gantt vẽ vùng khóa
(curtains) trên lane. Tách khỏi "trạng thái máy" (cờ hiện tại) và "ngày bảo trì kế hoạch" (mức ngày) —
đây là khoảng [từ, đến) theo GIỜ, quản lý được nhiều khoảng/máy.

Bảng MỚI → `create_all` tự tạo, KHÔNG migration (giống `xep_lich_cong_doan`). FK máy MỀM theo convention
repo (soft → `may_thiet_bi.id`). Mọi mốc DateTime tz-aware (đọc từ SQLite là naive → service `_aware()`).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# Lý do khóa (tập MỞ — UI cho chọn, service không ràng cứng).
LY_DO_BAO_TRI = "bao_tri"    # bảo trì định kỳ / vệ sinh lớn / hiệu chuẩn
LY_DO_HONG_HOC = "hong_hoc"  # máy hỏng / sự cố
LY_DO_NGHI = "nghi"          # nghỉ theo lịch riêng máy (khác ngày nghỉ toàn xưởng)
LY_DO_KHAC = "khac"
LY_DO_KHOA = (LY_DO_BAO_TRI, LY_DO_HONG_HOC, LY_DO_NGHI, LY_DO_KHAC)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MachineUnavailablePeriod(Base):
    """1 khoảng thời gian 1 máy không chạy được."""

    __tablename__ = "machine_unavailable_periods"
    # Query theo máy + khoảng thời gian (né khe / vẽ nền).
    __table_args__ = (
        Index("ix_may_khoa_may_time", "may_id", "unavailable_from"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    may_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)  # soft → may_thiet_bi.id
    reason: Mapped[str] = mapped_column(String(16), nullable=False, default=LY_DO_BAO_TRI)
    unavailable_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    unavailable_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)  # soft → users.id
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
