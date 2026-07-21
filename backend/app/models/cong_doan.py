"""Công đoạn (Operation · Routing) — danh mục thao tác + cách tính giá, spec `docs/spec-cong-doan.md` §2.

TẦNG 1 `cong_doan` (danh mục master, ở đây). TẦNG 2 `routing_step` (instance per job) để Phase D
(engine tính giá + jobspec) — chưa dựng vì cần FK jobspec/component. Engine cost/cascade/kẽm =
hàm thuần trong `services/routing_engine.py` (Phase D gọi).

Module MỚI (strangler) — song song `operation.py` cũ. Chưa wired. `may_id` = FK MỀM (plain int)
tới `may_thiet_bi.id` (khớp convention soft-ref của repo này, tránh coupling tạo bảng).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, Integer, JSON, Numeric, String, Text,
    false as sa_false, true as sa_true,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

NHOM = ("prepress", "print", "finishing")
CHE_DO_TINH = ("theo_san_luong",)  # "theo_gio" đã gỡ — công đoạn chỉ tính theo công thức/sản lượng
# Đơn vị tính giá công đoạn (bao trùm chế bản + in + sau in). Engine `routing_engine.basis_qty`
# quy đổi mỗi key → số lượng tính tiền từ ctx job.
PRICING_BASIS = (
    "per_sheet",          # Theo số tờ in
    "per_finished_area",  # Theo diện tích thành phẩm (cm²)
    "per_finished_qty",   # Theo số lượng thành phẩm
    "per_book_page",      # Theo số trang sách
    "per_position",       # Theo số vị trí
    "per_bag",            # Theo bao
    "per_carton",         # Theo thùng
    "per_area_sides",     # Theo diện tích (cm²) và số mặt
    "per_sheet_area",     # Theo diện tích tờ in (cm²)
    "per_book_page_q4",   # Theo số trang sách chia 4
    "per_job",            # Trọn gói một lần (cả đơn) — engine ÷ SL ở đơn giá bình quân (khuôn bế…)
    "per_other",          # Khác (nhập tay, giá phẳng)
)
TOOLING_TYPE = ("khuon_be", "khuon_ep", "kem")
# Cách công đoạn tính bù hao: không / tra bảng (trỏ 1 mã bù hao ở module Bù hao → tra bậc SL) /
# cộng cố định `so_to_bu_hao` tờ (ép kim, UV… — không theo bảng).
KIEU_BU_HAO = ("khong", "tra_bang", "co_dinh")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CongDoan(Base):
    __tablename__ = "cong_doan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ma: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    ten: Mapped[str] = mapped_column(String(150), nullable=False)
    ten_hien_thi: Mapped[str | None] = mapped_column(String(150), nullable=True)  # tên in cho thợ sản xuất
    # Bù hao: cách công đoạn này góp hao. tra_bang → trỏ 1 mã bù hao (`bu_hao_id`) rồi tra bậc theo
    # SL; co_dinh → cộng `so_to_bu_hao` tờ; khong → không góp.
    kieu_bu_hao: Mapped[str] = mapped_column(String(16), nullable=False, server_default="khong", default="khong")
    bu_hao_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)  # → bu_hao.id (soft) khi kieu=tra_bang
    so_to_bu_hao: Mapped[int] = mapped_column(Integer, nullable=False, server_default="50", default=50)  # +tờ hao khi kieu_bu_hao=co_dinh
    nhom: Mapped[str] = mapped_column(String(12), index=True, nullable=False)  # prepress|print|finishing
    may_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)  # → may_thiet_bi.id (soft)
    # Phòng ban / tổ phụ trách công đoạn (soft-ref → departments.id). Khi phát Lệnh SX, mỗi bước
    # công đoạn đẩy xuống đúng tổ này. Nullable: công đoạn cũ chưa gán vẫn hợp lệ.
    department_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)  # → departments.id (soft)
    # Lương khoán: công đoạn này có tính khoán không — nguoi (ghi Phiếu sản lượng theo từng người
    # → cột Khoán bảng lương) / khong (không khoán). Không còn 'theo tổ' (đã bỏ tầng sổ khoán).
    khoan_ghi_theo: Mapped[str] = mapped_column(String(8), nullable=False, server_default="khong", default="khong")
    # Pha 5b-2 trừ lỗi: ngưỡng hao CHO PHÉP (không bị trừ dù hỏng). Trừ = phần VƯỢT max(SL×pct, abs)
    # × đơn giá, chỉ khi lỗi DO THỢ, sàn 0. abs = số tuyệt đối (canh máy) chống trừ oan job nhỏ.
    allowed_defect_pct: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False, server_default="0", default=0)
    allowed_defect_abs: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, server_default="0", default=0)

    # Trục tính tiền (khác đơn vị đo)
    che_do_tinh: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="theo_san_luong", default="theo_san_luong"
    )
    pricing_basis: Mapped[str | None] = mapped_column(String(32), nullable=True)  # khi theo_san_luong

    setup_cost: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0", default=0)
    setup_time: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False, server_default="0", default=0)  # phút
    run_rate: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)   # đơn giá theo basis
    rate_tiers: Mapped[list | None] = mapped_column(JSON, nullable=True)            # [{from_qty,rate,kieu,driver}]
    # Bậc đơn giá theo KÍCH THƯỚC thành phẩm (cạnh dài, cm): [{den_cm, don_gia}] — "≤ den_cm → đơn giá".
    # Khi có, engine chọn đơn giá theo cỡ (thay run_rate); vd công dán ≤20cm=100 · 20–40=200 · 40–100=800.
    size_tiers: Mapped[list | None] = mapped_column(JSON, nullable=True)
    first_unit_floor: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)  # sàn bậc đầu (≠ min_charge)
    min_charge: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)         # sàn cả công đoạn

    requires_tooling: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_false(), default=False)
    tooling_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    spoilage_pct: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, server_default="0", default=0)  # KHÔNG áp bước in
    inline_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_false(), default=False)
    cong_thuc_gia: Mapped[str | None] = mapped_column(Text, nullable=True)
    ghi_chu: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_true(), default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
