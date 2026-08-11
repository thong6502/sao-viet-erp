"""Khóa sổ kỳ kế toán kho (chốt sổ) — docs/spec-bao-cao-kho.md §6.

LOG APPEND-ONLY: mỗi lần khóa/mở ghi 1 bản ghi cho KHOẢNG ngày [tu_ngay, den_ngay] và một phạm vi
(`kho_id` NULL = toàn kho). `hanh_dong` = 'khoa' | 'mo'. Bảng vừa là HIỆU LỰC vừa là LỊCH SỬ:
phiếu tại (kho, ngày) bị khóa nếu bản ghi MỚI NHẤT (thuộc phạm vi phủ ngày đó) có hanh_dong='khoa'.
→ 'mo' ghi sau đè 'khoa' ghi trước; kho riêng đè toàn kho khi ghi sau.

Bảng MỚI → create_all tự dựng; đổi cấu trúc ở migration 0170.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class KhoKhoaSo(Base):
    """1 thao tác khóa/mở kỳ kế toán kho (append-only = hiệu lực + lịch sử)."""

    __tablename__ = "kho_khoa_so"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # NULL = toàn kho; có giá trị = 1 kho cụ thể.
    kho_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("kho_hang.id"), index=True, nullable=True
    )
    # Khóa/mở KHOẢNG [tu_ngay, den_ngay] theo NGÀY CHỨNG TỪ phiếu (bao gồm 2 đầu).
    tu_ngay: Mapped[date] = mapped_column(Date, nullable=False)
    den_ngay: Mapped[date] = mapped_column(Date, nullable=False)
    # 'khoa' = khóa kỳ; 'mo' = mở lại kỳ.
    hanh_dong: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default="khoa", default="khoa"
    )
    nguoi_khoa_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    khoa_luc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
