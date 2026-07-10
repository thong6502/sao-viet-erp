"""Danh mục Giấy & Vật tư (Cấu hình danh mục).

- `ChungLoaiGiay`  — phân loại giấy (Couche/Ford/Bristol/Ivory/Duplex/Kraft…).
- `GiayNguyen`     — tờ giấy nguyên (khổ mua); ăn theo 1 Chủng loại giấy (`chung_loai_giay_id`).
- `VatTuInAn`      — vật tư in ấn GỘP (mực/kẽm/hoá chất/màng/keo…), phân bằng `loai_vat_tu`;
                     cột theo loại (mực: loai_muc/pantone/coverage; kẽm: khoa_class) để trống với loại khác.

Danh mục CRUD thuần (module bình bài/tính giá Hệ B đã gỡ) — không còn engine đọc để tính tiền.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean, Date, DateTime, Integer, JSON, Numeric, String,
    false as sa_false, true as sa_true,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

THO = ("canh_dai", "canh_ngan")
DON_VI_GIA_GIAY = ("kg", "cai", "ram", "to")
BE_MAT_GIAY = ("bong", "mo", "nham")
LOAI_MUC = ("process", "pantone", "special")
KHOA_CLASS = ("52", "74", "79", "102", "custom")
LOAI_VAT_TU = ("muc", "kem", "hoa_chat", "mang", "keo", "khac")
DON_VI_GIA_VAT_TU = ("kg", "lit", "nghin_luot", "ban", "cai", "bo", "thung", "met", "m2", "cuon")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ChungLoaiGiay(Base):
    """Chủng loại giấy — phân loại (Couche/Ford/Bristol/Ivory/Duplex/Kraft…). Giấy ăn theo đây."""

    __tablename__ = "chung_loai_giay"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ma: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    ten: Mapped[str] = mapped_column(String(150), nullable=False)
    be_mat: Mapped[str | None] = mapped_column(String(12), nullable=True)   # bong|mo|nham
    tho_mac_dinh: Mapped[str | None] = mapped_column(String(12), nullable=True)  # canh_dai|canh_ngan
    mo_ta: Mapped[str | None] = mapped_column(String(500), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_true(), default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class GiayNguyen(Base):
    """Tờ giấy nguyên (khổ lớn để mua) — ăn theo 1 Chủng loại giấy."""

    __tablename__ = "giay_nguyen"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ma: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    ten: Mapped[str] = mapped_column(String(150), nullable=False)
    chung_loai_giay_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)  # → chung_loai_giay.id
    kho_dai: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)   # mm; 0 = cuộn/khổ mở
    kho_rong: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)  # mm; 0 = cuộn/khổ mở
    gsm: Mapped[int] = mapped_column(Integer, nullable=False)       # định lượng
    caliper_micron: Mapped[int | None] = mapped_column(Integer, nullable=True)  # độ dày (spine/creep; ≠ gsm)
    tho: Mapped[str | None] = mapped_column(String(12), nullable=True)          # canh_dai|canh_ngan
    don_vi_gia: Mapped[str] = mapped_column(String(8), nullable=False, server_default="kg", default="kg")
    don_gia: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0", default=0)
    gia_thi_truong: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)   # giá tham khảo thị trường
    kho_tinh_gia: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_true(), default=True)  # khổ này dùng để tính giá?
    ghi_chu: Mapped[str | None] = mapped_column(String(500), nullable=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1", default=1)  # phiên bản giá hiện hành (mirror từ giay_gia_version)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_true(), default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class GiayGiaVersion(Base):
    """Phiên bản giá giấy — ẢNH CHỤP toàn bản ghi Giấy tại 1 mốc hiệu lực (lịch sử giá).

    Mỗi lần "Thêm phiên bản" đẻ 1 row; `is_current` = mốc đang áp dụng; `giay_nguyen` mirror
    các trường của version is_current. `giay_id` soft int → `giay_nguyen` (no DB FK).
    """

    __tablename__ = "giay_gia_version"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    giay_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)  # → giay_nguyen.id
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1", default=1)
    ngay_hieu_luc: Mapped[date | None] = mapped_column(Date, nullable=True)     # áp dụng từ ngày
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_true(), default=True)
    # -- ảnh chụp toàn bản ghi tại mốc này --
    kho_dai: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)
    kho_rong: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)
    gsm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    caliper_micron: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tho: Mapped[str | None] = mapped_column(String(12), nullable=True)
    don_vi_gia: Mapped[str] = mapped_column(String(8), nullable=False, server_default="kg", default="kg")
    don_gia: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0", default=0)
    gia_thi_truong: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    ghi_chu: Mapped[str | None] = mapped_column(String(500), nullable=True)     # lý do đổi (vd NCC tăng giá)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class VatTuInAn(Base):
    """Vật tư in ấn — danh mục PHẲNG (mực/kẽm/hoá chất/màng/keo… chung 1 bảng, phân biệt bằng TÊN).

    Đơn giản theo bảng xưởng: Mã · Tên · ĐVT · Giá · Ghi chú. Không phân loại, không tồn.
    """

    __tablename__ = "vat_tu_in_an"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ma: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    ten: Mapped[str] = mapped_column(String(150), nullable=False)
    don_vi_gia: Mapped[str] = mapped_column(String(16), nullable=False, server_default="cai", default="cai")
    don_gia: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0", default=0)
    ghi_chu: Mapped[str | None] = mapped_column(String(500), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_true(), default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class KhoGiayChuan(Base):
    """Khổ giấy chuẩn — mỗi dòng = 1 khổ của 1 chủng loại giấy (danh mục "DANH MỤC KHỔ GIẤY CHUẨN").

    Đơn vị **cm** (khớp bảng xưởng). `dai` trống = giấy cuộn/khổ mở — cắt tự do 1 chiều, chỉ chốt
    khổ rộng. `la_hiem` = khổ hiếm (báo thu mua/hỏi giấy trước khi dùng). Ăn theo 1 Chủng loại giấy
    (`chung_loai_giay_id`, soft ref — no DB FK).
    """

    __tablename__ = "kho_giay_chuan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ma: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    ten: Mapped[str] = mapped_column(String(150), nullable=False)
    chung_loai_giay_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)  # → chung_loai_giay.id
    rong: Mapped[int] = mapped_column(Integer, nullable=False)          # khổ rộng (cm)
    dai: Mapped[int | None] = mapped_column(Integer, nullable=True)     # khổ dài (cm); NULL = cuộn/mở 1 chiều
    la_hiem: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_false(), default=False)
    ghi_chu: Mapped[str | None] = mapped_column(String(500), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_true(), default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
