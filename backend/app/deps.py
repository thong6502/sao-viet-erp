"""FastAPI dependency providers (the composition root for each request).

Wires DB session -> repository -> service, and resolves the bearer token into the
current user. Auth enters here as an explicit dependency boundary, not by reaching
across layers (docs/ARCHITECTURE.md).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .db import get_db
from .models.user import User
from .repositories.audit_repo import AuditLogRepository
from .repositories.rbac_repo import DepartmentRepository, ModuleRepository, RoleRepository
from .repositories.user_repo import UserRepository
from .security import decode_access_token
from .services.auth_service import AuthError, AuthService
from .services.department_service import DepartmentService
from .services.rbac_service import AuthorizationService
from .services.role_service import RoleService
from .services.user_admin_service import UserAdminService

# auto_error=False so we can return our own 401 shape for missing/invalid tokens.
_bearer = HTTPBearer(auto_error=False)


def get_user_repository(db: Annotated[Session, Depends(get_db)]) -> UserRepository:
    return UserRepository(db)


def get_auth_service(
    users: Annotated[UserRepository, Depends(get_user_repository)],
) -> AuthService:
    return AuthService(users)


def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if creds is None or not creds.credentials:
        raise unauthorized

    claims = decode_access_token(creds.credentials)
    if claims is None:
        raise unauthorized
    try:
        user = auth.user_from_token_subject(claims.get("sub"))
    except AuthError:
        raise unauthorized from None
    # A locked account is rejected even with a still-valid token (RBAC, sprint-02).
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản đã bị khóa",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


# --- Authorization (RBAC enforcement) --------------------------------------


def get_role_repository(db: Annotated[Session, Depends(get_db)]) -> RoleRepository:
    return RoleRepository(db)


def get_authorization_service(
    roles: Annotated[RoleRepository, Depends(get_role_repository)],
) -> AuthorizationService:
    return AuthorizationService(roles)


def get_module_repository(db: Annotated[Session, Depends(get_db)]) -> ModuleRepository:
    return ModuleRepository(db)


def get_department_repository(db: Annotated[Session, Depends(get_db)]) -> DepartmentRepository:
    return DepartmentRepository(db)


def get_audit_repository(db: Annotated[Session, Depends(get_db)]) -> AuditLogRepository:
    return AuditLogRepository(db)


def get_role_service(
    roles: Annotated[RoleRepository, Depends(get_role_repository)],
    modules: Annotated[ModuleRepository, Depends(get_module_repository)],
    departments: Annotated[DepartmentRepository, Depends(get_department_repository)],
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
) -> RoleService:
    return RoleService(roles, modules, departments, audit, users)


def get_department_service(
    departments: Annotated[DepartmentRepository, Depends(get_department_repository)],
    roles: Annotated[RoleRepository, Depends(get_role_repository)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
) -> DepartmentService:
    return DepartmentService(departments, roles, users, audit)


def get_user_admin_service(
    users: Annotated[UserRepository, Depends(get_user_repository)],
    departments: Annotated[DepartmentRepository, Depends(get_department_repository)],
    roles: Annotated[RoleRepository, Depends(get_role_repository)],
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
) -> UserAdminService:
    return UserAdminService(users, departments, roles, audit)


def require_permission(module_key: str, action: str):
    """Build a dependency that allows the request only if the current user's role
    grants `action` on `module_key`. 401 if unauthenticated/locked is handled by
    `get_current_user`; this adds the 403 for a missing permission."""

    def dependency(
        user: CurrentUser,
        authz: Annotated[AuthorizationService, Depends(get_authorization_service)],
    ) -> User:
        if not authz.can(user, module_key, action):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bạn không có quyền thực hiện thao tác này",
            )
        return user

    return dependency
