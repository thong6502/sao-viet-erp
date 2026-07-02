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
from .repositories.machine_repo import MachineRepository
from .repositories.material_repo import MaterialRepository
from .repositories.operation_repo import OperationRepository
from .repositories.order_repo import OrderRepository
from .repositories.product_repo import ProductRepository
from .repositories.product_type_catalog_repo import ProductTypeCatalogRepository
from .repositories.quotation_repo import QuotationRepository
from .repositories.rbac_repo import (
    DepartmentRepository,
    ModuleRepository,
    RoleRepository,
    UnitLevelRepository,
)
from .repositories.refresh_token_repo import RefreshTokenRepository
from .repositories.user_repo import UserRepository
from .repositories.click_ink_rate_repo import ClickInkRateRepository
from .repositories.plate_die_rate_repo import PlateDieRateRepository
from .repositories.norm_repo import NormRepository
from .repositories.document_sequence_repo import DocumentSequenceRepository
from .repositories.estimate_repo import EstimateRepository
from .security import decode_access_token
from .services.auth_service import AuthError, AuthService
from .services.activity_service import ActivityService
from .services.costing_service import CostingService
from .services.estimate_service import EstimateService
from .services.customer_analytics import CustomerAnalyticsService
from .services.customer_service import CustomerService
from .services.department_service import DepartmentService
from .services.machine_service import MachineService
from .services.material_service import MaterialService
from .services.operation_service import OperationService
from .services.product_service import ProductService
from .services.product_type_catalog_service import ProductTypeCatalogService
from .services.order_service import OrderService
from .services.quotation_service import QuotationService
from .services.profile_service import ProfileService
from .services.rbac_service import AuthorizationService
from .services.refresh_service import RefreshTokenService
from .services.role_service import RoleService
from .services.unit_level_service import UnitLevelService
from .services.user_admin_service import UserAdminService
from .services.click_ink_rate_service import ClickInkRateService
from .services.plate_die_rate_service import PlateDieRateService
from .services.norm_service import NormService
from .services.sequence_service import SequenceService


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
    estimates: Annotated[EstimateRepository, Depends(get_estimate_repository)],
) -> QuotationService:
    # SEAM-14 CLOSED: the CRM repo is injected so the quotation can resolve the customer
    # display name (read-only). SEAM-13 CLOSED: the Tính giá (Estimate) repo is injected so
    # a quotation referencing a calculated estimate pulls the frozen giá vốn + snapshots.
    return QuotationService(quotations, audit, customers=customers, estimates=estimates)


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


def get_product_type_catalog_repository(
    db: Annotated[Session, Depends(get_db)],
) -> ProductTypeCatalogRepository:
    return ProductTypeCatalogRepository(db)


def get_product_type_catalog_service(
    repo: Annotated[
        ProductTypeCatalogRepository, Depends(get_product_type_catalog_repository)
    ],
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
) -> ProductTypeCatalogService:
    return ProductTypeCatalogService(repo, audit)


def get_material_repository(
    db: Annotated[Session, Depends(get_db)],
) -> MaterialRepository:
    return MaterialRepository(db)


def get_material_service(
    repo: Annotated[MaterialRepository, Depends(get_material_repository)],
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
) -> MaterialService:
    return MaterialService(repo, audit)


def get_machine_repository(
    db: Annotated[Session, Depends(get_db)],
) -> MachineRepository:
    return MachineRepository(db)


def get_machine_service(
    repo: Annotated[MachineRepository, Depends(get_machine_repository)],
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
) -> MachineService:
    return MachineService(repo, audit)


def get_operation_repository(
    db: Annotated[Session, Depends(get_db)],
) -> OperationRepository:
    return OperationRepository(db)


def get_operation_service(
    repo: Annotated[OperationRepository, Depends(get_operation_repository)],
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
) -> OperationService:
    return OperationService(repo, audit)


def get_click_ink_rate_repository(
    db: Annotated[Session, Depends(get_db)],
) -> ClickInkRateRepository:
    return ClickInkRateRepository(db)


def get_click_ink_rate_service(
    repo: Annotated[ClickInkRateRepository, Depends(get_click_ink_rate_repository)],
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
) -> ClickInkRateService:
    return ClickInkRateService(repo, audit)


def get_plate_die_rate_repository(
    db: Annotated[Session, Depends(get_db)],
) -> PlateDieRateRepository:
    return PlateDieRateRepository(db)


def get_plate_die_rate_service(
    repo: Annotated[PlateDieRateRepository, Depends(get_plate_die_rate_repository)],
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
) -> PlateDieRateService:
    return PlateDieRateService(repo, audit)


def get_norm_repository(
    db: Annotated[Session, Depends(get_db)],
) -> NormRepository:
    return NormRepository(db)


def get_norm_service(
    repo: Annotated[NormRepository, Depends(get_norm_repository)],
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
) -> NormService:
    return NormService(repo, audit)


def get_document_sequence_repository(
    db: Annotated[Session, Depends(get_db)],
) -> DocumentSequenceRepository:
    return DocumentSequenceRepository(db)


def get_sequence_service(
    repo: Annotated[DocumentSequenceRepository, Depends(get_document_sequence_repository)],
) -> SequenceService:
    return SequenceService(repo)


def get_estimate_repository(
    db: Annotated[Session, Depends(get_db)],
) -> EstimateRepository:
    return EstimateRepository(db)


def get_estimate_service(
    db: Annotated[Session, Depends(get_db)],
    repo: Annotated[EstimateRepository, Depends(get_estimate_repository)],
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
    sequence: Annotated[SequenceService, Depends(get_sequence_service)],
) -> EstimateService:
    return EstimateService(db, repo, audit, sequence)




