"""Khóa sổ kỳ kế toán công nợ (chốt công nợ) — đồng nhất với kho_khoa_so.

LOG APPEND-ONLY: mỗi lần khóa/mở ghi 1 bản ghi cho KHOẢNG ngày [tu_ngay, den_ngay].
'hanh_dong' = 'khoa' | 'mo'. Phiếu tại ngày bị khóa nếu bản ghi MỚI NHẤT phủ ngày đó có hanh_dong='khoa'.
'mo' ghi sau đè 'khoa' ghi trước.

Bảng MỚI -> create_all tự dựng; có migration trong db_migrations.py.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


#: Phân hệ công nợ. Trùng đúng bộ giá trị `CongNoKyChot.phan_he` đang dùng.
PHAN_HE_PHAI_THU = "phai_thu"
PHAN_HE_PHAI_TRA = "phai_tra"
PHAN_HE = (PHAN_HE_PHAI_THU, PHAN_HE_PHAI_TRA)


class CongNoKhoaSo(Base):
    """1 thao tác khóa/mở kỳ kế toán công nợ (append-only = hiệu lực + lịch sử)."""

    __tablename__ = "cong_no_khoa_so"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # PHÂN HỆ bị khoá — `phai_thu` (TK 131) hoặc `phai_tra` (TK 331). Thêm 04/09/2026 vì chủ báo:
    # *"tôi mới chốt công nợ phải trả sao nó tự động chốt công nợ phải thu, 2 cái này khác nhau
    # mà"*. Đúng: hai sổ độc lập, chốt sổ mua hàng không được đụng tới sổ bán hàng.
    #
    # NULL = bản ghi CŨ, sinh ra khi bảng chưa có cột này ⇒ nó KHOÁ CẢ HAI phân hệ. Giữ đúng
    # nghĩa lịch sử thay vì gán bừa một bên — bản ghi đó thật sự đã khoá cả hai.
    phan_he: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    tu_ngay: Mapped[date] = mapped_column(Date, nullable=False)
    den_ngay: Mapped[date] = mapped_column(Date, nullable=False)
    hanh_dong: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default="khoa", default="khoa"
    )
    nguoi_khoa_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    khoa_luc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    ten: Mapped[str | None] = mapped_column(String(120), nullable=True)


class CongNoKyChot(Base):
    """Snapshot công nợ chi tiết từng đối tượng / đơn / đợt giao khi chốt kỳ."""

    __tablename__ = "cong_no_ky_chot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Phân hệ: 'phai_thu' (AR) | 'phai_tra' (AP)
    phan_he: Mapped[str] = mapped_column(String(16), nullable=False)
    # Đối tượng: customer_id hoặc supplier_id
    doi_tuong_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # Loại tham chiếu: 'sales_invoice', 'purchase_delivery', 'deposit'
    ref_type: Mapped[str] = mapped_column(String(32), nullable=False)
    ref_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # Khoảng kỳ đã chốt
    tu_ngay: Mapped[date] = mapped_column(Date, nullable=False)
    den_ngay: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    ten_ky: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Số tiền tại thời điểm chốt kỳ
    tong_tien: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    da_thanh_toan: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    con_no: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    is_settled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
