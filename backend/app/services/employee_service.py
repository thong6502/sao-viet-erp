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
    SHIFT_LOG_ACTION_REMOVE,
    SHIFT_LOG_ACTION_SET,
    SHIFT_LOG_KIND_BASE,
    SHIFT_LOG_ORIGIN_BASE_BULK,
    SHIFT_LOG_ORIGIN_BASE_PANEL,
    SHIFT_LOG_ORIGIN_BASE_REMOVE,
    SHIFT_LOG_ORIGIN_PROFILE,
    STATUS_ACTIVE,
    STATUS_ON_LEAVE,
    STATUS_PROBATION,
    STATUS_RESIGNED,
    STATUS_SUSPENDED,
    Employee,
)
from ..config import settings
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.employee_repo import EmployeeRepository
from ..repositories.rbac_repo import DepartmentRepository
from ..repositories.user_repo import UserRepository
from ..security import hash_password
from ..shift_notify import push_shift_changes

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
    # `pay_grade_key` ĐÃ GỠ 29/07/2026: bậc nay chỉ có MỘT đường ghi là `job_grade_id`, và
    # đường đó là TRANSITION (nâng bậc/điều chuyển) chứ không phải sửa hồ sơ thường. Để cột
    # cũ ở đây là dựng lại đúng cái bẫy hai-ô-cùng-nghĩa (C-3).
    "payroll_group", "photo_url", "note",
    # Cách tính thuế TNCN (luy_tien / khau_tru_10 / cam_ket_08) — chủ 2026-07-27.
    "pit_mode",
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
    # `pit_mode` quyết định TIỀN THUẾ của người đó ⇒ chỉ người có quyền sửa lương mới được đổi.
    "pit_mode",
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
            elif key == "job_grade_id":
                # Kiểm ở đây thay vì để FK dưới DB nổ: lỗi FK ra 500 kèm SQL, người dùng không
                # hiểu gì. Đường vào duy nhất là TẠO hồ sơ (sửa thường bị `EDITABLE_FIELDS` chặn).
                g = self._resolve_job_grade(value, None)
                out[key] = g.id if g is not None else None
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
        if employee.default_shift_id is not None:
            self.employees.set_shift_assignment(
                employee=employee,
                shift_id=employee.default_shift_id,
                effective_from=hire_date or date.today(),
                created_by=actor.id,
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
        shift_marker = clean.pop("default_shift_id", ...)
        self.employees.update(employee, **clean)
        if shift_marker is not ... and shift_marker != employee.default_shift_id:
            today = date.today()
            log = self._log_base_shift(
                employee=employee, origin=SHIFT_LOG_ORIGIN_PROFILE,
                effective_from=today, shift_id_after=shift_marker, actor=actor)
            self.employees.set_shift_assignment(
                employee=employee,
                shift_id=shift_marker,
                effective_from=today,
                created_by=actor.id,
            )
            push_shift_changes([log] if log is not None else [])
        self._sync_user_from_employee(employee)  # Đ1: đồng bộ tên/ảnh/phòng xuống tài khoản
        self.audit.create(
            actor_user_id=actor.id,
            action="update_employee",
            target=f"employee:{employee.id}",
            detail=f"{employee.code} sửa hồ sơ",
        )
        return employee, dup_nid, dup_si

    def _log_base_shift(self, *, employee, origin: str, effective_from: date,
                        shift_id_after: int | None, actor, action: str = SHIFT_LOG_ACTION_SET,
                        shift_id_before: int | None = ...):
        """Ghi lịch sử cho một lần đổi CA NỀN. KHÔNG commit — đi cùng transaction của caller.

        ⚠️ Gọi TRƯỚC `set_shift_assignment` (nếu không thì `shift_id_before` đọc ra chính giá
        trị vừa ghi). `shift_id_before=...` = tự đọc ca nền đang hiệu lực tại `effective_from`.

        Trả dòng log (hoặc None khi trước == sau) để caller gom lại đẩy thông báo SAU commit."""
        if shift_id_before is ...:
            shift_id_before = self.employees.base_shift_id_on(employee, effective_from)
        return self.employees.log_shift_change(
            employee_id=employee.id, kind=SHIFT_LOG_KIND_BASE, origin=origin, action=action,
            apply_date=effective_from, shift_id_before=shift_id_before,
            shift_id_after=shift_id_after, actor_user_id=getattr(actor, "id", None),
            notified_user_id=getattr(employee, "user_id", None),
        )

    def set_default_shift(
        self, *, employee_id: int, scope: str, actor, shift_id: int | None,
        effective_from: date,
    ):
        """Gán ca làm việc mặc định cho NV — AN TOÀN: chỉ đụng default_shift_id (không clobber
        field khác như PUT hồ sơ đầy đủ). Dùng cho panel 'Gán ca' ở Chấm công (kể cả hàng loạt)."""
        employee = self.get_employee(employee_id=employee_id, scope=scope, actor=actor)
        if employee.hire_date is not None and effective_from < employee.hire_date:
            raise EmployeeValidationError("Ngày áp dụng ca không được trước ngày vào làm.")
        log = self._log_base_shift(
            employee=employee, origin=SHIFT_LOG_ORIGIN_BASE_PANEL,
            effective_from=effective_from, shift_id_after=shift_id, actor=actor)
        assignment = self.employees.set_shift_assignment(
            employee=employee,
            shift_id=shift_id,
            effective_from=effective_from,
            created_by=actor.id,
        )
        self.audit.create(
            actor_user_id=actor.id, action="assign_default_shift",
            target=f"employee:{employee.id}",
            detail=(f"{employee.code} → ca #{shift_id} từ {effective_from.isoformat()}"
                    if shift_id else f"{employee.code} → bỏ ca từ {effective_from.isoformat()}"),
        )
        push_shift_changes([log] if log is not None else [])
        return employee, assignment

    def set_default_shift_bulk(
        self, *, employee_ids: list[int], scope: str, actor, shift_id: int | None,
        effective_from: date,
    ) -> dict:
        """Gán ca nền cho NHIỀU NV trong MỘT request + MỘT transaction.

        Ca nền là lớp áp dụng "từ ngày hiệu lực trở về sau, cho mọi tháng" — khác
        với tô ca trên lưới (chỉ đúng ngày đã tô). Đây là đường duy nhất để đặt ca
        nền sau khi gộp thao tác vào màn Phân ca tháng.

        Ai VÀO LÀM SAU ngày được chọn thì tự lùi mốc về đúng ngày vào làm của họ
        (`adjusted`) thay vì bị loại — người khai ca không có cách nào biết ngày vào
        làm của từng người, mà loại họ ra thì cả lô hỏng vì một người mới. Ca vẫn
        không bao giờ có hiệu lực trước khi người ta vào làm.

        NV thực sự không hợp lệ (ngoài phạm vi, không tồn tại…) đi vào `failed` KÈM
        LÝ DO — không bỏ qua im lặng; các NV còn lại vẫn được ghi.
        """
        updated = 0
        adjusted = 0
        failed: list[dict] = []
        logs: list = []
        for eid in employee_ids:
            try:
                employee = self.get_employee(employee_id=eid, scope=scope, actor=actor)
                eff = effective_from
                if employee.hire_date is not None and eff < employee.hire_date:
                    eff = employee.hire_date
                    adjusted += 1
                # Log đi CÙNG transaction của cả lô (commit=False ở dưới) — không commit riêng
                # từng dòng, nếu không lỗi giữa chừng để lại lịch sử ghi một nửa.
                log = self._log_base_shift(
                    employee=employee, origin=SHIFT_LOG_ORIGIN_BASE_BULK,
                    effective_from=eff, shift_id_after=shift_id, actor=actor)
                if log is not None:
                    logs.append(log)
                self.employees.set_shift_assignment(
                    employee=employee, shift_id=shift_id,
                    effective_from=eff, created_by=actor.id, commit=False,
                )
                updated += 1
            except EmployeeError as exc:
                failed.append({"employee_id": eid, "reason": str(exc)})
        self.employees.commit()
        self.audit.create(
            actor_user_id=actor.id, action="assign_default_shift_bulk",
            target=f"employee_shift_bulk:{effective_from.isoformat()}",
            detail=(f"{updated} NV → ca #{shift_id} từ {effective_from.isoformat()}"
                    if shift_id else f"{updated} NV → bỏ ca từ {effective_from.isoformat()}")
                   + (f" · {adjusted} NV lùi về ngày vào làm" if adjusted else "")
                   + (f" · {len(failed)} NV bị bỏ qua" if failed else ""),
        )
        notified, not_notified = push_shift_changes(logs)
        return {"updated": updated, "adjusted": adjusted, "failed": failed,
                "changed": len(logs), "notified": notified, "not_notified": not_notified}

    def delete_shift_assignment(self, *, employee_id: int, assignment_id: int, scope: str, actor):
        """Gỡ một mốc ca nền gán nhầm. Không có đường này thì mọi lần gán nhầm đều
        VĨNH VIỄN — chỉ đè được bằng mốc khác đúng ngày hiệu lực của nó, mà người dùng
        không có cách nào đoán ra ngày đó."""
        employee = self.get_employee(employee_id=employee_id, scope=scope, actor=actor)
        # Đọc mốc TRƯỚC khi xoá — sau đó không còn gì để biết nó vốn là ca gì, ngày nào.
        goc = next((a for a in self.employees.list_shift_assignments(employee.id)
                    if a.id == assignment_id), None)
        if not self.employees.delete_shift_assignment(employee, assignment_id):
            raise EmployeeNotFound("Không tìm thấy mốc ca này của nhân viên.")
        log = None
        if goc is not None:
            # Gỡ mốc ⇒ ca rơi về mốc CÒN LẠI đang hiệu lực (đọc SAU khi xoá mới ra đúng).
            log = self._log_base_shift(
                employee=employee, origin=SHIFT_LOG_ORIGIN_BASE_REMOVE,
                action=SHIFT_LOG_ACTION_REMOVE, effective_from=goc.effective_from,
                shift_id_before=goc.shift_id,
                shift_id_after=self.employees.base_shift_id_on(employee, goc.effective_from),
                actor=actor)
            self.employees.commit()
        self.audit.create(
            actor_user_id=actor.id, action="delete_shift_assignment",
            target=f"employee:{employee.id}", detail=f"{employee.code} → xóa mốc #{assignment_id}",
        )
        push_shift_changes([log] if log is not None else [])
        return employee

    def list_shift_assignments(self, *, employee_id: int, scope: str, actor):
        self.get_employee(employee_id=employee_id, scope=scope, actor=actor)
        return self.employees.list_shift_assignments(employee_id)

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

    def decide_update_request(self, *, request_id: int, actor, approve: bool, scope: str,
                              note=None, can_edit_salary: bool = True):
        """Duyệt / từ chối yêu cầu NV xin sửa hồ sơ.

        Chủ chốt 29/07/2026: **YC cập nhật hồ sơ do bên NHÂN SỰ duyệt**. Hiện chỉ HCNS có
        `nhan_su.can_approve` (scope `all`) nên chốt phạm vi dưới đây không đổi hành vi hôm nay —
        nó là lớp khoá dự phòng, để mai kia cấp quyền duyệt cho một vai scope `department` thì
        người đó cũng chỉ duyệt được hồ sơ trong tổ mình."""
        req = self.employees.get_update_request(request_id)
        if req is None:
            raise EmployeeNotFound("Không tìm thấy yêu cầu cập nhật.")
        nv = self.employees.get_by_id(req.employee_id)
        if nv is not None and not self.employees.can_access(employee=nv, scope=scope, actor=actor):
            raise EmployeeForbidden("Nhân viên này ngoài phạm vi quản lý của bạn.")
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

    def _is_system_account(self, user_id: int | None) -> bool:
        """Hồ sơ này có đang gắn tài khoản QUẢN TRỊ HỆ THỐNG (`settings.seed_admin_username`) không?"""
        if user_id is None:
            return False
        account = self.users.get_by_id(user_id)
        return account is not None and account.username == settings.seed_admin_username

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
        new_job_grade_id: int | None = None,
        new_position: str | None = None,
        resign_reason: str | None = None,
    ) -> Employee:
        employee = self.get_employee(employee_id=employee_id, scope=scope, actor=actor)
        note = _clean(note)
        effective_date = effective_date or date.today()

        if kind in _STATUS_TRANSITIONS:
            return self._apply_status(employee, actor, kind, effective_date, note, resign_reason)
        if kind == "transfer":
            return self._apply_transfer(
                employee, actor, effective_date, note, new_department_id,
                new_job_grade=new_job_grade, new_job_grade_id=new_job_grade_id,
            )
        if kind == "promote":
            return self._apply_promote(employee, actor, effective_date, note, new_job_grade,
                                       new_position, new_job_grade_id)
        raise EmployeeValidationError(f"Loại thao tác không hợp lệ: {kind!r}")

    def _apply_status(self, employee, actor, kind, effective_date, note, resign_reason) -> Employee:
        allowed_from, to_status, event_type = _STATUS_TRANSITIONS[kind]
        if employee.status not in allowed_from:
            raise EmployeeValidationError(
                f"Không thể '{kind}' từ trạng thái hiện tại ({employee.status})."
            )
        if kind == "resign" and self._is_system_account(employee.user_id):
            # Admin CÓ hồ sơ (seed backfill) ⇒ "nghỉ việc ⇒ chặn login" sẽ khóa cứng đường vào hệ
            # thống, mà luật là KHÔNG có cửa hậu admin ⇒ chỉ còn nước sửa DB tay. Chặn ở NGUỒN
            # thay vì đẻ ngoại lệ trong xác thực (auth_service giữ nguyên 1 luật cho mọi người).
            raise EmployeeValidationError(
                "Hồ sơ này đang gắn tài khoản quản trị hệ thống — không cho nghỉ việc "
                "(sẽ khóa cứng đường đăng nhập). Gỡ liên kết tài khoản trước nếu thật sự cần."
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

    def _apply_transfer(self, employee, actor, effective_date, note, new_department_id,
                        new_job_grade=None, new_job_grade_id=None) -> Employee:
        if employee.status == STATUS_RESIGNED:
            raise EmployeeValidationError("Nhân viên đã nghỉ việc — không điều chuyển được.")
        if new_department_id is None:
            raise EmployeeValidationError("Cần chọn phòng/tổ mới.")
        old = employee.department_id
        if old == new_department_id:
            raise EmployeeValidationError("Phòng/tổ mới trùng phòng hiện tại.")
        # Chuyển tổ thì bậc phải khai LẠI theo tổ mới: không khai gì ⇒ XOÁ bậc, chứ không kéo
        # nhãn bậc của tổ cũ sang tổ mới (bậc tổ In không có nghĩa gì ở tổ Dán).
        grade = self._resolve_job_grade(new_job_grade_id, _clean(new_job_grade))
        self.employees.update(
            employee, department_id=new_department_id,
            job_grade_id=(grade.id if grade is not None else None),
        )
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
            self._apply_transfer(emp, actor, date.today(), note, target_department_id)
        return len(employees)

    def _apply_promote(self, employee, actor, effective_date, note, new_job_grade, new_position,
                       new_job_grade_id=None) -> Employee:
        if employee.status == STATUS_RESIGNED:
            raise EmployeeValidationError("Nhân viên đã nghỉ việc — không nâng bậc được.")
        new_job_grade = _clean(new_job_grade)
        new_position = _clean(new_position)
        # Từ 29/07/2026 bậc là DANH MỤC (`job_grade_id`). `new_job_grade` (chữ) chỉ còn cho
        # tương thích API cũ: có chữ mà không có id thì tra ngược danh mục theo tên.
        grade = self._resolve_job_grade(new_job_grade_id, new_job_grade)
        if grade is None and new_position is None:
            raise EmployeeValidationError("Cần chọn bậc tay nghề mới hoặc chức danh mới.")
        old_label = self._grade_label(employee)
        updates: dict = {}
        if grade is not None:
            updates["job_grade_id"] = grade.id
        if new_position is not None:
            updates["position"] = new_position
        self.employees.update(employee, **updates)
        new_label = grade.name if grade is not None else old_label
        self.employees.add_event(
            employee_id=employee.id,
            event_type=EVENT_PROMOTED,
            effective_date=effective_date,
            field="job_grade",
            from_value=old_label,
            to_value=new_label,
            note=note,
            actor_user_id=actor.id,
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="employee_promoted",
            target=f"employee:{employee.id}",
            detail=f"{employee.code} bậc {old_label}→{new_label}",
        )
        return employee

    # --- Bậc tay nghề (danh mục) --------------------------------------------

    def _grade_label(self, employee) -> str | None:
        """Tên bậc để hiển thị / ghi Quá trình công tác. Rơi về cột chữ CŨ khi hồ sơ chưa được
        gán bậc danh mục — người cũ vẫn thấy đúng bậc mình đang mang."""
        if employee.job_grade_id is not None:
            g = self.employees.get_job_grade(employee.job_grade_id)
            if g is not None:
                return g.name
        return employee.job_grade

    def _resolve_job_grade(self, grade_id, label):
        """Ra đối tượng bậc từ id (chính) hoặc từ tên (tương thích API cũ). None = không đổi bậc."""
        if grade_id is not None:
            g = self.employees.get_job_grade(int(grade_id))
            if g is None:
                raise EmployeeValidationError("Bậc tay nghề không tồn tại.")
            if not g.is_active:
                raise EmployeeValidationError(f"Bậc '{g.name}' đang tắt — bật lại rồi mới gán được.")
            return g
        if label:
            g = self.employees.find_job_grade_by_name(label)
            if g is None:
                raise EmployeeValidationError(
                    f"Chưa có bậc '{label}' trong danh mục. Thêm vào danh mục bậc rồi chọn lại.")
            return g
        return None

    def list_job_grades(self, *, active_only: bool = False):
        return self.employees.list_job_grades(active_only=active_only)

    def create_job_grade(self, *, actor, name: str, code: str | None = None,
                         seq: int | None = None, note: str | None = None):
        name = _clean(name)
        if not name:
            raise EmployeeValidationError("Cần nhập tên bậc.")
        if self.employees.find_job_grade_by_name(name) is not None:
            raise EmployeeValidationError(f"Bậc '{name}' đã có trong danh mục.")
        code = _clean(code) or f"bac_{self.employees.next_job_grade_seq()}"
        if self.employees.get_job_grade_by_code(code) is not None:
            raise EmployeeValidationError(f"Mã bậc '{code}' đã dùng.")
        g = self.employees.create_job_grade(
            code=code, name=name, note=_clean(note),
            seq=self.employees.next_job_grade_seq() if seq is None else int(seq),
        )
        self.audit.create(actor_user_id=actor.id, action="job_grade_created",
                          target=f"job_grade:{g.id}", detail=g.name)
        return g

    def update_job_grade(self, *, actor, grade_id: int, **fields):
        g = self.employees.get_job_grade(grade_id)
        if g is None:
            raise EmployeeNotFound("Không tìm thấy bậc tay nghề.")
        clean = {k: v for k, v in fields.items()
                 if k in ("name", "seq", "is_active", "note") and v is not None}
        if "name" in clean:
            clean["name"] = _clean(clean["name"])
            if not clean["name"]:
                raise EmployeeValidationError("Cần nhập tên bậc.")
            dup = self.employees.find_job_grade_by_name(clean["name"])
            if dup is not None and dup.id != g.id:
                raise EmployeeValidationError(f"Bậc '{clean['name']}' đã có trong danh mục.")
        g = self.employees.update_job_grade(g, **clean)
        self.audit.create(actor_user_id=actor.id, action="job_grade_updated",
                          target=f"job_grade:{g.id}", detail=g.name)
        return g

    def delete_job_grade(self, *, actor, grade_id: int) -> None:
        """Xoá CHỈ khi không ai đang mang bậc này — xoá bừa là hồ sơ trỏ vào bậc không còn tồn
        tại, mất luôn thông tin bậc của người ta. Muốn ẩn thì tắt `is_active`."""
        g = self.employees.get_job_grade(grade_id)
        if g is None:
            raise EmployeeNotFound("Không tìm thấy bậc tay nghề.")
        used = self.employees.count_employees_with_grade(grade_id)
        if used:
            raise EmployeeValidationError(
                f"Còn {used} nhân viên đang ở bậc '{g.name}' — không xoá được. "
                f"Chuyển họ sang bậc khác, hoặc TẮT bậc này để thôi dùng mà vẫn giữ lịch sử.")
        name = g.name
        self.employees.delete_job_grade(g)
        self.audit.create(actor_user_id=actor.id, action="job_grade_deleted",
                          target=f"job_grade:{grade_id}", detail=name)

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
