"""Kho — Đợt kiểm kê & phiếu điều chỉnh tồn (DacTa ch.8, spec-13 C).

So tồn HỆ THỐNG với tồn THỰC TẾ → khi duyệt tự sinh StockMove điều chỉnh chênh lệch.
Bảng mới → create_all tự dựng.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StockCount(Base):
    __tablename__ = "stock_counts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(24), unique=True, index=True, nullable=False)
    warehouse_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("warehouses.id"), index=True, nullable=False
    )
    # open (đang đếm) / posted (đã ghi điều chỉnh) / cancelled
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", index=True)
    participants: Mapped[str | None] = mapped_column(Text, nullable=True)  # người/ban tham gia kiểm kê
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    posted_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    lines: Mapped[list["StockCountLine"]] = relationship(
        back_populates="count", cascade="all, delete-orphan"
    )


class StockCountLine(Base):
    __tablename__ = "stock_count_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    count_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stock_counts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    material_id: Mapped[int] = mapped_column(Integer, ForeignKey("materials.id"), nullable=False)
    lot_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("stock_lots.id"), nullable=True)
    # Tồn HỆ THỐNG lúc chốt đợt (snapshot).
    system_qty: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False, default=0)
    # Tồn THỰC ĐẾM (null = chưa đếm → bỏ qua khi ghi điều chỉnh).
    counted_qty: Mapped[float | None] = mapped_column(Numeric(18, 3), nullable=True)
    # "Trong đó" (thuộc số thực đếm): kém phẩm chất / mất phẩm chất — ghi nhận để báo cáo.
    defective_qty: Mapped[float | None] = mapped_column(Numeric(18, 3), nullable=True)
    damaged_qty: Mapped[float | None] = mapped_column(Numeric(18, 3), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)  # lý do chênh lệch

    count: Mapped["StockCount"] = relationship(back_populates="lines")
