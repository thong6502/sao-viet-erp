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

from ..models.attendance import CHECK_IN, CHECK_OUT, WorkLocation

# Giờ Việt Nam (UTC+7, không DST) — dùng để gom "ngày công" theo lịch địa phương.
VN_TZ = timezone(timedelta(hours=7))
from ..repositories.attendance_repo import AttendanceRepository
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.employee_repo import EmployeeRepository

_EARTH_RADIUS_M = 6_371_000.0  # mean Earth radius, metres


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two WGS-84 points, in metres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


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

        rows = []
        for emp_id, days in by_emp.items():
            emp = self.employees.get_by_id(emp_id)
            if emp is None:
                continue
            if department_id is not None and emp.department_id != department_id:
                continue
            day_map: dict[str, dict] = {}
            total_hours = 0.0
            total_days = 0
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
                day_map[str(d)] = {
                    "first_in": first_in.strftime("%H:%M"),
                    "last_out": last_out.strftime("%H:%M") if last_out else None,
                    "hours": hours,
                    "present": True,
                }
            rows.append({
                "employee_id": emp_id, "employee_code": emp.code, "employee_name": emp.full_name,
                "department_id": emp.department_id, "days": day_map,
                "total_days": total_days, "total_hours": round(total_hours, 2),
            })
        rows.sort(key=lambda r: r["employee_code"])
        return {"year": year, "month": month, "days_in_month": days_in_month, "rows": rows}
