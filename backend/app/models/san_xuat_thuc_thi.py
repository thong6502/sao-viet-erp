"""Thực hiện sản xuất tại TỔ — PHÂN CÔNG · PHIÊN CHẠY · KHOẢNG THAM GIA (Giai đoạn 2, §7).

Ba bảng GHI này đứng SAU snapshot phát hành (`san_xuat_cong_viec` ở `san_xuat.py`). Chúng KHÔNG
sao chép công việc — chỉ neo trạng thái thực thi lên một work item đã đóng băng:

  san_xuat_phan_cong      — roster: ai được giao vào một công việc (§7.1). Lần giao ĐẦU tiên
                            đồng nghĩa tổ đã TIẾP NHẬN (§5.2) — không có nút "Nhận lệnh" riêng.
  san_xuat_phien_chay     — phiên chạy: một khoảng công việc THỰC SỰ chạy máy (§7.2). Bắt đầu mở
                            phiên mới; Tạm dừng/Kết thúc đóng phiên hiện tại. Một công việc nhiều phiên.
  san_xuat_khoang_tham_gia — khoảng một NGƯỜI tham gia một phiên (§7.2). Thêm/rút/chuyển người tự
                            đóng/mở khoảng. Một người KHÔNG được có hai khoảng MỞ chồng giờ (§7.1).

Mốc thời gian LẤY TỪ MÁY CHỦ, không backdate, không sửa mốc đã phát sinh (§7.2). Phút thực tế để
tính lương (§7.3 — giao khoảng tham gia × chấm công × tăng ca duyệt) TÍNH LÚC ĐỌC ở service, bảng
này chỉ giữ khoảng thô. Bảng MỚI → `create_all` tự dựng, KHÔNG migration. Boolean dùng `false()`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint,
    false as sa_false,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# --- Trạng thái phân công (roster) -----------------------------------------------------------
PC_HOAT_DONG = "active"    # đang trong tổ thực hiện
PC_DA_RUT = "removed"      # đã rút khỏi công việc (khoảng tham gia mở bị đóng lại)
TRANG_THAI_PHAN_CONG = (PC_HOAT_DONG, PC_DA_RUT)

# --- Loại đóng phiên chạy --------------------------------------------------------------------
PHIEN_TAM_DUNG = "tam_dung"    # đóng vì Tạm dừng (bắt buộc lý do)
PHIEN_KET_THUC = "ket_thuc"    # đóng vì Kết thúc công việc
LOAI_DONG_PHIEN = (PHIEN_TAM_DUNG, PHIEN_KET_THUC)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SanXuatPhanCong(Base):
    """Roster của một công việc: một dòng cho mỗi người được giao (§7.1).

    Người có thể KHÔNG có tài khoản (`employee_id` trỏ nhân viên, không bắt `user_id`) vẫn được
    giao và tính lương (§6). `la_luong_khoan` là ẢNH CHỤP tại lúc giao — dùng để soi luật "ít nhất
    một thợ lương khoán mới được bắt đầu" mà không phụ thuộc danh mục đổi về sau. Rút người =
    `trang_thai=removed` (giữ lịch sử, không xoá dòng)."""

    __tablename__ = "san_xuat_phan_cong"
    __table_args__ = (
        # Một người chỉ có MỘT dòng đang hoạt động trên một công việc (rút rồi giao lại đẻ dòng mới).
        UniqueConstraint("cong_viec_id", "employee_id", "trang_thai",
                         name="uq_phan_cong_cv_nv_tt"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cong_viec_id: Mapped[int] = mapped_column(
        ForeignKey("san_xuat_cong_viec.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Ảnh chụp: người này thuộc chế độ lương khoán tại lúc giao (§6 — chỉ thợ khoán vào bước nội bộ).
    la_luong_khoan: Mapped[bool] = mapped_column(
        nullable=False, server_default=sa_false(), default=False
    )
    trang_thai: Mapped[str] = mapped_column(String(16), nullable=False, default=PC_HOAT_DONG)
    ly_do_rut: Mapped[str | None] = mapped_column(String(255), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class SanXuatPhienChay(Base):
    """Một PHIÊN chạy = khoảng công việc thực sự chạy (§7.2). Bắt đầu mở phiên (ket_thuc NULL);
    Tạm dừng/Kết thúc đóng phiên (`ket_thuc` + `loai_dong`). Mốc lấy từ máy chủ, không backdate.

    `ly_do_bat_dau_tre` bắt buộc khi bắt đầu SAU dự kiến (§7.2). `ly_do` bắt buộc khi Tạm dừng.
    `ket_thuc_tre` đánh dấu kết thúc sau dự kiến để service quyết có cần thêm lý do hay không
    (§7.2 cuối: nếu đã có lý do tạm dừng giải thích được phần chậm thì miễn)."""

    __tablename__ = "san_xuat_phien_chay"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cong_viec_id: Mapped[int] = mapped_column(
        ForeignKey("san_xuat_cong_viec.id", ondelete="CASCADE"), nullable=False, index=True
    )
    so_thu_tu: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # thứ tự phiên trong công việc
    bat_dau: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ket_thuc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    loai_dong: Mapped[str | None] = mapped_column(String(16), nullable=True)  # tam_dung | ket_thuc
    ly_do_bat_dau_tre: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Bắt buộc khi số người thực tế bắt đầu KHÁC số dự kiến chốt lúc phát hành (§7.1). NULL = khớp.
    ly_do_so_nguoi: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ly_do: Mapped[str | None] = mapped_column(String(255), nullable=True)  # lý do tạm dừng / kết thúc trễ
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class SanXuatKhoangThamGia(Base):
    """Khoảng một NGƯỜI tham gia một phiên chạy (§7.2, §7.3). Mở khi phiên bắt đầu (cho mọi người
    đang trong roster) hoặc khi thêm người giữa chừng; đóng khi phiên tạm dừng/kết thúc hoặc khi
    rút/chuyển người. `ket_thuc IS NULL` = đang mở.

    LUẬT §7.1: một người KHÔNG được có hai khoảng MỞ cùng lúc (không chồng giờ). Service chặn mở
    khoảng thứ hai khi người đó còn khoảng mở ở bất kỳ công việc nào.

    SNAPSHOT BẬC (§8, Giai đoạn 4): `job_grade_id` + `output_coefficient` được ĐÓNG BĂNG tại lúc mở
    khoảng (engine đọc `Employee.job_grade_id` + `JobGrade.output_coefficient`). Danh mục bậc đổi về
    sau KHÔNG viết lại khoảng đang chạy/đã xong. NULL = người chưa gán bậc / bậc chưa khai hệ số →
    §8: KHÔNG chặn ghi sản xuất nhưng CHẶN chốt phân bổ (engine cần hệ số để chia trọng số §12.2)."""

    __tablename__ = "san_xuat_khoang_tham_gia"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cong_viec_id: Mapped[int] = mapped_column(
        ForeignKey("san_xuat_cong_viec.id", ondelete="CASCADE"), nullable=False, index=True
    )
    phien_chay_id: Mapped[int] = mapped_column(
        ForeignKey("san_xuat_phien_chay.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    bat_dau: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ket_thuc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Ảnh chụp bậc tay nghề + hệ số sản lượng tại lúc mở khoảng (§8) — dùng để chia trọng số §12.2.
    job_grade_id: Mapped[int | None] = mapped_column(
        ForeignKey("job_grades.id"), nullable=True
    )
    output_coefficient: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
