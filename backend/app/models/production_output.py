"""Phiếu sản lượng công đoạn — nguồn khoán thật.

Ghi sản lượng THỰC mỗi công đoạn của một Lệnh sản xuất (LSX), do người có quyền (`san_luong`)
nhập. Là NGUỒN DUY NHẤT của lương khoán: mỗi phiếu = 1 NGƯỜI · SL × đơn giá − trừ lỗi = tiền khoán,
cộng thẳng vào cột `khoan` của bảng lương khi tính lương (không còn tầng "sổ khoán" ở giữa).

Bảng mới → create_all tự dựng (PHẢI đăng ký models/__init__). Link mềm (plain int) tới LSX/máy/công
đoạn theo convention soft-ref của repo — tránh coupling khóa cứng.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

_MONEY = Numeric(14, 2)

# Chế độ ghi (khớp cong_doan.khoan_ghi_theo). Khoán chỉ ghi theo NGƯỜI.
OUTPUT_BY_NGUOI = "nguoi"

# Nguyên nhân hỏng (5b-2). CHỈ 'loi_tho' mới trừ tiền thợ.
DEFECT_LOI_THO = "loi_tho"
DEFECT_CAUSES = (DEFECT_LOI_THO, "vat_tu", "thiet_bi", "file_thiet_ke", "cong_doan_truoc")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProductionOutput(Base):
    """Một dòng sản lượng: (LSX, công đoạn, tổ) × khối lượng đạt × đơn giá khoán."""

    __tablename__ = "production_outputs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # LSX (soft-ref production_orders.id) — bắt buộc: sản lượng luôn thuộc một lệnh.
    production_order_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    cong_doan: Mapped[str] = mapped_column(String(30), index=True, nullable=False)   # mã cong_doan.ma
    ghi_theo: Mapped[str] = mapped_column(String(8), nullable=False, default=OUTPUT_BY_NGUOI, server_default=OUTPUT_BY_NGUOI)
    # Kỳ khoán (năm/tháng) → cột `khoan` bảng lương của kỳ đó.
    year: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    month: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    group_name: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)   # tổ/bộ phận — để tra đơn giá
    employee_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)      # người nhận tiền khoán
    may_id: Mapped[int | None] = mapped_column(Integer, nullable=True)                       # soft-ref máy (thống kê)
    piece_rate_id: Mapped[int | None] = mapped_column(Integer, nullable=True)                # đơn giá nguồn
    work_name: Mapped[str] = mapped_column(String(255), nullable=False)                      # tên công việc (snapshot)
    unit: Mapped[str] = mapped_column(String(12), nullable=False, default="khac", server_default="khac")
    unit_price: Mapped[float] = mapped_column(_MONEY, nullable=False)                        # đơn giá (snapshot)
    quantity: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")  # sản lượng đạt
    # Pha 5b-2 trừ lỗi: sản lượng HỎNG + nguyên nhân; defect_deduction = tiền trừ (tính lúc ghi,
    # chỉ >0 khi cause=loi_tho VÀ vượt ngưỡng công đoạn). Chỉ 'loi_tho' mới trừ (máy/vật tư/file/
    # công đoạn trước → không trừ thợ). Sàn 0 áp khi cộng vào lương.
    defect_qty: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    defect_cause: Mapped[str | None] = mapped_column(String(20), nullable=True)
    defect_deduction: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    # LSX bù (order_kind='bu'): mặc định KHÔNG tính khoán (công làm lại = trách nhiệm); HCNS bật khi
    # bù do lỗi khách/vật tư. Chỉ output tinh_khoan=true mới cộng vào cột khoán.
    tinh_khoan: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    work_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    recorded_by: Mapped[int | None] = mapped_column(Integer, nullable=True)                  # user ghi
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
