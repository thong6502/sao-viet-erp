"""Operation models — spec-20/21 master data.

Catalog of post-press finishing steps and operations (folding, binding, packing, etc.)
and their associated processing cost rates.
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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..db import Base

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

class Operation(Base):
    __tablename__ = "operations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # in, can_mang, be, gap, dong_cuon, dong_goi...
    operation_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False) # m2, luot, to, cuon...
    allow_outsource: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # basis_quantity: đại lượng engine nhân với run_rate (m2/to/luot/cm2/cuon/cai/thung/kg) — §2.2
    basis_quantity: Mapped[str] = mapped_column(String(16), nullable=False, server_default="to")
    # pricing_method: hình thức tính công NC (none/theo_gio/theo_ca/theo_sp/khoan) — mục 14 / spec §D
    pricing_method: Mapped[str] = mapped_column(String(16), nullable=False, server_default="theo_sp")

    # --- spec §A: phân nhóm & luồng xử lý ---------------------------------
    # process_group: sau_in / dong_goi / dac_biet
    process_group: Mapped[str] = mapped_column(String(20), nullable=False, server_default="sau_in")
    # process_type: internal / outsource / both — nội bộ / thuê ngoài / cả hai
    process_type: Mapped[str] = mapped_column(String(16), nullable=False, server_default="internal")
    default_sequence: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    # --- spec §B: công thức lượng tính ------------------------------------
    # quantity_formula_type: print_sheet_qty / finished_qty / area_m2 / linear_meter /
    #                        book_qty / box_qty / pack_qty / manual
    quantity_formula_type: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="print_sheet_qty"
    )
    allow_manual_quantity: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="0", default=False
    )

    # --- spec §C: cách tính nội bộ ----------------------------------------
    # internal_pricing_method: per_qty / per_hour / combined — theo sản lượng / giờ máy / kết hợp
    internal_pricing_method: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="per_qty"
    )
    # labor_people_count: số người tham gia (dùng cho nhân công theo giờ) — spec §D
    labor_people_count: Mapped[float] = mapped_column(
        Numeric(6, 2), CheckConstraint("labor_people_count >= 0"),
        nullable=False, server_default="1", default=1.0,
    )

    # --- spec §F: khuôn / tooling -----------------------------------------
    has_tooling: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0", default=False)
    # tooling_type: khuon_be / khuon_ep_kim / khuon_dap_noi / other
    tooling_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Link tới bảng giá khuôn ở DM Đơn giá kẽm & khuôn (#5). Khi set, engine lấy giá khuôn
    # theo pricing_method của bảng giá đó; NULL = dùng tooling_unit_price cũ trên OperationRate.
    tooling_rate_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)

    # --- spec §G: hao hụt (cờ + default; rule chi tiết ở Định mức & Bù hao) ---
    has_yield_loss: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0", default=False)
    # default_yield_rate: tỷ lệ đạt mặc định (%), vd 98.00
    default_yield_rate: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    # default_yield_rule: mã rule bù hao mặc định, vd YIELD_DIECUT
    default_yield_rule: Mapped[str | None] = mapped_column(String(40), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
    
    rates: Mapped[list[OperationRate]] = relationship(
        "OperationRate",
        back_populates="operation",
        cascade="all, delete-orphan",
        order_by="OperationRate.effective_from.desc()",
    )

class OperationRate(Base):
    __tablename__ = "operation_rates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("operations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    setup_fee: Mapped[int] = mapped_column(
        BigInteger, CheckConstraint("setup_fee >= 0"), nullable=False, default=0
    )
    run_rate: Mapped[int] = mapped_column(
        BigInteger, CheckConstraint("run_rate >= 0"), nullable=False, default=0
    )
    labor_rate: Mapped[int] = mapped_column(
        BigInteger, CheckConstraint("labor_rate >= 0"), nullable=False, default=0
    )
    min_charge: Mapped[int] = mapped_column(
        BigInteger, CheckConstraint("min_charge >= 0"), nullable=False, default=0
    )
    speed: Mapped[float] = mapped_column(
        Numeric(10, 2), CheckConstraint("speed >= 0"), nullable=False, default=0.0
    )
    # setup_time_mins: thời gian setup/đổi khuôn cho công đoạn (phút) — mục 12
    setup_time_mins: Mapped[float] = mapped_column(
        Numeric(10, 2), CheckConstraint("setup_time_mins >= 0"), nullable=False, server_default="0", default=0.0
    )

    # --- spec §C: đơn giá giờ máy nội bộ (per_hour / combined) ------------
    hourly_rate: Mapped[int] = mapped_column(
        BigInteger, CheckConstraint("hourly_rate >= 0"), nullable=False, server_default="0", default=0
    )

    # --- spec §D: nhân công đa hình thức (labor_rate = đơn giá giờ công / sản phẩm) ---
    labor_shift_rate: Mapped[int] = mapped_column(
        BigInteger, CheckConstraint("labor_shift_rate >= 0"), nullable=False, server_default="0", default=0
    )
    labor_fixed: Mapped[int] = mapped_column(
        BigInteger, CheckConstraint("labor_fixed >= 0"), nullable=False, server_default="0", default=0
    )
    labor_min: Mapped[int] = mapped_column(
        BigInteger, CheckConstraint("labor_min >= 0"), nullable=False, server_default="0", default=0
    )

    # --- spec §F: đơn giá khuôn -------------------------------------------
    tooling_unit_price: Mapped[int] = mapped_column(
        BigInteger, CheckConstraint("tooling_unit_price >= 0"), nullable=False, server_default="0", default=0
    )

    # --- spec §E: bảng giá thuê ngoài -------------------------------------
    outsource_supplier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    outsource_unit_price: Mapped[int] = mapped_column(
        BigInteger, CheckConstraint("outsource_unit_price >= 0"), nullable=False, server_default="0", default=0
    )
    outsource_setup_fee: Mapped[int] = mapped_column(
        BigInteger, CheckConstraint("outsource_setup_fee >= 0"), nullable=False, server_default="0", default=0
    )
    outsource_min_charge: Mapped[int] = mapped_column(
        BigInteger, CheckConstraint("outsource_min_charge >= 0"), nullable=False, server_default="0", default=0
    )
    outsource_transport_fee: Mapped[int] = mapped_column(
        BigInteger, CheckConstraint("outsource_transport_fee >= 0"), nullable=False, server_default="0", default=0
    )
    outsource_moq: Mapped[int] = mapped_column(
        BigInteger, CheckConstraint("outsource_moq >= 0"), nullable=False, server_default="0", default=0
    )
    outsource_lead_time_days: Mapped[int] = mapped_column(
        Integer, CheckConstraint("outsource_lead_time_days >= 0"), nullable=False, server_default="0", default=0
    )

    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
    
    operation: Mapped[Operation] = relationship("Operation", back_populates="rates")
    
    __table_args__ = (
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="chk_operation_effective_dates"
        ),
        Index(
            "uix_operation_rates_current",
            "operation_id",
            unique=True,
            sqlite_where=text("effective_to IS NULL"),
            postgresql_where=text("effective_to IS NULL")
        )
    )
