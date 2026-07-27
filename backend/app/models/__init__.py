"""ORM models. Importing this package registers every model on Base.metadata."""
from .attendance import (
    AttendanceLog,
    AttendancePeriod,
    AttendancePeriodLine,
    WorkLocation,
    WorkShift,
)
from .audit import AuditLog
from .costing import Costing, CostingOperation, CostingPaperOption
from .customer import Customer
from .department import Department
from .employee import Employee, EmployeeAttachment, EmployeeEvent, EmployeeShiftAssignment
from .profile_request import ProfileUpdateRequest
from .leave import LeaveRequest, LeaveType
from .overtime import OvertimeRequest
from .work_calendar import SpecialDay, WorkCalendarConfig
from .material import Material, MaterialCost
from .machine import Machine, MachineRate
from .module import Module
from .operation import Operation, OperationRate
from .order import (
    Order,
    OrderApproval,
    OrderAttachment,
    OrderLine,
)
from .payroll import (
    EmployeeSalary,
    LatePenaltyBracket,
    PayrollLine,
    PayrollParams,
    PayrollPeriod,
    PitTaxBracket,
    SalaryAdvance,
    SalaryRateRule,
)
from .piece_work import PieceRate
from .product import Product, ProductComponent
from .product_type_catalog import ProductTypeCatalog
from .purchase import (
    DepartmentPurchaseRequest,
    DepartmentPurchaseRequestLine,
    PurchaseRequest,
    PurchaseRequestLine,
    PurchaseRequestSource,
    Supplier,
)
from .accounting import (
    CompanyBankAccount,
    PaymentReceipt,
    PaymentReceiptAttachment,
    PaymentVoucher,
    PaymentVoucherAttachment,
    SupplierBankAccount,
)
from .quotation import (
    Quote,
    QuoteApproval,
    QuoteActivityLog,
    QuoteAttachment,
    QuoteItem,
    QuoteVersion,
)
from .refresh_token import RefreshToken
from .role import Role, RolePermission
from .unit_level import UnitLevel
from .user import User
from .plate_die_rate import PlateDieRate
from .norm import Norm
from .may_thiet_bi import MayThietBi
from .vat_lieu_kho import ChungLoaiGiay, GiayGiaVersion, GiayNguyen, VatTuInAn
from .cong_doan import CongDoan
from .bu_hao import BuHao
from .kho_hang import KhoHang
from .khuon_be import KhuonBe
from .loai_san_pham import LoaiSanPham
from .phieu_tinh_gia import PhieuTinhGia, PhieuThanhPhan, PhieuThanhPham
from .lsx import Lsx, LsxCongDoan
from .bai_ghep import BaiGhep, BaiGhepThanhVien
from .xep_lich import XepLichCongDoan
from .xep_lich_van_de import XepLichVanDe
from .machine_unavailable import MachineUnavailablePeriod
from .document_sequence import DocumentSequence
from .estimate import Estimate, EstimateOption, EstimateCostLine

__all__ = [
    "User",
    "Department",
    "Role",
    "RolePermission",
    "Module",
    "AuditLog",
    "RefreshToken",
    "UnitLevel",
    "Employee",
    "EmployeeShiftAssignment",
    "EmployeeEvent",
    "EmployeeAttachment",
    "ProfileUpdateRequest",
    "WorkLocation",
    "WorkShift",
    "AttendanceLog",
    "AttendancePeriod",
    "AttendancePeriodLine",
    "LeaveType",
    "LeaveRequest",
    "OvertimeRequest",
    "WorkCalendarConfig",
    "SpecialDay",
    "Customer",
    "Product",
    "ProductComponent",
    "ProductTypeCatalog",
    "Supplier",
    "DepartmentPurchaseRequest",
    "DepartmentPurchaseRequestLine",
    "PurchaseRequest",
    "PurchaseRequestLine",
    "PurchaseRequestSource",
    "CompanyBankAccount",
    "SupplierBankAccount",
    "PaymentVoucher",
    "PaymentReceipt",
    "PaymentVoucherAttachment",
    "PaymentReceiptAttachment",
    "Material",
    "MaterialCost",
    "Machine",
    "MachineRate",
    "Operation",
    "OperationRate",
    "Quote",
    "QuoteVersion",
    "QuoteItem",
    "QuoteAttachment",
    "QuoteActivityLog",
    "QuoteApproval",
    "Costing",
    "CostingPaperOption",
    "CostingOperation",
    "Order",
    "OrderLine",
    "OrderApproval",
    "OrderAttachment",
    "PayrollParams",
    "SalaryRateRule",
    "EmployeeSalary",
    "SalaryAdvance",
    "PayrollPeriod",
    "PayrollLine",
    "PitTaxBracket",
    "LatePenaltyBracket",
    "PieceRate",
    "PlateDieRate",
    "Norm",
    "DocumentSequence",
    "Estimate",
    "EstimateOption",
    "EstimateCostLine",
    "PhieuTinhGia",
    "PhieuThanhPhan",
    "PhieuThanhPham",
    "KhoHang",
    "KhuonBe",
    "Lsx",
    "LsxCongDoan",
    "BaiGhep",
    "BaiGhepThanhVien",
    "XepLichCongDoan",
    "XepLichVanDe",
    "MachineUnavailablePeriod",
]
