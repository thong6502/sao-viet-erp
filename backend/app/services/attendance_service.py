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
import math
from datetime import date, datetime, timedelta, timezone

from ..models.attendance import (
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
from ..models.role import SCOPE_ALL
from ..repositories.attendance_repo import AttendanceRepository
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.employee_repo import EmployeeRepository

# Giờ Việt Nam (UTC+7, không DST) — dùng để gom "ngày công" theo lịch địa phương.
VN_TZ = timezone(timedelta(hours=7))


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


def _hhmm_to_min(s: str) -> int:
    try:
        h, m = str(s).split(":")
        h, m = int(h), int(m)
    except (ValueError, AttributeError):
        raise AttendanceValidationError("Giờ phải dạng HH:MM.")
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise AttendanceValidationError("Giờ không hợp lệ (00:00–23:59).")
    return h * 60 + m


def compute_day_cong(
    *, start_min: int, end_min: int, is_overnight: bool, grace_min: int,
    first_in_min: int, last_out_min: int | None,
) -> dict:
    """Tính CÔNG một ngày theo ca (chốt với SVN):
      công = (số phút làm trong khung ca) ÷ (số phút chuẩn của ca), giữ 2 chữ số, tối đa 1,00.
      • Vào trễ ≤ dung sai (grace) vẫn coi đúng giờ (không trừ).
      • Đủ giờ (đúng giờ + ra ≥ giờ ca) ⇒ 1,00. Đi muộn/về sớm ⇒ giảm theo tỷ lệ (0,94…).
      • Thiếu chấm ra ⇒ 0 công (đánh dấu incomplete).
      • OT = phút ra vượt giờ ca (tính riêng, KHÔNG cộng vào công).
    `*_min` = phút-từ-nửa-đêm (giờ VN). Ca qua đêm: giờ RA/vào sau nửa đêm được ánh xạ +1440 lên
    trục thời gian tuyến tính của ca (ra 06:00 → 1800) để tính đúng theo NGÀY VÀO ca."""
    end_ref = (end_min + 1440) if is_overnight else end_min
    window = end_ref - start_min
    if window <= 0:
        return {"cong": 0.0, "late": False, "early": False, "ot_minutes": 0, "incomplete": True}

    def _lin(m: int) -> int:
        # Ca đêm: mốc rơi vào rạng sáng (≤ giờ RA) thuộc phần sau nửa đêm của ca → +1440.
        return m + 1440 if (is_overnight and m <= end_min) else m

    fin = _lin(first_in_min)
    late = fin > start_min + grace_min
    effective_in = start_min if fin <= start_min + grace_min else fin
    if last_out_min is None:
        return {"cong": 0.0, "late": late, "early": False, "ot_minutes": 0, "incomplete": True}

    lout = _lin(last_out_min)
    early = lout < end_ref
    ot_minutes = max(0, lout - end_ref)
    worked = min(lout, end_ref) - max(effective_in, start_min)
    worked = max(0, min(worked, window))
    cong = min(1.0, round(worked / window, 2))
    return {"cong": cong, "late": late, "early": early, "ot_minutes": ot_minutes, "incomplete": False}


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


class AttendanceService:
    def __init__(
        self,
        attendance: AttendanceRepository,
        employees: EmployeeRepository,
        audit: AuditLogRepository,
        leaves=None,
    ) -> None:
        self.attendance = attendance
        self.employees = employees
        self.audit = audit
        self.leaves = leaves  # LeaveRepository | None — để Bảng công tháng đánh dấu nghỉ đã duyệt

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
                     night_shift=False, grace_minutes=5, note=None) -> WorkShift:
        is_overnight = bool(is_overnight)
        name, sm, em, g = self._validate_shift(name, start_time, end_time, grace_minutes, is_overnight)
        s = self.attendance.create_shift(
            name=name, start_minute=sm, end_minute=em, is_overnight=is_overnight,
            night_shift=bool(night_shift), grace_minutes=g, note=_clean(note), is_active=True,
        )
        self.audit.create(actor_user_id=actor.id, action="create_work_shift",
                          target=f"work_shift:{s.id}", detail=f"{name} {start_time}–{end_time}")
        return s

    def update_shift(self, *, actor, shift_id, name, start_time, end_time, is_overnight=False,
                     night_shift=False, grace_minutes=5, note=None, is_active=True) -> WorkShift:
        s = self.attendance.get_shift(shift_id)
        if s is None:
            raise AttendanceNotFound("Không tìm thấy ca làm việc.")
        is_overnight = bool(is_overnight)
        name, sm, em, g = self._validate_shift(name, start_time, end_time, grace_minutes, is_overnight)
        self.attendance.update_shift(
            s, name=name, start_minute=sm, end_minute=em, is_overnight=is_overnight,
            night_shift=bool(night_shift), grace_minutes=g, note=_clean(note), is_active=bool(is_active),
        )
        self.audit.create(actor_user_id=actor.id, action="update_work_shift",
                          target=f"work_shift:{s.id}", detail=f"{name} {start_time}–{end_time}")
        return s

    def delete_shift(self, *, actor, shift_id) -> None:
        s = self.attendance.get_shift(shift_id)
        if s is None:
            raise AttendanceNotFound("Không tìm thấy ca làm việc.")
        self.attendance.delete_shift(s)
        self.audit.create(actor_user_id=actor.id, action="delete_work_shift",
                          target=f"work_shift:{shift_id}", detail=s.name)

    # --- self check-in ------------------------------------------------------

    def _employee_for_user(self, user):
        emp = self.employees.get_by_user_id(user.id)
        if emp is None:
            raise NoLinkedEmployee("Tài khoản của bạn chưa gắn hồ sơ nhân viên.")
        return emp

    def _next_check_type(self, employee_id: int) -> str:
        last = self.attendance.last_log(employee_id)
        return CHECK_OUT if (last is not None and last.check_type == CHECK_IN) else CHECK_IN

    def _today_summary(self, emp, shift) -> dict | None:
        """Tóm tắt chấm công HÔM NAY (giờ VN) của NV cho khối 'Hôm nay của tôi': giờ vào/ra,
        công dự kiến, và LÝ DO khi công < đủ (thiếu chấm RA / vào trễ / về sớm / chưa gán ca)."""
        today = datetime.now(timezone.utc).astimezone(VN_TZ).date()
        entries = []
        for lg in self.attendance.list_by_employee(emp.id, limit=20):
            local = _as_utc(lg.checked_at).astimezone(VN_TZ)
            wd = local.date()
            if shift is not None and shift.is_overnight and (local.hour * 60 + local.minute) <= shift.end_minute:
                wd = (local - timedelta(days=1)).date()
            if wd == today:
                entries.append((local, lg.check_type))
        if not entries:
            return None
        entries.sort(key=lambda x: x[0])
        ins = [t for t, ct in entries if ct == CHECK_IN]
        outs = [t for t, ct in entries if ct == CHECK_OUT]
        first_in = ins[0] if ins else entries[0][0]
        last_out = outs[-1] if outs else None
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
            last_out_min=(last_out.hour * 60 + last_out.minute) if last_out else None,
        )
        out.update(cong=info["cong"], late=info["late"], early=info["early"], ot_minutes=info["ot_minutes"])
        if info["incomplete"]:
            out["reason"] = "Chưa chấm RA"
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
                    "shift": None, "today": None}
        last = self.attendance.last_log(emp.id)
        shift = self.attendance.get_shift(emp.default_shift_id) if emp.default_shift_id else None
        return {
            "has_employee": True,
            "employee_id": emp.id,
            "employee_name": emp.full_name,
            "next_action": self._next_check_type(emp.id),
            "last_check": last,
            "locations_configured": len(locations) > 0,
            "shift": shift,
            "today": self._today_summary(emp, shift),
        }

    def preview(self, *, user, latitude, longitude) -> dict:
        """Dry-run geofence cho card chấm 'sống': tính điểm gần nhất + trong/ngoài phạm vi +
        còn cách bao nhiêu — KHÔNG ghi log. Dùng để vẽ vòng geofence realtime cho NV."""
        emp = self._employee_for_user(user)  # chỉ NV có hồ sơ mới preview (self-service)
        try:
            lat, lon = float(latitude), float(longitude)
        except (TypeError, ValueError):
            raise AttendanceValidationError("Toạ độ gửi lên không hợp lệ.")
        locations = self.attendance.list_locations(active_only=True)
        if not locations:
            return {"locations_configured": False, "within_range": False, "distance_m": None,
                    "meters_out": None, "nearest_name": None, "radius_m": None,
                    "next_action": self._next_check_type(emp.id),
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
            "next_action": self._next_check_type(emp.id),
            "message": (f"Trong phạm vi '{nearest.name}' (cách {distance:.0f} m)." if within
                        else f"Ngoài phạm vi '{nearest.name}' — còn cách {meters_out:.0f} m."),
        }

    def check(self, *, user, latitude, longitude) -> dict:
        """Attempt a GPS check-in/out. Returns a result dict; a log is created ONLY when
        the point is inside some active location's radius (chặn cứng)."""
        emp = self._employee_for_user(user)
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

        check_type = self._next_check_type(emp.id)
        log = self.attendance.create_log(
            employee_id=emp.id, work_location_id=nearest.id, check_type=check_type,
            latitude=lat, longitude=lon, distance_m=distance, within_range=True,
        )
        verb = "VÀO" if check_type == CHECK_IN else "RA"
        return {
            "success": True, "within_range": True, "check_type": check_type,
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

    def list_logs(self, *, scope=None, actor=None, employee_id: int | None = None, limit: int = 100):
        """Log chấm công, LỌC THEO SCOPE của người gọi (own/department/all). `employee_id` do
        client truyền chỉ được chấp nhận nếu nằm trong tập cho phép (ngoài → rỗng, không rò)."""
        allowed = self._allowed_employee_ids(scope, actor)
        if employee_id is not None:
            if allowed is not None and employee_id not in allowed:
                return []
            return self.attendance.list_all(employee_ids={employee_id}, limit=limit)
        return self.attendance.list_all(employee_ids=allowed, limit=limit)

    # --- bảng công tháng ----------------------------------------------------

    def monthly_timesheet(self, *, year: int, month: int, department_id: int | None = None,
                          scope=None, actor=None, only_employee_id: int | None = None) -> dict:
        """Gom attendance_logs của 1 tháng thành lưới NV × ngày (giờ VN). Mỗi ô ngày:
        giờ VÀO đầu tiên, giờ RA cuối cùng, số giờ (nếu đủ vào-ra). Không cần bảng mới.

        LỌC THEO SCOPE: `only_employee_id` (self-timesheet) > `scope/actor` (own/department/all).
        CA ĐÊM: lượt RA rạng sáng ngày N+1 được quy về NGÀY VÀO ca (ngày N)."""
        if not (1 <= month <= 12):
            raise AttendanceValidationError("Tháng phải trong khoảng 1–12.")
        days_in_month = calendar.monthrange(year, month)[1]

        if only_employee_id is not None:
            allowed: set[int] | None = {only_employee_id}
        else:
            allowed = self._allowed_employee_ids(scope, actor)

        # Mốc tháng theo giờ VN → quy về UTC để truy vấn. Nới thêm +12h cuối để lấy lượt RA rạng
        # sáng ngày đầu tháng sau (thuộc ca đêm VÀO ngày cuối tháng này); lượt thừa được lọc theo
        # "ngày công" ở dưới nên không trùng đếm sang tháng sau.
        start_vn = datetime(year, month, 1, tzinfo=VN_TZ)
        end_vn = (datetime(year + 1, 1, 1, tzinfo=VN_TZ) if month == 12
                  else datetime(year, month + 1, 1, tzinfo=VN_TZ))
        logs = self.attendance.logs_in_range(
            start_vn.astimezone(timezone.utc), (end_vn + timedelta(hours=12)).astimezone(timezone.utc)
        )

        shifts = {s.id: s for s in self.attendance.list_shifts()}

        def _work_day(local: datetime, shift) -> date:
            """Ngày CÔNG của một lượt chấm: bình thường = ngày lịch; ca đêm + rơi vào rạng sáng
            (≤ giờ RA của ca) → thuộc ngày VÀO ca liền trước (lùi 1 ngày)."""
            if shift is not None and shift.is_overnight:
                if local.hour * 60 + local.minute <= shift.end_minute:
                    return (local - timedelta(days=1)).date()
            return local.date()

        # employee_id → { day(int) → [(local_dt, check_type)] } theo NGÀY CÔNG, chỉ trong tháng này.
        by_emp: dict[int, dict[int, list]] = {}
        for lg in logs:
            if allowed is not None and lg.employee_id not in allowed:
                continue
            emp0 = self.employees.get_by_id(lg.employee_id)
            shift0 = shifts.get(emp0.default_shift_id) if (emp0 and emp0.default_shift_id) else None
            local = _as_utc(lg.checked_at).astimezone(VN_TZ)
            wd = _work_day(local, shift0)
            if wd.year != year or wd.month != month:
                continue  # lượt thuộc tháng khác (vd RA rạng sáng ngày 1 → thuộc tháng trước)
            by_emp.setdefault(lg.employee_id, {}).setdefault(wd.day, []).append((local, lg.check_type))

        # Ngày NGHỈ ĐÃ DUYỆT trong tháng: {emp_id → {day → {name, is_paid}}}.
        leave_map: dict[int, dict[int, dict]] = {}
        if self.leaves is not None:
            first = date(year, month, 1)
            last = date(year, month, days_in_month)
            ltypes = {t.id: t for t in self.leaves.list_types()}
            for r in self.leaves.approved_in_range(first, last):
                if allowed is not None and r.employee_id not in allowed:
                    continue  # lọc theo scope: chỉ ngày nghỉ của NV trong tầm nhìn người gọi
                lt = ltypes.get(r.leave_type_id)
                nm = lt.name if lt is not None else "Nghỉ"
                paid = lt.is_paid if lt is not None else True
                d, e = max(r.start_date, first), min(r.end_date, last)
                while d <= e:
                    leave_map.setdefault(r.employee_id, {})[d.day] = {"name": nm, "is_paid": paid}
                    d = date.fromordinal(d.toordinal() + 1)

        def _empty_cell() -> dict:
            return {"first_in": None, "last_out": None, "hours": None, "present": False,
                    "cong": None, "late": False, "early": False, "ot_minutes": 0, "night": False,
                    "leave": None, "leave_paid": False}

        rows = []
        for emp_id in set(by_emp) | set(leave_map):
            emp = self.employees.get_by_id(emp_id)
            if emp is None:
                continue
            if department_id is not None and emp.department_id != department_id:
                continue
            shift = shifts.get(emp.default_shift_id) if emp.default_shift_id else None
            att_days = by_emp.get(emp_id, {})
            lv_days = leave_map.get(emp_id, {})
            day_map: dict[str, dict] = {}
            total_hours = 0.0
            total_days = 0
            total_leave = 0
            total_cong = 0.0
            for d in sorted(set(att_days) | set(lv_days)):
                cell = _empty_cell()
                if d in att_days:  # có chấm công → attendance thắng ngày nghỉ
                    entries = sorted(att_days[d], key=lambda x: x[0])
                    ins = [t for t, ct in entries if ct == CHECK_IN]
                    outs = [t for t, ct in entries if ct == CHECK_OUT]
                    first_in = ins[0] if ins else entries[0][0]
                    last_out = outs[-1] if outs else None
                    hours = None
                    if last_out is not None and last_out > first_in:
                        hours = round((last_out - first_in).total_seconds() / 3600, 2)
                        total_hours += hours
                    total_days += 1
                    cell.update(first_in=first_in.strftime("%H:%M"),
                                last_out=last_out.strftime("%H:%M") if last_out else None,
                                hours=hours, present=True)
                    if shift is not None:
                        info = compute_day_cong(
                            start_min=shift.start_minute, end_min=shift.end_minute,
                            is_overnight=shift.is_overnight, grace_min=shift.grace_minutes,
                            first_in_min=first_in.hour * 60 + first_in.minute,
                            last_out_min=(last_out.hour * 60 + last_out.minute) if last_out else None,
                        )
                        cell.update(cong=info["cong"], late=info["late"], early=info["early"],
                                    ot_minutes=info["ot_minutes"], night=shift.night_shift)
                        total_cong += info["cong"]
                else:  # ngày nghỉ đã duyệt (không chấm công)
                    lv = lv_days[d]
                    cong = 1.0 if lv["is_paid"] else 0.0
                    cell.update(cong=cong, leave=lv["name"], leave_paid=lv["is_paid"])
                    total_leave += 1
                    total_cong += cong
                day_map[str(d)] = cell
            has_cong = shift is not None or total_leave > 0
            rows.append({
                "employee_id": emp_id, "employee_code": emp.code, "employee_name": emp.full_name,
                "department_id": emp.department_id, "days": day_map,
                "shift_id": shift.id if shift is not None else None,
                "shift_name": shift.name if shift is not None else None,
                "total_days": total_days, "total_leave": total_leave,
                "total_hours": round(total_hours, 2),
                "total_cong": round(total_cong, 2) if has_cong else None,
            })
        rows.sort(key=lambda r: r["employee_code"])
        return {"year": year, "month": month, "days_in_month": days_in_month, "rows": rows}

    def my_timesheet(self, *, user, year: int, month: int) -> dict:
        """Bảng công tháng CỦA CHÍNH NV đăng nhập (self-service, không cần quyền module).
        Tái dùng monthly_timesheet với chỉ hồ sơ NV của người gọi."""
        emp = self._employee_for_user(user)
        return self.monthly_timesheet(year=year, month=month, only_employee_id=emp.id)

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
            wd = local.date()
            if shift is not None and shift.is_overnight and (local.hour * 60 + local.minute) <= shift.end_minute:
                wd = (local - timedelta(days=1)).date()
            if wd == the_day:
                out.append((local, lg))
        out.sort(key=lambda x: x[0])
        return out

    def day_detail(self, *, scope, actor, employee_id: int, date_str: str) -> dict:
        """'Ô biết nói': punch thật của 1 NV trong 1 ngày + công tính lại + lý do."""
        emp = self._employee_in_scope(employee_id, scope, actor)
        the_day = self._parse_ymd(date_str)
        shift = self.attendance.get_shift(emp.default_shift_id) if emp.default_shift_id else None
        punches = self._day_punches(emp, shift, the_day)
        ins = [lc for lc, lg in punches if lg.check_type == CHECK_IN]
        outs = [lc for lc, lg in punches if lg.check_type == CHECK_OUT]
        first_in = ins[0] if ins else (punches[0][0] if punches else None)
        last_out = outs[-1] if outs else None
        cong = reason = None
        if shift is not None and first_in is not None:
            info = compute_day_cong(
                start_min=shift.start_minute, end_min=shift.end_minute,
                is_overnight=shift.is_overnight, grace_min=shift.grace_minutes,
                first_in_min=first_in.hour * 60 + first_in.minute,
                last_out_min=(last_out.hour * 60 + last_out.minute) if last_out else None,
            )
            cong = info["cong"]
            if info["incomplete"]:
                reason = "Chưa chấm RA"
            elif info["cong"] < 1.0:
                reason = ("Vào trễ và về sớm" if info["late"] and info["early"]
                          else "Vào trễ quá dung sai" if info["late"]
                          else "Về sớm" if info["early"] else None)
        elif shift is None:
            reason = "Chưa gán ca làm việc"
        return {
            "employee_id": emp.id, "employee_name": emp.full_name, "date": date_str,
            "shift_name": shift.name if shift is not None else None,
            "cong": cong, "reason": reason,
            "punches": [{
                "id": lg.id, "time": lc.strftime("%H:%M"), "check_type": lg.check_type,
                "is_manual": lg.is_manual, "adjust_reason": lg.adjust_reason,
                "fault_party": lg.fault_party, "distance_m": float(lg.distance_m) if lg.distance_m is not None else None,
            } for lc, lg in punches],
        }

    def _create_manual_punch(self, *, actor, emp, the_day: date, check_type: str,
                             time_hhmm: str, reason: str, fault_party: str | None):
        """Tạo 1 punch điều chỉnh tay (dùng chung cho chấm bù trực tiếp & duyệt YC)."""
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

    def adjust(self, *, actor, scope, employee_id: int, date_str: str, check_type: str,
               time_hhmm: str, reason: str, fault_party: str | None) -> dict:
        """HCNS thêm 1 PUNCH điều chỉnh tay (chấm bù/sửa) — công tự tính lại từ punch.
        KHÔNG ghi đè số công. Bắt buộc lý do; ghi audit + người thực hiện."""
        emp = self._employee_in_scope(employee_id, scope, actor)
        self._create_manual_punch(actor=actor, emp=emp, the_day=self._parse_ymd(date_str),
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
        if suggested_time:
            _hhmm_to_min(suggested_time)  # validate format
        r = self.attendance.create_request(
            employee_id=emp.id, work_date=the_day, check_type=check_type,
            suggested_time=suggested_time or None, reason=reason,
            status=REQ_PENDING, created_by_user_id=user.id,
        )
        return self._req_out(r, emp_name=emp.full_name)

    def my_requests(self, *, user) -> list[dict]:
        emp = self._employee_for_user(user)
        return [self._req_out(r, emp_name=emp.full_name)
                for r in self.attendance.requests_by_employee(emp.id)]

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
            shift = shifts.get(emp.default_shift_id) if (emp and emp.default_shift_id) else None
            if shift is not None and (fin.hour * 60 + fin.minute) > shift.start_minute + shift.grace_minutes:
                late_today += 1
        return {
            "present_now": present_now,
            "missing_out": missing_out,
            "late_today": late_today,
            "pending_requests": self.attendance.count_pending_requests(employee_ids=allowed),
        }
