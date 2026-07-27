"""Phiếu tăng ca (module `tang_ca`) — nghiệp vụ.

NV tự gửi phiếu → tổ trưởng duyệt; HOẶC tổ trưởng tạo thẳng cho NV (duyệt luôn, khỏi 2 bước).
Phiếu ĐÃ DUYỆT = **GIẤY PHÉP + MỨC TRẦN**: Bảng công tháng chỉ trả tiền phần giờ vượt ca NẰM TRONG
phiếu. Không có phiếu ⇒ vẫn đủ công ca chính, chỉ KHÔNG ra tiền tăng ca (chốt với chủ 23/07/2026).
Máy KHÔNG tự điền giờ ra từ phiếu — lượt bấm ra mới là sự thật, để người về sớm lộ ra.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from ..models.overtime import (
    STATUS_APPROVED,
    STATUS_CANCELLED,
    STATUS_PENDING,
    STATUS_REJECTED,
    OvertimeRequest,
)
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.employee_repo import EmployeeRepository
from ..repositories.overtime_repo import OvertimeRepository

# Trần độ dài MỘT phiếu (phút). Đ107 BLLĐ: tổng giờ làm + tăng ca ≤ 12h/ngày → 12h là trần rộng rãi.
MAX_OT_MINUTES = 12 * 60
# Mốc phút lớn nhất cho `to_minute` (2 ngày kể từ 00:00 ngày công) — chặn nhập bậy.
MAX_MINUTE = 2 * 1440


class OvertimeError(Exception):
    """Base cho lỗi miền tăng ca."""


class OvertimeValidationError(OvertimeError):
    """Sai dữ liệu, hoặc chuyển trạng thái không hợp lệ."""


class OvertimeNotFound(OvertimeError):
    """Không tìm thấy phiếu."""


class OvertimeForbidden(OvertimeError):
    """Không được phép thao tác trên phiếu này."""


class NoLinkedEmployee(OvertimeError):
    """Tài khoản chưa gắn hồ sơ NV — không tự gửi phiếu được."""


def _clean(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    return v or None


def hhmm(minute: int) -> str:
    """Phút-trên-trục-ngày-công → 'HH:MM' (kèm '+1' nếu đã sang hôm sau) để hiển thị/audit."""
    m = int(minute)
    day, rem = divmod(m, 1440)
    return f"{rem // 60:02d}:{rem % 60:02d}" + (f" (+{day})" if day else "")


class OvertimeService:
    def __init__(self, overtime: OvertimeRepository, employees: EmployeeRepository,
                 audit: AuditLogRepository) -> None:
        self.overtime = overtime
        self.employees = employees
        self.audit = audit

    # --- helpers ------------------------------------------------------------

    def _employee_for_user(self, user):
        emp = self.employees.get_by_user_id(user.id)
        if emp is None:
            raise NoLinkedEmployee("Tài khoản của bạn chưa gắn hồ sơ nhân viên.")
        return emp

    def has_employee(self, *, user) -> bool:
        return self.employees.get_by_user_id(user.id) is not None

    # --- tạo phiếu ----------------------------------------------------------

    def create_request(self, *, actor, work_date: date, from_minute: int, to_minute: int,
                       reason=None, employee_id=None, auto_approve: bool = False) -> OvertimeRequest:
        """Tạo phiếu. `employee_id` != None = tổ trưởng tạo HỘ; `auto_approve` = duyệt luôn
        (tổ trưởng tự tạo cho thợ thì không bắt duyệt lại bước nữa)."""
        if employee_id is not None:
            emp = self.employees.get_by_id(employee_id)
            if emp is None:
                raise OvertimeValidationError("Không tìm thấy nhân viên.")
        else:
            emp = self._employee_for_user(actor)

        if work_date is None:
            raise OvertimeValidationError("Cần chọn ngày công.")
        try:
            from_minute, to_minute = int(from_minute), int(to_minute)
        except (TypeError, ValueError):
            raise OvertimeValidationError("Giờ tăng ca không hợp lệ.")
        if from_minute < 0 or to_minute > MAX_MINUTE:
            raise OvertimeValidationError("Giờ tăng ca ngoài phạm vi cho phép.")
        if to_minute <= from_minute:
            raise OvertimeValidationError("Giờ kết thúc phải sau giờ bắt đầu.")
        if to_minute - from_minute > MAX_OT_MINUTES:
            raise OvertimeValidationError(
                f"Một phiếu tăng ca tối đa {MAX_OT_MINUTES // 60} giờ (Điều 107 BLLĐ)."
            )
        # Chặn 2 phiếu còn hiệu lực GIAO nhau trong cùng một ngày công.
        for other in self.overtime.live_for_day(emp.id, work_date):
            if from_minute < other.to_minute and other.from_minute < to_minute:
                raise OvertimeValidationError(
                    f"Đã có phiếu tăng ca {hhmm(other.from_minute)}–{hhmm(other.to_minute)} "
                    f"cho ngày này."
                )

        approved = bool(auto_approve)
        r = self.overtime.create_request(
            employee_id=emp.id, work_date=work_date, from_minute=from_minute,
            to_minute=to_minute, reason=_clean(reason),
            status=STATUS_APPROVED if approved else STATUS_PENDING,
            created_by=actor.id,
            decided_by=actor.id if approved else None,
            decided_at=datetime.now(timezone.utc) if approved else None,
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="create_overtime_request" + ("_approved" if approved else ""),
            target=f"overtime_request:{r.id}",
            detail=f"{emp.code} {work_date} {hhmm(from_minute)}–{hhmm(to_minute)}",
        )
        return r

    # --- đọc ----------------------------------------------------------------

    def my_requests(self, *, user, limit: int = 100) -> list[OvertimeRequest]:
        emp = self._employee_for_user(user)
        return self.overtime.list_by_employee(emp.id, limit=limit)

    def list_requests(self, *, scope: str, actor, status: str | None = None,
                      limit: int = 200) -> list[OvertimeRequest]:
        """Danh sách phiếu theo DATA-SCOPE người gọi (own = của mình / department = tổ mình +
        cây con / all = tất cả) ⇒ tổ trưởng chỉ thấy & duyệt được người trong tổ."""
        return self.overtime.list_scoped(scope=scope, actor=actor, status=status, limit=limit)

    def count_pending(self, *, scope: str, actor) -> int:
        return self.overtime.count_pending_scoped(scope=scope, actor=actor)

    def my_unseen_count(self, *, user) -> int:
        emp = self.employees.get_by_user_id(user.id)
        return self.overtime.count_my_unseen(emp.id) if emp is not None else 0

    def mark_seen(self, *, user) -> None:
        emp = self.employees.get_by_user_id(user.id)
        if emp is not None:
            self.overtime.mark_my_seen(emp.id)

    # --- duyệt / từ chối / hủy ----------------------------------------------

    def _decide(self, *, actor, request_id: int, new_status: str, note) -> OvertimeRequest:
        r = self.overtime.get_request(request_id)
        if r is None:
            raise OvertimeNotFound("Không tìm thấy phiếu tăng ca.")
        if r.status != STATUS_PENDING:
            raise OvertimeValidationError("Chỉ duyệt/từ chối được phiếu đang chờ.")
        self.overtime.update_request(
            r, status=new_status, decided_by=actor.id,
            decided_at=datetime.now(timezone.utc), decision_note=_clean(note),
        )
        self.audit.create(actor_user_id=actor.id, action=f"overtime_{new_status}",
                          target=f"overtime_request:{r.id}", detail=f"→ {new_status}")
        return r

    def approve(self, *, actor, request_id: int, note=None) -> OvertimeRequest:
        return self._decide(actor=actor, request_id=request_id,
                            new_status=STATUS_APPROVED, note=note)

    def reject(self, *, actor, request_id: int, note) -> OvertimeRequest:
        if not _clean(note):
            raise OvertimeValidationError("Từ chối phải ghi lý do.")
        return self._decide(actor=actor, request_id=request_id,
                            new_status=STATUS_REJECTED, note=note)

    def bulk_approve(self, *, actor, request_ids, note=None) -> list[OvertimeRequest]:
        """Duyệt cả mẻ (cả tổ tăng ca cùng một tối). Phiếu không-còn-chờ thì BỎ QUA, không vỡ mẻ."""
        out: list[OvertimeRequest] = []
        for rid in request_ids or []:
            r = self.overtime.get_request(rid)
            if r is None or r.status != STATUS_PENDING:
                continue
            out.append(self.approve(actor=actor, request_id=rid, note=note))
        return out

    def bulk_reject(self, *, actor, request_ids, note) -> list[OvertimeRequest]:
        if not _clean(note):
            raise OvertimeValidationError("Từ chối phải ghi lý do.")
        out: list[OvertimeRequest] = []
        for rid in request_ids or []:
            r = self.overtime.get_request(rid)
            if r is None or r.status != STATUS_PENDING:
                continue
            out.append(self.reject(actor=actor, request_id=rid, note=note))
        return out

    def cancel(self, *, actor, request_id: int, is_manager: bool = False) -> OvertimeRequest:
        """Hủy phiếu: người TẠO tự hủy, hoặc người có quyền duyệt hủy hộ. Chỉ hủy phiếu chưa quyết."""
        r = self.overtime.get_request(request_id)
        if r is None:
            raise OvertimeNotFound("Không tìm thấy phiếu tăng ca.")
        if not is_manager and r.created_by != actor.id:
            raise OvertimeForbidden("Bạn chỉ hủy được phiếu do mình tạo.")
        if r.status not in (STATUS_PENDING, STATUS_APPROVED):
            raise OvertimeValidationError("Phiếu này không còn để hủy.")
        self.overtime.update_request(r, status=STATUS_CANCELLED)
        self.audit.create(actor_user_id=actor.id, action="overtime_cancelled",
                          target=f"overtime_request:{r.id}", detail="→ cancelled")
        return r
