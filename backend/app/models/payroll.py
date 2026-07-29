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

Cấu hình lương — hai cấp `NV → tổ` (KHÔNG còn hệ thống bậc lương):
  - `employee_salaries`           — lương vị trí (= lương cơ bản = mức đóng BH) + trách nhiệm +
                                    3 khoản PHỤ CẤP KHAI TAY (ca · thâm niên · khác). Bậc thợ
                                    chỉ là free-text `employees.job_grade`, hệ thống không quản.
  - `department_salary_components` — bật/tắt + MỨC theo BỘ PHẬN: KPI · chuyên cần · khoán · tăng ca.

Portable SQLite/Postgres: Numeric(14,2) cho tiền, Date/DateTime DB-agnostic.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint,
    false as sa_false, true as sa_true,
)
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
# LOẠI phiếu trên bảng salary_advances (chủ 2026-07-24): tạm ứng ad-hoc vs thanh toán lương đợt 1
# (số cố định theo hồ sơ). Cùng workflow duyệt, tách nhau khi hiển thị trên phiếu lương.
ADV_KIND_TAM_UNG = "tam_ung"
ADV_KIND_LUONG_DOT_1 = "luong_dot_1"
ADVANCE_KINDS = (ADV_KIND_TAM_UNG, ADV_KIND_LUONG_DOT_1)

# --- Trạng thái kỳ lương ----------------------------------------------------
PERIOD_DRAFT = "draft"    # đang soạn, sửa được
PERIOD_LOCKED = "locked"  # đã chốt, khóa số
PERIOD_PAID = "paid"      # đã chi trả (khóa cứng; hủy chi → về locked)
PERIOD_STATUSES = (PERIOD_DRAFT, PERIOD_LOCKED, PERIOD_PAID)

# --- Thành phần lương bật/tắt theo BỘ PHẬN (màn Cấu hình lương, Tab 2) -------
COMP_KPI = "kpi"                                # thưởng năng suất KPI — `value` = mức trần đ/tháng
COMP_CHUYEN_CAN = "chuyen_can"                  # `value` = đ/tháng (trừ dần theo ngày nghỉ — C3)
COMP_LUONG_KHOAN = "luong_khoan"                # bật/tắt — soi cờ departments.has_piece_work
COMP_TANG_CA = "tang_ca"                        # bật/tắt tăng ca theo giờ
# Ba khoản phụ cấp (ca · trách nhiệm · thâm niên) ĐÃ CHUYỂN sang khai TAY theo TỪNG NGƯỜI ở
# `employee_salaries` — chủ chốt 2026-07-20: "cho nó khai tay đi, hệ thống không cần tính toán".
SALARY_COMPONENT_KEYS = (
    COMP_KPI, COMP_CHUYEN_CAN, COMP_LUONG_KHOAN, COMP_TANG_CA,
)

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
    # Tỷ lệ NGƯỜI SỬ DỤNG LAO ĐỘNG đóng: BHXH 17.5% + BHYT 3% + BHTN 1% = 21.5%.
    # KHÔNG trừ vào lương NV — chỉ để tính chi phí bảo hiểm của công ty + tổng quỹ lương.
    bhxh_rate_er: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False, default=0.175, server_default="0.175")
    bhyt_rate_er: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False, default=0.03, server_default="0.03")
    bhtn_rate_er: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False, default=0.01, server_default="0.01")
    # Đoàn phí công đoàn NV đóng (mẫu 0.5% = 0.005). Mặc định 0 — chủ tự khai; trừ vào thực nhận, KHÔNG giảm TNCN.
    cong_doan_rate: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False, default=0, server_default="0")
    # Tỷ lệ TNLĐ-BNN (Tai nạn lao động – Bệnh nghề nghiệp) do CÔNG TY chịu, mẫu 0.5% = 0.005. Dùng khi NV
    # có BH đóng ở nơi khác (cờ `employee_salaries.insurance_elsewhere`): công ty chỉ chịu khoản này, KHÔNG
    # trừ vào lương NV. Chỉ hiển thị ở màn Sửa lương (FE), engine không xuất vào bảng lương tháng.
    tnld_bnn_rate: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False, default=0.005, server_default="0.005")
    # Giảm trừ gia cảnh TNCN — mức 2026 (NQ 110/2025/UBTVQH15, từ kỳ tính thuế 2026).
    deduction_self: Mapped[float] = mapped_column(_MONEY, nullable=False, default=15_500_000, server_default="15500000")
    deduction_dependent: Mapped[float] = mapped_column(_MONEY, nullable=False, default=6_200_000, server_default="6200000")
    # DORMANT từ 2026-07-23 (chủ chốt): tiền chuyên cần chỉ khai ở HỒ SƠ NV, tổ chỉ còn công tắc
    # bật/tắt. Engine KHÔNG còn đọc cột này — giữ lại để không phải drop cột trên DB thật.
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
    # PHỤ TRỘI GIỜ ĐÊM (chủ 2026-07-22): dùng cho phần cộng dồn TĂNG CA ĐÊM (Đ98.3) — mặc định 0.3 = +30%
    # (sàn luật). Giờ đêm TRONG ca theo lịch dùng hệ số per-ca `work_shifts.night_multiplier` (khác).
    night_pct: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0.30, server_default="0.3")
    # Cộng dồn TĂNG CA ĐÊM (Đ98.3): +20% × hệ số loại ngày trên đơn giá giờ. Mặc định 0.2. KHAI ĐƯỢC.
    ot_night_extra_pct: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False, default=0.20, server_default="0.2")
    # --- Pha 4a: trần đóng BHXH (mức tham chiếu × 20; đổi hằng năm → sửa ở tham số) ---
    # Trần BHXH+BHYT = 20× mức tham chiếu (2.53tr từ 1/7/2026 → 50.6tr). 0 = không áp trần.
    bh_base_cap: Mapped[float] = mapped_column(_MONEY, nullable=False, default=50_600_000, server_default="50600000")
    # Trần BHTN = 20× lương tối thiểu vùng (vùng I 5.31tr từ 1/1/2026 → 106.2tr). 0 = không áp trần.
    bhtn_base_cap: Mapped[float] = mapped_column(_MONEY, nullable=False, default=106_200_000, server_default="106200000")
    # TRẦN TẠM ỨNG (chủ 2026-07-23): tổng tạm ứng trong MỘT tháng của 1 NV không vượt tỷ lệ này ×
    # (lương vị trí + trách nhiệm). Ứng nhiều lần trong tháng được, nhưng cộng dồn phải nằm trong trần.
    # Đơn ĐANG CHỜ DUYỆT cũng chiếm chỗ. 0 = KHÔNG giới hạn (đường thoát để duyệt nốt đơn tồn).
    advance_max_pct: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False, default=0.10, server_default="0.1")
    # HẠN MỨC CHỈNH CÔNG (chủ 2026-07-27): mỗi NV tự gửi "Yêu cầu chỉnh công" cho tối đa ngần này
    # NGÀY CÔNG trong một tháng. Đếm theo NGÀY chứ không theo số đơn — quên cả giờ vào lẫn giờ ra
    # của một ngày phải gửi 2 đơn, tính 2 lượt là chặt gấp đôi con số chủ nói. Đơn đang chờ duyệt
    # cũng giữ chỗ; bị từ chối/hủy thì trả lại lượt. HCNS chấm bù TRỰC TIẾP không bị giới hạn này
    # (máy chấm hỏng cả ngày thì phải sửa được cho cả tổ). 0 = KHÔNG giới hạn.
    adjust_max_per_month: Mapped[int] = mapped_column(Integer, nullable=False, default=5, server_default="5")
    # KHẤU TRỪ 10% TẠI NGUỒN cho HĐ dưới 3 tháng / thời vụ (chủ 2026-07-27). Hai số này đổi theo
    # luật nên PHẢI khai được, đừng viết cứng trong code.
    pit_flat_rate: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False, default=0.10, server_default="0.1")
    # Ngưỡng thu nhập/lần trả mới phải khấu trừ (hiện 2.000.000đ).
    pit_flat_threshold: Mapped[float] = mapped_column(_MONEY, nullable=False, default=2_000_000, server_default="2000000")
    # TRẦN KHẤU TRỪ KỶ LUẬT (chủ 29/07/2026 — "bỏ cái 30% đang fix cứng trong code").
    #
    # ⚠️ ĐÂY LÀ MỨC LUẬT, không phải chính sách công ty: Điều 102 BLLĐ 2019 — tiền phạt/bồi thường
    # trừ vào lương hằng tháng KHÔNG ĐƯỢC QUÁ 30% tiền lương thực trả sau khi trích BHXH/BHYT/BHTN
    # và thuế TNCN. Trước đây viết cứng `0.30` trong `_capped_penalty`; nay khai được để đổi khi
    # luật đổi, và để chủ tự quyết nếu chấp nhận rủi ro.
    #
    # `0` = TẮT TRẦN: ghi phạt bao nhiêu trừ bấy nhiêu (thực nhận vẫn có sàn 0, không âm).
    # Màn Cấu hình lương cảnh báo khi đặt 0 hoặc > 30%. Thêm qua migration 0126.
    phat_cap_pct: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False, default=0.30, server_default="0.3")
    # Phụ cấp cơm/ca ĐÃ CHUYỂN sang khai theo TỪNG CA (`work_shifts.meal_allowance` ·
    # `.shift_allowance`) — chủ đổi ý 2026-07-21: gắn vào ca thì NV được gán ca đó tự cộng.
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


class DepartmentSalaryComponent(Base):
    """Bật/tắt + giá trị TỪNG THÀNH PHẦN lương của một bộ phận (Cấu hình lương, Tab 2).

    Cấp GIỮA trong chuỗi ghi đè 3 cấp `NV → bộ phận → công ty`: không có dòng = "chưa khai"
    (rơi xuống cấp công ty); `is_enabled=false` = TẮT hẳn khoản đó cho cả bộ phận (cấp NV
    cũng không được cộng). `value` NULL = bật nhưng dùng mức mặc định của công ty."""

    __tablename__ = "department_salary_components"
    __table_args__ = (
        UniqueConstraint("department_id", "component_key", name="uq_dept_salary_component"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    department_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("departments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Một trong SALARY_COMPONENT_KEYS.
    component_key: Mapped[str] = mapped_column(String(32), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    # Đơn vị theo key: kpi/trách nhiệm/chuyên cần = đồng; ca đêm = % ; khoán/tăng ca/lương bậc = NULL.
    value: Mapped[float | None] = mapped_column(_MONEY, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


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
    # LEGACY/DORMANT: trỏ 1 dòng bảng lương của tổ. Bảng bậc đã GỠ (chủ 2026-07-20: bậc chỉ
    # để phân nhóm, về `employees.job_grade` free-text) — cột giữ dormant, engine không đọc.
    source_salary_row_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # MỨC LƯƠNG của NV — gõ riêng từng ô. Chủ 2026-07-20: **lương vị trí CHÍNH LÀ lương cơ bản,
    # dựa vào đó đóng bảo hiểm** (xem `_compute`). `monthly` nền = vị trí + trách nhiệm.
    luong_vi_tri: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    luong_trach_nhiem: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    # "Lương trả 1 lần" (chủ 2026-07-24): số CỐ ĐỊNH điền sẵn khi tạo phiếu "Thanh toán lương đợt 1".
    # Bản thân cột chỉ là mức mặc định; tiền thực trả ghi ở phiếu (salary_advances kind=luong_dot_1).
    luong_dot_1: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    # DORMANT: mức đóng BH khai riêng — engine THÔI đọc (mức đóng = `luong_vi_tri`). Giữ cột
    # cho tương thích dữ liệu cũ, không migration phá hủy.
    insurance_base: Mapped[float | None] = mapped_column(_MONEY, nullable=True)
    # --- 4 khoản PHỤ CẤP KHAI TAY theo TỪNG NGƯỜI (chủ chốt 2026-07-20) ------------------
    # Một SỐ CỐ ĐỊNH dùng cho mọi tháng; hệ thống KHÔNG tính toán gì (không đơn giá × số lượt,
    # không suy theo thâm niên) — sửa khi nào cần thì sửa. Cả 4 cộng PHẲNG vào thu nhập:
    # KHÔNG prorate theo công, KHÔNG vào gốc tính tăng ca.
    # `allowance` = "Phụ cấp KHÁC" (gộp: xăng/điện thoại/kiêm nhiệm… — giữ dữ liệu cũ).
    allowance: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    # Phụ cấp CA (ca đêm/ca tới sáng/cơm ca…) — gộp 1 số; dòng lương lưu ở `payroll_lines.night_pay`.
    phu_cap_ca: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    # `phu_cap_trach_nhiem` (khai tay) ĐÃ BỎ — trùng ý với `luong_trach_nhiem` (thành phần mức
    # nền). Trách nhiệm giờ CHỈ ở `luong_trach_nhiem`. Thâm niên vẫn khai tay ở đây.
    phu_cap_tham_nien: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    # Chuyên cần của RIÊNG người này (mỗi người mỗi khác). TRỪ DẦN theo số ngày nghỉ (C3):
    # tỷ lệ = max(0, 1 − 0,5 × số ngày nghỉ).
    chuyen_can: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    # Cờ "BH đóng ở nơi khác": NV đã được nơi khác (công ty B) đóng BHXH/BHYT/BHTN → công ty mình KHÔNG
    # trừ 3 khoản này của NV, chỉ chịu TNLĐ-BNN (`payroll_params.tnld_bnn_rate`, phía chủ SDLĐ, không trừ
    # vào lương). Đoàn phí công đoàn VẪN trừ như thường. Xem nhánh trong `_compute`.
    insurance_elsewhere: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    # Cờ "đoàn viên công đoàn": CHỈ đoàn viên mới bị trừ đoàn phí công đoàn (`params.cong_doan_rate`).
    # Mặc định false (opt-in — chủ 2026-07-21): không ai đóng cho tới khi tích từng người. Xem `_compute`.
    union_member: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    # Có áp GIẢM TRỪ BẢN THÂN khi tính TNCN không (chủ 2026-07-27). Người làm 2 nơi chỉ được đăng ký
    # giảm trừ bản thân ở MỘT nơi — bỏ tích ở nơi còn lại. Mặc định BẬT (đại đa số chỉ làm một nơi;
    # tắt là ngoại lệ). Giảm trừ NGƯỜI PHỤ THUỘC không đụng cờ này (theo `employees.dependents_count`).
    apply_self_deduction: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=sa_true()
    )
    # % HOA HỒNG của nhân viên kinh doanh (chủ 2026-07-29). PHÂN SỐ: 0.05 = 5%, đúng quy ước
    # `cong_doan_rate` / `phat_cap_pct`. Để ở ĐÂY chứ không ở `employees` là có chủ đích: bảng này
    # versioned sẵn theo `effective_from` ⇒ đổi % từ tháng sau thì kỳ tháng trước tính lại vẫn ra
    # số cũ. 0 = không hưởng hoa hồng (mặc định của mọi người).
    # ⚠️ ĐỢT NÀY CHỈ KHAI: `_compute` KHÔNG đọc cột này, khai bao nhiêu cũng không đổi một đồng.
    # Ra tiền cần `orders.commission_pct` + Σ phiếu thu theo đơn (redesign-luong-kinh-doanh §4.6).
    commission_pct: Mapped[float] = mapped_column(
        Numeric(6, 4), nullable=False, default=0, server_default="0"
    )
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
    # Loại phiếu: `tam_ung` (ad-hoc) | `luong_dot_1` (thanh toán lương đợt 1, số cố định theo hồ sơ).
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default=ADV_KIND_TAM_UNG, server_default=ADV_KIND_TAM_UNG)
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
    # TRONG ĐÓ của `luong_cong` — tiền của những NGÀY NGHỈ PHÉP, trả theo LƯƠNG VỊ TRÍ (không
    # lương trách nhiệm). Để phiếu lương giải thích được vì sao tháng có phép thì lương công thấp
    # hơn. ĐỪNG cộng thêm vào gross: đã nằm trong `luong_cong`. Khác hẳn cột tay `phep_nam`.
    luong_ngay_phep: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    paid_leave_cong: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0, server_default="0")
    # Công thiếu ĐƯỢC PHÉP (đơn nghỉ theo giờ đã duyệt) — chỉ để giải trình vì sao công thiếu mà
    # chuyên cần vẫn đủ. Không tham gia công thức nào ở dòng lương.
    excused_cong: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0, server_default="0")
    chuyen_can: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    # THU NHẬP MIỄN THUẾ của kỳ (chủ 2026-07-27) = tăng ca + ca đêm + các khoản danh mục có
    # `is_taxable = false`. Số DẪN XUẤT, KHÔNG cộng vào gross lần nữa.
    # ⚠️ `pit_taxable` KHÔNG phải số này: nó là thu nhập TÍNH thuế (đã trừ BHXH + giảm trừ gia
    # cảnh 15,5tr). Thu nhập CHỊU thuế = tổng lương − các khoản miễn, TRƯỚC mọi giảm trừ. Hai số
    # cách nhau ~15,5tr nên KHÔNG được dùng lẫn.
    thu_nhap_chiu_thue: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    thu_nhap_mien_thue: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    # TỔNG phụ cấp tháng = phụ cấp khác + thâm niên (cột dưới). Trách nhiệm KHÔNG ở đây — nó là
    # `luong_trach_nhiem`, đã nằm trong mức nền (luong_cong).
    allowance: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    # TRONG ĐÓ của `allowance` — chép từ `employee_salaries.phu_cap_tham_nien` để phiếu lương
    # hiện DÒNG RIÊNG (bệnh B2 "phụ cấp một cục"). ĐỪNG cộng thêm vào gross: đã nằm trong `allowance`.
    phu_cap_tham_nien: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    khoan: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")          # lương khoán (nhịp 2)
    ot_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")      # tổng phút tăng ca (Pha 4a)
    ot_pay: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")          # tiền tăng ca (Pha 4a)
    night_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")      # số ngày ca đêm (từ Chấm công)
    # PHỤ CẤP CA của kỳ = số KHAI TAY ở `employee_salaries.phu_cap_ca` (cộng phẳng, không
    # prorate). Giữ TÊN CỘT cũ vì đã nối sẵn gross/miễn TNCN/export/phiếu lương — không đẻ cột
    # thứ hai cùng nghĩa (API phơi thêm alias `ca_pay`).
    night_pay: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    # Premium CA ĐÊM theo GIỜ (giờ đêm × hệ số + tăng ca đêm) — tự tính từ chấm công, DÒNG RIÊNG, miễn TNCN.
    night_premium_pay: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    vi_pham: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")        # tay — giảm trừ khác (RAW; gộp trần 30% Đ102)
    other_bonus: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")    # tay (thưởng khác/hoa hồng)
    # --- Thưởng năng suất KPI: % đạt nhập TAY theo tháng × mức trần của bộ phận (component `kpi`).
    # kpi_bonus CHỊU thuế TNCN (khác tăng ca/ca đêm được miễn).
    kpi_percent: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0, server_default="0")
    kpi_bonus: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    # --- Khoản chi tiết phiếu lương (Pha 4d) — HCNS nhập tay/tháng. Thưởng = thu nhập chịu thuế. ---
    thuong_5s: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    thuong_doanh_so: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    thuong_thanh_tich: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    phep_nam: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    tra_dong_phuc: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    dieu_chinh_luong: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")  # ± cộng đại số
    di_tre: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")           # đi trễ/về sớm/nghỉ KP (phạt)
    # HCNS sửa tay ô "Đi trễ" → khóa không cho phạt TỰ ĐỘNG (từ chấm công) ghi đè. Mirror `pit_manual`.
    di_tre_manual: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
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
    advance_total: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")  # tạm ứng ĐÃ DUYỆT (kind=tam_ung)
    # Thanh toán lương đợt 1 ĐÃ DUYỆT (kind=luong_dot_1) của kỳ — snapshot, dòng riêng trên phiếu lương.
    luong_dot_1_total: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
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


class LatePenaltyBracket(Base):
    """Bậc PHẠT đi trễ / về sớm KHÔNG phép (toàn công ty) — dữ liệu SỬA ĐƯỢC, mirror PitTaxBracket.
    Tra theo SỐ PHÚT trễ/sớm (quá dung sai ca): bậc đầu tiên có `phút ≤ up_to_minute` → `amount`
    (tiền phạt/lần); `up_to_minute` NULL = bậc cao nhất (∞). Seed-once 4 bậc mặc định (PRD §4/D11).
    Bảng do create_all tạo (không migration), seed-once. ENGINE CHƯA áp bảng này để TỰ tính phạt
    (auto từ chấm công là Đợt 2) — hiện chỉ lưu + phơi + sửa + tra TAY ở helper "Tính nhanh phạt"."""

    __tablename__ = "late_penalty_brackets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)                 # thứ tự bậc (1..N)
    up_to_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)  # trần PHÚT của bậc; NULL = ∞
    amount: Mapped[float] = mapped_column(_MONEY, nullable=False)             # tiền phạt/lần (đồng)


# --- Danh mục KHOẢN THU NHẬP (chủ 2026-07-27) --------------------------------
# Thay cho ô "Phụ cấp KHÁC" gộp một cục: mỗi khoản là một dòng danh mục, HCNS tự thêm/xoá/bật tắt,
# và mỗi khoản mang cờ `is_taxable` — nguồn DUY NHẤT trả lời "khoản này có tính thuế TNCN không".
COMPONENT_KIND_THU = "thu"    # cộng vào tổng lương
COMPONENT_KIND_TRU = "tru"    # khấu trừ khỏi thực nhận
COMPONENT_KINDS = (COMPONENT_KIND_THU, COMPONENT_KIND_TRU)

# Nguồn của một dòng khoản trên BẢNG LƯƠNG (Tầng 3).
COMPONENT_SOURCE_EMPLOYEE = "employee"   # chép từ hồ sơ NV — ghi đè mỗi lần tính lại
COMPONENT_SOURCE_LINE = "line"           # thêm tay cho riêng kỳ này — giữ nguyên khi tính lại
COMPONENT_SOURCES = (COMPONENT_SOURCE_EMPLOYEE, COMPONENT_SOURCE_LINE)


class PayrollComponent(Base):
    """Một khoản thu nhập / khấu trừ trong danh mục lương.

    Trước đây mọi phụ cấp bị gộp vào `employee_salaries.allowance` nên engine thuế chỉ miễn được
    tăng ca + ca đêm (hai khoản duy nhất còn tách ra được), mọi phụ cấp khác bị tính thuế oan.
    Tách thành danh mục để `is_taxable` khai được tới từng khoản.

    XOÁ: khoản đã dùng ở kỳ lương nào rồi thì KHÔNG xoá cứng, chỉ `is_active = False`. Xoá cứng là
    phiếu lương kỳ cũ mất dòng, tổng không còn khớp chữ ký người nhận (xem `PayrollComponentService`).
    """

    __tablename__ = "payroll_components"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(
        String(8), nullable=False, default=COMPONENT_KIND_THU, server_default=COMPONENT_KIND_THU
    )
    # ⭐ Ô TÍCH "Chịu thuế" của chủ: True = cộng vào thu nhập chịu thuế TNCN; False = miễn.
    is_taxable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=sa_true()
    )
    # Có cộng vào GỐC ĐÓNG BẢO HIỂM không. Mặc định KHÔNG — gốc đóng BH là `luong_vi_tri`
    # (chủ chốt 2026-07-20), phụ cấp không đụng vào.
    in_insurance_base: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa_false()
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=sa_true()
    )
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class EmployeeSalaryComponent(Base):
    """Khoản thu nhập/khấu trừ CỐ ĐỊNH HÀNG THÁNG của một người (Tầng 2).

    Cố ý KHÔNG version theo `effective_from` như `employee_salaries`: kỳ lương đã chốt vốn đã đóng
    băng ở `payroll_lines` nên sửa mức hôm nay không đụng được số cũ; thêm một trục version nữa chỉ
    tạo chỗ để lệch."""

    __tablename__ = "employee_salary_components"
    __table_args__ = (
        UniqueConstraint("employee_id", "component_id", name="uq_employee_component"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    component_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("payroll_components.id", ondelete="CASCADE"), index=True, nullable=False
    )
    amount: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    # Ghi chú tự do — cho khoản "mở" như "Thu nhập khác (chịu thuế)" lưu vết vì sao có khoản này
    # (vd "Phụ cấp tiếng Nhật theo dự án X"). Chép sang snapshot dòng lương khi tính.
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class PayrollLineComponent(Base):
    """SNAPSHOT từng khoản trên MỘT dòng lương — phiếu lương hiện được từng khoản, và kỳ đã chốt
    giữ nguyên số cũ.

    Chép cả `code`/`name`/`kind`/`is_taxable` tại thời điểm tính, KHÔNG chỉ trỏ `component_id`:
    sau này chủ đổi tên khoản hay bỏ tích "Chịu thuế" thì phiếu lương các kỳ CŨ vẫn in ra đúng
    y như lúc trả tiền. Đây là lý do đổi cờ chỉ ảnh hưởng kỳ tính từ đó về sau."""

    __tablename__ = "payroll_line_components"
    __table_args__ = (
        UniqueConstraint("line_id", "component_id", name="uq_line_component"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    line_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("payroll_lines.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Soft-ref: khoản có thể bị xoá khỏi danh mục sau này, snapshot vẫn đứng vững nhờ 4 cột chép.
    component_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    is_taxable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_true())
    amount: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    # NGUỒN của dòng này — quyết định số phận khi bấm "Tính lại":
    #   `employee` = chép từ hồ sơ NV ⇒ bị GHI ĐÈ mỗi lần tính lại (đúng, vì hồ sơ là nguồn thật).
    #   `line`     = HCNS thêm tay cho RIÊNG kỳ này (thưởng nóng) ⇒ PHẢI GIỮ NGUYÊN qua mọi lần
    #                tính lại, và KHÔNG lặp sang kỳ sau.
    # Không có cột này thì "Tính lại" xoá sạch thưởng nóng — mất tiền, không báo lỗi.
    source: Mapped[str] = mapped_column(
        String(8), nullable=False, default=COMPONENT_SOURCE_EMPLOYEE,
        server_default=COMPONENT_SOURCE_EMPLOYEE,
    )
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
