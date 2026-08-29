"""Tồn CUỐI KỲ đã CHỐT khi khóa kỳ (snapshot N-X-T) — docs/spec-bao-cao-kho.md.

1 dòng = tồn CUỐI của MỘT mặt hàng tại MỘT kho ở CUỐI một kỳ đã khóa (`den_ngay`). Chốt lúc bấm
**Khóa kỳ**: `GT cuối = GT đầu (snapshot kỳ trước) + GT nhập − GT xuất(BQ kỳ này)`. Kỳ SAU đọc thẳng
dòng này làm ĐẦU KỲ → "đầu kỳ = cuối kỳ trước" đúng tuyệt đối, tự nối chuỗi (bình quân gia quyền
cuối kỳ). Mở lại kỳ → xoá các dòng của kỳ đó để tính lại.

Bảng MỚI → `create_all` tự dựng (không migration). Đây là LỚP báo cáo — KHÔNG phải nguồn tồn thật
(tồn thật vẫn Σ `stock_lots.sl_con_lai`); `SL/GT` ở đây là bản dựng theo BQ để in báo cáo kỳ.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    BigInteger, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class KhoKyTon(Base):
    """Tồn cuối kỳ đã chốt của 1 mặt hàng / 1 kho / 1 kỳ (khi khóa sổ)."""

    __tablename__ = "kho_ky_ton"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kho_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("kho_hang.id", ondelete="CASCADE"), index=True, nullable=False
    )
    hang_loai: Mapped[str] = mapped_column(String(10), nullable=False)   # "giay" | "vat_tu"
    hang_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # Khoảng kỳ đã chốt. `den_ngay` = mốc "as-of" của snapshot (đầu kỳ sau đọc dòng có den < tu sau).
    tu_ngay: Mapped[date] = mapped_column(Date, nullable=False)
    den_ngay: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    ten_ky: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Tồn CUỐI kỳ: số lượng theo ĐVT gốc + giá trị (đồng) + đơn giá bình quân của kỳ.
    sl_cuoi: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False, default=0)
    gt_cuoi: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    don_gia_bq: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    # Bản ghi khóa sổ đã sinh ra dòng này (để truy vết; xoá khi mở kỳ dò theo khoảng ngày + kho).
    khoa_so_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("kho_khoa_so.id", ondelete="SET NULL"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    __table_args__ = (
        # 1 mặt hàng / 1 kho chỉ có MỘT tồn cuối cho MỘT mốc kỳ (den_ngay). Khóa lại kỳ cũ → upsert đè.
        UniqueConstraint("kho_id", "hang_loai", "hang_id", "den_ngay", name="uq_kho_ky_ton"),
    )
