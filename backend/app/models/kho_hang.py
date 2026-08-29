"""Danh mục Kho hàng — KHAI BÁO kho (master data nhẹ).

Chỉ khai báo kho (mã / tên / vị trí / ghi chú) để đổ ra navbar và về sau gắn vận
hành (nhập / xuất / tồn). Bản này KHÔNG kèm tồn kho. Bảng MỚI → create_all tự dựng
(không cần migration; migration chỉ cho ALTER cột bảng cũ). Đặt tên `kho_hang` để
KHÔNG đụng bảng `warehouses` cũ (đã gỡ) có thể còn sót với schema khác.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    true as sa_true,
)
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


class KhoViTri(Base):
    """1 dòng = 1 VỊ TRÍ cất (kệ/ô) đã khai của MỘT kho. Danh sách này để khai lô chọn từ dropdown
    thay vì gõ tự do (`stock_lots.vi_tri`/`stock_voucher_lines.vi_tri` vẫn là chuỗi — chỉ dùng danh
    sách này làm GỢI Ý/chọn, không ràng buộc cứng để không vỡ dữ liệu cũ). Bảng MỚI → create_all tự
    dựng, KHÔNG cần migration."""

    __tablename__ = "kho_vi_tri"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kho_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("kho_hang.id", ondelete="CASCADE"), index=True, nullable=False
    )
    ma: Mapped[str] = mapped_column(String(60), nullable=False)   # "Kệ A - Ô 1", "Tầng 2 lô 3"…
    ghi_chu: Mapped[str | None] = mapped_column(String(255), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_true(), default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    __table_args__ = (
        # Không trùng tên vị trí trong CÙNG một kho (khác kho được trùng).
        UniqueConstraint("kho_id", "ma", name="uq_kho_vi_tri_kho_ma"),
    )
