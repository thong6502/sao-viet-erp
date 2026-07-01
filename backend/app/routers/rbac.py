"""RBAC admin routes: module catalog, departments (read), and role management
(list/create + permission matrix). Thin HTTP shell over RoleService; every route is
guarded by require_permission on the relevant module."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from ..deps import (
    get_activity_service,
    get_department_service,
    get_role_service,
    get_user_admin_service,
    require_permission,
)
from ..schemas.rbac import (
    ActiveUpdate,
    AuditRow,
    DepartmentCreate,
    DepartmentMemberOut,
    DepartmentSubtreeRow,
    DepartmentSummaryOut,
    DepartmentUpdate,
    ModuleOut,
    PermissionMatrixIn,
    PermissionRow,
    RoleAssign,
    RoleCreate,
    RoleOut,
    RoleRename,
    UserBrief,
    UserCreate,
    UserRow,
)
from ..services.department_service import (
    DepartmentBranchHasUsers,
    DepartmentNameTaken,
    InvalidHead,
)
from ..services.department_service import DepartmentNotFound as DeptNotFound
from ..services.department_service import DepartmentService
from ..services.role_service import (
    DepartmentNotFound,
    RoleInUse,
    RoleNameTaken,
    RoleNotFound,
    RoleService,
)
from ..services.user_admin_service import (
    CannotLockSelf,
    InvalidRoleForDepartment,
    UsernameTaken,
    UserAdminService,
    UserNotFound,
)
from ..services.user_admin_service import DepartmentNotFound as UADeptNotFound
from ..services.activity_service import ActivityService

router = APIRouter(prefix="/api", tags=["rbac"])

Service = Annotated[RoleService, Depends(get_role_service)]
Depts = Annotated[DepartmentService, Depends(get_department_service)]
Users = Annotated[UserAdminService, Depends(get_user_admin_service)]
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
            actor_id=user.id,
        )
    except DepartmentNameTaken as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except DeptNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return depts.summary_of(dept)


@router.put("/departments/{dept_id}", response_model=DepartmentSummaryOut)
def update_department(
    dept_id: int,
    payload: DepartmentUpdate,
    depts: Depts,
    user: Annotated[object, Depends(require_permission("phong_ban", "update"))],
) -> dict:
    try:
        dept = depts.update(
            dept_id=dept_id,
            name=payload.name,
            description=payload.description,
            head_user_id=payload.head_user_id,
            actor_id=user.id,
        )
    except DepartmentNameTaken as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except InvalidHead as e:
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


@router.get("/users", response_model=list[UserRow])
def list_users(
    admin: Users,
    _: Annotated[object, Depends(require_permission("nguoi_dung", "read"))],
) -> list[UserRow]:
    return admin.list_users()


@router.post("/users", response_model=UserRow, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    admin: Users,
    user: Annotated[object, Depends(require_permission("nguoi_dung", "create"))],
) -> dict:
    try:
        created = admin.create_user(
            name=payload.name,
            username=payload.username,
            department_id=payload.department_id,
            actor_id=user.id,
        )
    except UsernameTaken as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except UADeptNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return {
        "id": created.id,
        "name": created.name,
        "username": created.username,
        "department_id": created.department_id,
        "role_id": created.role_id,
        "is_active": created.is_active,
    }


@router.put("/users/{user_id}/role", response_model=UserRow)
def assign_user_role(
    user_id: int,
    payload: RoleAssign,
    admin: Users,
    user: Annotated[object, Depends(require_permission("nguoi_dung", "update"))],
) -> dict:
    try:
        updated = admin.assign_role(user_id=user_id, role_id=payload.role_id, actor_id=user.id)
    except InvalidRoleForDepartment as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except UserNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return {
        "id": updated.id,
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
    user: Annotated[object, Depends(require_permission("nguoi_dung", "update"))],
) -> dict:
    try:
        updated = admin.set_active(user_id=user_id, is_active=payload.is_active, actor_id=user.id)
    except CannotLockSelf as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except UserNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return {
        "id": updated.id,
        "name": updated.name,
        "username": updated.username,
        "department_id": updated.department_id,
        "role_id": updated.role_id,
        "is_active": updated.is_active,
    }


@router.get("/roles", response_model=list[RoleOut])
def list_roles(
    department_id: int,
    svc: Service,
    _: Annotated[object, Depends(require_permission("vai_tro", "read"))],
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
    user: Annotated[object, Depends(require_permission("vai_tro", "update"))],
) -> list[PermissionRow]:
    try:
        return svc.save_matrix(
            role_id=role_id,
            rows=[r.model_dump() for r in payload.permissions],
            actor_id=user.id,
        )
    except RoleNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
