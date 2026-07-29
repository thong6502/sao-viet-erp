"""Phiếu đi muộn / về sớm / nghỉ nửa buổi (module `di_muon`) — nghiệp vụ.

NV tự gửi phiếu → TỔ TRƯỞNG duyệt; HOẶC tổ trưởng khai hộ (duyệt luôn). Chép khuôn
`overtime_service`, khác 3 chỗ:

1. Bỏ trần 12h của tăng ca → trần là **1 ngày (1440′)**.
2. **Hai nhánh tiền** do người tạo tự chọn:
   - `leave_type_id = None` → không đụng quỹ phép; phần vắng KHÔNG được trả công.
   - `leave_type_id` khác None → tiêu `leave_cong` ngày phép (**làm tròn 0,5**) và phần vắng VẪN
     được trả theo LƯƠNG VỊ TRÍ.
3. Tích trừ phép mà **hết phép** ⇒ chặn ngay, báo rõ còn bao nhiêu ngày.

Cả hai nhánh đều được MIỄN PHẠT đi muộn/về sớm đúng số phút đã xin (xử lý ở engine chấm công).
"""
from __future__ import annotations

import math
from datetime import date, datetime, timezone

from ..models.late_early import (
    STATUS_APPROVED,
    STATUS_CANCELLED,
    STATUS_PENDING,
    STATUS_REJECTED,
    LateEarlyRequest,
)
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.employee_repo import EmployeeRepository
from ..repositories.late_early_repo import LateEarlyRepository

# Trần độ dài MỘT phiếu: 1 ngày. (Vắng cả ngày thì dùng đơn NGHỈ PHÉP, không dùng phiếu này.)
MAX_ABSENT_MINUTES = 1440
# Mốc phút lớn nhất cho `to_minute` (2 ngày kể từ 00:00 ngày công) — chặn nhập bậy.
MAX_MINUTE = 2 * 1440
# Khung ca dự phòng khi NV chưa gán ca (không để chia cho 0).
_FALLBACK_WINDOW = 8 * 60


class LateEarlyError(Exception):
    """Base cho lỗi miền phiếu đi muộn / về sớm."""


class LateEarlyValidationError(LateEarlyError):
    """Sai dữ liệu, hoặc chuyển trạng thái không hợp lệ."""


class LateEarlyNotFound(LateEarlyError):
    """Không tìm thấy phiếu."""


class LateEarlyForbidden(LateEarlyError):
    """Không được phép thao tác trên phiếu này."""


class NoLinkedEmployee(LateEarlyError):
    """Tài khoản chưa gắn hồ sơ NV — không tự gửi phiếu được."""


def _clean(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    return v or None


def hhmm(minute: int) -> str:
    """Phút-trên-trục-ngày-công → 'HH:MM' (kèm '+1' nếu sang hôm sau) để hiển thị/audit."""
    m = int(minute)
    day, rem = divmod(m, 1440)
    return f"{rem // 60:02d}:{rem % 60:02d}" + (f" (+{day})" if day else "")


class LateEarlyService:
    def __init__(self, late_early: LateEarlyRepository, employees: EmployeeRepository,
                 audit: AuditLogRepository, attendance=None, leaves=None) -> None:
        self.late_early = late_early
        self.employees = employees
        self.audit = audit
        # AttendanceRepository | None — để lấy KHUNG CA mà quy số phút vắng ra ngày phép.
        self.attendance = attendance
        # LeaveService | None — để hỏi số ngày phép còn lại. Một chiều, không vòng service↔service
        # (LeaveService chỉ đọc LateEarlyRepository, không đọc service này).
        self.leaves = leaves

    # --- helpers ------------------------------------------------------------

    def _employee_for_user(self, user):
        emp = self.employees.get_by_user_id(user.id)
        if emp is None:
            raise NoLinkedEmployee("Tài khoản của bạn chưa gắn hồ sơ nhân viên.")
        return emp

    def has_employee(self, *, user) -> bool:
        return self.employees.get_by_user_id(user.id) is not None

    def _shift_window(self, employee, work_date: date) -> int:
        """Số phút CHUẨN của ca hôm đó — mẫu số quy phút vắng ra ngày phép. Dùng ĐÚNG khung ca
        mà `compute_day_cong` dùng để tính công, nếu không sẽ có hai mẫu số trong cùng một ngày."""
        if self.attendance is None:
            return _FALLBACK_WINDOW
        shift_id = self.employees.shift_id_on(employee, work_date)
        shift = self.attendance.get_shift(shift_id) if shift_id is not None else None
        if shift is None:
            return _FALLBACK_WINDOW
        end = shift.end_minute + (1440 if shift.is_overnight else 0)
        return max(1, end - shift.start_minute)

    @staticmethod
    def _round_half(frac: float) -> float:
        """Làm tròn LÊN theo nửa ngày (chủ chốt): vắng ≤ nửa ca → 0,5 ngày; vượt → 1,0.
        Quỹ phép chỉ có số tròn đẹp (12 → 11,5 → 11), đúng cách xưởng hay ghi sổ."""
        return min(1.0, math.ceil(max(0.0, frac) * 2) / 2)

    def _leave_cong_for(self, employee, work_date: date, minutes: int) -> float:
        return self._round_half(minutes / self._shift_window(employee, work_date))

    # --- tạo phiếu ----------------------------------------------------------

    def _validate_window(self, employee_id: int, work_date: date, from_minute, to_minute,
                         *, exclude_id: int | None = None) -> tuple[int, int]:
        """Dùng chung cho TẠO + SỬA: biên phút · to>from · ≤1 ngày · **tối đa 1 phiếu còn hiệu
        lực/ngày**. `exclude_id` để lúc SỬA không tự đếm chính phiếu đang sửa."""
        if work_date is None:
            raise LateEarlyValidationError("Cần chọn ngày công.")
        try:
            from_minute, to_minute = int(from_minute), int(to_minute)
        except (TypeError, ValueError):
            raise LateEarlyValidationError("Giờ xin vắng không hợp lệ.")
        if from_minute < 0 or to_minute > MAX_MINUTE:
            raise LateEarlyValidationError("Giờ xin vắng ngoài phạm vi cho phép.")
        if to_minute <= from_minute:
            raise LateEarlyValidationError("Giờ kết thúc phải sau giờ bắt đầu.")
        if to_minute - from_minute > MAX_ABSENT_MINUTES:
            raise LateEarlyValidationError(
                "Vắng quá 1 ngày thì dùng đơn nghỉ phép, không dùng phiếu này."
            )
        if self.late_early.live_for_day(employee_id, work_date, exclude_id=exclude_id):
            raise LateEarlyValidationError(
                "Ngày này đã có phiếu xin vắng — sửa hoặc hủy phiếu cũ trước."
            )
        return from_minute, to_minute

    def _resolve_leave(self, employee, work_date: date, minutes: int,
                       leave_type_id, *, exclude_id: int | None = None) -> tuple[int | None, float]:
        """Quy phần vắng ra ngày phép + CHẶN khi hết phép. Trả (leave_type_id, leave_cong)."""
        if leave_type_id is None:
            return None, 0.0
        leave_cong = self._leave_cong_for(employee, work_date, minutes)
        if self.leaves is None:
            return int(leave_type_id), leave_cong
        remaining = self.leaves.remaining_for(
            employee=employee, leave_type_id=int(leave_type_id), year=work_date.year,
            exclude_late_early_id=exclude_id,
        )
        if remaining is None:                      # loại nghỉ không giới hạn hạn mức
            return int(leave_type_id), leave_cong
        if leave_cong > remaining + 1e-9:
            raise LateEarlyValidationError(
                f"Không đủ phép năm: phiếu này cần {leave_cong:g} ngày, "
                f"còn lại {remaining:g} ngày. Bỏ tick 'Trừ vào phép năm' để xin không lương."
            )
        return int(leave_type_id), leave_cong

    def _guard_scope(self, emp, *, scope: str | None, actor) -> None:
        """Chặn GHI ra ngoài tầm dữ liệu của người gọi.

        Quyền `approve` chỉ trả lời "được duyệt hay không", KHÔNG trả lời "được duyệt CHO AI".
        Thiếu chốt này thì tổ trưởng tổ A duyệt được phiếu của người tổ B — mà chính họ không
        thấy phiếu đó trên màn của mình (đường ĐỌC đã lọc scope). Phiếu duyệt là dữ liệu RA
        TIỀN: miễn phạt, hoàn công, trừ quỹ phép năm."""
        if scope is None:
            return    # gọi nội bộ / unit test dựng tay ⇒ giữ hành vi cũ
        if not self.employees.can_access(employee=emp, scope=scope, actor=actor):
            raise LateEarlyForbidden("Nhân viên này ngoài phạm vi quản lý của bạn.")

    def create_request(self, *, actor, work_date: date, from_minute: int, to_minute: int,
                       reason=None, employee_id=None, leave_type_id=None,
                       auto_approve: bool = False, scope: str | None = None) -> LateEarlyRequest:
        """Tạo phiếu. `employee_id` != None = tổ trưởng khai HỘ; `auto_approve` = duyệt luôn."""
        if employee_id is not None:
            emp = self.employees.get_by_id(employee_id)
            if emp is None:
                raise LateEarlyValidationError("Không tìm thấy nhân viên.")
            self._guard_scope(emp, scope=scope, actor=actor)
        else:
            emp = self._employee_for_user(actor)

        from_minute, to_minute = self._validate_window(emp.id, work_date, from_minute, to_minute)
        lt_id, leave_cong = self._resolve_leave(
            emp, work_date, to_minute - from_minute, leave_type_id
        )

        approved = bool(auto_approve)
        r = self.late_early.create_request(
            employee_id=emp.id, work_date=work_date, from_minute=from_minute,
            to_minute=to_minute, reason=_clean(reason),
            leave_type_id=lt_id, leave_cong=leave_cong,
            status=STATUS_APPROVED if approved else STATUS_PENDING,
            created_by=actor.id,
            decided_by=actor.id if approved else None,
            decided_at=datetime.now(timezone.utc) if approved else None,
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="create_late_early_request" + ("_approved" if approved else ""),
            target=f"late_early_request:{r.id}",
            detail=(f"{emp.code} {work_date} {hhmm(from_minute)}–{hhmm(to_minute)}"
                    + (f" · trừ {leave_cong:g} ngày phép" if lt_id else " · không trừ phép")),
        )
        return r

    # --- đọc ----------------------------------------------------------------

    def my_requests(self, *, user, limit: int = 100) -> list[LateEarlyRequest]:
        emp = self._employee_for_user(user)
        return self.late_early.list_by_employee(emp.id, limit=limit)

    def list_requests(self, *, scope: str, actor, status: str | None = None,
                      limit: int = 200) -> list[LateEarlyRequest]:
        """Danh sách theo DATA-SCOPE người gọi ⇒ tổ trưởng chỉ thấy & duyệt được người trong tổ."""
        return self.late_early.list_scoped(scope=scope, actor=actor, status=status, limit=limit)

    def count_pending(self, *, scope: str, actor) -> int:
        return self.late_early.count_pending_scoped(scope=scope, actor=actor)

    def my_unseen_count(self, *, user) -> int:
        emp = self.employees.get_by_user_id(user.id)
        return self.late_early.count_my_unseen(emp.id) if emp is not None else 0

    def mark_seen(self, *, user) -> None:
        emp = self.employees.get_by_user_id(user.id)
        if emp is not None:
            self.late_early.mark_my_seen(emp.id)

    # --- duyệt / từ chối / hủy ----------------------------------------------

    def _decide(self, *, actor, request_id: int, new_status: str, note,
                scope: str | None = None) -> LateEarlyRequest:
        r = self.late_early.get_request(request_id)
        if r is None:
            raise LateEarlyNotFound("Không tìm thấy phiếu xin vắng.")
        emp = self.employees.get_by_id(r.employee_id)
        if emp is not None:
            self._guard_scope(emp, scope=scope, actor=actor)
        if r.status != STATUS_PENDING:
            raise LateEarlyValidationError("Chỉ duyệt/từ chối được phiếu đang chờ.")
        self.late_early.update_request(
            r, status=new_status, decided_by=actor.id,
            decided_at=datetime.now(timezone.utc), decision_note=_clean(note),
        )
        self.audit.create(actor_user_id=actor.id, action=f"late_early_{new_status}",
                          target=f"late_early_request:{r.id}", detail=f"→ {new_status}")
        return r

    def approve(self, *, actor, request_id: int, note=None,
                scope: str | None = None) -> LateEarlyRequest:
        return self._decide(actor=actor, request_id=request_id,
                            new_status=STATUS_APPROVED, note=note, scope=scope)

    def reject(self, *, actor, request_id: int, note,
               scope: str | None = None) -> LateEarlyRequest:
        if not _clean(note):
            raise LateEarlyValidationError("Từ chối phải ghi lý do.")
        return self._decide(actor=actor, request_id=request_id,
                            new_status=STATUS_REJECTED, note=note, scope=scope)

    def bulk_approve(self, *, actor, request_ids, note=None,
                     scope: str | None = None) -> list[LateEarlyRequest]:
        """Duyệt cả mẻ. Phiếu không-còn-chờ hoặc NGOÀI SCOPE thì BỎ QUA, không vỡ mẻ."""
        out: list[LateEarlyRequest] = []
        for rid in request_ids or []:
            r = self.late_early.get_request(rid)
            if r is None or r.status != STATUS_PENDING:
                continue
            try:
                out.append(self.approve(actor=actor, request_id=rid, note=note, scope=scope))
            except LateEarlyForbidden:
                continue   # ngoài tổ ⇒ bỏ qua, rơi vào `skipped` như phiếu đã xử lý
        return out

    def bulk_reject(self, *, actor, request_ids, note,
                    scope: str | None = None) -> list[LateEarlyRequest]:
        if not _clean(note):
            raise LateEarlyValidationError("Từ chối phải ghi lý do.")
        out: list[LateEarlyRequest] = []
        for rid in request_ids or []:
            r = self.late_early.get_request(rid)
            if r is None or r.status != STATUS_PENDING:
                continue
            try:
                out.append(self.reject(actor=actor, request_id=rid, note=note, scope=scope))
            except LateEarlyForbidden:
                continue
        return out

    def update_request(self, *, actor, request_id: int, work_date: date, from_minute: int,
                       to_minute: int, reason=None, leave_type_id=None) -> LateEarlyRequest:
        """Sửa phiếu ĐANG CHỜ DUYỆT. Chỉ người TẠO sửa được, và chỉ khi còn `pending`."""
        r = self.late_early.get_request(request_id)
        if r is None:
            raise LateEarlyNotFound("Không tìm thấy phiếu xin vắng.")
        if r.created_by != actor.id:
            raise LateEarlyForbidden("Bạn chỉ sửa được phiếu do mình tạo.")
        if r.status != STATUS_PENDING:
            raise LateEarlyValidationError("Chỉ sửa được phiếu đang chờ duyệt.")
        from_minute, to_minute = self._validate_window(
            r.employee_id, work_date, from_minute, to_minute, exclude_id=r.id
        )
        emp = self.employees.get_by_id(r.employee_id)
        lt_id, leave_cong = self._resolve_leave(
            emp, work_date, to_minute - from_minute, leave_type_id, exclude_id=r.id
        )
        self.late_early.update_request(
            r, work_date=work_date, from_minute=from_minute, to_minute=to_minute,
            reason=_clean(reason), leave_type_id=lt_id, leave_cong=leave_cong,
        )
        self.audit.create(actor_user_id=actor.id, action="late_early_updated",
                          target=f"late_early_request:{r.id}",
                          detail=f"{work_date} {hhmm(from_minute)}–{hhmm(to_minute)}")
        return r

    def cancel(self, *, actor, request_id: int, is_manager: bool = False,
               scope: str | None = None) -> LateEarlyRequest:
        """Hủy phiếu: người TẠO tự hủy, hoặc người có quyền duyệt hủy hộ (trong tổ mình)."""
        r = self.late_early.get_request(request_id)
        if r is None:
            raise LateEarlyNotFound("Không tìm thấy phiếu xin vắng.")
        if is_manager and r.created_by != actor.id:
            emp = self.employees.get_by_id(r.employee_id)
            if emp is not None:
                self._guard_scope(emp, scope=scope, actor=actor)
        if not is_manager and r.created_by != actor.id:
            raise LateEarlyForbidden("Bạn chỉ hủy được phiếu do mình tạo.")
        if r.status not in (STATUS_PENDING, STATUS_APPROVED):
            raise LateEarlyValidationError("Phiếu này không còn để hủy.")
        self.late_early.update_request(r, status=STATUS_CANCELLED)
        self.audit.create(actor_user_id=actor.id, action="late_early_cancelled",
                          target=f"late_early_request:{r.id}", detail="→ cancelled")
        return r
