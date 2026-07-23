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
  - `employee_attachments` — file hồ sơ (HĐ scan / CCCD / bằng cấp), lưu dưới /static như
                             avatar (mirror `quote_attachments`).

Portable across SQLite and Postgres (integer PK, string/date columns, DB-agnostic
timestamp default).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# --- Trạng thái nhân viên (vòng đời) ----------------------------------------
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


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
    # Bậc thợ (vd "3/7") — đầu vào lương khoán sau này. Free-text ở lát #1.
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
    bank_account: Mapped[str | None] = mapped_column(String(30), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # --- Lương (module `luong`) ---
    # Nhóm lương — trục tra bảng chính sách mức lương (salary_rate_rules), vd 'to_in',
    # 'to_dan', 'van_phong'. Null = chưa gán (tính lương sẽ nhắc khai).
    payroll_group: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    # Bậc lương chuẩn hóa cho tổ tính theo bậc (tổ In): 'tho_1'/'tho_2'/'tho_3'/'phu_1'/'phu_2'.
    # Tách khỏi `job_grade` free-text ("3/7") để tra rule được. Null = không theo bậc.
    pay_grade_key: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # --- Ca kíp ---
    # Ca làm việc mặc định (logical link → work_shifts.id; không FK cứng để tránh vòng
    # create_all, giống head_user_id). Null = chưa gán ca.
    default_shift_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)

    # Server-relative path of the profile photo (mirror users.avatar_url), e.g.
    # `/static/hr/<id>/photo.jpg`. Null → UI shows initials fallback.
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
    """A file attached to an employee (HĐ scan / CCCD / bằng cấp). The bytes live under
    <backend>/static and are served read-only at /static; only the path is stored here
    (mirror quote_attachments / users.avatar_url)."""

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
