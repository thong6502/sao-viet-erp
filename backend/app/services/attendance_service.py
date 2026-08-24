"""Attendance / chấm công GPS business logic (module `nhan_su`, lát Chấm công).

Geofence rule (chốt với SVN): HR khai nhiều điểm chấm công (toạ độ + bán kính). Nhân viên
gửi toạ độ trình duyệt; server tính khoảng cách Haversine tới điểm active gần nhất và CHẶN
CỨNG nếu ngoài bán kính (không ghi log). Trong phạm vi ⇒ ghi 1 dòng, VÀO/RA tự luân phiên
theo lần chấm gần nhất. Người chấm = user đăng nhập → hồ sơ NV qua `employees.user_id`.

Cảnh báo: toạ độ trình duyệt có thể bị giả (GPS spoofing) — server-side check là cổng chính
nhưng chưa chống spoofing sâu ở lát này.
"""
from __future__ import annotations

import calendar
import json
import math
from datetime import date, datetime, time as dtime, timedelta, timezone

from ..models.attendance import (
    APERIOD_DRAFT,
    APERIOD_LOCKED,
    CHECK_IN,
    CHECK_OUT,
    CHECK_TYPES,
    FAULT_PARTIES,
    REQ_APPROVED,
    REQ_CANCELLED,
    REQ_PENDING,
    REQ_REJECTED,
    WorkLocation,
    WorkShift,
)
from ..models.employee import (
    SHIFT_LOG_ACTION_INHERIT,
    SHIFT_LOG_ACTION_OFF,
    SHIFT_LOG_ACTION_SET,
    SHIFT_LOG_KIND_DAY,
    SHIFT_LOG_ORIGIN_GRID,
)
from ..models.leave import STATUS_PENDING as LEAVE_PENDING
from ..models.payroll import PERIOD_LOCKED, PERIOD_PAID

# Kỳ lương đã KHOÁ SỐ — không được mở lại kỳ công đằng sau nó nữa.
#
# Phải có CẢ `paid`, không chỉ `locked`. `paid` là trạng thái ĐI SAU `locked` (chốt → đã chi), nên
# chỉ chặn `locked` là quên đúng lúc nguy hiểm nhất: tiền đã phát cho công nhân rồi mà bảng công
# đằng sau vẫn sửa được ⇒ mất hẳn dấu vết "lương tháng này trả theo công nào".
PAYROLL_DA_KHOA = (PERIOD_LOCKED, PERIOD_PAID)
from ..models.role import SCOPE_ALL
from ..repositories.attendance_repo import AttendanceRepository
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.employee_repo import EmployeeRepository
from ..shift_notify import push_shift_changes as _push_shift_changes

# Giờ Việt Nam (UTC+7, không DST) — dùng để gom "ngày công" theo lịch địa phương.
VN_TZ = timezone(timedelta(hours=7))
CHECK_IN_EARLY_MINUTES = 60
# Sau giờ tan ca còn bao lâu thì lượt bấm vẫn được coi là "RA của ca đang mở" (ôm trọn tăng ca vượt
# nửa đêm mà vẫn cách rất xa giờ vào ca kế tiếp — ca 8h thì khoảng cách tới ca sau là 16h). Quá mốc
# này ⇒ coi là VÀO ca mới, đêm cũ để treo (chống "kéo trạng thái xuyên ngày" khi quên chấm RA).
CHECK_OUT_GRACE_HOURS = 8


def _chuan_ot_days(v) -> dict[str, dict[int, int]]:
    """{"lam"/"nghi": {ngày → phút}} với KHOÁ NGÀY LÀ SỐ.

    JSON chỉ có khoá chuỗi, nên đọc lại từ ảnh chụp ra `{"7": 240}` còn nhánh live ra `{7: 240}`.
    Hai nhánh trả hai kiểu khoá là engine đếm đúng ở kỳ chưa chốt và sai ở kỳ đã chốt — đúng loại
    lệch âm thầm mà cả file này đã dính nhiều lần."""
    v = v or {}
    return {k: {int(d): int(m) for d, m in (v.get(k) or {}).items()} for k in ("lam", "nghi")}


def _as_utc(dt: datetime) -> datetime:
    """checked_at được ghi UTC (aware) nhưng SQLite trả về NAIVE khi đọc lại. Dán lại
    nhãn UTC để `.astimezone(VN_TZ)` đúng trên MỌI múi giờ máy chủ (không phụ thuộc TZ hệ)."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt

_EARTH_RADIUS_M = 6_371_000.0  # mean Earth radius, metres


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two WGS-84 points, in metres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


def min_to_hhmm(m: int) -> str:
    return f"{int(m) // 60:02d}:{int(m) % 60:02d}"


def check_in_block_reason(*, shift, work_day: date, now_local: datetime) -> str | None:
    """Lý do không được chấm VÀO; None nghĩa là đang trong cửa sổ hợp lệ."""
    midnight = datetime(work_day.year, work_day.month, work_day.day, tzinfo=VN_TZ)
    start_at = midnight + timedelta(minutes=shift.start_minute)
    end_at = midnight + timedelta(
        minutes=shift.end_minute + (1440 if shift.is_overnight else 0)
    )
    earliest = start_at - timedelta(minutes=CHECK_IN_EARLY_MINUTES)
    if now_local < earliest:
        return (
            f"Ca {shift.name} bắt đầu lúc {min_to_hhmm(shift.start_minute)}. "
            f"Bạn chỉ được chấm vào từ {earliest.strftime('%H:%M')}."
        )
    if now_local >= end_at:
        return (
            f"Ca {shift.name} đã kết thúc lúc {min_to_hhmm(shift.end_minute)}. "
            "Không thể chấm vào cho ca này."
        )
    return None


def _hhmm_to_min(s: str) -> int:
    raw = str(s).strip()
    try:
        if ":" in raw:
            parts = raw.split(":")
            if len(parts) != 2 or not all(part.isdigit() for part in parts):
                raise ValueError
            h, m = int(parts[0]), int(parts[1])
        elif raw.isdigit() and 1 <= len(raw) <= 4:
            if len(raw) <= 2:
                h, m = int(raw), 0
            elif len(raw) == 3:
                h, m = int(raw[0]), int(raw[1:])
            else:
                h, m = int(raw[:2]), int(raw[2:])
        else:
            raise ValueError
    except (ValueError, AttributeError):
        raise AttendanceValidationError(
            "Giờ phải là HH:MM hoặc dạng số như 7, 730, 1200."
        )
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise AttendanceValidationError("Giờ không hợp lệ (00:00–23:59).")
    return h * 60 + m


def compute_day_cong(
    *, start_min: int, end_min: int, is_overnight: bool, grace_min: int,
    first_in_min: int, main_out_min: int | None,
    in_day_offset: int | None = None, main_out_offset: int | None = None,
    ot_in_min: int | None = None, ot_out_min: int | None = None,
    ot_in_offset: int | None = None, ot_out_offset: int | None = None,
    ot_window: tuple[int, int] | None = None,
) -> dict:
    """Tính CÔNG + TĂNG CA một ngày theo ca (chốt với SVN, cập nhật 25/07/2026 — tăng ca là PHIÊN
    CHẤM RIÊNG):
      công = (số phút làm trong khung ca) ÷ (số phút chuẩn của ca), giữ 2 chữ số, tối đa 1,00.
      • Vào trễ ≤ dung sai (grace) vẫn coi đúng giờ (không trừ).
      • Đủ giờ (đúng giờ + ra ≥ giờ ca) ⇒ 1,00. Đi muộn/về sớm ⇒ giảm theo tỷ lệ (0,94…).
      • Thiếu chấm RA ca chính ⇒ 0 công (đánh dấu incomplete).
    CÔNG tính theo PHIÊN CA CHÍNH `(first_in, main_out)` — `main_out` = lượt RA của phiên ĐẦU (ca
    chính), KHÔNG phải lượt ra cuối ngày. Về sớm ⇒ công giảm theo giờ ra thực tế của ca chính.
    TĂNG CA tính theo PHIÊN RIÊNG `(ot_in, ot_out)` (lượt VÀO-RA sau khi đã chấm ra ca chính):
    `ot_minutes` = phần phiên TC NẰM TRONG cửa sổ phiếu `ot_window` (về sớm hơn phiếu ⇒ trả theo thực;
    quá phiếu ⇒ kẹp trần). KHÔNG có phiên TC (thiếu cặp chấm) ⇒ `ot_minutes = 0` (bắt buộc 2 cặp).
    Khe giữa `main_out` và `ot_in` (nghỉ giữa ca) KHÔNG tính vào đâu cả.
    `*_min` = phút-từ-nửa-đêm (giờ VN); `*_offset` = số ngày lệch giữa lượt chấm và NGÀY CÔNG (caller
    biết chính xác từ datetime) → ánh xạ +1440×offset lên trục tuyến tính, cho tăng ca vượt nửa đêm
    tính đúng. Bỏ trống offset ⇒ suy đoán theo đồng hồ (ca đêm + mốc rạng sáng → +1440).
    `ot_window` = khoảng phiếu TC đã duyệt (cùng trục phút); `(0,0)` = không phiếu ⇒ TC = 0."""
    end_ref = (end_min + 1440) if is_overnight else end_min
    window = end_ref - start_min
    if window <= 0:
        return {"cong": 0.0, "late": False, "early": False, "late_minutes": 0,
                "early_minutes": 0, "ot_minutes": 0, "ot_minutes_raw": 0, "night_minutes": 0,
                "ot_night_minutes": 0, "incomplete": True,
                "window_minutes": 0, "missing_minutes": 0}

    def _lin(m: int, offset: int | None = None) -> int:
        # Có offset (caller biết ngày thật của lượt chấm) → cộng thẳng. Không có thì suy đoán cũ:
        # ca đêm + mốc rơi rạng sáng (≤ giờ RA) thuộc phần sau nửa đêm của ca → +1440.
        if offset is not None:
            return m + 1440 * offset
        return m + 1440 if (is_overnight and m <= end_min) else m

    fin = _lin(first_in_min, in_day_offset)
    late = fin > start_min + grace_min
    # SỐ PHÚT đi trễ (quá dung sai) — nền cho phạt tự động (Đợt 2). > 0 đúng khi `late`.
    late_minutes = max(0, fin - (start_min + grace_min))
    effective_in = start_min if fin <= start_min + grace_min else fin

    # --- TĂNG CA: phiên chấm riêng ∩ cửa sổ phiếu (độc lập với việc có chấm ra ca chính hay chưa) ---
    if ot_in_min is None or ot_out_min is None:
        ot_from = ot_to = 0
        ot_minutes = ot_minutes_raw = 0
    else:
        ot_in_lin = _lin(ot_in_min, ot_in_offset)
        ot_out_lin = _lin(ot_out_min, ot_out_offset)
        ot_minutes_raw = max(0, ot_out_lin - ot_in_lin)   # độ dài phiên TC thô (đối chiếu duyệt vs thực)
        if ot_window is None:
            ot_from, ot_to = ot_in_lin, ot_out_lin
        else:
            ot_from = max(ot_in_lin, int(ot_window[0]))
            ot_to = min(ot_out_lin, int(ot_window[1]))
        ot_minutes = max(0, ot_to - ot_from)

    if main_out_min is None:
        return {"cong": 0.0, "late": late, "early": False, "late_minutes": late_minutes,
                "early_minutes": 0, "ot_minutes": ot_minutes, "ot_minutes_raw": ot_minutes_raw,
                "night_minutes": 0, "ot_night_minutes": 0, "incomplete": True,
                "window_minutes": window, "missing_minutes": window}

    mout = _lin(main_out_min, main_out_offset)
    early = mout < end_ref
    early_minutes = max(0, end_ref - mout)     # SỐ PHÚT về sớm ca chính; > 0 đúng khi `early`.
    worked = min(mout, end_ref) - max(effective_in, start_min)
    worked = max(0, min(worked, window))
    cong = min(1.0, round(worked / window, 2))
    # SỐ PHÚT rơi cửa sổ ĐÊM 22:00–06:00 (nền tính lương ca đêm theo giờ). `night_minutes` = giờ đêm
    # TRONG ca (kẹp trần end_ref → loại phần OT); `ot_night_minutes` = giờ TĂNG CA (sau end_ref) rơi đêm.
    def _ov(a, b, c, d):  # độ dài giao [a,b] ∩ [c,d]
        return max(0, min(b, d) - max(a, c))

    def _night_ov(a: int, b: int) -> int:
        """Phút của [a,b] rơi cửa sổ ĐÊM 22:00–06:00, LẶP theo từng ngày trên trục tuyến tính
        ([1320,1800] + k×1440). MỘT công thức cho mọi ca — kể cả tăng ca vượt nửa đêm (nhánh
        'trong ngày' cũ tính hụt phần 00:00–06:00 của hôm sau)."""
        return sum(_ov(a, b, 1320 + 1440 * k, 1800 + 1440 * k) for k in (-1, 0, 1))

    w_start = max(effective_in, start_min)
    in_end = min(mout, end_ref)
    night_minutes = _night_ov(w_start, in_end)
    ot_night_minutes = _night_ov(ot_from, ot_to) if ot_minutes > 0 else 0
    return {"cong": cong, "late": late, "early": early, "late_minutes": late_minutes,
            "early_minutes": early_minutes, "ot_minutes": ot_minutes,
            "ot_minutes_raw": ot_minutes_raw,
            "night_minutes": night_minutes, "ot_night_minutes": ot_night_minutes, "incomplete": False,
            # Nền cho "nghỉ có phép": phải so trên PHÚT (trước khi round(cong,2)) và phải là
            # phút THIẾU THẬT so với khung ca — `late_minutes` đã trừ dung sai nên nhỏ hơn.
            "window_minutes": window, "missing_minutes": max(0, window - worked)}


def work_day_of(local: datetime, shift) -> date:
    """NGÀY CÔNG của một lượt chấm (giờ VN): bình thường = ngày lịch; ca đêm + lượt rơi rạng sáng
    (≤ giờ RA của ca) → thuộc ngày VÀO ca liền trước (lùi 1 ngày). Nguồn sự thật DUY NHẤT cho
    quy tắc gom ca (trước lặp 3 nơi: bảng công / hôm nay / punch 1 ngày / luân phiên VÀO-RA)."""
    if shift is not None and shift.is_overnight and (local.hour * 60 + local.minute) <= shift.end_minute:
        return (local - timedelta(days=1)).date()
    return local.date()


def pair_sessions(entries: list) -> list:
    """Ghép các lượt bấm của MỘT ngày công thành các PHIÊN (in, out).
    `entries` = list[(datetime, check_type)] ĐÃ SORT theo thời gian. Gặp VÀO thì mở phiên, gặp RA
    thì đóng. Lượt lẻ (RA khi chưa VÀO, hoặc VÀO cuối chưa RA) bị bỏ khỏi danh sách phiên.
    Phiên 0 = CA CHÍNH; phiên 1.. = TĂNG CA (chấm riêng sau khi ra ca chính)."""
    sessions: list = []
    open_in = None
    for local, ct in entries:
        if ct == CHECK_IN:
            open_in = local
        elif open_in is not None:   # CHECK_OUT đóng phiên đang mở
            sessions.append((open_in, local))
            open_in = None
    return sessions


def _gop_khoang(
    manh: list[tuple[datetime, datetime]], lo: datetime, hi: datetime,
) -> list[tuple[datetime, datetime]]:
    """Kẹp các mảnh khoảng vào [lo,hi], sắp xếp rồi HỢP các khoảng chồng/kề nhau — trả danh sách
    KHÔNG chồng lấn. Chống đếm TRÙNG phút khi cửa sổ ca thường và phiếu tăng ca lỡ giao nhau."""
    kep: list[tuple[datetime, datetime]] = []
    for a, b in manh:
        a2, b2 = max(a, lo), min(b, hi)
        if b2 > a2:
            kep.append((a2, b2))
    kep.sort(key=lambda x: x[0])
    ra: list[list[datetime]] = []
    for a, b in kep:
        if ra and a <= ra[-1][1]:
            if b > ra[-1][1]:
                ra[-1][1] = b
        else:
            ra.append([a, b])
    return [(a, b) for a, b in ra]


class AttendanceError(Exception):
    """Base for attendance domain errors."""


class AttendanceValidationError(AttendanceError):
    """A field failed validation."""


class AttendanceNotFound(AttendanceError):
    """No such work location."""


class NoLinkedEmployee(AttendanceError):
    """The acting user has no linked employee record — cannot self check-in."""


def _clean(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    return v or None


def _today_vn() -> date:
    """Hôm nay theo giờ VN (không phải giờ máy chủ).

    SEAM cố ý để test GHIM được ngày: mọi luật bám "hôm nay" mà không ghim được thì suite xanh/đỏ
    theo NGÀY CHẠY chứ không theo code — vd test hạn mức chỉnh công dùng ngày 1–11 của tháng hiện
    tại, chạy cuối tháng thì là quá khứ, chạy mùng 3 thì là tương lai."""
    return datetime.now(timezone.utc).astimezone(VN_TZ).date()


def _in_headcount_on(emp, d: date) -> bool:
    """NV có trong biên chế ngày d (đã vào làm & chưa nghỉ việc) → đủ điều kiện hưởng công lễ."""
    if getattr(emp, "hire_date", None) is not None and emp.hire_date > d:
        return False
    if getattr(emp, "resign_date", None) is not None and emp.resign_date < d:
        return False
    return True


class AttendanceService:
    def __init__(
        self,
        attendance: AttendanceRepository,
        employees: EmployeeRepository,
        audit: AuditLogRepository,
        leaves=None,
        calendar=None,
        payroll=None,
        overtime=None,
        late_early=None,
    ) -> None:
        self.attendance = attendance
        self.employees = employees
        self.audit = audit
        self.leaves = leaves  # LeaveRepository | None — để Bảng công tháng đánh dấu nghỉ đã duyệt
        # CalendarService | None — lịch chung: cộng công ngày lễ (PP-B) + số công chuẩn tháng.
        self._work_calendar = calendar
        # PayrollRepository | None — chỉ để CHẶN mở kỳ công khi kỳ lương đã chốt (Q3). Không vòng
        # service↔service (payroll_service phụ thuộc attendance_service, đây chỉ đọc payroll REPO).
        self._payroll = payroll
        # OvertimeRepository | None — phiếu tăng ca ĐÃ DUYỆT là GIẤY PHÉP + TRẦN cho tiền tăng ca.
        # None (unit test dựng tay) ⇒ KHÔNG gate, giữ hành vi cũ.
        self.overtime = overtime
        # LateEarlyRepository | None — phiếu đi muộn/về sớm/nghỉ nửa buổi ĐÃ DUYỆT: miễn phạt
        # đúng phần đã xin, và (khi tick trừ phép) hoàn công trả theo lương vị trí.
        self.late_early = late_early
        self._shift_id_cache: dict[tuple[int, date], int | None] = {}

    def _shift_for_day(self, employee, work_date: date, shifts: dict | None = None):
        key = (employee.id, work_date)
        if key not in self._shift_id_cache:
            self._shift_id_cache[key] = self.employees.shift_id_on(employee, work_date)
        shift_id = self._shift_id_cache[key]
        if shift_id is None:
            return None
        return shifts.get(shift_id) if shifts is not None else self.attendance.get_shift(shift_id)

    def prefetch_shift_days(self, employee_ids: set[int] | None, start: date, end: date) -> dict:
        """Nạp sẵn ca-khai-theo-ngày vào cache — cắt N+1 cho lưới NV × ngày. Trả luôn
        map đã đọc để caller dùng tiếp, khỏi truy vấn lần hai.

        Chỉ seed những ô có ca cụ thể: đó là đáp án cuối vì lớp per-day ĐÈ lên mốc.
        Ô nghỉ theo lịch (`is_off`) cố ý không seed để `_shift_for_day` rơi xuống ca
        nền — đúng luật "nghỉ chỉ là dấu kế hoạch, không chặn chấm công".
        """
        day_map = self.employees.shift_days_map(employee_ids, start, end)
        for (emp_id, wd), row in day_map.items():
            if row.shift_id is not None:
                self._shift_id_cache[(emp_id, wd)] = row.shift_id
        return day_map

    def _shift_and_work_day_for_local(self, employee, local: datetime, shifts: dict | None = None):
        """Resolve the shift and work date, including an overnight shift from yesterday."""
        previous_day = local.date() - timedelta(days=1)
        previous_shift = self._shift_for_day(employee, previous_day, shifts)
        minute = local.hour * 60 + local.minute
        if (previous_shift is not None and previous_shift.is_overnight
                and minute <= previous_shift.end_minute):
            return previous_shift, previous_day
        shift = self._shift_for_day(employee, local.date(), shifts)
        return shift, work_day_of(local, shift)

    def _checkout_deadline_for(self, employee, in_local: datetime, shifts: dict | None = None):
        """Hạn chót mà một lượt bấm còn được tính là RA của ca mở lúc `in_local`:
        HẾT CA + `CHECK_OUT_GRACE_HOURS`. Nhờ mốc này, tăng ca vượt nửa đêm vẫn ghép đúng cặp
        vào-ra (trước đây lượt RA rạng sáng bị ném sang ngày mới ⇒ mất trắng công cả ngày)."""
        shift, wd = self._shift_and_work_day_for_local(employee, in_local, shifts)
        if shift is None:
            return in_local + timedelta(hours=CHECK_OUT_GRACE_HOURS)
        midnight = datetime(wd.year, wd.month, wd.day, tzinfo=VN_TZ)
        end_at = midnight + timedelta(
            minutes=shift.end_minute + (1440 if shift.is_overnight else 0)
        )
        return end_at + timedelta(hours=CHECK_OUT_GRACE_HOURS)

    # --- work locations (HR) -----------------------------------------------

    @staticmethod
    def _validate_location(name, latitude, longitude, radius_m):
        name = (name or "").strip()
        if not name:
            raise AttendanceValidationError("Tên điểm là bắt buộc.")
        try:
            lat, lon = float(latitude), float(longitude)
        except (TypeError, ValueError):
            raise AttendanceValidationError("Toạ độ không hợp lệ.")
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            raise AttendanceValidationError("Toạ độ ngoài khoảng cho phép (vĩ độ ±90, kinh độ ±180).")
        if radius_m is None or int(radius_m) <= 0:
            raise AttendanceValidationError("Bán kính phải là số dương (mét).")
        return name, lat, lon, int(radius_m)

    def list_locations(self, *, active_only: bool = False) -> list[WorkLocation]:
        return self.attendance.list_locations(active_only=active_only)

    def create_location(self, *, actor, name, latitude, longitude, radius_m, note=None) -> WorkLocation:
        name, lat, lon, radius = self._validate_location(name, latitude, longitude, radius_m)
        loc = self.attendance.create_location(
            name=name, latitude=lat, longitude=lon, radius_m=radius, note=_clean(note), is_active=True
        )
        self.audit.create(
            actor_user_id=actor.id, action="create_work_location",
            target=f"work_location:{loc.id}", detail=f"{name} ({lat},{lon}) r={radius}m",
        )
        return loc

    def update_location(self, *, actor, location_id, name, latitude, longitude, radius_m, note=None, is_active=True) -> WorkLocation:
        loc = self.attendance.get_location(location_id)
        if loc is None:
            raise AttendanceNotFound("Không tìm thấy điểm chấm công.")
        name, lat, lon, radius = self._validate_location(name, latitude, longitude, radius_m)
        self.attendance.update_location(
            loc, name=name, latitude=lat, longitude=lon, radius_m=radius,
            note=_clean(note), is_active=bool(is_active),
        )
        self.audit.create(
            actor_user_id=actor.id, action="update_work_location",
            target=f"work_location:{loc.id}", detail=f"{name} ({lat},{lon}) r={radius}m active={loc.is_active}",
        )
        return loc

    def delete_location(self, *, actor, location_id) -> None:
        loc = self.attendance.get_location(location_id)
        if loc is None:
            raise AttendanceNotFound("Không tìm thấy điểm chấm công.")
        self.attendance.delete_location(loc)
        self.audit.create(
            actor_user_id=actor.id, action="delete_work_location",
            target=f"work_location:{location_id}", detail=loc.name,
        )

    # --- work shifts / ca kíp (HR) -----------------------------------------

    @staticmethod
    def _validate_shift(name, start_time, end_time, grace_minutes, is_overnight):
        name = (name or "").strip()
        if not name:
            raise AttendanceValidationError("Tên ca là bắt buộc.")
        start_min = _hhmm_to_min(start_time)
        end_min = _hhmm_to_min(end_time)
        if not is_overnight and end_min <= start_min:
            raise AttendanceValidationError("Giờ ra phải sau giờ vào (hoặc tích 'Ca qua đêm').")
        g = int(grace_minutes) if grace_minutes is not None else 0
        if g < 0:
            raise AttendanceValidationError("Dung sai đi muộn không được âm.")
        return name, start_min, end_min, g

    def list_shifts(self, *, active_only: bool = False) -> list[WorkShift]:
        return self.attendance.list_shifts(active_only=active_only)

    def create_shift(self, *, actor, name, start_time, end_time, is_overnight=False,
                     grace_minutes=5, meal_allowance=25000,
                     shift_allowance=50000, night_multiplier=1.3, note=None) -> WorkShift:
        is_overnight = bool(is_overnight)
        name, sm, em, g = self._validate_shift(name, start_time, end_time, grace_minutes, is_overnight)
        s = self.attendance.create_shift(
            name=name, start_minute=sm, end_minute=em, is_overnight=is_overnight,
            grace_minutes=g, meal_allowance=meal_allowance, shift_allowance=shift_allowance,
            night_multiplier=max(1.0, float(night_multiplier or 1.0)),
            note=_clean(note), is_active=True,
        )
        self.audit.create(actor_user_id=actor.id, action="create_work_shift",
                          target=f"work_shift:{s.id}", detail=f"{name} {start_time}–{end_time}")
        return s

    def update_shift(self, *, actor, shift_id, name, start_time, end_time, is_overnight=False,
                     grace_minutes=5, meal_allowance=25000,
                     shift_allowance=50000, night_multiplier=1.3, note=None, is_active=True) -> WorkShift:
        s = self.attendance.get_shift(shift_id)
        if s is None:
            raise AttendanceNotFound("Không tìm thấy ca làm việc.")
        is_overnight = bool(is_overnight)
        name, sm, em, g = self._validate_shift(name, start_time, end_time, grace_minutes, is_overnight)
        self.attendance.update_shift(
            s, name=name, start_minute=sm, end_minute=em, is_overnight=is_overnight,
            grace_minutes=g, meal_allowance=meal_allowance, shift_allowance=shift_allowance,
            night_multiplier=max(1.0, float(night_multiplier or 1.0)),
            note=_clean(note), is_active=bool(is_active),
        )
        self.audit.create(actor_user_id=actor.id, action="update_work_shift",
                          target=f"work_shift:{s.id}", detail=f"{name} {start_time}–{end_time}")
        return s

    def delete_shift(self, *, actor, shift_id) -> None:
        s = self.attendance.get_shift(shift_id)
        if s is None:
            raise AttendanceNotFound("Không tìm thấy ca làm việc.")
        if self.employees.shift_is_referenced(shift_id):
            raise AttendanceValidationError(
                "Ca đã được gán cho nhân viên nên không thể xóa. Hãy chuyển ca sang trạng thái ngừng sử dụng."
            )
        self.attendance.delete_shift(s)
        self.audit.create(actor_user_id=actor.id, action="delete_work_shift",
                          target=f"work_shift:{shift_id}", detail=s.name)

    # --- self check-in ------------------------------------------------------

    def _employee_for_user(self, user):
        emp = self.employees.get_by_user_id(user.id)
        if emp is None:
            raise NoLinkedEmployee("Tài khoản của bạn chưa gắn hồ sơ nhân viên.")
        return emp

    def _shift_for_check(self, employee, now_local: datetime):
        """Ca có hiệu lực tại thời điểm chấm; không có ca thì tuyệt đối không ghi log."""
        shift, work_day = self._shift_and_work_day_for_local(employee, now_local)
        if shift is None:
            raise AttendanceValidationError(
                "Bạn chưa được gán ca làm việc có hiệu lực hôm nay. Liên hệ HCNS để được gán ca."
            )
        if not shift.is_active:
            raise AttendanceValidationError(
                "Ca làm việc được gán hiện đã ngừng sử dụng. Liên hệ HCNS để được gán ca khác."
            )
        return shift, work_day

    def _require_shift_on_day(self, employee, work_day: date):
        """Dùng cho chấm bù/yêu cầu điều chỉnh tại một ngày công cụ thể."""
        shift = self._shift_for_day(employee, work_day)
        if shift is None:
            raise AttendanceValidationError(
                "Nhân viên chưa được gán ca làm việc có hiệu lực trong ngày này."
            )
        if not shift.is_active:
            raise AttendanceValidationError("Ca làm việc trong ngày này đã ngừng sử dụng.")
        return shift

    def _next_check_type(self, employee_id: int, shift=None,
                         now_local: datetime | None = None) -> str:
        """VÀO/RA luân phiên theo CA ĐANG MỞ: lượt gần nhất là VÀO và ca đó CHƯA đóng (còn trong
        cửa sổ nhận-RA = hết ca + `CHECK_OUT_GRACE_HOURS`) → lượt này là RA, KỂ CẢ đã sang ngày
        dương lịch mới (tăng ca vượt nửa đêm). Ngoài cửa sổ (quên chấm RA hôm qua, hôm nay mới bấm)
        → VÀO ca mới, đêm cũ để treo — giữ ý đồ chống 'kéo trạng thái xuyên ngày'."""
        last = self.attendance.last_log(employee_id)
        if last is None or last.check_type != CHECK_IN:
            return CHECK_IN
        now_local = now_local or datetime.now(timezone.utc).astimezone(VN_TZ)
        last_local = _as_utc(last.checked_at).astimezone(VN_TZ)
        emp = self.employees.get_by_id(employee_id)
        if emp is None:
            return CHECK_IN
        return CHECK_OUT if now_local <= self._checkout_deadline_for(emp, last_local) else CHECK_IN

    def _ot_window_on(self, emp, work_day: date) -> tuple[int, int] | None:
        """Cửa sổ (from_minute, to_minute) của phiếu TĂNG CA đã DUYỆT của NV cho ngày công `work_day`,
        hoặc None. Dùng để (a) cho phép chấm VÀO tăng ca sau khi ra ca chính, (b) hiện nhãn nút."""
        if self.overtime is None or emp is None:
            return None
        for t in self.overtime.approved_in_range(work_day, work_day):
            if t.employee_id == emp.id and t.work_date == work_day:
                return (int(t.from_minute), int(t.to_minute))
        return None

    def _today_punch_counts(self, emp, shift, work_day: date) -> tuple[int, int]:
        """(số lượt VÀO, số lượt RA) của NV trong NGÀY CÔNG `work_day` — để biết đã ra ca chính chưa
        (outs ≥ 1) và đang ở phiên nào (ins ≥ 2 = đang trong phiên tăng ca)."""
        ins = outs = 0
        for lg in self.attendance.list_by_employee(emp.id, limit=30):
            local = _as_utc(lg.checked_at).astimezone(VN_TZ)
            if work_day_of(local, shift) == work_day:
                if lg.check_type == CHECK_IN:
                    ins += 1
                else:
                    outs += 1
        return ins, outs

    def _check_timing(self, employee_id: int, shift, work_day: date,
                      now_local: datetime) -> tuple[str, str | None, bool]:
        """Trả (action, reason, ot_mode). `ot_mode` = lượt bấm kế tiếp thuộc phiên TĂNG CA (vào/ra
        tăng ca) — để FE đổi nhãn nút. Sau khi đã RA ca chính, chỉ cho chấm VÀO lại (thành VÀO tăng
        ca) khi có phiếu tăng ca ĐÃ DUYỆT phủ giờ hiện tại (chốt 25/07/2026)."""
        action = self._next_check_type(employee_id, shift, now_local)
        emp = self.employees.get_by_id(employee_id)
        ins_today, outs_today = (self._today_punch_counts(emp, shift, work_day) if emp else (0, 0))
        reason = None
        ot_mode = False
        if action == CHECK_IN:
            reason = check_in_block_reason(shift=shift, work_day=work_day, now_local=now_local)
            if outs_today >= 1:      # đã ra ca chính → lượt VÀO này là VÀO TĂNG CA
                ot_mode = True
                if reason is not None:   # sau tan ca: chỉ mở nếu có phiếu duyệt phủ giờ này
                    ot_win = self._ot_window_on(emp, work_day)
                    midnight = datetime(work_day.year, work_day.month, work_day.day, tzinfo=VN_TZ)
                    now_min = round((now_local - midnight).total_seconds() / 60)
                    if ot_win is None:
                        reason = ("Bạn đã chấm ra ca chính. Chưa có phiếu tăng ca được duyệt cho hôm "
                                  "nay nên không thể chấm vào tăng ca.")
                    elif now_min <= ot_win[1] + CHECK_OUT_GRACE_HOURS * 60:
                        reason = None    # trong khung phiếu (nới hậu kỳ) → cho chấm vào tăng ca
                    else:
                        reason = (f"Phiếu tăng ca hôm nay kết thúc lúc {min_to_hhmm(ot_win[1] % 1440)}. "
                                  "Đã quá giờ nên không chấm vào tăng ca được.")
        else:  # CHECK_OUT
            ot_mode = ins_today >= 2   # đang đóng phiên thứ 2+ = RA tăng ca
        return action, reason, ot_mode

    def _today_summary(self, emp, shift) -> dict | None:
        """Tóm tắt chấm công HÔM NAY (giờ VN) của NV cho khối 'Hôm nay của tôi': giờ vào/ra,
        công dự kiến, và LÝ DO khi công < đủ (thiếu chấm RA / vào trễ / về sớm / chưa gán ca)."""
        today = datetime.now(timezone.utc).astimezone(VN_TZ).date()
        entries = []
        for lg in self.attendance.list_by_employee(emp.id, limit=20):
            local = _as_utc(lg.checked_at).astimezone(VN_TZ)
            if work_day_of(local, shift) == today:
                entries.append((local, lg.check_type))
        if not entries:
            return None
        entries.sort(key=lambda x: x[0])
        ins = [t for t, ct in entries if ct == CHECK_IN]
        outs = [t for t, ct in entries if ct == CHECK_OUT]
        first_in = ins[0] if ins else entries[0][0]
        last_out = outs[-1] if outs else None
        sessions = pair_sessions(entries)
        main_out = sessions[0][1] if sessions else None
        ot_in, ot_out = ((sessions[1][0], sessions[-1][1])
                         if len(sessions) >= 2 else (None, None))
        out = {"first_in": first_in.strftime("%H:%M"),
               "last_out": last_out.strftime("%H:%M") if last_out else None,
               "cong": None, "late": False, "early": False, "ot_minutes": 0, "reason": None}
        if shift is None:
            out["reason"] = "Chưa gán ca làm việc"
            return out
        info = compute_day_cong(
            start_min=shift.start_minute, end_min=shift.end_minute,
            is_overnight=shift.is_overnight, grace_min=shift.grace_minutes,
            first_in_min=first_in.hour * 60 + first_in.minute,
            main_out_min=(main_out.hour * 60 + main_out.minute) if main_out else None,
            in_day_offset=(first_in.date() - today).days,
            main_out_offset=((main_out.date() - today).days if main_out else None),
            ot_in_min=(ot_in.hour * 60 + ot_in.minute) if ot_in else None,
            ot_out_min=(ot_out.hour * 60 + ot_out.minute) if ot_out else None,
            ot_in_offset=((ot_in.date() - today).days if ot_in else None),
            ot_out_offset=((ot_out.date() - today).days if ot_out else None),
            ot_window=self._ot_window_on(emp, today),
        )
        out.update(cong=info["cong"], late=info["late"], early=info["early"], ot_minutes=info["ot_minutes"])
        if info["incomplete"]:
            out["reason"] = "Chưa chấm RA ca chính"
        elif info["cong"] < 1.0:
            out["reason"] = ("Vào trễ và về sớm" if info["late"] and info["early"]
                             else "Vào trễ quá dung sai" if info["late"]
                             else "Về sớm" if info["early"] else None)
        return out

    def my_status(self, *, user) -> dict:
        """What the self-check-in card needs: linked employee, next action, last check,
        whether any location is configured, ca hôm nay + tóm tắt công hôm nay."""
        emp = self.employees.get_by_user_id(user.id)
        locations = self.attendance.list_locations(active_only=True)
        if emp is None:
            return {"has_employee": False, "employee_name": None, "next_action": None,
                    "last_check": None, "locations_configured": len(locations) > 0,
                    "shift": None, "today": None, "can_check": False,
                    "check_block_reason": "Tài khoản chưa gắn hồ sơ nhân viên."}
        last = self.attendance.last_log(emp.id)
        now_local = datetime.now(timezone.utc).astimezone(VN_TZ)
        shift, work_day = self._shift_and_work_day_for_local(emp, now_local)
        if shift is not None and not shift.is_active:
            shift = None
        if shift is None:
            next_action = None
            block_reason = "Bạn chưa được gán ca làm việc có hiệu lực hôm nay. Liên hệ HCNS để được gán ca."
            ot_mode = False
        else:
            next_action, block_reason, ot_mode = self._check_timing(emp.id, shift, work_day, now_local)
        return {
            "has_employee": True,
            "employee_id": emp.id,
            "employee_name": emp.full_name,
            "next_action": next_action,
            # Lượt kế tiếp thuộc phiên TĂNG CA (vào/ra tăng ca) → FE đổi nhãn nút.
            "ot_mode": ot_mode,
            "last_check": last,
            "locations_configured": len(locations) > 0,
            "shift": shift,
            "today": self._today_summary(emp, shift),
            "can_check": block_reason is None,
            "check_block_reason": block_reason,
        }

    def preview(self, *, user, latitude, longitude) -> dict:
        """Dry-run geofence cho card chấm 'sống': tính điểm gần nhất + trong/ngoài phạm vi +
        còn cách bao nhiêu — KHÔNG ghi log. Dùng để vẽ vòng geofence realtime cho NV."""
        emp = self._employee_for_user(user)  # chỉ NV có hồ sơ mới preview (self-service)
        now_local = datetime.now(timezone.utc).astimezone(VN_TZ)
        shift, work_day = self._shift_for_check(emp, now_local)
        check_type, block_reason, ot_mode = self._check_timing(emp.id, shift, work_day, now_local)
        if block_reason is not None:
            raise AttendanceValidationError(block_reason)
        try:
            lat, lon = float(latitude), float(longitude)
        except (TypeError, ValueError):
            raise AttendanceValidationError("Toạ độ gửi lên không hợp lệ.")
        locations = self.attendance.list_locations(active_only=True)
        if not locations:
            return {"locations_configured": False, "within_range": False, "distance_m": None,
                    "meters_out": None, "nearest_name": None, "radius_m": None,
                    "next_action": check_type, "ot_mode": ot_mode,
                    "message": "Chưa cấu hình điểm chấm công nào."}
        nearest, best = None, None
        for loc in locations:
            d = haversine_m(lat, lon, float(loc.latitude), float(loc.longitude))
            if best is None or d < best:
                best, nearest = d, loc
        distance = round(best, 1)
        within = distance <= nearest.radius_m
        meters_out = 0.0 if within else round(distance - nearest.radius_m, 1)
        return {
            "locations_configured": True, "within_range": within, "distance_m": distance,
            "meters_out": meters_out, "nearest_name": nearest.name, "radius_m": nearest.radius_m,
            "next_action": check_type, "ot_mode": ot_mode,
            "message": (f"Trong phạm vi '{nearest.name}' (cách {distance:.0f} m)." if within
                        else f"Ngoài phạm vi '{nearest.name}' — còn cách {meters_out:.0f} m."),
        }

    def check(self, *, user, latitude, longitude) -> dict:
        """Attempt a GPS check-in/out. Returns a result dict; a log is created ONLY when
        the point is inside some active location's radius (chặn cứng)."""
        emp = self._employee_for_user(user)
        now_local = datetime.now(timezone.utc).astimezone(VN_TZ)
        shift, work_day = self._shift_for_check(emp, now_local)
        check_type, block_reason, ot_mode = self._check_timing(emp.id, shift, work_day, now_local)
        if block_reason is not None:
            raise AttendanceValidationError(block_reason)
        try:
            lat, lon = float(latitude), float(longitude)
        except (TypeError, ValueError):
            raise AttendanceValidationError("Toạ độ gửi lên không hợp lệ.")

        locations = self.attendance.list_locations(active_only=True)
        if not locations:
            return {"success": False, "within_range": False, "check_type": None,
                    "distance_m": None, "nearest_location": None,
                    "message": "Chưa cấu hình điểm chấm công nào. Liên hệ HCNS.", "log": None}

        # Nearest active location.
        nearest, best = None, None
        for loc in locations:
            d = haversine_m(lat, lon, float(loc.latitude), float(loc.longitude))
            if best is None or d < best:
                best, nearest = d, loc
        distance = round(best, 1)
        within = distance <= nearest.radius_m

        if not within:
            return {
                "success": False, "within_range": False, "check_type": None,
                "distance_m": distance, "nearest_location": nearest,
                "message": (f"Bạn đang cách điểm '{nearest.name}' {distance:.0f} m "
                            f"(bán kính {nearest.radius_m} m) — ngoài phạm vi, chưa chấm được."),
                "log": None,
            }

        log = self.attendance.create_log(
            employee_id=emp.id, work_location_id=nearest.id, check_type=check_type,
            latitude=lat, longitude=lon, distance_m=distance, within_range=True,
        )
        suffix = " TĂNG CA" if ot_mode else ""
        verb = ("VÀO" if check_type == CHECK_IN else "RA") + suffix
        return {
            "success": True, "within_range": True, "check_type": check_type, "ot_mode": ot_mode,
            "distance_m": distance, "nearest_location": nearest,
            "message": f"Đã chấm {verb} tại '{nearest.name}' (cách {distance:.0f} m).",
            "log": log,
        }

    def my_logs(self, *, user, limit: int = 30):
        emp = self._employee_for_user(user)
        return self.attendance.list_by_employee(emp.id, limit=limit)

    def _allowed_employee_ids(self, scope, actor) -> set[int] | None:
        """Tập employee_id mà `actor` được phép xem theo scope. None = không giới hạn (all).
        department/own → dùng lại EmployeeRepository (đã xử lý actor không có phòng → thu về own)."""
        if scope is None or scope == SCOPE_ALL:
            return None
        return {e.id for e in self.employees.list_scoped_all(scope=scope, actor=actor)}

    # Trần khi CÓ lọc ngày. Khoảng ngày đã tự bó dữ liệu lại, nhưng một ngày của xưởng 50 người là
    # ~200 lượt — giữ trần 100 thì lọc xong vẫn MẤT NỬA NGÀY trong im lặng, tức lọc ngày mà vẫn
    # không tin được. Số này cũng là số hiện trên màn ("tối đa N"), đừng để hai nơi lệch nhau.
    LOG_LIMIT_CO_LOC_NGAY = 1000

    def list_logs(self, *, scope=None, actor=None, employee_id: int | None = None,
                  limit: int = 100, q: str | None = None, tu_ngay=None, den_ngay=None):
        """Log chấm công, LỌC THEO SCOPE của người gọi (own/department/all). `employee_id` do
        client truyền chỉ được chấp nhận nếu nằm trong tập cho phép (ngoài → rỗng, không rò).

        `q` (tìm theo tên/mã NV) đi XUỐNG SQL cùng tập `allowed` — nó THU HẸP thêm chứ không bao
        giờ thay thế lớp scope. Gõ tên người ngoài phạm vi thì `allowed` đã loại từ trước, kết quả
        rỗng; tìm kiếm không được là đường vòng để nhìn trộm."""
        # Ngày do người dùng chọn là NGÀY VN; log lưu UTC ⇒ phải quy đổi ở đây, không đẩy xuống
        # repo. `den_ngay` lấy TRỌN ngày đó nên biên phải là 00:00 hôm SAU (nửa mở), không thì
        # người chọn "đến 28/7" mất sạch lượt bấm trong ngày 28.
        tu = datetime.combine(tu_ngay, dtime(0, 0), tzinfo=VN_TZ).astimezone(timezone.utc) if tu_ngay else None
        den = (datetime.combine(den_ngay, dtime(0, 0), tzinfo=VN_TZ)
               + timedelta(days=1)).astimezone(timezone.utc) if den_ngay else None
        if tu is not None or den is not None:
            limit = self.LOG_LIMIT_CO_LOC_NGAY

        allowed = self._allowed_employee_ids(scope, actor)
        if employee_id is not None:
            if allowed is not None and employee_id not in allowed:
                return []
            return self.attendance.list_all(employee_ids={employee_id}, limit=limit, q=q,
                                            tu=tu, den=den)
        return self.attendance.list_all(employee_ids=allowed, limit=limit, q=q, tu=tu, den=den)

    # --- lịch sử thay đổi ca + hộp thư của NV -------------------------------

    def shift_changes(self, *, scope=None, actor=None, year: int | None = None,
                      month: int | None = None, employee_id: int | None = None,
                      kind: str | None = None, limit: int = 500) -> list[dict]:
        """Lịch sử đổi ca cho màn HCNS — LỌC THEO SCOPE (tổ trưởng chỉ thấy tổ mình).

        Trả dict đã kèm TÊN người và TÊN ca: màn hình cần đọc được ngay "từ Ca ngày sang Ca
        đêm", không phải tự đi tra 3 bảng."""
        allowed = self._allowed_employee_ids(scope, actor)
        if employee_id is not None:
            if allowed is not None and employee_id not in allowed:
                return []          # ngoài phạm vi → rỗng, KHÔNG rò dữ liệu tổ khác
            allowed = [employee_id]
        elif allowed is not None:
            allowed = list(allowed)

        start = end = None
        if year and month:
            start = date(year, month, 1)
            end = date(year, month, calendar.monthrange(year, month)[1])
        rows = self.employees.list_shift_changes(
            employee_ids=allowed, kind=kind, start=start, end=end, limit=limit)
        return self._decorate_shift_changes(rows)

    def _decorate_shift_changes(self, rows) -> list[dict]:
        """Gắn tên NV / tên ca / tên người sửa vào từng dòng — MỘT lượt tra cho cả mẻ."""
        shift_names = {s.id: s.name for s in self.attendance.list_shifts()}
        emp_ids = {r.employee_id for r in rows}
        emps = {e: self.employees.get_by_id(e) for e in emp_ids}
        actor_ids = {r.actor_user_id for r in rows if r.actor_user_id}
        actors = {}
        for uid in actor_ids:
            emp = self.employees.get_by_user_id(uid)
            actors[uid] = emp.full_name if emp is not None else None
        out = []
        for r in rows:
            emp = emps.get(r.employee_id)
            out.append({
                "id": r.id, "employee_id": r.employee_id,
                "employee_name": getattr(emp, "full_name", None),
                "employee_code": getattr(emp, "code", None),
                "kind": r.kind, "origin": r.origin, "action": r.action,
                "apply_date": r.apply_date,
                "shift_id_before": r.shift_id_before,
                "shift_name_before": shift_names.get(r.shift_id_before),
                "shift_id_after": r.shift_id_after,
                "shift_name_after": shift_names.get(r.shift_id_after),
                "is_off_before": bool(r.is_off_before), "is_off_after": bool(r.is_off_after),
                "inherited_before": bool(r.inherited_before),
                "actor_user_id": r.actor_user_id,
                "actor_name": actors.get(r.actor_user_id),
                "created_at": r.created_at,
                # NULL = NV không có tài khoản ⇒ màn hiện chip "chưa báo được".
                "notified": r.notified_user_id is not None,
                "seen": r.seen_at is not None,
            })
        return out

    def my_shift_changes(self, *, user, unseen_only: bool = False, limit: int = 50) -> list[dict]:
        """Hộp thư của chính người đăng nhập. Đọc theo `notified_user_id` — người không có tài
        khoản thì vốn không có hộp thư nên không cần map qua employee.

        `unseen_only` cho khối báo ở màn "Công của tôi": nó là tin MỚI, đọc xong phải thôi hiện.
        Lấy cả đã đọc thì khối đó bám đầu màn vĩnh viễn."""
        rows = self.employees.list_my_shift_changes(
            user.id, unseen_only=unseen_only, limit=limit)
        return self._decorate_shift_changes(rows)

    def unseen_shift_changes(self, *, user) -> int:
        return self.employees.count_unseen_shift_changes(user.id)

    def mark_shift_changes_seen(self, *, user) -> int:
        return self.employees.mark_shift_changes_seen(user.id)

    # --- ngày nghỉ phép đã duyệt (dùng chung) --------------------------------

    def _leave_map(self, year: int, month: int,
                   allowed: set[int] | None) -> dict[int, dict[int, dict]]:
        """Ngày NGHỈ NGUYÊN NGÀY đã duyệt trong tháng: `{emp_id → {day → {name, is_paid}}}`.

        ⚠️ **MỘT định nghĩa duy nhất, dùng cho CẢ Bảng công tháng LẪN lưới Phân ca tháng.** Hai màn
        nói về cùng một ngày nghỉ; chép ra hai bản là sớm muộn Bảng công bảo "có phép" còn lưới bảo
        "không", mà không ai biết bên nào đúng.

        `allowed=None` = không lọc; có tập thì chỉ giữ nhân sự trong tầm nhìn của người gọi — chống
        rò ngày nghỉ của tổ khác.

        Chỉ `approved`; phiếu đang chờ KHÔNG tính (`approved_in_range`). Khoảng ngày được **cắt
        đúng trong tháng** nên phiếu vắt qua hai tháng chỉ hiện phần thuộc tháng đang xem."""
        out: dict[int, dict[int, dict]] = {}
        if self.leaves is None:
            return out
        days_in_month = calendar.monthrange(year, month)[1]
        first = date(year, month, 1)
        last = date(year, month, days_in_month)
        ltypes = {t.id: t for t in self.leaves.list_types()}
        for r in self.leaves.approved_in_range(first, last):
            if allowed is not None and r.employee_id not in allowed:
                continue
            lt = ltypes.get(r.leave_type_id)
            nm = lt.name if lt is not None else "Nghỉ"
            paid = lt.is_paid if lt is not None else True
            d, e = max(r.start_date, first), min(r.end_date, last)
            while d <= e:
                out.setdefault(r.employee_id, {})[d.day] = {"name": nm, "is_paid": paid}
                d = date.fromordinal(d.toordinal() + 1)
        return out

    # --- ai LÊN BẢNG trong tháng (dùng chung Bảng công + lưới Phân ca) -------

    def _employees_in_month(self, year: int, month: int, department_id: int | None,
                            scope, actor) -> list:
        """MỌI NV trong scope còn biên chế trong tháng.

        ⚠️ **NGUỒN CHUNG của CẢ Bảng công tháng LẪN lưới Phân ca tháng** — cố ý gom về một mối để
        hai màn không nói khác nhau về cùng một tháng.

        Trước đây chỉ lưới Phân ca dùng hàm này, còn `monthly_timesheet` tự lấy "ai có lượt bấm /
        đơn phép". Hệ quả: người CẢ THÁNG không chấm buổi nào biến mất khỏi Bảng công — HCNS không
        soi ra được ai vắng cả tháng, NV quên chấm thì không còn ô ngày nào để bấm xin chỉnh công,
        và họ mất luôn công lễ. Người chưa chấm công buổi nào chính là người cần nhìn thấy nhất."""
        last = date(year, month, calendar.monthrange(year, month)[1])
        first = date(year, month, 1)
        rows = [
            e for e in self.employees.list_scoped_all(scope=scope or SCOPE_ALL, actor=actor)
            if _in_headcount_on(e, last) or _in_headcount_on(e, first)
        ]
        if department_id is not None:
            rows = [e for e in rows if e.department_id == department_id]
        return sorted(rows, key=lambda e: (e.code or "", e.id))

    # --- bảng công tháng ----------------------------------------------------

    def he_so_ngay(self) -> dict[str, float]:
        """Hệ số công HIỂN THỊ theo loại ngày — để ô lịch nói "→ tính N công" mà KHÔNG viết cứng số.

        Đây là số ĐỌC RA TỪ CẤU HÌNH LƯƠNG, không phải công thức thứ hai: nó phải khớp từng đồng
        với `PayrollService._compute`. Hai chỗ dùng HAI công thức khác nhau, CỐ Ý (chủ chốt
        17/08/2026 — xem `payroll_service.py` khối premium Đ98):

          • NGÀY LỄ  = **1 + holiday_work_multiplier** (mặc định 1 + 3 = 4×). Phần 1× là tiền lương
            ngày lễ Đ112 — người đó hưởng dù nghỉ ở nhà; Đ98.1.c trả TRỌN 300% "chưa kể" khoản đó.
          • NGHỈ TUẦN = **restday_work_multiplier** (mặc định 2×), KHÔNG cộng 1. Chủ nhật nghỉ ở nhà
            thì không có đồng nào, nên phần 1× trong lương công CHÍNH LÀ tiền đi làm ⇒ 1× + 1×.
            Cộng thêm 1 ở đây là màn hình hứa 3× trong khi phiếu lương trả 2×.
          • off1x = 1× phẳng, không hệ số (Lương trả riêng, uncapped).

        Đọc PayrollRepository (đã có sẵn ở `self._payroll`) chứ KHÔNG gọi PayrollService — service
        Lương đang phụ thuộc service này, nối ngược lại là vòng."""
        params = self._payroll.get_params() if self._payroll is not None else None
        m_hol = float(getattr(params, "holiday_work_multiplier", 3.0) or 3.0)
        m_rest = float(getattr(params, "restday_work_multiplier", 2.0) or 2.0)
        return {"le": round(1.0 + m_hol, 2), "nghi_tuan": round(m_rest, 2), "off1x": 1.0}

    def monthly_timesheet(self, *, year: int, month: int, department_id: int | None = None,
                          scope=None, actor=None, only_employee_id: int | None = None) -> dict:
        """Gom attendance_logs của 1 tháng thành lưới NV × ngày (giờ VN). Mỗi ô ngày:
        giờ VÀO đầu tiên, giờ RA cuối cùng, số giờ (nếu đủ vào-ra). Không cần bảng mới.

        LỌC THEO SCOPE: `only_employee_id` (self-timesheet) > `scope/actor` (own/department/all).
        CA ĐÊM: lượt RA rạng sáng ngày N+1 được quy về NGÀY VÀO ca (ngày N)."""
        if not (1 <= month <= 12):
            raise AttendanceValidationError("Tháng phải trong khoảng 1–12.")
        days_in_month = calendar.monthrange(year, month)[1]
        today = _today_vn()   # mốc "ngày chưa tới" để trải ca nền xem trước (giờ VN)

        if only_employee_id is not None:
            allowed: set[int] | None = {only_employee_id}
        else:
            allowed = self._allowed_employee_ids(scope, actor)

        # Mốc tháng theo giờ VN → quy về UTC để truy vấn. Nới +12h cuối để lấy lượt RA rạng sáng
        # ngày đầu tháng sau (thuộc ca VÀO ngày cuối tháng này), và −12h đầu để lấy lượt VÀO của ca
        # cuối tháng TRƯỚC — thiếu nó thì lượt RA rạng sáng ngày 1 thành "RA mồ côi". Lượt thừa được
        # lọc theo "ngày công" ở dưới nên không trùng đếm sang tháng khác.
        start_vn = datetime(year, month, 1, tzinfo=VN_TZ)
        end_vn = (datetime(year + 1, 1, 1, tzinfo=VN_TZ) if month == 12
                  else datetime(year, month + 1, 1, tzinfo=VN_TZ))
        logs = self.attendance.logs_in_range(
            (start_vn - timedelta(hours=12)).astimezone(timezone.utc),
            (end_vn + timedelta(hours=12)).astimezone(timezone.utc),
        )

        shifts = {s.id: s for s in self.attendance.list_shifts()}

        # Ca khai theo NGÀY (lưới phân ca) — 1 query cho cả tháng. Biên nới ±2 ngày vì
        # `_shift_and_work_day_for_local` luôn dò ca của ngày HÔM TRƯỚC, và log đã lấy
        # rộng ±12h nên chạm được ngày cuối tháng trước / đầu tháng sau.
        shift_day_map = self.prefetch_shift_days(
            allowed,
            date(year, month, 1) - timedelta(days=2),
            date(year, month, days_in_month) + timedelta(days=2),
        )
        # Ngày NGHỈ theo lịch xoay ca (khai tay trên lưới) — chỉ để bảng công phân biệt
        # "nghỉ có kế hoạch" với "vắng". KHÔNG ra tiền, KHÔNG đụng công.
        planned_off_by_emp: dict[int, set[int]] = {}
        # Ngày ĐÃ XẾP CA nhưng CHƯA chấm (nhất là ngày TƯƠNG LAI) — để ô lịch vẫn hiện "mai làm ca
        # nào" (chủ chốt 24/08/2026). Trước đây ô chỉ dựng cho ngày có chấm/nghỉ/lễ nên ngày mai
        # trống trơn. CHỈ lấy ngày có `shift_id` thật (không phải `is_off`); ngày nghỉ đã vào
        # `planned_off`. Chỉ ngày trong ĐÚNG tháng đang xem.
        scheduled_by_emp: dict[int, set[int]] = {}
        for (emp_id_k, wd), row_k in shift_day_map.items():
            if wd.year != year or wd.month != month:
                continue
            if row_k.is_off:
                planned_off_by_emp.setdefault(emp_id_k, set()).add(wd.day)
            elif row_k.shift_id is not None:
                scheduled_by_emp.setdefault(emp_id_k, set()).add(wd.day)

        # employee_id → { day(int) → [(local_dt, check_type)] } theo NGÀY CÔNG, chỉ trong tháng này.
        # Duyệt TUẦN TỰ theo thời gian cho TỪNG NV và giữ "ca đang mở": lượt RA rơi sau nửa đêm được
        # ghép về NGÀY CÔNG của lượt VÀO đang mở (tăng ca vượt 24:00), thay vì rơi sang ngày dương
        # lịch mới — rơi sang ngày mới thì ngày cũ thiếu lượt RA ⇒ treo ⇒ MẤT TRẮNG cả công ca chính
        # lẫn tăng ca (bug chủ phát hiện 23/07/2026).
        punches_by_emp: dict[int, list] = {}
        for lg in logs:
            if allowed is not None and lg.employee_id not in allowed:
                continue
            punches_by_emp.setdefault(lg.employee_id, []).append(
                # Cờ thứ 3 = lượt này do HCNS CHẤM BÙ hay thợ tự bấm. Cần cho luật kẹp giờ ra theo
                # phiếu về sớm: chấm bù là hành động có chủ ý, có lý do, có tên người sửa ⇒ THẮNG
                # phiếu. Thợ quên bấm thì không.
                (_as_utc(lg.checked_at).astimezone(VN_TZ), lg.check_type, bool(lg.is_manual))
            )

        by_emp: dict[int, dict[int, list]] = {}
        # {emp → {ngày → set(thời điểm lượt RA do HCNS chấm bù)}} — tra lại ở vòng lặp ngày.
        ra_cham_bu: dict[int, dict[int, set]] = {}
        for emp_id, punches in punches_by_emp.items():
            emp0 = self.employees.get_by_id(emp_id)
            if emp0 is None:
                continue
            open_wd = None        # ngày công của ca đang mở (đã VÀO, chưa RA)
            open_until = None     # hạn chót còn được ghép làm RA của ca đó
            for local, ctype, la_cham_bu in sorted(punches, key=lambda x: x[0]):
                if ctype == CHECK_OUT and open_wd is not None and local <= open_until:
                    wd = open_wd                       # ghép RA về đúng ca đang mở
                    open_wd = open_until = None
                else:
                    _, wd = self._shift_and_work_day_for_local(emp0, local, shifts)
                    if ctype == CHECK_IN:
                        open_wd = wd
                        open_until = self._checkout_deadline_for(emp0, local, shifts)
                    else:
                        open_wd = open_until = None
                if wd.year != year or wd.month != month:
                    continue  # lượt thuộc tháng khác (vd RA rạng sáng ngày 1 → thuộc tháng trước)
                by_emp.setdefault(emp_id, {}).setdefault(wd.day, []).append((local, ctype))
                if ctype == CHECK_OUT and la_cham_bu:
                    ra_cham_bu.setdefault(emp_id, {}).setdefault(wd.day, set()).add(local)

        # Ngày NGHỈ NGUYÊN NGÀY đã duyệt: {emp_id → {day → {name, is_paid}}}.
        first = date(year, month, 1)
        last = date(year, month, days_in_month)
        leave_map = self._leave_map(year, month, allowed)

        # Phiếu ĐI MUỘN / VỀ SỚM / NGHỈ NỬA BUỔI đã duyệt (bảng RIÊNG, tổ trưởng duyệt):
        #   `hourly_map`      {emp_id → {day → tổng PHÚT xin vắng}}  — nền MIỄN PHẠT
        #   `hourly_leave`    {emp_id → {day → số ngày phép bị trừ}} — nhánh CÓ trừ phép
        # TUYỆT ĐỐI không nhét vào `leave_map`: `lv_days` lái 6 nhánh, trong đó nhánh phép cấp
        # `cong = 1.0` ⇒ người xin vắng 2 tiếng mà hôm ấy KHÔNG chấm công sẽ được biếu nguyên
        # một ngày lương.
        hourly_map: dict[int, dict[int, int]] = {}
        hourly_leave: dict[int, dict[int, float]] = {}
        # Khai NGOÀI nhánh `if`: vòng lặp NV bên dưới đọc nó VÔ ĐIỀU KIỆN, mà `late_early` là tham
        # số TUỲ CHỌN của service — dựng service không kèm repo phiếu (Lương gọi `metrics_map` kiểu
        # đó) là vỡ UnboundLocalError giữa chừng bảng công.
        hourly_windows: dict[int, dict[int, list]] = {}
        if self.late_early is not None:
            for r in self.late_early.approved_in_range(first, last):
                if allowed is not None and r.employee_id not in allowed:
                    continue
                d0 = r.work_date
                if not (first <= d0 <= last):
                    continue
                mins = max(0, int(r.to_minute) - int(r.from_minute))
                cur = hourly_map.setdefault(r.employee_id, {})
                cur[d0.day] = min(1440, cur.get(d0.day, 0) + mins)
                # Giữ cả KHUNG GIỜ: tổng phút không nói được phiếu nằm ĐẦU ca (đi muộn) hay CUỐI
                # ca (về sớm), mà luật kẹp giờ ra chỉ áp cho phiếu về sớm.
                hourly_windows.setdefault(r.employee_id, {}).setdefault(d0.day, []).append(
                    (int(r.from_minute), int(r.to_minute))
                )
                if r.leave_type_id is not None and float(r.leave_cong or 0) > 0:
                    lv = hourly_leave.setdefault(r.employee_id, {})
                    lv[d0.day] = min(1.0, lv.get(d0.day, 0.0) + float(r.leave_cong))
            # Đơn nghỉ NGUYÊN NGÀY thắng phiếu giờ cùng ngày — chống tha/trả hai lần.
            for eid, hdays in hourly_map.items():
                for dd in [k for k in hdays if k in leave_map.get(eid, {})]:
                    hdays.pop(dd)
                    hourly_leave.get(eid, {}).pop(dd, None)

        # Phiếu TĂNG CA đã duyệt trong tháng: {emp_id → {ngày → (from_minute, to_minute)}}. Phiếu là
        # GIẤY PHÉP + MỨC TRẦN: phần giờ vượt ca NẰM NGOÀI phiếu không ra tiền; KHÔNG có phiếu ⇒ cửa
        # sổ rỗng (0,0) ⇒ tăng ca = 0 đ. CÔNG CA CHÍNH không bị ảnh hưởng (chốt với chủ 23/07/2026).
        ot_map: dict[int, dict[int, tuple[int, int]]] = {}
        if self.overtime is not None:
            for t in self.overtime.approved_in_range(date(year, month, 1),
                                                     date(year, month, days_in_month)):
                ot_map.setdefault(t.employee_id, {})[t.work_date.day] = (
                    int(t.from_minute), int(t.to_minute)
                )

        # Ngày nghỉ lễ HƯỞNG LƯƠNG trong tháng (từ Lịch chung) → cộng 1 công cho NV trong biên chế
        # (giống ngày nghỉ phép có lương — PP-B: mẫu số Lương giữ 26, tử số phải gồm công lễ).
        paid_holidays: dict[int, str] = {}   # {day-of-month → tên lễ}
        holidays_info: list[dict] = []
        standard_cong: int | None = None
        plain_days: set[int] = set()   # ngày 'off1x' — làm chỉ 1× (không hệ số), nghỉ = không lương
        if self._work_calendar is not None:
            for s in self._work_calendar.paid_holidays_in_month(year, month):
                paid_holidays[s.day.day] = s.name
                holidays_info.append({"day": s.day.day, "date": s.day.isoformat(), "name": s.name})
            plain_days = {s.day.day for s in self._work_calendar.plain_days_in_month(year, month)}
            standard_cong = self._work_calendar.standard_working_days(year, month)

        def _empty_cell() -> dict:
            return {"first_in": None, "last_out": None, "hours": None, "present": False,
                    "cong": None, "late": False, "early": False, "ot_minutes": 0, "night": False,
                    "leave": None, "leave_paid": False, "holiday": False,
                    # Ô NGÀY tự nói LOẠI NGÀY của nó (18/08/2026). Trước đây chỉ có `holiday`, nên
                    # ngày nghỉ tuần / ngày `off1x` CÓ đi làm hiện y hệt ngày thường ("Công: 1") —
                    # người làm Chủ nhật tưởng mình bị trả thiếu. Ba cờ này LOẠI TRỪ NHAU, đúng
                    # thứ tự `plain > holiday > restday` mà tiền đang tính ở dưới.
                    "restday": False, "plain": False,
                    "planned_off": False}

        # AI LÊN BẢNG = NV còn biên chế trong tháng **HỢP** NV có dấu vết (lượt bấm / đơn phép /
        # phiếu giờ).
        #
        # HỢP chứ không THAY: người đã nghỉ việc tháng trước mà còn lượt bấm sót vẫn phải giữ hàng.
        # Đổi thành "chỉ biên chế" là làm BIẾN MẤT hàng đang thấy — thay đổi chỉ được phép thuần
        # cộng thêm.
        #
        # Nhánh dấu vết một mình là đủ cho tới 31/07/2026, và nó bỏ rơi đúng người cần thấy nhất:
        # ai CẢ THÁNG không chấm buổi nào thì không có hàng nào, nên (1) không tự xem được lịch
        # công, (2) không bấm được ô ngày để xin chỉnh công, (3) HCNS không soi ra họ, (4) mất
        # công lễ vì nhánh `emp_holidays` bên dưới không bao giờ chạy tới.
        emp_cache: dict[int, object] = {}
        if only_employee_id is not None:
            base_ids = {only_employee_id}
        else:
            emp_cache = {e.id: e for e in self._employees_in_month(
                year, month, department_id, scope, actor)}
            base_ids = set(emp_cache)
        rows = []
        for emp_id in base_ids | set(by_emp) | set(leave_map) | set(hourly_map):
            # Dùng lại object đã nạp ở trên; chỉ những id đến từ nhánh "có dấu vết" mới phải hỏi
            # DB. Không có nó thì bảng 100 NV bắn 100 query lẻ mỗi lần mở màn.
            emp = emp_cache.get(emp_id) or self.employees.get_by_id(emp_id)
            if emp is None:
                continue
            if department_id is not None and emp.department_id != department_id:
                continue
            att_days = by_emp.get(emp_id, {})
            lv_days = leave_map.get(emp_id, {})
            hl_days = hourly_map.get(emp_id, {})          # {day → phút xin vắng}
            hl_leave = hourly_leave.get(emp_id, {})       # {day → ngày phép bị trừ}
            hl_khung = hourly_windows.get(emp_id, {})     # {day → [(từ phút, đến phút)]}
            ra_bu_ngay = ra_cham_bu.get(emp_id, {})       # {day → set(thời điểm RA do chấm bù)}
            # Ngày lễ NV hưởng công lễ: không chấm công + đang trong biên chế ngày đó. CÓ đơn phép
            # phủ ngày lễ VẪN vào đây (lễ thắng phép: không tiêu ngày phép); công lễ tính theo
            # is_paid của đơn nền ở nhánh dưới (nghỉ không lương phủ lễ → 0 công, đúng luật).
            emp_holidays = {d for d in paid_holidays
                            if d not in att_days
                            and _in_headcount_on(emp, date(year, month, d))}
            day_map: dict[str, dict] = {}
            total_hours = 0.0
            total_days = 0
            total_leave = 0
            total_cong = 0.0
            total_ot = 0
            night_days = 0
            holiday_cong = 0.0   # công LÀM ngày lễ (Đ98 → premium)
            restday_cong = 0.0   # công LÀM ngày nghỉ tuần (Đ98 → premium)
            plain_cong = 0.0     # công LÀM ngày nghỉ 'off1x' — Lương trả 1× (KHÔNG hệ số), uncapped
            excused_cong = 0.0   # công THIẾU nhưng CÓ ĐƠN — chỉ nuôi chuyên cần, KHÔNG cộng vào công
            ot_holiday = 0       # phút OT ngày lễ
            ot_restday = 0       # phút OT ngày nghỉ tuần
            paid_leave = 0
            unpaid_leave = 0
            # Ngày phép LẺ do phiếu đi muộn/về sớm có tick "trừ phép" (nửa buổi = 0,5). Cộng chung
            # vào `paid_leave_days` để Lương trả theo lương vị trí như ngày phép nguyên ngày.
            paid_leave_cong = 0.0
            hanging = 0
            used_shift_ids: set[int] = set()
            late_off_days: list[int] = []   # số PHÚT vi phạm (trễ+sớm) mỗi ngày KHÔNG phép — nền phạt tự động
            # Phút tăng ca TỪNG NGÀY, tách theo LOẠI NGÀY — nền tính SUẤT CƠM TĂNG CA ở Lương.
            # Phải theo ngày chứ không gộp tháng: luật hỏi "ngày nào tăng ca ≥ ngưỡng", mà
            # `ot_minutes` tổng tháng không trả lời được câu đó.
            #   `lam`  = ngày LÀM VIỆC theo Lịch chung ⇒ phải đủ ngưỡng mới có suất
            #   `nghi` = ngày NGHỈ theo Lịch chung (gồm cả ngày lễ và off1x) ⇒ cứ tăng ca là có
            ot_days_lam: dict[int, int] = {}
            ot_days_nghi: dict[int, int] = {}
            night_premium_minutes = 0.0     # Σ (phút đêm TRONG ca × (hệ số ca − 1)) — premium giờ đêm
            ot_night_normal = 0; ot_night_restday = 0; ot_night_holiday = 0  # phút TĂNG CA ĐÊM theo loại ngày
            planned_off = planned_off_by_emp.get(emp_id, set())
            scheduled = scheduled_by_emp.get(emp_id, set())   # ngày XẾP TAY, chưa chấm → hiện ca
            # XEM TRƯỚC CA NGÀY CHƯA TỚI (chủ chốt 24/08/2026): "hiện ca lên các ngày chưa đến — để
            # xem ngày mai làm ca gì". Trải ca nền lên ngày LÀM VIỆC tương lai, KHÔNG lên ngày nghỉ
            # tuần: tuần chuẩn của chủ là T2–T7, Chủ nhật NGHỈ. Muốn làm Chủ nhật thì tô TAY từng ô
            # (tạo `EmployeeShiftDay` → vào nhánh `scheduled`, hiện bất kể lịch tuần).
            #   · CHỈ ngày >= hôm nay (VN): quá khứ không chấm = vắng, không phải "xem trước".
            #   · CHỈ ngày LÀM VIỆC (lịch tuần công ty) — Chủ nhật không trải ca nền lên.
            #   · Ngày đã có dòng phân ca (shift/off) để nhánh `scheduled`/`planned_off` lo.
            # `hist` = mốc ca nền của NV, nạp MỘT LẦN/NV (giống `shift_plan`) rồi resolve trong bộ
            # nhớ — đừng gọi `base_shift_id_on` mỗi ngày, kẻo lưới N NV × 31 ngày nổ hàng ngàn query.
            hist = self.employees.list_shift_assignments(emp_id)   # mốc giảm dần theo effective_from
            xem_truoc: set[int] = set()
            for dd in range(1, days_in_month + 1):
                the_d = date(year, month, dd)
                if the_d < today or (emp_id, the_d) in shift_day_map:
                    continue
                if (self._work_calendar is not None
                        and not self._work_calendar.is_working_day(the_d)):
                    continue                                       # Chủ nhật: nghỉ mặc định
                assign = next((h for h in hist if h.effective_from <= the_d), None)
                sid = (assign.shift_id if assign is not None
                       else (emp.default_shift_id if not hist else None))
                if sid is not None:
                    self._shift_id_cache[(emp_id, the_d)] = sid   # seed: khỏi query per-ngày
                    xem_truoc.add(dd)
            # Ngày CHỈ có đơn giờ (không chấm công) vẫn hiện ô để HCNS thấy — nó rơi vào nhánh
            # "không phép" bên dưới ⇒ KHÔNG công, KHÔNG tiền (đúng: xin nghỉ 2h mà vắng cả ngày).
            for d in sorted(set(att_days) | set(lv_days) | emp_holidays | planned_off
                            | scheduled | xem_truoc | set(hl_days)):
                cell = _empty_cell()
                main_out_min_kep = None
                shift = self._shift_for_day(emp, date(year, month, d), shifts)
                if shift is not None:
                    cell.update(shift_id=shift.id, shift_name=shift.name)
                    # Ngày CHỈ mới xếp ca (tương lai, chưa chấm/nghỉ/lễ) KHÔNG tính vào "ca đã làm"
                    # của tháng: nó chỉ hiện cho biết "mai làm ca nào". Để nó vào `used_shift_ids`
                    # thì summary nhảy "Nhiều ca" và `total_cong` ra 0 thay vì trống.
                    chi_xep_truoc = (d in (scheduled | xem_truoc) and d not in att_days
                                     and d not in lv_days and d not in emp_holidays)
                    if not chi_xep_truoc:
                        used_shift_ids.add(shift.id)
                if d in planned_off:
                    cell["planned_off"] = True
                if d in att_days:  # có chấm công → attendance thắng ngày nghỉ/lễ
                    entries = sorted(att_days[d], key=lambda x: x[0])
                    ins = [t for t, ct in entries if ct == CHECK_IN]
                    outs = [t for t, ct in entries if ct == CHECK_OUT]
                    first_in = ins[0] if ins else entries[0][0]
                    last_out = outs[-1] if outs else None
                    # Ghép PHIÊN: phiên 0 = ca chính (tính công theo giờ RA thực tế của nó); phiên 1.. =
                    # tăng ca (chấm riêng sau khi ra ca chính). Khe giữa 2 phiên (nghỉ giữa ca) không tính.
                    sessions = pair_sessions(entries)
                    main_out = sessions[0][1] if sessions else None
                    ot_in, ot_out = ((sessions[1][0], sessions[-1][1])
                                     if len(sessions) >= 2 else (None, None))
                    hours = None
                    if last_out is not None and last_out > first_in:
                        hours = round((last_out - first_in).total_seconds() / 3600, 2)
                        total_hours += hours
                    total_days += 1
                    if main_out is None:
                        hanging += 1  # thiếu chấm RA ca chính → ngày treo (cảnh báo trước khi Chốt)
                    cell.update(first_in=first_in.strftime("%H:%M"),
                                last_out=last_out.strftime("%H:%M") if last_out else None,
                                hours=hours, present=True)
                    if shift is not None:
                        wd_date = date(year, month, d)
                        # ── KẸP GIỜ RA THEO PHIẾU VỀ SỚM (chủ chốt 12/08/2026) ──────────────
                        # "Xin về 16h mà 17h mới bấm ra thì phải lấy 16h chứ." Đơn đã duyệt là
                        # CAM KẾT hai chiều: ngày đó tính đến giờ trên đơn.
                        #
                        # Hệ thống KHÔNG phân biệt được hai chuyện có dữ liệu y hệt nhau:
                        #   (A) về đúng 16h nhưng QUÊN BẤM, 17h mới bấm  → trước đây cộng dư 1h
                        #   (B) xin về 16h nhưng Ở LẠI LÀM tới 17h       → nay bị cắt 1h
                        # Chủ chốt chọn chịu sai ở (B): "kệ họ, họ có thể sửa công hoặc xoá phiếu
                        # tạo lại". Nên phải chừa đúng hai đường đó ra —
                        #   • xoá phiếu  → không còn phiếu thì không kẹp;
                        #   • sửa công   → lượt RA do HCNS CHẤM BÙ thì THẮNG phiếu (dưới đây).
                        # Chấm bù có lý do + tên người sửa; thợ quên bấm thì không có gì cả.
                        mo_ra = main_out
                        mo_offset = ((main_out.date() - wd_date).days if main_out else None)
                        if main_out is not None and main_out not in ra_bu_ngay.get(d, set()):
                            cuoi_ca = shift.end_minute + (1440 if shift.is_overnight else 0)
                            # Chỉ phiếu phủ tới CUỐI CA mới là "về sớm". Phiếu đi muộn (đầu ca)
                            # không đụng tới giờ ra.
                            moc = [f for f, t in hl_khung.get(d, []) if t >= cuoi_ca]
                            if moc:
                                kep = min(moc)
                                thuc = (main_out.hour * 60 + main_out.minute) + 1440 * (mo_offset or 0)
                                if thuc > kep:
                                    mo_offset, phut = divmod(kep, 1440)
                                    mo_ra = None
                                    main_out_min_kep = phut
                        info = compute_day_cong(
                            start_min=shift.start_minute, end_min=shift.end_minute,
                            is_overnight=shift.is_overnight, grace_min=shift.grace_minutes,
                            first_in_min=first_in.hour * 60 + first_in.minute,
                            main_out_min=(main_out_min_kep if mo_ra is None and main_out is not None
                                          else ((main_out.hour * 60 + main_out.minute)
                                                if main_out else None)),
                            # Lệch NGÀY THẬT giữa lượt chấm và ngày công (caller biết chắc từ datetime)
                            # → tăng ca / ca chính vượt nửa đêm tính đúng, không suy đoán theo đồng hồ.
                            in_day_offset=(first_in.date() - wd_date).days,
                            main_out_offset=mo_offset,
                            # Phiên TĂNG CA (cặp chấm riêng) — thiếu cặp ⇒ None ⇒ TC = 0 (bắt buộc 2 cặp).
                            ot_in_min=(ot_in.hour * 60 + ot_in.minute) if ot_in else None,
                            ot_out_min=(ot_out.hour * 60 + ot_out.minute) if ot_out else None,
                            ot_in_offset=((ot_in.date() - wd_date).days if ot_in else None),
                            ot_out_offset=((ot_out.date() - wd_date).days if ot_out else None),
                            # Phiếu tăng ca đã duyệt = TRẦN tiền TC; không có phiếu ⇒ (0,0) = 0 đ.
                            ot_window=(ot_map.get(emp.id, {}).get(d, (0, 0))
                                       if self.overtime is not None else None),
                        )
                        cell.update(cong=info["cong"], late=info["late"], early=info["early"],
                                    ot_minutes=info["ot_minutes"], night=False)
                        total_cong += info["cong"]
                        total_ot += info["ot_minutes"]
                        # night_days để dormant = 0 (đã gỡ cờ ca đêm; phụ cấp ca khai tay ở Lương).
                        # Đ98: phân loại công/OT theo LOẠI NGÀY (làm việc ngày lễ/nghỉ tuần → premium).
                        is_restday = (self._work_calendar is not None
                                      and not self._work_calendar.is_working_day(date(year, month, d)))
                        if info["ot_minutes"] > 0:
                            # `is_restday` chính là `not is_working_day` ⇒ ngày lễ và off1x cũng rơi
                            # vào nhánh `nghi`, đúng chốt của chủ 12/08/2026 ("theo lịch nghỉ").
                            (ot_days_nghi if is_restday else ot_days_lam)[d] = info["ot_minutes"]
                        if d in plain_days:
                            # Ngày 'off1x': làm chỉ 1× (KHÔNG hệ số). Loại khỏi BASE (total_cong) để Lương
                            # trả riêng uncapped, KHÔNG rơi vào premium lễ/nghỉ tuần.
                            plain_cong += info["cong"]
                            total_cong -= info["cong"]
                            cell["plain"] = True
                        elif d in paid_holidays:
                            holiday_cong += info["cong"]
                            ot_holiday += info["ot_minutes"]
                            cell["holiday"] = True
                        elif is_restday:
                            restday_cong += info["cong"]
                            ot_restday += info["ot_minutes"]
                            cell["restday"] = True
                        # Phạt trễ/sớm TỰ ĐỘNG: gom SỐ PHÚT vi phạm (trễ + về sớm) ngày này để payroll áp
                        # bảng phạt (mỗi ngày 1 lần). CHỈ khi KHÔNG có đơn phép duyệt phủ ngày đó (có phép →
                        # miễn) và KHÔNG phải ngày lễ. Ngày nghỉ tuần (CN): ×2 phút (khớp "Chủ nhật ×2" ở ô
                        # Tính nhanh). Ngày treo (quên chấm ra) vẫn tính phần đi trễ.
                        if d not in lv_days and d not in paid_holidays and d not in plain_days:
                            hl = int(hl_days.get(d, 0))     # số PHÚT đã xin nghỉ (đơn giờ đã duyệt)
                            off = int(info["late_minutes"]) + int(info["early_minutes"])
                            # Tha ĐÚNG phần đã xin, phần vắng vượt đơn vẫn phạt. Miễn sạch cả ngày
                            # thì ai cũng khai 5 phút để thoát mọi khoản phạt hôm đó.
                            off_net = max(0, off - hl)
                            if off_net > 0:
                                late_off_days.append(off_net * 2 if is_restday else off_net)
                            if hl > 0:
                                # Kẹp theo công thiếu THẬT: ngày làm đủ mà khai khống thì không đúc
                                # ra công ảo — phần dư sẽ âm thầm trả nợ cho một ngày vắng thật ở
                                # ngày khác (chuyên cần tính trên TỔNG tháng).
                                miss = int(info["missing_minutes"])
                                win = int(info["window_minutes"]) or 1
                                # So trên PHÚT vì `grace_minutes` làm `missing > late+early`.
                                gap = (max(0.0, 1.0 - float(info["cong"]))
                                       if hl >= miss else hl / win)
                                lv_cong = float(hl_leave.get(d, 0.0))
                                if lv_cong > 0:
                                    # CÓ TRỪ PHÉP: phần vắng được HOÀN công và trả theo lương vị trí.
                                    # Cộng vào cả `total_cong` lẫn `paid_leave` để `_luong_cong_split`
                                    # bên Lương tự trả đúng giá. KHÔNG sinh `excused_cong` ở nhánh này
                                    # — công đã hoàn thì chuyên cần tự đủ, bù thêm là BÙ HAI LẦN.
                                    take = min(lv_cong, gap)
                                    total_cong += take
                                    paid_leave_cong += take
                                    # Ô ngày phải hiện công ĐÃ hoàn, không thì lưới cộng tay ra
                                    # một số còn cột Tổng công ra số khác — HCNS mất niềm tin.
                                    cell["cong"] = round(float(cell["cong"]) + take, 2)
                                    cell["leave_cong"] = round(take, 2)
                                else:
                                    # KHÔNG trừ phép: mất công phần vắng, chỉ bù chuyên cần.
                                    excused_cong += gap
                        # Lương CA ĐÊM theo giờ: (A) giờ đêm TRONG ca × hệ số per-ca — CHỈ ca qua đêm;
                        # (B) TĂNG CA ĐÊM (giờ OT rơi 22h–06h) — MỌI ca, tách LOẠI NGÀY (engine áp hệ số luật).
                        if shift.is_overnight and int(info["night_minutes"]) > 0:
                            night_premium_minutes += int(info["night_minutes"]) * max(
                                0.0, float(getattr(shift, "night_multiplier", 1) or 1) - 1.0)
                            night_days += 1
                        onm = int(info["ot_night_minutes"])
                        if onm > 0:
                            if d in plain_days:      ot_night_normal += onm   # off1x → OT thường (không hệ số)
                            elif d in paid_holidays: ot_night_holiday += onm
                            elif is_restday:         ot_night_restday += onm
                            else:                    ot_night_normal += onm
                elif d in emp_holidays:  # NGÀY LỄ thắng đơn phép: 1 công lễ, KHÔNG tiêu ngày phép
                    lv = lv_days.get(d)   # đơn phép phủ ngày lễ (nếu có) → công lễ theo is_paid đơn
                    paid = lv["is_paid"] if lv is not None else True
                    cong = 1.0 if paid else 0.0   # nghỉ không lương phủ lễ → 0 công (đúng luật)
                    cell.update(cong=cong, leave=lv["name"] if lv is not None else paid_holidays[d],
                                leave_paid=paid, holiday=True)
                    total_cong += cong
                elif d not in lv_days:
                    # Ngày CHỈ mang dấu 'nghỉ theo lịch' HOẶC ngày đã XẾP CA nhưng chưa tới (tương
                    # lai): giữ ô để bảng công hiện ca / "nghỉ theo lịch" thay vì để trống giống
                    # vắng. Không công, không tiền — `cell.cong` vẫn None.
                    pass
                elif (self._work_calendar is not None
                      and not self._work_calendar.is_working_day(date(year, month, d))):
                    continue  # ngày nghỉ tuần (CN) trong đơn phép → không tiêu phép, không cộng công
                else:  # d in lv_days: ngày LÀM VIỆC có phép đã duyệt (không rơi lễ)
                    lv = lv_days[d]
                    cong = 1.0 if lv["is_paid"] else 0.0
                    cell.update(cong=cong, leave=lv["name"], leave_paid=lv["is_paid"])
                    total_leave += 1
                    if lv["is_paid"]:
                        paid_leave += 1
                    else:
                        unpaid_leave += 1
                    total_cong += cong
                day_map[str(d)] = cell

            # NGÀY THỰC LÀM theo từng CA — nền cho phụ cấp cơm / phụ cấp ca khai trên `work_shifts`.
            #
            # Ở đây CHỈ báo SỰ THẬT ("ca này làm mấy ngày, mỗi ngày được bao nhiêu công"), KHÔNG áp
            # ngưỡng: ngưỡng là CHÍNH SÁCH TRẢ TIỀN, tham số của nó nằm bên Lương. Chấm công mà tự
            # quyết ngày nào đáng tiền là đặt sai tầng, và đổi ngưỡng lại phải sửa hai chỗ.
            #
            # Chạy SAU khi `day_map` xong (không nhét vào 5 nhánh trên) vì `cell["cong"]` còn bị
            # cộng thêm ở nhánh hoàn công phép — đọc sớm là đọc số chưa chốt.
            ca_lam: dict[int, list[float]] = {}
            for c in day_map.values():
                sid = c.get("shift_id")
                if sid is None or not c.get("present"):
                    continue          # nghỉ phép / nghỉ lễ / không đi làm → không phải ngày làm ca
                ca_lam.setdefault(int(sid), []).append(round(float(c.get("cong") or 0), 2))

            summary_shift = shifts.get(next(iter(used_shift_ids))) if len(used_shift_ids) == 1 else None
            has_cong = bool(used_shift_ids) or total_leave > 0 or bool(emp_holidays)
            rows.append({
                "employee_id": emp_id, "employee_code": emp.code, "employee_name": emp.full_name,
                "department_id": emp.department_id, "days": day_map,
                "shift_id": summary_shift.id if summary_shift is not None else None,
                "shift_name": (summary_shift.name if summary_shift is not None
                               else "Nhiều ca" if len(used_shift_ids) > 1 else None),
                "total_days": total_days, "total_leave": total_leave,
                "paid_leave_days": round(paid_leave + paid_leave_cong, 2),
                "unpaid_leave_days": unpaid_leave,
                "holiday_days": len(emp_holidays), "ot_minutes": total_ot, "night_days": night_days,
                "holiday_cong": round(holiday_cong, 2), "restday_cong": round(restday_cong, 2),
                "plain_cong": round(plain_cong, 2),
                "excused_cong": round(excused_cong, 2),
                "ot_holiday_minutes": ot_holiday, "ot_restday_minutes": ot_restday,
                "hanging_days": hanging,
                "late_off_days": late_off_days,   # [số phút vi phạm mỗi ngày không phép] → payroll áp bảng phạt
                # {ngày → phút tăng ca}, tách ngày làm việc / ngày nghỉ → Lương tính suất cơm tăng ca.
                "ot_days": {"lam": ot_days_lam, "nghi": ot_days_nghi},
                # {ca → [công của từng ngày làm ca đó]} → Lương tính phụ cấp cơm / phụ cấp ca
                "ca_lam": ca_lam,
                "night_premium_minutes": round(night_premium_minutes, 2),   # Σ phút đêm × (hệ số−1) → premium giờ đêm
                "ot_night_normal_minutes": ot_night_normal,
                "ot_night_restday_minutes": ot_night_restday,
                "ot_night_holiday_minutes": ot_night_holiday,
                "total_hours": round(total_hours, 2),
                "total_cong": round(total_cong, 2) if has_cong else None,
            })
        rows.sort(key=lambda r: r["employee_code"])
        return {"year": year, "month": month, "days_in_month": days_in_month,
                "standard_cong": standard_cong, "holidays": holidays_info,
                # Hệ số theo LOẠI NGÀY (cấp tháng, không phải per-NV) → ô lịch tự ghi "→ tính N công".
                "he_so_ngay": self.he_so_ngay(), "rows": rows}

    def my_timesheet(self, *, user, year: int, month: int) -> dict:
        """Bảng công tháng CỦA CHÍNH NV đăng nhập (self-service, không cần quyền module).
        Tái dùng monthly_timesheet với chỉ hồ sơ NV của người gọi."""
        emp = self._employee_for_user(user)
        return self.monthly_timesheet(year=year, month=month, only_employee_id=emp.id)

    # --- Chốt công tháng (kỳ công + snapshot đóng băng) --------------------

    def list_periods(self):
        return self.attendance.list_periods()

    def get_or_create_period(self, year: int, month: int):
        p = self.attendance.get_period_by_ym(year, month)
        if p is None:
            p = self.attendance.create_period(year=year, month=month, status=APERIOD_DRAFT)
        return p

    def _pending_blockers(self, year: int, month: int) -> dict:
        """Đơn phép / chỉnh-công còn treo của tháng — guard thứ tự phép→công→lương (Q2)."""
        last = calendar.monthrange(year, month)[1]
        first, lastd = date(year, month, 1), date(year, month, last)
        pending_leaves = 0
        if self.leaves is not None:
            pending_leaves = len(self.leaves.list_overlapping(first, lastd, (LEAVE_PENDING,)))
        # Phiếu đi muộn/về sớm treo cũng phải chặn: duyệt SAU khi chốt thì snapshot không nhận
        # nữa ⇒ NLĐ vẫn ăn phạt + mất chuyên cần dù đã xin phép. Đếm RIÊNG (không gộp vào
        # `pending_leaves`) để thông điệp gọi đúng tên loại phiếu — gộp là bắt HCNS đi mò.
        pending_late_early = 0
        if self.late_early is not None:
            pending_late_early = self.late_early.count_pending_in_range(first, lastd)
        # Phiếu TĂNG CA treo — chặn từ 15/08/2026. Sót cái này là ngõ cụt: chốt xong thì duyệt
        # cũng không được nữa (L2), mà không duyệt thì không có tiền tăng ca; muốn gỡ phải mở lại
        # cả kỳ công. Cùng lý do đã áp cho ba loại trên, chỉ là hôm đó quên mất loại này.
        pending_overtime = 0
        if self.overtime is not None:
            pending_overtime = self.overtime.count_pending_in_range(first, lastd)
        return {"pending_leaves": pending_leaves,
                "pending_late_early": pending_late_early,
                "pending_overtime": pending_overtime,
                "pending_adjusts": self.attendance.count_pending_requests(
                    start=first, end=lastd)}

    def period_status(self, *, year: int, month: int) -> dict:
        if not (1 <= month <= 12):
            raise AttendanceValidationError("Tháng phải trong 1–12.")
        p = self.attendance.get_period_by_ym(year, month)
        blockers = self._pending_blockers(year, month)
        ts = self.monthly_timesheet(year=year, month=month)
        hanging = sum(r.get("hanging_days", 0) for r in ts["rows"])
        payroll_locked = False
        if self._payroll is not None:
            pp = self._payroll.get_period_by_ym(year, month)
            # Cùng luật với `reopen_period`: sót `paid` ở đây thì giao diện vẫn bày nút "Mở lại kỳ
            # công" cho kỳ đã chi, người dùng bấm vào mới ăn lỗi — đúng kiểu hai tầng nói khác nhau.
            payroll_locked = pp is not None and pp.status in PAYROLL_DA_KHOA
        return {
            "year": year, "month": month,
            "status": p.status if p is not None else APERIOD_DRAFT,
            "locked_at": p.locked_at if p is not None else None,
            "locked_by": p.locked_by if p is not None else None,
            "line_count": len(self.attendance.list_period_lines(p.id)) if p is not None else 0,
            "employee_count": len(ts["rows"]),
            "hanging_days": hanging,
            # L3 — kỳ ĐÃ CHỐT rồi mà vẫn có lượt bấm mới ghi vào. Chấm công GPS cố ý KHÔNG bị
            # chặn (chặn thợ bấm giờ là họ đứng ở cổng bấm mãi không xong, nhất là ca đêm qua nửa
            # đêm), nên phải ĐÁNH DẤU: ảnh chụp không có mấy lượt này, Bảng lương cũng không.
            "phat_sinh_sau_chot": self._dem_phat_sinh_sau_chot(p, year, month),
            "pending_leaves": blockers["pending_leaves"],
            "pending_late_early": blockers["pending_late_early"],
            "pending_overtime": blockers["pending_overtime"],
            "pending_adjusts": blockers["pending_adjusts"],
            "payroll_locked": payroll_locked,
        }

    def lock_period(self, *, year: int, month: int, actor) -> dict:
        """Chốt công: chụp Bảng công tháng thành snapshot đóng băng + khóa kỳ. CHẶN nếu còn
        đơn phép/chỉnh-công treo (Q2)."""
        if not (1 <= month <= 12):
            raise AttendanceValidationError("Tháng phải trong 1–12.")
        p = self.get_or_create_period(year, month)
        if p.status == APERIOD_LOCKED:
            raise AttendanceValidationError("Kỳ công đã chốt.")
        blockers = self._pending_blockers(year, month)
        if (blockers["pending_leaves"] or blockers["pending_adjusts"]
                or blockers["pending_late_early"] or blockers["pending_overtime"]):
            parts = []
            if blockers["pending_leaves"]:
                parts.append(f"{blockers['pending_leaves']} đơn nghỉ phép")
            if blockers["pending_late_early"]:
                parts.append(f"{blockers['pending_late_early']} phiếu đi muộn/về sớm")
            if blockers["pending_overtime"]:
                parts.append(f"{blockers['pending_overtime']} phiếu tăng ca")
            if blockers["pending_adjusts"]:
                parts.append(f"{blockers['pending_adjusts']} yêu cầu chỉnh công")
            raise AttendanceValidationError(
                f"Còn {' và '.join(parts)} chưa duyệt — duyệt hết trước khi chốt công."
            )
        ts = self.monthly_timesheet(year=year, month=month)
        # NGÀY TREO = bấm VÀO mà không có bấm RA. `period_status` vẫn đếm và trả về cho giao diện
        # từ lâu, nhưng chỗ QUYẾT ĐỊNH này lại không dùng tới — đếm để hiển thị rồi bỏ qua lúc
        # chốt là kiểu bẫy khó thấy nhất: nhìn màn thấy có cảnh báo, tưởng hệ thống đang canh.
        # Chốt khi còn ngày treo = ĐÓNG BĂNG LUÔN CÁI SAI: ngày đó vào ảnh chụp với 0 giờ, lương
        # trả thiếu, mà sau đó không sửa được nữa (`_require_period_open` khoá đường chấm bù).
        treo = sum(r.get("hanging_days", 0) for r in ts["rows"])
        if treo:
            raise AttendanceValidationError(
                f"Còn {treo} ngày treo (bấm VÀO nhưng thiếu bấm RA) — chấm bù cho đủ trước khi "
                "chốt công. Chốt bây giờ là đóng băng luôn số công thiếu, sau đó không sửa được."
            )
        self.attendance.delete_period_lines(p.id)
        for r in ts["rows"]:
            self.attendance.create_period_line(
                period_id=p.id, employee_id=r["employee_id"],
                total_cong=r["total_cong"] or 0, total_days=r["total_days"],
                total_leave=r["total_leave"], paid_leave_days=r.get("paid_leave_days", 0),
                unpaid_leave_days=r.get("unpaid_leave_days", 0), holiday_days=r.get("holiday_days", 0),
                total_hours=r["total_hours"], ot_minutes=r.get("ot_minutes", 0),
                night_days=r.get("night_days", 0),
                holiday_cong=r.get("holiday_cong", 0), restday_cong=r.get("restday_cong", 0),
                plain_cong=r.get("plain_cong", 0),
                excused_cong=r.get("excused_cong", 0),
                ot_holiday_minutes=r.get("ot_holiday_minutes", 0),
                ot_restday_minutes=r.get("ot_restday_minutes", 0),
                night_premium_minutes=r.get("night_premium_minutes", 0),
                ot_night_normal_minutes=r.get("ot_night_normal_minutes", 0),
                ot_night_restday_minutes=r.get("ot_night_restday_minutes", 0),
                ot_night_holiday_minutes=r.get("ot_night_holiday_minutes", 0),
                late_off_days_json=json.dumps(r.get("late_off_days") or []),
                ca_lam_json=json.dumps(r.get("ca_lam") or {}),
                ot_days_json=json.dumps(r.get("ot_days") or {"lam": {}, "nghi": {}}),
            )
        # CÔNG CHUẨN vào ảnh chụp cùng lúc với công từng người (15/08/2026). Đọc TRỰC TIẾP từ
        # lịch, KHÔNG gọi `self.standard_working_days` — hàm đó nay ưu tiên số đóng băng, mà lúc
        # này kỳ chưa chuyển sang locked nên nó vẫn trả số sống; gọi vòng chỉ thêm chỗ để sai sau
        # này nếu ai đó đổi thứ tự hai lệnh dưới đây.
        std = (self._work_calendar.standard_working_days(year, month)
               if self._work_calendar is not None else None)
        self.attendance.update_period(
            p, status=APERIOD_LOCKED, locked_at=datetime.now(timezone.utc),
            locked_by=getattr(actor, "id", None), updated_at=datetime.now(timezone.utc),
            standard_cong=(float(std) if std else None),
        )
        self.audit.create(actor_user_id=getattr(actor, "id", None), action="lock_attendance_period",
                          target=f"attendance_period:{p.id}", detail=f"{month}/{year} · {len(ts['rows'])} NV")
        return self.period_status(year=year, month=month)

    def reopen_period(self, *, year: int, month: int, actor) -> dict:
        """Mở lại kỳ công: xóa snapshot + về draft. CHẶN nếu kỳ LƯƠNG tháng đó đã chốt (Q3)."""
        if not (1 <= month <= 12):
            raise AttendanceValidationError("Tháng phải trong 1–12.")
        p = self.attendance.get_period_by_ym(year, month)
        if p is None or p.status != APERIOD_LOCKED:
            raise AttendanceValidationError("Kỳ công chưa chốt.")
        if self._payroll is not None:
            pp = self._payroll.get_period_by_ym(year, month)
            if pp is not None and pp.status in PAYROLL_DA_KHOA:
                da_chi = pp.status == PERIOD_PAID
                raise AttendanceValidationError(
                    ("Kỳ lương tháng này ĐÃ CHI — tiền đã phát, không mở lại kỳ công. "
                     if da_chi else
                     "Kỳ lương tháng này đã chốt — không mở lại kỳ công. ")
                    + "Điều chỉnh sai sót bằng truy lĩnh/khấu trừ kỳ sau."
                )
        self.attendance.delete_period_lines(p.id)
        # Xoá luôn công chuẩn đóng băng: mở lại kỳ là bỏ cả tấm ảnh, giữ lại một mảnh của ảnh cũ
        # thì lần chốt sau có thể ghi đè, nhưng khoảng giữa hai lần chốt lại đọc số đã lỗi thời.
        self.attendance.update_period(p, status=APERIOD_DRAFT, locked_at=None, locked_by=None,
                                      standard_cong=None,
                                      updated_at=datetime.now(timezone.utc))
        self.audit.create(actor_user_id=getattr(actor, "id", None), action="reopen_attendance_period",
                          target=f"attendance_period:{p.id}", detail=f"{month}/{year}")
        return self.period_status(year=year, month=month)

    def _dem_phat_sinh_sau_chot(self, p, year: int, month: int) -> int:
        """Số lượt bấm của tháng được GHI VÀO sau khi kỳ đã chốt. 0 nếu kỳ chưa chốt."""
        if p is None or p.status != APERIOD_LOCKED or p.locked_at is None:
            return 0
        # Cùng biên ±12h với `monthly_timesheet`: lượt RA rạng sáng ngày 1 tháng sau vẫn thuộc ca
        # VÀO của ngày cuối tháng này. Lệch biên là đếm sót đúng ca đêm — chỗ hay phát sinh nhất.
        start_vn = datetime(year, month, 1, tzinfo=VN_TZ)
        end_vn = (datetime(year + 1, 1, 1, tzinfo=VN_TZ) if month == 12
                  else datetime(year, month + 1, 1, tzinfo=VN_TZ))
        return self.attendance.count_logs_created_after(
            (start_vn - timedelta(hours=12)).astimezone(timezone.utc),
            (end_vn + timedelta(hours=12)).astimezone(timezone.utc),
            _as_utc(p.locked_at),
        )

    def so_luot_bam_sau_chot(self, year: int, month: int) -> int:
        """Cho LƯƠNG hỏi: tháng này đã chốt công rồi mà còn bao nhiêu lượt bấm ghi vào sau đó.

        Cùng con số dải cảnh báo màn Chấm công đang hiện (L3) — nhưng L3 chỉ NÓI, không CHẶN, mà
        nó nói ở màn Chấm công, trong khi người bấm chốt lương ngồi ở màn khác. Mở cửa công khai
        để `ly_do_chua_chot_duoc` chặn nốt đầu bên kia (L8)."""
        return self._dem_phat_sinh_sau_chot(
            self.attendance.get_period_by_ym(year, month), year, month
        )

    def ky_cong_chot_luc(self, year: int, month: int) -> datetime | None:
        """Thời điểm chốt kỳ công (UTC aware), None nếu chưa chốt.

        Lương so mốc này với `payroll_periods.generated_at` để biết bảng lương có đang là số tính
        TRƯỚC lúc đóng băng bảng công không. Trả AWARE vì SQLite đọc lại ra naive — so hai kiểu
        khác nhau là `TypeError` giữa lúc người ta đang bấm chốt lương."""
        p = self.attendance.get_period_by_ym(year, month)
        if p is None or p.status != APERIOD_LOCKED or p.locked_at is None:
            return None
        return _as_utc(p.locked_at)

    def ky_cong_da_chot(self, year: int, month: int) -> bool:
        """Kỳ công tháng này đã chốt chưa — cho Lương hỏi trước khi chốt bảng lương.

        CHƯA CÓ DÒNG KỲ = CHƯA CHỐT. Kỳ công chỉ sinh ra khi có người đụng tới tháng đó
        (`get_or_create_period`), nên tháng cũ của hệ thống hoàn toàn không có dòng nào."""
        p = self.attendance.get_period_by_ym(year, month)
        return p is not None and p.status == APERIOD_LOCKED

    def metrics_map(self, year: int, month: int) -> dict[int, dict]:
        """{emp_id → {cong, ot_minutes, night_days}} cho Lương (Pha 4a): đọc SNAPSHOT nếu kỳ
        công đã CHỐT; chưa chốt thì tính LIVE từ Bảng công tháng. Nguồn duy nhất — cong_map rút từ đây."""
        p = self.attendance.get_period_by_ym(year, month)
        if p is not None and p.status == APERIOD_LOCKED:
            return self.attendance.period_metrics_map(p.id)
        ts = self.monthly_timesheet(year=year, month=month)
        out: dict[int, dict] = {}
        for r in ts["rows"]:
            cong = r.get("total_cong")
            out[r["employee_id"]] = {
                # Không có ca thì các log cũ cũng không được quy đổi thành nguyên công.
                # Nghỉ hưởng lương/ngày lễ vẫn có total_cong riêng và đi qua nhánh `cong is not None`.
                "cong": float(cong if cong is not None else 0),
                "ot_minutes": int(r.get("ot_minutes") or 0),
                "night_days": int(r.get("night_days") or 0),
                "holiday_cong": float(r.get("holiday_cong") or 0),
                "restday_cong": float(r.get("restday_cong") or 0),
                "plain_cong": float(r.get("plain_cong") or 0),
                # Nghỉ theo giờ có đơn: giữ chuyên cần. Ngày phép có lương: Lương trả theo
                # lương vị trí. CẢ HAI phải có ở NHÁNH SNAPSHOT nữa, không thì số nhảy lúc chốt công.
                "excused_cong": float(r.get("excused_cong") or 0),
                # FLOAT: nửa buổi có trừ phép = 0,5 ngày. Ép int là người lao động MẤT TIỀN.
                "paid_leave_days": float(r.get("paid_leave_days") or 0),
                "ot_holiday_minutes": int(r.get("ot_holiday_minutes") or 0),
                "ot_restday_minutes": int(r.get("ot_restday_minutes") or 0),
                "late_off_days": [int(x) for x in (r.get("late_off_days") or [])],
                # {ca → [công từng ngày]}. PHẢI có ở CẢ nhánh snapshot bên dưới, không thì phụ cấp
                # ca/cơm NHẢY SỐ đúng lúc chốt công — lỗi đã gặp với `excused_cong`/`paid_leave_days`.
                "ca_lam": {int(k): [float(x) for x in v] for k, v in (r.get("ca_lam") or {}).items()},
                # {"lam"/"nghi": {ngày: phút}} — nền tính suất cơm tăng ca. PHẢI có ở CẢ nhánh
                # ảnh chụp bên dưới, không thì tiền cơm NHẢY SỐ đúng lúc chốt công (đã dính hai
                # lần với `excused_cong` / `paid_leave_days` / `ca_lam`).
                "ot_days": _chuan_ot_days(r.get("ot_days")),
                "night_premium_minutes": float(r.get("night_premium_minutes") or 0),
                "ot_night_normal_minutes": int(r.get("ot_night_normal_minutes") or 0),
                "ot_night_restday_minutes": int(r.get("ot_night_restday_minutes") or 0),
                "ot_night_holiday_minutes": int(r.get("ot_night_holiday_minutes") or 0),
            }
        return out

    def cong_map(self, year: int, month: int) -> dict[int, float]:
        """Số công/NV cho Lương (giữ tương thích) — rút cong từ metrics_map (1 nguồn)."""
        return {eid: m["cong"] for eid, m in self.metrics_map(year, month).items()}

    def standard_working_days(self, year: int, month: int) -> int | None:
        """Công chuẩn ĐỘNG của tháng (số ngày làm việc thực theo Lịch chung — Đ3/N4) cho Lương.
        None nếu chưa cấu hình lịch → Lương fallback về `standard_cong_default`.

        KỲ ĐÃ CHỐT thì trả số ĐÓNG BĂNG lúc chốt, không tính lại theo lịch hiện tại. Cùng lối rẽ
        nhánh với `metrics_map`: chốt công là chụp ảnh, và mẫu số của đơn giá ngày cũng thuộc về
        tấm ảnh đó. Không có nó thì công ty bỏ làm thứ Bảy hôm nay là đơn giá ngày của MỌI THÁNG
        CŨ đổi theo, tính lại tháng nào ra tiền tháng đó.

        Kỳ chốt TRƯỚC bản vá 15/08/2026 chưa có số đóng băng (NULL) ⇒ rơi về đọc lịch sống như
        cũ. Cố ý: bịa một con số cho quá khứ còn tệ hơn."""
        p = self.attendance.get_period_by_ym(year, month)
        if (p is not None and p.status == APERIOD_LOCKED
                and getattr(p, "standard_cong", None)):
            return float(p.standard_cong)
        if self._work_calendar is None:
            return None
        return self._work_calendar.standard_working_days(year, month)

    # --- lưới phân ca theo tháng (khai ca NV × ngày) ------------------------

    def shift_plan(self, *, year: int, month: int, department_id: int | None = None,
                   scope=None, actor=None) -> dict:
        """Lưới phân ca tháng: mỗi ô cho biết ca của (NV, ngày) và ca đó ĐẾN TỪ ĐÂU.

        `source`: `day` = khai tay trên lưới · `assign` = mốc ca mặc định ·
        `default` = cache `default_shift_id` (NV chưa có mốc nào) · `none` = chưa
        có ca. Ô `off` = nghỉ theo lịch (khai tay, không ra tiền)."""
        if not (1 <= month <= 12):
            raise AttendanceValidationError("Tháng phải trong khoảng 1–12.")
        days_in_month = calendar.monthrange(year, month)[1]
        emps = self._employees_in_month(year, month, department_id, scope, actor)
        day_map = self.employees.shift_days_map(
            {e.id for e in emps}, date(year, month, 1), date(year, month, days_in_month)
        )

        specials: dict[date, object] = {}
        if self._work_calendar is not None:
            specials = {s.day: s for s in self._work_calendar.list_special_days(year)}

        cal_days = []
        for d in range(1, days_in_month + 1):
            the_day = date(year, month, d)
            sp = specials.get(the_day)
            working = True
            if self._work_calendar is not None:
                working = self._work_calendar.is_working_day(the_day)
            cal_days.append({
                "day": d, "date": the_day.isoformat(), "weekday": the_day.weekday(),
                "is_working": working,
                "special_kind": sp.kind if sp is not None else None,
                "name": sp.name if sp is not None else None,
            })

        # Ngày nghỉ phép ĐÃ DUYỆT — chỉ để HIỂN THỊ.
        #
        # Chốt chống rò dữ liệu KHÔNG nằm ở tham số lọc này mà ở chỗ khác: lớp phủ bên dưới chỉ dán
        # dấu cho `e` trong `emps`, mà `emps` đã qua `_employees_in_month` (áp `scope` +
        # `department_id`). Nên người ngoài tầm nhìn không có DÒNG nào trên lưới để mà dán.
        # Truyền tập id vào đây là để KHỎI DỰNG map thừa cho cả công ty — tiết kiệm, không phải
        # hàng rào. Đừng nhầm hai vai trò đó: gỡ dòng này không làm rò, nhưng gỡ nhầm bộ lọc ở
        # `_employees_in_month` thì rò thật.
        leave_map = self._leave_map(year, month, {e.id for e in emps})

        rows = []
        for e in emps:
            # Cả LỊCH SỬ MỐC của NV, 1 query (đã sort effective_from giảm dần). Dùng lại
            # cho mọi ngày thay vì hỏi DB từng ngày, và để biết NV có mốc nào chưa.
            hist = self.employees.list_shift_assignments(e.id)
            days: dict[str, dict] = {}
            for d in range(1, days_in_month + 1):
                the_day = date(year, month, d)
                cell = day_map.get((e.id, the_day))
                if cell is not None and cell.is_off:
                    days[str(d)] = {"shift_id": None, "source": "day", "is_off": True}
                    continue
                if cell is not None and cell.shift_id is not None:
                    days[str(d)] = {"shift_id": cell.shift_id, "source": "day", "is_off": False}
                    continue
                assign = next((h for h in hist if h.effective_from <= the_day), None)
                if assign is not None:
                    days[str(d)] = {"shift_id": assign.shift_id, "is_off": False,
                                    "source": "assign" if assign.shift_id is not None else "none"}
                elif not hist and e.default_shift_id is not None:
                    # `default_shift_id` CHỈ là nguồn khi NV chưa có mốc nào — đúng như
                    # `shift_id_on`. Trước đây lưới rơi về nó cả khi đã có mốc, nên NHỮNG
                    # NGÀY TRƯỚC MỐC ĐẦU TIÊN bị vẽ ra một ca mà engine không hề công nhận:
                    # màn hình báo có ca, thực tế NV không chấm công được.
                    days[str(d)] = {"shift_id": e.default_shift_id, "source": "default",
                                    "is_off": False}
                else:
                    days[str(d)] = {"shift_id": None, "source": "none", "is_off": False}

            # LỚP PHỦ nghỉ phép — dán SAU khi ô đã dựng xong, cố ý tách hẳn khỏi 5 nhánh trên.
            # Nhờ đặt ở đây mà tính chất "chỉ để XEM" là hiển nhiên khi đọc code: nó KHÔNG đụng
            # `shift_id` / `source` / `is_off`, và KHÔNG ghi gì xuống DB. Người nghỉ phép vẫn
            # ĐƯỢC PHÂN ca đó — chỉ là vắng mặt.
            for ngay, lv in (leave_map.get(e.id) or {}).items():
                o = days.get(str(ngay))
                if o is not None:
                    o["leave_name"] = lv["name"]
                    o["leave_paid"] = lv["is_paid"]

            rows.append({
                "employee_id": e.id, "employee_code": e.code, "employee_name": e.full_name,
                "department_id": e.department_id,
                "no_default": all(v["shift_id"] is None and not v["is_off"] for v in days.values()),
                "days": days,
            })

        p = self.attendance.get_period_by_ym(year, month)
        return {
            "year": year, "month": month, "days_in_month": days_in_month,
            "locked": p is not None and p.status == APERIOD_LOCKED,
            "calendar": cal_days,
            "shifts": self.attendance.list_shifts(),
            "rows": rows,
        }

    def set_shift_plan(self, *, year: int, month: int, cells: list[dict], scope=None,
                       actor=None) -> dict:
        """Ghi hàng loạt ô lưới. `action`: `set` (gán ca) · `off` (nghỉ theo lịch) ·
        `inherit` (xóa ô → về ca mặc định).

        Một transaction, commit MỘT lần ở cuối. Ô không hợp lệ đi vào `rejected`
        KÈM LÝ DO — không bỏ qua im lặng (mất dữ liệu không dấu vết là kiểu lỗi
        khó lần nhất)."""
        if not (1 <= month <= 12):
            raise AttendanceValidationError("Tháng phải trong khoảng 1–12.")
        p = self.attendance.get_period_by_ym(year, month)
        if p is not None and p.status == APERIOD_LOCKED:
            raise AttendanceValidationError(
                f"Kỳ công {month}/{year} đã chốt — mở lại kỳ công trước khi sửa ca."
            )
        allowed = self._allowed_employee_ids(scope, actor)
        shifts = {s.id: s for s in self.attendance.list_shifts()}
        emp_cache: dict[int, object] = {}
        actor_id = getattr(actor, "id", None)
        today = _today_vn()   # mốc khoá quá khứ (giờ VN) — chủ chốt: "cứ quá khứ là không đổi ca nữa"

        saved = cleared = 0
        rejected: list[dict] = []
        # Dòng lịch sử vừa ghi — dùng để đẩy thông báo SAU commit và đếm "chưa báo được".
        logs: list = []

        def _reject(c, reason):
            rejected.append({"employee_id": c.get("employee_id"),
                             "date": str(c.get("work_date")), "reason": reason})

        def _log(emp, wd, action, *, shift_after=None, is_off_after=False):
            """Chụp trạng thái TRƯỚC rồi ghi một dòng lịch sử.

            Phải gọi TRƯỚC khi upsert/delete — sau đó thì giá trị cũ đã bị ghi đè mất."""
            day = self.employees.shift_day_on(emp.id, wd)
            inherited = day is None
            log = self.employees.log_shift_change(
                employee_id=emp.id, kind=SHIFT_LOG_KIND_DAY,
                origin=SHIFT_LOG_ORIGIN_GRID, action=action, apply_date=wd,
                # Chưa khai tay ngày này ⇒ ca đang hiệu lực là CA NỀN; resolve qua seam
                # `shift_id_on` thay vì tự dò lại (một nguồn sự thật duy nhất).
                shift_id_before=(self.employees.shift_id_on(emp, wd) if inherited
                                 else day.shift_id),
                shift_id_after=shift_after,
                is_off_before=(False if inherited else bool(day.is_off)),
                is_off_after=is_off_after,
                inherited_before=inherited,
                actor_user_id=actor_id,
                notified_user_id=getattr(emp, "user_id", None),
            )
            if log is not None:
                logs.append(log)

        for c in cells:
            emp_id, wd, action = c["employee_id"], c["work_date"], c["action"]
            if wd.year != year or wd.month != month:
                _reject(c, f"Ngày {wd.isoformat()} không thuộc tháng {month}/{year}.")
                continue
            if allowed is not None and emp_id not in allowed:
                _reject(c, "Ngoài phạm vi quản lý của bạn.")
                continue
            if emp_id not in emp_cache:
                emp_cache[emp_id] = self.employees.get_by_id(emp_id)
            emp = emp_cache[emp_id]
            if emp is None:
                _reject(c, "Không tìm thấy nhân viên.")
                continue
            if not _in_headcount_on(emp, wd):
                _reject(c, "Ngày này nhân viên chưa vào làm hoặc đã nghỉ việc.")
                continue
            # ⭐ KHOÁ NGÀY QUÁ KHỨ (chủ chốt 24/08/2026 — "lỗi chí mạng", chủ chốt lại: "quá khứ rồi
            # thì không cho sửa nữa"): gán một loạt 1–30 mà đè lên ngày đã chấm công / đang chờ đơn
            # thì công quá khứ bị TÍNH LẠI theo ca mới, sai âm thầm. Đơn giản nhất: ngày < HÔM NAY
            # thì KHÔNG cho đổi ca. Đây là hàng rào TẦNG DỮ LIỆU — bút hay loạt hay gọi thẳng API
            # đều dính. (Giao diện còn chặn thêm: kéo loạt tự bỏ ngày quá khứ, không sinh reject.)
            # ⭐ KHOÁ QUÁ KHỨ (chủ chốt 24/08/2026 — "lỗi chí mạng"; chốt B: "cứ quá khứ là không
            # cho đổi ca nữa"): ngày < HÔM NAY thì không set/off/inherit được — kể cả tháng cũ chưa
            # chốt. Đổi ca ngày đã qua ⇒ tính lại công quá khứ (đã chấm / chờ đơn) theo ca mới, sai
            # âm thầm. Hàng rào TẦNG DỮ LIỆU: bút · loạt · gọi thẳng API đều dính.
            if wd < today:
                _reject(c, "Ngày đã qua — không sửa ca được nữa. Chỉ đổi được ca từ hôm nay trở đi.")
                continue
            if action == "inherit":
                # Ô về kế thừa ca nền: ca SAU chính là ca nền đang hiệu lực ngày đó.
                _log(emp, wd, SHIFT_LOG_ACTION_INHERIT,
                     shift_after=self.employees.base_shift_id_on(emp, wd))
                if self.employees.delete_shift_day(emp_id, wd):
                    cleared += 1
                continue
            if action == "off":
                _log(emp, wd, SHIFT_LOG_ACTION_OFF, shift_after=None, is_off_after=True)
                self.employees.upsert_shift_day(employee_id=emp_id, work_date=wd, shift_id=None,
                                                is_off=True, created_by=actor_id)
                saved += 1
                continue
            shift = shifts.get(c.get("shift_id"))
            if shift is None:
                _reject(c, "Ca không tồn tại.")
                continue
            if not shift.is_active:
                _reject(c, f"Ca '{shift.name}' đã ngừng sử dụng.")
                continue
            _log(emp, wd, SHIFT_LOG_ACTION_SET, shift_after=shift.id)
            self.employees.upsert_shift_day(employee_id=emp_id, work_date=wd, shift_id=shift.id,
                                            is_off=False, created_by=actor_id)
            saved += 1

        self.employees.commit()
        # Cache resolve ca sống theo request: ghi xong mà không dọn thì lần đọc sau
        # trong CÙNG request sẽ trả số cũ.
        self._shift_id_cache.clear()
        self.audit.create(
            actor_user_id=actor_id, action="set_shift_plan",
            target=f"attendance_shift_plan:{year}-{month:02d}",
            detail=f"{saved} ô khai, {cleared} ô về mặc định, {len(rejected)} ô bị từ chối",
        )
        notified, not_notified = _push_shift_changes(logs)
        return {"saved": saved, "cleared": cleared, "rejected": rejected,
                "changed": len(logs), "notified": notified, "not_notified": not_notified}

    # --- "ô biết nói": chi tiết 1 ngày + điều chỉnh punch nguồn -------------

    def _employee_in_scope(self, employee_id: int, scope, actor):
        allowed = self._allowed_employee_ids(scope, actor)
        if allowed is not None and employee_id not in allowed:
            raise AttendanceNotFound("Nhân viên ngoài phạm vi của bạn.")
        emp = self.employees.get_by_id(employee_id)
        if emp is None:
            raise AttendanceNotFound("Không tìm thấy nhân viên.")
        return emp

    @staticmethod
    def _parse_ymd(date_str: str) -> date:
        try:
            y, m, d = (int(x) for x in str(date_str).split("-"))
            return date(y, m, d)
        except (ValueError, AttributeError):
            raise AttendanceValidationError("Ngày phải dạng YYYY-MM-DD.")

    def _day_punches(self, emp, shift, the_day: date) -> list:
        """Các punch thuộc NGÀY CÔNG `the_day` (giờ VN, gồm gộp ca đêm), cũ→mới."""
        start = datetime(the_day.year, the_day.month, the_day.day, tzinfo=VN_TZ).astimezone(timezone.utc)
        end = (datetime(the_day.year, the_day.month, the_day.day, tzinfo=VN_TZ)
               + timedelta(days=1, hours=12)).astimezone(timezone.utc)
        out = []
        for lg in self.attendance.list_by_employee_in_range(emp.id, start, end):
            local = _as_utc(lg.checked_at).astimezone(VN_TZ)
            if work_day_of(local, shift) == the_day:
                out.append((local, lg))
        out.sort(key=lambda x: x[0])
        return out

    def _khung_tra_cong_utc(self, employee, shift, work_day: date) -> list[tuple[datetime, datetime]]:
        """Khung 'được trả công' của NGÀY CÔNG (mốc UTC): cửa sổ CA THƯỜNG + cửa sổ PHIẾU TĂNG CA
        đã duyệt (§7.3 'ngoài ca thường'). Phút-từ-nửa-đêm (giờ VN) → mốc tuyệt đối, cộng qua nửa
        đêm cho ca đêm / phiếu TC vượt ngày (to_minute > 1440)."""
        nua_dem = datetime(work_day.year, work_day.month, work_day.day, tzinfo=VN_TZ)
        khung: list[tuple[datetime, datetime]] = []
        if shift is not None:
            s0 = nua_dem + timedelta(minutes=shift.start_minute)
            s1 = nua_dem + timedelta(minutes=shift.end_minute + (1440 if shift.is_overnight else 0))
            khung.append((s0.astimezone(timezone.utc), s1.astimezone(timezone.utc)))
        otw = self._ot_window_on(employee, work_day)
        if otw is not None and otw[1] > otw[0]:
            o0 = nua_dem + timedelta(minutes=int(otw[0]))
            o1 = nua_dem + timedelta(minutes=int(otw[1]))
            khung.append((o0.astimezone(timezone.utc), o1.astimezone(timezone.utc)))
        return khung

    def khoang_co_mat_hop_le(
        self, employee, start_utc: datetime, end_utc: datetime,
    ) -> list[tuple[datetime, datetime]]:
        """§7.3 — các KHOẢNG CÓ MẶT HỢP LỆ (UTC-aware, KHÔNG chồng lấn) của NV trong [start,end):
        giao của (các cặp chấm công IN/OUT thực tế) với (TRONG CA THƯỜNG ∪ PHIẾU TĂNG CA ĐÃ DUYỆT).
        Phút THÔ — không grace, không làm tròn. Ca qua đêm gom vào ngày VÀO ca (`work_day_of`).

        Dùng nuôi lương khoán (§12.2): engine phân bổ lấy phút = giao(khoảng THAM GIA, khoảng này).
        NV chưa gán ca + không có phiếu TC ⇒ khung trả công rỗng ⇒ trả [] (⇒ đánh 'thiếu chấm công')."""
        start_utc, end_utc = _as_utc(start_utc), _as_utc(end_utc)
        if employee is None or end_utc <= start_utc:
            return []
        # Nới ±1 ngày quanh biên để ôm ca đêm gom về ngày vào ca.
        d = start_utc.astimezone(VN_TZ).date() - timedelta(days=1)
        d_het = end_utc.astimezone(VN_TZ).date() + timedelta(days=1)
        manh: list[tuple[datetime, datetime]] = []
        while d <= d_het:
            shift = self._shift_for_day(employee, d)
            punches = self._day_punches(employee, shift, d)
            sessions = pair_sessions([(lc, lg.check_type) for lc, lg in punches])
            if sessions:
                khung = self._khung_tra_cong_utc(employee, shift, d)
                for s_in, s_out in sessions:
                    a0 = s_in.astimezone(timezone.utc)
                    a1 = s_out.astimezone(timezone.utc)
                    for w0, w1 in khung:
                        lo, hi = max(a0, w0), min(a1, w1)
                        if hi > lo:
                            manh.append((lo, hi))
            d += timedelta(days=1)
        return _gop_khoang(manh, start_utc, end_utc)

    def day_detail(self, *, scope, actor, employee_id: int, date_str: str) -> dict:
        """'Ô biết nói': punch thật của 1 NV trong 1 ngày + công tính lại + lý do."""
        emp = self._employee_in_scope(employee_id, scope, actor)
        the_day = self._parse_ymd(date_str)
        shift = self._shift_for_day(emp, the_day)
        punches = self._day_punches(emp, shift, the_day)
        ins = [lc for lc, lg in punches if lg.check_type == CHECK_IN]
        outs = [lc for lc, lg in punches if lg.check_type == CHECK_OUT]
        first_in = ins[0] if ins else (punches[0][0] if punches else None)
        last_out = outs[-1] if outs else None
        # Ghép phiên: phiên 0 = ca chính (tính công), phiên 1.. = tăng ca (cặp chấm riêng).
        sessions = pair_sessions([(lc, lg.check_type) for lc, lg in punches])
        main_out = sessions[0][1] if sessions else None
        ot_in, ot_out = ((sessions[1][0], sessions[-1][1]) if len(sessions) >= 2 else (None, None))
        cong = reason = None
        if shift is not None and first_in is not None:
            info = compute_day_cong(
                start_min=shift.start_minute, end_min=shift.end_minute,
                is_overnight=shift.is_overnight, grace_min=shift.grace_minutes,
                first_in_min=first_in.hour * 60 + first_in.minute,
                main_out_min=(main_out.hour * 60 + main_out.minute) if main_out else None,
                in_day_offset=(first_in.date() - the_day).days,
                main_out_offset=((main_out.date() - the_day).days if main_out else None),
                ot_in_min=(ot_in.hour * 60 + ot_in.minute) if ot_in else None,
                ot_out_min=(ot_out.hour * 60 + ot_out.minute) if ot_out else None,
                ot_in_offset=((ot_in.date() - the_day).days if ot_in else None),
                ot_out_offset=((ot_out.date() - the_day).days if ot_out else None),
                ot_window=self._ot_window_on(emp, the_day),
            )
            cong = info["cong"]
            if info["incomplete"]:
                reason = "Chưa chấm RA ca chính"
            elif info["cong"] < 1.0:
                reason = ("Vào trễ và về sớm" if info["late"] and info["early"]
                          else "Vào trễ quá dung sai" if info["late"]
                          else "Về sớm" if info["early"] else None)
        elif shift is None:
            reason = "Chưa gán ca làm việc"
        # Gợi ý chấm bù CẶP TĂNG CA: có phiếu TC đã duyệt (trong ngày) + đã xong ca chính nhưng CHƯA có
        # phiên tăng ca (thiếu cặp chấm) → HCNS bấm 1 nút điền sẵn khung phiếu. Phiếu qua nửa đêm
        # (to > 1440) bỏ gợi ý (ô giờ HH:MM 1 ngày không biểu diễn được lượt RA hôm sau).
        ot_suggestion = None
        otw = self._ot_window_on(emp, the_day)
        if otw is not None and len(sessions) == 1 and otw[1] <= 1440:
            ot_suggestion = {"from_time": min_to_hhmm(otw[0]), "to_time": min_to_hhmm(otw[1] % 1440)}
        return {
            "employee_id": emp.id, "employee_name": emp.full_name, "date": date_str,
            "shift_name": shift.name if shift is not None else None,
            "cong": cong, "reason": reason, "ot_suggestion": ot_suggestion,
            "punches": [{
                "id": lg.id, "time": lc.strftime("%H:%M"), "check_type": lg.check_type,
                "is_manual": lg.is_manual, "adjust_reason": lg.adjust_reason,
                "fault_party": lg.fault_party, "distance_m": float(lg.distance_m) if lg.distance_m is not None else None,
            } for lc, lg in punches],
        }

    def _create_manual_punch(self, *, actor, emp, the_day: date, check_type: str,
                             time_hhmm: str, reason: str, fault_party: str | None):
        """Tạo 1 punch điều chỉnh tay (dùng chung cho chấm bù trực tiếp & duyệt YC)."""
        self._require_period_open(the_day, "chấm bù")
        self._require_shift_on_day(emp, the_day)
        if check_type not in CHECK_TYPES:
            raise AttendanceValidationError("Loại chấm phải là VÀO hoặc RA.")
        reason = (reason or "").strip()
        if not reason:
            raise AttendanceValidationError("Phải nhập lý do điều chỉnh.")
        if fault_party is not None and fault_party not in FAULT_PARTIES:
            raise AttendanceValidationError("Nguyên nhân không hợp lệ.")
        hh, mm = divmod(_hhmm_to_min(time_hhmm), 60)
        when_utc = datetime(the_day.year, the_day.month, the_day.day, hh, mm, tzinfo=VN_TZ).astimezone(timezone.utc)
        log = self.attendance.create_log(
            employee_id=emp.id, work_location_id=None, check_type=check_type,
            checked_at=when_utc, within_range=True, is_manual=True,
            adjust_reason=reason, fault_party=fault_party, created_by_user_id=actor.id,
        )
        self.audit.create(
            actor_user_id=actor.id, action="adjust_attendance",
            target=f"attendance_log:{log.id}",
            detail=f"{emp.code} {the_day.isoformat()} {time_hhmm} {check_type} ({fault_party or '-'}): {reason}",
        )
        return log

    def _require_period_open(self, the_day: date, what: str) -> None:
        """Chặn sửa punch của kỳ công ĐÃ CHỐT.

        Chốt công là ĐÓNG BĂNG snapshot; Lương đọc snapshot chứ không đọc bảng công live
        (`metrics_map` rẽ nhánh khi kỳ locked). Cho chấm bù vào tháng đã chốt thì màn Chấm công
        đổi số mà phiếu lương KHÔNG đổi — hai bên lệch nhau âm thầm, không ai thấy.
        Cùng một luật `set_shift_plan` đã áp cho đường sửa CA."""
        p = self.attendance.get_period_by_ym(the_day.year, the_day.month)
        if p is not None and p.status == APERIOD_LOCKED:
            raise AttendanceValidationError(
                f"Kỳ công {the_day.month}/{the_day.year} đã chốt — mở lại kỳ công trước khi {what}."
            )

    def _require_not_future(self, the_day: date, what: str) -> None:
        """Chặn ghi nhận chấm công cho ngày CHƯA TỚI.

        Chấm công là ghi nhận việc ĐÃ XẢY RA — không ai quên chấm một ngày chưa đến. Trước
        31/07/2026 không có chốt này ở đâu cả (chủ phát hiện: ngày 31/7 vẫn gửi được yêu cầu
        chỉnh công cho 02/8). Hai đường phải chặn:
        · Đơn chỉnh công của NV — đơn tương lai vẫn ĂN HẠN MỨC tháng đó (`adjust_quota` đếm cả đơn
          chờ), nên NV tự đốt sạch hạn mức tháng sau bằng những ngày chưa tới.
        · Chấm bù tay của HCNS — nặng hơn: punch tương lai RA CÔNG THẬT khi tới ngày.

        HÔM NAY vẫn cho (quên chấm sáng nay, chiều xin sửa là chuyện thường) — chỉ chặn `>`.
        Ngày theo giờ **VN** chứ không giờ máy chủ: lệch múi giờ là cuối ngày chặn nhầm cả ngày
        hợp lệ (cùng lý do `my_requests` lấy hôm nay theo VN_TZ)."""
        if the_day > _today_vn():
            raise AttendanceValidationError(
                f"Không thể {what} cho ngày chưa tới ({the_day.strftime('%d/%m/%Y')})."
            )

    def adjust(self, *, actor, scope, employee_id: int, date_str: str, check_type: str,
               time_hhmm: str, reason: str, fault_party: str | None) -> dict:
        """HCNS thêm 1 PUNCH điều chỉnh tay (chấm bù/sửa) — công tự tính lại từ punch.
        KHÔNG ghi đè số công. Bắt buộc lý do; ghi audit + người thực hiện."""
        emp = self._employee_in_scope(employee_id, scope, actor)
        the_day = self._parse_ymd(date_str)
        self._require_not_future(the_day, "chấm bù")
        self._create_manual_punch(actor=actor, emp=emp, the_day=the_day,
                                  check_type=check_type, time_hhmm=time_hhmm, reason=reason,
                                  fault_party=fault_party)
        return self.day_detail(scope=scope, actor=actor, employee_id=emp.id, date_str=date_str)

    def delete_manual(self, *, actor, scope, log_id: int, date_str: str, employee_id: int) -> dict:
        """Xóa 1 punch ĐIỀU CHỈNH TAY (chỉ manual, trong phạm vi) — hoàn tác chấm bù."""
        log = self.attendance.get_log(log_id)
        if log is None:
            raise AttendanceNotFound("Không tìm thấy bản ghi chấm công.")
        if not log.is_manual:
            raise AttendanceValidationError("Chỉ được xóa punch điều chỉnh tay (không xóa chấm GPS gốc).")
        self._require_period_open(
            _as_utc(log.checked_at).astimezone(VN_TZ).date(), "xóa punch chấm bù")
        self._employee_in_scope(log.employee_id, scope, actor)
        self.attendance.delete_log(log)
        self.audit.create(
            actor_user_id=actor.id, action="delete_manual_attendance",
            target=f"attendance_log:{log_id}", detail=f"xóa punch bù #{log_id}",
        )
        return self.day_detail(scope=scope, actor=actor, employee_id=employee_id, date_str=date_str)

    # --- yêu cầu chỉnh công (NV gửi → HCNS duyệt) --------------------------

    @staticmethod
    def _req_out(r, emp_name: str | None = None, decider_name: str | None = None) -> dict:
        return {
            "id": r.id, "employee_id": r.employee_id, "employee_name": emp_name,
            "work_date": r.work_date.isoformat(), "check_type": r.check_type,
            "suggested_time": r.suggested_time, "reason": r.reason, "fault_party": r.fault_party,
            "status": r.status, "decided_at": r.decided_at, "decision_note": r.decision_note,
            "decided_by_name": decider_name,
        }

    def adjust_quota(self, employee_id: int, year: int, month: int) -> dict:
        """Hạn mức chỉnh công của 1 NV trong 1 tháng → {limit, used, remaining, days, year, month}.

        NGUỒN DUY NHẤT cho cả CHẶN lẫn HIỂN THỊ — số hiện trên màn và số backend dùng để từ chối
        không bao giờ lệch nhau. `limit = 0` ⇒ không giới hạn.

        Đếm theo NGÀY CÔNG phân biệt (`days`), không theo số đơn. Chỉ tính đơn còn hiệu lực
        (chờ duyệt + đã duyệt); từ chối/hủy trả lại lượt.
        """
        limit = 0
        if self._payroll is not None:
            p = self._payroll.get_params()
            # Không có dòng tham số (DB trắng) ⇒ dùng mặc định của model. `self._payroll is None`
            # là service dựng tay trong unit test ⇒ tắt luật, giữ nguyên hành vi cũ.
            limit = 5 if p is None else int(getattr(p, "adjust_max_per_month", 5) or 0)
        days = self.attendance.live_adjust_days(employee_id, year, month)
        return {"year": year, "month": month, "limit": limit, "used": len(days),
                "remaining": max(0, limit - len(days)) if limit else None, "days": days}

    def request_adjust(self, *, user, date_str: str, check_type: str, suggested_time: str | None,
                       reason: str) -> dict:
        """NV tự gửi yêu cầu chỉnh công cho 1 ngày (self-service)."""
        emp = self._employee_for_user(user)
        if check_type not in CHECK_TYPES:
            raise AttendanceValidationError("Loại chấm phải là VÀO hoặc RA.")
        reason = (reason or "").strip()
        if not reason:
            raise AttendanceValidationError("Phải nhập lý do.")
        the_day = self._parse_ymd(date_str)
        # Chặn ngay từ lúc GỬI, không đợi tới lúc duyệt: đơn cho tháng đã chốt không bao giờ
        # duyệt được, để NV gửi là ăn oan một lượt hạn mức.
        # Cùng lý do đó, hai chốt dưới phải đứng TRƯỚC `adjust_quota` — chặn sau khi đã trừ hạn
        # mức thì đơn hỏng vẫn kịp ăn mất một lượt.
        self._require_not_future(the_day, "gửi yêu cầu chỉnh công")
        self._require_period_open(the_day, "gửi yêu cầu chỉnh công")
        self._require_shift_on_day(emp, the_day)
        q = self.adjust_quota(emp.id, the_day.year, the_day.month)
        # Ngày ĐÃ nằm trong hạn mức thì gửi thêm KHÔNG tốn lượt: mỗi đơn chỉ khai được một lượt
        # chấm (VÀO hoặc RA), nên quên cả hai đầu của một ngày phải gửi 2 đơn — tính 2 lượt là
        # chặt gấp đôi con số chủ chốt.
        if q["limit"] and the_day not in q["days"] and q["used"] >= q["limit"]:
            raise AttendanceValidationError(
                f"Vượt hạn mức chỉnh công tháng {the_day.month}/{the_day.year}: đã dùng/đang chờ "
                f"{q['used']}/{q['limit']} ngày. Hủy một yêu cầu đang chờ, hoặc nhờ HCNS chấm bù "
                f"trực tiếp."
            )
        if suggested_time:
            _hhmm_to_min(suggested_time)  # validate format
        r = self.attendance.create_request(
            employee_id=emp.id, work_date=the_day, check_type=check_type,
            suggested_time=suggested_time or None, reason=reason,
            status=REQ_PENDING, created_by_user_id=user.id,
        )
        return self._req_out(r, emp_name=emp.full_name)

    def my_requests(self, *, user) -> dict:
        """Đơn của NV + HẠN MỨC tháng hiện tại. Trả kèm quota (thay vì bắt FE gọi thêm một
        endpoint nữa) để số hiện trên màn luôn cùng một lần đọc DB với số dùng để chặn."""
        emp = self._employee_for_user(user)
        # Giờ VN, không phải giờ máy chủ — cuối tháng lệch múi giờ là hạn mức nhảy sai tháng.
        today = datetime.now(timezone.utc).astimezone(VN_TZ).date()
        return {
            "items": [self._req_out(r, emp_name=emp.full_name)
                      for r in self.attendance.requests_by_employee(emp.id)],
            "quota": self.adjust_quota(emp.id, today.year, today.month),
        }

    def cancel_request(self, *, user, request_id: int) -> dict:
        emp = self._employee_for_user(user)
        r = self.attendance.get_request(request_id)
        if r is None or r.employee_id != emp.id:
            raise AttendanceNotFound("Không tìm thấy yêu cầu.")
        if r.status != REQ_PENDING:
            raise AttendanceValidationError("Chỉ hủy được yêu cầu đang chờ duyệt.")
        self.attendance.update_request(r, status=REQ_CANCELLED)
        return self._req_out(r, emp_name=emp.full_name)

    def list_requests(self, *, scope, actor, status: str | None = REQ_PENDING) -> list[dict]:
        """HCNS xem yêu cầu chỉnh công theo scope."""
        allowed = self._allowed_employee_ids(scope, actor)
        rows = self.attendance.list_requests(status=status, employee_ids=allowed)
        out = []
        for r in rows:
            emp = self.employees.get_by_id(r.employee_id)
            out.append(self._req_out(r, emp_name=emp.full_name if emp else None))
        return out

    def approve_request(self, *, actor, scope, request_id: int, time_hhmm: str | None,
                        fault_party: str | None, note: str | None = None) -> dict:
        """Duyệt YC → sinh 1 punch điều chỉnh tay (công tự tính lại) + đánh dấu approved."""
        r = self.attendance.get_request(request_id)
        if r is None:
            raise AttendanceNotFound("Không tìm thấy yêu cầu.")
        emp = self._employee_in_scope(r.employee_id, scope, actor)
        if r.status != REQ_PENDING:
            raise AttendanceValidationError("Yêu cầu đã được xử lý.")
        time_val = time_hhmm or r.suggested_time
        if not time_val:
            raise AttendanceValidationError("Cần nhập giờ cho punch chấm bù.")
        log = self._create_manual_punch(
            actor=actor, emp=emp, the_day=r.work_date, check_type=r.check_type,
            time_hhmm=time_val, reason=f"[Duyệt YC #{r.id}] {r.reason}", fault_party=fault_party or r.fault_party,
        )
        self.attendance.update_request(
            r, status=REQ_APPROVED, decided_by=actor.id, decided_at=datetime.now(timezone.utc),
            decision_note=(note or "").strip() or None, resulting_log_id=log.id,
            fault_party=fault_party or r.fault_party,
        )
        return self._req_out(r, emp_name=emp.full_name)

    def reject_request(self, *, actor, scope, request_id: int, note: str) -> dict:
        r = self.attendance.get_request(request_id)
        if r is None:
            raise AttendanceNotFound("Không tìm thấy yêu cầu.")
        emp = self._employee_in_scope(r.employee_id, scope, actor)
        if r.status != REQ_PENDING:
            raise AttendanceValidationError("Yêu cầu đã được xử lý.")
        note = (note or "").strip()
        if not note:
            raise AttendanceValidationError("Phải ghi lý do từ chối.")
        self.attendance.update_request(
            r, status=REQ_REJECTED, decided_by=actor.id, decided_at=datetime.now(timezone.utc),
            decision_note=note,
        )
        return self._req_out(r, emp_name=emp.full_name)

    # --- KPI giám sát hôm nay (HR) -----------------------------------------

    def today_kpi(self, *, scope, actor) -> dict:
        """Đếm nhanh cho dải KPI: đang có mặt / quên chấm RA / đi muộn hôm nay / YC chờ duyệt.
        Theo scope người gọi. Xấp xỉ (không xử lý ca đêm) — đủ cho giám sát trong ngày."""
        allowed = self._allowed_employee_ids(scope, actor)
        now_vn = datetime.now(timezone.utc).astimezone(VN_TZ)
        today = now_vn.date()
        # Quét log 3 ngày gần nhất để suy trạng thái mới nhất mỗi NV.
        start = (datetime(today.year, today.month, today.day, tzinfo=VN_TZ) - timedelta(days=3)).astimezone(timezone.utc)
        end = (datetime(today.year, today.month, today.day, tzinfo=VN_TZ) + timedelta(days=1)).astimezone(timezone.utc)
        shifts = {s.id: s for s in self.attendance.list_shifts()}
        last: dict[int, tuple] = {}          # emp_id → (local_dt, check_type)
        first_in_today: dict[int, datetime] = {}
        for lg in self.attendance.logs_in_range(start, end):
            if allowed is not None and lg.employee_id not in allowed:
                continue
            local = _as_utc(lg.checked_at).astimezone(VN_TZ)
            prev = last.get(lg.employee_id)
            if prev is None or local >= prev[0]:
                last[lg.employee_id] = (local, lg.check_type)
            if local.date() == today and lg.check_type == CHECK_IN:
                cur = first_in_today.get(lg.employee_id)
                if cur is None or local < cur:
                    first_in_today[lg.employee_id] = local
        present_now = missing_out = 0
        for emp_id, (local, ct) in last.items():
            if ct == CHECK_IN:
                if local.date() == today:
                    present_now += 1
                else:
                    missing_out += 1
        late_today = 0
        for emp_id, fin in first_in_today.items():
            emp = self.employees.get_by_id(emp_id)
            shift = self._shift_for_day(emp, today, shifts) if emp is not None else None
            if shift is not None and (fin.hour * 60 + fin.minute) > shift.start_minute + shift.grace_minutes:
                late_today += 1
        return {
            "present_now": present_now,
            "missing_out": missing_out,
            "late_today": late_today,
            "pending_requests": self.attendance.count_pending_requests(employee_ids=allowed),
        }
