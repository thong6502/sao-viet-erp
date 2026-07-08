"""Vật liệu Kho — giấy / mực / bản kẽm (engine tính giá đọc từ đây), spec-tinh-gia §3.1.

"Thay Vật tư đã xóa" (spec-tinh-gia §11): engine đọc giá giấy/mực/bản bằng KHÓA KHO; thiếu
mặt hàng → LỖI (E-TG-KHO-MISS), KHÔNG âm thầm tính 0. `ban_kem` key theo `khoa_class` (khớp
máy) để tra giá kẽm (spec-cong-doan §5.1 `don_gia_kem = lookup(khoa_class)`).

Module MỚI (strangler) — song song `material.py` cũ tới khi engine mới thay. Chưa wired.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, Integer, JSON, Numeric, String,
    true as sa_true,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

THO = ("canh_dai", "canh_ngan")
DON_VI_GIA_GIAY = ("kg", "ram", "to")
LOAI_MUC = ("process", "pantone", "special")
KHOA_CLASS = ("52", "74", "79", "102", "custom")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GiayNguyen(Base):
    """Tờ giấy nguyên (khổ lớn để mua) — spec-tinh-gia §3.1."""

    __tablename__ = "giay_nguyen"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ma: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    ten: Mapped[str] = mapped_column(String(150), nullable=False)
    kho_dai: Mapped[int] = mapped_column(Integer, nullable=False)   # mm
    kho_rong: Mapped[int] = mapped_column(Integer, nullable=False)  # mm
    gsm: Mapped[int] = mapped_column(Integer, nullable=False)       # định lượng
    caliper_micron: Mapped[int | None] = mapped_column(Integer, nullable=True)  # độ dày (spine/creep; ≠ gsm)
    tho: Mapped[str | None] = mapped_column(String(12), nullable=True)          # canh_dai|canh_ngan
    don_vi_gia: Mapped[str] = mapped_column(String(8), nullable=False, server_default="kg", default="kg")
    don_gia: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0", default=0)
    ton: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, server_default="0", default=0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_true(), default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class Muc(Base):
    """Mực in — mặt hàng Kho. Tiền mực = don_gia × (số_lượt/1000) × số_màu_mặt (+coverage)."""

    __tablename__ = "muc"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ma: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    ten: Mapped[str] = mapped_column(String(150), nullable=False)
    loai_muc: Mapped[str] = mapped_column(String(12), nullable=False, server_default="process", default="process")
    ma_pantone: Mapped[str | None] = mapped_column(String(30), nullable=True)  # khi pantone/special
    don_gia: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0", default=0)  # /nghìn lượt
    # Bậc theo coverage (tùy chọn): [{coverage_pct_max, don_gia}, ...]
    coverage_tiers: Mapped[list | None] = mapped_column(JSON, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_true(), default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class BanKem(Base):
    """Bản kẽm — mặt hàng Kho. Giá tra theo `khoa_class` (khớp máy). kem_line §5.1."""

    __tablename__ = "ban_kem"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ma: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    ten: Mapped[str] = mapped_column(String(150), nullable=False)
    khoa_class: Mapped[str] = mapped_column(String(16), index=True, nullable=False)  # KHÓA tra giá
    don_gia_kem: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0", default=0)
    ton: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, server_default="0", default=0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_true(), default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
