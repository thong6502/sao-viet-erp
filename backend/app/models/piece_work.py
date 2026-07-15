"""Đơn giá khoán ORM (module `luong`, nhịp 2).

Một bảng duy nhất:
  - `piece_rates` — đơn giá khoán theo tổ/bộ phận + đơn vị (m²/bài in/tấn/cuốn/lượt/hộp).
                    Số hóa các bảng "CÔNG KHOÁN" thật; là bảng giá tra khi ghi Phiếu sản lượng.

Lương khoán KHÔNG còn tầng "sổ khoán" (quỹ tổ + chia hệ số). Tiền khoán mỗi NV = Phiếu sản
lượng theo NGƯỜI (SL × đơn giá − trừ lỗi) cộng thẳng vào cột `khoan` của payroll_lines khi tính
lương (xem PieceWorkService.khoan_map). Portable SQLite/Postgres.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# --- Đơn vị tính đơn giá khoán ----------------------------------------------
UNIT_M2 = "m2"          # mét vuông (bồi, cán/phủ)
UNIT_BAI_IN = "bai_in"  # bài in (máy in, theo số màu)
UNIT_TAN = "tan"        # tấn (cắt giấy cuộn)
UNIT_CUON = "cuon"      # cuốn (cắt/bắt thành phẩm)
UNIT_LUOT = "luot"      # lượt (cắt demi)
UNIT_HOP = "hop"        # hộp (gỡ hàng)
UNIT_TO = "to"          # tờ
UNIT_KHAC = "khac"      # khác
PIECE_UNITS = (UNIT_M2, UNIT_BAI_IN, UNIT_TAN, UNIT_CUON, UNIT_LUOT, UNIT_HOP, UNIT_TO, UNIT_KHAC)

_MONEY = Numeric(14, 2)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PieceRate(Base):
    """Đơn giá khoán: 1 công việc của 1 tổ với đơn vị + đơn giá."""

    __tablename__ = "piece_rates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Tổ khoán (vd 'to_boi', 'to_can_phu', 'to_cat', 'may_in_5mau'). Trục gom + tra.
    group_name: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    code: Mapped[str | None] = mapped_column(String(20), nullable=True)  # mã (A–F cho máy in)
    name: Mapped[str] = mapped_column(String(255), nullable=False)       # tên công việc
    # Công đoạn gắn đơn giá (mã cong_doan.ma) — tra đơn giá theo (tổ + công đoạn) khi ghi phiếu.
    cong_doan: Mapped[str | None] = mapped_column(String(30), index=True, nullable=True)
    unit: Mapped[str] = mapped_column(String(12), nullable=False, default=UNIT_KHAC, server_default=UNIT_KHAC)
    unit_price: Mapped[float] = mapped_column(_MONEY, nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
