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
from .repositories.costing_repo import CostingRepository
from .repositories.customer_repo import CustomerRepository
from .repositories.order_repo import OrderRepository
from .repositories.product_repo import ProductRepository
from .repositories.quotation_repo import QuotationRepository
from .repositories.rbac_repo import (
    DepartmentRepository,
    ModuleRepository,
    RoleRepository,
    UnitLevelRepository,
)
from .repositories.refresh_token_repo import RefreshTokenRepository
from .repositories.user_repo import UserRepository
from .security import decode_access_token
from .services.auth_service import AuthError, AuthService
from .services.activity_service import ActivityService
from .services.costing_service import CostingService
from .services.customer_analytics import CustomerAnalyticsService
from .services.customer_service import CustomerService
from .services.department_service import DepartmentService
from .services.product_service import ProductService
from .services.order_service import OrderService
from .services.quotation_service import QuotationService
from .services.profile_service import ProfileService
from .services.rbac_service import AuthorizationService
from .services.refresh_service import RefreshTokenService
from .services.role_service import RoleService
from .services.unit_level_service import UnitLevelService
from .services.user_admin_service import UserAdminService

# auto_error=False so we can return our own 401 shape for missing/invalid tokens.
_bearer = HTTPBearer(auto_error=False)


def get_user_repository(db: Annotated[Session, Depends(get_db)]) -> UserRepository:
    return UserRepository(db)


def get_auth_service(
    users: Annotated[UserRepository, Depends(get_user_repository)],
) -> AuthService:
    return AuthService(users)


def get_refresh_token_repository(
    db: Annotated[Session, Depends(get_db)],
) -> RefreshTokenRepository:
    return RefreshTokenRepository(db)


def get_refresh_service(
    tokens: Annotated[RefreshTokenRepository, Depends(get_refresh_token_repository)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
) -> RefreshTokenService:
    return RefreshTokenService(tokens, users)


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
    # Hard-revoke: a token whose `tv` no longer matches the user's token_version is dead
    # (logout-all / forced invalidation), even if not yet expired (spec-03).
    if claims.get("tv") != user.token_version:
        raise unauthorized
    # A locked account is rejected even with a still-valid token (RBAC, spec-02).
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


def get_unit_level_repository(
    db: Annotated[Session, Depends(get_db)],
) -> UnitLevelRepository:
    return UnitLevelRepository(db)


def get_department_service(
    departments: Annotated[DepartmentRepository, Depends(get_department_repository)],
    roles: Annotated[RoleRepository, Depends(get_role_repository)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
    levels: Annotated[UnitLevelRepository, Depends(get_unit_level_repository)],
) -> DepartmentService:
    return DepartmentService(departments, roles, users, audit, levels)


def get_unit_level_service(
    levels: Annotated[UnitLevelRepository, Depends(get_unit_level_repository)],
    departments: Annotated[DepartmentRepository, Depends(get_department_repository)],
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
) -> UnitLevelService:
    return UnitLevelService(levels, departments, audit)


def get_user_admin_service(
    users: Annotated[UserRepository, Depends(get_user_repository)],
    departments: Annotated[DepartmentRepository, Depends(get_department_repository)],
    roles: Annotated[RoleRepository, Depends(get_role_repository)],
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
) -> UserAdminService:
    return UserAdminService(users, departments, roles, audit)


def get_profile_service(
    users: Annotated[UserRepository, Depends(get_user_repository)],
    departments: Annotated[DepartmentRepository, Depends(get_department_repository)],
    roles: Annotated[RoleRepository, Depends(get_role_repository)],
) -> ProfileService:
    return ProfileService(users, departments, roles)


def get_activity_service(
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
) -> ActivityService:
    return ActivityService(audit, users)


def get_customer_repository(
    db: Annotated[Session, Depends(get_db)],
) -> CustomerRepository:
    return CustomerRepository(db)


def get_customer_service(
    customers: Annotated[CustomerRepository, Depends(get_customer_repository)],
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
) -> CustomerService:
    # The receivable port defaults to the raising SEAM-16 stub inside the service.
    return CustomerService(customers, audit)


def get_customer_analytics_service(
    db: Annotated[Session, Depends(get_db)],
) -> CustomerAnalyticsService:
    """CRM-360 analytics read over the live orders/quotations tables (same app)."""
    return CustomerAnalyticsService(db)


def get_product_repository(
    db: Annotated[Session, Depends(get_db)],
) -> ProductRepository:
    return ProductRepository(db)


def get_product_service(
    products: Annotated[ProductRepository, Depends(get_product_repository)],
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
) -> ProductService:
    return ProductService(products, audit)


def get_costing_repository(
    db: Annotated[Session, Depends(get_db)],
) -> CostingRepository:
    return CostingRepository(db)


def get_costing_service(
    costings: Annotated[CostingRepository, Depends(get_costing_repository)],
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
) -> CostingService:
    return CostingService(costings, audit)


def get_quotation_repository(
    db: Annotated[Session, Depends(get_db)],
) -> QuotationRepository:
    return QuotationRepository(db)


def get_quotation_service(
    quotations: Annotated[QuotationRepository, Depends(get_quotation_repository)],
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
    customers: Annotated[CustomerRepository, Depends(get_customer_repository)],
) -> QuotationService:
    # SEAM-14 CLOSED: the CRM repo is injected so the quotation can resolve the customer
    # display name (read-only). SEAM-13 (Tính giá result) stays a raising stub inside the
    # service until the giá-vốn engine (feat-040..042) is built.
    return QuotationService(quotations, audit, customers=customers)


def get_order_repository(
    db: Annotated[Session, Depends(get_db)],
) -> OrderRepository:
    return OrderRepository(db)


def get_order_service(
    orders: Annotated[OrderRepository, Depends(get_order_repository)],
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
    quotations: Annotated[QuotationRepository, Depends(get_quotation_repository)],
    customers: Annotated[CustomerRepository, Depends(get_customer_repository)],
) -> OrderService:
    # SEAM-04 quotation_ref half CLOSED-live: the Báo giá repo is injected so the order can
    # pull an approved quotation (read-only). The deposit half (Payment) stays a raising stub
    # inside order_ports until the Payment table is built (feat-048). CRM repo resolves the
    # customer display name (kéo từ báo giá, read-only).
    return OrderService(orders, audit, quotations=quotations, customers=customers)


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
