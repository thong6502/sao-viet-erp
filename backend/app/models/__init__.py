"""ORM models. Importing this package registers every model on Base.metadata."""
from .attendance import (
    AttendanceLog,
    AttendancePeriod,
    AttendancePeriodLine,
    WorkLocation,
    WorkShift,
)
from .audit import AuditLog
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
    SalesInvoice,
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
from .cong_doan import CongDoan, CongDoanDauViec, CongDoanDauViecVatTu
from .bu_hao import BuHao
from .don_vi_do import DonViDo, DonViQuyDoi
from .kho_hang import KhoHang, KhoViTri
from .kho_khoa_so import KhoKhoaSo
from .kho_ky_ton import KhoKyTon
from .notification import Notification
from .delivery import (
    DeliveryRequest,
    DeliveryRequestLine,
    DeliveryStatusHistory,
    DeliveryTrip,
    DeliveryTripLine,
)
from .stock_request import StockRequest, StockRequestLine
from .stock_lot import StockLot, StockThreshold
from .stock_voucher import StockVoucher, StockVoucherAttachment, StockVoucherLine
from .khuon_be import KhuonBe
from .vat_tu_giu_cho import VatTuGiuCho
from .loai_san_pham import LoaiSanPham
from .phieu_tinh_gia import PhieuTinhGia, PhieuThanhPhan, PhieuThanhPham, SanPhamTaiBan
from .lsx import Lsx, LsxCongDoan, LsxCongDoanVatTu, LsxCongDoanPhuThuoc
from .bai_ghep import BaiGhep, BaiGhepThanhVien
from .bai_ghep_cong_doan import BaiGhepCongDoan, BaiGhepCongDoanMap, BaiGhepCongDoanVatTu
from .xep_lich import XepLichCongDoan
from .xep_lich_van_de import XepLichVanDe
from .machine_unavailable import MachineUnavailablePeriod
# Bảng MỚI phải import Ở ĐÂY thì `create_all` mới dựng: module không được import thì class không
# chạy, không đăng ký lên `Base.metadata`, và bảng lặng lẽ không tồn tại (không lỗi nào bật ra).
from .to_quan_so import ToQuanSoNgay
from .document_sequence import DocumentSequence
from .cong_thuc_lich_su import CongThucLichSu
from .ky_thuat_may import BaoTriMay, KyThuatMayAnh, SuaChuaMay, YeuCauSuaChua
from .module_notification import ModuleNotification, ModuleNotificationRead
from .san_xuat import (
    SanXuatCongViec,
    SanXuatGoiPhatHanh,
    SanXuatNhom,
    SanXuatNhomLsx,
    SanXuatPhienBan,
    SanXuatPhuThuoc,
)
from .san_xuat_thuc_thi import (
    SanXuatKhoangThamGia,
    SanXuatPhanCong,
    SanXuatPhienChay,
)
from .san_xuat_ly_do import SanXuatLyDo
from .san_xuat_san_luong import (
    SanXuatBanGiao,
    SanXuatBanGiaoDieuChinh,
    SanXuatBatch,
    SanXuatBatchLotVao,
    SanXuatKetQuaNhanh,
    SanXuatVatTuNhan,
)
from .san_xuat_phan_bo import (
    SanXuatHoTro,
    SanXuatPhanBo,
    SanXuatPhanBoBuTru,
    SanXuatPhanBoDong,
    SanXuatPhanBoLoaiTru,
)
from .san_xuat_kcs import (
    SanXuatKcsBatch,
    SanXuatKcsLoi,
    SanXuatKcsLoiAnh,
)
from .san_xuat_kho import (
    SanXuatKhoHang,
    SanXuatKhoLot,
    SanXuatNhapKhoYc,
)
from .cong_doan_tag import CongDoanTag, CongDoanTagCatalog

__all__ = [
    "CongDoanTag",
    "CongDoanTagCatalog",
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
    "SalesInvoice",
    "PaymentVoucherAttachment",
    "PaymentReceiptAttachment",
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
    "ModuleNotification",
    "ModuleNotificationRead",
    "PhieuTinhGia",
    "PhieuThanhPhan",
    "PhieuThanhPham",
    "SanPhamTaiBan",
    "KhoHang",
    "KhoViTri",
    "KhoKhoaSo",
    "KhoKyTon",
    "Notification",
    "DeliveryRequest",
    "DeliveryRequestLine",
    "DeliveryStatusHistory",
    "DeliveryTrip",
    "DeliveryTripLine",
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
    "CongDoanDauViecVatTu",
    "BaiGhep",
    "BaiGhepThanhVien",
    "XepLichCongDoan",
    "XepLichVanDe",
    "MachineUnavailablePeriod",
    "SuaChuaMay",
    "BaoTriMay",
    "KyThuatMayAnh",
    "YeuCauSuaChua",
    "ToQuanSoNgay",
    "CongThucLichSu",
    "DonViDo",
    "DonViQuyDoi",
    "SanXuatNhom",
    "SanXuatNhomLsx",
    "SanXuatGoiPhatHanh",
    "SanXuatPhienBan",
    "SanXuatCongViec",
    "SanXuatPhuThuoc",
    "SanXuatPhanCong",
    "SanXuatPhienChay",
    "SanXuatKhoangThamGia",
    "SanXuatLyDo",
    "SanXuatBatch",
    "SanXuatBatchLotVao",
    "SanXuatBanGiao",
    "SanXuatBanGiaoDieuChinh",
    "SanXuatVatTuNhan",
    "SanXuatKetQuaNhanh",
    "SanXuatHoTro",
    "SanXuatPhanBo",
    "SanXuatPhanBoDong",
    "SanXuatPhanBoBuTru",
    "SanXuatPhanBoLoaiTru",
    "SanXuatKcsBatch",
    "SanXuatKcsLoi",
    "SanXuatKcsLoiAnh",
    "SanXuatKhoHang",
    "SanXuatKhoLot",
    "SanXuatNhapKhoYc",
]
