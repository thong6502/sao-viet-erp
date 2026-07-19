"""Danh mục Kho hàng — KHAI BÁO kho (master data nhẹ).

Chỉ khai báo kho (mã / tên / vị trí / ghi chú) để đổ ra navbar và về sau gắn vận
hành (nhập / xuất / tồn). Bản này KHÔNG kèm tồn kho. Bảng MỚI → create_all tự dựng
(không cần migration; migration chỉ cho ALTER cột bảng cũ). Đặt tên `kho_hang` để
KHÔNG đụng bảng `warehouses` cũ (đã gỡ) có thể còn sót với schema khác.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, true as sa_true
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class KhoHang(Base):
    """1 dòng = 1 kho đã khai báo (vd "Kho thành phẩm")."""

    __tablename__ = "kho_hang"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ma: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    ten: Mapped[str] = mapped_column(String(150), nullable=False)          # "Kho thành phẩm"
    vi_tri: Mapped[str | None] = mapped_column(String(255), nullable=True)  # "Tầng 1 — xưởng A"
    ghi_chu: Mapped[str | None] = mapped_column(String(500), nullable=True)

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_true(), default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
