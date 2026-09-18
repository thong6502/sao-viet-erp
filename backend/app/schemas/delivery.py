"""Schemas — Giao hàng (docs/prd-giao-hang.md)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

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
    total: int = 0


# --- Lần giao ------------------------------------------------------------------------------
class PlanIn(BaseModel):
    request_id: int
    employee_id: int
    #: Phụ xe — TUỲ CHỌN, tối đa một người (mg 0231). Vai trò do Ô THẢ NGƯỜI VÀO quyết định, nên
    #: hai ô cùng lấy từ danh sách nhân viên khối Giao hàng; service chặn trùng người.
    phu_xe_employee_id: int | None = None
    #: Xe chạy chuyến — **BẮT BUỘC** khi danh mục Xe đã có xe và tài xế thuộc khối Giao hàng
    #: (chủ chốt 12/09/2026). Nullable ở schema chứ không ở luật: máy chủ chặn bằng `_doi_xe` để
    #: câu báo lỗi nói được LÝ DO, thay vì 422 "field required" trống trơn.
    vehicle_id: int | None = None
    gio_lay_hang: datetime
    gio_du_kien_giao: datetime
    kho_id: int | None = None
    ghi_chu_phan_cong: str | None = None
    #: LƯỢT XE (PRD khoán km §14): `"moi"` = lượt mới · id = ghép vào lượt đang mở của CÙNG xe ·
    #: bỏ trống = không vào lượt (đường cũ: một ô km cho cả chuyến).
    luot_xe_id: int | Literal["moi"] | None = None


class PlanUpdate(BaseModel):
    employee_id: int | None = None
    #: Gửi `null` = GỠ phụ xe; KHÔNG gửi = giữ nguyên. Router dùng `exclude_unset=True` nên hai
    #: trường hợp đó xuống service khác nhau (`None` vs mốc `_KHONG_GUI`).
    phu_xe_employee_id: int | None = None
    #: Gửi `null` = GỠ xe; KHÔNG gửi = giữ nguyên — cùng cơ chế `exclude_unset` như phụ xe.
    vehicle_id: int | None = None
    gio_lay_hang: datetime | None = None
    gio_du_kien_giao: datetime | None = None
    ghi_chu_phan_cong: str | None = None


class SoThucNhanIn(BaseModel):
    order_line_id: int
    qty: int = Field(ge=0)


class KetQuaIn(BaseModel):
    ket_qua: str
    # `ge=0`, KHÔNG phải `gt=0`: xe chưa lăn bánh mà khách không nghe máy thì 0 km là số THẬT.
    # Bỏ trống được từ 18/09/2026: chuyến trong LƯỢT XE không gõ km, gửi `so_dong_ho` — máy chủ
    # vẫn đòi km với chuyến ngoài lượt.
    km: int | None = Field(default=None, ge=0)
    #: Số đồng hồ lúc TỚI khách — chỉ cho chuyến trong lượt xe (PRD khoán km §14).
    so_dong_ho: int | None = Field(default=None, ge=0)
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
    #: Xe đã chạy chuyến — gửi để điền/đổi ngay lúc ghi kết quả. Chuyến khối Giao hàng mà cả
    #: đây lẫn chuyến đều trống thì máy chủ chặn (`_doi_xe_truoc_khi_chup`).
    vehicle_id: int | None = None


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
    phu_xe_employee_id: int | None = None
    phu_xe_name: str | None = None
    vehicle_id: int | None = None
    #: Biển số + tên xe để bảng chuyến đọc được ngay, khỏi tra danh mục cho từng dòng.
    xe_bien_so: str | None = None
    xe_ten: str | None = None
    gio_lay_hang: datetime
    gio_du_kien_giao: datetime
    ghi_chu_phan_cong: str | None = None
    trang_thai: str
    km: int | None = None
    #: TỔNG km cả các lần giao của yêu cầu (không phải km riêng lần này) — dùng cho tab
    #: "Đơn giao hàng" đã gộp theo yêu cầu. Mặc định = km của chính chuyến khi không truyền.
    tong_km: int = 0
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
    #: Lượt xe của chuyến (PRD khoán km §14). None = chuyến ngoài lượt (đường cũ, một ô km).
    luot: "LuotXeTrongChuyenOut | None" = None
    #: Cảnh báo KHÔNG chặn của thao tác vừa làm (vd "xe chạy ngoài sổ N km").
    canh_bao: list[str] = []


class LuotXeTrongChuyenOut(BaseModel):
    """Lượt xe nhìn từ MỘT chuyến — đủ để bảng chuyến biết hiện nút nào."""

    id: int
    code: str
    vehicle_id: int
    ngay: date
    so_diem: int
    so_dong_ho_xuat_phat: int | None = None
    so_dong_ho_ve_kho: int | None = None
    ve_kho_luc: datetime | None = None
    km_ve_kho: int | None = None
    #: Số đồng hồ lúc TỚI điểm của chính chuyến này (None = chưa nhập kết quả).
    so_dong_ho: int | None = None
    #: Số đồng hồ lớn nhất đã ghi trong lượt (hoặc số xuất phát) — hộp nhập kết quả / về kho nhắc.
    so_dong_ho_gan_nhat: int | None = None
    #: Gợi ý số lúc xuất phát = số cuối đã ghi của xe ở lượt khác. Chỉ có khi lượt chưa xuất phát.
    goi_y_xuat_phat: int | None = None
    #: Mọi điểm đã có kết quả, lượt chưa về kho ⇒ hiện nút "Về kho" (ở điểm cuối).
    cho_ve_kho: bool = False
    #: Chuyến này là điểm có số đồng hồ lớn nhất của lượt — nút "Về kho" đặt ở đây.
    la_diem_cuoi: bool = False


class LuotXeMoOut(BaseModel):
    """Một lượt CHƯA về kho của một xe — ô Lượt xe lúc lên đơn."""

    id: int
    code: str
    ngay: date
    so_diem: int
    tai_xe: str | None = None
    da_xuat_phat: bool = False


class LuotXeMoPage(BaseModel):
    items: list[LuotXeMoOut] = []


class BatDauGiaoIn(BaseModel):
    #: Chỉ chuyến ĐẦU của một lượt xe mới cần — số đồng hồ lúc xe rời kho.
    so_dong_ho_xuat_phat: int | None = Field(default=None, ge=0)


class VeKhoIn(BaseModel):
    so_dong_ho: int = Field(ge=0)
    xac_nhan_km_lon: bool = False


class VeKhoOut(BaseModel):
    id: int
    code: str
    so_dong_ho_ve_kho: int | None = None
    km_ve_kho: int | None = None
    ve_kho_luc: datetime | None = None
    canh_bao: list[str] = []


class LenLuotIn(BaseModel):
    """Lên đơn NHIỀU yêu cầu vào MỘT lượt xe một lần (chủ chốt 18/09/2026). Mỗi yêu cầu vẫn một
    chuyến, một phiếu xuất kho; tất cả hoặc không gì."""

    request_ids: list[int] = Field(min_length=1)
    employee_id: int
    phu_xe_employee_id: int | None = None
    #: Lượt là vòng chạy của MỘT chiếc xe ⇒ bắt buộc (service chặn để câu lỗi nói được lý do).
    vehicle_id: int | None = None
    gio_lay_hang: datetime
    gio_du_kien_giao: datetime
    ghi_chu_phan_cong: str | None = None
    #: `"moi"` = lượt mới · id = ghép vào lượt đang mở của cùng xe.
    luot_xe_id: int | Literal["moi"] = "moi"


class LenLuotOut(BaseModel):
    luot_id: int
    code: str
    trips: list[TripOut]
    canh_bao: list[str] = []


class LuotXeChiTietOut(BaseModel):
    """Cả lượt nhìn một chỗ — ngăn Lượt xe trên màn Giao hàng."""

    id: int
    code: str
    ngay: date
    vehicle_id: int
    xe_bien_so: str | None = None
    xe_ten: str | None = None
    so_dong_ho_xuat_phat: int | None = None
    so_dong_ho_ve_kho: int | None = None
    ve_kho_luc: datetime | None = None
    km_ve_kho: int | None = None
    goi_y_xuat_phat: int | None = None
    #: Số lớn nhất đã ghi trong lượt (hoặc số xuất phát) — xem trước chặng về kho.
    so_dong_ho_gan_nhat: int | None = None
    #: Mọi điểm đã có kết quả, lượt chưa về kho ⇒ bày nút "Về kho".
    cho_ve_kho: bool = False
    tong_km: int = 0
    #: Các điểm theo THỨ TỰ CHẶNG (số đồng hồ tăng dần; chưa có số thì xếp cuối).
    diem: list[TripOut] = []
    so_cho_gui_kho: int = 0
    so_cho_lay_hang: int = 0
    so_cho_bat_dau: int = 0
    so_dang_giao: int = 0


class BangGiaoItem(BaseModel):
    """Một KHỐI của tab Đơn giao hàng: đúng MỘT trong hai ô có giá trị."""

    luot: LuotXeChiTietOut | None = None
    trip: TripOut | None = None


class BangGiaoPage(BaseModel):
    items: list[BangGiaoItem]
    #: Tổng số KHỐI (lượt + chuyến lẻ) — để phân trang.
    total: int
    #: Tổng số ĐƠN giao (chuyến) — số đếm trên tab / đầu trang, như trước.
    so_don: int


class GuiXuatKhoCaLuotIn(BaseModel):
    ghi_chu: str | None = None


class CaLuotOut(BaseModel):
    """Kết quả một thao tác cả lượt: bao nhiêu chuyến vừa đi tiếp + cảnh báo không chặn."""

    so_chuyen: int
    phieu: list[str] = []
    canh_bao: list[str] = []


class TripPage(BaseModel):
    items: list[TripOut]
    total: int = 0


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


# --- Bậc đơn giá khoán km (bảng bậc của một MỨC) -------------------------------------------
class KmBracketIn(BaseModel):
    """Một bậc. `up_to_km=None` = bậc cao nhất (từ đó trở lên) — CHỈ được có một, và ở CUỐI."""

    up_to_km: int | None = Field(default=None, gt=0)
    don_gia: float = Field(ge=0)


class KmBracketOut(BaseModel):
    up_to_km: int | None = None
    don_gia: float = 0


# --- MỨC khoán km (PRD §11) -------------------------------------------------------------------
class MucKmIn(BaseModel):
    """Tạo / sửa một MỨC. Tên là khoá người dùng đọc ("Xe 2 tấn") nên không được trùng."""
    ten: str = Field(min_length=1, max_length=150)
    ghi_chu: str | None = None
    active: bool = True


class MucKmSua(BaseModel):
    """Sửa một MỨC — mọi ô TUỲ CHỌN, KHÔNG gửi = giữ nguyên (router đọc `exclude_unset`).

    Tách khỏi `MucKmIn` (14/09/2026): dùng chung thì màn đổi tên chỉ gửi `{ten}` mà pydantic điền
    mặc định `ghi_chu=None` + `active=True` rồi GHI ĐÈ — đổi tên là mất ghi chú, mức đang tắt tự
    bật lại.
    """
    ten: str | None = Field(default=None, min_length=1, max_length=150)
    ghi_chu: str | None = None
    active: bool | None = None


class MucKmBracketsIn(BaseModel):
    """Danh sách RỖNG = xoá trắng bảng giá — chỉ được khi mức không còn xe nào ăn."""
    items: list[KmBracketIn] = Field(default_factory=list)


class MucKmOut(BaseModel):
    id: int
    #: Luôn RỖNG — mức chỉ có TÊN. Khoá vẫn phải có: ô chọn dùng chung của nền danh mục vẽ
    #: "ma · ten" (tự giấu phần mã khi rỗng), thiếu khoá thì menu hiện "undefined · Xe 5 tấn".
    ma: str = ""
    ten: str
    ghi_chu: str | None = None
    active: bool
    items: list[KmBracketOut]
    #: SỐ XE đang ăn mức này — màn cấu hình phải nói trước khi người ta sửa giá: sửa một mức là
    #: đổi tiền của cả nhóm xe, khác hẳn sửa bảng giá của riêng một chiếc.
    so_xe: int


class MucKmListOut(BaseModel):
    items: list[MucKmOut]


# --- % chia tiền một chuyến cho kíp xe -------------------------------------------------------
# Tách khỏi endpoint bảng bậc cấp phòng khi bảng đó GỠ (12/09/2026). Hai ô này vẫn là luật thật:
# tiền một chuyến chia cho tài xế và phụ xe; đi một mình thì tài xế ăn trọn.
class KhoanKmPctIn(BaseModel):
    pct_tai_xe: float = Field(ge=0, le=100)
    pct_phu_xe: float = Field(ge=0, le=100)


class KhoanKmPctOut(BaseModel):
    pct_tai_xe: float
    pct_phu_xe: float


# `TripOut.luot` trỏ tới lớp khai SAU nó — dựng lại để pydantic nối đúng kiểu.
TripOut.model_rebuild()
