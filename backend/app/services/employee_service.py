"""Employee (Hồ sơ nhân sự / `nhan_su`) business logic — lát #1.

Framework-agnostic: raises domain errors the router maps to HTTP. Enforces:
  - full_name required (non-blank);
  - CCCD / số sổ BHXH duplicates are SOFT warnings — the employee is STILL saved;
  - status / gender / event_type must be a known enum value;
  - every stage change (status / department / job_grade) goes through a TRANSITION that
    writes an `employee_events` row (Quá trình công tác) — never a bare column edit;
  - a resigned employee's hồ sơ is read-only (edit blocked; only `reinstate` reopens it);
  - `user_id` link is 1–1 (one login ↔ at most one employee);
  - every create/update/transition writes an AuditLog (target `employee:<id>`).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from ..models.employee import (
    ATTACHMENT_DOC_KINDS,
    DOC_KHAC,
    EMPLOYEE_STATUSES,
    EVENT_CONFIRMED,
    EVENT_HIRED,
    EVENT_LEAVE_END,
    EVENT_LEAVE_START,
    EVENT_PROMOTED,
    EVENT_REINSTATED,
    EVENT_RESIGNED,
    EVENT_SUSPENDED,
    EVENT_TRANSFERRED,
    GENDERS,
    STATUS_ACTIVE,
    STATUS_ON_LEAVE,
    STATUS_PROBATION,
    STATUS_RESIGNED,
    STATUS_SUSPENDED,
    Employee,
)
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.employee_repo import EmployeeRepository
from ..repositories.rbac_repo import DepartmentRepository
from ..repositories.user_repo import UserRepository
from ..security import hash_password

# Status transitions: kind → (allowed from-statuses, resulting status, event_type).
_STATUS_TRANSITIONS: dict[str, tuple[set[str], str, str]] = {
    "confirm": ({STATUS_PROBATION}, STATUS_ACTIVE, EVENT_CONFIRMED),
    "leave_start": ({STATUS_ACTIVE}, STATUS_ON_LEAVE, EVENT_LEAVE_START),
    "leave_end": ({STATUS_ON_LEAVE}, STATUS_ACTIVE, EVENT_LEAVE_END),
    "suspend": ({STATUS_PROBATION, STATUS_ACTIVE, STATUS_ON_LEAVE}, STATUS_SUSPENDED, EVENT_SUSPENDED),
    "resign": ({STATUS_PROBATION, STATUS_ACTIVE, STATUS_ON_LEAVE, STATUS_SUSPENDED}, STATUS_RESIGNED, EVENT_RESIGNED),
    "reinstate": ({STATUS_RESIGNED}, STATUS_ACTIVE, EVENT_REINSTATED),
}
# Fields the plain edit (PUT) may set — deliberately EXCLUDES status/department_id/job_grade
# and resign_*, which only a transition may change.
EDITABLE_FIELDS = (
    "full_name", "position", "probation_end_date", "date_of_birth", "gender",
    "national_id", "national_id_date", "national_id_place", "phone", "email",
    "permanent_address", "current_address", "emergency_contact_name",
    "emergency_contact_phone", "social_insurance_no", "pit_tax_code",
    "dependents_count", "bank_account", "bank_name", "default_shift_id",
    "payroll_group", "pay_grade_key", "photo_url", "note",
)

# Nhân viên tự sửa ("Hồ sơ của tôi") — CHỈ các field liên lạc, không đụng định danh/pháp
# lý/tiền. Backend là cổng thật: whitelist cứng, không tin FE.
SELF_EDITABLE_FIELDS = (
    "phone", "email", "current_address", "emergency_contact_name", "emergency_contact_phone",
)

# NV chỉ được ĐỀ NGHỊ đổi (HCNS duyệt mới áp) — các field định danh/pháp lý/ngân hàng.
REQUESTABLE_FIELDS = (
    "full_name", "date_of_birth", "national_id", "national_id_date", "national_id_place",
    "permanent_address", "bank_account", "bank_name", "dependents_count",
)

# Field lương/BHXH nhạy cảm — chỉ GHI được nếu actor có quyền `nhan_su:edit_salary` (N5).
# Dùng CHUNG với router (che khi đọc `_mask_salary`) để đọc/ghi đối xứng, không lệch danh sách.
SENSITIVE_FIELDS = (
    "social_insurance_no", "pit_tax_code", "bank_account", "bank_name",
    "payroll_group", "pay_grade_key",
)


class EmployeeError(Exception):
    """Base for employee domain errors."""


class EmployeeValidationError(EmployeeError):
    """A field failed validation, or an illegal state transition was requested."""


class EmployeeNotFound(EmployeeError):
    """No employee with that id (or not visible under the caller's scope)."""


class EmployeeForbidden(EmployeeError):
    """The employee exists but is outside the caller's data scope."""


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


class EmployeeService:
    def __init__(
        self,
        employees: EmployeeRepository,
        audit: AuditLogRepository,
        users: UserRepository,
        departments: DepartmentRepository,
    ) -> None:
        self.employees = employees
        self.audit = audit
        self.users = users
        self.departments = departments

    # --- validation helpers -------------------------------------------------

    @staticmethod
    def _validate_name(name: str | None) -> str:
        name = (name or "").strip()
        if not name:
            raise EmployeeValidationError("Họ tên là bắt buộc.")
        return name

    @staticmethod
    def _validate_gender(gender: str | None) -> str | None:
        gender = _clean(gender)
        if gender is not None and gender not in GENDERS:
            raise EmployeeValidationError("Giới tính không hợp lệ.")
        return gender

    @staticmethod
    def _validate_status(status: str | None) -> str:
        status = (status or STATUS_PROBATION).strip()
        if status not in EMPLOYEE_STATUSES:
            raise EmployeeValidationError("Trạng thái không hợp lệ.")
        return status

    @staticmethod
    def _validate_dependents(n: int | None) -> int:
        if n is None:
            return 0
        if not isinstance(n, int) or isinstance(n, bool) or n < 0:
            raise EmployeeValidationError("Số người phụ thuộc phải là số nguyên ≥ 0.")
        return n

    def _clean_fields(self, fields: dict) -> dict:
        """Trim string inputs; validate the constrained ones. Returns a cleaned copy
        containing only recognised employee columns."""
        out: dict = {}
        for key, value in fields.items():
            if key == "full_name":
                out[key] = self._validate_name(value)
            elif key == "gender":
                out[key] = self._validate_gender(value)
            elif key == "dependents_count":
                out[key] = self._validate_dependents(value)
            elif isinstance(value, str):
                out[key] = _clean(value)
            else:
                out[key] = value
        return out

    def _sync_user_from_employee(self, employee) -> None:
        """Đồng bộ danh tính hồ sơ → tài khoản đã gắn (Đ1: hồ sơ là nguồn). No-op nếu chưa
        gắn tài khoản. Ảnh chỉ ghi khi hồ sơ có ảnh (repo tự lo)."""
        if employee.user_id is None:
            return
        user = self.users.get_by_id(employee.user_id)
        if user is not None:
            self.users.sync_from_employee(
                user, name=employee.full_name,
                department_id=employee.department_id, avatar_url=employee.photo_url,
            )

    # --- reads --------------------------------------------------------------

    def list_employees(self, **kwargs) -> tuple[list[Employee], int]:
        return self.employees.list(**kwargs)

    def list_scoped_all(self, *, scope: str, actor) -> list[Employee]:
        return self.employees.list_scoped_all(scope=scope, actor=actor)

    def get_employee(self, *, employee_id: int, scope: str, actor) -> Employee:
        employee = self.employees.get_by_id(employee_id)
        if employee is None:
            raise EmployeeNotFound("Không tìm thấy nhân viên.")
        if not self.employees.can_access(employee=employee, scope=scope, actor=actor):
            raise EmployeeForbidden("Bạn không có quyền xem nhân viên này.")
        return employee

    def find_duplicates(
        self, *, national_id: str | None, social_insurance_no: str | None, exclude_id: int | None = None
    ) -> tuple[Employee | None, Employee | None]:
        """(dup_by_CCCD, dup_by_BHXH) — soft warnings; either may be None. A row matching
        `exclude_id` (itself, on edit) is not a duplicate."""
        dup_nid = self.employees.find_by_national_id(_clean(national_id))
        dup_si = self.employees.find_by_social_insurance_no(_clean(social_insurance_no))
        if dup_nid is not None and dup_nid.id == exclude_id:
            dup_nid = None
        if dup_si is not None and dup_si.id == exclude_id:
            dup_si = None
        return dup_nid, dup_si

    def list_events(self, *, employee_id: int, scope: str, actor):
        self.get_employee(employee_id=employee_id, scope=scope, actor=actor)
        return self.employees.list_events(employee_id)

    def list_attachments(self, *, employee_id: int, scope: str, actor):
        self.get_employee(employee_id=employee_id, scope=scope, actor=actor)
        return self.employees.list_attachments(employee_id)

    # --- create -------------------------------------------------------------

    def create_employee(
        self,
        *,
        actor,
        department_id: int | None,
        status: str | None,
        hire_date: date | None,
        fields: dict,
        can_edit_salary: bool = True,
    ) -> tuple[Employee, Employee | None, Employee | None]:
        """Create an employee, record the first 'hired' event, return
        (employee, dup_by_CCCD, dup_by_BHXH). A duplicate does NOT block creation."""
        status = self._validate_status(status)
        # N5: thiếu quyền edit_salary → bỏ field lương/BHXH ngay khi tạo (không lưu lén).
        if not can_edit_salary:
            fields = {k: v for k, v in fields.items() if k not in SENSITIVE_FIELDS}
        clean = self._clean_fields(fields)
        clean["full_name"] = self._validate_name(clean.get("full_name"))

        dup_nid, dup_si = self.find_duplicates(
            national_id=clean.get("national_id"),
            social_insurance_no=clean.get("social_insurance_no"),
        )

        employee = self.employees.create(
            department_id=department_id,
            status=status,
            hire_date=hire_date,
            **clean,
        )
        # First stage on the Quá trình công tác timeline (effective = ngày vào).
        self.employees.add_event(
            employee_id=employee.id,
            event_type=EVENT_HIRED,
            effective_date=hire_date,
            field="status",
            from_value=None,
            to_value=status,
            note="Vào làm",
            actor_user_id=actor.id,
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="create_employee",
            target=f"employee:{employee.id}",
            detail=f"{employee.code} {employee.full_name}",
        )
        return employee, dup_nid, dup_si

    # --- edit (no stage change) --------------------------------------------

    def update_employee(
        self, *, employee_id: int, scope: str, actor, fields: dict,
        can_edit_salary: bool = True,
    ) -> tuple[Employee, Employee | None, Employee | None]:
        """Edit hồ sơ (personal / BHXH / contacts). Does NOT touch status /
        department / job_grade (those are transitions). Blocked once resigned."""
        employee = self.get_employee(employee_id=employee_id, scope=scope, actor=actor)
        if employee.status == STATUS_RESIGNED:
            raise EmployeeValidationError(
                "Hồ sơ đã nghỉ việc (khóa sửa). Dùng 'Tuyển lại' nếu cần mở lại."
            )
        clean = {k: v for k, v in fields.items() if k in EDITABLE_FIELDS}
        # N5: thiếu quyền edit_salary → bỏ field lương/BHXH khỏi bản ghi (không chặn cả request).
        if not can_edit_salary:
            clean = {k: v for k, v in clean.items() if k not in SENSITIVE_FIELDS}
        clean = self._clean_fields(clean)
        if "full_name" in clean:
            clean["full_name"] = self._validate_name(clean["full_name"])

        dup_nid, dup_si = self.find_duplicates(
            national_id=clean.get("national_id", employee.national_id),
            social_insurance_no=clean.get("social_insurance_no", employee.social_insurance_no),
            exclude_id=employee.id,
        )
        self.employees.update(employee, **clean)
        self._sync_user_from_employee(employee)  # Đ1: đồng bộ tên/ảnh/phòng xuống tài khoản
        self.audit.create(
            actor_user_id=actor.id,
            action="update_employee",
            target=f"employee:{employee.id}",
            detail=f"{employee.code} sửa hồ sơ",
        )
        return employee, dup_nid, dup_si

    def set_default_shift(self, *, employee_id: int, scope: str, actor, shift_id: int | None) -> Employee:
        """Gán ca làm việc mặc định cho NV — AN TOÀN: chỉ đụng default_shift_id (không clobber
        field khác như PUT hồ sơ đầy đủ). Dùng cho panel 'Gán ca' ở Chấm công (kể cả hàng loạt)."""
        employee = self.get_employee(employee_id=employee_id, scope=scope, actor=actor)
        self.employees.update(employee, default_shift_id=shift_id)
        self.audit.create(
            actor_user_id=actor.id, action="assign_default_shift",
            target=f"employee:{employee.id}",
            detail=(f"{employee.code} → ca #{shift_id}" if shift_id else f"{employee.code} → bỏ ca"),
        )
        return employee

    # --- self-service "Hồ sơ của tôi" (nhân viên thường) --------------------

    def my_employee(self, *, user) -> Employee | None:
        """Hồ sơ gắn với tài khoản đang đăng nhập (qua employees.user_id), hoặc None."""
        return self.employees.get_by_user_id(user.id)

    def my_events(self, *, user):
        emp = self.employees.get_by_user_id(user.id)
        return self.employees.list_events(emp.id) if emp is not None else []

    def my_attachments(self, *, user):
        emp = self.employees.get_by_user_id(user.id)
        return self.employees.list_attachments(emp.id) if emp is not None else []

    def update_my_contact(self, *, user, fields: dict) -> Employee:
        """NV tự cập nhật liên lạc của CHÍNH MÌNH — whitelist SELF_EDITABLE_FIELDS."""
        emp = self.employees.get_by_user_id(user.id)
        if emp is None:
            raise EmployeeValidationError("Tài khoản chưa gắn hồ sơ nhân viên.")
        clean = self._clean_fields({k: v for k, v in fields.items() if k in SELF_EDITABLE_FIELDS})
        self.employees.update(emp, **clean)
        self.audit.create(
            actor_user_id=user.id, action="update_my_contact",
            target=f"employee:{emp.id}", detail=f"{emp.code} tự cập nhật liên lạc",
        )
        return emp

    # --- yêu cầu cập nhật hồ sơ (NV đề nghị → HCNS duyệt) -------------------

    def create_update_request(self, *, user, changes: dict, reason=None):
        emp = self.employees.get_by_user_id(user.id)
        if emp is None:
            raise EmployeeValidationError("Tài khoản chưa gắn hồ sơ nhân viên.")
        clean = self._clean_fields({k: v for k, v in (changes or {}).items() if k in REQUESTABLE_FIELDS})
        if not clean:
            raise EmployeeValidationError("Không có thay đổi hợp lệ để đề nghị.")
        # date/int về dạng chuỗi để JSON lưu gọn.
        payload = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in clean.items()}
        return self.employees.create_update_request(
            employee_id=emp.id, changes=payload, reason=_clean(reason),
        )

    def my_update_requests(self, *, user):
        emp = self.employees.get_by_user_id(user.id)
        return self.employees.list_update_requests_by_employee(emp.id) if emp is not None else []

    def list_update_requests(self, *, status=None):
        return self.employees.list_update_requests(status=status)

    def decide_update_request(self, *, request_id: int, actor, approve: bool, note=None,
                              can_edit_salary: bool = True):
        req = self.employees.get_update_request(request_id)
        if req is None:
            raise EmployeeNotFound("Không tìm thấy yêu cầu cập nhật.")
        if req.status != "pending":
            raise EmployeeValidationError("Yêu cầu đã được xử lý.")
        if approve:
            emp = self.employees.get_by_id(req.employee_id)
            if emp is None:
                raise EmployeeNotFound("Không tìm thấy nhân viên.")
            allowed = {k: v for k, v in req.changes.items() if k in REQUESTABLE_FIELDS}
            # N5: người duyệt thiếu quyền edit_salary → bỏ field nhạy cảm (bank...) khi áp.
            if not can_edit_salary:
                allowed = {k: v for k, v in allowed.items() if k not in SENSITIVE_FIELDS}
            clean = self._clean_fields(allowed)
            self.employees.update(emp, **clean)
            self._sync_user_from_employee(emp)  # Đ1: duyệt đổi tên → đồng bộ tài khoản
            self.audit.create(
                actor_user_id=actor.id, action="approve_profile_request",
                target=f"employee:{emp.id}", detail=f"{emp.code} duyệt yêu cầu #{req.id}",
            )
        return self.employees.update_update_request(
            req, status="approved" if approve else "rejected",
            decided_by=actor.id, decided_at=datetime.now(timezone.utc), decision_note=_clean(note),
        )

    # --- transitions (stage changes) ---------------------------------------

    def apply_transition(
        self,
        *,
        employee_id: int,
        scope: str,
        actor,
        kind: str,
        effective_date: date | None = None,
        note: str | None = None,
        new_department_id: int | None = None,
        new_job_grade: str | None = None,
        new_position: str | None = None,
        resign_reason: str | None = None,
    ) -> Employee:
        employee = self.get_employee(employee_id=employee_id, scope=scope, actor=actor)
        note = _clean(note)

        if kind in _STATUS_TRANSITIONS:
            return self._apply_status(employee, actor, kind, effective_date, note, resign_reason)
        if kind == "transfer":
            return self._apply_transfer(employee, actor, effective_date, note, new_department_id)
        if kind == "promote":
            return self._apply_promote(employee, actor, effective_date, note, new_job_grade, new_position)
        raise EmployeeValidationError(f"Loại thao tác không hợp lệ: {kind!r}")

    def _apply_status(self, employee, actor, kind, effective_date, note, resign_reason) -> Employee:
        allowed_from, to_status, event_type = _STATUS_TRANSITIONS[kind]
        if employee.status not in allowed_from:
            raise EmployeeValidationError(
                f"Không thể '{kind}' từ trạng thái hiện tại ({employee.status})."
            )
        old_status = employee.status
        updates: dict = {"status": to_status}
        if kind == "resign":
            resign_reason = _clean(resign_reason)
            if not resign_reason:
                raise EmployeeValidationError("Cần nhập lý do nghỉ việc.")
            updates["resign_date"] = effective_date
            updates["resign_reason"] = resign_reason
        elif kind == "reinstate":
            # Reopening: clear the resignation stamp.
            updates["resign_date"] = None
            updates["resign_reason"] = None
        self.employees.update(employee, **updates)
        if kind == "resign" and employee.user_id is not None:
            # Login đã tự chặn theo trạng thái hồ sơ, nhưng token đã phát thì vẫn còn hạn —
            # bump token_version để cắt luôn phiên đang sống của người vừa nghỉ.
            account = self.users.get_by_id(employee.user_id)
            if account is not None:
                self.users.bump_token_version(account)
        self.employees.add_event(
            employee_id=employee.id,
            event_type=event_type,
            effective_date=effective_date,
            field="status",
            from_value=old_status,
            to_value=to_status,
            note=note or resign_reason,
            actor_user_id=actor.id,
        )
        self.audit.create(
            actor_user_id=actor.id,
            action=f"employee_{event_type}",
            target=f"employee:{employee.id}",
            detail=f"{employee.code} {old_status}→{to_status}",
        )
        return employee

    def _apply_transfer(self, employee, actor, effective_date, note, new_department_id) -> Employee:
        if employee.status == STATUS_RESIGNED:
            raise EmployeeValidationError("Nhân viên đã nghỉ việc — không điều chuyển được.")
        if new_department_id is None:
            raise EmployeeValidationError("Cần chọn phòng/tổ mới.")
        old = employee.department_id
        if old == new_department_id:
            raise EmployeeValidationError("Phòng/tổ mới trùng phòng hiện tại.")
        self.employees.update(employee, department_id=new_department_id)
        self._sync_user_from_employee(employee)  # Đ1/Đ2: chuyển phòng → tài khoản đổi phòng (scope)
        # Đ2: NV đang là trưởng phòng CŨ → gỡ chức (không để head phòng cũ treo người đã đi).
        if old is not None and employee.user_id is not None:
            old_dept = self.departments.get_by_id(old)
            if old_dept is not None and old_dept.head_user_id == employee.user_id:
                self.departments.set_head(old_dept, None)
        # Vai trò thuộc ĐÚNG 1 phòng → chuyển phòng phải GỠ vai trò cũ, về mức tối thiểu tới khi
        # trưởng phòng mới gán lại (khớp bulk transfer_users). Không gỡ thì tài khoản giữ vai trò
        # của phòng khác — trạng thái mà chính API gán-vai-trò từ chối (400).
        if employee.user_id is not None:
            account = self.users.get_by_id(employee.user_id)
            if account is not None and account.role_id is not None:
                self.users.set_assignment(
                    account, department_id=new_department_id, role_id=None,
                    is_active=account.is_active,
                )
        self.employees.add_event(
            employee_id=employee.id,
            event_type=EVENT_TRANSFERRED,
            effective_date=effective_date,
            field="department",
            from_value=str(old) if old is not None else None,
            to_value=str(new_department_id),
            note=note,
            actor_user_id=actor.id,
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="employee_transferred",
            target=f"employee:{employee.id}",
            detail=f"{employee.code} phòng {old}→{new_department_id}",
        )
        return employee

    def transfer_many(
        self, *, employee_ids: list[int], target_department_id: int, scope: str, actor,
        note: str | None = None,
    ) -> int:
        """Bulk điều chuyển theo HỒ SƠ (màn Phòng ban) — kể cả người CHƯA có tài khoản.

        Kiểm tra TOÀN BỘ trước rồi mới ghi, để một id hỏng không làm chuyển dở dang. Mỗi
        người đi qua đúng luồng điều chuyển đơn `_apply_transfer` nên được: đồng bộ phòng
        xuống tài khoản, gỡ vai trò cũ, gỡ chức trưởng phòng cũ, ghi Quá trình công tác +
        nhật ký. (Bản cũ chuyển theo TÀI KHOẢN nên bỏ sót người không có tài khoản và
        không ghi Quá trình công tác.)
        """
        if self.departments.get_by_id(target_department_id) is None:
            raise EmployeeNotFound("Không tìm thấy phòng đích.")
        employees = []
        for eid in employee_ids:
            emp = self.get_employee(employee_id=eid, scope=scope, actor=actor)
            if emp.status == STATUS_RESIGNED:
                raise EmployeeValidationError(
                    f"{emp.code} đã nghỉ việc — không điều chuyển được."
                )
            if emp.department_id == target_department_id:
                raise EmployeeValidationError(f"{emp.code} đã thuộc phòng đích.")
            employees.append(emp)
        for emp in employees:
            self._apply_transfer(emp, actor, None, note, target_department_id)
        return len(employees)

    def _apply_promote(self, employee, actor, effective_date, note, new_job_grade, new_position) -> Employee:
        if employee.status == STATUS_RESIGNED:
            raise EmployeeValidationError("Nhân viên đã nghỉ việc — không nâng bậc được.")
        new_job_grade = _clean(new_job_grade)
        new_position = _clean(new_position)
        if new_job_grade is None and new_position is None:
            raise EmployeeValidationError("Cần nhập bậc thợ mới hoặc chức danh mới.")
        old_grade = employee.job_grade
        updates: dict = {}
        if new_job_grade is not None:
            updates["job_grade"] = new_job_grade
        if new_position is not None:
            updates["position"] = new_position
        self.employees.update(employee, **updates)
        self.employees.add_event(
            employee_id=employee.id,
            event_type=EVENT_PROMOTED,
            effective_date=effective_date,
            field="job_grade",
            from_value=old_grade,
            to_value=new_job_grade or employee.job_grade,
            note=note,
            actor_user_id=actor.id,
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="employee_promoted",
            target=f"employee:{employee.id}",
            detail=f"{employee.code} bậc {old_grade}→{new_job_grade}",
        )
        return employee

    # --- account link (nguoi_dung) -----------------------------------------

    def link_account(self, *, employee_id: int, scope: str, actor, user_id: int) -> Employee:
        employee = self.get_employee(employee_id=employee_id, scope=scope, actor=actor)
        user = self.users.get_by_id(user_id)
        if user is None:
            raise EmployeeValidationError("Không tìm thấy tài khoản.")
        other = self.employees.get_by_user_id(user_id)
        if other is not None and other.id != employee.id:
            raise EmployeeValidationError(f"Tài khoản này đã gắn với nhân viên {other.code}.")
        self.employees.update(employee, user_id=user_id)
        self._sync_user_from_employee(employee)  # Đ1: nối tài khoản → đồng bộ danh tính theo hồ sơ
        self.audit.create(
            actor_user_id=actor.id,
            action="employee_link_account",
            target=f"employee:{employee.id}",
            detail=f"{employee.code} ↔ user:{user_id}",
        )
        return employee

    def create_account(
        self,
        *,
        employee_id: int,
        scope: str,
        actor,
        username: str,
        password: str,
        name: str | None = None,
        role_id: int | None = None,
    ) -> tuple[Employee, object]:
        employee = self.get_employee(employee_id=employee_id, scope=scope, actor=actor)
        if employee.user_id is not None:
            raise EmployeeValidationError("Nhân viên đã có tài khoản.")
        username = (username or "").strip()
        if not username:
            raise EmployeeValidationError("Tên đăng nhập là bắt buộc.")
        if len(password or "") < 6:
            raise EmployeeValidationError("Mật khẩu tối thiểu 6 ký tự.")
        if self.users.get_by_username(username) is not None:
            raise EmployeeValidationError("Tên đăng nhập đã tồn tại.")
        user = self.users.create(
            username=username,
            name=(name or employee.full_name),
            password_hash=hash_password(password),
        )
        # Default the account's department to the employee's; role/head assigned elsewhere.
        self.users.set_assignment(
            user, department_id=employee.department_id, role_id=role_id, is_active=True
        )
        self.employees.update(employee, user_id=user.id)
        self._sync_user_from_employee(employee)  # Đ1: đồng bộ danh tính hồ sơ xuống tài khoản mới
        self.audit.create(
            actor_user_id=actor.id,
            action="employee_create_account",
            target=f"employee:{employee.id}",
            detail=f"{employee.code} → tạo user {username}",
        )
        return employee, user

    # `unlink_account` ĐÃ GỠ: mọi tài khoản phải thuộc một hồ sơ (gỡ liên kết = đẻ tài khoản
    # mồ côi). Chặn một người = KHÓA tài khoản; nghỉ việc = login tự chặn theo trạng thái hồ sơ.

    # --- attachments (router does the disk IO; service records metadata) ---

    def add_attachment(
        self, *, employee_id: int, scope: str, actor, doc_kind: str,
        file_name: str, file_url: str, file_type: str | None,
    ):
        employee = self.get_employee(employee_id=employee_id, scope=scope, actor=actor)
        if doc_kind not in ATTACHMENT_DOC_KINDS:
            doc_kind = DOC_KHAC
        att = self.employees.add_attachment(
            employee_id=employee.id,
            doc_kind=doc_kind,
            file_name=file_name,
            file_url=file_url,
            file_type=file_type,
            uploaded_by=actor.id,
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="employee_add_attachment",
            target=f"employee:{employee.id}",
            detail=f"{employee.code} + {doc_kind}: {file_name}",
        )
        return att

    def delete_attachment(self, *, employee_id: int, scope: str, actor, attachment_id: int) -> None:
        employee = self.get_employee(employee_id=employee_id, scope=scope, actor=actor)
        att = self.employees.get_attachment(attachment_id)
        if att is None or att.employee_id != employee.id:
            raise EmployeeNotFound("Không tìm thấy tệp đính kèm.")
        self.employees.delete_attachment(att)
        self.audit.create(
            actor_user_id=actor.id,
            action="employee_delete_attachment",
            target=f"employee:{employee.id}",
            detail=f"{employee.code} xóa tệp {att.file_name}",
        )
