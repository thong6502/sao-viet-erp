"""FastAPI dependency providers (the composition root for each request).

Wires DB session -> repository -> service, and resolves the bearer token into the
current user. Auth enters here as an explicit dependency boundary, not by reaching
across layers (docs/ARCHITECTURE.md).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .db import get_db
from .models.user import User
from .repositories.audit_repo import AuditLogRepository
from .repositories.accounting_repo import AccountingRepository
from .repositories.attendance_repo import AttendanceRepository
from .repositories.calendar_repo import CalendarRepository
from .repositories.late_early_repo import LateEarlyRepository
from .repositories.leave_repo import LeaveRepository
from .repositories.overtime_repo import OvertimeRepository
from .repositories.payroll_component_repo import PayrollComponentRepository
from .repositories.payroll_repo import PayrollRepository
from .repositories.piece_work_repo import PieceWorkRepository
from .repositories.cong_doan_repo import CongDoanRepository
from .repositories.customer_repo import CustomerRepository
from .repositories.employee_repo import EmployeeRepository
from .repositories.noi_quy_repo import NoiQuyRepository
from .repositories.machine_repo import MachineRepository
from .repositories.operation_repo import OperationRepository
from .repositories.product_type_catalog_repo import ProductTypeCatalogRepository
from .repositories.purchase_repo import (
    DepartmentPurchaseRequestRepository,
    PurchaseRequestRepository,
    PurchaseStatusHistoryRepository,
    SupplierRepository,
)
from .repositories.quotation_repo import QuotationRepository
from .repositories.order_repo import OrderRepository
from .repositories.rbac_repo import (
    DepartmentRepository,
    ModuleRepository,
    RoleRepository,
    UnitLevelRepository,
)
from .repositories.refresh_token_repo import RefreshTokenRepository
from .repositories.user_repo import UserRepository
from .repositories.plate_die_rate_repo import PlateDieRateRepository
from .repositories.norm_repo import NormRepository
from .repositories.document_sequence_repo import DocumentSequenceRepository
from .security import decode_access_token, decode_file_token
from .services.auth_service import AuthError, AuthService
from .services.accounting_service import AccountingService
from .services.activity_service import ActivityService
from .services.customer_analytics import CustomerAnalyticsService
from .services.attendance_service import AttendanceService
from .services.calendar_service import CalendarService
from .services.leave_service import LeaveService
from .services.late_early_service import LateEarlyService
from .services.overtime_service import OvertimeService
from .services.payroll_component_service import PayrollComponentService
from .services.payroll_service import PayrollService
from .services.piece_work_service import PieceWorkService
from .services.customer_service import CustomerService
from .services.department_service import DepartmentService
from .services.employee_service import EmployeeService
from .services.noi_quy_service import NoiQuyService
from .services.machine_service import MachineService
from .services.operation_service import OperationService
from .services.product_type_catalog_service import ProductTypeCatalogService
from .services.purchase_service import PurchaseService
from .services.quotation_service import QuotationService
from .services.order_service import OrderService
from .services.profile_service import ProfileService
from .services.rbac_service import AuthorizationService
from .services.refresh_service import RefreshTokenService
from .services.role_service import RoleService
from .services.unit_level_service import UnitLevelService
from .services.user_admin_service import UserAdminService
from .services.sequence_service import SequenceService


# auto_error=False so we can return our own 401 shape for missing/invalid tokens.
_bearer = HTTPBearer(auto_error=False)


def get_user_repository(db: Annotated[Session, Depends(get_db)]) -> UserRepository:
    return UserRepository(db)


def get_auth_service(
    users: Annotated[UserRepository, Depends(get_user_repository)],
    db: Annotated[Session, Depends(get_db)],
) -> AuthService:
    # EmployeeRepository dựng thẳng từ db (get_employee_repository khai bên dưới file này):
    # login cần đọc hồ sơ để chặn tài khoản của người ĐÃ NGHỈ VIỆC.
    return AuthService(users, EmployeeRepository(db))


def get_refresh_token_repository(
    db: Annotated[Session, Depends(get_db)],
) -> RefreshTokenRepository:
    return RefreshTokenRepository(db)


def get_refresh_service(
    tokens: Annotated[RefreshTokenRepository, Depends(get_refresh_token_repository)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
) -> RefreshTokenService:
    return RefreshTokenService(tokens, users)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _user_from_claims(claims: dict | None, auth: AuthService) -> User:
    """Claims đã giải mã → User. Hai chốt chặn dùng chung cho MỌI đường vào (Bearer lẫn cookie
    file), nên thêm đường vào mới không lỡ bỏ sót cái nào."""
    if claims is None:
        raise _unauthorized()
    try:
        user = auth.user_from_token_subject(claims.get("sub"))
    except AuthError:
        raise _unauthorized() from None
    # Hard-revoke: a token whose `tv` no longer matches the user's token_version is dead
    # (logout-all / forced invalidation), even if not yet expired (spec-03).
    if claims.get("tv") != user.token_version:
        raise _unauthorized()
    # A locked account is rejected even with a still-valid token (RBAC, spec-02).
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản đã bị khóa",
        )
    return user


def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    if creds is None or not creds.credentials:
        raise _unauthorized()
    return _user_from_claims(decode_access_token(creds.credentials), auth)


CurrentUser = Annotated[User, Depends(get_current_user)]


# --- Cửa vào bằng cookie (chỉ cho /api/files) -------------------------------
# `<img src>` / `<a download>` do trình duyệt tự phát nên KHÔNG mang được header Bearer, mà
# access token cố ý chỉ nằm trong RAM của tab. Cookie là đường duy nhất — xem app/routers/files.py.
FILE_COOKIE = "file_access"
FILE_COOKIE_PATH = "/api/files"


def get_file_user(
    request: Request,
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    raw = request.cookies.get(FILE_COOKIE)
    if not raw:
        raise _unauthorized()
    return _user_from_claims(decode_file_token(raw), auth)


FileUser = Annotated[User, Depends(get_file_user)]


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
    db: Annotated[Session, Depends(get_db)],
    departments: Annotated[DepartmentRepository, Depends(get_department_repository)],
    roles: Annotated[RoleRepository, Depends(get_role_repository)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
    levels: Annotated[UnitLevelRepository, Depends(get_unit_level_repository)],
) -> DepartmentService:
    return DepartmentService(departments, roles, users, audit, levels, EmployeeRepository(db))


def get_unit_level_service(
    levels: Annotated[UnitLevelRepository, Depends(get_unit_level_repository)],
    departments: Annotated[DepartmentRepository, Depends(get_department_repository)],
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
) -> UnitLevelService:
    return UnitLevelService(levels, departments, audit)


def get_user_admin_service(
    db: Annotated[Session, Depends(get_db)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
    departments: Annotated[DepartmentRepository, Depends(get_department_repository)],
    roles: Annotated[RoleRepository, Depends(get_role_repository)],
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
    tokens: Annotated[RefreshTokenRepository, Depends(get_refresh_token_repository)],
) -> UserAdminService:
    return UserAdminService(users, departments, roles, audit, tokens, EmployeeRepository(db))


def get_profile_service(
    db: Annotated[Session, Depends(get_db)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
    departments: Annotated[DepartmentRepository, Depends(get_department_repository)],
    roles: Annotated[RoleRepository, Depends(get_role_repository)],
) -> ProfileService:
    return ProfileService(users, departments, roles, EmployeeRepository(db))


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


def get_employee_repository(
    db: Annotated[Session, Depends(get_db)],
) -> EmployeeRepository:
    return EmployeeRepository(db)


def get_employee_service(
    employees: Annotated[EmployeeRepository, Depends(get_employee_repository)],
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
    departments: Annotated[DepartmentRepository, Depends(get_department_repository)],
) -> EmployeeService:
    return EmployeeService(employees, audit, users, departments)


def get_noi_quy_repository(
    db: Annotated[Session, Depends(get_db)],
) -> NoiQuyRepository:
    return NoiQuyRepository(db)


def get_noi_quy_service(
    noi_quy: Annotated[NoiQuyRepository, Depends(get_noi_quy_repository)],
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
) -> NoiQuyService:
    return NoiQuyService(noi_quy, audit)


def get_calendar_repository(
    db: Annotated[Session, Depends(get_db)],
) -> CalendarRepository:
    return CalendarRepository(db)


def get_calendar_service(
    calendar: Annotated[CalendarRepository, Depends(get_calendar_repository)],
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
) -> CalendarService:
    return CalendarService(calendar, audit)


def get_attendance_repository(
    db: Annotated[Session, Depends(get_db)],
) -> AttendanceRepository:
    return AttendanceRepository(db)


def get_leave_repository(
    db: Annotated[Session, Depends(get_db)],
) -> LeaveRepository:
    return LeaveRepository(db)


def get_late_early_repository(
    db: Annotated[Session, Depends(get_db)],
) -> LateEarlyRepository:
    return LateEarlyRepository(db)


def get_attendance_service(
    attendance: Annotated[AttendanceRepository, Depends(get_attendance_repository)],
    employees: Annotated[EmployeeRepository, Depends(get_employee_repository)],
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
    leaves: Annotated[LeaveRepository, Depends(get_leave_repository)],
    calendar: Annotated[CalendarService, Depends(get_calendar_service)],
    payroll: Annotated[PayrollRepository, Depends(get_payroll_repository)],
    overtime: Annotated[OvertimeRepository, Depends(get_overtime_repository)],
    late_early: Annotated[LateEarlyRepository, Depends(get_late_early_repository)],
) -> AttendanceService:
    # leaves → đánh dấu ngày nghỉ (P/KL); calendar → công lễ; payroll (REPO) → chặn mở kỳ công
    # khi kỳ lương đã chốt (Q3); overtime (REPO) → gate tiền tăng ca theo phiếu đã duyệt;
    # late_early (REPO) → phiếu đi muộn/về sớm: miễn phạt + nhánh trừ phép.
    # Chỉ đọc REPO nên không vòng service↔service.
    return AttendanceService(attendance, employees, audit, leaves=leaves, calendar=calendar,
                             payroll=payroll, overtime=overtime, late_early=late_early)


def get_leave_service(
    leaves: Annotated[LeaveRepository, Depends(get_leave_repository)],
    employees: Annotated[EmployeeRepository, Depends(get_employee_repository)],
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
    calendar: Annotated[CalendarService, Depends(get_calendar_service)],
    late_early: Annotated[LateEarlyRepository, Depends(get_late_early_repository)],
) -> LeaveService:
    # calendar → loại ngày lễ khỏi quota + tuần T2–T7 (Thứ 7 nay trừ phép).
    # late_early (REPO) → phiếu đi muộn/về sớm có tick "trừ phép" cũng tiêu quỹ phép năm.
    return LeaveService(leaves, employees, audit, calendar=calendar, late_early=late_early)


def get_late_early_service(
    late_early: Annotated[LateEarlyRepository, Depends(get_late_early_repository)],
    employees: Annotated[EmployeeRepository, Depends(get_employee_repository)],
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
    attendance: Annotated[AttendanceRepository, Depends(get_attendance_repository)],
    leaves: Annotated[LeaveService, Depends(get_leave_service)],
) -> LateEarlyService:
    # attendance (REPO) → lấy KHUNG CA để quy phút vắng ra ngày phép (cùng mẫu số với tiền công).
    # leaves (SERVICE) → hỏi số ngày phép còn lại. Một chiều: LeaveService chỉ đọc LateEarly REPO.
    return LateEarlyService(late_early, employees, audit, attendance=attendance, leaves=leaves)


def get_overtime_repository(
    db: Annotated[Session, Depends(get_db)],
) -> OvertimeRepository:
    return OvertimeRepository(db)


def get_overtime_service(
    overtime: Annotated[OvertimeRepository, Depends(get_overtime_repository)],
    employees: Annotated[EmployeeRepository, Depends(get_employee_repository)],
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
) -> OvertimeService:
    return OvertimeService(overtime, employees, audit)


def get_payroll_repository(
    db: Annotated[Session, Depends(get_db)],
) -> PayrollRepository:
    return PayrollRepository(db)


def get_piece_work_repository(
    db: Annotated[Session, Depends(get_db)],
) -> PieceWorkRepository:
    return PieceWorkRepository(db)


def get_cong_doan_repository(
    db: Annotated[Session, Depends(get_db)],
) -> CongDoanRepository:
    return CongDoanRepository(db)


def get_piece_work_service(
    piece: Annotated[PieceWorkRepository, Depends(get_piece_work_repository)],
) -> PieceWorkService:
    # Lương khoán = đơn giá khoán (PieceRate). Nguồn sản lượng đã gỡ → khoán-theo-sản-lượng bỏ.
    return PieceWorkService(piece)


def get_payroll_component_repository(
    db: Annotated[Session, Depends(get_db)],
) -> PayrollComponentRepository:
    return PayrollComponentRepository(db)


def get_payroll_component_service(
    components: Annotated[PayrollComponentRepository, Depends(get_payroll_component_repository)],
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
    employees: Annotated[EmployeeRepository, Depends(get_employee_repository)],
) -> PayrollComponentService:
    # `employees` cho gán HÀNG LOẠT: lọc NV theo scope người bấm (tổ trưởng không gán ra ngoài tổ).
    return PayrollComponentService(components, audit, employees)


def get_payroll_service(
    payroll: Annotated[PayrollRepository, Depends(get_payroll_repository)],
    employees: Annotated[EmployeeRepository, Depends(get_employee_repository)],
    attendance: Annotated[AttendanceService, Depends(get_attendance_service)],
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
    piece: Annotated[PieceWorkService, Depends(get_piece_work_service)],
    departments: Annotated[DepartmentRepository, Depends(get_department_repository)],
    components: Annotated[PayrollComponentRepository, Depends(get_payroll_component_repository)],
) -> PayrollService:
    # attendance → số CÔNG; piece → tiền KHOÁN (nhịp 2); departments → cờ has_piece_work.
    return PayrollService(payroll, employees, attendance, audit=audit, piece=piece,
                          departments=departments, components=components)


def get_quotation_repository(
    db: Annotated[Session, Depends(get_db)],
) -> QuotationRepository:
    return QuotationRepository(db)


def get_quotation_service(
    quotations: Annotated[QuotationRepository, Depends(get_quotation_repository)],
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
    customers: Annotated[CustomerRepository, Depends(get_customer_repository)],
    sequence: Annotated[SequenceService, Depends(get_sequence_service)],
) -> QuotationService:
    # SEAM-14 CLOSED: the CRM repo is injected so the quotation can resolve the customer
    # display name (read-only). Nguồn giá vốn giờ CHỈ còn Phiếu tính giá (PhieuTinhGia) —
    # QuotationService đọc thẳng qua session của `quotations`, không cần repo riêng.
    return QuotationService(quotations, audit, customers=customers, sequence=sequence)


def get_order_repository(
    db: Annotated[Session, Depends(get_db)],
) -> OrderRepository:
    return OrderRepository(db)


# get_order_service khai SAU get_accounting_service (bên dưới) vì nó Depends vào — Depends resolve
# tên ở thời điểm định nghĩa hàm (xem ghi chú get_sequence_service ↔ get_accounting_service).


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


def require_any_permission(*grants: tuple[str, str]):
    """Like `require_permission`, but allows the request if ANY of the
    (module_key, action) pairs is granted — for read endpoints that legitimately
    serve more than one screen (e.g. role names shown inside the department view)."""

    def dependency(
        user: CurrentUser,
        authz: Annotated[AuthorizationService, Depends(get_authorization_service)],
    ) -> User:
        if not any(authz.can(user, module_key, action) for module_key, action in grants):
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


def get_supplier_repository(
    db: Annotated[Session, Depends(get_db)],
) -> SupplierRepository:
    return SupplierRepository(db)


def get_department_purchase_request_repository(
    db: Annotated[Session, Depends(get_db)],
) -> DepartmentPurchaseRequestRepository:
    return DepartmentPurchaseRequestRepository(db)


def get_purchase_request_repository(
    db: Annotated[Session, Depends(get_db)],
) -> PurchaseRequestRepository:
    return PurchaseRequestRepository(db)


def get_purchase_status_history_repository(
    db: Annotated[Session, Depends(get_db)],
) -> PurchaseStatusHistoryRepository:
    return PurchaseStatusHistoryRepository(db)


def get_purchase_service(
    suppliers: Annotated[SupplierRepository, Depends(get_supplier_repository)],
    department_requests: Annotated[
        DepartmentPurchaseRequestRepository,
        Depends(get_department_purchase_request_repository),
    ],
    requests: Annotated[PurchaseRequestRepository, Depends(get_purchase_request_repository)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
    departments: Annotated[DepartmentRepository, Depends(get_department_repository)],
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
    authz: Annotated[AuthorizationService, Depends(get_authorization_service)],
    lich_su: Annotated[
        PurchaseStatusHistoryRepository, Depends(get_purchase_status_history_repository)
    ],
    db: Annotated[Session, Depends(get_db)] = None,  # type: ignore[assignment]
) -> PurchaseService:
    # `hang` = danh mục gốc (Giấy + Vật tư khác): bảng giá NCC gắn về mặt hàng và so giá qua đó.
    from .repositories.don_vi_do_repo import DonViDoRepository
    from .repositories.vat_lieu_kho_repo import VatLieuKhoRepository
    from .services.vat_lieu_kho_service import VatLieuKhoService

    hang = VatLieuKhoService(VatLieuKhoRepository(db), DonViDoRepository(db))
    return PurchaseService(
        suppliers, department_requests, requests, users, departments, audit, authz, lich_su,
        hang=hang,
    )


def get_accounting_repository(
    db: Annotated[Session, Depends(get_db)],
) -> AccountingRepository:
    return AccountingRepository(db)


# Đánh số chứng từ — đặt TRƯỚC get_accounting_service vì nó Depends vào (Depends resolve
# ở thời điểm định nghĩa hàm).
def get_document_sequence_repository(
    db: Annotated[Session, Depends(get_db)],
) -> DocumentSequenceRepository:
    return DocumentSequenceRepository(db)


def get_sequence_service(
    repo: Annotated[DocumentSequenceRepository, Depends(get_document_sequence_repository)],
) -> SequenceService:
    return SequenceService(repo)


def get_accounting_service(
    repo: Annotated[AccountingRepository, Depends(get_accounting_repository)],
    requests: Annotated[PurchaseRequestRepository, Depends(get_purchase_request_repository)],
    suppliers: Annotated[SupplierRepository, Depends(get_supplier_repository)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
    sequences: Annotated[SequenceService, Depends(get_sequence_service)],
) -> AccountingService:
    return AccountingService(repo, requests, suppliers, users, audit, sequences)


def get_order_service(
    db: Annotated[Session, Depends(get_db)],
    repo: Annotated[OrderRepository, Depends(get_order_repository)],
    audit: Annotated[AuditLogRepository, Depends(get_audit_repository)],
    quotations: Annotated[QuotationRepository, Depends(get_quotation_repository)],
    accounting_repo: Annotated[AccountingRepository, Depends(get_accounting_repository)],
    accounting: Annotated[AccountingService, Depends(get_accounting_service)],
) -> OrderService:
    # SEAM-04: đọc báo giá (QuotationRepository) để snapshot dòng + deposit_pct khi tạo đơn.
    # V5: accounting_repo → đọc Σ cọc received + list phiếu; accounting (service) → LẬP phiếu thu cọc.
    return OrderService(repo, audit, quotations, db, accounting_repo, accounting)


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


# Gỡ 2026-07-16: get_{product,plate_die_rate,norm}_{repository,service} — chỉ nuôi 3 router
# products/plate_die_rates/norms đã gỡ. Bảng norms/plate_die_rates GIỮ: engine tính giá đang chạy
# (thanh_phan_engine) vẫn đọc, tự dựng từ db chứ không đi qua DI.
# Gỡ 2026-08-08 (Đợt 5): get_{costing,material,estimate}_{repository,service} — cụm tính giá đời cũ
# đã xoá hẳn cùng 3 router costings/materials/estimates.


