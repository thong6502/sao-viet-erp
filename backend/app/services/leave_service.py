"""Leave (Nghỉ phép) business logic — module `nhan_su`.

- Loại nghỉ (leave_types): HR khai (tên + cờ có-lương + hạn mức/năm).
- Đơn nghỉ (leave_requests): NV tạo (nguyên ngày) → workflow chờ duyệt → duyệt / từ chối /
  hủy. Đơn ĐÃ DUYỆT được Bảng công tháng đọc (đánh dấu P/KL). Người tạo = user đăng nhập →
  hồ sơ NV qua `employees.user_id`; HR có thể tạo hộ (truyền employee_id).
Hạn mức phép năm trừ dần + quy lương nghỉ: để module Lương (giờ chỉ đánh dấu).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from ..models.leave import (
    STATUS_APPROVED,
    STATUS_CANCELLED,
    STATUS_PENDING,
    STATUS_REJECTED,
    LeaveRequest,
    LeaveType,
)
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.employee_repo import EmployeeRepository
from ..repositories.leave_repo import LeaveRepository


class LeaveError(Exception):
    """Base for leave domain errors."""


class LeaveValidationError(LeaveError):
    """A field failed validation, or an illegal state transition."""


class LeaveNotFound(LeaveError):
    """No such leave type / request."""


class LeaveForbidden(LeaveError):
    """Not allowed to act on this request."""


class NoLinkedEmployee(LeaveError):
    """Acting user has no linked employee — cannot self-file leave."""


def _clean(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    return v or None


class LeaveService:
    def __init__(
        self,
        leaves: LeaveRepository,
        employees: EmployeeRepository,
        audit: AuditLogRepository,
    ) -> None:
        self.leaves = leaves
        self.employees = employees
        self.audit = audit

    # --- leave types (HR) ---------------------------------------------------

    @staticmethod
    def _validate_type(name, annual_quota):
        name = (name or "").strip()
        if not name:
            raise LeaveValidationError("Tên loại nghỉ là bắt buộc.")
        q = int(annual_quota) if annual_quota is not None else 0
        if q < 0:
            raise LeaveValidationError("Hạn mức/năm không được âm.")
        return name, q

    def list_types(self, *, active_only: bool = False) -> list[LeaveType]:
        return self.leaves.list_types(active_only=active_only)

    def create_type(self, *, actor, name, is_paid=True, annual_quota=0, note=None) -> LeaveType:
        name, q = self._validate_type(name, annual_quota)
        t = self.leaves.create_type(name=name, is_paid=bool(is_paid), annual_quota=q,
                                    note=_clean(note), is_active=True)
        self.audit.create(actor_user_id=actor.id, action="create_leave_type",
                          target=f"leave_type:{t.id}", detail=f"{name} paid={t.is_paid} quota={q}")
        return t

    def update_type(self, *, actor, type_id, name, is_paid=True, annual_quota=0, note=None, is_active=True) -> LeaveType:
        t = self.leaves.get_type(type_id)
        if t is None:
            raise LeaveNotFound("Không tìm thấy loại nghỉ.")
        name, q = self._validate_type(name, annual_quota)
        self.leaves.update_type(t, name=name, is_paid=bool(is_paid), annual_quota=q,
                                note=_clean(note), is_active=bool(is_active))
        self.audit.create(actor_user_id=actor.id, action="update_leave_type",
                          target=f"leave_type:{t.id}", detail=f"{name} paid={t.is_paid}")
        return t

    def delete_type(self, *, actor, type_id) -> None:
        t = self.leaves.get_type(type_id)
        if t is None:
            raise LeaveNotFound("Không tìm thấy loại nghỉ.")
        self.leaves.delete_type(t)
        self.audit.create(actor_user_id=actor.id, action="delete_leave_type",
                          target=f"leave_type:{type_id}", detail=t.name)

    # --- requests -----------------------------------------------------------

    def _employee_for_user(self, user):
        emp = self.employees.get_by_user_id(user.id)
        if emp is None:
            raise NoLinkedEmployee("Tài khoản của bạn chưa gắn hồ sơ nhân viên.")
        return emp

    def has_employee(self, *, user) -> bool:
        return self.employees.get_by_user_id(user.id) is not None

    def create_request(self, *, actor, leave_type_id, start_date: date, end_date: date,
                       reason=None, employee_id=None) -> LeaveRequest:
        # HR có thể tạo hộ (employee_id); mặc định = hồ sơ của người đăng nhập.
        if employee_id is not None:
            emp = self.employees.get_by_id(employee_id)
            if emp is None:
                raise LeaveValidationError("Không tìm thấy nhân viên.")
        else:
            emp = self._employee_for_user(actor)

        if start_date is None or end_date is None:
            raise LeaveValidationError("Cần chọn từ ngày và đến ngày.")
        if end_date < start_date:
            raise LeaveValidationError("Đến ngày phải sau hoặc bằng từ ngày.")
        lt = self.leaves.get_type(leave_type_id)
        if lt is None or not lt.is_active:
            raise LeaveValidationError("Loại nghỉ không hợp lệ.")
        days = (end_date - start_date).days + 1

        r = self.leaves.create_request(
            employee_id=emp.id, leave_type_id=leave_type_id, start_date=start_date,
            end_date=end_date, days=days, reason=_clean(reason), status=STATUS_PENDING,
            created_by=actor.id,
        )
        self.audit.create(actor_user_id=actor.id, action="create_leave_request",
                          target=f"leave_request:{r.id}",
                          detail=f"{emp.code} {lt.name} {start_date}→{end_date} ({days}n)")
        return r

    def my_requests(self, *, user, limit: int = 100) -> list[LeaveRequest]:
        emp = self._employee_for_user(user)
        return self.leaves.list_by_employee(emp.id, limit=limit)

    def list_requests(self, *, status: str | None = None, limit: int = 200) -> list[LeaveRequest]:
        return self.leaves.list_all(status=status, limit=limit)

    def _decide(self, *, actor, request_id, new_status, note) -> LeaveRequest:
        r = self.leaves.get_request(request_id)
        if r is None:
            raise LeaveNotFound("Không tìm thấy đơn nghỉ.")
        if r.status != STATUS_PENDING:
            raise LeaveValidationError("Chỉ duyệt/từ chối được đơn đang chờ.")
        self.leaves.update_request(
            r, status=new_status, decided_by=actor.id,
            decided_at=datetime.now(timezone.utc), decision_note=_clean(note),
        )
        self.audit.create(actor_user_id=actor.id, action=f"leave_{new_status}",
                          target=f"leave_request:{r.id}", detail=f"→ {new_status}")
        return r

    def approve(self, *, actor, request_id, note=None) -> LeaveRequest:
        return self._decide(actor=actor, request_id=request_id, new_status=STATUS_APPROVED, note=note)

    def reject(self, *, actor, request_id, note=None) -> LeaveRequest:
        note = _clean(note)
        if not note:
            raise LeaveValidationError("Cần nhập lý do từ chối.")
        return self._decide(actor=actor, request_id=request_id, new_status=STATUS_REJECTED, note=note)

    def cancel(self, *, actor, request_id, is_hr: bool = False) -> LeaveRequest:
        r = self.leaves.get_request(request_id)
        if r is None:
            raise LeaveNotFound("Không tìm thấy đơn nghỉ.")
        # Người tạo hủy đơn của mình, hoặc HR hủy bất kỳ.
        if not is_hr and r.created_by != actor.id:
            raise LeaveForbidden("Bạn chỉ hủy được đơn của mình.")
        if r.status in (STATUS_REJECTED, STATUS_CANCELLED):
            raise LeaveValidationError("Đơn đã kết thúc, không hủy được.")
        self.leaves.update_request(r, status=STATUS_CANCELLED)
        self.audit.create(actor_user_id=actor.id, action="leave_cancelled",
                          target=f"leave_request:{r.id}", detail="hủy đơn")
        return r

    # --- helper cho Bảng công tháng ----------------------------------------

    def leave_day_map(self, *, year: int, month: int) -> dict[int, dict[int, dict]]:
        """{employee_id → {day(int) → {name, is_paid}}} cho các ngày NGHỈ ĐÃ DUYỆT trong
        tháng — Bảng công tháng đọc để đánh dấu P/KL."""
        import calendar

        first = date(year, month, 1)
        last = date(year, month, calendar.monthrange(year, month)[1])
        approved = self.leaves.approved_in_range(first, last)
        types = {t.id: t for t in self.leaves.list_types()}
        out: dict[int, dict[int, dict]] = {}
        for r in approved:
            lt = types.get(r.leave_type_id)
            name = lt.name if lt is not None else "Nghỉ"
            is_paid = lt.is_paid if lt is not None else True
            d = max(r.start_date, first)
            end = min(r.end_date, last)
            while d <= end:
                out.setdefault(r.employee_id, {})[d.day] = {"name": name, "is_paid": is_paid}
                d = date.fromordinal(d.toordinal() + 1)
        return out
