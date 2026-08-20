"""RBAC admin routes: module catalog, departments (read), and role management
(list/create + permission matrix). Thin HTTP shell over RoleService; every route is
guarded by require_permission on the relevant module."""
from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from ..deps import (
    get_activity_service,
    get_authorization_service,
    get_department_service,
    get_employee_service,
    get_payroll_service,
    get_role_service,
    get_unit_level_service,
    get_user_admin_service,
    require_any_permission,
    require_permission,
)
from ..schemas.rbac import (
    RoleTemplateOut,
    ActiveUpdate,
    AuditRow,
    DepartmentCreate,
    DepartmentMemberOut,
    DepartmentSubtreeRow,
    DepartmentSummaryOut,
    DepartmentTransferIn,
    DepartmentUpdate,
    ModuleOut,
    PermissionMatrixIn,
    PermissionRow,
    RoleAssign,
    RoleAssignResult,
    RoleBulkAssignIn,
    RoleCreate,
    ResetPasswordOut,
    RoleOut,
    RoleRename,
    SessionOut,
    TransferResult,
    UnitLevelCreate,
    UnitLevelOut,
    UnitLevelUpdate,
    UserBrief,
    UserRow,
    UserUpdate,
)
from ..services.department_service import (
    DepartmentBranchHasUsers,
    DepartmentCycle,
    DepartmentNameTaken,
    InvalidHead,
    InvalidLevelOrder,
    ReparentForbidden,
    SetHeadForbidden,
)
from ..services.department_service import DepartmentNotFound as DeptNotFound
from ..services.department_service import DepartmentService
from ..services.employee_service import (
    EmployeeNotFound,
    EmployeeService,
    EmployeeValidationError,
)
from ..services.unit_level_service import (
    UnitLevelInUse,
    UnitLevelNameTaken,
    UnitLevelNotFound,
    UnitLevelRankTaken,
    UnitLevelService,
)
from ..services.role_service import (
    DepartmentNotFound,
    RoleInUse,
    RoleNameTaken,
    RoleNotFound,
    RoleService,
)
from ..services.user_admin_service import (
    CannotLockSelf,
    CannotRevokeSelf,
    InvalidRoleForDepartment,
    TransferForbidden,
    UserAdminService,
    UserNotFound,
)
from ..services.user_admin_service import DepartmentNotFound as UADeptNotFound
from ..services.activity_service import ActivityService
from ..services.rbac_service import AuthorizationService
from ..services.payroll_service import PayrollError, PayrollService

router = APIRouter(prefix="/api", tags=["rbac"])

Service = Annotated[RoleService, Depends(get_role_service)]
Depts = Annotated[DepartmentService, Depends(get_department_service)]
Levels = Annotated[UnitLevelService, Depends(get_unit_level_service)]
Users = Annotated[UserAdminService, Depends(get_user_admin_service)]
# Điều chuyển nhân sự đi qua HỒ SƠ (ghi Quá trình công tác) → màn Phòng ban cần EmployeeService.
EmployeeSvc = Annotated[EmployeeService, Depends(get_employee_service)]
PayrollSvc = Annotated[PayrollService, Depends(get_payroll_service)]
Authz = Annotated[AuthorizationService, Depends(get_authorization_service)]
Activity = Annotated[ActivityService, Depends(get_activity_service)]


@router.get("/audit", response_model=list[AuditRow])
def list_audit(
    activity: Activity,
    _: Annotated[object, Depends(require_permission("activity_log", "read"))],
) -> list[AuditRow]:
    return activity.list_recent()


@router.get("/rbac/modules", response_model=list[ModuleOut])
def list_modules(
    svc: Service,
    _: Annotated[object, Depends(require_permission("vai_tro", "read"))],
) -> list[ModuleOut]:
    return svc.list_modules()


@router.get("/departments", response_model=list[DepartmentSummaryOut])
def list_departments(
    depts: Depts,
    _: Annotated[object, Depends(require_permission("phong_ban", "read"))],
) -> list[DepartmentSummaryOut]:
    return depts.list_summaries()


@router.get("/departments/{dept_id}/users", response_model=list[DepartmentMemberOut])
def department_users(
    dept_id: int,
    depts: Depts,
    _: Annotated[object, Depends(require_permission("phong_ban", "read"))],
) -> list[dict]:
    # PBI-4001: staff of a department with role + status + head flag for the detail panel.
    return depts.members_of_department(dept_id)


@router.post("/departments", response_model=DepartmentSummaryOut, status_code=status.HTTP_201_CREATED)
def create_department(
    payload: DepartmentCreate,
    depts: Depts,
    user: Annotated[object, Depends(require_permission("phong_ban", "create"))],
) -> dict:
    try:
        dept = depts.create(
            name=payload.name,
            description=payload.description,
            parent_id=payload.parent_id,
            level_id=payload.level_id,
            salary_mechanism=payload.salary_mechanism,
            probation_ratio=payload.probation_ratio,
            has_piece_work=payload.has_piece_work,
            la_san_xuat=payload.la_san_xuat,
            la_kinh_doanh=payload.la_kinh_doanh,
            is_kcs=payload.is_kcs,
            actor_id=user.id,
        )
    except DepartmentNameTaken as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except (DepartmentCycle, InvalidLevelOrder) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except DeptNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return depts.summary_of(dept)


@router.put("/departments/{dept_id}", response_model=DepartmentSummaryOut)
def update_department(
    dept_id: int,
    payload: DepartmentUpdate,
    depts: Depts,
    authz: Authz,
    user: Annotated[object, Depends(require_permission("phong_ban", "update"))],
) -> dict:
    try:
        # Only re-parent when the client explicitly sends parent_id (absent → keep current).
        parent_kw = (
            {"parent_id": payload.parent_id}
            if "parent_id" in payload.model_fields_set
            else {}
        )
        # Bộ nguyên tắc lương: chỉ đụng field client THỰC SỰ gửi — tránh sửa tên phòng
        # lại vô tình reset cơ chế lương về mặc định.
        salary_kw = {
            k: getattr(payload, k)
            for k in ("salary_mechanism", "probation_ratio", "has_piece_work")
            if k in payload.model_fields_set
        }
        # Cờ khối Kinh doanh: KHÔNG gửi = giữ nguyên — màn Phòng ban có nhiều luồng sửa chỉ đụng
        # tên/trưởng phòng, ghi đè mặc định ở đó là âm thầm gỡ khối Kinh doanh của phòng.
        kd_kw = (
            {"la_kinh_doanh": payload.la_kinh_doanh}
            if "la_kinh_doanh" in payload.model_fields_set
            else {}
        )
        # Cờ KCS: cùng luật "KHÔNG gửi = giữ nguyên".
        kcs_kw = (
            {"is_kcs": payload.is_kcs}
            if "is_kcs" in payload.model_fields_set
            else {}
        )
        dept = depts.update(
            dept_id=dept_id,
            name=payload.name,
            description=payload.description,
            head_user_id=payload.head_user_id,
            level_id=payload.level_id,
            la_san_xuat=payload.la_san_xuat,
            actor_id=user.id,
            allow_set_head=authz.can(user, "phong_ban", "set_head"),
            allow_reparent=authz.can(user, "phong_ban", "reparent"),
            **parent_kw,
            **salary_kw,
            **kd_kw,
            **kcs_kw,
        )
    except (SetHeadForbidden, ReparentForbidden) as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from None
    except DepartmentNameTaken as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except (InvalidHead, DepartmentCycle, InvalidLevelOrder) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except DeptNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return depts.summary_of(dept)


@router.delete("/departments/{dept_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_department(
    dept_id: int,
    depts: Depts,
    user: Annotated[object, Depends(require_permission("phong_ban", "delete"))],
) -> Response:
    try:
        depts.delete(dept_id=dept_id, actor_id=user.id)
    except DepartmentBranchHasUsers as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except DeptNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/departments/{dept_id}/subtree", response_model=list[DepartmentSubtreeRow])
def department_subtree(
    dept_id: int,
    depts: Depts,
    _: Annotated[object, Depends(require_permission("phong_ban", "read"))],
) -> list[dict]:
    # The units a delete of this department would remove (PBI-4005 confirm preview).
    return [{"id": d.id, "name": d.name, "code": d.code} for d in depts.branch(dept_id)]


@router.get("/departments/{dept_id}/head-candidates", response_model=list[UserBrief])
def department_head_candidates(
    dept_id: int,
    depts: Depts,
    _: Annotated[object, Depends(require_permission("phong_ban", "read"))],
) -> list[UserBrief]:
    # PBI-4004: valid heads are people in this unit OR any of its sub-units (subtree).
    return depts.head_candidates(dept_id)


@router.post("/departments/transfer", response_model=TransferResult)
def transfer_department_staff(
    payload: DepartmentTransferIn,
    employees: EmployeeSvc,
    payroll: PayrollSvc,
    user: Annotated[object, Depends(require_permission("nguoi_dung", "transfer"))],
) -> TransferResult:
    """PBI-4008 — bulk điều chuyển NHÂN SỰ sang phòng khác (vai trò cũ bị gỡ, ghi Quá trình
    công tác + nhật ký cho từng người). Chuyển theo HỒ SƠ nên người chưa có tài khoản cũng đi
    được. Đây là thao tác quản trị phòng ban nên đọc hồ sơ ở phạm vi `all` — cổng quyền là
    `nguoi_dung:transfer` (giữ nguyên như trước)."""
    try:
        n = employees.transfer_many(
            employee_ids=payload.employee_ids,
            target_department_id=payload.target_department_id,
            scope="all",
            actor=user,
        )
    except EmployeeNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except EmployeeValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except PayrollError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    return TransferResult(transferred=n)


@router.post("/departments/assign-role", response_model=RoleAssignResult)
def bulk_assign_role(
    payload: RoleBulkAssignIn,
    admin: Users,
    user: Annotated[object, Depends(require_permission("nguoi_dung", "assign_role"))],
) -> RoleAssignResult:
    # Gán một vai trò cho nhiều người cùng lúc từ màn Phòng ban (audit từng người).
    try:
        n = admin.bulk_assign_role(
            user_ids=payload.user_ids,
            role_id=payload.role_id,
            actor_id=user.id,
        )
    except InvalidRoleForDepartment as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except UserNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return RoleAssignResult(assigned=n)


@router.get("/unit-levels", response_model=list[UnitLevelOut])
def list_unit_levels(
    levels: Levels,
    _: Annotated[object, Depends(require_permission("phong_ban", "read"))],
) -> list[UnitLevelOut]:
    return levels.list_levels()


@router.post("/unit-levels", response_model=UnitLevelOut, status_code=status.HTTP_201_CREATED)
def create_unit_level(
    payload: UnitLevelCreate,
    levels: Levels,
    user: Annotated[object, Depends(require_permission("phong_ban", "create"))],
) -> UnitLevelOut:
    try:
        return levels.create(
            name=payload.name,
            rank=payload.rank,
            head_title=payload.head_title,
            actor_id=user.id,
        )
    except (UnitLevelNameTaken, UnitLevelRankTaken) as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None


@router.put("/unit-levels/{level_id}", response_model=UnitLevelOut)
def update_unit_level(
    level_id: int,
    payload: UnitLevelUpdate,
    levels: Levels,
    user: Annotated[object, Depends(require_permission("phong_ban", "update"))],
) -> UnitLevelOut:
    try:
        return levels.update(
            level_id=level_id,
            name=payload.name,
            rank=payload.rank,
            head_title=payload.head_title,
            actor_id=user.id,
        )
    except (UnitLevelNameTaken, UnitLevelRankTaken) as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except UnitLevelNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@router.delete(
    "/unit-levels/{level_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_unit_level(
    level_id: int,
    levels: Levels,
    user: Annotated[object, Depends(require_permission("phong_ban", "delete"))],
) -> Response:
    try:
        levels.delete(level_id=level_id, actor_id=user.id)
    except UnitLevelInUse as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except UnitLevelNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/users", response_model=list[UserRow])
def list_users(
    admin: Users,
    _: Annotated[object, Depends(require_permission("nguoi_dung", "read"))],
) -> list[UserRow]:
    return admin.list_users()


# GỠ `POST /users`: mọi tài khoản đăng nhập PHẢI thuộc một hồ sơ nhân viên, nên đường tạo
# tài khoản duy nhất là qua Hồ sơ nhân sự (`POST /api/employees` kèm `account`, hoặc
# `POST /api/employees/{id}/account`). Không còn cửa nào đẻ ra tài khoản mồ côi.
# Ngoại lệ duy nhất là tài khoản hệ thống `admin` do seed tạo.


@router.put("/users/{user_id}/role", response_model=UserRow)
def assign_user_role(
    user_id: int,
    payload: RoleAssign,
    admin: Users,
    user: Annotated[object, Depends(require_permission("nguoi_dung", "assign_role"))],
) -> dict:
    try:
        updated = admin.assign_role(user_id=user_id, role_id=payload.role_id, actor_id=user.id)
    except InvalidRoleForDepartment as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except UserNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return {
        "id": updated.id,
        "code": updated.code,
        "name": updated.name,
        "username": updated.username,
        "department_id": updated.department_id,
        "role_id": updated.role_id,
        "is_active": updated.is_active,
    }


@router.put("/users/{user_id}/active", response_model=UserRow)
def set_user_active(
    user_id: int,
    payload: ActiveUpdate,
    admin: Users,
    user: Annotated[object, Depends(require_permission("nguoi_dung", "lock"))],
) -> dict:
    try:
        updated = admin.set_active(user_id=user_id, is_active=payload.is_active, actor_id=user.id)
    except CannotLockSelf as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except UserNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return {
        "id": updated.id,
        "code": updated.code,
        "name": updated.name,
        "username": updated.username,
        "department_id": updated.department_id,
        "role_id": updated.role_id,
        "is_active": updated.is_active,
    }


@router.put("/users/{user_id}", response_model=UserRow)
def update_user(
    user_id: int,
    payload: UserUpdate,
    admin: Users,
    authz: Authz,
    user: Annotated[object, Depends(require_permission("nguoi_dung", "update"))],
) -> dict:
    # PBI-2003: edit name + department. Changing department drops the old role (service).
    # Đổi phòng ban là quyền chi tiết `transfer` (đổi tên trong cùng phòng chỉ cần `update`).
    try:
        updated, _dropped = admin.update_user(
            user_id=user_id,
            name=payload.name,
            department_id=payload.department_id,
            actor_id=user.id,
            allow_transfer=authz.can(user, "nguoi_dung", "transfer"),
        )
    except TransferForbidden as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from None
    except UADeptNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except UserNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return {
        "id": updated.id,
        "code": updated.code,
        "name": updated.name,
        "username": updated.username,
        "department_id": updated.department_id,
        "role_id": updated.role_id,
        "is_active": updated.is_active,
    }


@router.post("/users/{user_id}/reset-password", response_model=ResetPasswordOut)
def reset_user_password(
    user_id: int,
    admin: Users,
    user: Annotated[object, Depends(require_permission("nguoi_dung", "reset_password"))],
) -> ResetPasswordOut:
    # PBI-2006: set a temp password (shown once), revoke every session, audit.
    try:
        temp = admin.reset_password(user_id=user_id, actor_id=user.id)
    except UserNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return ResetPasswordOut(temporary_password=temp)


@router.post(
    "/users/{user_id}/revoke-sessions",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def revoke_user_sessions(
    user_id: int,
    admin: Users,
    user: Annotated[object, Depends(require_permission("nguoi_dung", "revoke_sessions"))],
) -> Response:
    # PBI-2008: log the user out everywhere.
    try:
        admin.revoke_sessions(user_id=user_id, actor_id=user.id)
    except CannotRevokeSelf as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except UserNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/users/{user_id}/sessions", response_model=list[SessionOut])
def list_user_sessions(
    user_id: int,
    admin: Users,
    _: Annotated[object, Depends(require_permission("nguoi_dung", "read"))],
) -> list[SessionOut]:
    return admin.list_sessions(user_id)


@router.get("/users/{user_id}/activity", response_model=list[AuditRow])
def list_user_activity(
    user_id: int,
    admin: Users,
    _: Annotated[object, Depends(require_permission("nguoi_dung", "read"))],
) -> list[AuditRow]:
    return [
        AuditRow(
            id=a.id,
            actor_user_id=a.actor_user_id,
            action=a.action,
            target=a.target,
            detail=a.detail,
            created_at=a.created_at,
        )
        for a in admin.list_activity(user_id)
    ]


@router.get("/roles", response_model=list[RoleOut])
def list_roles(
    department_id: int,
    svc: Service,
    # Tên vai trò trong một phòng là một phần của việc XEM phòng ban (màn chi tiết phòng
    # hiển thị chip vai trò; danh sách nhân sự vốn đã trả role_name với phong_ban:read).
    # Ma trận quyền chi tiết vẫn khóa sau vai_tro:read (GET /roles/{id}/permissions).
    _: Annotated[
        object,
        Depends(require_any_permission(("vai_tro", "read"), ("phong_ban", "read"))),
    ],
) -> list[RoleOut]:
    return svc.list_roles(department_id)


@router.post("/roles", response_model=RoleOut, status_code=status.HTTP_201_CREATED)
def create_role(
    payload: RoleCreate,
    svc: Service,
    user: Annotated[object, Depends(require_permission("vai_tro", "create"))],
) -> RoleOut:
    try:
        return svc.create_role(
            name=payload.name, department_id=payload.department_id, actor_id=user.id
        )
    except RoleNameTaken as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except DepartmentNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@router.put("/roles/{role_id}", response_model=RoleOut)
def rename_role(
    role_id: int,
    payload: RoleRename,
    svc: Service,
    user: Annotated[object, Depends(require_permission("vai_tro", "update"))],
) -> RoleOut:
    try:
        return svc.rename_role(role_id=role_id, name=payload.name, actor_id=user.id)
    except RoleNameTaken as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except RoleNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@router.delete(
    "/roles/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_role(
    role_id: int,
    svc: Service,
    user: Annotated[object, Depends(require_permission("vai_tro", "delete"))],
) -> Response:
    try:
        svc.delete_role(role_id=role_id, actor_id=user.id)
    except RoleInUse as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except RoleNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/roles/templates", response_model=list[RoleTemplateOut])
def list_role_templates(
    svc: Service,
    _: Annotated[object, Depends(require_permission("vai_tro", "read"))],
) -> list[RoleTemplateOut]:
    """Bảng VAI MẪU — bộ quyền dựng sẵn cho các vai điển hình.

    ⚠️ ĐƯỜNG DẪN PHẢI ĐỨNG TRƯỚC `/roles/{role_id}/permissions`: FastAPI khớp route theo thứ tự
    khai báo, để sau thì "templates" bị nuốt làm `role_id` và trả 422.

    CHỈ ĐỌC — không có đường nào ghi thẳng vào DB từ đây. Giao diện điền mẫu vào ma trận đang mở,
    quản trị xem lại rồi mới bấm Lưu (đi qua `PUT /roles/{id}/permissions`, vẫn gác
    `vai_tro:manage_permissions` như cũ). Nhờ vậy chọn nhầm mẫu cũng không hỏng gì.
    """
    return [RoleTemplateOut(**m) for m in svc.role_templates()]


@router.get("/roles/{role_id}/permissions", response_model=list[PermissionRow])
def get_role_permissions(
    role_id: int,
    svc: Service,
    _: Annotated[object, Depends(require_permission("vai_tro", "read"))],
) -> list[PermissionRow]:
    try:
        return svc.get_matrix(role_id)
    except RoleNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@router.put("/roles/{role_id}/permissions", response_model=list[PermissionRow])
def save_role_permissions(
    role_id: int,
    payload: PermissionMatrixIn,
    svc: Service,
    user: Annotated[object, Depends(require_permission("vai_tro", "manage_permissions"))],
) -> list[PermissionRow]:
    try:
        return svc.save_matrix(
            role_id=role_id,
            rows=[r.model_dump() for r in payload.permissions],
            actor_id=user.id,
        )
    except RoleNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
