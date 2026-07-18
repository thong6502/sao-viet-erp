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
AMOUNT_DEPT_ROW = "dept_row"  # trỏ 1 dòng bảng lương của tổ (source_salary_row_id) — đọc sống
AMOUNT_MODES = (AMOUNT_RULE, AMOUNT_MANUAL, AMOUNT_DEPT_ROW)

# --- Kiểu áp một dòng lương của phòng (Pha 1, lát 2) ------------------------
# Cách map một NV vào dòng mức lương khi gán vào phòng:
APPLY_CUNG = "cung"                       # gán tay (lương cứng thỏa thuận)
APPLY_BAC_THO = "bac_tho"                 # theo bậc thợ (pay_grade_key)
APPLY_THAM_NIEN = "tham_nien"             # theo nhóm thâm niên (seniority_band)
APPLY_THAM_NIEN_GT = "tham_nien_gioi_tinh"  # theo thâm niên × giới tính
SALARY_APPLY_BYS = (APPLY_CUNG, APPLY_BAC_THO, APPLY_THAM_NIEN, APPLY_THAM_NIEN_GT)

# --- Trạng thái tạm ứng (mirror leave workflow) -----------------------------
ADV_PENDING = "pending"
ADV_APPROVED = "approved"
ADV_REJECTED = "rejected"
ADV_CANCELLED = "cancelled"
ADVANCE_STATUSES = (ADV_PENDING, ADV_APPROVED, ADV_REJECTED, ADV_CANCELLED)

# --- Trạng thái kỳ lương ----------------------------------------------------
PERIOD_DRAFT = "draft"    # đang soạn, sửa được
PERIOD_LOCKED = "locked"  # đã chốt, khóa số
PERIOD_PAID = "paid"      # đã chi trả (khóa cứng; hủy chi → về locked)
PERIOD_STATUSES = (PERIOD_DRAFT, PERIOD_LOCKED, PERIOD_PAID)

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
    # Thử việc hưởng % của lương chính thức — công ty dùng 0.80 (Đ26 BLLĐ tối thiểu 85%).
    probation_ratio: Mapped[float] = mapped_column(
        Numeric(5, 4), nullable=False, default=0.80, server_default="0.80"
    )
    # Tỷ lệ NV đóng: BHXH 8% + BHYT 1.5% + BHTN 1% = 10.5%.
    bhxh_rate: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False, default=0.08, server_default="0.08")
    bhyt_rate: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False, default=0.015, server_default="0.015")
    bhtn_rate: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False, default=0.01, server_default="0.01")
    # Đoàn phí công đoàn NV đóng (mẫu 0.5% = 0.005). Mặc định 0 — chủ tự khai; trừ vào thực nhận, KHÔNG giảm TNCN.
    cong_doan_rate: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False, default=0, server_default="0")
    # Giảm trừ gia cảnh TNCN — mức 2026 (NQ 110/2025/UBTVQH15, từ kỳ tính thuế 2026).
    deduction_self: Mapped[float] = mapped_column(_MONEY, nullable=False, default=15_500_000, server_default="15500000")
    deduction_dependent: Mapped[float] = mapped_column(_MONEY, nullable=False, default=6_200_000, server_default="6200000")
    # Mức chuyên cần mặc định (thưởng đủ công).
    chuyen_can_default: Mapped[float] = mapped_column(_MONEY, nullable=False, default=300_000, server_default="300000")
    # --- Pha 4a: tăng ca (OT) + phụ cấp ca đêm ---
    # Giờ công chuẩn/ngày để quy đơn giá giờ khi tính OT.
    standard_hours_per_day: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=8, server_default="8")
    # Hệ số OT theo LOẠI NGÀY (Đ98): ngày thường ≥1.5 · ngày nghỉ tuần ≥2.0 · ngày lễ ≥3.0.
    ot_multiplier: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=1.5, server_default="1.5")
    ot_multiplier_restday: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=2.0, server_default="2")
    ot_multiplier_holiday: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=3.0, server_default="3")
    # Làm NGUYÊN CÔNG ngày nghỉ tuần / ngày lễ (Đ98 kh.1): CN ≥200% · lễ ≥300% (gồm cả lương công).
    restday_work_multiplier: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=2.0, server_default="2")
    holiday_work_multiplier: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=3.0, server_default="3")
    # Phụ cấp ca đêm: % đơn giá 1 công cho mỗi ngày làm ca đêm (Đ98 kh.2: ≥30%).
    night_pct: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0.30, server_default="0.3")
    # --- Pha 4a: trần đóng BHXH (mức tham chiếu × 20; đổi hằng năm → sửa ở tham số) ---
    # Trần BHXH+BHYT = 20× mức tham chiếu (2.53tr từ 1/7/2026 → 50.6tr). 0 = không áp trần.
    bh_base_cap: Mapped[float] = mapped_column(_MONEY, nullable=False, default=50_600_000, server_default="50600000")
    # Trần BHTN = 20× lương tối thiểu vùng (vùng I 5.31tr từ 1/1/2026 → 106.2tr). 0 = không áp trần.
    bhtn_base_cap: Mapped[float] = mapped_column(_MONEY, nullable=False, default=106_200_000, server_default="106200000")
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


class DepartmentSalaryRow(Base):
    """Một DÒNG trong 'bảng lương của phòng' (Pha 1, lát 2). Mỗi phòng tự thêm nhiều dòng
    mức lương, mỗi dòng: nhãn tự do + kiểu áp (cứng/bậc thợ/thâm niên/±giới tính) + 4 thành
    phần (vị trí/trách nhiệm/phụ cấp/chuyên cần). Một phòng có thể trộn nhiều kiểu (chủ chốt
    'cho chọn nhiều'). Khi gán người vào phòng, hệ thống gợi ý dòng khớp theo
    pay_grade_key/seniority_band/gender của người (lát sau)."""

    __tablename__ = "department_salary_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    department_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("departments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Nhãn tự do phòng đặt, vd "Tổ trưởng", "Thợ bậc 1", "Dưới 1 năm - Nam".
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    # Kiểu áp (xem SALARY_APPLY_BYS) — cách map người vào dòng này.
    apply_by: Mapped[str] = mapped_column(
        String(24), nullable=False, default=APPLY_CUNG, server_default=APPLY_CUNG
    )
    # Điều kiện khớp (null nếu kiểu áp không dùng chiều đó).
    pay_grade_key: Mapped[str | None] = mapped_column(String(20), nullable=True)
    seniority_band: Mapped[str | None] = mapped_column(String(8), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # 4 thành phần lương (VND). Tăng ca sẽ tính trên vị trí + trách nhiệm (lát engine).
    luong_vi_tri: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    luong_trach_nhiem: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    phu_cap: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    chuyen_can: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
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
    # rule = tự tra bảng chính sách; manual = dùng base_amount; dept_row = tra sống 1 dòng
    # bảng lương của tổ (source_salary_row_id) → mức đổi theo khi sửa bảng lương của tổ.
    amount_mode: Mapped[str] = mapped_column(String(8), nullable=False, default=AMOUNT_RULE, server_default=AMOUNT_RULE)
    base_amount: Mapped[float | None] = mapped_column(_MONEY, nullable=True)      # khi manual
    # Trỏ tới 1 dòng `department_salary_rows` (khi amount_mode=dept_row). Soft-ref (không FK cứng,
    # theo tiền lệ default_shift_id) → engine đọc SỐNG 4 thành phần của dòng lúc tính lương.
    source_salary_row_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Mức đóng BH (nullable → mặc định = mức lương). KHÔNG prorate theo công.
    insurance_base: Mapped[float | None] = mapped_column(_MONEY, nullable=True)
    # Phụ cấp hàng tháng của RIÊNG người này (cơm/xăng/điện thoại/kiêm nhiệm…). Cộng phẳng,
    # KHÔNG prorate, KHÔNG vào tăng ca. (Mỗi người mỗi khác → khai per-NV, không ở bảng lương tổ.)
    allowance: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    # Chuyên cần của RIÊNG người này (mỗi người mỗi khác). All-or-nothing: chỉ cộng khi đủ công.
    chuyen_can: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class SalaryAdvance(Base):
    """Tạm ứng lương — đa lần/tháng, gắn vào kỳ (year, month). Workflow duyệt như Nghỉ phép."""

    __tablename__ = "salary_advances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Mã tạm ứng (TU26-0001) — sinh khi tạo; nullable để migration backfill hàng cũ an toàn.
    code: Mapped[str | None] = mapped_column(String(32), unique=True, index=True, nullable=True)
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
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)   # Pha 4c: đã chi
    paid_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
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
    ot_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")      # tổng phút tăng ca (Pha 4a)
    ot_pay: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")          # tiền tăng ca (Pha 4a)
    night_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")      # số ngày ca đêm (Pha 4a)
    night_pay: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")       # phụ cấp ca đêm (Pha 4a)
    vi_pham: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")        # tay — giảm trừ khác (RAW; gộp trần 30% Đ102)
    other_bonus: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")    # tay (thưởng khác/hoa hồng)
    # --- Khoản chi tiết phiếu lương (Pha 4d) — HCNS nhập tay/tháng. Thưởng = thu nhập chịu thuế. ---
    thuong_5s: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    thuong_doanh_so: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    thuong_thanh_tich: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    phep_nam: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    tra_dong_phuc: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    dieu_chinh_luong: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")  # ± cộng đại số
    di_tre: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")           # đi trễ/về sớm/nghỉ KP (phạt)
    dt_vuot_troi: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")     # điện thoại vượt trội (phạt)
    phat_bien_ban: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    phat_5s_dong_phuc: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    gross: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    insurance_base: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    bhxh: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    cong_doan: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")        # đoàn phí = insurance_base×cong_doan_rate (tự tính, thử việc=0)
    pit: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")            # thuế TNCN (tự tính, có thể ghi đè tay)
    pit_manual: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")  # HCNS ghi đè TNCN tay (Pha 4b)
    pit_taxable: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")    # thu nhập tính thuế đã dùng (Pha 4b)
    advance_total: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    net_pay: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class PitTaxBracket(Base):
    """Bậc thuế TNCN lũy tiến từng phần (biểu THÁNG) — dữ liệu SỬA ĐƯỢC để cập nhật khi luật đổi.
    Seed 2026 = 5 bậc (Luật 109/2025/QH15). `up_to` = trần thu nhập TÍNH THUẾ/tháng của bậc;
    NULL = bậc cao nhất (∞). Bảng do create_all tạo (không migration), seed-once."""

    __tablename__ = "pit_tax_brackets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)                 # thứ tự bậc (1..N)
    up_to: Mapped[float | None] = mapped_column(_MONEY, nullable=True)        # trần bậc; NULL = ∞
    rate: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)        # thuế suất (0.05 = 5%)
