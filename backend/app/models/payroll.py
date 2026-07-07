"""Payroll ORM models (module `luong`, Phase 1 — lương thời gian).

Sáu bảng:
  - `payroll_params`     — cấu hình chung (1 dòng active): công chuẩn, %thử việc, tỷ lệ BHXH,
                            giảm trừ gia cảnh, mức chuyên cần mặc định.
  - `salary_rate_rules`  — bảng chính sách MỨC lương theo (nhóm, bậc, thâm niên, giới tính).
                            Lookup khớp cụ thể nhất, `effective_from ≤ kỳ`.
  - `employee_salaries`  — lương ẤN ĐỊNH của 1 NV, versioned theo `effective_from` (điều chỉnh
                            = thêm bản ghi mới, giữ lịch sử). manual/rule.
  - `salary_advances`    — tạm ứng lương (đa lần/tháng, workflow duyệt như Nghỉ phép).
  - `payroll_periods`    — kỳ lương tháng (year, month UNIQUE); draft→locked.
  - `payroll_lines`      — dòng lương 1 NV/kỳ (snapshot bất biến khi khóa).

Portable SQLite/Postgres: Numeric(14,2) cho tiền, Date/DateTime DB-agnostic.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# --- Nhóm thâm niên (suy từ hire_date) --------------------------------------
BAND_LT1 = "lt1"        # dưới 1 năm
BAND_Y1_5 = "y1_5"      # 1–5 năm
BAND_Y5_10 = "y5_10"    # 5–10 năm
BAND_GT10 = "gt10"      # trên 10 năm
SENIORITY_BANDS = (BAND_LT1, BAND_Y1_5, BAND_Y5_10, BAND_GT10)

# --- Cách lấy mức lương của 1 NV --------------------------------------------
AMOUNT_RULE = "rule"      # tra bảng chính sách theo nhóm/bậc/thâm niên
AMOUNT_MANUAL = "manual"  # nhập tay (quản lý cấp cao / đặc biệt)
AMOUNT_MODES = (AMOUNT_RULE, AMOUNT_MANUAL)

# --- Trạng thái tạm ứng (mirror leave workflow) -----------------------------
ADV_PENDING = "pending"
ADV_APPROVED = "approved"
ADV_REJECTED = "rejected"
ADV_CANCELLED = "cancelled"
ADVANCE_STATUSES = (ADV_PENDING, ADV_APPROVED, ADV_REJECTED, ADV_CANCELLED)

# --- Trạng thái kỳ lương ----------------------------------------------------
PERIOD_DRAFT = "draft"    # đang soạn, sửa được
PERIOD_LOCKED = "locked"  # đã chốt, khóa số
PERIOD_STATUSES = (PERIOD_DRAFT, PERIOD_LOCKED)

_MONEY = Numeric(14, 2)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PayrollParams(Base):
    """Tham số cấu hình lương — 1 dòng active (id nhỏ nhất). Không hardcode."""

    __tablename__ = "payroll_params"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Công chuẩn/tháng để prorate lương thời gian (đủ công = 1.0 tháng).
    standard_cong_default: Mapped[float] = mapped_column(
        Numeric(6, 2), nullable=False, default=26, server_default="26"
    )
    # Thử việc hưởng % của lương chính thức.
    probation_ratio: Mapped[float] = mapped_column(
        Numeric(5, 4), nullable=False, default=0.8, server_default="0.8"
    )
    # Tỷ lệ NV đóng: BHXH 8% + BHYT 1.5% + BHTN 1% = 10.5%.
    bhxh_rate: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False, default=0.08, server_default="0.08")
    bhyt_rate: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False, default=0.015, server_default="0.015")
    bhtn_rate: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False, default=0.01, server_default="0.01")
    # Giảm trừ gia cảnh TNCN (để sẵn cho Phase TNCN auto).
    deduction_self: Mapped[float] = mapped_column(_MONEY, nullable=False, default=11_000_000, server_default="11000000")
    deduction_dependent: Mapped[float] = mapped_column(_MONEY, nullable=False, default=4_400_000, server_default="4400000")
    # Mức chuyên cần mặc định (thưởng đủ công).
    chuyen_can_default: Mapped[float] = mapped_column(_MONEY, nullable=False, default=300_000, server_default="300000")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class SalaryRateRule(Base):
    """Một dòng = một MỨC lương chuẩn cho một tổ hợp (nhóm, bậc, thâm niên, giới tính).
    Chiều nào không áp dụng để NULL (wildcard). Lookup chọn dòng khớp cụ thể nhất."""

    __tablename__ = "salary_rate_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Nhóm lương (trục chính) — vd 'to_in', 'to_dan', 'van_phong'. Khóa tra chính.
    payroll_group: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    # Bậc lương chuẩn hóa (tổ In): 'tho_1'/'tho_2'/'tho_3'/'phu_1'/'phu_2'. NULL nếu không theo bậc.
    pay_grade_key: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Nhóm thâm niên (lt1/y1_5/y5_10/gt10). NULL = mọi thâm niên.
    seniority_band: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # Giới tính (male/female). NULL = mọi giới.
    gender: Mapped[str | None] = mapped_column(String(8), nullable=True)
    monthly_amount: Mapped[float] = mapped_column(_MONEY, nullable=False)
    # Mức chuyên cần riêng cho nhóm (NULL = dùng params.chuyen_can_default).
    chuyen_can: Mapped[float | None] = mapped_column(_MONEY, nullable=True)
    effective_from: Mapped[date | None] = mapped_column(Date, index=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class EmployeeSalary(Base):
    """Lương ấn định của 1 NV tại một mốc hiệu lực. Điều chỉnh lương = thêm bản ghi mới
    (giữ lịch sử); "hiện hành" cho 1 kỳ = bản có effective_from lớn nhất ≤ kỳ."""

    __tablename__ = "employee_salaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    effective_from: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    # rule = tự tra bảng chính sách; manual = dùng base_amount.
    amount_mode: Mapped[str] = mapped_column(String(8), nullable=False, default=AMOUNT_RULE, server_default=AMOUNT_RULE)
    base_amount: Mapped[float | None] = mapped_column(_MONEY, nullable=True)      # khi manual
    # Mức đóng BH (nullable → mặc định = mức lương). KHÔNG prorate theo công.
    insurance_base: Mapped[float | None] = mapped_column(_MONEY, nullable=True)
    # Phụ cấp cố định hàng tháng (điện thoại, kiêm nhiệm…).
    allowance: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class SalaryAdvance(Base):
    """Tạm ứng lương — đa lần/tháng, gắn vào kỳ (year, month). Workflow duyệt như Nghỉ phép."""

    __tablename__ = "salary_advances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    period_year: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    period_month: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    advance_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[float] = mapped_column(_MONEY, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(12), index=True, nullable=False, default=ADV_PENDING, server_default=ADV_PENDING)
    decided_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class PayrollPeriod(Base):
    """Kỳ lương 1 tháng. UNIQUE(year, month). Chốt = chuyển sang locked, khóa số."""

    __tablename__ = "payroll_periods"
    __table_args__ = (UniqueConstraint("year", "month", name="uq_payroll_period_ym"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(8), nullable=False, default=PERIOD_DRAFT, server_default=PERIOD_DRAFT)
    standard_cong: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=26, server_default="26")
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class PayrollLine(Base):
    """Dòng lương 1 NV trong 1 kỳ. Sinh khi "Tạo bảng lương"; sửa được ô tay khi draft;
    snapshot bất biến sau khi khóa kỳ."""

    __tablename__ = "payroll_lines"
    __table_args__ = (UniqueConstraint("period_id", "employee_id", name="uq_payroll_line_pe"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    period_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("payroll_periods.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    is_probation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    actual_cong: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0, server_default="0")
    standard_cong: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=26, server_default="26")
    monthly_salary: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    luong_cong: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    chuyen_can: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    allowance: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    khoan: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")          # lương khoán (nhịp 2)
    vi_pham: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")        # tay
    other_bonus: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")    # tay (thưởng/hoa hồng)
    gross: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    insurance_base: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    bhxh: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    pit: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")            # tay
    advance_total: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    net_pay: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
