"""Phiếu tính giá (Costing ticket) — mô hình THEO THÀNH PHẦN (component-based).

1 phiếu = header + NHIỀU "Thành phần" (mỗi thành phần = 1 tờ giấy riêng: giấy + kỹ thuật in
+ màu + gia công sau in). Mỗi thành phần lại có NHIỀU dòng "công đoạn sau in" (finishing).
Engine tính giá vốn từng thành phần rồi CỘNG lại → `tong_gia_von` / `gia_von_don`.

Thay cho mô hình 1-form cũ (số con/màu/mặt + 1 giấy nằm ngay header): các trường đó DỜI xuống
`phieu_thanh_phan`. Header chỉ giữ thông tin chung + ảnh chụp kết quả engine.

Module MỚI (song song máy tính stateless). RBAC MODULE quyền = "tinh_gia_thanh".
Các FK danh mục là MỀM (plain int) — khớp convention soft-ref của repo. FK cha-con trong phiếu
(`phieu_id`, `thanh_phan_id`) là FK THẬT để cascade xoá + quan hệ ORM.
Gotcha Postgres: JSON default = `default=list`/`default=dict` (Python), KHÔNG server_default;
Boolean default = Python True/False, KHÔNG server_default.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, true as sa_true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PhieuTinhGia(Base):
    __tablename__ = "phieu_tinh_gia"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ma: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)  # PTG-2026-0001

    # --- Thông tin phiếu ---
    ten_san_pham: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    kho_thanh_pham: Mapped[str | None] = mapped_column(String(100), nullable=True)   # spec tự do, vd "20×30×5 cm"
    loai_san_pham_id: Mapped[int | None] = mapped_column(Integer, nullable=True)    # → loai_san_pham.id (soft)
    so_luong: Mapped[int] = mapped_column(Integer, nullable=False, default=0)        # SL đặt

    # --- Ảnh chụp kết quả (Σ mọi thành phần) ---
    tong_gia_von: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    gia_von_don: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)   # dict engine đầy đủ
    warnings_json: Mapped[list | None] = mapped_column(JSON, nullable=True)  # list[str]

    ktv: Mapped[str | None] = mapped_column(String(255), nullable=True)     # tên người tạo (hiển thị)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)  # → users.id: chủ sở hữu (lọc scope)
    ghi_chu: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    thanh_phans: Mapped[list["PhieuThanhPhan"]] = relationship(
        "PhieuThanhPhan",
        back_populates="phieu",
        order_by="PhieuThanhPhan.thu_tu",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class PhieuThanhPhan(Base):
    """1 SẢN PHẨM (dòng hạng mục) của phiếu — có SL + loại + khổ + giấy/in/màu/gia công RIÊNG → giá vốn riêng.

    (Tên bảng/lớp giữ `thanh_phan` vì lý do lịch sử; khái niệm nay là "sản phẩm": 1 phiếu = nhiều sản phẩm,
    mỗi sản phẩm tính giá vốn độc lập với `so_luong` của nó. Sách/hộp = tách thành nhiều sản phẩm: ruột/bìa/đóng cuốn.)
    """

    __tablename__ = "phieu_thanh_phan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phieu_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("phieu_tinh_gia.id", ondelete="CASCADE"), index=True, nullable=False
    )
    thu_tu: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    loai_thanh_phan: Mapped[str] = mapped_column(String(30), nullable=False, default="to_roi")
    ten: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    kho_thanh_pham: Mapped[str | None] = mapped_column(String(100), nullable=True)  # nhãn tự do hiển thị
    dai_thanh_pham: Mapped[int] = mapped_column(Integer, nullable=False, default=0)   # mm — khổ thành phẩm ③ (bình bài)
    rong_thanh_pham: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # mm ★
    kho_mo_rong: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tay_gap: Mapped[str | None] = mapped_column(String(50), nullable=True)
    so_to_per_sp: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    so_luong: Mapped[int] = mapped_column(Integer, nullable=False, default=0)   # SL đặt của SẢN PHẨM này (0 = lấy SL mặc định phiếu)
    don_vi_tinh: Mapped[str] = mapped_column(String(30), nullable=False, default="cái")  # ĐVT sản phẩm (text tự do) → chảy sang Báo giá
    loai_san_pham_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # → loai_san_pham.id (soft) — loại của sản phẩm này

    # --- Giấy ---
    giay_id: Mapped[int | None] = mapped_column(Integer, nullable=True)             # → giay_nguyen.id (soft)
    kho_nguyen: Mapped[str | None] = mapped_column(String(100), nullable=True)      # nhãn hiển thị "rộng×dài" (giay_ten fallback)
    kho_nguyen_dai: Mapped[int] = mapped_column(Integer, nullable=False, default=0)   # mm — khổ giấy nguyên ① dài (ĐÈ danh mục khi > 0)
    kho_nguyen_rong: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # mm — rộng ①
    don_gia_giay: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    don_gia_don_vi: Mapped[str] = mapped_column(String(8), nullable=False, default="to")   # to|tan
    nguon_giay: Mapped[str] = mapped_column(String(12), nullable=False, default="cong_ty")  # cong_ty|khach
    bu_hao_so_to: Mapped[int] = mapped_column(Integer, nullable=False, default=0)   # bù hao (tờ in cộng thêm) — KHÔNG hệ số
    hao_so_to: Mapped[int] = mapped_column(Integer, nullable=False, default=0)      # hao (tờ in trừ đi)
    # Bật/TẮT tính bù hao công đoạn TỰ (mỗi công đoạn tra theo số tờ). Tắt → không cộng bù hao tự;
    # người dùng tự nhập `bu_hao_so_to`. Mặc định BẬT.
    tinh_bu_hao_cd: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_true(), default=True)
    chua_xen: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    chua_tay_ke: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    chua_nhip: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    chua_duoi: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    chua_ca_gay: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)

    # --- In ---
    co_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    che_ban_loai: Mapped[str | None] = mapped_column(String(30), nullable=True)
    che_ban_don_gia: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    quy_cach_in: Mapped[str] = mapped_column(String(12), nullable=False, default="mot_mat")  # mot_mat|hai_mat|tu_tro
    kho_in_dai: Mapped[int] = mapped_column(Integer, nullable=False, default=0)     # mm — khổ tờ in ② (bình bài + số lượt)
    kho_in_rong: Mapped[int] = mapped_column(Integer, nullable=False, default=0)    # mm ★
    so_con: Mapped[int] = mapped_column(Integer, nullable=False, default=1)         # con/tờ ④ (auto bình bài; override được)
    con_auto: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)   # True: engine tự bình bài; False: dùng so_con
    may_id: Mapped[int | None] = mapped_column(Integer, nullable=True)              # → may_thiet_bi.id (soft)
    don_gia_cong_in: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0)  # mực GỘP trong đơn giá

    # --- Màu (đã gộp: chỉ SỐ MÀU mỗi mặt — không SEL/Pan/Nền, không hệ số) ---
    so_mau_a: Mapped[int] = mapped_column(Integer, nullable=False, default=0)   # số màu mặt A
    so_mau_b: Mapped[int] = mapped_column(Integer, nullable=False, default=0)   # số màu mặt B

    gia_von_tp: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    phieu: Mapped["PhieuTinhGia"] = relationship("PhieuTinhGia", back_populates="thanh_phans")
    thanh_phams: Mapped[list["PhieuThanhPham"]] = relationship(
        "PhieuThanhPham",
        back_populates="thanh_phan",
        order_by="PhieuThanhPham.thu_tu",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    # Vật tư in ấn thêm tay (mực/màng/keo…) → dòng NGUYÊN VẬT LIỆU (song song giấy). Mỗi dòng trỏ
    # 1 mã vật tư (soft) + engine thế biến vào `cong_thuc_gia` của vật tư — HỆT giấy.
    vat_tus: Mapped[list["PhieuVatTu"]] = relationship(
        "PhieuVatTu",
        back_populates="thanh_phan",
        order_by="PhieuVatTu.thu_tu",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class PhieuThanhPham(Base):
    """1 dòng công đoạn gia công sau in (finishing) của 1 thành phần."""

    __tablename__ = "phieu_thanh_pham"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thanh_phan_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("phieu_thanh_phan.id", ondelete="CASCADE"), index=True, nullable=False
    )
    thu_tu: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cong_doan_id: Mapped[int | None] = mapped_column(Integer, nullable=True)   # → cong_doan.id (soft)
    ten: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    don_gia: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    so_luong: Mapped[int] = mapped_column(Integer, nullable=False, default=0)   # 0 = dùng SL đặt
    bu_hao: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    so_mat: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    so_vi_tri: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dien_tich: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)  # cm²/thành phẩm
    nha_cung_cap: Mapped[str | None] = mapped_column(String(150), nullable=True)   # thuê ngoài
    ghi_chu: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    thanh_phan: Mapped["PhieuThanhPhan"] = relationship("PhieuThanhPhan", back_populates="thanh_phams")


class PhieuVatTu(Base):
    """1 dòng VẬT TƯ IN ẤN (mực/màng/keo…) của 1 thành phần → NGUYÊN VẬT LIỆU.

    Trỏ 1 mã `vat_tu_id` (soft → vat_tu_in_an.id). Engine kéo `cong_thuc_gia` + `don_gia` +
    `don_vi_gia` từ danh mục rồi thế biến vào — giống hệt Giấy. `don_gia` ở đây = ghi đè
    (0 = lấy theo danh mục). `so_luong` (0 = SL đặt) chỉ để công thức dùng nếu cần.
    """

    __tablename__ = "phieu_vat_tu"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thanh_phan_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("phieu_thanh_phan.id", ondelete="CASCADE"), index=True, nullable=False
    )
    thu_tu: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    vat_tu_id: Mapped[int | None] = mapped_column(Integer, nullable=True)   # → vat_tu_in_an.id (soft)
    ten: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    don_gia: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0)  # 0 = lấy danh mục
    so_luong: Mapped[int] = mapped_column(Integer, nullable=False, default=0)   # 0 = dùng SL đặt
    ghi_chu: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    thanh_phan: Mapped["PhieuThanhPhan"] = relationship("PhieuThanhPhan", back_populates="vat_tus")
