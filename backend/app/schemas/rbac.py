"""RBAC admin schemas — shapes the role-management routes parse and return."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ModuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    label: str
    #: Những "việc" ĐÃ XÁC MINH là chết — bật cũng không mở thêm gì. Ma trận tắt sẵn + khoá + hover
    #: cảnh báo đúng mấy ô này, KHÔNG suy ngược từ "cái gì máy chủ không gác thì chết": rất nhiều ô
    #: được thi hành ở giao diện (ẩn/hiện nút) nên máy chủ không thấy mà vẫn có tác dụng thật.
    viec_chet: list[str] = []


class DepartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class DepartmentSummaryOut(BaseModel):
    """Department list row: identity + code + tree + head + role/user counts for the screen.

    `role_count`/`user_count` are this department's OWN counts; `total_role_count`/
    `total_user_count` roll the whole branch up (the department + every descendant), so a
    parent unit shows the aggregate of its sub-tree (spec-05 / PBI-4001).
    """

    id: int
    name: str
    code: str
    description: str | None = None
    parent_id: int | None = None
    head_user_id: int | None = None
    head_name: str | None = None
    # Ảnh đại diện của trưởng phòng. Null = chưa gán trưởng, hoặc trưởng chưa tải ảnh.
    head_avatar_url: str | None = None
    # Organizational tier (spec-06 / PBI-4009): the level id + its head-title label, so the
    # UI can show e.g. "Trưởng khối" instead of a generic "Người đứng đầu". Null = untagged.
    level_id: int | None = None
    head_title: str | None = None
    # Đánh dấu khối SẢN XUẤT (spec §13.1). FE tính "effective" theo cây (self hoặc tổ tiên tick).
    la_san_xuat: bool = False
    # Đánh dấu khối KINH DOANH — cùng luật kế thừa cây con. Nền cho danh sách "NV phụ trách" ở
    # màn Khách hàng (chip KHỐI KD trên danh sách phòng ban dùng "effective" y như khối SX).
    la_kinh_doanh: bool = False
    # Tổ KIỂM TRA CHẤT LƯỢNG (KCS) — cờ ĐÍCH DANH, không kế thừa cây con (module Thực hiện SX §3.1).
    is_kcs: bool = False
    la_giao_hang: bool = False
    # --- Khoán km giao hàng (mg 0231) — chỉ có nghĩa khi `la_giao_hang` bật ------------------
    #: Đơn giá mỗi km, là số TÀI XẾ ĐƯỢC HƯỞNG (không còn tầng % nào nữa).
    don_gia_km: float = Field(default=0, ge=0)
    #: Chia tiền một chuyến cho kíp xe. HAI ô BẮT BUỘC cộng đúng 100 — service chặn.
    pct_tai_xe: float = Field(default=60, ge=0, le=100)
    pct_phu_xe: float = Field(default=40, ge=0, le=100)
    role_count: int = 0
    user_count: int = 0
    employee_count: int = 0
    total_role_count: int = 0
    total_user_count: int = 0
    total_employee_count: int = 0
    # Bộ nguyên tắc lương của phòng (Pha 1).
    salary_mechanism: str = "cung"
    probation_ratio: float = 0.80
    has_piece_work: bool = False


class DepartmentMemberOut(BaseModel):
    """NHÂN SỰ của một phòng — một dòng = một HỒ SƠ (Đ2), kèm tài khoản nếu có.

    `user_id`/`username` null = người này chưa có tài khoản đăng nhập (công nhân xưởng).
    Họ vẫn thuộc phòng và vẫn chuyển phòng được, chỉ là không gán vai trò được.
    """

    employee_id: int
    code: str | None = None
    name: str
    position: str | None = None
    status: str
    user_id: int | None = None
    username: str | None = None
    role_name: str | None = None
    is_active: bool | None = None
    is_head: bool = False
    # Ảnh đại diện, lấy từ `users.avatar_url`. Null = người này chưa có tài khoản, hoặc có mà chưa
    # tải ảnh ⇒ FE hiện chữ viết tắt.
    avatar_url: str | None = None


_SalaryMechanism = Literal["cung", "bac_tho", "tham_nien", "tham_nien_gioi_tinh"]


class DepartmentCreate(BaseModel):
    # Code is system-generated (spec-05) — never accepted from the client.
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=500)
    parent_id: int | None = None
    # Optional org tier (spec-06 / PBI-4009).
    level_id: int | None = None
    # Bộ nguyên tắc lương của phòng (Pha 1).
    salary_mechanism: _SalaryMechanism = "cung"
    probation_ratio: float = Field(default=0.80, ge=0, le=1)
    has_piece_work: bool = False
    # Khối SẢN XUẤT (spec §13.1) — mặc định không phải sản xuất.
    la_san_xuat: bool = False
    # Khối KINH DOANH — mặc định không phải kinh doanh.
    la_kinh_doanh: bool = False
    # Tổ KCS — mặc định không phải KCS.
    is_kcs: bool = False
    la_giao_hang: bool = False
    # --- Khoán km giao hàng (mg 0231) — chỉ có nghĩa khi `la_giao_hang` bật ------------------
    #: Đơn giá mỗi km, là số TÀI XẾ ĐƯỢC HƯỞNG (không còn tầng % nào nữa).
    don_gia_km: float = Field(default=0, ge=0)
    #: Chia tiền một chuyến cho kíp xe. HAI ô BẮT BUỘC cộng đúng 100 — service chặn.
    pct_tai_xe: float = Field(default=60, ge=0, le=100)
    pct_phu_xe: float = Field(default=40, ge=0, le=100)


class DepartmentUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=500)
    head_user_id: int | None = None
    level_id: int | None = None
    # Re-parent in the org tree (spec-06 / PBI-4007); null = make it a root unit.
    parent_id: int | None = None
    # Bộ nguyên tắc lương của phòng (Pha 1).
    salary_mechanism: _SalaryMechanism = "cung"
    probation_ratio: float = Field(default=0.80, ge=0, le=1)
    has_piece_work: bool = False
    # Khối SẢN XUẤT (spec §13.1). FE gửi cả object nên luôn kèm cờ này.
    la_san_xuat: bool = False
    # Khối KINH DOANH. KHÔNG gửi = giữ nguyên (router lọc theo `model_fields_set`): màn Phòng ban
    # có nhiều luồng sửa chỉ đụng tên/trưởng phòng, ghi đè mặc định ở đó là âm thầm gỡ cờ khối.
    la_kinh_doanh: bool = False
    # Tổ KCS. KHÔNG gửi = giữ nguyên (router lọc theo `model_fields_set`) — cùng lý do như
    # `la_kinh_doanh`: nhiều luồng sửa chỉ đụng tên/trưởng phòng, ghi đè mặc định là âm thầm gỡ cờ.
    is_kcs: bool = False
    la_giao_hang: bool = False
    # --- Khoán km giao hàng (mg 0231) — chỉ có nghĩa khi `la_giao_hang` bật ------------------
    #: Đơn giá mỗi km, là số TÀI XẾ ĐƯỢC HƯỞNG (không còn tầng % nào nữa).
    don_gia_km: float = Field(default=0, ge=0)
    #: Chia tiền một chuyến cho kíp xe. HAI ô BẮT BUỘC cộng đúng 100 — service chặn.
    pct_tai_xe: float = Field(default=60, ge=0, le=100)
    pct_phu_xe: float = Field(default=40, ge=0, le=100)
    # `ca_lam_ids` ĐÃ BỎ (2026-08-10): ca khai một chỗ duy nhất ở Nhân sự → Ca kíp, không lặp lại
    # ở từng tổ. Cột còn trong DB nhưng không nhận/không trả.


class UnitLevelOut(BaseModel):
    """A tier in the org-level catalog (spec-06 / PBI-4009)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    rank: int
    head_title: str


class UnitLevelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    rank: int = Field(ge=1)
    head_title: str = Field(default="", max_length=100)


class UnitLevelUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    rank: int = Field(ge=1)
    head_title: str = Field(default="", max_length=100)


class DepartmentSubtreeRow(BaseModel):
    """A node in a department's delete-preview subtree (spec-05): identity + code."""

    id: int
    name: str
    code: str


class UserBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    username: str
    # Để danh sách chọn Trưởng phòng hiện ảnh thật. `from_attributes` tự lấy từ model `User`.
    avatar_url: str | None = None


class UserRow(BaseModel):
    """A row in the Users admin table: identity + department + role + status."""

    id: int
    code: str | None = None
    name: str
    username: str
    department_id: int | None = None
    department_name: str | None = None
    role_id: int | None = None
    role_name: str | None = None
    is_active: bool = True


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    username: str = Field(min_length=1, max_length=150)
    department_id: int
    # Tùy chọn: để trống → dùng mật khẩu mặc định (settings.default_user_password).
    password: str | None = Field(default=None, min_length=6, max_length=128)


class UserCreatedOut(UserRow):
    """Response khi tạo tài khoản — kèm mật khẩu ban đầu để admin bàn giao."""

    initial_password: str


class UserUpdate(BaseModel):
    """Admin edit of a user (spec-08 / PBI-2003): name + department. Username is not editable."""

    name: str = Field(min_length=1, max_length=255)
    department_id: int


class SessionOut(BaseModel):
    """A live login session (active refresh token) — read-only in the user detail (spec-08)."""

    id: int
    user_agent: str | None = None
    created_at: datetime
    expires_at: datetime


class ResetPasswordOut(BaseModel):
    """The one-time temporary password returned after an admin reset (spec-08 / PBI-2006)."""

    temporary_password: str


class RoleAssign(BaseModel):
    role_id: int | None = None


class ActiveUpdate(BaseModel):
    is_active: bool


class DepartmentTransferIn(BaseModel):
    """Bulk điều chuyển nhân sự sang phòng khác (spec-06 / PBI-4008).

    Chuyển theo HỒ SƠ (`employee_ids`), không theo tài khoản — để người chưa có tài khoản
    (công nhân xưởng) cũng chuyển được, và để mỗi lần chuyển đều ghi Quá trình công tác.
    """

    employee_ids: list[int] = Field(min_length=1)
    target_department_id: int


class TransferResult(BaseModel):
    transferred: int


class RoleBulkAssignIn(BaseModel):
    """Gán một vai trò cho nhiều người cùng lúc từ màn Phòng ban (bulk)."""

    user_ids: list[int] = Field(min_length=1)
    role_id: int


class RoleAssignResult(BaseModel):
    assigned: int


class AuditRow(BaseModel):
    """A row in the Activity Log: who did what, to what, when."""

    id: int
    actor_user_id: int | None = None
    actor_name: str | None = None
    action: str
    target: str
    detail: str
    created_at: datetime


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    department_id: int


class RoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    department_id: int


class RoleRename(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class RoleTemplateOut(BaseModel):
    """Một VAI MẪU: mô tả + bộ quyền điền sẵn cho ma trận (đợt 6, 11/08/2026).

    `permissions` là ma trận ĐẦY ĐỦ (mọi module, cờ nào không thuộc mẫu thì tắt) để giao diện chỉ
    việc thay thẳng state — không phải trộn nửa vời rồi lẫn với quyền cũ của vai."""

    key: str
    label: str
    mo_ta: str
    permissions: list["PermissionRow"]


class PermissionRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    module_key: str
    can_read: bool = False
    can_create: bool = False
    can_update: bool = False
    can_delete: bool = False
    scope: Literal["own", "department", "all"] = "own"
    # Quyền chi tiết (Cách B).
    can_reassign: bool = False
    can_export: bool = False
    can_view_debt: bool = False
    can_view_discount: bool = False
    can_approve: bool = False
    can_manage_status: bool = False
    can_reset_password: bool = False
    can_lock: bool = False
    can_revoke_sessions: bool = False
    can_assign_role: bool = False
    can_transfer: bool = False
    can_set_head: bool = False
    can_requote: bool = False
    can_manage_price: bool = False
    can_cancel: bool = False
    can_manage_permissions: bool = False
    can_clone: bool = False
    can_toggle_active: bool = False
    can_reparent: bool = False
    can_view_salary: bool = False
    can_edit_salary: bool = False
    can_adjust: bool = False
    can_view_log: bool = False  # cham_cong: xem tab Nhật ký chấm công (tách khỏi `can_read` 11/08/2026).
    # cham_cong (mg 0194) — MỘT Ô = MỘT TAB. Xem `models/role.py` để biết ô nào mở tab nào.
    can_view_timesheet: bool = False      # tab Bảng công tháng (lưới cả công ty + nút Chốt kỳ)
    can_approve_late_early: bool = False  # tab con Duyệt phiếu đi muộn / về sớm / nghỉ nửa buổi
    can_manage_locations: bool = False    # tab Điểm chấm công
    can_manage_shifts: bool = False       # tab Khai ca
    can_manage_calendar: bool = False     # tab Lịch & Ngày lễ
    can_view_payroll_table: bool = False  # luong — tab Bảng lương tháng
    can_manage_salary_profiles: bool = False  # luong — tab Lương nhân viên
    can_manage_piece_rates: bool = False      # luong — tab Lương khoán
    can_manage_leave_types: bool = False      # nghi_phep — danh mục loại nghỉ
    can_plan: bool = False                    # giao_hang — tab Lên kế hoạch
    can_view_drivers: bool = False            # giao_hang — tab Nhân viên giao hàng
    can_approve_exception: bool = False
    can_set_credit_terms: bool = False
    can_record_deposit: bool = False   # don_hang_ban — Kế toán ghi phiếu thu cọc
    can_assign_work: bool = False      # san_xuat — tổ trưởng gán thợ vào công đoạn
    can_record_output: bool = False    # san_xuat — tổ trưởng ghi sản lượng đạt/hỏng (Lát 2)
    can_handover: bool = False         # san_xuat — tổ trưởng bàn giao + xác nhận nhận (Lát 2)
    can_request: bool = False          # kho — tạo đề nghị nhập/xuất (tách khỏi lập phiếu)
    can_view_stock: bool = False       # kho — xem SỐ tồn (thiếu → chỉ đèn tín hiệu 5 màu)
    can_view_cost: bool = False        # kho — xem giá vốn & giá trị tồn (chỉ KT + BGĐ)
    can_set_threshold: bool = False    # kho — khai ngưỡng tồn / cận tồn / tối đa
    can_post: bool = False             # kho — GHI SỔ phiếu (chốt tồn); tách khỏi lập nháp (SoD)
    can_close_book: bool = False       # kho — KHÓA KỲ (chốt sổ) + Báo cáo kho kế toán + export


class PermissionMatrixIn(BaseModel):
    permissions: list[PermissionRow]
