"""Thực hiện sản xuất — KIỂM TRA CHẤT LƯỢNG (KCS), bản "KCS theo LỆNH" (mg `0306`, 17/09/2026).

Spec: `docs/design-kcs-theo-lenh.md`. KCS mở một lệnh → bấm một công đoạn → ghi Số đạt / Số lỗi.
Ba bảng GHI neo lên snapshot công việc (`san_xuat_cong_viec`), KHÔNG chép lại công việc:

  san_xuat_kcs_batch   — MỘT LẦN KIỂM một công đoạn: số đạt / lỗi (`so_luong_nhan` = tổng), checklist
                         đã tick, người kiểm = `created_by`. Bản ghi chất lượng thuần: không đẻ mẻ sản
                         lượng, không trừ số, không đổi trạng thái công việc.
  san_xuat_kcs_loi     — phần LỖI của một lần kiểm: mô tả, số lượng, tổ chịu = tổ của công đoạn.
                         Tổ bấm "Đã xem" → `phan_hoi_by_id` / `phan_hoi_luc`. Không có nhận / từ chối.
  san_xuat_kcs_loi_anh — ẢNH bằng chứng của một lỗi (≥1 ảnh, service kiểm).

Ai là KCS: thành viên phòng ban có `departments.is_kcs` — kiểm được công đoạn của mọi tổ.
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


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SanXuatKcsBatch(Base):
    """MỘT LẦN KIỂM một công đoạn. `so_luong_nhan = so_luong_dat + so_luong_khong_dat` (service
    kiểm). Kiểm nhiều lần được — số đạt cộng dồn ở công đoạn cuối là số đề nghị nhập kho.
    `bat_dau` = `ket_thuc` = lúc ghi (UTC thật)."""

    __tablename__ = "san_xuat_kcs_batch"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cong_viec_id: Mapped[int] = mapped_column(
        ForeignKey("san_xuat_cong_viec.id", ondelete="CASCADE"), nullable=False, index=True
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
    # Kết quả checklist đã tick: list[{thu_tu, dat}] khớp `san_xuat_cong_viec.kcs_tieu_chi_json`.
    # NULL = công đoạn không có tiêu chí.
    checklist_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class SanXuatKcsLoi(Base):
    """Phần LỖI của một lần kiểm — mô tả + số lượng + ảnh. `to_chiu_id` = tổ của công đoạn bị kiểm,
    `cong_doan_ref_id` = chính công việc đó (tự điền, không chọn). Tổ chịu bấm "Đã xem"
    (`phan_hoi_by_id` / `phan_hoi_luc`) — thông báo một chiều, không chặn gì."""

    __tablename__ = "san_xuat_kcs_loi"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kcs_batch_id: Mapped[int] = mapped_column(
        ForeignKey("san_xuat_kcs_batch.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mo_ta: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Tổ chịu + công đoạn bị kiểm (snapshot công việc). SET NULL giữ lịch sử.
    to_chiu_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    cong_doan_ref_id: Mapped[int | None] = mapped_column(
        ForeignKey("san_xuat_cong_viec.id", ondelete="SET NULL"), nullable=True, index=True
    )
    so_luong: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False, server_default="0", default=0)
    don_vi: Mapped[str | None] = mapped_column(String(24), nullable=True)
    # "Đã xem" của tổ chịu — ai bấm, lúc nào. NULL = chưa xem.
    phan_hoi_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    phan_hoi_luc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
