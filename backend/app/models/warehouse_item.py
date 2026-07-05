"""Warehouse item model — module "Kho hàng" vận hành (nhân viên nhập).

Mỗi bản ghi là một mặt hàng cơ bản được nhập vào MỘT kho do admin đã cấu hình
(bảng `warehouses`). Ghi lại người nhập (created_by_user_id). Đây là MVP — về sau
có thể mở rộng thành phiếu nhập/xuất kho đầy đủ.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WarehouseItem(Base):
    __tablename__ = "warehouse_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Kho chứa — phải là kho admin đã cấu hình (dm_kho).
    warehouse_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("warehouses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[float] = mapped_column(
        Numeric(14, 2), CheckConstraint("quantity >= 0"), nullable=False, default=0
    )
    unit: Mapped[str] = mapped_column(String(32), nullable=False, default="cái")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Người nhập (spec-kho): nullable để không mất bản ghi khi user bị xóa.
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
