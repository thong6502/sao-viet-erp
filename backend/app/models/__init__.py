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
from .employee import (
    Employee,
    EmployeeAttachment,
    EmployeeEvent,
    EmployeeShiftAssignment,
    EmployeeShiftChangeLog,
    EmployeeShiftDay,
    JobGrade,
)
from .noi_quy import (
    NoiQuyAttachment,
    NoiQuyDocument,
    NoiQuyPage,
    NoiQuyRecord,
    NoiQuyVersion,
)
from .profile_request import ProfileUpdateRequest
from .leave import LeaveRequest, LeaveType
from .late_early import LateEarlyRequest
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
    EmployeeSalaryComponent,
    LatePenaltyBracket,
    PayrollComponent,
    PayrollLine,
    PayrollLineComponent,
    PayrollParams,
    PayrollPeriod,
    PitTaxBracket,
    SalaryAdvance,
    SalaryRateRule,
)
from .piece_work import PieceLeaderBonusBracket, PieceLeaderBonusSetting, PieceRate
from .product import Product, ProductComponent
from .product_type_catalog import ProductTypeCatalog
from .purchase import (
    DepartmentPurchaseRequest,
    DepartmentPurchaseRequestLine,
    PurchaseAttachment,
    PurchaseDelivery,
    PurchaseDeliveryLine,
    PurchaseRequest,
    PurchaseRequestLine,
    PurchaseRequestSource,
    PurchaseStatusHistory,
    Supplier,
    SupplierItem,
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
from .may_thiet_bi import MayThietBi, NhomMay
from .vat_lieu_kho import ChungLoaiGiay, GiayGiaVersion, GiayNguyen, VatTuInAn
from .cong_doan import CongDoan, CongDoanDauViec
from .bu_hao import BuHao
from .don_vi_do import DonViDo, DonViQuyDoi
from .kho_hang import KhoHang
from .stock_request import StockRequest, StockRequestLine
from .stock_lot import StockLot, StockThreshold
from .stock_voucher import StockVoucher, StockVoucherAttachment, StockVoucherLine
from .khuon_be import KhuonBe
from .loai_san_pham import LoaiSanPham
from .phieu_tinh_gia import PhieuTinhGia, PhieuThanhPhan, PhieuThanhPham
from .lsx import Lsx, LsxCongDoan, LsxCongDoanVatTu, LsxCongDoanPhuThuoc
from .bai_ghep import BaiGhep, BaiGhepThanhVien
from .bai_ghep_cong_doan import BaiGhepCongDoan, BaiGhepCongDoanMap, BaiGhepCongDoanVatTu
from .xep_lich import XepLichCongDoan
from .xep_lich_van_de import XepLichVanDe
from .machine_unavailable import MachineUnavailablePeriod
from .document_sequence import DocumentSequence
from .estimate import Estimate, EstimateOption, EstimateCostLine

__all__ = [
    "BaiGhepCongDoan",
    "BaiGhepCongDoanMap",
    "BaiGhepCongDoanVatTu",
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
    "EmployeeShiftChangeLog",
    "EmployeeShiftDay",
    "EmployeeEvent",
    "EmployeeAttachment",
    "JobGrade",
    "NoiQuyDocument",
    "NoiQuyRecord",
    "NoiQuyVersion",
    "NoiQuyAttachment",
    "NoiQuyPage",
    "ProfileUpdateRequest",
    "WorkLocation",
    "WorkShift",
    "AttendanceLog",
    "AttendancePeriod",
    "AttendancePeriodLine",
    "LeaveType",
    "LeaveRequest",
    "OvertimeRequest",
    "LateEarlyRequest",
    "WorkCalendarConfig",
    "SpecialDay",
    "Customer",
    "Product",
    "ProductComponent",
    "ProductTypeCatalog",
    "Supplier",
    "SupplierItem",
    "DepartmentPurchaseRequest",
    "DepartmentPurchaseRequestLine",
    "PurchaseRequest",
    "PurchaseRequestLine",
    "PurchaseRequestSource",
    "PurchaseDelivery",
    "PurchaseDeliveryLine",
    "PurchaseAttachment",
    "PurchaseStatusHistory",
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
    "PayrollComponent",
    "EmployeeSalaryComponent",
    "PayrollLineComponent",
    "PitTaxBracket",
    "LatePenaltyBracket",
    "PieceLeaderBonusBracket",
    "PieceLeaderBonusSetting",
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
    "StockRequest",
    "StockRequestLine",
    "StockVoucher",
    "StockVoucherAttachment",
    "StockVoucherLine",
    "StockLot",
    "StockThreshold",
    "KhuonBe",
    "Lsx",
    "LsxCongDoan",
    "LsxCongDoanVatTu",
    "LsxCongDoanPhuThuoc",
    "CongDoanDauViec",
    "BaiGhep",
    "BaiGhepThanhVien",
    "XepLichCongDoan",
    "XepLichVanDe",
    "MachineUnavailablePeriod",
    "DonViDo",
    "DonViQuyDoi",
]
