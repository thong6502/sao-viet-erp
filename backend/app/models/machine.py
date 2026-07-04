"""Machine models — spec-20/21 master data.

Catalog of printing and processing machinery and their associated operating rates.
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
    Numeric,
    String,
    Text,
    JSON,
    false as sa_false,
    true as sa_true,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..db import Base

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Nhóm máy (spec A). Máy in / cán / bế / xén / khác.
MACHINE_GROUPS = ("may_in", "may_can", "may_be", "may_xen", "khac")
# Trạng thái máy (spec A): đang chạy / tạm ngưng / bảo trì.
MACHINE_STATUSES = ("active", "inactive", "maintenance")
# Làm tròn giờ máy (spec E).
ROUNDING_POLICIES = ("none", "0.01", "0.25", "0.5")

class Machine(Base):
    __tablename__ = "machines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # offset, digital, large_format, flexo...
    machine_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    # in, can_mang, be, gap...
    process_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # A — Nhóm máy (may_in/may_can/may_be/may_xen/khac) + trạng thái 3 mức + ghi chú.
    machine_group: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="may_in", default="may_in"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="active", default="active"
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    max_width_cm: Mapped[float | None] = mapped_column(
        Numeric(10, 2), CheckConstraint("max_width_cm >= 0"), nullable=True
    )
    max_height_cm: Mapped[float | None] = mapped_column(
        Numeric(10, 2), CheckConstraint("max_height_cm >= 0"), nullable=True
    )
    min_width_cm: Mapped[float | None] = mapped_column(
        Numeric(10, 2), CheckConstraint("min_width_cm >= 0"), nullable=True
    )
    min_height_cm: Mapped[float | None] = mapped_column(
        Numeric(10, 2), CheckConstraint("min_height_cm >= 0"), nullable=True
    )
    
    speed: Mapped[float] = mapped_column(
        Numeric(10, 2), CheckConstraint("speed > 0"), nullable=False
    )
    speed_unit: Mapped[str] = mapped_column(String(32), nullable=False) # trang/phut, to/gio, m2/gio
    
    setup_time_mins: Mapped[int] = mapped_column(
        Integer, CheckConstraint("setup_time_mins >= 0"), nullable=False, default=0
    )
    changeover_time_mins: Mapped[int] = mapped_column(
        Integer, CheckConstraint("changeover_time_mins >= 0"), nullable=False, default=0
    )
    setup_waste_sheets: Mapped[float] = mapped_column(
        Numeric(10, 2), CheckConstraint("setup_waste_sheets >= 0"), nullable=False, default=0.0
    )
    
    supported_materials: Mapped[list[str] | None] = mapped_column(JSON, nullable=True) # list material_type

    # #2 — số đơn vị in (số màu máy in được trong 1 lượt); pricing_engine dùng để tính số pass
    # (⌈màu/num_ink_units⌉) khi job nhiều màu hơn số đơn vị của máy (§31c). NULL = không tính pass.
    num_ink_units: Mapped[int | None] = mapped_column(
        Integer, CheckConstraint("num_ink_units IS NULL OR num_ink_units >= 1"), nullable=True
    )
    # #11 — trở nhật/lật: máy in được 2 mặt trong 1 lượt (perfecting). Thông tin cấu hình (§3).
    supports_perfecting: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # ---- B. Vùng in (tách khỏi khổ giấy) + bình bản ----
    # Khổ IN tối đa = vùng thực in được, ≤ khổ giấy tối đa. Nhíp + lề trừ ra khỏi vùng in khả dụng.
    max_print_width_cm: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    max_print_height_cm: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    gripper_cm: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False, server_default="0", default=0.0
    )
    side_margin_cm: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False, server_default="0", default=0.0
    )
    top_bottom_margin_cm: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False, server_default="0", default=0.0
    )
    # list paper_size id chạy được (rỗng/NULL = không giới hạn theo DM khổ).
    compatible_paper_size_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # ---- C. Dải tốc độ (speed = tốc độ chuẩn ở trên) ----
    min_speed: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    max_speed: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)

    # ---- D. Thời gian setup/vệ sinh/đổi màu/đổi kẽm (GIỜ). 0 hết ⇒ engine fallback (mins+changeover) ----
    setup_time_base_hour: Mapped[float] = mapped_column(Numeric(8, 3), nullable=False, server_default="0", default=0.0)
    setup_time_per_color_hour: Mapped[float] = mapped_column(Numeric(8, 3), nullable=False, server_default="0", default=0.0)
    setup_time_per_side_hour: Mapped[float] = mapped_column(Numeric(8, 3), nullable=False, server_default="0", default=0.0)
    cleaning_time_hour: Mapped[float] = mapped_column(Numeric(8, 3), nullable=False, server_default="0", default=0.0)
    color_change_time_hour: Mapped[float] = mapped_column(Numeric(8, 3), nullable=False, server_default="0", default=0.0)
    plate_change_time_per_plate_hour: Mapped[float] = mapped_column(Numeric(8, 3), nullable=False, server_default="0", default=0.0)
    color_check_time_hour: Mapped[float] = mapped_column(Numeric(8, 3), nullable=False, server_default="0", default=0.0)
    min_setup_time_hour: Mapped[float] = mapped_column(Numeric(8, 3), nullable=False, server_default="0", default=0.0)
    max_setup_time_hour: Mapped[float | None] = mapped_column(Numeric(8, 3), nullable=True)

    # ---- E. Chính sách đơn giá giờ (giá versioned ở MachineRate) ----
    rounding_hour_policy: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default="none", default="none"
    )
    overhead_included: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_true(), default=True
    )
    # hourly_rate_includes_operator (spec F)
    operator_included: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_true(), default=True
    )

    # ---- G. Audit / dùng ----
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
    
    rates: Mapped[list[MachineRate]] = relationship(
        "MachineRate",
        back_populates="machine",
        cascade="all, delete-orphan",
        order_by="MachineRate.effective_from.desc()",
    )

class MachineRate(Base):
    __tablename__ = "machine_rates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    machine_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("machines.id", ondelete="CASCADE"), index=True, nullable=False
    )
    hourly_rate: Mapped[int] = mapped_column(
        BigInteger, CheckConstraint("hourly_rate >= 0"), nullable=False
    )
    min_charge: Mapped[int] = mapped_column(
        BigInteger, CheckConstraint("min_charge >= 0"), nullable=False, default=0
    )
    min_run_time_mins: Mapped[int] = mapped_column(
        Integer, CheckConstraint("min_run_time_mins >= 0"), nullable=False, default=0
    )
    # Cấu thành đơn giá (tham khảo/diễn giải; engine chỉ dùng tổng hourly_rate). đ/giờ.
    rate_depreciation: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0", default=0)
    rate_energy: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0", default=0)
    rate_maintenance: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0", default=0)
    rate_labor: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0", default=0)
    rate_overhead: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0", default=0)

    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
    
    machine: Mapped[Machine] = relationship("Machine", back_populates="rates")
    
    __table_args__ = (
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="chk_machine_effective_dates"
        ),
        Index(
            "uix_machine_rates_current",
            "machine_id",
            unique=True,
            sqlite_where=text("effective_to IS NULL"),
            postgresql_where=text("effective_to IS NULL")
        )
    )
