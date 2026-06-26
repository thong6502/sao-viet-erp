"""RBAC admin routes: module catalog, departments (read), and role management
(list/create + permission matrix). Thin HTTP shell over RoleService; every route is
guarded by require_permission on the relevant module."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from ..deps import get_department_service, get_role_service, require_permission
from ..schemas.rbac import (
    DepartmentCreate,
    DepartmentSummaryOut,
    DepartmentUpdate,
    ModuleOut,
    PermissionMatrixIn,
    PermissionRow,
    RoleCreate,
    RoleOut,
    RoleRename,
    UserBrief,
)
from ..services.department_service import (
    DepartmentInUse,
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

router = APIRouter(prefix="/api", tags=["rbac"])

Service = Annotated[RoleService, Depends(get_role_service)]
Depts = Annotated[DepartmentService, Depends(get_department_service)]


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


@router.get("/departments/{dept_id}/users", response_model=list[UserBrief])
def department_users(
    dept_id: int,
    depts: Depts,
    _: Annotated[object, Depends(require_permission("phong_ban", "read"))],
) -> list[UserBrief]:
    return depts.users_in_department(dept_id)


@router.post("/departments", response_model=DepartmentSummaryOut, status_code=status.HTTP_201_CREATED)
def create_department(
    payload: DepartmentCreate,
    depts: Depts,
    user: Annotated[object, Depends(require_permission("phong_ban", "create"))],
) -> dict:
    try:
        dept = depts.create(name=payload.name, actor_id=user.id)
    except DepartmentNameTaken as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    return {"id": dept.id, "name": dept.name}


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
            head_user_id=payload.head_user_id,
            actor_id=user.id,
        )
    except DepartmentNameTaken as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except InvalidHead as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except DeptNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return {"id": dept.id, "name": dept.name, "head_user_id": dept.head_user_id}


@router.delete("/departments/{dept_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_department(
    dept_id: int,
    depts: Depts,
    user: Annotated[object, Depends(require_permission("phong_ban", "delete"))],
) -> Response:
    try:
        depts.delete(dept_id=dept_id, actor_id=user.id)
    except DepartmentInUse as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except DeptNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
