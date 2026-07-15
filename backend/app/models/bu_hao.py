"""Danh mục Bù hao (waste) — bảng tra số tờ bù hao theo TRỤC (số màu / số con) × BẬC số lượng.

Mô hình MỞ: bậc số lượng là DỮ LIỆU (cột `bac` JSON), KHÔNG phải cột cứng — xưởng thêm/bớt/đổi
ngưỡng bậc thoải mái, không đụng schema. Trục tra tường minh bằng số (`key_tu..key_den`):
- truc=so_mau: dòng "In 3-4 màu" ⇒ key 3..4 (engine tra: số màu đơn nằm trong dải).
- truc=so_con: dòng "Sóng 1 con" ⇒ key 1..1; "nhiều con" ⇒ 2..999.

`bac` = [{"sl_tu":0,"sl_den":3000,"gia_tri":150,"don_vi":"to"}, …]; đơn vị mỗi bậc tự chọn
tờ|% (bậc SL lớn thường %). Danh mục tra cứu — engine (khi dựng lại) đọc lookup theo trục+SL.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Integer, JSON, String, true as sa_true
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

TRUC_BU_HAO = ("so_mau", "so_con")   # tra theo số màu (giấy in) | số con (sóng bồi/bế)
DON_VI_BAC = ("to", "pct")           # giá trị bậc = số tờ | %


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BuHao(Base):
    """1 dòng bù hao = 1 dải trục (số màu / số con) + danh sách bậc số lượng động."""

    __tablename__ = "bu_hao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ma: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    ten: Mapped[str] = mapped_column(String(150), nullable=False)     # "In 3-4 màu" / "Sóng — nhiều con"
    truc: Mapped[str] = mapped_column(String(8), index=True, nullable=False,
                                      server_default="so_mau", default="so_mau")  # so_mau|so_con
    key_tu: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)   # dải trục từ
    key_den: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)  # dải trục đến
    # Bậc số lượng ĐỘNG: [{sl_tu, sl_den(None=∞), gia_tri, don_vi}]
    bac: Mapped[list | None] = mapped_column(JSON, nullable=True)
    ghi_chu: Mapped[str | None] = mapped_column(String(500), nullable=True)

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_true(), default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )



