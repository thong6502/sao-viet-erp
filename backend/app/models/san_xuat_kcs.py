"""Thực hiện sản xuất — KIỂM TRA CHẤT LƯỢNG (KCS) — Giai đoạn 5, §13.

Ba bảng GHI đứng SAU khung sản lượng (Giai đoạn 3) và neo lên snapshot công việc KCS
(`san_xuat_cong_viec` có `la_kcs=true`). Chúng KHÔNG chép lại công việc — chỉ ghi kết quả
kiểm tra thực tế và chuỗi nhận-trách-nhiệm lỗi:

  san_xuat_kcs_batch   — một BATCH KIỂM TRA (§13.1): số nhận & kết luận, cỡ mẫu, số đạt/không
                         đạt, cửa sổ thời gian, kết luận. NĂNG SUẤT KCS chia theo `so_luong_nhan`
                         (số nhận-và-kết-luận, KHÔNG phải số đạt) → khi tạo batch, service đẻ
                         kèm MỘT `san_xuat_batch` sản lượng (`tot = so_luong_nhan`, `hong = 0`)
                         để tái dùng NGUYÊN pipeline phân bổ (§13.1); `batch_id` neo về nó.
  san_xuat_kcs_loi     — một LỖI phát hiện trong batch (§13.2): nhóm lỗi chuẩn hoá, mô tả, tổ/
                         công đoạn bị yêu cầu nhận trách nhiệm, số lượng. Tổ trưởng phụ trách
                         CHẤP NHẬN hoặc TỪ CHỐI-kèm-lý-do (chung thẩm, không phân xử tiếp §13.2).
  san_xuat_kcs_loi_anh — ẢNH bằng chứng của một lỗi (§13.2): mỗi lỗi bắt buộc ≥1 ảnh (service
                         kiểm). Soft ref `file_url` (không ORM StoredFile) theo precedent
                         QuoteAttachment / KyThuatMayAnh.

NEO snapshot: batch/lỗi trỏ `san_xuat_cong_viec.id` (bản đóng băng). Trần "đóng đủ" nhóm dẫn xuất
TÍNH LÚC ĐỌC ở service (§16) — không cache cột.

Bảng MỚI → `create_all` tự dựng, KHÔNG migration. Bảng nghiệp vụ (batch, lỗi) mang `version`
chống bấm trùng; bảng LỊCH SỬ chỉ-thêm (ảnh) không có `version`.

--- Module KCS KIÊM NHIỆM (2026-08-31, mg `0250`) — Task 1 chỉ dựng NỀN SCHEMA -----------------

`SanXuatKcsBatch` được CỘNG THÊM `loai`/`kcs_department_id`/`checklist_json` (ALTER — bảng này đã
tồn tại trong DB dev/prod hiện tại nên đi qua `db_migrations.py`, KHÔNG như hai bảng mới dưới đây).

Hai bảng MỚI (`create_all` tự dựng, KHÔNG migration) là danh mục CHECKLIST tiêu chí KCS:

  san_xuat_kcs_tieu_chi — một HẠNG MỤC KIỂM của MỘT công đoạn (mã, tên, hướng dẫn, bắt buộc).

Bảng nối `san_xuat_kcs_tieu_chi_cong_doan` (nhiều-nhiều) đã GỠ ở mg `0285` — xem docstring của
`SanXuatKcsTieuChi`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, String, UniqueConstraint,
    true as sa_true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base

# --- Kết luận batch KCS (§13.1) --------------------------------------------------------------
KCS_DAT = "dat"                 # đạt toàn bộ
KCS_DAT_MOT_PHAN = "dat_mot_phan"  # đạt một phần (có số không đạt được giữ lại)
KCS_KHONG_DAT = "khong_dat"     # không đạt toàn bộ
KET_LUAN_KCS = (KCS_DAT, KCS_DAT_MOT_PHAN, KCS_KHONG_DAT)

# --- Trạng thái nhận trách nhiệm lỗi (§13.2) -------------------------------------------------
TN_CHO = "pending"          # chờ tổ phụ trách phản hồi
TN_CHAP_NHAN = "accepted"   # tổ nhận trách nhiệm → tính vào chất lượng tổ
TN_TU_CHOI = "rejected"     # tổ từ chối kèm lý do → không quy trách nhiệm nhưng GIỮ đủ bằng chứng
TN_RECORDED = "recorded"    # lỗi MỚI (kiêm nhiệm, mg 0250) — ghi một chiều, không chờ phản hồi
TRANG_THAI_TRACH_NHIEM = (TN_CHO, TN_CHAP_NHAN, TN_TU_CHOI)

# --- Loại batch KCS (module KCS kiêm nhiệm, mg `0250`) ---------------------------------------
KCS_LOAI_ROUTING = "routing"    # BƯỚC KCS đứng sẵn trong routing (`la_kcs`) — có sản lượng + cửa kho
KCS_LOAI_DOT_XUAT = "dot_xuat"  # KCS kiêm nhiệm — tổ SX khác được giao kiểm ĐỘT XUẤT, ngoài kế hoạch
# ĐIỂM KIỂM theo công đoạn (08/09/2026, `docs/design-kcs-theo-cong-doan.md`): công đoạn có tiêu chí
# gắn ở danh mục ⇒ tổ KCS tới kiểm tại chỗ. Ghi CHẤT LƯỢNG thuần như `dot_xuat` (không đẻ sản
# lượng, không đụng kho, KHÔNG chặn bước sau), nhưng KHÔNG phải "đột xuất" — nó đứng sẵn trong kế
# hoạch, nên tách mã riêng để báo cáo đừng gọi nhầm tên. Khác `routing` ở chỗ thẻ việc thuộc tổ
# SẢN XUẤT chứ không thuộc tổ KCS.
KCS_LOAI_DIEM_KIEM = "diem_kiem"
LOAI_KCS_BATCH = (KCS_LOAI_ROUTING, KCS_LOAI_DOT_XUAT, KCS_LOAI_DIEM_KIEM)  # validate ở service


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SanXuatKcsBatch(Base):
    """Một BATCH KIỂM TRA KCS của một công việc KCS (§13.1).

    `so_luong_nhan = so_luong_dat + so_luong_khong_dat` (± dung sai, service kiểm). NĂNG SUẤT
    KCS lấy NỀN theo `so_luong_nhan` (số nhận-và-kết-luận), KHÔNG theo số đạt — nên service tạo
    kèm một `san_xuat_batch` sản lượng với `tot = so_luong_nhan`, `hong = 0`, cửa sổ
    `[bat_dau, ket_thuc]`; `batch_id` neo về batch đó để pipeline phân bổ chạy NGUYÊN. SET NULL
    để giữ bản ghi KCS nếu batch sản lượng bị gỡ."""

    __tablename__ = "san_xuat_kcs_batch"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cong_viec_id: Mapped[int] = mapped_column(
        ForeignKey("san_xuat_cong_viec.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Batch sản lượng nền cho phân bổ năng suất KCS (tạo kèm). U: một batch KCS ↔ một batch sản lượng.
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("san_xuat_batch.id", ondelete="SET NULL"), nullable=True, unique=True, index=True
    )
    # Nhóm thành phẩm đang kiểm (snapshot từ công việc) — định danh lô thành phẩm cho nhập kho (§14.1).
    nhom_id: Mapped[int | None] = mapped_column(
        ForeignKey("san_xuat_nhom.id", ondelete="SET NULL"), nullable=True, index=True
    )
    bat_dau: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ket_thuc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    so_luong_nhan: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False)
    co_mau: Mapped[float | None] = mapped_column(Numeric(18, 3), nullable=True)
    so_luong_dat: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False)
    so_luong_khong_dat: Mapped[float] = mapped_column(
        Numeric(18, 3), nullable=False, server_default="0", default=0
    )
    don_vi: Mapped[str] = mapped_column(String(24), nullable=False)
    ket_luan: Mapped[str] = mapped_column(String(16), nullable=False, default=KCS_DAT)
    ghi_chu: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # --- KCS kiêm nhiệm (mg `0250`) — cột CỘNG THÊM, KHÔNG động vào các cột legacy phía trên ---
    # `routing` (mặc định) = batch của công việc KCS ĐÃ có sẵn trong routing/bài ghép (cách cũ, duy
    # nhất trước đây — backfill set cứng giá trị này cho mọi dòng cũ). `dot_xuat` = tổ SX khác được
    # GIAO kiểm đột xuất, không đứng sẵn trong routing. `diem_kiem` (08/09/2026) = điểm kiểm theo
    # công đoạn, đứng sẵn trong kế hoạch nhờ tiêu chí gắn ở danh mục. Validate ở service — String
    # trần không CHECK, cùng phong cách `ket_luan`/`trang_thai` ở trên.
    loai: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=KCS_LOAI_ROUTING, default=KCS_LOAI_ROUTING
    )
    # Tổ KCS SỞ HỮU kết quả — khác `cong_viec_id` (qua đó suy ra tổ THỰC HIỆN công việc gốc): kiểm
    # đột xuất thì người kiểm thuộc tổ khác tổ đang chạy việc. SET NULL giữ bản ghi KCS nếu tổ bị gỡ.
    kcs_department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Snapshot checklist đã áp dụng cho batch này — cùng hình dạng `san_xuat_cong_viec.kcs_tieu_chi_json`.
    # NULL = batch cũ (trước module này) hoặc chưa gắn checklist. Task 3 mới thực sự GHI.
    checklist_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class SanXuatKcsLoi(Base):
    """Một LỖI phát hiện trong batch KCS (§13.2). Bảng nghiệp vụ (đổi trạng thái nhận-trách-nhiệm)
    → mang `version`.

    `nhom_loi_id` trỏ danh mục lỗi chuẩn hoá (nhóm `loi`); `mo_ta` chỉ bổ sung. `to_chiu_id` là tổ
    bị yêu cầu nhận trách nhiệm, `cong_doan_ref_id` là công việc/công đoạn liên đới (tuỳ chọn).
    Tổ trưởng phụ trách CHẤP NHẬN (`accepted`) hoặc TỪ CHỐI (`rejected` + `ly_do_tu_choi`); quyết
    định chung thẩm. Lỗi CHỜ không chặn nhập kho phần đạt nhưng CHẶN đóng đủ nhóm (§13.2, §16)."""

    __tablename__ = "san_xuat_kcs_loi"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kcs_batch_id: Mapped[int] = mapped_column(
        ForeignKey("san_xuat_kcs_batch.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nhom_loi_id: Mapped[int | None] = mapped_column(
        ForeignKey("san_xuat_ly_do.id", ondelete="SET NULL"), nullable=True, index=True
    )
    mo_ta: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Tổ bị yêu cầu nhận trách nhiệm + công đoạn liên đới (snapshot công việc). SET NULL giữ lịch sử.
    to_chiu_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    cong_doan_ref_id: Mapped[int | None] = mapped_column(
        ForeignKey("san_xuat_cong_viec.id", ondelete="SET NULL"), nullable=True, index=True
    )
    so_luong: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False, server_default="0", default=0)
    don_vi: Mapped[str | None] = mapped_column(String(24), nullable=True)
    trang_thai: Mapped[str] = mapped_column(String(16), nullable=False, default=TN_CHO)
    phan_hoi_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    phan_hoi_luc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ly_do_tu_choi: Mapped[str | None] = mapped_column(String(500), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class SanXuatKcsLoiAnh(Base):
    """ẢNH bằng chứng của một lỗi KCS (§13.2). Bảng CHỈ-THÊM (không `version`). Lưu `file_url` soft
    ref (không ORM StoredFile) theo precedent `QuoteAttachment` / `KyThuatMayAnh`; file phục vụ qua
    `/api/files` (prefix `san-xuat`). Mỗi lỗi bắt buộc ≥1 ảnh — service kiểm khi tạo/xoá."""

    __tablename__ = "san_xuat_kcs_loi_anh"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    loi_id: Mapped[int] = mapped_column(
        ForeignKey("san_xuat_kcs_loi.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    uploaded_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class SanXuatKcsTieuChi(Base):
    """Một HẠNG MỤC KIỂM của MỘT công đoạn — vd "Chồng màu đúng mẫu đã ký" của công đoạn In
    offset. `bat_buoc` = mục này chưa trả lời thì KCS không gửi được kết luận.

    THUỘC ĐÚNG MỘT CÔNG ĐOẠN (mg `0285`, đổi từ nhiều-nhiều). Người khai đi theo đường
    Giai đoạn → Công đoạn → hạng mục, nên hạng mục sinh ra đã nằm dưới một công đoạn; cùng một
    câu chữ dùng cho hai công đoạn thì khai hai dòng. GIAI ĐOẠN không lưu ở đây — nó là
    `cong_doan.nhom`, chỉ dùng để lọc lúc chọn công đoạn.

    Từ 08/09/2026 (`docs/design-kcs-theo-cong-doan.md`) bảng này là NGUỒN DUY NHẤT của checklist:
    ô "Tiêu chí KCS bổ sung" trên bước lệnh đã gỡ (mg `0283`). Mọi công đoạn có hạng mục khai vào
    đều thành ĐIỂM KIỂM, không riêng bước KCS cuối routing.

    `UniqueConstraint(cong_doan_id, ten)`: cùng một công đoạn không khai trùng câu chữ. Không đặt
    unique theo `ten` toàn bảng — hai công đoạn khác nhau được phép có cùng hạng mục."""

    __tablename__ = "san_xuat_kcs_tieu_chi"
    __table_args__ = (
        UniqueConstraint("cong_doan_id", "ten", name="uq_kcs_hang_muc_cong_doan_ten"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ma: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    # Công đoạn sở hữu hạng mục này. CASCADE: gỡ công đoạn khỏi danh mục thì checklist của nó
    # cũng hết nghĩa (bản đã phát hành không ảnh hưởng — đó là ảnh chụp trong `san_xuat_cong_viec`).
    cong_doan_id: Mapped[int] = mapped_column(
        ForeignKey("cong_doan.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ten: Mapped[str] = mapped_column(String(200), nullable=False)
    huong_dan: Mapped[str | None] = mapped_column(String(500), nullable=True)
    bat_buoc: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_true(), default=True)
    thu_tu: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_true(), default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
