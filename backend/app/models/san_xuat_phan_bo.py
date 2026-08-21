"""Thực hiện sản xuất — HỖ TRỢ CHÉO · PHÂN BỔ SẢN LƯỢNG · BÙ TRỪ (Giai đoạn 4, §8–§9 · §12).

Bốn bảng GHI đứng SAU sản lượng (Giai đoạn 3) và neo lên snapshot công việc (`san_xuat_cong_viec`)
+ batch (`san_xuat_batch`). Chúng biến sản lượng batch thành lương khoán theo người:

  san_xuat_ho_tro        — THỎA THUẬN hỗ trợ chéo giữa hai tổ (§9.1): người hỗ trợ + tổ gốc + tổ
                           thực hiện + công đoạn + ngày + tỷ lệ, xác nhận HAI tổ trưởng. Tỷ lệ do
                           người nhập (5%/7%/12,5%…) — KHÔNG hard-code, KHÔNG mặc định, KHÔNG giới
                           hạn 7%. Trạng thái: pending_both → confirmed → cancelled.
  san_xuat_phan_bo       — HEADER phân bổ MỘT batch (§12.1: chia theo từng batch, không gộp công
                           đoạn). Đóng băng Q trả lương + đơn giá + tổng tỷ lệ hỗ trợ tại lúc chốt.
                           Trạng thái: draft → finalized → reopened.
  san_xuat_phan_bo_dong  — DÒNG phân bổ theo người (§12.2). Giữ RIÊNG sản lượng bản địa và sản lượng
                           trả lương đã quy đổi. Sinh lại toàn bộ mỗi lần chốt (bảng dẫn xuất, không
                           version). `la_ho_tro` phân biệt phần người hỗ trợ (ghi cho tổ gốc) với
                           phần tổ thực hiện chia theo phút×hệ số.
  san_xuat_phan_bo_bu_tru — DÒNG BÙ TRỪ sau khi kỳ lương ĐÃ KHÓA (§12.3): không sửa kỳ cũ, đẻ dòng
                           chênh lệch ở kỳ mở tiếp theo, tham chiếu batch + kỳ gốc. Bảng CHỈ-THÊM.
  san_xuat_phan_bo_loai_tru — NGƯỜI bị LOẠI khỏi lương batch (§7.3): tổ trưởng xác nhận một người
                           KHÔNG được chia lương của batch (vd không có chấm công hợp lệ và không thể
                           bổ sung) kèm LÝ DO. Người bị loại bị bỏ khỏi vòng chia trọng số → phần của
                           họ chia lại cho người còn lại, và cờ "thiếu chấm công" của họ tan (cho chốt).

Bảng MỚI → `create_all` tự dựng, KHÔNG migration (chỉ ALTER cột bảng cũ mới cần). Boolean dùng
`false()`/`true()` (bẫy Postgres DB trắng). Số dẫn xuất (phút thực tế, trọng số) TÍNH LÚC CHỐT rồi
đóng băng vào dòng — engine không đọc-sống lại khoảng tham gia sau khi đã chốt (§8: danh mục đổi về
sau không viết lại dữ liệu đã chốt). Bảng nghiệp vụ mang `version` chống bấm trùng; bảng dẫn-xuất /
chỉ-thêm (dòng phân bổ, bù trừ) KHÔNG version.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint,
    false as sa_false,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# --- Trạng thái thỏa thuận hỗ trợ (§9.1, §18) ------------------------------------------------
HT_CHO_HAI_BEN = "pending_both"   # chờ đủ xác nhận của hai tổ trưởng (gốc + thực hiện)
HT_XAC_NHAN = "confirmed"         # cả hai tổ trưởng đã xác nhận → tỷ lệ này áp vào phân bổ
HT_HUY = "cancelled"              # đã huỷ (vd lịch chưa chạy bị phát hành cập nhật §9.2)
TRANG_THAI_HO_TRO = (HT_CHO_HAI_BEN, HT_XAC_NHAN, HT_HUY)

# --- Trạng thái phân bổ (§12.3, §18) ---------------------------------------------------------
PB_NHAP = "draft"          # đã tính nhưng chưa chốt — công nhân CHƯA xem được
PB_DA_CHOT = "finalized"   # tổ trưởng đã chốt — feed lương khoán + công nhân xem được
PB_MO_LAI = "reopened"     # mở lại (trước khi kỳ lương khoá) kèm lý do; chốt lại → finalized
TRANG_THAI_PHAN_BO = (PB_NHAP, PB_DA_CHOT, PB_MO_LAI)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SanXuatHoTro(Base):
    """Một THỎA THUẬN hỗ trợ chéo giữa hai tổ cho một công đoạn (§9.1).

    Tỷ lệ `ty_le_phan_tram` là PHẦN TRĂM người nhập theo từng thỏa thuận (7 = 7%, 12.5 = 12,5%).
    §9.1 cấm hard-code/mặc định/giới hạn 7%. Tổng tỷ lệ đã xác nhận trong cùng phạm vi phân bổ
    (cùng công đoạn + cùng ngày) không vượt 100% — service kiểm khi xác nhận.

    Xác nhận HAI tổ trưởng: `xac_nhan_goc_*` (tổ gốc của người hỗ trợ) và `xac_nhan_thuc_hien_*`
    (tổ đang thực hiện công đoạn). Đủ cả hai → `trang_thai=confirmed`. Phần hỗ trợ thuộc
    `ngay_lam_viec` (§9.2: không chuyển sang ngày hoàn thành công đoạn)."""

    __tablename__ = "san_xuat_ho_tro"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cong_viec_id: Mapped[int] = mapped_column(
        ForeignKey("san_xuat_cong_viec.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Tổ gốc = nơi ghi nhận phần hỗ trợ (§9.2). Tổ thực hiện = snapshot tổ của công đoạn.
    to_goc_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    to_thuc_hien_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    ngay_lam_viec: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    ty_le_phan_tram: Mapped[float] = mapped_column(Numeric(7, 4), nullable=False)
    trang_thai: Mapped[str] = mapped_column(String(16), nullable=False, default=HT_CHO_HAI_BEN)
    mo_ta: Mapped[str | None] = mapped_column(String(500), nullable=True)
    de_xuat_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    xac_nhan_goc_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    xac_nhan_goc_luc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    xac_nhan_thuc_hien_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    xac_nhan_thuc_hien_luc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    huy_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    huy_luc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ly_do_huy: Mapped[str | None] = mapped_column(String(500), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class SanXuatPhanBo(Base):
    """HEADER phân bổ sản lượng của MỘT batch (§12.1). Một batch tối đa một phân bổ (`batch_id`
    UNIQUE). Đóng băng tại lúc TÍNH: `q_tra_luong` (Q sau quy đổi), `don_gia` (từ khoan_json),
    `tong_ty_le_ho_tro` (tổng P đã xác nhận), giữ RIÊNG sản lượng bản địa `q_ban_dia`/`don_vi_ban_dia`
    (§12.2). `ky_nam`/`ky_thang` = kỳ lương của batch (suy từ ngày batch) để lọc theo kỳ nhanh.

    Trạng thái §12.3: draft (chưa chốt, công nhân chưa xem) → finalized (chốt, feed lương) →
    reopened (mở lại trước khi kỳ khoá, kèm lý do) → finalized lại. `mo_lai_ly_do_id` thuộc nhóm
    `mo_lai_phan_bo` của danh mục lý do."""

    __tablename__ = "san_xuat_phan_bo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("san_xuat_batch.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    cong_viec_id: Mapped[int] = mapped_column(
        ForeignKey("san_xuat_cong_viec.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ngay: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    ky_nam: Mapped[int] = mapped_column(Integer, nullable=False)
    ky_thang: Mapped[int] = mapped_column(Integer, nullable=False)
    trang_thai: Mapped[str] = mapped_column(String(16), nullable=False, default=PB_NHAP)
    # Sản lượng trả lương (đã quy đổi) + đơn giá snapshot.
    q_tra_luong: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False, default=0)
    don_vi_tra_luong: Mapped[str | None] = mapped_column(String(24), nullable=True)
    don_gia: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    # Sản lượng BẢN ĐỊA giữ riêng (§12.2 "luôn giữ riêng bản địa và trả lương").
    q_ban_dia: Mapped[float | None] = mapped_column(Numeric(18, 3), nullable=True)
    don_vi_ban_dia: Mapped[str | None] = mapped_column(String(24), nullable=True)
    tong_ty_le_ho_tro: Mapped[float] = mapped_column(Numeric(7, 4), nullable=False, default=0)  # % (0..100)
    chot_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    chot_luc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mo_lai_ly_do_id: Mapped[int | None] = mapped_column(
        ForeignKey("san_xuat_ly_do.id", ondelete="SET NULL"), nullable=True
    )
    mo_lai_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    mo_lai_luc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class SanXuatPhanBoDong(Base):
    """DÒNG phân bổ theo NGƯỜI (§12.2). Bảng DẪN XUẤT: sinh lại toàn bộ mỗi lần tính/chốt (không
    version). Giữ RIÊNG `so_luong_tra_luong` (đã quy đổi, dùng tính lương) và `so_luong_ban_dia`.

    `la_ho_tro=true`: phần người hỗ trợ = Q×tỷ lệ, ghi cho `department_id`=tổ GỐC, `ngay`=ngày thỏa
    thuận (§9.2), KHÔNG chia theo phút×hệ số → `trong_so`/`phut_thuc_te`/`he_so_bac` để trống.
    `la_ho_tro=false`: phần tổ thực hiện, chia phần còn lại Q×(1−P) theo
    `trong_so = phut_thuc_te × he_so_bac` (§12.2)."""

    __tablename__ = "san_xuat_phan_bo_dong"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phan_bo_id: Mapped[int] = mapped_column(
        ForeignKey("san_xuat_phan_bo.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    la_ho_tro: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_false(), default=False
    )
    ho_tro_id: Mapped[int | None] = mapped_column(
        ForeignKey("san_xuat_ho_tro.id", ondelete="SET NULL"), nullable=True
    )
    ngay: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    so_luong_tra_luong: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False, default=0)
    so_luong_ban_dia: Mapped[float | None] = mapped_column(Numeric(18, 3), nullable=True)
    trong_so: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    phut_thuc_te: Mapped[float | None] = mapped_column(Numeric(12, 3), nullable=True)
    he_so_bac: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)
    don_gia: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class SanXuatPhanBoBuTru(Base):
    """DÒNG BÙ TRỪ sau khi kỳ lương ĐÃ KHÓA (§12.3). Không sửa kỳ cũ — ghi chênh lệch (có thể âm)
    vào kỳ mở tiếp theo (`ky_bu_*`), tham chiếu batch gốc + kỳ gốc. Bảng CHỈ-THÊM (không version).

    `so_luong_tra_luong` là DELTA so với phân bổ đã khoá (dương = trả thêm, âm = thu bớt). Seam
    lương đọc dòng này theo `ky_bu_*`. `ly_do_id` nên thuộc nhóm `mo_lai_phan_bo` của danh mục lý do."""

    __tablename__ = "san_xuat_phan_bo_bu_tru"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("san_xuat_batch.id", ondelete="SET NULL"), nullable=True, index=True
    )
    phan_bo_id: Mapped[int | None] = mapped_column(
        ForeignKey("san_xuat_phan_bo.id", ondelete="SET NULL"), nullable=True
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    ky_goc_nam: Mapped[int] = mapped_column(Integer, nullable=False)
    ky_goc_thang: Mapped[int] = mapped_column(Integer, nullable=False)
    ky_bu_nam: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    ky_bu_thang: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    ngay: Mapped[date] = mapped_column(Date, nullable=False)
    so_luong_tra_luong: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False, default=0)
    don_gia: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    ly_do_id: Mapped[int | None] = mapped_column(
        ForeignKey("san_xuat_ly_do.id", ondelete="SET NULL"), nullable=True
    )
    mo_ta: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class SanXuatPhanBoLoaiTru(Base):
    """NGƯỜI bị LOẠI khỏi lương của MỘT batch (§7.3). Khi một người tham gia nhưng KHÔNG có phút
    chấm công hợp lệ (thiếu/quên chấm công) và không thể bổ sung, tổ trưởng xác nhận loại người đó
    khỏi đợt trả lương của batch kèm LÝ DO — engine bỏ họ khỏi vòng chia trọng số (phần của họ chia
    lại cho người còn lại) và cờ 'thiếu chấm công' của họ tan để cho phép chốt.

    Khoá (batch_id, employee_id) — mỗi người tối đa một dòng loại trừ / batch. Gỡ loại trừ = XOÁ
    dòng (bảng trạng thái, không version); toàn bộ vết ai-gì-lúc-nào nằm ở AuditLog."""

    __tablename__ = "san_xuat_phan_bo_loai_tru"
    __table_args__ = (UniqueConstraint("batch_id", "employee_id", name="uq_sxpb_loai_tru"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("san_xuat_batch.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ly_do: Mapped[str] = mapped_column(String(500), nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
