"""Plate/Die Rate model — Đơn giá kẽm & khuôn (catalog #5).

ONE table, discriminator `plate_type`, holding BOTH:
  A. Kẽm in offset (`ban_kem_offset`) — engine chọn theo MÁY áp dụng; tiền kẽm =
     số màu × số bộ kẽm × số form × đơn giá 1 bản.
  B. Khuôn gia công (`khuon_be` / `khuon_ep_kim` / `khuon_dap_noi` / `khuon_khac`) — engine
     lấy giá theo `pricing_method` (fixed/area/perimeter/size_tier/manual), tiền khuôn ghi vào
     dòng Gia công của công đoạn liên kết (Operation.tooling_rate_id).

Versioning = hiệu lực-theo-ngày (đóng & tạo mới) như Đơn giá giờ máy; family key = **`code`**
(một bản MỞ duy nhất mỗi mã → cho phép nhiều bảng giá kẽm PLATE_52/72/102/109 cùng loại).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from ..db import Base

# plate_type: kẽm vs các loại khuôn
PLATE_KEM = "ban_kem_offset"
DIE_TYPES = ("khuon_be", "khuon_ep_kim", "khuon_dap_noi", "khuon_khac")
VALID_PLATE_TYPES = (PLATE_KEM, *DIE_TYPES)
# pricing_method cho khuôn (kẽm luôn = per-bản, không dùng field này)
PRICING_METHODS = ("fixed", "area", "perimeter", "size_tier", "manual")
# reuse_price_method khi dùng lại khuôn cũ
REUSE_METHODS = ("zero", "maintenance_fee", "manual")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PlateDieRate(Base):
    __tablename__ = "plate_die_rates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Mã bảng giá (gõ tay): PLATE_102_CTP, DIE_BOX_STD… Family key của version-chain hiệu lực-ngày.
    code: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # plate_type: ban_kem_offset | khuon_be | khuon_ep_kim | khuon_dap_noi | khuon_khac
    plate_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    # technology / process: offset, flexo, be, ep_kim, dap_noi
    technology: Mapped[str] = mapped_column(String(32), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)  # ban, bo, cm2, met

    # --- A. Kẽm: loại kẽm + khổ kẽm + máy/khổ áp dụng ---------------------
    plate_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)  # ctp/ps/thuong
    plate_width_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    plate_height_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # list machine id áp dụng (NULL/[]=mọi máy) — engine chọn giá kẽm theo máy.
    machine_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    paper_size_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # --- Đơn giá (chung) --------------------------------------------------
    unit_price: Mapped[int] = mapped_column(
        BigInteger, CheckConstraint("unit_price >= 0"), nullable=False
    )
    setup_fee: Mapped[int] = mapped_column(
        BigInteger, CheckConstraint("setup_fee >= 0"), nullable=False, default=0
    )
    min_charge: Mapped[int] = mapped_column(
        BigInteger, CheckConstraint("min_charge >= 0"), nullable=False, default=0
    )

    # --- B. Khuôn: cách tính + đơn giá theo diện tích/chu vi + trần -------
    pricing_method: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="fixed", default="fixed"
    )
    unit_price_area: Mapped[int] = mapped_column(
        BigInteger, CheckConstraint("unit_price_area >= 0"), nullable=False,
        server_default="0", default=0,
    )
    unit_price_perimeter: Mapped[int] = mapped_column(
        BigInteger, CheckConstraint("unit_price_perimeter >= 0"), nullable=False,
        server_default="0", default=0,
    )
    max_charge: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    allow_manual_price: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="0", default=False
    )

    # --- Dùng lại khuôn cũ ------------------------------------------------
    reusable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # reuse_price_method: zero / maintenance_fee / manual (khi dùng lại)
    reuse_price_method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    maintenance_fee: Mapped[int] = mapped_column(
        BigInteger, CheckConstraint("maintenance_fee >= 0"), nullable=False,
        server_default="0", default=0,
    )

    # --- Nhà cung cấp / thời gian ----------------------------------------
    supplier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lead_time_days: Mapped[int] = mapped_column(
        Integer, CheckConstraint("lead_time_days >= 0"), nullable=False,
        server_default="0", default=0,
    )
    transport_fee: Mapped[int] = mapped_column(
        BigInteger, CheckConstraint("transport_fee >= 0"), nullable=False,
        server_default="0", default=0,
    )
    moq: Mapped[int] = mapped_column(
        Integer, CheckConstraint("moq >= 0"), nullable=False, server_default="0", default=0
    )

    # --- Hiệu lực / audit -------------------------------------------------
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="chk_plate_die_rates_effective_dates",
        ),
        # Một bản MỞ duy nhất mỗi mã (family key = code) → cho phép nhiều mã cùng plate_type.
        Index(
            "uix_plate_die_rates_current",
            "code",
            unique=True,
            sqlite_where=text("effective_to IS NULL"),
            postgresql_where=text("effective_to IS NULL"),
        ),
    )

    @property
    def is_plate(self) -> bool:
        return self.plate_type == PLATE_KEM
