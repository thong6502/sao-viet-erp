"""Employee ORM models (Hồ sơ nhân sự — module `nhan_su`, lát #1).

Three tables:
  - `employees`            — hồ sơ nhân viên (master). `code` NV### tự sinh; owned by a
                             `department_id` (trục RBAC data-scope). `user_id` nối tài khoản
                             login 1–1 tùy chọn (UNIQUE, nullable) — công nhân xưởng không
                             đăng nhập vẫn có hồ sơ. `employees` là PROVIDER sẵn cho SEAM-19
                             (đóng khi Tài xế build, thêm FK `drivers.employee_id`).
  - `employee_events`      — Quá trình công tác: mỗi giai đoạn (thử việc→chính thức, điều
                             chuyển, nâng bậc, nghỉ…) là 1 dòng theo `effective_date` (ngày
                             hiệu lực, KHÁC `created_at` ngày nhập máy). Là nguồn timeline.
  - `employee_attachments` — file hồ sơ (HĐ scan / CCCD / bằng cấp), nằm trong kho file
                             (app/storage.py) như avatar; đọc qua /api/files, đòi quyền `nhan_su`.

Portable across SQLite and Postgres (integer PK, string/date columns, DB-agnostic
timestamp default).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    false as sa_false,
    true as sa_true,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# --- Trạng thái nhân viên (vòng đời) ----------------------------------------
# --- Cách tính thuế TNCN của một người --------------------------------------
PIT_LUY_TIEN = "luy_tien"        # HĐ ≥ 3 tháng: bảng luỹ tiến + giảm trừ gia cảnh
PIT_KHAU_TRU_10 = "khau_tru_10"  # HĐ < 3 tháng / thời vụ: khấu trừ 10% tại nguồn
PIT_CAM_KET_08 = "cam_ket_08"    # có cam kết 08/CK-TNCN ⇒ không khấu trừ
PIT_MODES = (PIT_LUY_TIEN, PIT_KHAU_TRU_10, PIT_CAM_KET_08)

STATUS_PROBATION = "probation"      # thử việc
STATUS_ACTIVE = "active"            # đang làm việc (chính thức)
STATUS_ON_LEAVE = "on_leave"        # nghỉ dài hạn (thai sản / ốm / không lương)
STATUS_SUSPENDED = "suspended"      # tạm đình chỉ
STATUS_RESIGNED = "resigned"        # đã nghỉ việc
EMPLOYEE_STATUSES = (
    STATUS_PROBATION,
    STATUS_ACTIVE,
    STATUS_ON_LEAVE,
    STATUS_SUSPENDED,
    STATUS_RESIGNED,
)

GENDERS = ("male", "female", "other")

# --- Loại mốc Quá trình công tác --------------------------------------------
EVENT_HIRED = "hired"               # vào làm (mốc đầu, sinh tự động khi tạo NV)
EVENT_CONFIRMED = "confirmed"       # chuyển chính thức (probation → active)
EVENT_TRANSFERRED = "transferred"   # điều chuyển phòng/tổ
EVENT_PROMOTED = "promoted"         # nâng bậc thợ / đổi chức danh
EVENT_LEAVE_START = "leave_start"   # bắt đầu nghỉ dài hạn
EVENT_LEAVE_END = "leave_end"       # kết thúc nghỉ dài hạn (đi làm lại)
EVENT_SUSPENDED = "suspended"       # đình chỉ
EVENT_RESIGNED = "resigned"         # nghỉ việc
EVENT_REINSTATED = "reinstated"     # tuyển lại (resigned → active)
EMPLOYEE_EVENT_TYPES = (
    EVENT_HIRED,
    EVENT_CONFIRMED,
    EVENT_TRANSFERRED,
    EVENT_PROMOTED,
    EVENT_LEAVE_START,
    EVENT_LEAVE_END,
    EVENT_SUSPENDED,
    EVENT_RESIGNED,
    EVENT_REINSTATED,
)

# --- Loại file đính kèm hồ sơ -----------------------------------------------
DOC_HOP_DONG = "hop_dong"           # hợp đồng lao động (scan)
DOC_CCCD = "cccd"                   # CCCD / CMND
DOC_BANG_CAP = "bang_cap"           # bằng cấp / chứng chỉ
DOC_KHAC = "khac"                   # khác
ATTACHMENT_DOC_KINDS = (DOC_HOP_DONG, DOC_CCCD, DOC_BANG_CAP, DOC_KHAC)


# --- Danh mục BẬC TAY NGHỀ (chủ 2026-07-29) ---------------------------------
# 5 BẬC CHÍNH, hạng CAO NHẤT đứng đầu (seq 1). Tên gọi DÂN DÃ theo cách xưởng gọi nhau
# (chủ 2026-08-19): thợ cứng tay nhất → mới vào. Mã `bac_1…bac_5` GIỮ NGUYÊN làm khoá ổn định —
# tên chỉ là nhãn hiển thị, đổi tên không đụng hạng của ai.
# (Đường đời: bản đầu 3 chính + 2 phụ `tho_*`/`phu_*` → migration 0129 gộp về Bậc 1…5 → migration
# 0155 đổi sang tên dân dã dưới đây. Tất cả đổi tên TẠI CHỖ giữ id nên không ai mất bậc.)
JOB_GRADE_SEED = (
    ("bac_1", "Thợ lành nghề", 1),
    ("bac_2", "Thợ vững", 2),
    ("bac_3", "Thợ thường", 3),
    ("bac_4", "Tập việc", 4),
    ("bac_5", "Lính mới", 5),
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobGrade(Base):
    """Danh mục bậc tay nghề — dùng cho khối SẢN XUẤT.

    🚫 **KHAI BẬC THÔI — KHÔNG có tiền, KHÔNG có hệ số** (chủ 2026-07-29). Bảng này cố ý chỉ có
    mã · tên · thứ tự · bật/tắt. Gán bậc cho một người KHÔNG làm đổi một đồng nào trên bảng lương;
    có test chốt việc đó. Khi nào cần chia sản lượng khoán theo bậc thì treo thêm cột vào ĐÂY —
    không phải đi sửa hồ sơ từng người. Đó là lý do bậc là một BẢNG có id, không phải ô chữ.
    """

    __tablename__ = "job_grades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Mã ổn định: `bac_1`…`bac_5`. Bộ `pay_grade_key` CŨ ('tho_*'/'phu_*') được migration 0127
    # ánh xạ sang đây khi backfill, nên hồ sơ khai bằng mã cũ vẫn về đúng bậc.
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    # Thứ tự hiển thị. Số NHỎ = bậc CAO (hạng cứng tay nhất đứng đầu) — theo cách chủ liệt kê.
    seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # Tắt thay vì xoá khi một bậc thôi dùng: hồ sơ cũ đang trỏ vào vẫn đọc được tên bậc.
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=sa_true()
    )
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Hệ số quy đổi SẢN LƯỢNG theo bậc — nền chia khoán ở module Thực hiện sản xuất
    # (spec-thuc-hien-san-xuat §8). Đây ĐÚNG là "treo cột vào bảng bậc" mà docstring lớp này đã dặn:
    # khi phân bổ sản lượng lô cho từng người, phần của mỗi người được nhân hệ số bậc này (thợ cứng
    # tay ăn nhiều hơn tập việc trên cùng một mẻ). NULL = CHƯA khai ⇒ engine coi như 1.0 (chia đều theo
    # thời gian tham gia); khai bậc KHÔNG tự động đổi lương cho tới khi hệ số được điền + có mẻ khoán.
    output_coefficient: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # System-generated sequential code (NV001, NV002…). Unique + read-only; never entered
    # by the user (following the KH###/SP###/PB### pattern).
    code: Mapped[str] = mapped_column(
        String(20), unique=True, index=True, nullable=False
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Phòng/tổ — trục RBAC data-scope (own/department/all lọc theo cột này). Nullable so a
    # freshly-created hồ sơ can exist before assignment.
    department_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("departments.id"), index=True, nullable=True
    )
    # Optional 1–1 login account. UNIQUE ⇒ one user account backs at most one employee;
    # nullable ⇒ a factory worker who never logs in still has a hồ sơ.
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), unique=True, index=True, nullable=True
    )
    position: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # BẬC TAY NGHỀ — nguồn sự thật DUY NHẤT từ 2026-07-29 (chủ). Trỏ danh mục `job_grades`.
    # Chỉ đổi qua TRANSITION (`promote`/`transfer`), KHÔNG qua sửa hồ sơ thường — xem
    # `EDITABLE_FIELDS` trong employee_service — nên mọi lần đổi bậc đều có dòng Quá trình công tác.
    job_grade_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("job_grades.id"), index=True, nullable=True
    )
    # DORMANT từ 2026-07-29: bậc thợ chữ tự do (vd "3/7"). Migration 0127 đã chuyển sang
    # `job_grade_id`; cột giữ lại cho dữ liệu cũ, NGỪNG GHI, chỉ đọc khi `job_grade_id` null.
    job_grade: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Thâm niên ĐÃ CÓ trước khi vào làm (tháng) — người từng làm nơi khác chuyển sang phải khai.
    # Tổng thâm niên = prior_seniority_months + thời gian từ hire_date. Đợt 1 chỉ LƯU + hiển thị;
    # engine CHƯA dùng số này tính tiền (phụ cấp thâm niên vẫn khai tay per-người).
    prior_seniority_months: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=STATUS_PROBATION, server_default=STATUS_PROBATION
    )
    hire_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Ngày dự kiến hết thử việc → cơ sở KPI "sắp hết thử việc".
    probation_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    resign_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    resign_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # --- Cá nhân ---
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # CCCD/CMND. Indexed for the soft duplicate-check but NOT unique (cảnh báo mềm, không chặn).
    national_id: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)
    national_id_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    national_id_place: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    permanent_address: Mapped[str | None] = mapped_column(String(500), nullable=True)  # hộ khẩu
    current_address: Mapped[str | None] = mapped_column(String(500), nullable=True)    # chỗ ở
    emergency_contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # --- BHXH / TNCN / ngân hàng (khai sẵn cho phân hệ Lương) ---
    # Số sổ BHXH. Indexed for the soft duplicate-check but NOT unique.
    social_insurance_no: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)
    pit_tax_code: Mapped[str | None] = mapped_column(String(20), nullable=True)  # MST cá nhân
    dependents_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # CÁCH TÍNH THUẾ TNCN (chủ 2026-07-27). Ba trạng thái nên dùng String, KHÔNG nhồi 2 cờ Boolean
    # (2 cờ = 4 tổ hợp, có 1 tổ hợp vô nghĩa — chỗ để dữ liệu lệch):
    #   `luy_tien`    — HĐ từ 3 tháng trở lên: bảng luỹ tiến + giảm trừ gia cảnh (mặc định).
    #   `khau_tru_10` — HĐ dưới 3 tháng / thời vụ / thực tập: khấu trừ 10% tại nguồn, KHÔNG bảng
    #                   luỹ tiến, KHÔNG giảm trừ gia cảnh.
    #   `cam_ket_08`  — đã làm cam kết 08/CK-TNCN (cả năm chưa tới ngưỡng chịu thuế) ⇒ không khấu trừ.
    pit_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default=PIT_LUY_TIEN, server_default=PIT_LUY_TIEN
    )
    bank_account: Mapped[str | None] = mapped_column(String(30), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # --- Lương (module `luong`) ---
    # Nhóm lương — trục tra bảng chính sách mức lương (salary_rate_rules), vd 'to_in',
    # 'to_dan', 'van_phong'. Null = chưa gán (tính lương sẽ nhắc khai).
    payroll_group: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    # DORMANT từ 2026-07-29: bậc lương chuẩn hóa 'tho_1'…'phu_2'. Bộ mã này ĐÃ THÀNH danh mục
    # `job_grades` (cùng mã) và bậc của NV nằm ở `job_grade_id`. Cột giữ cho dữ liệu cũ, đã GỠ
    # khỏi `EDITABLE_FIELDS` ⇒ không ai ghi được nữa. Để hai ô cùng nghĩa cùng sửa được chính là
    # cái bẫy C-3 (sửa ô này không đổi ô kia) — nên chỉ còn MỘT đường ghi.
    pay_grade_key: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # --- Ca kíp ---
    # Ca làm việc mặc định (logical link → work_shifts.id; không FK cứng để tránh vòng
    # create_all, giống head_user_id). Null = chưa gán ca.
    default_shift_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)

    # Server-relative path of the profile photo (mirror users.avatar_url), e.g.
    # `/api/files/hr/<id>/photo.jpg`. Null → UI shows initials fallback.
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class EmployeeShiftAssignment(Base):
    """Ca mac dinh cua nhan vien tai mot moc hieu luc.

    Doi ca tao them mot moc moi. Khoang ket thuc cua mot moc duoc suy ra bang
    ngay lien truoc moc ke tiep, giong cach employee_salaries chon muc luong
    hien hanh. ``shift_id = NULL`` bieu dien bo gan ca tu ngay hieu luc.
    """

    __tablename__ = "employee_shift_assignments"
    __table_args__ = (
        UniqueConstraint("employee_id", "effective_from", name="uq_employee_shift_effective"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Logical link to work_shifts.id. Nullable means the employee has no default
    # shift from this date onward.
    shift_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    effective_from: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class EmployeeShiftDay(Base):
    """Ca cua nhan vien tai MOT NGAY cu the — lop DE len ca mac dinh theo moc.

    Dung cho xoay ca linh hoat (hom nay ca khuya, mai ca ngay). Moi ngay cong van
    chi 1 ca: ``UniqueConstraint(employee_id, work_date)`` la hang rao cung cho luat
    do. Lam ngoai khung ca la TANG CA (module rieng), khong phai ca thu hai.

    Ba trang thai cua mot o luoi phan ca:
      - KHONG co dong        -> ke thua ca mac dinh (employee_shift_assignments).
      - dong co ``shift_id`` -> ca cu the cho ngay do (de len moc).
      - dong ``is_off=True`` -> NGHI theo lich (nghi luan phien rieng cua tung nguoi).

    ``is_off`` chi la DAU KE HOACH: no KHONG chan cham cong va KHONG sinh he so
    luong. Nguoi bi goi di lam dung ngay nghi rieng van cham cong duoc va huong
    1x nhu ngay thuong — nen ``shift_id_on`` co y BO QUA dong ``is_off`` va roi
    xuong ca nen. Chu nhat van theo luat nghi tuan chung (x2), khong doi.
    """

    __tablename__ = "employee_shift_days"
    __table_args__ = (
        UniqueConstraint("employee_id", "work_date", name="uq_employee_shift_day"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # NGAY CONG (khong phai ngay lich cua luot bam) — cung truc voi work_day_of().
    work_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    # Logical link to work_shifts.id (khong FK cung, giong employee_shift_assignments).
    # NULL di kem is_off=True nghia la ngay nghi theo lich.
    shift_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    is_off: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=sa_false(), nullable=False
    )
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


# Hai LỚP sinh ra ca của một người — trục `kind` của bảng lịch sử dưới đây.
SHIFT_LOG_KIND_DAY = "day"     # ô một ngày trên lưới phân ca (`employee_shift_days`)
SHIFT_LOG_KIND_BASE = "base"   # ca nền theo mốc hiệu lực (`employee_shift_assignments`)
SHIFT_LOG_KINDS = (SHIFT_LOG_KIND_DAY, SHIFT_LOG_KIND_BASE)

# Thao tác đến TỪ MÀN NÀO. Có 5 đường thật sự đổi ca của người ta; thiếu một đường là màn
# lịch sử báo "không có thay đổi" trong khi ca đã đổi — xem docstring `EmployeeShiftChangeLog`.
SHIFT_LOG_ORIGIN_GRID = "grid"                # Khai ca → Phân ca tháng (lưới)
SHIFT_LOG_ORIGIN_BASE_PANEL = "base_panel"    # panel Gán ca — một người
SHIFT_LOG_ORIGIN_BASE_BULK = "base_bulk"      # panel Gán ca — hàng loạt
SHIFT_LOG_ORIGIN_PROFILE = "profile"          # sửa hồ sơ NV (đổi `default_shift_id`)
SHIFT_LOG_ORIGIN_BASE_REMOVE = "base_remove"  # gỡ một mốc ca nền gán nhầm
SHIFT_LOG_ORIGINS = (
    SHIFT_LOG_ORIGIN_GRID, SHIFT_LOG_ORIGIN_BASE_PANEL, SHIFT_LOG_ORIGIN_BASE_BULK,
    SHIFT_LOG_ORIGIN_PROFILE, SHIFT_LOG_ORIGIN_BASE_REMOVE,
)

SHIFT_LOG_ACTION_SET = "set"
SHIFT_LOG_ACTION_OFF = "off"
SHIFT_LOG_ACTION_INHERIT = "inherit"
SHIFT_LOG_ACTION_REMOVE = "remove"
SHIFT_LOG_ACTIONS = (SHIFT_LOG_ACTION_SET, SHIFT_LOG_ACTION_OFF,
                     SHIFT_LOG_ACTION_INHERIT, SHIFT_LOG_ACTION_REMOVE)


class EmployeeShiftChangeLog(Base):
    """LỊCH SỬ mọi lần ca của một người bị đổi — và hộp thư báo cho chính người đó.

    Vì sao phải có bảng riêng: `employee_shift_days` / `employee_shift_assignments` đều GHI ĐÈ,
    nên giá trị cũ mất hẳn. Nhật ký chung (`audit_logs`) chỉ có một dòng gộp kiểu "3 ô khai, 1 ô
    về mặc định" — không biết ô nào, từ ca gì sang ca gì.

    ⚠️ CA CỦA MỘT NGƯỜI ĐẾN TỪ HAI LỚP, và có **5 đường** ghi. Quên móc một đường là màn lịch sử
    nói "không có thay đổi nào" trong khi ca người ta vừa bị đổi — tệ hơn là không có màn lịch sử:

        lưới ngày   → `attendance_service.set_shift_plan`            (kind=day,  origin=grid)
        ca nền      → `employee_service.set_default_shift`           (kind=base, origin=base_panel)
                    → `employee_service.set_default_shift_bulk`      (kind=base, origin=base_bulk)
                    → `employee_service.update_employee`             (kind=base, origin=profile)
                    → `employee_service.delete_shift_assignment`     (kind=base, origin=base_remove)

    `create_employee` CỐ Ý KHÔNG ghi (chốt chủ 28/07/2026): gán ca lần đầu lúc lập hồ sơ chưa có ca
    cũ nào để so — ghi vào chỉ làm lịch sử lẫn dòng rác. Ca đầu tiên vẫn tra được ở bảng mốc.

    Mọi đường ghi qua CÙNG một hàm `ShiftChangeLogRepository.log()`. Và luật xuyên suốt:
    **trước == sau thì KHÔNG ghi** — lưới phân ca hay được bấm Lưu cả tháng một lần, không lọc là
    mỗi lần lưu đẻ vài chục dòng rỗng + ngần ấy thông báo rác, chuông mất giá trị sau đúng một ngày.
    """

    __tablename__ = "employee_shift_change_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(8), nullable=False)     # SHIFT_LOG_KINDS
    origin: Mapped[str] = mapped_column(String(16), nullable=False)  # SHIFT_LOG_ORIGINS
    action: Mapped[str] = mapped_column(String(8), nullable=False)   # SHIFT_LOG_ACTIONS
    # kind=day  → NGÀY CÔNG bị đổi.
    # kind=base → `effective_from` của mốc (ca áp từ ngày này TRỞ VỀ SAU, không riêng ngày đó).
    apply_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    # Logical link → work_shifts.id (không FK cứng, giống 2 bảng ca kia). NULL = không có ca.
    shift_id_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shift_id_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Chỉ có nghĩa với kind=day (ô "Nghỉ theo lịch").
    is_off_before: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa_false()
    )
    is_off_after: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa_false()
    )
    # kind=day: TRƯỚC đó ô đang KẾ THỪA ca nền (chưa ai khai tay ngày này). Đây là chỗ trả lời
    # "ca này do nền hay do người sửa" mà giao diện cần để hiện icon cây bút.
    inherited_before: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa_false()
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True, nullable=False
    )
    # Tài khoản ĐÃ đẩy thông báo tới. NULL = NV không có tài khoản đăng nhập (công nhân xưởng) ⇒
    # không báo được cho ai; màn khai ca đếm số này ra dòng "N người chưa báo được".
    notified_user_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    # Người nhận đã đọc lúc nào. NULL = chưa đọc ⇒ nuôi badge (mirror `count_my_decided_unseen`).
    seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EmployeeEvent(Base):
    """One mốc "Quá trình công tác" of an employee. Written by the service whenever a
    stage changes (status / department / job_grade) — never edited by hand."""

    __tablename__ = "employee_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # One of EMPLOYEE_EVENT_TYPES (hired/confirmed/transferred/promoted/leave_*/suspended/resigned/reinstated).
    event_type: Mapped[str] = mapped_column(String(24), nullable=False)
    # Ngày hiệu lực của giai đoạn (khác created_at = ngày nhập máy).
    effective_date: Mapped[date | None] = mapped_column(Date, index=True, nullable=True)
    # What changed, e.g. field="status", from_value="probation", to_value="active".
    field: Mapped[str | None] = mapped_column(String(40), nullable=True)
    from_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    to_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)  # lý do / ghi chú
    actor_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class EmployeeAttachment(Base):
    """A file attached to an employee (HĐ scan / CCCD / bằng cấp). The bytes live in the shared
    file store (app/storage.py) and are served through /api/files, which requires a login and the
    `nhan_su` read permission; only the path is stored here (mirror users.avatar_url)."""

    __tablename__ = "employee_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # One of ATTACHMENT_DOC_KINDS (hop_dong/cccd/bang_cap/khac).
    doc_kind: Mapped[str] = mapped_column(
        String(24), nullable=False, default=DOC_KHAC, server_default=DOC_KHAC
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str | None] = mapped_column(String(100), nullable=True)  # MIME
    uploaded_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
