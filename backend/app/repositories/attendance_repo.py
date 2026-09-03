"""Attendance / chấm công data access (module `nhan_su`). The ONLY layer touching the DB
for work_locations + attendance_logs. No business rules (those live in AttendanceService)."""
from __future__ import annotations

import calendar
import json
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models.employee import Employee
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


def _load_ot_days(raw):
    """Đọc `ot_days_json`. Ép khoá ngày về SỐ để khớp nhánh live — xem `_chuan_ot_days`."""
    import json as _json
    try:
        v = _json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        v = {}
    return {k: {int(d): int(m) for d, m in (v.get(k) or {}).items()} for k in ("lam", "nghi")}


def _load_ca_lam(raw: str | None) -> dict[int, list[float]]:
    """Đọc cột JSON `ca_lam_json` → {ca → [công từng ngày làm ca đó]}.

    Khoá JSON luôn là CHUỖI, phải ép về int — không thì bên Lương tra `work_shifts` bằng "3" thay
    vì 3 và im lặng ra 0 đồng phụ cấp. Hỏng dữ liệu → {} chứ không nổ, giống `_load_off_days`."""
    if not raw:
        return {}
    try:
        v = json.loads(raw)
        if not isinstance(v, dict):
            return {}
        return {int(k): [float(x) for x in val] for k, val in v.items() if isinstance(val, list)}
    except (ValueError, TypeError):
        return {}


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

    def ca_lich_xuong(self) -> list[WorkShift]:
        """Tập ca CHẠY DƯỚI XƯỞNG — NGUỒN DÙNG CHUNG cho cả Xếp lịch
        (`XepLichService._ca_lich_may`, nay chỉ gọi lại hàm này) và Theo dõi sản xuất
        (`services/lenh_sx/bang_theo_doi.theo_ca`) — Ruling C117, task-16-brief.md.

        Ca ĐANG DÙNG (`is_active`) VÀ có tick "chạy dưới xưởng" (`ca_san_xuat`), sort theo giờ
        vào rồi id. Ca văn phòng ("Hành chính" 08:00–17:00) KHÔNG được vào đây — xem
        `WorkShift.ca_san_xuat` (`models/attendance.py:103-113`) cho lý do.

        ⚠ KHÔNG ca nào tick `ca_san_xuat` ⇒ trả TẤT CẢ ca đang dùng, KHÔNG trả rỗng. Đường lùi
        này BẮT BUỘC — chính nó là thứ giết cờ đời trước (`dung_cho_lich_may`, mg 0095 → gỡ ở mg
        0226): mặc định TẮT và không có ô khai nên 4/4 ca đều FALSE, hàm trả rỗng rồi lịch xưởng
        rơi về fallback 08:00–16:00 im lặng, không ai thấy.

        Trước Task 16, `XepLichService._ca_lich_may()` tự truy vấn thẳng `work_shifts` (một bản
        sao gần giống hệt hàm này). Rút về MỘT chỗ vì tab "Theo ca" của Theo dõi sản xuất xếp
        việc vào cột ca, mà việc đó do Xếp lịch đặt bằng đúng tập ca kia — hai bên tự đi lấy tập
        ca theo hai đường khác nhau là có việc rơi ra ngoài mọi cột ở một bên mà không ai biết.
        Bài canh hai bên trùng nhau: `tests/test_theo_doi_may_ca_gantt.py::test_tap_ca_trung_voi_xep_lich`.
        """
        cas = self.list_shifts(active_only=True)  # đã ORDER BY start_minute, id
        return [s for s in cas if bool(getattr(s, "ca_san_xuat", True))] or cas

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

    def count_logs_created_after(self, start, end, moc) -> int:
        """Số lượt bấm của khoảng [start, end) mà được GHI VÀO sau mốc `moc` (UTC).

        Dùng để biết kỳ công đã chốt còn "phát sinh" gì không. Lọc theo HAI trục khác nhau, cố ý:
        `checked_at` nói lượt bấm thuộc THÁNG nào, `created_at` nói nó được ghi LÚC nào. Chỉ nhìn
        một trục là hỏng — người chấm công hôm nay cho tháng này (created mới, checked mới) khác
        hẳn HCNS ghi bù hôm nay cho tháng trước.
        """
        return int(self.db.execute(
            select(func.count()).select_from(AttendanceLog)
            .where(AttendanceLog.checked_at >= start, AttendanceLog.checked_at < end,
                   AttendanceLog.created_at > moc)
        ).scalar() or 0)

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
        self, *, employee_ids: set[int] | None = None, limit: int = 100, q: str | None = None,
        tu=None, den=None,
    ) -> list[AttendanceLog]:
        """Logs mới nhất. `employee_ids=None` = mọi nhân viên; tập rỗng = không ai (an toàn
        cho scope không thấy NV nào); tập có phần tử = chỉ các NV đó (dùng cho lọc scope).

        `q` = tìm theo TÊN hoặc MÃ nhân viên. Lọc ở SQL chứ không ở FE là có chủ đích: hàm này chỉ
        trả `limit` lượt gần nhất của CẢ XƯỞNG, mà xưởng 50 người bấm 2–4 lượt/ngày thì 100 lượt
        chưa hết nửa ngày — lọc sau khi đã cắt thì gõ tên ai không bấm trong vài giờ qua sẽ ra
        "không tìm thấy" dù họ vẫn đi làm. Đẩy xuống SQL để `limit` là 100 lượt CỦA NGƯỜI ĐƯỢC TÌM.

        ⚠️ `q` lọc BÊN TRONG `employee_ids` (đã áp scope ở service), KHÔNG thay thế nó — tìm kiếm
        không được là đường vòng để thấy người ngoài phạm vi."""
        stmt = select(AttendanceLog)
        if employee_ids is not None:
            stmt = stmt.where(AttendanceLog.employee_id.in_(employee_ids))
        # `tu`/`den` là mốc UTC đã quy đổi từ NGÀY VN ở service — repo không tự đoán múi giờ.
        if tu is not None:
            stmt = stmt.where(AttendanceLog.checked_at >= tu)
        if den is not None:
            stmt = stmt.where(AttendanceLog.checked_at < den)
        kw = (q or "").strip()
        if kw:
            like = f"%{kw.lower()}%"
            stmt = stmt.join(Employee, Employee.id == AttendanceLog.employee_id).where(
                or_(func.lower(Employee.full_name).like(like),
                    func.lower(Employee.code).like(like))
            )
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
                "ca_lam": _load_ca_lam(getattr(ln, "ca_lam_json", None)),
                "ot_days": _load_ot_days(getattr(ln, "ot_days_json", None)),
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
