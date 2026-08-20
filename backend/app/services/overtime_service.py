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
from .ky_cong_guard import ly_do_ky_cong_da_chot

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


def _gio_phut(minute: int) -> str:
    """Số PHÚT (độ dài) → "8h30" / "40h". Khác `hhmm` — cái kia là MỐC giờ trên trục ngày công,
    in ra "16:40 (+1)" cho 2400 phút thì vô nghĩa với người đọc."""
    m = max(0, int(minute))
    g, ph = divmod(m, 60)
    return f"{g}h{ph:02d}" if ph else f"{g}h"


def _hhmm(minute: int) -> str:
    """Mốc giờ để người dùng sửa ô "Đến giờ" — dùng lại `hhmm` sẵn có."""
    return hhmm(minute)


class OvertimeService:
    def __init__(self, overtime: OvertimeRepository, employees: EmployeeRepository,
                 audit: AuditLogRepository, attendance=None, payroll=None) -> None:
        self.overtime = overtime
        self.employees = employees
        self.audit = audit
        # PayrollRepository | None — CHỈ để đọc trần giờ làm thêm ở `payroll_params` (Đ107).
        # None (unit test dựng tay) ⇒ rơi về hằng số cũ, hành vi y như trước 17/08/2026.
        self._payroll = payroll
        # AttendanceRepository | None — hỏi "kỳ công tháng đó chốt chưa" trước khi duyệt/hủy phiếu
        # ĐÃ DUYỆT. Phiếu tăng ca duyệt xong là RA PHÚT TĂNG CA trong bảng công. Chỉ đọc REPO.
        self._attendance = attendance

    def _chan_neu_ky_cong_da_chot(self, ngay: date, viec: str) -> None:
        if self._attendance is None:
            return
        loi = ly_do_ky_cong_da_chot(self._attendance, ngay, viec=viec)
        if loi:
            raise OvertimeValidationError(loi)

    # --- helpers ------------------------------------------------------------

    def _tran_thang(self) -> int:
        """Số PHÚT làm thêm tối đa một người trong một tháng. `0` = TẮT trần."""
        if self._payroll is None:
            return 0
        return int(getattr(self._payroll.get_params(), "ot_max_minutes_per_month", 0) or 0)

    def _tran_mot_phieu(self) -> int:
        """Số PHÚT tối đa của MỘT phiếu (Đ107.1, mặc định 12 giờ)."""
        if self._payroll is None:
            return MAX_OT_MINUTES
        return int(getattr(self._payroll.get_params(), "ot_max_minutes_per_day", MAX_OT_MINUTES)
                   or MAX_OT_MINUTES)

    def tran_thang_info(self, employee_id: int, year: int, month: int, *,
                        exclude_id: int | None = None) -> dict:
        """Số dư trần tháng của 1 NV — nuôi dải bộ đếm trên modal tạo/sửa phiếu."""
        tran = self._tran_thang()
        da_dung = self.overtime.sum_live_minutes_in_month(
            employee_id, year, month, exclude_id=exclude_id)
        return {
            "ap_tran": tran > 0,
            "tran_phut": tran,
            "da_dung_phut": da_dung,
            "con_lai_phut": max(0, tran - da_dung) if tran > 0 else None,
        }

    def _employee_for_user(self, user):
        emp = self.employees.get_by_user_id(user.id)
        if emp is None:
            raise NoLinkedEmployee("Tài khoản của bạn chưa gắn hồ sơ nhân viên.")
        return emp

    def has_employee(self, *, user) -> bool:
        return self.employees.get_by_user_id(user.id) is not None

    # --- tạo phiếu ----------------------------------------------------------

    def _validate_window(self, employee_id: int, work_date: date, from_minute, to_minute,
                         *, exclude_id: int | None = None) -> tuple[int, int]:
        """Kiểm khoảng tăng ca dùng chung cho TẠO + SỬA: biên phút · to>from · ≤12h (Đ107) ·
        **tối đa 1 phiếu còn hiệu lực/ngày** (chủ chốt 2026-07-24). `exclude_id` để lúc SỬA không
        tự đếm chính phiếu đang sửa. Trả (from, to) đã ép int."""
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
        tran_phieu = self._tran_mot_phieu()
        if to_minute - from_minute > tran_phieu:
            raise OvertimeValidationError(
                f"Một phiếu tăng ca tối đa {_gio_phut(tran_phieu)} (Điều 107 BLLĐ)."
            )
        if self.overtime.live_for_day(employee_id, work_date, exclude_id=exclude_id):
            raise OvertimeValidationError(
                "Mỗi ngày chỉ được 1 phiếu tăng ca. Ngày này đã có phiếu — sửa hoặc hủy phiếu cũ."
            )
        # --- TRẦN GIỜ LÀM THÊM THEO THÁNG (Đ107) — CHẶN CỨNG, không có đường vượt -----------
        # Chủ chốt 17/08/2026. `0` = tắt trần (mặc định khi mới migrate) ⇒ không chặn ai.
        # Đếm cả phiếu CHỜ DUYỆT (giữ chỗ) — xem docstring `sum_live_minutes_in_month`.
        tran_thang = self._tran_thang()
        if tran_thang > 0:
            da_dung = self.overtime.sum_live_minutes_in_month(
                employee_id, work_date.year, work_date.month, exclude_id=exclude_id)
            con_lai = tran_thang - da_dung
            phieu_nay = to_minute - from_minute
            if phieu_nay > con_lai:
                thang = f"{work_date.month:02d}/{work_date.year}"
                if con_lai <= 0:
                    raise OvertimeValidationError(
                        f"Tháng {thang} đã dùng hết trần tăng ca "
                        f"({_gio_phut(da_dung)}/{_gio_phut(tran_thang)}). Không cấp thêm phiếu được."
                    )
                raise OvertimeValidationError(
                    f"Vượt trần tăng ca tháng {thang}. Đã đăng ký {_gio_phut(da_dung)}"
                    f"/{_gio_phut(tran_thang)} — còn {_gio_phut(con_lai)} (gồm cả phiếu chờ duyệt). "
                    f"Phiếu này {_gio_phut(phieu_nay)}. "
                    f"Sửa giờ kết thúc còn tối đa {_hhmm(from_minute + con_lai)}."
                )
        return from_minute, to_minute

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

        from_minute, to_minute = self._validate_window(emp.id, work_date, from_minute, to_minute)

        approved = bool(auto_approve)
        if approved:
            # Tổ trưởng tạo hộ = DUYỆT LUÔN, không qua `_decide`. Thiếu cửa này thì "tạo hộ"
            # thành đường vòng ghi thẳng phút tăng ca vào tháng đã chốt.
            self._chan_neu_ky_cong_da_chot(work_date, "tạo phiếu tăng ca đã duyệt")
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

    def my_requests(self, *, user, page: int = 1,
                    size: int = 20) -> tuple[list[OvertimeRequest], int]:
        """Trả `(rows, total)` — `total` là TỔNG phiếu của NV, không phải số dòng của trang."""
        emp = self._employee_for_user(user)
        total = self.overtime.count_by_employee(emp.id)
        rows = self.overtime.list_by_employee(emp.id, limit=size,
                                              offset=max(0, (page - 1) * size))
        return rows, total

    def list_requests(self, *, scope: str, actor, status: str | None = None,
                      employee_id: int | None = None, page: int = 1,
                      size: int = 20) -> tuple[list[OvertimeRequest], int]:
        """Danh sách phiếu theo DATA-SCOPE người gọi (own = của mình / department = tổ mình +
        cây con / all = tất cả) ⇒ tổ trưởng chỉ thấy & duyệt được người trong tổ.

        `employee_id` chỉ THU HẸP thêm bên trong phạm vi đã có — không nới quyền: gõ id người
        ngoài tổ thì `_scope_condition` vẫn cắt, kết quả rỗng chứ không lộ phiếu."""
        total = self.overtime.count_scoped(scope=scope, actor=actor, status=status,
                                           employee_id=employee_id)
        rows = self.overtime.list_scoped(scope=scope, actor=actor, status=status,
                                         employee_id=employee_id, limit=size,
                                         offset=max(0, (page - 1) * size))
        return rows, total

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

    def _guard_scope(self, employee_id: int, *, scope: str, actor) -> None:
        """Chặn GHI ra ngoài tầm dữ liệu của người gọi.

        Ô quyền `approve` chỉ trả lời "được duyệt hay không", KHÔNG trả lời "được duyệt CHO AI".
        Thiếu chốt này thì tổ trưởng tổ A duyệt được phiếu của người tổ B chỉ cần biết mã phiếu —
        mà chính họ KHÔNG thấy phiếu đó trên màn của mình (đường ĐỌC đã lọc scope). Che ở màn
        không phải là khoá. Phiếu tăng ca RA TIỀN: 150% / 200% / 300% tùy loại ngày.

        `scope` là tham số BẮT BUỘC — cố ý không cho mặc định. Cơ chế "quên khai thì bỏ qua kiểm
        tra" chính là thứ đã để lỗ này tồn tại mà không ai biết (chủ 29/07/2026)."""
        emp = self.employees.get_by_id(employee_id)
        if emp is None:
            return                # phiếu mồ côi NV — validate khác lo, đừng che lỗi thật ở đây
        if not self.employees.can_access(employee=emp, scope=scope, actor=actor):
            raise OvertimeForbidden("Nhân viên này ngoài phạm vi quản lý của bạn.")

    def _decide(self, *, actor, request_id: int, new_status: str, note,
                scope: str) -> OvertimeRequest:
        r = self.overtime.get_request(request_id)
        if r is None:
            raise OvertimeNotFound("Không tìm thấy phiếu tăng ca.")
        self._guard_scope(r.employee_id, scope=scope, actor=actor)
        if r.status != STATUS_PENDING:
            raise OvertimeValidationError("Chỉ duyệt/từ chối được phiếu đang chờ.")
        # Chỉ chặn chiều DUYỆT: phiếu chờ chưa ra phút tăng ca nào, từ chối nó không đổi số.
        if new_status == STATUS_APPROVED:
            self._chan_neu_ky_cong_da_chot(r.work_date, "duyệt phiếu tăng ca")
        self.overtime.update_request(
            r, status=new_status, decided_by=actor.id,
            decided_at=datetime.now(timezone.utc), decision_note=_clean(note),
        )
        self.audit.create(actor_user_id=actor.id, action=f"overtime_{new_status}",
                          target=f"overtime_request:{r.id}", detail=f"→ {new_status}")
        return r

    def approve(self, *, actor, request_id: int, scope: str, note=None) -> OvertimeRequest:
        return self._decide(actor=actor, request_id=request_id,
                            new_status=STATUS_APPROVED, note=note, scope=scope)

    def reject(self, *, actor, request_id: int, note, scope: str) -> OvertimeRequest:
        if not _clean(note):
            raise OvertimeValidationError("Từ chối phải ghi lý do.")
        return self._decide(actor=actor, request_id=request_id,
                            new_status=STATUS_REJECTED, note=note, scope=scope)

    def bulk_approve(self, *, actor, request_ids, scope: str, note=None) -> list[OvertimeRequest]:
        """Duyệt cả mẻ (cả tổ tăng ca cùng một tối). Phiếu không-còn-chờ hoặc NGOÀI PHẠM VI thì
        BỎ QUA, không vỡ mẻ.

        Ngoài phạm vi rơi vào `skipped` chứ KHÔNG nổ 403 cả mẻ: mẻ gửi từ màn chỉ chứa phiếu
        người dùng nhìn thấy, còn ai dò mã lạ thì nhận `skipped` — không lộ phiếu đó có tồn tại
        hay không. 403 cả mẻ vừa hỏng thao tác thật, vừa thành kênh dò thông tin."""
        out: list[OvertimeRequest] = []
        for rid in request_ids or []:
            r = self.overtime.get_request(rid)
            if r is None or r.status != STATUS_PENDING:
                continue
            try:
                out.append(self.approve(actor=actor, request_id=rid, note=note, scope=scope))
            except OvertimeForbidden:
                continue
        return out

    def bulk_reject(self, *, actor, request_ids, note, scope: str) -> list[OvertimeRequest]:
        if not _clean(note):
            raise OvertimeValidationError("Từ chối phải ghi lý do.")
        out: list[OvertimeRequest] = []
        for rid in request_ids or []:
            r = self.overtime.get_request(rid)
            if r is None or r.status != STATUS_PENDING:
                continue
            try:
                out.append(self.reject(actor=actor, request_id=rid, note=note, scope=scope))
            except OvertimeForbidden:
                continue
        return out

    def update_request(self, *, actor, request_id: int, work_date: date, from_minute: int,
                       to_minute: int, reason=None) -> OvertimeRequest:
        """Sửa phiếu ĐANG CHỜ DUYỆT (chủ chốt 2026-07-24). Chỉ người TẠO sửa được phiếu của mình,
        và chỉ khi còn `pending` — duyệt/từ chối/hủy rồi thì khóa. Chạy lại đúng bộ validate như tạo
        (loại chính phiếu này khỏi luật 1 phiếu/ngày)."""
        r = self.overtime.get_request(request_id)
        if r is None:
            raise OvertimeNotFound("Không tìm thấy phiếu tăng ca.")
        if r.created_by != actor.id:
            raise OvertimeForbidden("Bạn chỉ sửa được phiếu do mình tạo.")
        if r.status != STATUS_PENDING:
            raise OvertimeValidationError("Chỉ sửa được phiếu đang chờ duyệt.")
        from_minute, to_minute = self._validate_window(
            r.employee_id, work_date, from_minute, to_minute, exclude_id=r.id
        )
        self.overtime.update_request(r, work_date=work_date, from_minute=from_minute,
                                     to_minute=to_minute, reason=_clean(reason))
        self.audit.create(actor_user_id=actor.id, action="overtime_updated",
                          target=f"overtime_request:{r.id}",
                          detail=f"{work_date} {hhmm(from_minute)}–{hhmm(to_minute)}")
        return r

    def cancel(self, *, actor, request_id: int, is_manager: bool = False) -> OvertimeRequest:
        """Hủy phiếu: người TẠO tự hủy, hoặc người có quyền duyệt hủy hộ. Chỉ hủy phiếu chưa quyết."""
        r = self.overtime.get_request(request_id)
        if r is None:
            raise OvertimeNotFound("Không tìm thấy phiếu tăng ca.")
        if not is_manager and r.created_by != actor.id:
            raise OvertimeForbidden("Bạn chỉ hủy được phiếu do mình tạo.")
        if r.status not in (STATUS_PENDING, STATUS_APPROVED):
            raise OvertimeValidationError("Phiếu này không còn để hủy.")
        # Hủy phiếu ĐÃ DUYỆT của tháng đã chốt = rút phút tăng ca đã đóng băng.
        if r.status == STATUS_APPROVED:
            self._chan_neu_ky_cong_da_chot(r.work_date, "hủy phiếu tăng ca đã duyệt")
        self.overtime.update_request(r, status=STATUS_CANCELLED)
        self.audit.create(actor_user_id=actor.id, action="overtime_cancelled",
                          target=f"overtime_request:{r.id}", detail="→ cancelled")
        return r
