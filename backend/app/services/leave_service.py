"""Leave (Nghỉ phép) business logic — module `nhan_su`.

- Loại nghỉ (leave_types): HR khai (tên + cờ có-lương + hạn mức/năm).
- Đơn nghỉ (leave_requests): NV tạo (nguyên ngày) → workflow chờ duyệt → duyệt / từ chối /
  hủy. Đơn ĐÃ DUYỆT được Bảng công tháng đọc (đánh dấu P/KL). Người tạo = user đăng nhập →
  hồ sơ NV qua `employees.user_id`; HR có thể tạo hộ (truyền employee_id).
Hạn mức phép năm trừ dần NGAY Ở ĐÂY (`_used_working_days`, đơn chờ + đã duyệt, theo ngày làm việc,
reset dương lịch). Quy tiền ngày phép ở Lương (`_luong_cong_split`): từ 17/08/2026 ngày phép có lương
trả ĐỦ mức nền (cơ bản + trách nhiệm), cùng đơn giá với công đi làm.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from ..models.leave import (
    STATUS_APPROVED,
    STATUS_CANCELLED,
    STATUS_PENDING,
    STATUS_REJECTED,
    LeaveRequest,
    LeaveType,
)
from ..models.role import SCOPE_ALL
from ..models.yeu_cau_huy import (
    LOAI_NGHI_PHEP,
    TT_CHO,
    TT_DONG_Y,
    TT_GIU_NGUYEN,
    TT_RUT_LAI,
)
from .bien_che import ly_do_ngoai_bien_che
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.employee_repo import EmployeeRepository
from ..repositories.leave_repo import LeaveRepository
from .khoang_thang import khoang_tao_theo_thang
from .ky_cong_guard import ly_do_ky_cong_da_chot


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


# Giờ Việt Nam cố định +7 (không có giờ mùa hè) — "hôm nay" của luật xin hủy phải là ngày ở xưởng,
# không phải ngày UTC của máy chủ (7h sáng VN mới sang ngày UTC).
_VN = timezone(timedelta(hours=7))


def hom_nay_vn() -> date:
    return datetime.now(_VN).date()


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
        attendance=None,
        payroll=None,
        yeu_cau_huy=None,
    ) -> None:
        self.leaves = leaves
        self.employees = employees
        self.audit = audit
        # AttendanceRepository | None — chỉ để hỏi "kỳ công tháng đó chốt chưa" trước khi duyệt/hủy
        # đơn ĐÃ DUYỆT. Đơn nghỉ có lương RA CÔNG, mà công tháng đã chốt thì đã đóng băng cho bảng
        # lương. Chỉ đọc REPO nên không vòng service↔service.
        self._attendance = attendance
        # LateEarlyRepository | None — phiếu đi muộn/về sớm có tick "trừ vào phép năm" cũng tiêu
        # quỹ phép (nửa buổi = 0,5 ngày). Chỉ đọc REPO nên không vòng service↔service.
        self._late_early = late_early
        # CalendarService | None — lịch chung (loại ngày lễ + tuần T2–T7). Đặt tên `_work_calendar`
        # để KHÔNG che method `calendar()` (lịch nghỉ tháng) của service này. None → fallback Mon–Fri.
        self._work_calendar = calendar
        # PayrollService | None — CHỈ hỏi "tổ này có ăn khoán không" (`che_do_khoan`) để chặn nghỉ
        # phép CÓ LƯƠNG của người khoán / tài xế (khách chốt 15/09/2026). Không có dây này (unit
        # test dựng tối giản) ⇒ không chặn, y như trước.
        self._payroll = payroll
        # YeuCauHuyRepository | None — xin hủy đơn ĐÃ DUYỆT (23/09/2026). None (unit test dựng tối
        # giản) ⇒ không có đường xin hủy, đường hủy thẳng vẫn siết như dưới.
        self._yc = yeu_cau_huy

    def _chan_phep_co_luong_khoan(self, emp, lt) -> None:
        """Người ăn khoán sản lượng / khoán km KHÔNG được dùng loại nghỉ CÓ LƯƠNG.

        Khách chốt 15/09/2026 (PRD bù lỗ §00 F): *"nghỉ phép có lương ấy bên khoán mình sẽ không cho
        dùng"*. Lương cũng không đếm công phép của họ vào bù lỗ theo công — chặn ngay từ cửa đơn để
        không đẻ ra đơn đã duyệt mà không ra tiền. Loại nghỉ KHÔNG lương vẫn dùng bình thường.
        ⚠️ Rủi ro đã ghi cho khách: Đ113 BLLĐ cho nghỉ hằng năm hưởng nguyên lương — khách vẫn chọn."""
        if lt is None or not bool(getattr(lt, "is_paid", False)):
            return
        if self._payroll is None:
            return
        if self._payroll.che_do_khoan(getattr(emp, "department_id", None)):
            raise LeaveValidationError(
                # Câu này HIỆN RA MÀN HÌNH cho người tạo đơn ⇒ chỉ nói luật + cách làm tiếp.
                # Lý do / ngày chốt để ở docstring bên trên, đừng nhét vào câu người dùng đọc.
                "Người ăn lương khoán / khoán km không dùng nghỉ phép có lương. "
                    "Chọn loại nghỉ KHÔNG lương cho người này."
            )

    def chan_phep_khoan(self, emp, leave_type_id) -> None:
        """Cửa công khai cho phiếu đi muộn / về sớm có tick "trừ phép" — cùng luật với đơn nghỉ."""
        if leave_type_id is None:
            return
        self._chan_phep_co_luong_khoan(emp, self.leaves.get_type(int(leave_type_id)))

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
        canh_bao = None
        if bool(t.is_paid) != bool(is_paid):
            # Đổi cờ có-lương hồi tố vào mọi đơn ĐÃ DUYỆT của tháng chưa chốt công (bản rà liên thông
            # C16, 08/09/2026): Tính lại kỳ lương chưa chốt là đổi tiền. Không chặn (chủ có thể cố ý),
            # nhưng nói ra số đơn bị ảnh hưởng để người sửa biết mà Tính lại / kiểm.
            hom_nay = date.today()
            dau_thang = date(hom_nay.year, hom_nay.month, 1)
            anh_huong = [r for r in self.leaves.list_overlapping(dau_thang, date(2100, 1, 1), (STATUS_APPROVED,))
                         if r.leave_type_id == t.id]
            if anh_huong:
                canh_bao = (f"Đổi cờ có lương ảnh hưởng {len(anh_huong)} đơn đã duyệt từ tháng "
                            f"{hom_nay.month:02d}/{hom_nay.year} trở đi (kỳ chưa chốt công): công/tiền "
                            "của những ngày đó đổi theo khi Tính lại bảng lương.")
        self.leaves.update_type(t, name=name, is_paid=bool(is_paid), annual_quota=q,
                                note=_clean(note), is_active=bool(is_active))
        t.canh_bao = canh_bao
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

    def _chan_ngoai_bien_che(self, emp, start_date: date, end_date: date) -> None:
        """Đơn cho ngày NGOÀI biên chế (trước ngày vào, từ ngày nghỉ việc, đang nghỉ dài hạn / đình
        chỉ) ⇒ 400 ở cả lúc gửi lẫn lúc duyệt (bản rà liên thông C1, 08/09/2026): trước đó người đã
        rời công ty vẫn được duyệt phép và trả 1 công/ngày."""
        su_kien = self.employees.list_events(emp.id)
        for d in (start_date, end_date):
            ly_do = ly_do_ngoai_bien_che(emp, su_kien, d)
            if ly_do:
                raise LeaveValidationError(ly_do)

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
        self._chan_ngoai_bien_che(emp, start_date, end_date)
        # Tháng đã chốt công: đơn treo vĩnh viễn, giữ chỗ hạn mức, badge sai — chặn lúc gửi cùng câu
        # chữ với lúc duyệt (bản rà liên thông C4, 08/09/2026).
        if self._attendance is not None:
            loi = ly_do_ky_cong_da_chot(self._attendance, start_date, end_date, viec="gửi đơn nghỉ")
            if loi:
                raise LeaveValidationError(loi)
        lt = self.leaves.get_type(leave_type_id)
        if lt is None or not lt.is_active:
            raise LeaveValidationError("Loại nghỉ không hợp lệ.")
        self._chan_phep_co_luong_khoan(emp, lt)
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

    @staticmethod
    def _khoang_thang(thang):
        """`thang` (YYYY-MM, theo NGÀY TẠO đơn) → (tu, den) UTC, hoặc (None, None) = không lọc."""
        try:
            k = khoang_tao_theo_thang(thang)
        except ValueError as exc:
            raise LeaveValidationError(str(exc)) from None
        return k if k is not None else (None, None)

    def my_requests(self, *, user, page: int = 1, size: int = 20,
                    thang: str | None = None) -> tuple[list[LeaveRequest], int]:
        """Trả `(rows, total)` — `total` là TỔNG đơn của NV (trong tháng tạo nếu lọc), không phải
        số dòng của trang. Mới tạo nhất lên đầu."""
        emp = self._employee_for_user(user)
        tu, den = self._khoang_thang(thang)
        total = self.leaves.count_by_employee(emp.id, tao_tu=tu, tao_den=den)
        rows = self.leaves.list_by_employee(emp.id, limit=size, offset=max(0, (page - 1) * size),
                                            tao_tu=tu, tao_den=den)
        return rows, total

    def list_requests(self, *, scope: str, actor, status: str | None = None,
                      employee_id: int | None = None, page: int = 1,
                      size: int = 20, thang: str | None = None) -> tuple[list[LeaveRequest], int]:
        """Danh sách đơn theo DATA-SCOPE người gọi (own = của mình / department = của phòng /
        all = tất cả). Duyệt tập trung: HCNS/Admin scope=all thấy mọi đơn.

        `employee_id` chỉ THU HẸP thêm bên trong phạm vi đã có — không mở rộng quyền: gõ id của
        người ngoài phạm vi thì `_scope_condition` vẫn cắt, kết quả rỗng chứ không lộ đơn."""
        tu, den = self._khoang_thang(thang)
        total = self.leaves.count_scoped(scope=scope, actor=actor, status=status,
                                         employee_id=employee_id, tao_tu=tu, tao_den=den)
        rows = self.leaves.list_scoped(scope=scope, actor=actor, status=status,
                                       employee_id=employee_id, limit=size,
                                       offset=max(0, (page - 1) * size), tao_tu=tu, tao_den=den)
        return rows, total

    def count_pending(self, *, scope: str, actor) -> int:
        """Số việc chờ duyệt trong scope — nuôi badge sidebar: đơn mới + yêu cầu HỦY đơn đã duyệt
        (23/09/2026). Người duyệt nhìn một con số là biết còn bao nhiêu việc phải quyết."""
        n = self.leaves.count_pending_scoped(scope=scope, actor=actor)
        if self._yc is not None:
            n += self._yc.count_cho_scoped(LOAI_NGHI_PHEP, scope=scope, actor=actor)
        return n

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
            # Phần ĐANG CHỜ trong `used` (đơn nguyên ngày) — chip "đã dùng X · đang chờ Y" (C5b, 08/09/2026):
            # gộp chung thì người ta tưởng đã mất phép cho đơn còn chưa ai duyệt.
            pending = sum(self._wd(r.start_date, r.end_date)
                          for r in self.leaves.list_for_quota(emp.id, t.id, year)
                          if r.status == STATUS_PENDING)
            out.append({
                "leave_type_id": t.id,
                "name": t.name,
                "annual_quota": quota,
                "used": used,
                "remaining": max(quota - used, 0),
                "pending": float(pending),
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

    def _chan_neu_ky_cong_da_chot(self, r: LeaveRequest, viec: str) -> None:
        """Đơn bắc cầu hai tháng (28/8 → 03/9) thì soi CẢ HAI đầu — chỉ cần một đầu nằm trong
        tháng đã chốt là đủ làm lệch số."""
        if self._attendance is None:
            return
        loi = ly_do_ky_cong_da_chot(self._attendance, r.start_date, r.end_date, viec=viec)
        if loi:
            raise LeaveValidationError(loi)

    def _decide(self, *, actor, request_id, new_status, note, scope: str) -> LeaveRequest:
        r = self.leaves.get_request(request_id)
        if r is None:
            raise LeaveNotFound("Không tìm thấy đơn nghỉ.")
        self._guard_scope(r.employee_id, scope=scope, actor=actor)
        # Không TỰ duyệt đơn của mình khi phạm vi chỉ là tổ (07/09/2026): tổ trưởng cũng là NV
        # trong tổ mình. Phạm vi toàn công ty (HCNS/GĐ) là cấp duyệt cuối nên vẫn được.
        if scope != SCOPE_ALL:
            me = self.employees.get_by_user_id(actor.id)
            if me is not None and me.id == r.employee_id:
                raise LeaveForbidden("Không tự duyệt đơn nghỉ của chính mình — nhờ cấp trên duyệt.")
        if r.status != STATUS_PENDING:
            raise LeaveValidationError("Chỉ duyệt/từ chối được đơn đang chờ.")
        # TỪ CHỐI thì không chặn: đơn chờ vốn không tính vào bảng công, từ chối nó chẳng đổi số nào.
        # DUYỆT mới đổi — đó là lúc ngày nghỉ thành công (có lương hoặc không lương).
        if new_status == STATUS_APPROVED:
            emp = self.employees.get_by_id(r.employee_id)
            if emp is not None:
                self._chan_ngoai_bien_che(emp, r.start_date, r.end_date)
            self._chan_neu_ky_cong_da_chot(r, "duyệt đơn nghỉ")
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

    # --- hủy / xin hủy (chủ chốt 23/09/2026 — docs/prd-xin-huy-don-da-duyet.md) -------------
    #
    # Đơn ĐÃ DUYỆT là cam kết trong kế hoạch của tổ ⇒ người lao động KHÔNG tự hủy thẳng nữa, chỉ
    # được XIN hủy; ai có quyền duyệt đơn (trong phạm vi) thì quyết. Không hạn chót. Đơn đang chờ
    # duyệt vẫn tự hủy thoải mái — nó chưa vào kế hoạch nào.

    def _la_cua_minh(self, r: LeaveRequest, actor) -> bool:
        """Đơn của CHÍNH người gọi: người đứng tên đơn, hoặc người đã tạo nó."""
        if r.created_by == actor.id:
            return True
        me = self.employees.get_by_user_id(actor.id)
        return me is not None and me.id == r.employee_id

    def _quan_ly_duoc(self, r: LeaveRequest, actor, *, is_hr: bool, scope: str) -> bool:
        """Người gọi có quyền QUYẾT trên đơn này không: có ô duyệt, người đứng tên nằm trong phạm vi,
        và không tự quyết đơn của mình khi phạm vi chỉ là tổ (cùng luật với `_decide`)."""
        if not is_hr:
            return False
        try:
            self._guard_scope(r.employee_id, scope=scope, actor=actor)
        except LeaveForbidden:
            return False
        if scope != SCOPE_ALL:
            me = self.employees.get_by_user_id(actor.id)
            if me is not None and me.id == r.employee_id:
                return False
        return True

    def cancel(self, *, actor, request_id, is_hr: bool = False, scope: str = "own",
               ly_do=None) -> LeaveRequest:
        """Hủy THẲNG. Đơn đang chờ: người đứng tên / người tạo tự hủy, hoặc người duyệt hủy hộ.
        Đơn ĐÃ DUYỆT: chỉ người có quyền duyệt (trong phạm vi), và phải ghi lý do — người lao động
        đi đường XIN hủy (`xin_huy`)."""
        r = self.leaves.get_request(request_id)
        if r is None:
            raise LeaveNotFound("Không tìm thấy đơn nghỉ.")
        quan_ly = self._quan_ly_duoc(r, actor, is_hr=is_hr, scope=scope)
        if not quan_ly and not self._la_cua_minh(r, actor):
            if is_hr:
                self._guard_scope(r.employee_id, scope=scope, actor=actor)   # nói đúng lý do 403
            raise LeaveForbidden("Bạn chỉ hủy được đơn của mình.")
        if r.status in (STATUS_REJECTED, STATUS_CANCELLED):
            raise LeaveValidationError("Đơn đã kết thúc, không hủy được.")
        ly_do = _clean(ly_do)
        da_duyet = r.status == STATUS_APPROVED
        if da_duyet:
            if not quan_ly:
                raise LeaveValidationError(
                    "Đơn đã được duyệt nên không tự hủy được. Bấm “Xin hủy” và ghi lý do — người "
                    "duyệt đồng ý thì đơn mới hủy."
                )
            if not ly_do:
                raise LeaveValidationError("Hủy đơn đã duyệt phải ghi lý do để người lao động biết.")
            # Hủy một đơn ĐÃ DUYỆT của tháng đã chốt = GỠ công đã đóng băng ⇒ hai màn lệch nhau.
            self._chan_neu_ky_cong_da_chot(r, "hủy đơn nghỉ đã duyệt")
        self.leaves.update_request(r, status=STATUS_CANCELLED)
        if da_duyet and self._yc is not None:
            # Lý do hủy thẳng có chỗ lưu + người lao động đọc được. Yêu cầu xin hủy đang chờ (nếu có)
            # coi như được đồng ý bằng chính lần hủy này.
            cho = self._yc.get_cho(LOAI_NGHI_PHEP, r.id)
            bay_gio = datetime.now(timezone.utc)
            if cho is not None:
                self._yc.update(cho, trang_thai=TT_DONG_Y, decided_by=actor.id, decided_at=bay_gio,
                                ly_do_quyet=ly_do)
            else:
                self._yc.create(loai=LOAI_NGHI_PHEP, request_id=r.id, employee_id=r.employee_id,
                                ly_do=ly_do, trang_thai=TT_DONG_Y, truc_tiep=True,
                                created_by=actor.id, decided_by=actor.id, decided_at=bay_gio,
                                ly_do_quyet=ly_do)
        self.audit.create(actor_user_id=actor.id, action="leave_cancelled",
                          target=f"leave_request:{r.id}",
                          detail="hủy đơn" + (f" — {ly_do}" if ly_do else ""))
        return r

    def get_request(self, request_id) -> LeaveRequest | None:
        return self.leaves.get_request(request_id)

    def _can_yc(self):
        if self._yc is None:
            raise LeaveValidationError("Chưa bật chức năng xin hủy.")
        return self._yc

    def xin_huy(self, *, actor, request_id, ly_do, hom_nay: date | None = None):
        """Người lao động XIN hủy đơn ĐÃ DUYỆT. Đơn vẫn hiệu lực tới khi người duyệt đồng ý.

        Đơn nghỉ ĐANG DỞ (đã tới ngày bắt đầu) — chủ chốt *"tính nghỉ 1 ngày"*: đồng ý thì đơn
        được RÚT NGẮN, giữ các ngày TRƯỚC ngày gửi xin hủy, hủy từ ngày gửi trở đi. Đơn đã qua hết
        (quá ngày kết thúc) thì không xin hủy được — việc đã xảy ra, sai sót thì báo HCNS."""
        yc_repo = self._can_yc()
        r = self.leaves.get_request(request_id)
        if r is None:
            raise LeaveNotFound("Không tìm thấy đơn nghỉ.")
        if not self._la_cua_minh(r, actor):
            raise LeaveForbidden("Bạn chỉ xin hủy được đơn của mình.")
        if r.status == STATUS_PENDING:
            raise LeaveValidationError("Đơn đang chờ duyệt — bấm “Hủy đơn” để hủy thẳng, không cần xin.")
        if r.status != STATUS_APPROVED:
            raise LeaveValidationError("Đơn đã kết thúc, không hủy được.")
        ly_do = _clean(ly_do)
        if not ly_do:
            raise LeaveValidationError("Cần ghi lý do xin hủy để người duyệt cân nhắc.")
        hom_nay = hom_nay or hom_nay_vn()
        if r.end_date < hom_nay:
            raise LeaveValidationError(
                "Đơn nghỉ này đã qua nên không xin hủy được. Có sai sót thì báo HCNS."
            )
        if yc_repo.get_cho(LOAI_NGHI_PHEP, r.id) is not None:
            raise LeaveValidationError("Đơn này đã có yêu cầu hủy đang chờ duyệt.")
        huy_tu = max(r.start_date, hom_nay)
        # Phần bị hủy nằm ở tháng đã chốt công thì yêu cầu này là ngõ cụt — chặn ngay lúc gửi.
        if self._attendance is not None:
            loi = ly_do_ky_cong_da_chot(self._attendance, huy_tu, r.end_date, viec="xin hủy đơn nghỉ")
            if loi:
                raise LeaveValidationError(loi)
        dang_do = huy_tu > r.start_date
        yc = yc_repo.create(loai=LOAI_NGHI_PHEP, request_id=r.id, employee_id=r.employee_id,
                            ly_do=ly_do, trang_thai=TT_CHO,
                            huy_tu_ngay=huy_tu if dang_do else None, created_by=actor.id)
        self.audit.create(actor_user_id=actor.id, action="leave_cancel_requested",
                          target=f"leave_request:{r.id}",
                          detail=(f"xin hủy từ {huy_tu:%d/%m/%Y}" if dang_do else "xin hủy cả đơn")
                          + f" — {ly_do}")
        return r, yc

    def rut_lai_xin_huy(self, *, actor, yc_id):
        """Người lao động rút lại yêu cầu hủy khi chưa ai quyết — đơn giữ nguyên như đã duyệt."""
        yc_repo = self._can_yc()
        yc = yc_repo.get(yc_id)
        if yc is None or yc.loai != LOAI_NGHI_PHEP:
            raise LeaveNotFound("Không tìm thấy yêu cầu hủy.")
        if yc.created_by != actor.id:
            raise LeaveForbidden("Bạn chỉ rút lại được yêu cầu của mình.")
        if yc.trang_thai != TT_CHO:
            raise LeaveValidationError("Yêu cầu này đã được xử lý, không rút lại được.")
        yc_repo.update(yc, trang_thai=TT_RUT_LAI, decided_at=datetime.now(timezone.utc))
        self.audit.create(actor_user_id=actor.id, action="leave_cancel_request_withdrawn",
                          target=f"leave_request:{yc.request_id}", detail="rút lại yêu cầu hủy")
        return self.leaves.get_request(yc.request_id), yc

    def quyet_xin_huy(self, *, actor, yc_id, dong_y: bool, ghi_chu=None, scope: str):
        """Người có quyền duyệt (trong phạm vi) ĐỒNG Ý hủy hoặc GIỮ NGUYÊN đơn. Giữ nguyên phải ghi
        lý do để người lao động biết vì sao vẫn nghỉ / vẫn phải đi làm như đã duyệt."""
        yc_repo = self._can_yc()
        yc = yc_repo.get(yc_id)
        if yc is None or yc.loai != LOAI_NGHI_PHEP:
            raise LeaveNotFound("Không tìm thấy yêu cầu hủy.")
        r = self.leaves.get_request(yc.request_id)
        if r is None:
            raise LeaveNotFound("Không tìm thấy đơn nghỉ.")
        self._guard_scope(r.employee_id, scope=scope, actor=actor)
        if scope != SCOPE_ALL:
            me = self.employees.get_by_user_id(actor.id)
            if me is not None and me.id == r.employee_id:
                raise LeaveForbidden("Không tự duyệt yêu cầu hủy đơn của chính mình — nhờ cấp trên.")
        if yc.trang_thai != TT_CHO:
            raise LeaveValidationError("Yêu cầu hủy này đã được xử lý.")
        ghi_chu = _clean(ghi_chu)
        bay_gio = datetime.now(timezone.utc)
        if not dong_y:
            if not ghi_chu:
                raise LeaveValidationError("Giữ nguyên đơn phải ghi lý do để người lao động biết.")
            yc_repo.update(yc, trang_thai=TT_GIU_NGUYEN, decided_by=actor.id, decided_at=bay_gio,
                           ly_do_quyet=ghi_chu)
            self.audit.create(actor_user_id=actor.id, action="leave_cancel_request_rejected",
                              target=f"leave_request:{r.id}", detail=f"giữ nguyên đơn — {ghi_chu}")
            return r, yc
        if r.status != STATUS_APPROVED:
            raise LeaveValidationError("Đơn không còn ở trạng thái đã duyệt — không cần hủy nữa.")
        huy_tu = yc.huy_tu_ngay
        giu_den = (huy_tu - timedelta(days=1)) if huy_tu is not None and huy_tu > r.start_date else None
        # Phần giữ lại rơi hết vào ngày nghỉ (vd nghỉ từ T7, xin hủy từ T2) thì chẳng còn ngày phép
        # nào để giữ ⇒ hủy cả đơn cho sạch, đừng để lại một đơn "nghỉ" toàn ngày không đi làm.
        if giu_den is not None and self._wd(r.start_date, giu_den) == 0:
            giu_den = None
        if self._attendance is not None:
            loi = ly_do_ky_cong_da_chot(self._attendance, huy_tu if giu_den else r.start_date,
                                        r.end_date, viec="đồng ý hủy đơn nghỉ")
            if loi:
                raise LeaveValidationError(loi)
        if giu_den is not None:
            den_cu = r.end_date
            self.leaves.update_request(r, end_date=giu_den, days=(giu_den - r.start_date).days + 1)
            yc_repo.update(yc, trang_thai=TT_DONG_Y, decided_by=actor.id, decided_at=bay_gio,
                           ly_do_quyet=ghi_chu, den_ngay_cu=den_cu)
            viec = f"rút ngắn đơn còn {r.start_date:%d/%m}–{giu_den:%d/%m/%Y} (gốc tới {den_cu:%d/%m/%Y})"
        else:
            self.leaves.update_request(r, status=STATUS_CANCELLED)
            yc_repo.update(yc, trang_thai=TT_DONG_Y, decided_by=actor.id, decided_at=bay_gio,
                           ly_do_quyet=ghi_chu)
            viec = "hủy cả đơn"
        self.audit.create(actor_user_id=actor.id, action="leave_cancel_request_approved",
                          target=f"leave_request:{r.id}",
                          detail=viec + (f" — {ghi_chu}" if ghi_chu else ""))
        return r, yc

    def xin_huy_cho_duyet(self, *, scope: str, actor) -> list:
        """Yêu cầu hủy đang chờ trong phạm vi người duyệt, kèm đơn gốc: [(yc, đơn)]."""
        if self._yc is None:
            return []
        out = []
        for yc in self._yc.list_cho_scoped(LOAI_NGHI_PHEP, scope=scope, actor=actor):
            r = self.leaves.get_request(yc.request_id)
            if r is not None:
                out.append((yc, r))
        return out

    def yeu_cau_huy_moi_nhat(self, request_ids) -> dict:
        """{request_id: yêu cầu hủy mới nhất} — nuôi nhãn trên bảng đơn."""
        if self._yc is None:
            return {}
        return self._yc.moi_nhat_theo_don(LOAI_NGHI_PHEP, request_ids)

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
        # Đơn đã duyệt đang có yêu cầu hủy chờ quyết: VẪN là ngày nghỉ (đơn còn hiệu lực), chỉ gắn dấu
        # để tổ trưởng xếp người biết có thể người này sẽ đi làm lại (23/09/2026).
        yc_moi = self.yeu_cau_huy_moi_nhat([r.id for r in reqs if r.status == STATUS_APPROVED])
        dang_xin_huy = {rid for rid, yc in yc_moi.items() if yc.trang_thai == TT_CHO}
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
                        "dang_xin_huy": r.id in dang_xin_huy,
                    }
                d = date.fromordinal(d.toordinal() + 1)
        return {
            "year": year, "month": month, "days_in_month": last.day,
            "employees": sorted(out.values(), key=lambda e: e["employee_name"]),
        }
