"""Lệnh sản xuất (LSX) — 1 DÒNG ĐƠN = 1 LỆNH, các lệnh NGANG HÀNG (không cha-con).

Mô hình 3 tầng chuẩn print MIS: Job (đơn hàng bán) → Part (`lsx`) → Operation (`lsx_cong_doan`).
Mỗi "chi tiết sản phẩm" đã tính giá (`PhieuThanhPhan`) mà khách CHỐT (thành `OrderLine`) sinh đúng
1 lệnh; lệnh nào cũng chạy độc lập dù cùng một đơn. Ghép bài (nhiều lệnh in chung 1 tờ) là tầng
KHÁC, dựng ở pha sau — KHÔNG gộp lệnh.

Quy cách + routing CHỤP SNAPSHOT lúc tạo (`quy_cach_json` + các dòng `lsx_cong_doan`): sau đó ai sửa
phiếu tính giá cũng không làm xê dịch lệnh đã phát ra, và kế hoạch sửa routing tại lệnh cũng không
ngược lên phiếu tính giá. Số lượng lấy từ ĐƠN HÀNG (`order_lines.qty` — bản cam kết bán), KHÔNG lấy
số lúc tính giá.

RBAC MODULE = "san_xuat". FK cha-con (`lsx_id`) + nguồn (`order_id`, `order_line_id`) là FK THẬT;
FK danh mục (máy, khuôn, công đoạn, tổ, user) là MỀM (plain int) theo convention soft-ref của repo.
Gotcha Postgres: Boolean default = `false()`/`true()` của SQLAlchemy, KHÔNG server_default "0"/"1".
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text,
    false as sa_false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base

# --- Loại lệnh (§13 spec) — lát 1 chỉ sinh `san_xuat_moi`; các loại sau nối ở pha bổ sung/bù/làm lại.
LOAI_MOI = "san_xuat_moi"
LOAI_BO_SUNG = "bo_sung"
LOAI_BU = "bu"
LOAI_LAM_LAI = "lam_lai"
LOAI_MAU = "mau"
LOAI_NOI_BO = "noi_bo"
LOAI_LSX = (LOAI_MOI, LOAI_BO_SUNG, LOAI_BU, LOAI_LAM_LAI, LOAI_MAU, LOAI_NOI_BO)

# --- Trạng thái — lát 1 dừng ở `san_sang`. Các mốc sau (`da_lap_ke_hoach`, `da_phat_hanh`,
# `dang_san_xuat`, `hoan_thanh`, `da_dong`) thuộc pha xếp lịch / thực thi, CHƯA dùng.
TT_NHAP = "nhap"                 # vừa tạo, dữ liệu đủ
TT_CHO_BO_SUNG = "cho_bo_sung"   # thiếu file/khuôn/quy cách/routing
TT_SAN_SANG = "san_sang"         # kế hoạch xác nhận đủ → chờ xếp lịch
TRANG_THAI_LSX = (TT_NHAP, TT_CHO_BO_SUNG, TT_SAN_SANG)
TRANG_THAI_SUA_DUOC = (TT_NHAP, TT_CHO_BO_SUNG, TT_SAN_SANG)  # chưa phát hành → sửa/xoá được

# --- Đơn vị đếm của 1 công đoạn (print MIS: mỗi operation có đơn vị riêng, đổi ở ranh giới xén).
DV_TO = "to"      # tờ in
DV_CAI = "cai"    # con / thành phẩm
DV_KEM = "kem"    # bộ kẽm (chế bản)
DON_VI_CONG_DOAN = (DV_TO, DV_CAI, DV_KEM)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Lsx(Base):
    __tablename__ = "lsx"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ma: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)  # LSX26-0001

    # --- Nhận diện ---
    loai: Mapped[str] = mapped_column(String(20), nullable=False, default=LOAI_MOI)
    # Lệnh bổ sung/bù/làm lại trỏ về lệnh gốc (pha sau; soft-ref để khỏi vướng cascade).
    lsx_goc_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    ten: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    # --- Nguồn (Job → Part) ---
    order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("orders.id"), index=True, nullable=False
    )
    order_line_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("order_lines.id"), index=True, nullable=False
    )
    # Phiên bản báo giá đã chốt (truy vết thương mại) + "chi tiết tính giá" nguồn. CẢ HAI là soft-ref
    # và chỉ để TRUY VẾT: `phieu_thanh_phan_id` KHÔNG đọc-sống để tính lại (id đổi mỗi lần lưu PTG vì
    # phiếu ghi kiểu replace-all) — mọi số của lệnh nằm ở snapshot dưới đây.
    quote_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    phieu_thanh_phan_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- Số lượng (MIS: Ordered → Planned; Produced thuộc pha thực thi) ---
    so_luong_dat: Mapped[int] = mapped_column(Integer, nullable=False, default=0)      # = order_lines.qty
    don_vi_tinh: Mapped[str] = mapped_column(String(30), nullable=False, default="cái")
    bu_hao_to: Mapped[int] = mapped_column(Integer, nullable=False, default=0)         # tờ bù (auto+tay)
    so_to_ke_hoach: Mapped[int] = mapped_column(Integer, nullable=False, default=0)    # tờ vào máy
    so_to_nguyen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)      # tờ giấy nguyên
    so_con: Mapped[int] = mapped_column(Integer, nullable=False, default=1)            # con/tờ

    # --- Thời gian (2 mốc: hạn khách từ đơn + hạn nội bộ do kế hoạch đặt) ---
    ban_giao_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    han_giao_khach: Mapped[date | None] = mapped_column(Date, nullable=True)
    han_hoan_thanh_sx: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_rush: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_false(), default=False
    )

    # --- Kỹ thuật ---
    # Snapshot quy cách lúc tạo: khổ ①②③ · giấy + định lượng · số màu A/B · cách in · chừa · số kẽm ·
    # số lượt · ghi chú kỹ thuật. READ-ONLY ở lát 1 (đổi giấy/màu/khổ = yêu cầu thay đổi kỹ thuật).
    quy_cach_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    khuon_be_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)  # → khuon_be.id
    may_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)       # → may_thiet_bi.id

    # --- Quản lý ---
    trang_thai: Mapped[str] = mapped_column(String(20), nullable=False, default=TT_NHAP)
    nguoi_phu_trach_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)  # → users.id
    ghi_chu: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    cong_doans: Mapped[list["LsxCongDoan"]] = relationship(
        "LsxCongDoan",
        back_populates="lsx",
        order_by="LsxCongDoan.thu_tu",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class LsxCongDoan(Base):
    """1 bước routing của lệnh (Operation) — copy từ `phieu_thanh_pham` lúc tạo, kế hoạch SỬA được.

    Mỗi bước tự mang SỐ LƯỢNG VÀO/RA + ĐƠN VỊ riêng vì đơn vị đổi qua ranh giới xén: chế bản đếm
    bộ kẽm, in/cán/bế đếm TỜ, dán/đóng gói đếm CON. Máy điền mặc định theo nhóm công đoạn, người
    kế hoạch quyết con số cuối.
    """

    __tablename__ = "lsx_cong_doan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lsx_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lsx.id", ondelete="CASCADE"), index=True, nullable=False
    )
    thu_tu: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    cong_doan_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)  # → cong_doan.id
    ten: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    nhom: Mapped[str | None] = mapped_column(String(12), nullable=True)  # prepress|print|finishing
    # Tổ nhận việc — snapshot `cong_doan.department_id` lúc copy (đổi danh mục sau không lay lệnh đã tạo).
    department_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    may_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)  # → may_thiet_bi.id

    so_luong_vao: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    so_luong_ra: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    don_vi: Mapped[str] = mapped_column(String(8), nullable=False, default=DV_TO)
    hao_hut: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)

    thue_ngoai: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_false(), default=False
    )
    nha_cung_cap: Mapped[str | None] = mapped_column(String(150), nullable=True)
    ghi_chu: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    lsx: Mapped["Lsx"] = relationship("Lsx", back_populates="cong_doans")
