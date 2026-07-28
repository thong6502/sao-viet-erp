"""Employee data access (Hồ sơ nhân sự / `nhan_su`) — the ONLY layer that touches the DB
for employees, events and attachments. SQL goes through SQLAlchemy bound parameters.
No business rules here (those live in EmployeeService).

Scope note: an employee's data-scope axis is `department_id`. `own` narrows to the record
linked to the acting user (`user_id == actor.id`); `department` to the actor's department;
`all` to everyone.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.orm import Session

from ..models.employee import (
    Employee,
    EmployeeAttachment,
    EmployeeEvent,
    EmployeeShiftAssignment,
    EmployeeShiftDay,
)
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

    # --- default shift history --------------------------------------------

    def list_shift_assignments(self, employee_id: int) -> list[EmployeeShiftAssignment]:
        return list(
            self.db.execute(
                select(EmployeeShiftAssignment)
                .where(EmployeeShiftAssignment.employee_id == employee_id)
                .order_by(
                    EmployeeShiftAssignment.effective_from.desc(),
                    EmployeeShiftAssignment.id.desc(),
                )
            ).scalars()
        )

    def shift_assignment_on(self, employee_id: int, on: date) -> EmployeeShiftAssignment | None:
        return self.db.execute(
            select(EmployeeShiftAssignment)
            .where(
                EmployeeShiftAssignment.employee_id == employee_id,
                EmployeeShiftAssignment.effective_from <= on,
            )
            .order_by(
                EmployeeShiftAssignment.effective_from.desc(),
                EmployeeShiftAssignment.id.desc(),
            )
            .limit(1)
        ).scalars().first()

    def shift_day_on(self, employee_id: int, on: date) -> EmployeeShiftDay | None:
        return self.db.execute(
            select(EmployeeShiftDay).where(
                EmployeeShiftDay.employee_id == employee_id,
                EmployeeShiftDay.work_date == on,
            )
        ).scalars().first()

    def shift_id_on(self, employee: Employee, on: date) -> int | None:
        """Resolve the shift on a date, preserving legacy employees.

        Order: ca khai riêng cho NGÀY đó (lưới phân ca) → mốc hiệu lực → cache
        ``default_shift_id``. Before an employee has any versioned assignment,
        ``default_shift_id`` is the compatibility source. Once history exists, a
        date before its first row intentionally means "no shift", not the cached
        current value.

        Dòng per-day chỉ thắng khi có ``shift_id``. Dòng ``is_off`` (nghỉ theo
        lịch) cố ý TRONG SUỐT với bước này: nghỉ luân phiên là dấu KẾ HOẠCH, nó
        không được chặn người bị gọi đi làm hôm đó chấm công (họ vẫn hưởng 1× như
        ngày thường). Nhờ chỉ hành động khi ``shift_id`` khác NULL, hàm cũng không
        vướng chỗ dễ sai "không có dòng" vs "dòng NULL".
        """
        day = self.shift_day_on(employee.id, on)
        if day is not None and day.shift_id is not None:
            return day.shift_id
        row = self.shift_assignment_on(employee.id, on)
        if row is not None:
            return row.shift_id
        has_history = self.db.execute(
            select(EmployeeShiftAssignment.id)
            .where(EmployeeShiftAssignment.employee_id == employee.id)
            .limit(1)
        ).first()
        return None if has_history is not None else employee.default_shift_id

    def delete_shift_assignment(self, employee: Employee, assignment_id: int) -> bool:
        """Xóa một MỐC ca nền gán nhầm. Trả False nếu mốc không thuộc NV này.

        Sau khi xóa, đồng bộ lại `default_shift_id` theo mốc mới nhất còn lại — nó là
        cache của mốc hiện hành, để lệch thì các màn cũ hiển thị sai. Nếu không còn mốc
        nào thì GIỮ NGUYÊN giá trị cũ: `shift_id_on` lúc đó rơi về `default_shift_id`,
        xóa nó đi là NV mất ca và không chấm công được.
        """
        row = self.db.get(EmployeeShiftAssignment, assignment_id)
        if row is None or row.employee_id != employee.id:
            return False
        self.db.delete(row)
        self.db.flush()
        remaining = self.list_shift_assignments(employee.id)
        if remaining:
            employee.default_shift_id = remaining[0].shift_id
        self.db.commit()
        self.db.refresh(employee)
        return True

    def shift_is_referenced(self, shift_id: int) -> bool:
        history_ref = self.db.execute(
            select(EmployeeShiftAssignment.id)
            .where(EmployeeShiftAssignment.shift_id == shift_id)
            .limit(1)
        ).first()
        if history_ref is not None:
            return True
        # Ca chỉ được dùng trong lưới phân ca ngày cũng là ĐANG DÙNG. Bỏ nhánh này
        # thì xóa được ca đó, những ngày đã khai sẽ trỏ vào ca không tồn tại và
        # mất công một cách im lặng.
        day_ref = self.db.execute(
            select(EmployeeShiftDay.id).where(EmployeeShiftDay.shift_id == shift_id).limit(1)
        ).first()
        if day_ref is not None:
            return True
        legacy_ref = self.db.execute(
            select(Employee.id).where(Employee.default_shift_id == shift_id).limit(1)
        ).first()
        return legacy_ref is not None

    def shift_days_map(
        self, employee_ids: set[int] | None, start: date, end: date
    ) -> dict[tuple[int, date], EmployeeShiftDay]:
        """Mọi ô đã khai trong [start, end] — 1 query, để cắt N+1 của lưới NV × ngày.

        Key vắng mặt = ngày đó không khai riêng (kế thừa mốc). Trả nguyên dòng để
        caller phân biệt được "ca cụ thể" với "nghỉ theo lịch" (`is_off`).
        """
        stmt = select(EmployeeShiftDay).where(
            EmployeeShiftDay.work_date >= start, EmployeeShiftDay.work_date <= end
        )
        if employee_ids is not None:
            if not employee_ids:
                return {}
            stmt = stmt.where(EmployeeShiftDay.employee_id.in_(employee_ids))
        return {(r.employee_id, r.work_date): r for r in self.db.execute(stmt).scalars()}

    def upsert_shift_day(
        self, *, employee_id: int, work_date: date, shift_id: int | None,
        is_off: bool, created_by: int | None,
    ) -> EmployeeShiftDay:
        """Ghi 1 ô. KHÔNG commit — caller gom cả lô rồi commit một lần (lưới có thể
        tới ~1.800 ô; commit từng ô sẽ chết)."""
        row = self.shift_day_on(employee_id, work_date)
        if row is None:
            row = EmployeeShiftDay(
                employee_id=employee_id, work_date=work_date,
                shift_id=shift_id, is_off=is_off, created_by=created_by,
            )
            self.db.add(row)
        else:
            row.shift_id = shift_id
            row.is_off = is_off
            row.created_by = created_by
        return row

    def delete_shift_day(self, employee_id: int, work_date: date) -> bool:
        """Xóa ô → ngày đó quay về kế thừa ca mặc định. KHÔNG commit (xem trên)."""
        row = self.shift_day_on(employee_id, work_date)
        if row is None:
            return False
        self.db.delete(row)
        return True

    def commit(self) -> None:
        """Chốt lô ghi lưới phân ca — ranh giới transaction do caller quyết định vì
        một lần lưu có thể tới hàng nghìn ô."""
        self.db.commit()

    def set_shift_assignment(
        self,
        *,
        employee: Employee,
        shift_id: int | None,
        effective_from: date,
        created_by: int | None,
        commit: bool = True,
    ) -> EmployeeShiftAssignment:
        history = self.list_shift_assignments(employee.id)

        # Preserve the legacy value as the first historical period before adding
        # a later change. This keeps old attendance months stable.
        if not history and employee.default_shift_id is not None:
            baseline = employee.hire_date or date(1900, 1, 1)
            if baseline < effective_from:
                self.db.add(EmployeeShiftAssignment(
                    employee_id=employee.id,
                    shift_id=employee.default_shift_id,
                    effective_from=baseline,
                    created_by=created_by,
                ))

        row = self.db.execute(
            select(EmployeeShiftAssignment).where(
                EmployeeShiftAssignment.employee_id == employee.id,
                EmployeeShiftAssignment.effective_from == effective_from,
            )
        ).scalars().first()
        if row is None:
            row = EmployeeShiftAssignment(
                employee_id=employee.id,
                shift_id=shift_id,
                effective_from=effective_from,
                created_by=created_by,
            )
            self.db.add(row)
        else:
            row.shift_id = shift_id
            row.created_by = created_by

        # Compatibility cache used by older screens. Attendance calculations use
        # the versioned history above and therefore remain correct for old dates.
        employee.default_shift_id = shift_id
        # `commit=False` cho đường gán HÀNG LOẠT: gom cả lô vào một transaction thay
        # vì commit từng người (gán cả tổ = hàng chục commit, và lỗi giữa chừng để lại
        # trạng thái ghi một nửa).
        if commit:
            self.db.commit()
            self.db.refresh(row)
            self.db.refresh(employee)
        else:
            self.db.flush()
        return row

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
