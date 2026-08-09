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


def _working_days(start: date, end: date) -> int:
    """Số NGÀY LÀM VIỆC trong [start, end] (loại Thứ Bảy + Chủ Nhật). Là đơn vị TRỪ hạn
    mức phép năm (theo quyết định: cuối tuần không trừ phép; ngày lễ + ca cuối tuần → P2).
    KHÁC `days` lưu trên đơn (số ngày lịch, để hiển thị)."""
    if end < start:
        return 0
    n = 0
    d = start
    while d <= end:
        if d.weekday() < 5:  # Mon..Fri = 0..4
            n += 1
        d = date.fromordinal(d.toordinal() + 1)
    return n


class LeaveService:
    def __init__(
        self,
        leaves: LeaveRepository,
        employees: EmployeeRepository,
        audit: AuditLogRepository,
        calendar=None,
        late_early=None,
    ) -> None:
        self.leaves = leaves
        self.employees = employees
        self.audit = audit
        # LateEarlyRepository | None — phiếu đi muộn/về sớm có tick "trừ vào phép năm" cũng tiêu
        # quỹ phép (nửa buổi = 0,5 ngày). Chỉ đọc REPO nên không vòng service↔service.
        self._late_early = late_early
        # CalendarService | None — lịch chung (loại ngày lễ + tuần T2–T7). Đặt tên `_work_calendar`
        # để KHÔNG che method `calendar()` (lịch nghỉ tháng) của service này. None → fallback Mon–Fri.
        self._work_calendar = calendar

    def _wd(self, start: date, end: date) -> int:
        """Số NGÀY LÀM VIỆC để trừ hạn mức phép — ưu tiên lịch chung (loại lễ + Thứ 7 nay là
        ngày làm), fallback Mon–Fri khi chưa gắn calendar."""
        if self._work_calendar is not None:
            return self._work_calendar.working_days_between(start, end)
        return _working_days(start, end)

    def _quota_for(self, emp, annual_quota: int, year: int) -> int:
        """Hạn mức phép năm áp cho 1 NV — prorate năm ĐẦU vào làm (Điều 113 BLLĐ + NĐ145 Đ66):
        quota × số tháng làm (từ tháng vào đến hết năm) ÷ 12, làm tròn NỬA-LÊN (thiên NLĐ; hệ
        thống không dùng nửa ngày). Vào từ năm trước / không rõ ngày vào → đủ cả năm."""
        if annual_quota <= 0:
            return 0
        hire = getattr(emp, "hire_date", None)
        if hire is None or hire.year < year:
            return annual_quota
        if hire.year > year:
            return 0
        months = 12 - hire.month + 1  # vào tháng 7 → 6 tháng (7..12); tính trọn tháng vào
        return int(annual_quota * months / 12 + 0.5)

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
        if self._wd(start_date, end_date) == 0:
            raise LeaveValidationError("Khoảng nghỉ rơi hết vào ngày nghỉ, không có ngày làm việc.")
        days = (end_date - start_date).days + 1  # số ngày LỊCH (để hiển thị trên đơn)

        # Hạn mức phép năm: loại có annual_quota > 0 mới bị trừ dần + chặn khi vượt (theo
        # NGÀY LÀM VIỆC, reset dương lịch, KHÔNG cộng dồn). Loại quota=0 (ốm/không lương) bỏ qua.
        if lt.annual_quota and lt.annual_quota > 0:
            year = start_date.year
            quota = self._quota_for(emp, lt.annual_quota, year)  # prorate người mới vào giữa năm
            used = self._used_working_days(emp.id, leave_type_id, year)
            want = self._wd(start_date, end_date)
            if used + want > quota:
                remaining = max(quota - used, 0)
                raise LeaveValidationError(
                    f"Vượt hạn mức {lt.name} năm {year}: đã dùng/đang chờ {used} ngày, "
                    f"còn {remaining} ngày, đơn này {want} ngày làm việc."
                )

        r = self.leaves.create_request(
            employee_id=emp.id, leave_type_id=leave_type_id, start_date=start_date,
            end_date=end_date, days=days, reason=_clean(reason), status=STATUS_PENDING,
            created_by=actor.id,
        )
        self.audit.create(actor_user_id=actor.id, action="create_leave_request",
                          target=f"leave_request:{r.id}",
                          detail=f"{emp.code} {lt.name} {start_date}→{end_date} ({days}n)")
        return r

    def my_requests(self, *, user, page: int = 1, size: int = 20) -> tuple[list[LeaveRequest], int]:
        """Trả `(rows, total)` — `total` là TỔNG đơn của NV, không phải số dòng của trang."""
        emp = self._employee_for_user(user)
        total = self.leaves.count_by_employee(emp.id)
        rows = self.leaves.list_by_employee(emp.id, limit=size, offset=max(0, (page - 1) * size))
        return rows, total

    def list_requests(self, *, scope: str, actor, status: str | None = None,
                      employee_id: int | None = None, page: int = 1,
                      size: int = 20) -> tuple[list[LeaveRequest], int]:
        """Danh sách đơn theo DATA-SCOPE người gọi (own = của mình / department = của phòng /
        all = tất cả). Duyệt tập trung: HCNS/Admin scope=all thấy mọi đơn.

        `employee_id` chỉ THU HẸP thêm bên trong phạm vi đã có — không mở rộng quyền: gõ id của
        người ngoài phạm vi thì `_scope_condition` vẫn cắt, kết quả rỗng chứ không lộ đơn."""
        total = self.leaves.count_scoped(scope=scope, actor=actor, status=status,
                                         employee_id=employee_id)
        rows = self.leaves.list_scoped(scope=scope, actor=actor, status=status,
                                       employee_id=employee_id, limit=size,
                                       offset=max(0, (page - 1) * size))
        return rows, total

    def count_pending(self, *, scope: str, actor) -> int:
        """Số đơn chờ duyệt trong scope — nuôi badge sidebar."""
        return self.leaves.count_pending_scoped(scope=scope, actor=actor)

    def my_unseen_count(self, *, user) -> int:
        """Số đơn của tôi vừa được quyết mà tôi chưa xem — nuôi chuông Topbar."""
        emp = self.employees.get_by_user_id(user.id)
        return self.leaves.count_my_unseen(emp.id) if emp is not None else 0

    def mark_seen(self, *, user) -> None:
        """NV xác nhận đã xem kết quả các đơn của mình → đóng chuông."""
        emp = self.employees.get_by_user_id(user.id)
        if emp is not None:
            self.leaves.mark_my_seen(emp.id)

    # --- hạn mức phép năm ----------------------------------------------------

    def _used_working_days(self, employee_id: int, leave_type_id: int, year: int) -> float:
        """Tổng NGÀY phép đã dùng + đang giữ (approved + pending) của 1 loại nghỉ trong năm
        dương lịch — mẫu số kiểm hạn mức.

        Cộng từ HAI kênh: đơn nghỉ nguyên ngày, và phiếu đi muộn/về sớm có tick "trừ vào phép
        năm" (nửa buổi → 0,5 ngày). Thiếu kênh thứ hai thì người ta xin nửa buổi trừ phép thoải
        mái mà số dư không hề giảm. Trả FLOAT vì có số lẻ 0,5."""
        total = 0.0
        for r in self.leaves.list_for_quota(employee_id, leave_type_id, year):
            total += self._wd(r.start_date, r.end_date)
        if self._late_early is not None:
            total += self._late_early.leave_cong_used(employee_id, leave_type_id, year)
        return total

    def remaining_for(self, *, employee, leave_type_id: int, year: int,
                      exclude_late_early_id: int | None = None) -> float | None:
        """Số ngày phép CÒN LẠI của 1 NV cho 1 loại nghỉ. None = loại không giới hạn hạn mức.

        Dùng chung cho cả đơn nghỉ lẫn phiếu đi muộn/về sớm ⇒ hai đường không bao giờ tính lệch.
        `exclude_late_early_id` để lúc SỬA phiếu không tự đếm chính nó."""
        lt = self.leaves.get_type(leave_type_id)
        if lt is None or not lt.annual_quota or lt.annual_quota <= 0:
            return None
        quota = self._quota_for(employee, lt.annual_quota, year)
        used = self._used_working_days(employee.id, leave_type_id, year)
        if exclude_late_early_id is not None and self._late_early is not None:
            old = self._late_early.get_request(exclude_late_early_id)
            if old is not None and old.leave_type_id == leave_type_id:
                used -= float(old.leave_cong or 0)
        return max(0.0, quota - used)

    def my_quotas(self, *, user, year: int) -> list[dict]:
        """Tình hình hạn mức của NV đăng nhập (chỉ loại có annual_quota > 0): đã dùng / còn
        lại theo ngày làm việc. Trả rỗng nếu tài khoản chưa gắn hồ sơ NV."""
        emp = self.employees.get_by_user_id(user.id)
        if emp is None:
            return []
        out: list[dict] = []
        for t in self.leaves.list_types(active_only=True):
            if not t.annual_quota or t.annual_quota <= 0:
                continue
            quota = self._quota_for(emp, t.annual_quota, year)  # prorate người mới vào giữa năm
            used = self._used_working_days(emp.id, t.id, year)
            out.append({
                "leave_type_id": t.id,
                "name": t.name,
                "annual_quota": quota,
                "used": used,
                "remaining": max(quota - used, 0),
            })
        return out

    def _guard_scope(self, employee_id: int, *, scope: str, actor) -> None:
        """Chặn GHI ra ngoài tầm dữ liệu của người gọi.

        Ô quyền `approve` chỉ trả lời "được duyệt hay không", KHÔNG trả lời "được duyệt CHO AI".
        Từ 29/07/2026 tổ trưởng ĐƯỢC duyệt nghỉ phép (chủ chốt) nên chốt này là thứ giữ họ trong
        tổ mình — thiếu nó là cấp quyền duyệt cho cả công ty. Đơn nghỉ RA TIỀN: trừ quỹ phép năm,
        nghỉ có lương hay không.

        `scope` BẮT BUỘC — cố ý không cho mặc định, vì "quên khai thì bỏ qua kiểm tra" chính là
        cơ chế đã để lỗ này tồn tại mà không ai biết."""
        emp = self.employees.get_by_id(employee_id)
        if emp is None:
            return
        if not self.employees.can_access(employee=emp, scope=scope, actor=actor):
            raise LeaveForbidden("Nhân viên này ngoài phạm vi quản lý của bạn.")

    def _decide(self, *, actor, request_id, new_status, note, scope: str) -> LeaveRequest:
        r = self.leaves.get_request(request_id)
        if r is None:
            raise LeaveNotFound("Không tìm thấy đơn nghỉ.")
        self._guard_scope(r.employee_id, scope=scope, actor=actor)
        if r.status != STATUS_PENDING:
            raise LeaveValidationError("Chỉ duyệt/từ chối được đơn đang chờ.")
        self.leaves.update_request(
            r, status=new_status, decided_by=actor.id,
            decided_at=datetime.now(timezone.utc), decision_note=_clean(note),
        )
        self.audit.create(actor_user_id=actor.id, action=f"leave_{new_status}",
                          target=f"leave_request:{r.id}", detail=f"→ {new_status}")
        return r

    def approve(self, *, actor, request_id, scope: str, note=None) -> LeaveRequest:
        return self._decide(actor=actor, request_id=request_id, new_status=STATUS_APPROVED,
                            note=note, scope=scope)

    def reject(self, *, actor, request_id, scope: str, note=None) -> LeaveRequest:
        note = _clean(note)
        if not note:
            raise LeaveValidationError("Cần nhập lý do từ chối.")
        return self._decide(actor=actor, request_id=request_id, new_status=STATUS_REJECTED,
                            note=note, scope=scope)

    def bulk_approve(self, *, actor, ids: list[int], scope: str) -> dict:
        """Duyệt hàng loạt: bỏ qua (skip) đơn không-chờ HOẶC ngoài phạm vi, thay vì vỡ cả mẻ.

        `LeaveForbidden` là con của `LeaveError` nên đơn ngoài tổ tự rơi vào `skipped` — đúng ý:
        mẻ gửi từ màn chỉ chứa đơn người dùng thấy, còn ai dò mã lạ thì nhận `skipped`, không lộ
        đơn đó có tồn tại hay không."""
        done, skipped = [], []
        for i in ids:
            try:
                self.approve(actor=actor, request_id=i, scope=scope)
                done.append(i)
            except LeaveError:
                skipped.append(i)
        return {"done": done, "skipped": skipped}

    def bulk_reject(self, *, actor, ids: list[int], note, scope: str) -> dict:
        """Từ chối hàng loạt với 1 lý do chung (bắt buộc)."""
        note = _clean(note)
        if not note:
            raise LeaveValidationError("Cần nhập lý do từ chối.")
        done, skipped = [], []
        for i in ids:
            try:
                self._decide(actor=actor, request_id=i, new_status=STATUS_REJECTED, note=note,
                             scope=scope)
                done.append(i)
            except LeaveError:
                skipped.append(i)
        return {"done": done, "skipped": skipped}

    def cancel(self, *, actor, request_id, is_hr: bool = False, scope: str = "own") -> LeaveRequest:
        r = self.leaves.get_request(request_id)
        if r is None:
            raise LeaveNotFound("Không tìm thấy đơn nghỉ.")
        # Người tạo hủy đơn của mình, hoặc người có quyền duyệt hủy đơn TRONG PHẠM VI của họ.
        # Trước 29/07/2026 `is_hr` nghĩa là "hủy BẤT KỲ" — an toàn khi chỉ HCNS (scope `all`) có
        # cờ đó. Nay tổ trưởng cũng có `approve` ⇒ để nguyên là tổ trưởng hủy được đơn cả công ty.
        if not is_hr and r.created_by != actor.id:
            raise LeaveForbidden("Bạn chỉ hủy được đơn của mình.")
        if is_hr and r.created_by != actor.id:
            self._guard_scope(r.employee_id, scope=scope, actor=actor)
        if r.status in (STATUS_REJECTED, STATUS_CANCELLED):
            raise LeaveValidationError("Đơn đã kết thúc, không hủy được.")
        self.leaves.update_request(r, status=STATUS_CANCELLED)
        self.audit.create(actor_user_id=actor.id, action="leave_cancelled",
                          target=f"leave_request:{r.id}", detail="hủy đơn")
        return r

    # --- lịch nghỉ (toàn công ty) ------------------------------------------

    def calendar(self, *, year: int, month: int, scope: str = "all", actor=None) -> dict:
        """Lịch nghỉ tháng: mỗi NV có đơn ĐÃ DUYỆT hoặc ĐANG CHỜ giao với tháng → các ngày
        nghỉ + trạng thái (để tránh duyệt trùng người). Bao gồm cả ngày cuối tuần trong khoảng
        (phản chiếu đúng đơn).

        LỌC THEO PHẠM VI người xem: màn này gác bằng ô quyền `approve`, mà từ 29/07/2026 tổ
        trưởng cũng có cờ đó ⇒ không lọc là tổ trưởng đọc được lịch nghỉ của cả công ty."""
        import calendar as _cal

        first = date(year, month, 1)
        last = date(year, month, _cal.monthrange(year, month)[1])
        reqs = self.leaves.list_overlapping(first, last, (STATUS_APPROVED, STATUS_PENDING))
        if actor is not None and scope != "all":
            trong_tam: dict[int, bool] = {}
            def _duoc_xem(emp_id: int) -> bool:
                if emp_id not in trong_tam:
                    emp = self.employees.get_by_id(emp_id)
                    trong_tam[emp_id] = emp is not None and self.employees.can_access(
                        employee=emp, scope=scope, actor=actor)
                return trong_tam[emp_id]
            reqs = [r for r in reqs if _duoc_xem(r.employee_id)]
        types = {t.id: t for t in self.leaves.list_types()}
        out: dict[int, dict] = {}
        for r in reqs:
            lt = types.get(r.leave_type_id)
            if r.employee_id not in out:
                emp = self.employees.get_by_id(r.employee_id)
                out[r.employee_id] = {
                    "employee_id": r.employee_id,
                    "employee_name": emp.full_name if emp is not None else f"NV#{r.employee_id}",
                    "days": {},
                }
            d, end = max(r.start_date, first), min(r.end_date, last)
            while d <= end:
                # pending không đè lên approved cùng ngày (approved thắng để HR thấy chắc chắn).
                cur = out[r.employee_id]["days"].get(str(d.day))
                if cur is None or (cur["status"] != STATUS_APPROVED):
                    out[r.employee_id]["days"][str(d.day)] = {
                        "status": r.status,
                        "leave_type_name": lt.name if lt is not None else "Nghỉ",
                        "is_paid": lt.is_paid if lt is not None else True,
                    }
                d = date.fromordinal(d.toordinal() + 1)
        return {
            "year": year, "month": month, "days_in_month": last.day,
            "employees": sorted(out.values(), key=lambda e: e["employee_name"]),
        }
