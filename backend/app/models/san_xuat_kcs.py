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
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

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
TRANG_THAI_TRACH_NHIEM = (TN_CHO, TN_CHAP_NHAN, TN_TU_CHOI)


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
