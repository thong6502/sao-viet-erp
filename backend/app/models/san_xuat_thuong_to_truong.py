"""Thực hiện sản xuất — THƯỞNG/PHẠT TỔ TRƯỞNG theo chất lượng (§8 nối tiếp phân bổ sản lượng).

Chốt của chủ 04/09/2026: *"xong lệnh nào là biết sản lượng cá nhân và số tiền tương ứng luôn"* +
*"tỉ lệ lỗi lấy từ phiếu KCS"*. Bảng này là VẾT của phép tính đó — một dòng cho MỘT TỔ trong MỘT
NHÓM thành phẩm, ghi đúng lúc nhóm đóng (`services/san_xuat/dong_nhom.py`).

Vì sao neo vào NHÓM chứ không vào từng LSX: hôm nay `lsx.trang_thai` dừng ở `da_phat_hanh` — ba
mốc `dang_san_xuat`/`hoan_thanh`/`da_dong` CHƯA dùng, nên "lệnh đóng" chưa phải một sự kiện có
thật trong hệ. Sự kiện "xong" duy nhất đang chạy là ĐÓNG NHÓM thành phẩm (§16), và cổng của nó
đã đòi đúng những thứ phép thưởng cần: mọi việc hoàn thành · phân bổ đã CHỐT · hết lỗi KCS đang
chờ tổ phản hồi · kho xong. Một nhóm = một thành phẩm gồm lệnh thân chính + các lệnh bổ sung/bù/
làm lại của nó, nên "sản lượng của tổ trong lệnh" ở bảng bậc chính là tổng của cả nhóm.

Bảng DẪN XUẤT + ĐÓNG BĂNG: mọi số dùng để ra tiền (sản lượng, tiền khoán, số lỗi, tỷ lệ lỗi, %
bậc trúng) đều snapshot tại lúc đóng nhóm. Sửa bậc thưởng hay sửa hệ số bậc về sau KHÔNG viết lại
dòng đã ghi — cùng nguyên tắc §8 với `san_xuat_phan_bo_dong`.

Bảng MỚI → `create_all` tự dựng, KHÔNG cần migration. Riêng cột `payroll_lines.thuong_to_truong`
là ALTER trên bảng cũ nên có migration `0265` đi kèm.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SanXuatThuongToTruong(Base):
    """Một dòng thưởng (dương) hoặc phạt (âm) cho TỔ TRƯỞNG của một tổ, trong một nhóm thành phẩm.

    Cách ra tiền — hai điều kiện của bảng bậc `piece_leader_bonus_brackets`:

      1. `san_luong` = Σ `san_xuat_phan_bo_dong.so_luong_tra_luong` của tổ đó trong nhóm (chỉ dòng
         thuộc header ĐÃ CHỐT). Lấy theo `department_id` CỦA DÒNG, nên phần người hỗ trợ chéo được
         tính cho TỔ GỐC — đúng như §9.2 đã quy ước cho tiền khoán.
      2. `ty_le_loi` = `so_luong_loi` ÷ `san_luong` × 100, với `so_luong_loi` = Σ số lượng lỗi KCS
         mà KCS đã CHỈ ĐÍCH DANH tổ này chịu (`san_xuat_kcs_loi.to_chiu_id`) và tổ đã nhận trách
         nhiệm (`accepted`) hoặc lỗi ghi một chiều (`recorded`). Lỗi `pending` (tổ chưa phản hồi)
         và `rejected` (tổ từ chối, không quy trách nhiệm) KHÔNG tính — chính hai trạng thái đó đã
         được model KCS định nghĩa như vậy, đây chỉ đọc lại cho đúng.

    Tra bậc ra `rate_pct` rồi `so_tien = tien_khoan × rate_pct / 100`. Nhân vào TIỀN KHOÁN chứ
    không phải (sản lượng × một đơn giá): một tổ có thể làm NHIỀU công đoạn trong cùng nhóm, mỗi
    công đoạn một đơn giá khoán. Khi tổ chỉ làm một công đoạn thì hai cách ra cùng một số, đúng
    công thức chủ nêu (5.000 × 5% × 300 = 75.000đ).

    `employee_id` NULL = tổ trưởng chưa nối tài khoản với hồ sơ nhân sự (`employees.user_id`) —
    dòng vẫn ghi để tiền không bốc hơi im lặng, nhưng bảng lương bỏ qua cho tới khi nối xong.
    `so_tien = 0` cũng GHI: tổ khai bậc mà rơi vào ô 0% thì phải thấy được là đã xét rồi, khác hẳn
    tổ chưa khai bậc (không có dòng nào)."""

    __tablename__ = "san_xuat_thuong_to_truong"
    __table_args__ = (
        UniqueConstraint("nhom_id", "department_id", name="uq_sx_thuong_tt_nhom_to"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nhom_id: Mapped[int] = mapped_column(
        ForeignKey("san_xuat_nhom.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Soft-ref `departments.id` — cùng kiểu neo với `piece_leader_bonus_brackets.department_id`.
    department_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # Ai là tổ trưởng LÚC ĐÓNG (`departments.head_user_id`). Đổi tổ trưởng sau đó không viết lại.
    head_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Ngày đóng nhóm — quyết định tiền rơi vào KỲ LƯƠNG nào.
    ngay: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    ky_nam: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    ky_thang: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # --- Snapshot đầu vào của phép tính ------------------------------------------------------
    san_luong: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False, default=0)
    tien_khoan: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    so_luong_loi: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False, default=0)
    ty_le_loi: Mapped[float] = mapped_column(Numeric(7, 4), nullable=False, default=0)   # %
    # --- Kết quả tra bậc ---------------------------------------------------------------------
    rate_pct: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)    # ±%
    so_tien: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)    # ± đồng
    ghi_chu: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
