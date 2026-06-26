"""RBAC admin routes: module catalog, departments (read), and role management
(list/create + permission matrix). Thin HTTP shell over RoleService; every route is
guarded by require_permission on the relevant module."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from ..deps import get_role_service, require_permission
from ..schemas.rbac import (
    DepartmentOut,
    ModuleOut,
    PermissionMatrixIn,
    PermissionRow,
    RoleCreate,
    RoleOut,
)
from ..services.role_service import (
    DepartmentNotFound,
    RoleNameTaken,
    RoleNotFound,
    RoleService,
)

router = APIRouter(prefix="/api", tags=["rbac"])

Service = Annotated[RoleService, Depends(get_role_service)]


@router.get("/rbac/modules", response_model=list[ModuleOut])
def list_modules(
    svc: Service,
    _: Annotated[object, Depends(require_permission("vai_tro", "read"))],
) -> list[ModuleOut]:
    return svc.list_modules()


@router.get("/departments", response_model=list[DepartmentOut])
def list_departments(
    svc: Service,
    _: Annotated[object, Depends(require_permission("phong_ban", "read"))],
) -> list[DepartmentOut]:
    return svc.list_departments()


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
