"""Employee data access (Hồ sơ nhân sự / `nhan_su`) — the ONLY layer that touches the DB
for employees, events and attachments. SQL goes through SQLAlchemy bound parameters.
No business rules here (those live in EmployeeService).

Scope note: an employee's data-scope axis is `department_id`. `own` narrows to the record
linked to the acting user (`user_id == actor.id`); `department` to the actor's department;
`all` to everyone.
"""
from __future__ import annotations

from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.orm import Session

from ..models.employee import Employee, EmployeeAttachment, EmployeeEvent
from ..models.profile_request import ProfileUpdateRequest
from ..models.role import SCOPE_ALL, SCOPE_DEPARTMENT, SCOPE_OWN
from .org_scope import dept_subtree_ids

# Columns a caller may sort by (whitelist — never interpolate a raw sort key).
_SORTABLE = {
    "code": Employee.code,
    "full_name": Employee.full_name,
    "status": Employee.status,
    "hire_date": Employee.hire_date,
    "created_at": Employee.created_at,
}


class EmployeeRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- reads --------------------------------------------------------------

    def get_by_id(self, employee_id: int) -> Employee | None:
        return self.db.get(Employee, employee_id)

    def get_by_user_id(self, user_id: int) -> Employee | None:
        """The employee linked to this login account, if any (UNIQUE user_id)."""
        return self.db.execute(
            select(Employee).where(Employee.user_id == user_id)
        ).scalars().first()

    def count_by_department(self, department_id: int) -> int:
        """Số HỒ SƠ nhân sự thuộc phòng (Đ2: 'số nhân sự' đếm theo hồ sơ, không theo tài
        khoản). Chỉ phòng trực tiếp — cuộn cây do service lo."""
        return self.db.execute(
            select(func.count()).select_from(Employee).where(Employee.department_id == department_id)
        ).scalar_one()

    def find_by_national_id(self, national_id: str | None) -> Employee | None:
        """First employee carrying this CCCD, for the soft duplicate warning. None for
        an empty value. Does NOT enforce uniqueness (deliberate soft check)."""
        if not national_id:
            return None
        return self.db.execute(
            select(Employee).where(Employee.national_id == national_id).order_by(Employee.id)
        ).scalars().first()

    def find_by_social_insurance_no(self, si_no: str | None) -> Employee | None:
        """First employee carrying this số sổ BHXH (soft duplicate warning)."""
        if not si_no:
            return None
        return self.db.execute(
            select(Employee).where(Employee.social_insurance_no == si_no).order_by(Employee.id)
        ).scalars().first()

    def _scope_condition(self, *, scope: str, actor):
        """WHERE expression narrowing employees to a data scope, or None for `all`."""
        if scope == SCOPE_ALL:
            return None
        if scope == SCOPE_OWN:
            return Employee.user_id == actor.id
        if scope == SCOPE_DEPARTMENT:
            # Subtree semantics (#26): phòng mình + mọi đơn vị con.
            dept_ids = dept_subtree_ids(self.db, actor.department_id)
            if not dept_ids:
                # No department → can only see own record (avoids leaking the whole table).
                return Employee.user_id == actor.id
            return Employee.department_id.in_(dept_ids)
        raise ValueError(f"Unknown scope: {scope!r}")

    def can_access(self, *, employee: Employee, scope: str, actor) -> bool:
        """Whether `actor` may see this one employee under `scope` (detail/edit guard)."""
        if scope == SCOPE_ALL:
            return True
        if scope == SCOPE_OWN:
            return employee.user_id == actor.id
        if scope == SCOPE_DEPARTMENT:
            dept_ids = dept_subtree_ids(self.db, actor.department_id)
            if not dept_ids:
                return employee.user_id == actor.id
            return employee.department_id in dept_ids
        raise ValueError(f"Unknown scope: {scope!r}")

    def list(
        self,
        *,
        scope: str,
        actor,
        q: str | None = None,
        department_id: int | None = None,
        status: str | None = None,
        has_account: bool | None = None,
        sort: str = "code",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Employee], int]:
        """Return (rows, total) for the scoped, filtered, sorted, paginated list.

        `q` matches full_name / code / national_id / phone (case-insensitive substring).
        `total` is the count BEFORE pagination so the UI can render page counts.
        """
        conditions = []
        scope_cond = self._scope_condition(scope=scope, actor=actor)
        if scope_cond is not None:
            conditions.append(scope_cond)

        if q:
            like = f"%{q.strip().lower()}%"
            conditions.append(
                or_(
                    func.lower(Employee.full_name).like(like),
                    func.lower(Employee.code).like(like),
                    func.lower(func.coalesce(Employee.national_id, "")).like(like),
                    func.lower(func.coalesce(Employee.phone, "")).like(like),
                )
            )
        if department_id is not None:
            conditions.append(Employee.department_id == department_id)
        if status is not None:
            conditions.append(Employee.status == status)
        if has_account is not None:
            conditions.append(
                Employee.user_id.isnot(None) if has_account else Employee.user_id.is_(None)
            )

        base = select(Employee)
        count_stmt = select(func.count()).select_from(Employee)
        for c in conditions:
            base = base.where(c)
            count_stmt = count_stmt.where(c)

        total = self.db.execute(count_stmt).scalar_one()

        direction = asc
        key = sort or "code"
        if key.startswith("-"):
            direction = desc
            key = key[1:]
        col = _SORTABLE.get(key, Employee.code)
        base = base.order_by(direction(col), Employee.id.asc())

        page = max(1, page)
        size = max(1, min(size, 200))
        base = base.offset((page - 1) * size).limit(size)

        rows = list(self.db.execute(base).scalars())
        return rows, total

    def list_scoped_all(self, *, scope: str, actor) -> list[Employee]:
        """Every employee visible under the caller's scope (no pagination) — for the KPI
        header roll-up which must reflect the whole scoped set, not just one page."""
        stmt = select(Employee)
        cond = self._scope_condition(scope=scope, actor=actor)
        if cond is not None:
            stmt = stmt.where(cond)
        return list(self.db.execute(stmt).scalars())

    def list_by_department(self, department_id: int) -> list[Employee]:
        """Mọi hồ sơ thuộc MỘT phòng, sắp theo mã (không phân trang, không lọc scope) —
        cho màn Phòng ban: "ai thuộc phòng nào" tính theo HỒ SƠ (Đ2), kể cả người chưa
        có tài khoản đăng nhập."""
        stmt = (
            select(Employee)
            .where(Employee.department_id == department_id)
            .order_by(Employee.code)
        )
        return list(self.db.execute(stmt).scalars())

    # --- writes -------------------------------------------------------------

    def _next_code(self) -> str:
        """Next sequential employee code: 'NV' + zero-padded number (NV001, NV002…).

        Based on the max existing NV-number so codes stay unique even after deletions
        (no reuse), following the KH### pattern.
        """
        max_n = 0
        for code in self.db.execute(select(Employee.code)).scalars():
            if code and code.startswith("NV"):
                try:
                    max_n = max(max_n, int(code[2:]))
                except ValueError:
                    continue
        return f"NV{max_n + 1:03d}"

    def create(self, **fields) -> Employee:
        employee = Employee(code=self._next_code(), **fields)
        self.db.add(employee)
        self.db.commit()
        self.db.refresh(employee)
        return employee

    def update(self, employee: Employee, **fields) -> Employee:
        """Assign the given attributes (code is never among them) and persist."""
        for key, value in fields.items():
            setattr(employee, key, value)
        self.db.commit()
        self.db.refresh(employee)
        return employee

    # --- events (Quá trình công tác) ---------------------------------------

    def add_event(self, **fields) -> EmployeeEvent:
        event = EmployeeEvent(**fields)
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def list_events(self, employee_id: int) -> list[EmployeeEvent]:
        """Timeline dọc theo effective_date desc (mới nhất trên cùng), tie-break id desc."""
        return list(
            self.db.execute(
                select(EmployeeEvent)
                .where(EmployeeEvent.employee_id == employee_id)
                .order_by(
                    EmployeeEvent.effective_date.desc().nullslast(),
                    EmployeeEvent.id.desc(),
                )
            ).scalars()
        )

    # --- attachments --------------------------------------------------------

    def add_attachment(self, **fields) -> EmployeeAttachment:
        att = EmployeeAttachment(**fields)
        self.db.add(att)
        self.db.commit()
        self.db.refresh(att)
        return att

    def get_attachment(self, attachment_id: int) -> EmployeeAttachment | None:
        return self.db.get(EmployeeAttachment, attachment_id)

    def list_attachments(self, employee_id: int) -> list[EmployeeAttachment]:
        return list(
            self.db.execute(
                select(EmployeeAttachment)
                .where(EmployeeAttachment.employee_id == employee_id)
                .order_by(EmployeeAttachment.id.desc())
            ).scalars()
        )

    def delete_attachment(self, attachment: EmployeeAttachment) -> None:
        self.db.delete(attachment)
        self.db.commit()

    # --- profile update requests (NV đề nghị → HCNS duyệt) ------------------

    def create_update_request(self, **fields) -> ProfileUpdateRequest:
        req = ProfileUpdateRequest(**fields)
        self.db.add(req)
        self.db.commit()
        self.db.refresh(req)
        return req

    def get_update_request(self, request_id: int) -> ProfileUpdateRequest | None:
        return self.db.get(ProfileUpdateRequest, request_id)

    def update_update_request(self, req: ProfileUpdateRequest, **fields) -> ProfileUpdateRequest:
        for k, v in fields.items():
            setattr(req, k, v)
        self.db.commit()
        self.db.refresh(req)
        return req

    def list_update_requests_by_employee(self, employee_id: int) -> list[ProfileUpdateRequest]:
        return list(self.db.execute(
            select(ProfileUpdateRequest)
            .where(ProfileUpdateRequest.employee_id == employee_id)
            .order_by(ProfileUpdateRequest.id.desc())
        ).scalars())

    def list_update_requests(self, *, status: str | None = None) -> list[ProfileUpdateRequest]:
        stmt = select(ProfileUpdateRequest)
        if status is not None:
            stmt = stmt.where(ProfileUpdateRequest.status == status)
        return list(self.db.execute(
            stmt.order_by(ProfileUpdateRequest.status.asc(), ProfileUpdateRequest.id.desc())
        ).scalars())
