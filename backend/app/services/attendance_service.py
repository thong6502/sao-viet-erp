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
from datetime import datetime, timedelta, timezone

from ..models.attendance import CHECK_IN, CHECK_OUT, WorkLocation, WorkShift
from ..repositories.attendance_repo import AttendanceRepository
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.employee_repo import EmployeeRepository

# Giờ Việt Nam (UTC+7, không DST) — dùng để gom "ngày công" theo lịch địa phương.
VN_TZ = timezone(timedelta(hours=7))

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
    `*_min` = phút-từ-nửa-đêm (giờ VN). Ca qua đêm chỉ gần đúng (in/out khác ngày lịch)."""
    window = (1440 - start_min + end_min) if is_overnight else (end_min - start_min)
    if window <= 0:
        return {"cong": 0.0, "late": False, "early": False, "ot_minutes": 0, "incomplete": True}

    late = first_in_min > start_min + grace_min
    effective_in = start_min if first_in_min <= start_min + grace_min else first_in_min
    if last_out_min is None:
        return {"cong": 0.0, "late": late, "early": False, "ot_minutes": 0, "incomplete": True}

    early = last_out_min < end_min
    ot_minutes = max(0, last_out_min - end_min)
    worked = min(last_out_min, end_min) - max(effective_in, start_min)
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
    ) -> None:
        self.attendance = attendance
        self.employees = employees
        self.audit = audit

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

    def my_status(self, *, user) -> dict:
        """What the self-check-in card needs: linked employee, next action, last check,
        whether any location is configured."""
        emp = self.employees.get_by_user_id(user.id)
        locations = self.attendance.list_locations(active_only=True)
        if emp is None:
            return {"has_employee": False, "employee_name": None, "next_action": None,
                    "last_check": None, "locations_configured": len(locations) > 0}
        last = self.attendance.last_log(emp.id)
        return {
            "has_employee": True,
            "employee_id": emp.id,
            "employee_name": emp.full_name,
            "next_action": self._next_check_type(emp.id),
            "last_check": last,
            "locations_configured": len(locations) > 0,
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

    def list_logs(self, *, employee_id: int | None = None, limit: int = 100):
        return self.attendance.list_all(employee_id=employee_id, limit=limit)

    # --- bảng công tháng ----------------------------------------------------

    def monthly_timesheet(self, *, year: int, month: int, department_id: int | None = None) -> dict:
        """Gom attendance_logs của 1 tháng thành lưới NV × ngày (giờ VN). Mỗi ô ngày:
        giờ VÀO đầu tiên, giờ RA cuối cùng, số giờ (nếu đủ vào-ra). Không cần bảng mới."""
        if not (1 <= month <= 12):
            raise AttendanceValidationError("Tháng phải trong khoảng 1–12.")
        days_in_month = calendar.monthrange(year, month)[1]

        # Mốc tháng theo giờ VN → quy về UTC để truy vấn.
        start_vn = datetime(year, month, 1, tzinfo=VN_TZ)
        end_vn = (datetime(year + 1, 1, 1, tzinfo=VN_TZ) if month == 12
                  else datetime(year, month + 1, 1, tzinfo=VN_TZ))
        logs = self.attendance.logs_in_range(
            start_vn.astimezone(timezone.utc), end_vn.astimezone(timezone.utc)
        )

        # employee_id → { day(int) → [(local_dt, check_type)] }
        by_emp: dict[int, dict[int, list]] = {}
        for lg in logs:
            local = lg.checked_at.astimezone(VN_TZ)
            by_emp.setdefault(lg.employee_id, {}).setdefault(local.day, []).append((local, lg.check_type))

        shifts = {s.id: s for s in self.attendance.list_shifts()}

        rows = []
        for emp_id, days in by_emp.items():
            emp = self.employees.get_by_id(emp_id)
            if emp is None:
                continue
            if department_id is not None and emp.department_id != department_id:
                continue
            shift = shifts.get(emp.default_shift_id) if emp.default_shift_id else None
            day_map: dict[str, dict] = {}
            total_hours = 0.0
            total_days = 0
            total_cong = 0.0
            for d, entries in days.items():
                entries.sort(key=lambda x: x[0])
                ins = [t for t, ct in entries if ct == CHECK_IN]
                outs = [t for t, ct in entries if ct == CHECK_OUT]
                first_in = ins[0] if ins else entries[0][0]
                last_out = outs[-1] if outs else None
                hours = None
                if last_out is not None and last_out > first_in:
                    hours = round((last_out - first_in).total_seconds() / 3600, 2)
                    total_hours += hours
                total_days += 1
                cell = {
                    "first_in": first_in.strftime("%H:%M"),
                    "last_out": last_out.strftime("%H:%M") if last_out else None,
                    "hours": hours, "present": True,
                    "cong": None, "late": False, "early": False, "ot_minutes": 0, "night": False,
                }
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
                day_map[str(d)] = cell
            rows.append({
                "employee_id": emp_id, "employee_code": emp.code, "employee_name": emp.full_name,
                "department_id": emp.department_id, "days": day_map,
                "shift_id": shift.id if shift is not None else None,
                "shift_name": shift.name if shift is not None else None,
                "total_days": total_days, "total_hours": round(total_hours, 2),
                "total_cong": round(total_cong, 2) if shift is not None else None,
            })
        rows.sort(key=lambda r: r["employee_code"])
        return {"year": year, "month": month, "days_in_month": days_in_month, "rows": rows}
