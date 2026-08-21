"""Pydantic request/response models for the Hồ sơ nhân sự (nhan_su) API — lát #1.

Field-level constraints here are the first line of validation (422 shape); the service
enforces the domain rules (non-blank name, soft duplicate CCCD/BHXH, legal transitions).
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


# --- create / edit ----------------------------------------------------------


class AccountCreateIn(BaseModel):
    """Optional login account to create together with the employee (wizard step 5)."""

    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=6, max_length=128)
    name: str | None = Field(default=None, max_length=255)
    role_id: int | None = None


class InitialEmployeeSalaryIn(BaseModel):
    """Mức lương ban đầu khai cùng hồ sơ NV. Lương vị trí = lương cơ bản = mức đóng BH;
    bậc tay nghề khai ở bước Định danh (`job_grade_id` → danh mục `job_grades`)."""

    effective_from: date | None = None
    luong_vi_tri: float = Field(gt=0)
    luong_trach_nhiem: float = Field(default=0, ge=0)
    # "Lương trả 1 lần" (đợt 1) — mức điền sẵn khi lập phiếu thanh toán lương đợt 1.
    luong_dot_1: float = Field(default=0, ge=0)
    insurance_base: float | None = Field(default=None, ge=0)
    allowance: float = Field(default=0, ge=0)
    phu_cap_ca: float = Field(default=0, ge=0)
    phu_cap_tham_nien: float = Field(default=0, ge=0)
    chuyen_can: float = Field(default=0, ge=0)
    # BH đóng ở nơi khác → công ty chỉ đóng TNLĐ-BNN (không trừ BHXH/BHYT/BHTN của NV).
    insurance_elsewhere: bool = False
    # Đoàn viên công đoàn → mới bị trừ đoàn phí công đoàn.
    union_member: bool = False
    # % hoa hồng NV kinh doanh — PHÂN SỐ (0.05 = 5%). CHỈ KHAI, engine chưa cộng vào lương.
    commission_pct: float = Field(default=0, ge=0, le=1)
    note: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def require_positive_salary(self):
        if self.luong_vi_tri + self.luong_trach_nhiem <= 0:
            raise ValueError("Muc luong rieng cua nhan vien phai lon hon 0.")
        return self


class EmployeeBase(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    department_id: int | None = None
    position: str | None = Field(default=None, max_length=255)
    # Bậc tay nghề = ID danh mục `job_grades` (chủ 29/07/2026). Ô CHỮ cũ đã bỏ khỏi API:
    # để cả hai là dựng lại bẫy hai-ô-cùng-nghĩa. Chỉ khối SẢN XUẤT mới khai ô này.
    job_grade_id: int | None = None
    hire_date: date | None = None
    probation_end_date: date | None = None
    date_of_birth: date | None = None
    gender: str | None = Field(default=None, max_length=8)
    national_id: str | None = Field(default=None, max_length=20)
    national_id_date: date | None = None
    national_id_place: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=255)
    permanent_address: str | None = Field(default=None, max_length=500)
    current_address: str | None = Field(default=None, max_length=500)
    emergency_contact_name: str | None = Field(default=None, max_length=255)
    emergency_contact_phone: str | None = Field(default=None, max_length=30)
    social_insurance_no: str | None = Field(default=None, max_length=20)
    pit_tax_code: str | None = Field(default=None, max_length=20)
    dependents_count: int = Field(default=0, ge=0)
    # Cách tính thuế TNCN: luy_tien (mặc định) · khau_tru_10 (HĐ<3 tháng) · cam_ket_08.
    pit_mode: str = Field(default="luy_tien", pattern="^(luy_tien|khau_tru_10|cam_ket_08)$")
    bank_account: str | None = Field(default=None, max_length=30)
    bank_name: str | None = Field(default=None, max_length=100)
    default_shift_id: int | None = None  # ca làm việc mặc định (ca kíp)
    payroll_group: str | None = Field(default=None, max_length=40)   # nhóm lương (module luong)
    pay_grade_key: str | None = Field(default=None, max_length=20)   # bậc lương chuẩn hóa
    note: str | None = Field(default=None, max_length=1000)


class EmployeeCreate(EmployeeBase):
    # New employees default to Thử việc; the API accepts an override for imports.
    status: str = Field(default="probation", max_length=16)
    # Thâm niên đã có TRƯỚC khi vào làm (tháng) — chỉ khai lúc TẠO (không ở EmployeeBase để
    # bản PUT sửa hồ sơ không vô tình reset về 0). Wizard nhập theo NĂM rồi × 12.
    prior_seniority_months: int = Field(default=0, ge=0)
    # Optional: create + link a login account in the same call (wizard "Lưu").
    account: AccountCreateIn | None = None
    # Accepted only with `luong:update`; grade ownership is validated against
    # the selected department before the employee is created.
    initial_salary: InitialEmployeeSalaryIn | None = None


class EmployeeUpdate(EmployeeBase):
    """Edit hồ sơ. status / department reassignment / job_grade are NOT here — they are
    stage changes done via the transitions endpoint."""


# --- transitions / account --------------------------------------------------


class TransitionIn(BaseModel):
    kind: str = Field(description="confirm|leave_start|leave_end|suspend|resign|reinstate|transfer|promote")
    effective_date: date | None = None
    note: str | None = Field(default=None, max_length=500)
    new_department_id: int | None = None      # transfer
    # Bậc tay nghề mới. `new_job_grade_id` là đường CHÍNH (danh mục `job_grades`);
    # `new_job_grade` (chữ) giữ cho API cũ — service tra ngược danh mục theo tên.
    new_job_grade_id: int | None = None                             # promote | transfer
    new_job_grade: str | None = Field(default=None, max_length=50)   # promote (tương thích)
    new_position: str | None = Field(default=None, max_length=255)   # promote
    resign_reason: str | None = Field(default=None, max_length=255)  # resign


class AccountIn(BaseModel):
    """Gắn tài khoản đăng nhập cho một hồ sơ — hai kiểu, chọn MỘT:

    - TẠO MỚI (đường chính): `username` + `password` (+ `role_id`).
    - LIÊN KẾT tài khoản có sẵn: `user_id` — chỉ dùng để dọn tài khoản mồ côi cũ.
    """

    user_id: int | None = None
    username: str | None = None
    password: str | None = None
    role_id: int | None = None


class AssignShiftIn(BaseModel):
    effective_from: date = Field(default_factory=date.today)
    default_shift_id: int | None = None   # null = bỏ gán ca


class AssignShiftBulkIn(BaseModel):
    """Đặt CA NỀN cho nhiều NV một lượt (màn Phân ca tháng).

    Ca nền áp dụng từ `effective_from` trở về sau cho MỌI tháng — khác với tô ca
    trên lưới (chỉ đúng ngày đã tô)."""

    employee_ids: list[int] = Field(min_length=1, max_length=500)
    effective_from: date = Field(default_factory=date.today)
    default_shift_id: int | None = None   # null = bỏ gán ca


class AssignShiftBulkFail(BaseModel):
    employee_id: int
    reason: str


class AssignShiftBulkOut(BaseModel):
    updated: int = 0
    # Số NV vào làm SAU ngày được chọn → mốc tự lùi về đúng ngày vào làm của họ.
    adjusted: int = 0
    failed: list[AssignShiftBulkFail] = []


class ShiftAssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    shift_id: int | None = None
    effective_from: date
    effective_to: date | None = None
    is_current: bool = False
    created_at: datetime


class ShiftAssignmentsOut(BaseModel):
    employee_id: int
    items: list[ShiftAssignmentOut]


# --- responses --------------------------------------------------------------


class DuplicateRef(BaseModel):
    """Points at an existing employee already carrying the submitted CCCD / số BHXH."""

    id: int
    code: str
    full_name: str


class EmployeeRow(BaseModel):
    """A row in the Danh sách nhân viên list."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    full_name: str
    department_id: int | None
    department_name: str | None = None
    position: str | None = None
    job_grade_id: int | None = None
    job_grade_name: str | None = None   # tên bậc để hiện thẳng, khỏi tra thêm
    job_grade: str | None = None        # CỘT CŨ (chữ) — chỉ còn để hồ sơ chưa chuyển vẫn hiện
    status: str
    hire_date: date | None = None
    probation_end_date: date | None = None
    user_id: int | None = None
    account_username: str | None = None
    role_name: str | None = None          # Vai trò (RBAC) của tài khoản NV — dùng làm Chức danh ở list
    photo_url: str | None = None
    default_shift_id: int | None = None   # ca mặc định (cho panel gán ca ở Chấm công)
    created_at: datetime | None = None


class EmployeeOut(EmployeeRow):
    """Full detail (Thông tin tab). Inherits the row fields + the rest of the hồ sơ."""

    date_of_birth: date | None = None
    gender: str | None = None
    national_id: str | None = None
    national_id_date: date | None = None
    national_id_place: str | None = None
    phone: str | None = None
    email: str | None = None
    permanent_address: str | None = None
    current_address: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None
    social_insurance_no: str | None = None
    pit_tax_code: str | None = None
    dependents_count: int = 0
    pit_mode: str = "luy_tien"
    bank_account: str | None = None
    bank_name: str | None = None
    default_shift_id: int | None = None
    payroll_group: str | None = None
    pay_grade_key: str | None = None
    resign_date: date | None = None
    resign_reason: str | None = None
    note: str | None = None
    # Thâm niên đã có TRƯỚC khi vào làm (tháng). Trước đây chỉ NHẬN lúc tạo chứ không TRẢ ra —
    # nên màn nào tính thâm niên tổng cũng thiếu vế này với người chuyển từ nơi khác sang.
    prior_seniority_months: int = 0
    # Trưởng bộ phận (departments.head_user_id → tên tài khoản). CHỈ route self-service
    # `/me` điền — danh sách HCNS bỏ trống để không phải tra thêm mỗi dòng (N+1).
    department_head_name: str | None = None


class EmployeeKpis(BaseModel):
    """List header KPI strip — rolled up over the whole scoped set."""

    total: int
    active: int
    probation: int
    on_leave: int
    resigned: int
    probation_ending_soon: int  # probation_end_date trong ≤N ngày


class EmployeeListOut(BaseModel):
    items: list[EmployeeRow]
    total: int
    page: int
    size: int
    kpis: EmployeeKpis


class EmployeeCreateOut(BaseModel):
    """Create response: the new employee + optional soft duplicate warnings + created
    account username (if the wizard also created one)."""

    employee: EmployeeOut
    duplicate_national_id: DuplicateRef | None = None
    duplicate_social_insurance: DuplicateRef | None = None
    account_username: str | None = None


class EmployeeUpdateOut(BaseModel):
    employee: EmployeeOut
    duplicate_national_id: DuplicateRef | None = None
    duplicate_social_insurance: DuplicateRef | None = None


# --- self-service "Hồ sơ của tôi" (nhân viên thường) -----------------------


class MyProfileOut(BaseModel):
    has_employee: bool
    employee: EmployeeOut | None = None


class MyContactIn(BaseModel):
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=255)
    current_address: str | None = Field(default=None, max_length=500)
    emergency_contact_name: str | None = Field(default=None, max_length=255)
    emergency_contact_phone: str | None = Field(default=None, max_length=30)


# --- yêu cầu cập nhật hồ sơ (NV đề nghị → HCNS duyệt) ----------------------


class UpdateRequestIn(BaseModel):
    changes: dict[str, object]  # {field: giá trị mới} — service whitelist REQUESTABLE_FIELDS
    reason: str | None = Field(default=None, max_length=500)


class RequestDecisionIn(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class UpdateRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    employee_name: str | None = None       # router fills (HCNS list)
    changes: dict
    # Giá trị ĐANG có trên hồ sơ của đúng các field trong `changes` — router điền cho hàng đợi
    # HCNS. Thiếu ô này thì người duyệt chỉ thấy giá trị mới, không biết đang đổi TỪ GÌ sang gì
    # (màn "Hồ sơ của tôi" không cần: nó đã cầm sẵn hồ sơ của chính người xem).
    current: dict = {}
    reason: str | None = None
    status: str
    decision_note: str | None = None
    # Vết xử lý: lúc nào + ai. Thiếu hai ô này thì NV bị từ chối cũng không biết ai quyết,
    # lúc nào — màn "Hồ sơ của tôi" đọc đúng hai field này.
    decided_at: datetime | None = None
    decided_by_name: str | None = None       # router fills
    created_at: datetime


class UpdateRequestsOut(BaseModel):
    items: list[UpdateRequestOut]


class MyUpdateRequestsOut(UpdateRequestsOut):
    """Phong bì phân trang cho danh sách đề nghị của CHÍNH NV (màn "Hồ sơ của tôi").

    Giữ đúng bộ `items · total · page · size` như các danh mục đã cắt trang ở máy chủ
    (`schemas/vat_lieu_kho.ListOut`), thêm `dem`: số đề nghị theo từng trạng thái tính trên TOÀN
    BỘ hồ sơ. `dem` không phải trang trí — badge "N chờ duyệt" và số trên pill lọc phải đọc ở đây,
    đếm trên `items` của trang đang xem sẽ sai khi NV có nhiều hơn một trang.

    Hàng đợi HCNS (`UpdateRequestsOut`) chưa cắt trang, để nguyên."""

    total: int = 0
    page: int = 1
    size: int = 0
    dem: dict[str, int] = Field(default_factory=dict)


class EmployeeEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    effective_date: date | None = None
    field: str | None = None
    from_value: str | None = None
    to_value: str | None = None
    note: str | None = None
    actor_user_id: int | None = None
    actor_name: str | None = None
    created_at: datetime | None = None


class EmployeeEventsOut(BaseModel):
    items: list[EmployeeEventOut]


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    doc_kind: str
    file_name: str
    file_url: str
    file_type: str | None = None
    uploaded_by: int | None = None
    uploaded_at: datetime | None = None


class AttachmentsOut(BaseModel):
    items: list[AttachmentOut]


class EmployeeActivityRowOut(BaseModel):
    """One entry in an employee's Nhật ký (from the audit log, target employee:<id>)."""

    action: str
    target: str
    detail: str
    actor_name: str | None = None
    created_at: datetime


class EmployeeActivityOut(BaseModel):
    items: list[EmployeeActivityRowOut]


class DepartmentOption(BaseModel):
    id: int
    name: str
    # Khối SẢN XUẤT — cờ HIỆU LỰC: tự tick HOẶC có tổ tiên tick (server đã leo cây `parent_id`).
    # FE chỉ đọc một boolean để ẩn/hiện ô Bậc tay nghề, không phải tự đi leo cây.
    la_san_xuat: bool = False


class UserOption(BaseModel):
    id: int
    username: str
    name: str


class RoleOption(BaseModel):
    """Vai trò để gán cho tài khoản. Role thuộc ĐÚNG 1 phòng ban, nên FE lọc theo
    `department_id` của hồ sơ đang mở."""

    id: int
    name: str
    department_id: int


class EmployeeMetaOut(BaseModel):
    """Dropdown data for the forms: departments + roles + accounts not yet linked to any NV."""

    departments: list[DepartmentOption]
    unlinked_users: list[UserOption]
    roles: list[RoleOption] = []


class JobGradeIn(BaseModel):
    """Thêm một bậc tay nghề. `code` bỏ trống thì service tự sinh."""

    name: str = Field(min_length=1, max_length=60)
    code: str | None = Field(default=None, max_length=20)
    seq: int | None = None
    note: str | None = Field(default=None, max_length=255)
    # Hệ số chia sản lượng khoán theo bậc (module Thực hiện SX §8). Bỏ trống = chưa khai (engine coi 1.0).
    output_coefficient: float | None = Field(default=None, ge=0, le=999.999)


class JobGradeUpdateIn(BaseModel):
    """Sửa bậc. `exclude_unset` ở router ⇒ không gửi field nào thì field đó KHÔNG bị đụng."""

    name: str | None = Field(default=None, max_length=60)
    seq: int | None = None
    is_active: bool | None = None
    note: str | None = Field(default=None, max_length=255)
    output_coefficient: float | None = Field(default=None, ge=0, le=999.999)


class JobGradeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    seq: int
    is_active: bool
    note: str | None = None
    output_coefficient: float | None = None


class JobGradesOut(BaseModel):
    items: list[JobGradeOut]
