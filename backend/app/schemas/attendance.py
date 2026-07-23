"""Pydantic models for the Chấm công GPS API (module `nhan_su`)."""
from __future__ import annotations

from datetime import date, datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_serializer


# --- work locations ---------------------------------------------------------


class WorkLocationIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius_m: int = Field(default=100, gt=0, le=100000)
    note: str | None = Field(default=None, max_length=500)
    is_active: bool = True


class WorkLocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    latitude: float
    longitude: float
    radius_m: int
    is_active: bool
    note: str | None = None
    created_at: datetime | None = None


class WorkLocationsOut(BaseModel):
    items: list[WorkLocationOut]


# --- work shifts / ca kíp ---------------------------------------------------


class WorkShiftIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    start_time: str = Field(
        min_length=1,
        max_length=5,
        description='HH:MM hoặc dạng rút gọn, vd "08:00", "8", "730"',
    )
    end_time: str = Field(min_length=1, max_length=5)
    is_overnight: bool = False
    # Hệ số ca đêm (1.3 = +30%) cho giờ rơi 22h–06h trong ca — chỉ áp ca qua đêm.
    night_multiplier: float = Field(default=1.3, ge=1.0, le=3.0)
    grace_minutes: int = Field(default=5, ge=0, le=240)
    # Phụ cấp khai theo ca (đ): cơm (tăng ca 17h30→24h) · ca (áp ca ngày/đêm).
    meal_allowance: float = Field(default=25000, ge=0)
    shift_allowance: float = Field(default=50000, ge=0)
    note: str | None = Field(default=None, max_length=500)
    is_active: bool = True


class WorkShiftOut(BaseModel):
    id: int
    name: str
    start_time: str          # "HH:MM" (router convert từ start_minute)
    end_time: str
    is_overnight: bool
    night_multiplier: float = 1.3
    grace_minutes: int
    meal_allowance: float = 25000
    shift_allowance: float = 50000
    is_active: bool
    note: str | None = None


class WorkShiftsOut(BaseModel):
    items: list[WorkShiftOut]


# --- attendance logs --------------------------------------------------------


class AttendanceLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    employee_name: str | None = None       # filled by the router (HR table)
    work_location_id: int | None = None
    location_name: str | None = None        # filled by the router
    check_type: str
    checked_at: datetime
    latitude: float | None = None
    longitude: float | None = None
    distance_m: float | None = None
    within_range: bool = True
    note: str | None = None

    @field_serializer("checked_at")
    def _utc_checked_at(self, dt: datetime) -> str:
        """checked_at ghi UTC nhưng SQLite trả naive → serialize KÈM nhãn UTC ('...Z')
        để client (new Date) hiểu đúng múi giờ, khỏi lệch 7h."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class AttendanceLogsOut(BaseModel):
    items: list[AttendanceLogOut]


# --- self check-in ----------------------------------------------------------


class CheckIn(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class NearestLocationOut(BaseModel):
    id: int
    name: str
    radius_m: int


class CheckResultOut(BaseModel):
    success: bool
    within_range: bool
    check_type: str | None = None
    distance_m: float | None = None
    nearest_location: NearestLocationOut | None = None
    message: str
    log: AttendanceLogOut | None = None


class PreviewOut(BaseModel):
    """Dry-run geofence cho card chấm 'sống' (không ghi log)."""
    locations_configured: bool = False
    within_range: bool = False
    distance_m: float | None = None
    meters_out: float | None = None       # còn cách bao nhiêu mét mới vào vùng (0 nếu đã trong)
    nearest_name: str | None = None
    radius_m: int | None = None
    next_action: str | None = None        # "in" | "out" — nhãn nút kế tiếp
    message: str


class MyShiftOut(BaseModel):
    id: int
    name: str
    start_time: str          # "HH:MM"
    end_time: str
    is_overnight: bool = False


class TodaySummaryOut(BaseModel):
    first_in: str | None = None    # "HH:MM"
    last_out: str | None = None
    cong: float | None = None      # công dự kiến hôm nay theo ca
    reason: str | None = None      # lý do khi công chưa đủ (thiếu chấm RA / vào trễ / về sớm…)
    late: bool = False
    early: bool = False
    ot_minutes: int = 0


class MyStatusOut(BaseModel):
    has_employee: bool
    employee_name: str | None = None
    next_action: str | None = None          # "in" | "out"
    can_check: bool = False
    check_block_reason: str | None = None
    last_check: AttendanceLogOut | None = None
    locations_configured: bool = False
    shift: MyShiftOut | None = None          # ca mặc định của NV (nếu đã gán)
    today: TodaySummaryOut | None = None     # tóm tắt "Hôm nay của tôi"


# --- bảng công tháng --------------------------------------------------------


class TimesheetDay(BaseModel):
    shift_id: int | None = None
    shift_name: str | None = None
    first_in: str | None = None    # "HH:MM"
    last_out: str | None = None
    hours: float | None = None
    present: bool = True
    # Đối chiếu ca kíp (null/False khi NV chưa gán ca).
    cong: float | None = None      # công theo ca (0..1, 2 chữ số)
    late: bool = False             # đi muộn
    early: bool = False            # về sớm
    ot_minutes: int = 0            # tăng ca (phút vượt giờ ca)
    night: bool = False            # ca đêm
    leave: str | None = None       # tên loại nghỉ (nếu ngày này nghỉ đã duyệt) HOẶC tên ngày lễ
    leave_paid: bool = False       # nghỉ có lương (P) hay không (KL)
    holiday: bool = False          # ngày nghỉ lễ hưởng lương (cộng 1 công tự động, không cần chấm)


class TimesheetRow(BaseModel):
    employee_id: int
    employee_code: str
    employee_name: str
    department_id: int | None = None
    department_name: str | None = None
    shift_id: int | None = None
    shift_name: str | None = None
    days: dict[str, TimesheetDay]  # keyed by day-of-month ("1".."31")
    total_days: int
    total_leave: int = 0             # số ngày nghỉ đã duyệt trong tháng
    total_hours: float
    total_cong: float | None = None  # tổng công (theo ca + nghỉ có lương)


class HolidayMark(BaseModel):
    day: int           # ngày trong tháng (1..31)
    date: date
    name: str


class TimesheetOut(BaseModel):
    year: int
    month: int
    days_in_month: int
    # Công chuẩn động của tháng (số ngày làm việc theo lịch) — hiển thị; Lương Pha 1 vẫn dùng 26.
    standard_cong: int | None = None
    holidays: list[HolidayMark] = []   # ngày nghỉ lễ hưởng lương trong tháng (tô màu)
    rows: list[TimesheetRow]


# --- Chốt công tháng (kỳ công) ----------------------------------------------


class PeriodActionIn(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)


class AttendancePeriodOut(BaseModel):
    year: int
    month: int
    status: str                       # draft | locked
    locked_at: datetime | None = None
    locked_by: int | None = None
    line_count: int                   # số dòng snapshot đã đóng băng
    employee_count: int               # số NV trong bảng công tháng
    hanging_days: int                 # số ngày treo (thiếu chấm RA) — xử trước khi Chốt
    pending_leaves: int               # đơn nghỉ phép chưa duyệt của tháng
    pending_adjusts: int              # yêu cầu chỉnh công chưa duyệt
    payroll_locked: bool              # kỳ lương tháng này đã chốt → không mở lại kỳ công


# --- "ô biết nói": chi tiết 1 ngày + điều chỉnh punch ----------------------


class DayPunchOut(BaseModel):
    id: int
    time: str                 # "HH:MM" (giờ VN)
    check_type: str           # in | out
    is_manual: bool = False   # punch điều chỉnh tay
    adjust_reason: str | None = None
    fault_party: str | None = None
    distance_m: float | None = None


class DayDetailOut(BaseModel):
    employee_id: int
    employee_name: str
    date: str
    shift_name: str | None = None
    cong: float | None = None
    reason: str | None = None
    punches: list[DayPunchOut]


class AdjustIn(BaseModel):
    employee_id: int
    date: str                                   # "YYYY-MM-DD"
    check_type: str                             # in | out
    time: str = Field(min_length=3, max_length=5)  # "HH:MM"
    reason: str = Field(min_length=1, max_length=500)
    fault_party: str | None = None              # nv_quen | may_hong | duyet | khac


# --- KPI giám sát hôm nay ---------------------------------------------------


class TodayKpiOut(BaseModel):
    present_now: int = 0        # đang trong ca (chấm VÀO chưa RA hôm nay)
    missing_out: int = 0        # quên chấm RA (VÀO từ ngày trước, chưa RA)
    late_today: int = 0         # đi muộn hôm nay
    pending_requests: int = 0   # yêu cầu chỉnh công chờ duyệt


# --- yêu cầu chỉnh công (NV gửi → HCNS duyệt) ------------------------------


class AdjustRequestOut(BaseModel):
    id: int
    employee_id: int
    employee_name: str | None = None
    work_date: str
    check_type: str
    suggested_time: str | None = None
    reason: str
    fault_party: str | None = None
    status: str
    decided_at: datetime | None = None
    decision_note: str | None = None
    decided_by_name: str | None = None


class AdjustRequestsOut(BaseModel):
    items: list[AdjustRequestOut]


class RequestAdjustIn(BaseModel):
    date: str                                   # "YYYY-MM-DD"
    check_type: str                             # in | out (punch NV đề nghị bù)
    suggested_time: str | None = Field(default=None, max_length=5)  # "HH:MM"
    reason: str = Field(min_length=1, max_length=500)


class ApproveRequestIn(BaseModel):
    time: str | None = Field(default=None, max_length=5)  # ghi đè giờ (mặc định = suggested_time)
    fault_party: str | None = None
    note: str | None = Field(default=None, max_length=500)


class RejectRequestIn(BaseModel):
    note: str = Field(min_length=1, max_length=500)
