"""Thiết bị / Máy (Machine · Cost Center) — master data, spec `docs/spec-may-thiet-bi.md`.

1 bảng master `may_thiet_bi`, phân biệt bằng `loai_may` (discriminator §3.2). Mỗi máy vừa là
**cost center** (mang BHR — đơn giá giờ giá vốn, §3.4/§4) vừa là **spec năng lực** (khổ, tốc độ…).

Chiến lược cột: các field CHUNG (§3.1/3.3–3.6) + các field engine hay đọc nhất của
`press_offset_sheet` (§3.7A: gripper_mm, kho_max/min, so_units, khoa_class, tự trở, bù hao…)
là **cột thật** (nullable — chỉ offset dùng). Các field đặc thù còn lại theo từng `loai_may`
(web/digital/flexo/gravure/wide/finishing/thue_ngoai + offset phụ) gói trong JSON
`fields_theo_loai` để tránh 100 cột chết. `active` KHÔNG có cột riêng — suy từ `trang_thai`.

Module MỚI theo kiến trúc rebuild (strangler): song song với `machine.py` cũ tới khi engine
mới thay xong. Chưa wired vào main.py/models __init__ (wiring gom 1 pass sau).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    false as sa_false,
    true as sa_true,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# --- Enums (khớp spec + engine) ---
LOAI_MAY = (
    "press_offset_sheet", "press_offset_web", "press_digital", "press_flexo_label",
    "press_gravure", "wide_format", "prepress_ctp", "finishing", "thue_ngoai", "other",
)
TRANG_THAI = ("active", "maintenance", "retired")          # active mới cho báo giá
NGUON_BHR = ("nhap_truc_tiep", "dung_tu_von")
KHAU_HAO = ("duong_thang", "so_du_giam_dan")
KHOA_CLASS = ("52", "74", "79", "102", "custom")           # lớp khổ máy → tra giá kẽm
DON_VI_TOC_DO = ("to_gio", "m2_gio", "cuon_gio", "luot_gio", "met_gio")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MayThietBi(Base):
    __tablename__ = "may_thiet_bi"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ---- §3.1 Nhận diện (mọi máy) ----
    ma: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    ten: Mapped[str] = mapped_column(String(150), nullable=False)
    loai_may: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    finishing_subtype: Mapped[str | None] = mapped_column(String(24), nullable=True)
    nhom_cost_center: Mapped[str | None] = mapped_column(String(30), nullable=True)  # in/che_ban/sau_in
    phong_ban_id: Mapped[int | None] = mapped_column(Integer, nullable=True)         # FK mềm (no DB FK)
    dia_diem: Mapped[str | None] = mapped_column(String(100), nullable=True)
    hang_san_xuat: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    so_seri: Mapped[str | None] = mapped_column(String(100), nullable=True)
    trang_thai: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="active", default="active"
    )
    ghi_chu: Mapped[str | None] = mapped_column(Text, nullable=True)
    ghi_chu_2: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ---- §3.3 Tài sản / tài chính ----
    ma_tai_san: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ma_TK_cost_center: Mapped[str | None] = mapped_column(String(50), nullable=True)
    nha_cung_cap: Mapped[str | None] = mapped_column(String(150), nullable=True)
    ngay_dua_vao_su_dung: Mapped[date | None] = mapped_column(Date, nullable=True)
    het_han_bao_hanh: Mapped[date | None] = mapped_column(Date, nullable=True)
    phuong_phap_khau_hao: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="duong_thang", default="duong_thang"
    )

    # ---- §3.4 Chi phí — BHR (giá vốn giờ máy) ----
    nguon_bhr: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="dung_tu_von", default="dung_tu_von"
    )
    don_gia_gio_BHR: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)  # nếu nhập trực tiếp
    von_dau_tu: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    gia_tri_thu_hoi: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0", default=0)
    nam_khau_hao: Mapped[int] = mapped_column(Integer, nullable=False, server_default="8", default=8)
    lai_von_pct: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    gio_lam_nam: Mapped[int] = mapped_column(Integer, nullable=False, server_default="2000", default=2000)
    availability_pct: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, server_default="85", default=85)
    productivity_pct: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, server_default="85", default=85)
    efficiency_pct: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, server_default="80", default=80)
    so_nhan_cong: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, server_default="1", default=1)
    luong_gio: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    luong_burden_pct: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, server_default="30", default=30)
    cong_suat_kW: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    he_so_tai_dien: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, server_default="0.65", default=0.65)
    don_gia_dien: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    bao_hiem_nam: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0", default=0)
    dien_tich_san_m2: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    don_gia_thue_m2_nam: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    bao_tri_gio: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    overhead_gio: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    markup_pct: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    ngay_cap_nhat_bhr: Mapped[date | None] = mapped_column(Date, nullable=True)

    # ---- §3.5 Năng lực / tốc độ ----
    toc_do: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    don_vi_toc_do: Mapped[str | None] = mapped_column(String(16), nullable=True)
    makeready_time_default: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)  # phút
    thoi_gian_rua_muc: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)       # phút
    min_stock_gsm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_stock_gsm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vat_lieu_ho_tro_class: Mapped[list | None] = mapped_column(JSON, nullable=True)
    so_may_song_song: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1", default=1)
    so_ca: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chi_so_dem_luot: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # ---- §3.6 Bảo trì ----
    ngay_bao_tri_gan_nhat: Mapped[date | None] = mapped_column(Date, nullable=True)
    chu_ky_bao_tri: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chu_ky_bao_tri_don_vi: Mapped[str | None] = mapped_column(String(8), nullable=True)  # gio|luot
    ngay_bao_tri_ke_tiep: Mapped[date | None] = mapped_column(Date, nullable=True)

    # ---- §3.7A press_offset_sheet — field engine hay đọc (promoted, nullable) ----
    kho_max_dai: Mapped[int | None] = mapped_column(Integer, nullable=True)   # ★ bình bài
    kho_max_rong: Mapped[int | None] = mapped_column(Integer, nullable=True)  # ★
    kho_min_dai: Mapped[int | None] = mapped_column(Integer, nullable=True)   # ★
    kho_min_rong: Mapped[int | None] = mapped_column(Integer, nullable=True)  # ★
    kho_kem_dai: Mapped[int | None] = mapped_column(Integer, nullable=True)   # khổ bản kẽm (mm)
    kho_kem_rong: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vung_in_dai: Mapped[int | None] = mapped_column(Integer, nullable=True)   # vùng in lớn nhất (mm)
    vung_in_rong: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gripper_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)    # mép nhíp trên BẢN KẼM (~44mm)
    # Nhíp GIẤY — cạnh máy kẹp tờ giấy, KHÁC `gripper_mm` (nhíp kẽm) cả về nghĩa lẫn độ lớn (~8-12mm).
    # ★ bình bài: trừ vào chiều DÀI tờ in (1 cạnh nạp), KHÔNG trừ chiều rộng.
    nhip_giay_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    le_hong_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)          # ★ trừ MỖI BÊN chiều rộng
    duoi_thang_mau_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)   # ★ trừ chiều dài (đuôi tờ)
    so_units: Mapped[int | None] = mapped_column(Integer, nullable=True)      # ★ đếm lượt/kẽm
    units_truoc: Mapped[int | None] = mapped_column(Integer, nullable=True)   # perfector
    units_sau: Mapped[int | None] = mapped_column(Integer, nullable=True)
    khoa_class: Mapped[str | None] = mapped_column(String(16), index=True, nullable=True)  # → giá kẽm
    co_tro_mat: Mapped[bool | None] = mapped_column(Boolean, nullable=True)   # perfector
    cho_phep_tu_tro: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # work-and-turn
    cho_phep_tro_dau_duoi: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    bu_hao_canh_may_per_mau: Mapped[int | None] = mapped_column(Integer, nullable=True)   # tờ/màu
    bu_hao_chay_pct: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)   # %
    ho_tro_cip3: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # ---- Field đặc thù còn lại theo loai_may (web/digital/flexo/gravure/wide/finishing/
    #      thue_ngoai + offset phụ: so_zone_muc, co_thap_phu, loai_phu, chi_phi_phu_per_m2…) ----
    fields_theo_loai: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    @property
    def active(self) -> bool:
        """`active` suy từ trang_thai — chỉ máy đang hoạt động mới cho báo giá (§3.1)."""
        return self.trang_thai == "active"
