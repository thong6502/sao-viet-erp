"""Schemas — Giao hàng (docs/prd-giao-hang.md)."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


# --- Yêu cầu giao hàng ---------------------------------------------------------------------
class DeliveryLineIn(BaseModel):
    """Chỉ HAI ô: dòng đơn nào, bao nhiêu.

    Ba ô `hang_loai` / `hang_id` / `dvt` đã GỠ 19/08/2026 (mg 0203). Bản trước bắt người lập
    chọn "mặt hàng kho" — tức bắt chọn một thứ chưa tồn tại, vì sản phẩm in là hàng đặt riêng.
    Nay hệ tự khai lúc CHỐT ĐƠN (docs/prd-thanh-pham.md), máy chủ tự điền vào
    `delivery_request_lines`. Ba cột đó vẫn còn TRÊN BẢNG — chỉ không nhận từ client nữa.
    """

    order_line_id: int
    qty: int = Field(gt=0)


class DeliveryRequestCreate(BaseModel):
    order_id: int
    ngay_can_giao: date
    lines: list[DeliveryLineIn]
    # Bỏ trống ⇒ kéo từ đơn hàng bán (PRD §5: CHỌN, không gõ lại).
    dia_chi: str | None = None
    nguoi_nhan: str | None = None
    sdt_nguoi_nhan: str | None = None
    ghi_chu: str | None = None


class DeliveryRequestUpdate(BaseModel):
    ngay_can_giao: date | None = None
    dia_chi: str | None = None
    nguoi_nhan: str | None = None
    sdt_nguoi_nhan: str | None = None
    ghi_chu: str | None = None


class LyDoIn(BaseModel):
    ly_do: str


class DeliveryRequestLineOut(BaseModel):
    id: int
    order_line_id: int
    qty: int
    mo_ta: str | None = None
    don_vi_tinh: str | None = None
    da_giao: int = 0
    hang_loai: str | None = None
    hang_id: int | None = None
    hang_ten: str | None = None
    dvt: str | None = None


class DeliveryRequestOut(BaseModel):
    id: int
    code: str
    order_id: int
    order_code: str | None = None
    customer_id: int | None = None
    customer_name: str | None = None
    department_id: int | None = None
    ngay_can_giao: date
    dia_chi: str
    nguoi_nhan: str | None = None
    sdt_nguoi_nhan: str | None = None
    ghi_chu: str | None = None
    # Trạng thái HIỂN THỊ — hàm, không phải cột (PRD §7 tầng 1).
    trang_thai: str
    ly_do_huy: str | None = None
    created_by: int | None = None
    created_by_name: str | None = None
    created_at: datetime
    lines: list[DeliveryRequestLineOut] = []
    so_lan_giao: int = 0


class DeliveryRequestPage(BaseModel):
    items: list[DeliveryRequestOut]


# --- Lần giao ------------------------------------------------------------------------------
class PlanIn(BaseModel):
    request_id: int
    employee_id: int
    gio_lay_hang: datetime
    gio_du_kien_giao: datetime
    kho_id: int | None = None
    ghi_chu_phan_cong: str | None = None


class PlanUpdate(BaseModel):
    employee_id: int | None = None
    gio_lay_hang: datetime | None = None
    gio_du_kien_giao: datetime | None = None
    ghi_chu_phan_cong: str | None = None


class SoThucNhanIn(BaseModel):
    order_line_id: int
    qty: int = Field(ge=0)


class KetQuaIn(BaseModel):
    ket_qua: str
    # `ge=0`, KHÔNG phải `gt=0`: xe chưa lăn bánh mà khách không nghe máy thì 0 km là số THẬT.
    km: int = Field(ge=0)
    thoi_gian_ket_thuc: datetime | None = None
    nguoi_nhan_thuc_te: str | None = None
    ly_do_that_bai: str | None = None
    huong_xu_ly: str | None = None
    # `ngay_hen_lai` GỠ khỏi ô khai (22/08/2026): kết quả "hẹn lại" không còn. Cột DB vẫn còn để
    # đọc dòng cũ — xem `models/delivery.LG_HEN_LAI`.
    ghi_chu: str | None = None
    so_thuc_nhan: list[SoThucNhanIn] | None = None
    # Bật khi người dùng đã xem cảnh báo "km lớn bất thường" và khẳng định đúng.
    xac_nhan_km_lon: bool = False


class TripLineOut(BaseModel):
    order_line_id: int
    qty_giao: int


class TripOut(BaseModel):
    id: int
    request_id: int
    request_code: str | None = None
    order_id: int | None = None
    order_code: str | None = None
    customer_name: str | None = None
    lan_thu: int
    employee_id: int
    employee_name: str | None = None
    gio_lay_hang: datetime
    gio_du_kien_giao: datetime
    ghi_chu_phan_cong: str | None = None
    trang_thai: str
    km: int | None = None
    thoi_gian_ket_thuc: datetime | None = None
    nguoi_nhan_thuc_te: str | None = None
    ly_do_that_bai: str | None = None
    huong_xu_ly: str | None = None
    #: Chỉ còn để hiện dòng CŨ khai trước 22/08/2026; chuyến mới luôn `None`.
    ngay_hen_lai: date | None = None
    ghi_chu_ket_qua: str | None = None
    lines: list[TripLineOut] = []
    # Mã + trạng thái YÊU CẦU XUẤT KHO của chuyến (chứng từ của KHO, không phải của
    # Giao hàng). None = chưa gửi.
    yeu_cau_kho_ma: str | None = None
    yeu_cau_kho_trang_thai: str | None = None
    #: Kho đã LẬP PHIẾU chưa ⇒ hiện "Kho đã chuẩn bị xong". Suy ra từ `stock_vouchers`, không
    #: phải cột lưu — kho thao tác trên màn của họ, cột lưu ở đây sớm muộn lệch với sổ kho.
    kho_da_lap_phieu: bool = False


class TripPage(BaseModel):
    items: list[TripOut]


class PlanOut(BaseModel):
    trip: TripOut
    canh_bao: list[str] = []


class HistoryOut(BaseModel):
    id: int
    tu_trang_thai: str | None = None
    den_trang_thai: str
    nguoi_thao_tac_id: int | None = None
    nguoi_thao_tac_name: str | None = None
    luc: datetime
    ghi_chu: str | None = None
    ly_do: str | None = None


class RequestDetailOut(BaseModel):
    request: DeliveryRequestOut
    trips: list[TripOut] = []
    lich_su: list[HistoryOut] = []


# --- Yêu cầu xuất kho (dùng CHỨNG TỪ CỦA KHO, không dựng loại riêng) --------------------------
class HangCanXuatOut(BaseModel):
    """Một dòng SẼ gửi kho — máy suy ra, người dùng chỉ xem."""

    hang_loai: str
    hang_id: int
    hang_ten: str | None = None
    dvt: str
    sl_de_nghi: float


class YeuCauXuatKhoIn(BaseModel):
    """Chỉ gửi xuống kho. Dòng hàng suy ra từ chính yêu cầu giao — không nhận từ ngoài.

    `kho_id` để TRỐNG (chủ 21/08/2026: "gửi phiếu xuống kho để họ duyệt, mà họ xuất kho nào kệ
    họ chứ"). Người gửi không biết hàng đang nằm kho nào — thủ kho biết. Màn Hộp yêu cầu bên kho
    vốn đã tự chọn được (`request.kho_id ?? initialKhoId`), nên để trống không kẹt ai.
    """

    kho_id: int | None = None
    ngay_can: date | None = None
    ghi_chu: str | None = None


class YeuCauKhoOut(BaseModel):
    id: int
    ma: str
    trang_thai: str


# --- Tab Nhân viên giao hàng -------------------------------------------------------------
class DriverOut(BaseModel):
    employee_id: int
    ho_ten: str
    trang_thai: str
    chuyen_dang_thuc_hien: str | None = None
    chuyen_ke_tiep: str | None = None
    #: Trong NGÀY đang xem — để điều độ ("hôm nay ai đang rảnh").
    so_chuyen_xong: int = 0
    tong_km: int = 0
    #: Trong THÁNG chứa ngày đang xem — để theo dõi định kỳ (chủ chốt 20/08/2026).
    so_chuyen_thang: int = 0
    tong_km_thang: int = 0


class DriverPage(BaseModel):
    items: list[DriverOut]


class TaiXeChonOut(BaseModel):
    """Danh sách tài xế CHỌN ĐƯỢC khi phân công.

    Có đường riêng vì `/api/employees` gác bằng ô `nhan_su`, mà Quản lý Giao hàng không nhất
    thiết có ô đó — bắt cấp thêm `nhan_su` chỉ để chọn tài xế là mở toang hồ sơ nhân sự cả công
    ty. Cùng lý do hệ đã làm roster riêng cho màn Đi muộn / về sớm.
    """

    id: int
    code: str | None = None
    full_name: str
    department: str | None = None
    # HAI câu hỏi KHÁC NHAU, cố ý tách — giao diện phải nói đúng việc người dùng cần làm:
    #   · chưa có TÀI KHOẢN  ⇒ đi cấp tài khoản (màn Người dùng);
    #   · có tài khoản nhưng chưa có ô THAO TÁC ⇒ đi tích ô (Vai trò → Giao hàng → Thao tác).
    # Gộp một cờ thì câu cảnh báo phải nói chung chung, mà nói chung chung thì người đọc không
    # biết đi đâu sửa (chủ chốt hỏi đúng chỗ này 20/08/2026).
    co_tai_khoan: bool = False
    # Có ô THAO TÁC chưa. Không có thì họ mở được màn, thấy chuyến của mình, nhưng KHÔNG bấm được
    # "Đã lấy hàng" / nhập kết quả — quản lý phải bấm hộ.
    co_thao_tac: bool = False


class TaiXeChonPage(BaseModel):
    items: list[TaiXeChonOut]


# --- Còn phải giao (dùng ở màn Đơn hàng bán) -----------------------------------------------
class ConPhaiGiaoLine(BaseModel):
    order_line_id: int
    mo_ta: str | None = None
    don_vi_tinh: str | None = None
    qty_dat: int
    da_giao: int
    con_phai_giao: int


class ConPhaiGiaoOut(BaseModel):
    order_id: int
    da_giao_du: bool
    lines: list[ConPhaiGiaoLine]


class DinhKemOut(BaseModel):
    """File minh chứng của chuyến giao (ảnh/PDF). `file_url` đọc qua `/api/files`."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    trip_id: int
    file_name: str
    file_url: str
    file_type: str | None = None
    uploaded_by: int | None = None
    uploaded_at: datetime


class DinhKemListOut(BaseModel):
    items: list[DinhKemOut] = []
