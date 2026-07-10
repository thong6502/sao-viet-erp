"""Kho — danh mục cấu hình HÀNH VI cho cỗ máy chứng từ (spec-13, DacTa 3.15/3.16).

- `WhItemStatus`  : trạng thái hàng (Khả dụng/Giữ chỗ/Chờ KCS/Lỗi/Hủy) — quyết định tồn khả dụng.
- `WhVoucherType` : loại phiếu — khai hành vi (chiều tồn, kho nguồn/đích, duyệt, MISA).
Bảng mới → create_all tự dựng.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class WhItemStatus(_TimestampMixin, Base):
    """Trạng thái hàng (DacTa 3.15). count_available quyết định tồn khả dụng."""

    __tablename__ = "wh_item_statuses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(24), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    count_on_hand: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    count_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_issue: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class WhVoucherType(_TimestampMixin, Base):
    """Loại phiếu — cỗ máy chứng từ (DacTa 3.16). Khai hành vi, không viết code riêng."""

    __tablename__ = "wh_voucher_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(24), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # nhap / xuat / dieu_chuyen / kiem_ke / dieu_chinh
    voucher_group: Mapped[str] = mapped_column(String(24), nullable=False, default="nhap")
    # tang / giam / chuyen_vi_tri / khong_tac_dong
    stock_effect: Mapped[str] = mapped_column(String(24), nullable=False, default="tang")
    require_src_wh: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    require_dst_wh: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    require_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sync_misa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # cờ, chưa hiện thực
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
