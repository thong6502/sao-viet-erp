"""Attendance / chấm công data access (module `nhan_su`). The ONLY layer touching the DB
for work_locations + attendance_logs. No business rules (those live in AttendanceService)."""
from __future__ import annotations

import calendar
import json
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.attendance import (
    AttendanceAdjustRequest,
    AttendanceLog,
    AttendancePeriod,
    AttendancePeriodLine,
    REQ_APPROVED,
    REQ_PENDING,
    WorkLocation,
    WorkShift,
)


def _load_off_days(raw: str | None) -> list[int]:
    """Đọc cột JSON `late_off_days_json` (danh sách số phút vi phạm mỗi ngày) an toàn → list[int]."""
    if not raw:
        return []
    try:
        v = json.loads(raw)
        return [int(x) for x in v] if isinstance(v, list) else []
    except (ValueError, TypeError):
        return []


class AttendanceRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- work_shifts --------------------------------------------------------

    def list_shifts(self, *, active_only: bool = False) -> list[WorkShift]:
        stmt = select(WorkShift)
        if active_only:
            stmt = stmt.where(WorkShift.is_active.is_(True))
        return list(self.db.execute(stmt.order_by(WorkShift.start_minute, WorkShift.id)).scalars())

    def get_shift(self, shift_id: int) -> WorkShift | None:
        return self.db.get(WorkShift, shift_id)

    def create_shift(self, **fields) -> WorkShift:
        s = WorkShift(**fields)
        self.db.add(s)
        self.db.commit()
        self.db.refresh(s)
        return s

    def update_shift(self, shift: WorkShift, **fields) -> WorkShift:
        for key, value in fields.items():
            setattr(shift, key, value)
        self.db.commit()
        self.db.refresh(shift)
        return shift

    def delete_shift(self, shift: WorkShift) -> None:
        self.db.delete(shift)
        self.db.commit()

    # --- work_locations -----------------------------------------------------

    def list_locations(self, *, active_only: bool = False) -> list[WorkLocation]:
        stmt = select(WorkLocation)
        if active_only:
            stmt = stmt.where(WorkLocation.is_active.is_(True))
        return list(self.db.execute(stmt.order_by(WorkLocation.id)).scalars())

    def get_location(self, location_id: int) -> WorkLocation | None:
        return self.db.get(WorkLocation, location_id)

    def create_location(self, **fields) -> WorkLocation:
        loc = WorkLocation(**fields)
        self.db.add(loc)
        self.db.commit()
        self.db.refresh(loc)
        return loc

    def update_location(self, loc: WorkLocation, **fields) -> WorkLocation:
        for key, value in fields.items():
            setattr(loc, key, value)
        self.db.commit()
        self.db.refresh(loc)
        return loc

    def delete_location(self, loc: WorkLocation) -> None:
        self.db.delete(loc)
        self.db.commit()

    # --- attendance_logs ----------------------------------------------------

    def create_log(self, **fields) -> AttendanceLog:
        log = AttendanceLog(**fields)
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        return log

    def last_log(self, employee_id: int) -> AttendanceLog | None:
        """Most recent log for the employee (drives auto VÀO/RA toggling)."""
        return self.db.execute(
            select(AttendanceLog)
            .where(AttendanceLog.employee_id == employee_id)
            .order_by(AttendanceLog.checked_at.desc(), AttendanceLog.id.desc())
        ).scalars().first()

    def list_by_employee(self, employee_id: int, *, limit: int = 30) -> list[AttendanceLog]:
        return list(
            self.db.execute(
                select(AttendanceLog)
                .where(AttendanceLog.employee_id == employee_id)
                .order_by(AttendanceLog.checked_at.desc(), AttendanceLog.id.desc())
                .limit(limit)
            ).scalars()
        )

    def get_log(self, log_id: int) -> AttendanceLog | None:
        return self.db.get(AttendanceLog, log_id)

    def delete_log(self, log: AttendanceLog) -> None:
        self.db.delete(log)
        self.db.commit()

    def list_by_employee_in_range(self, employee_id: int, start, end) -> list[AttendanceLog]:
        """Punch của 1 NV trong [start,end) UTC, cũ→mới — cho 'ô biết nói' (chi tiết 1 ngày)."""
        return list(
            self.db.execute(
                select(AttendanceLog)
                .where(AttendanceLog.employee_id == employee_id,
                       AttendanceLog.checked_at >= start, AttendanceLog.checked_at < end)
                .order_by(AttendanceLog.checked_at.asc(), AttendanceLog.id.asc())
            ).scalars()
        )

    def logs_in_range(self, start, end) -> list[AttendanceLog]:
        """All logs with checked_at in [start, end) (UTC), oldest first — for the monthly
        timesheet aggregation."""
        return list(
            self.db.execute(
                select(AttendanceLog)
                .where(AttendanceLog.checked_at >= start, AttendanceLog.checked_at < end)
                .order_by(AttendanceLog.checked_at.asc(), AttendanceLog.id.asc())
            ).scalars()
        )

    # --- attendance_adjust_requests (yêu cầu chỉnh công) --------------------

    def create_request(self, **fields) -> AttendanceAdjustRequest:
        r = AttendanceAdjustRequest(**fields)
        self.db.add(r)
        self.db.commit()
        self.db.refresh(r)
        return r

    def get_request(self, request_id: int) -> AttendanceAdjustRequest | None:
        return self.db.get(AttendanceAdjustRequest, request_id)

    def update_request(self, req: AttendanceAdjustRequest, **fields) -> AttendanceAdjustRequest:
        for k, v in fields.items():
            setattr(req, k, v)
        self.db.commit()
        self.db.refresh(req)
        return req

    def requests_by_employee(self, employee_id: int, *, limit: int = 100) -> list[AttendanceAdjustRequest]:
        return list(self.db.execute(
            select(AttendanceAdjustRequest)
            .where(AttendanceAdjustRequest.employee_id == employee_id)
            .order_by(AttendanceAdjustRequest.created_at.desc(), AttendanceAdjustRequest.id.desc())
            .limit(limit)
        ).scalars())

    def list_requests(self, *, status: str | None = None, employee_ids: set[int] | None = None,
                      limit: int = 200) -> list[AttendanceAdjustRequest]:
        stmt = select(AttendanceAdjustRequest)
        if status is not None:
            stmt = stmt.where(AttendanceAdjustRequest.status == status)
        if employee_ids is not None:
            stmt = stmt.where(AttendanceAdjustRequest.employee_id.in_(employee_ids))
        stmt = stmt.order_by(AttendanceAdjustRequest.created_at.desc(), AttendanceAdjustRequest.id.desc()).limit(limit)
        return list(self.db.execute(stmt).scalars())

    def live_adjust_days(self, employee_id: int, year: int, month: int) -> set:
        """Tập NGÀY CÔNG (`work_date`) mà NV đang có yêu cầu chỉnh công CÒN HIỆU LỰC trong tháng —
        nền cho hạn mức "tối đa N lần/tháng".

        Trả SET NGÀY chứ không trả số đếm: service cần vừa biết đã dùng bao nhiêu, vừa biết ngày
        sắp gửi có nằm sẵn trong đó không (quên cả giờ vào lẫn giờ ra của cùng một ngày phải gửi
        2 đơn, nhưng chỉ tính 1 lượt) — cả hai bằng MỘT truy vấn.

        `pending` cũng giữ chỗ như `approved` (chống gửi ồ ạt rồi duyệt sau); `rejected`/`cancelled`
        trả lại lượt."""
        last = calendar.monthrange(year, month)[1]
        rows = self.db.execute(
            select(AttendanceAdjustRequest.work_date).where(
                AttendanceAdjustRequest.employee_id == employee_id,
                AttendanceAdjustRequest.status.in_((REQ_PENDING, REQ_APPROVED)),
                AttendanceAdjustRequest.work_date >= date(year, month, 1),
                AttendanceAdjustRequest.work_date <= date(year, month, last),
            ).distinct()
        ).scalars()
        return set(rows)

    def count_pending_requests(self, *, employee_ids: set[int] | None = None,
                               start: date | None = None, end: date | None = None) -> int:
        """`start`/`end` lọc theo NGÀY CÔNG. Guard chốt công phải truyền khoảng của đúng tháng
        đang chốt — không lọc thì một đơn treo từ tháng 5 chặn chốt tháng 7, mà HCNS mở tháng 7
        ra chẳng thấy nó đâu để mà duyệt."""
        from sqlalchemy import func
        stmt = select(func.count()).select_from(AttendanceAdjustRequest).where(
            AttendanceAdjustRequest.status == REQ_PENDING)
        if employee_ids is not None:
            stmt = stmt.where(AttendanceAdjustRequest.employee_id.in_(employee_ids))
        if start is not None:
            stmt = stmt.where(AttendanceAdjustRequest.work_date >= start)
        if end is not None:
            stmt = stmt.where(AttendanceAdjustRequest.work_date <= end)
        return self.db.execute(stmt).scalar_one()

    def list_all(
        self, *, employee_ids: set[int] | None = None, limit: int = 100
    ) -> list[AttendanceLog]:
        """Logs mới nhất. `employee_ids=None` = mọi nhân viên; tập rỗng = không ai (an toàn
        cho scope không thấy NV nào); tập có phần tử = chỉ các NV đó (dùng cho lọc scope)."""
        stmt = select(AttendanceLog)
        if employee_ids is not None:
            stmt = stmt.where(AttendanceLog.employee_id.in_(employee_ids))
        stmt = stmt.order_by(AttendanceLog.checked_at.desc(), AttendanceLog.id.desc()).limit(limit)
        return list(self.db.execute(stmt).scalars())

    # --- attendance_periods (Chốt công) ------------------------------------

    def get_period_by_ym(self, year: int, month: int) -> AttendancePeriod | None:
        return self.db.execute(
            select(AttendancePeriod).where(AttendancePeriod.year == year, AttendancePeriod.month == month)
        ).scalars().first()

    def create_period(self, **fields) -> AttendancePeriod:
        p = AttendancePeriod(**fields)
        self.db.add(p)
        self.db.commit()
        self.db.refresh(p)
        return p

    def update_period(self, p: AttendancePeriod, **fields) -> AttendancePeriod:
        for k, v in fields.items():
            setattr(p, k, v)
        self.db.commit()
        self.db.refresh(p)
        return p

    def list_periods(self, *, limit: int = 36) -> list[AttendancePeriod]:
        return list(self.db.execute(
            select(AttendancePeriod).order_by(AttendancePeriod.year.desc(), AttendancePeriod.month.desc()).limit(limit)
        ).scalars())

    def list_period_lines(self, period_id: int) -> list[AttendancePeriodLine]:
        return list(self.db.execute(
            select(AttendancePeriodLine).where(AttendancePeriodLine.period_id == period_id)
            .order_by(AttendancePeriodLine.id)
        ).scalars())

    def period_cong_map(self, period_id: int) -> dict[int, float]:
        return {ln.employee_id: float(ln.total_cong) for ln in self.list_period_lines(period_id)}

    def period_metrics_map(self, period_id: int) -> dict[int, dict]:
        """{emp_id → {cong, ot_minutes, night_days}} từ snapshot kỳ công đã chốt — cho Lương
        cắm tăng ca + ca đêm (Pha 4a)."""
        return {
            ln.employee_id: {
                "cong": float(ln.total_cong),
                "ot_minutes": int(ln.ot_minutes or 0),
                "night_days": int(ln.night_days or 0),
                "holiday_cong": float(getattr(ln, "holiday_cong", 0) or 0),
                "restday_cong": float(getattr(ln, "restday_cong", 0) or 0),
                "plain_cong": float(getattr(ln, "plain_cong", 0) or 0),
                # PHẢI khớp 1-1 với nhánh LIVE của `AttendanceService.metrics_map`. Thiếu ở đây
                # thì lương ĐỔI SỐ đúng lúc HCNS bấm Chốt công (draft một số, chốt xong một số).
                "excused_cong": float(getattr(ln, "excused_cong", 0) or 0),
                "paid_leave_days": float(getattr(ln, "paid_leave_days", 0) or 0),
                "ot_holiday_minutes": int(getattr(ln, "ot_holiday_minutes", 0) or 0),
                "ot_restday_minutes": int(getattr(ln, "ot_restday_minutes", 0) or 0),
                "late_off_days": _load_off_days(getattr(ln, "late_off_days_json", None)),
                "night_premium_minutes": float(getattr(ln, "night_premium_minutes", 0) or 0),
                "ot_night_normal_minutes": int(getattr(ln, "ot_night_normal_minutes", 0) or 0),
                "ot_night_restday_minutes": int(getattr(ln, "ot_night_restday_minutes", 0) or 0),
                "ot_night_holiday_minutes": int(getattr(ln, "ot_night_holiday_minutes", 0) or 0),
            }
            for ln in self.list_period_lines(period_id)
        }

    def delete_period_lines(self, period_id: int) -> None:
        for ln in self.list_period_lines(period_id):
            self.db.delete(ln)
        self.db.commit()

    def create_period_line(self, **fields) -> AttendancePeriodLine:
        ln = AttendancePeriodLine(**fields)
        self.db.add(ln)
        self.db.commit()
        self.db.refresh(ln)
        return ln
