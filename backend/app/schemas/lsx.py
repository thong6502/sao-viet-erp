"""Pydantic schemas — Lệnh sản xuất (LSX).

3 nhóm: (a) HÀNG CHỜ = đơn Sale đã chuyển xuống SX còn dòng chưa lên lệnh; (b) PREVIEW = danh sách
lệnh DỰ KIẾN dẫn xuất tại chỗ từ dòng đơn + phiếu tính giá (chưa ghi DB); (c) LSX = lệnh đã tạo
(kèm routing + checklist thiếu).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ============================ Hàng chờ ============================
class HangChoItem(BaseModel):
    order_id: int
    order_no: str
    customer_name: str | None = None
    sale_name: str | None = None
    delivery_committed_date: date | None = None
    is_rush: bool = False
    production_note: str | None = None
    san_xuat_released_at: datetime | None = None
    so_dong: int = 0        # tổng dòng đơn
    so_dong_co_lsx: int = 0  # dòng đã lên lệnh


class HangChoOut(BaseModel):
    items: list[HangChoItem]
    total: int          # TỔNG số đơn còn nợ lệnh, không phải số dòng của trang
    page: int = 1
    size: int = 50


# ============================ Preview (lệnh dự kiến) ============================
class PreviewRouting(BaseModel):
    thu_tu: int
    ten: str
    nhom: str | None = None
    # Cùng bộ mã với `LsxCongDoanOut.loai_buoc` — THAY cờ `thue_ngoai` cũ để màn "lệnh dự kiến"
    # và màn lệnh đã tạo hiển thị giống nhau (`thue_ngoai` chỉ là một giá trị của trường này).
    loai_buoc: str = "may"
    department_id: int | None = None
    department_ten: str | None = None
    nha_cung_cap: str | None = None


class PreviewLine(BaseModel):
    order_line_id: int
    ten: str
    so_luong_dat: int
    don_vi_tinh: str
    phieu_thanh_phan_id: int | None = None
    ptg_ma: str | None = None
    # Nhãn nhóm (ruột + bìa của 1 cuốn) — CHỈ để gom hiển thị cho dễ đọc. Sản xuất vẫn tạo
    # 1 LỆNH cho MỖI dòng: ruột và bìa chạy máy khác nhau, không gộp được.
    nhom: str | None = None
    # Số của engine chạy lại theo SL của ĐƠN (không lấy số lúc tính giá).
    # None = CHƯA tính được (dòng chưa có bài tính giá) → UI hiện "—", KHÔNG bày số 0 giả.
    bu_hao_to: int | None = None
    so_to_ke_hoach: int | None = None
    so_to_nguyen: int | None = None
    so_con: int | None = None
    so_kem: int | None = None
    so_luot: int | None = None
    # MÃ đơn vị từng chặng dòng giấy của DÒNG NÀY (`don_vi_chuoi`). Bảng hàng chờ xếp nhiều dòng
    # đơn cạnh nhau, mỗi dòng có thể đếm bằng đơn vị khác — nên đơn vị đi theo dòng, không nằm ở
    # tiêu đề cột. Gửi MÃ, client tra tên trong danh mục Đơn vị. None = routing không nói tới chặng
    # đó (vd không có bước xả giấy) ⇒ client dùng nhãn mặc định.
    don_vi_to: str | None = None
    don_vi_to_nguyen: str | None = None
    don_vi_tp: str | None = None
    don_vi_tay: str | None = None
    routing: list[PreviewRouting] = Field(default_factory=list)
    quy_cach: dict | None = None
    thieu: list[str] = Field(default_factory=list)
    # SL lúc tính giá khác SL đơn → cảnh báo mềm (vẫn lấy số của đơn).
    sl_ptg: int | None = None
    # Đã tạo lệnh rồi → khoá dòng.
    lsx_id: int | None = None
    lsx_ma: str | None = None


class PreviewOut(BaseModel):
    order_id: int
    order_no: str
    customer_name: str | None = None
    sale_name: str | None = None
    delivery_committed_date: date | None = None
    is_rush: bool = False
    production_note: str | None = None
    lines: list[PreviewLine]
    warnings: list[str] = Field(default_factory=list)


class TaoLsxIn(BaseModel):
    order_line_ids: list[int] = Field(default_factory=list)


# ============================ LSX ============================
class LeadTimeOut(BaseModel):
    """Tổng thời gian dẫn của cả lệnh — DẪN XUẤT, không lưu cột."""

    tong_phut: float = 0
    chiem_may_phut: float = 0     # phần ĂN capacity máy/tổ (không gồm chờ, di chuyển)
    so_ngay: float = 0            # quy ước 8h/ngày, CHƯA trừ nghỉ lễ/ca kíp
    ngay_du_kien_xong: date | None = None
    ngay_con_lai: int | None = None   # tới `han_giao_khach`; âm = đã trễ


class LsxBuocVatTuIn(BaseModel):
    vat_tu_id: int
    so_luong: float = Field(gt=0)
    # True = dòng MÁY bung khi chọn công việc khoán ⇒ lần bung sau thay được. False = người tự thêm
    # hoặc đã sửa số ⇒ máy chừa ra. Mặc định False: client cũ không gửi thì coi như người khai.
    tu_dong: bool = False


class LsxBuocVatTuOut(BaseModel):
    id: int
    vat_tu_id: int
    vat_tu_ma: str
    vat_tu_ten: str
    don_vi: str
    so_luong: float
    tu_dong: bool = False


class KhuonMoiIn(BaseModel):
    """Nhánh "làm dao mới" ở bước lệnh. KHÔNG có `khach_hang_id` — server lấy từ chính lệnh."""

    ten: str = Field(min_length=1, max_length=200)
    loai: str | None = None
    #: Ngày cần có dao. Service của danh mục Khuôn bắt buộc trường này khi `dang_dat_lam`.
    ngay_ve_du_kien: date


class PhuThuocOption(BaseModel):
    lsx_id: int
    lsx_ma: str
    nhom: str | None = None
    step_key: str
    ten_buoc: str
    thu_tu: int


class LsxCongDoanIn(BaseModel):
    """Một dòng routing client gửi lên để upsert tại chỗ theo ``step_key``."""

    thu_tu: int | None = None
    step_key: str | None = None
    cong_doan_id: int | None = None
    ten: str | None = None
    nhom: str | None = None
    loai_buoc: str | None = None
    bat_buoc: bool | None = None
    # Tiêu chí KCS BỔ SUNG riêng cho lệnh này (Task 3) — không sửa được checklist danh mục ở đây,
    # chỉ thêm/bớt vài dòng chỉ áp cho lệnh này. `[]` để XOÁ SẠCH (không gửi field = giữ nguyên).
    kcs_tieu_chi_bo_sung_json: list | None = None
    department_id: int | None = None
    may_id: int | None = None
    #: Con dao của bước (`khuon_be.id`). Gửi null = bỏ gán.
    khuon_be_id: int | None = None

    # Đầu việc khoán của bước (`piece_rates.id`) — 0/null = bỏ chọn. KHÔNG gửi field này = giữ mặc
    # định theo tổ + công đoạn (server tự điền), đừng gửi null "cho chắc" kẻo xoá mất đầu việc.
    piece_rate_id: int | None = None
    # Số lượng & hao hụt
    so_luong_vao: float | None = None
    so_luong_ra: float | None = None
    don_vi_vao: str | None = None
    don_vi_ra: str | None = None
    he_so_quy_doi: float | None = Field(default=None, gt=0)
    hao_hut: float | None = Field(default=None, ge=0)
    hao_hut_pct: float | None = Field(default=None, ge=0)
    so_luot_chay: int | None = Field(default=None, ge=1)
    # Năng suất & thời gian (phút)
    so_nhan_cong: int | None = Field(default=None, ge=1)
    # Ba mốc nhân lực KẾ THỪA từ định mức đầu việc nhưng SỬA ĐƯỢC tại bước — mỗi lệnh một hoàn
    # cảnh (tổ mượn người, việc gấp). Không gửi = giữ số đang có / để server điền từ định mức.
    so_nhan_cong_toi_thieu: int | None = Field(default=None, ge=1)
    so_nhan_cong_tieu_chuan: int | None = Field(default=None, ge=1)
    so_nhan_cong_toi_da: int | None = Field(default=None, ge=1)
    # Hai ô gõ được ở tab Thời gian. `setup_phut` · `nang_suat` · `chay_phut` · `di_chuyen_phut`
    # vẫn BỎ khỏi input: chuẩn bị + tốc độ kế thừa SỐNG từ module Máy, người kế hoạch không sửa
    # tại bước.
    phat_sinh_phut: float | None = Field(default=None, ge=0)
    # Gia công ngoài (§8)
    nha_cung_cap: str | None = None
    sl_gui: float | None = Field(default=None, ge=0)
    ngay_gui_dk: date | None = None
    van_chuyen_ngay: float | None = Field(default=None, ge=0)
    gia_cong_ngay: float | None = Field(default=None, ge=0)
    ngay_nhan_dk: date | None = None
    hao_hut_cho_phep: float | None = Field(default=None, ge=0)
    don_gia_gia_cong: float | None = Field(default=None, ge=0)
    yeu_cau_ky_thuat: str | None = None
    # Người giao / người nhận + số thực KHÔNG nhận ở đây: đó là THỰC THI, ghi qua
    # `POST /api/lsx/{id}/buoc/{buoc_id}/giao-nhan`. Lưu routing bị chặn khi lệnh đã lập kế
    # hoạch, mà hàng ra cổng đúng lúc lệnh đang chạy.
    ghi_chu: str | None = None
    phu_thuoc_step_keys: list[str] | None = None
    vat_tus: list[LsxBuocVatTuIn] | None = None


class LsxCongDoanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    step_key: str
    thu_tu: int
    cong_doan_id: int | None = None
    ten: str
    nhom: str | None = None
    loai_buoc: str
    bat_buoc: bool = True
    # KCS kiêm nhiệm — suy TỰ ĐỘNG (không còn khai tay): bước này có phải bước cuối của routing +
    # tổ thực hiện có `Department.is_kcs=true` không (xem `lsx_service._cong_doan_dict`). FE dùng
    # để ẩn/hiện khối "Tiêu chí KCS bổ sung" trong drawer bước. ⚠️ Thêm field vào schema THÔI CHƯA
    # ĐỦ — `LsxCongDoanOut` được dựng bằng dict thủ công ở `lsx_service._cong_doan_dict()`, không
    # phải `from_attributes` tự động; PHẢI copy hai khoá này vào dict đó (đúng bẫy "Pydantic nuốt
    # field im lặng").
    la_kcs: bool = False
    kcs_tieu_chi_bo_sung_json: list | None = None
    department_id: int | None = None
    department_ten: str | None = None
    may_id: int | None = None
    may_ten: str | None = None
    # Hai CỜ đọc từ danh mục Công đoạn — quyết định bước có hỏi khuôn không, và `tooling_type` là
    # chiều lọc thứ hai của ô chọn dao. Bốn field `khuon_be_*` là ẢNH CHỤP để bày cho thợ (mã · tên
    # · SỐ KỆ · tình trạng · ngày về), server ghép sẵn nên màn khỏi tra danh mục Khuôn.
    requires_tooling: bool = False
    tooling_type: str | None = None
    khuon_be_id: int | None = None
    khuon_be_ma: str | None = None
    khuon_be_ten: str | None = None
    khuon_be_so_ke: str | None = None
    khuon_be_tinh_trang: str | None = None
    khuon_be_ngay_ve: date | None = None
    # Ý ĐỊNH của sale chép từ phiếu tính giá + chỗ lệch với con dao kế hoạch đã chốt. `khuon_lech`
    # là câu tiếng Việt server dựng sẵn (hoặc None) — mọi màn nói cùng một câu, FE không suy lại.
    khuon_nguon: str | None = None
    khuon_phi: float = 0
    khuon_lech: str | None = None

    so_luong_vao: float
    so_luong_ra: float
    # NULL = bước KHÔNG CHẠM GIẤY (chế bản đếm kẽm) → đứng ngoài chuỗi tính ngược. Khai `str`
    # cứng thì mọi lần mở chi tiết lệnh có bước chế bản là 500.
    don_vi_vao: str | None = None
    don_vi_ra: str | None = None
    # Bước có nằm trên DÒNG GIẤY không — quyết định bởi CỜ TRẠM của danh mục Đơn vị, FE không tự
    # suy được từ mã. Sai/thiếu field này thì màn hiện hai số 0 (số lượng + hao) mà không nói vì sao.
    tren_dong_giay: bool = True
    # Câu lỗi khi bước NGOÀI dòng thiếu cầu quy đổi giữa hai đơn vị (`bài in → bản kẽm`) ở module
    # Đơn vị & quy đổi. None = không lỗi. Drawer bày đỏ + số vào để 0 cho tới khi người khai cầu.
    loi_quy_doi: str | None = None
    # Diễn giải công thức SỐ RA cho bước ngoài dòng ("Số bản kẽm = 5 bản kẽm"). None với bước
    # trên dòng giấy (số suy ngược theo chuỗi, không có công thức riêng).
    san_luong_dien_giai: str | None = None
    he_so_quy_doi: float
    hao_hut: float
    hao_hut_pct: float
    ty_le_hao_hut: float = 0      # derived = hao_hut / so_luong_vao
    so_luot_chay: int = 1

    so_nhan_cong: int = 1
    so_nhan_cong_toi_thieu: int | None = None
    so_nhan_cong_tieu_chuan: int = 1
    so_nhan_cong_toi_da: int | None = None
    # `setup_phut` KẾ THỪA từ máy (read-only trên UI); `phat_sinh_phut` là ô người gõ.
    setup_phut: float = 0
    phat_sinh_phut: float = 0
    # CHỜ KỸ THUẬT (mực khô · keo đông · màng nguội) — kế thừa từ danh mục Công đoạn theo cặp
    # (công đoạn × loại SP), SỬA ĐÈ được tại bước. Vào `tong_phut` nhưng KHÔNG vào `chiem_may_phut`:
    # tờ nằm trên pallet chờ khô thì máy vẫn chạy job khác.
    nang_suat: float | None = None
    don_vi_nang_suat: str | None = None
    chay_phut: float | None = None      # dẫn xuất: SL vào × 60 ÷ tốc độ máy × số lượt
    # derived — thời lượng theo tốc độ TRUNG BÌNH (Gantt đặt thanh), kèm dải nhanh/chậm nhất
    # suy từ tốc độ tối đa / tối thiểu của máy. Máy chưa khai dải ⇒ cả ba bằng nhau.
    chiem_may_phut: float = 0
    chiem_may_phut_min: float = 0
    chiem_may_phut_max: float = 0
    tong_phut: float = 0
    thoi_luong_dien_giai: dict = Field(default_factory=dict)

    nha_cung_cap: str | None = None
    sl_gui: float | None = None
    ngay_gui_dk: date | None = None
    van_chuyen_ngay: float | None = None
    gia_cong_ngay: float | None = None
    ngay_nhan_dk: date | None = None
    hao_hut_cho_phep: float | None = None
    don_gia_gia_cong: float | None = None
    yeu_cau_ky_thuat: str | None = None
    # --- Gia công ngoài: sổ THỰC TẾ + dẫn xuất đọc từ nó ---------------------------
    nguoi_giao_id: int | None = None
    nguoi_giao_ten: str | None = None
    giao_luc: datetime | None = None
    sl_giao_thuc: float | None = None
    nguoi_nhan_id: int | None = None
    nguoi_nhan_ten: str | None = None
    nhan_luc: datetime | None = None
    sl_nhan_thuc: float | None = None
    # DẪN XUẤT (tính lúc đọc, không lưu cột)
    giao_nhan_trang_thai: str | None = None   # chua_gui | dang_ngoai | da_ve
    so_hut: float | None = None               # giao − nhận
    hut_vuot_dinh_muc: bool = False
    tien_gia_cong_thuc: float | None = None
    qua_han_ngay: int | None = None           # >0 = quá hạn nhận, chỉ khi chưa nhận
    ghi_chu: str | None = None

    # --- Khoán theo đầu việc ---------------------------------------------------
    # GHIM (snapshot lúc chọn, xưởng lên giá sau không xê dịch lệnh đã phát):
    khoan_rate_id: int | None = None
    khoan_ten: str | None = None
    khoan_don_vi: str | None = None
    khoan_don_gia: float | None = None
    # Các đầu việc CHỌN ĐƯỢC cho bước (theo tổ + công đoạn) — nuôi dropdown ở drawer.
    khoan_chon_duoc: list[dict] = Field(default_factory=list)
    # `[{vat_tu_id, so_luong, dien_giai}]` — lượng tính sẵn cho MỌI vật tư theo bước này. Drawer
    # chọn món nào là điền số ngay, khỏi bắt gõ tay. Món chưa tính ra được thì KHÔNG có ở đây.
    vat_tu_goi_y: list[dict] = Field(default_factory=list)
    # Số ĐÚNG RA phải là theo danh mục HIỆN TẠI, khi nó KHÁC số đã lưu (None = không lệch).
    # Lệnh là ẢNH CHỤP nên server không tự đè — chỉ phơi ra để màn gạch số cũ + mời "Tính lại".
    so_luong_vao_moi: float | None = None
    so_luong_ra_moi: float | None = None
    # DẪN XUẤT (tính lúc đọc, không lưu): SL đã quy đổi · tiền dự kiến · diễn giải cách tính.
    khoan_sl: float | None = None
    khoan_don_vi_sl: str | None = None
    khoan_tien: float | None = None
    khoan_dien_giai: str | None = None
    # Không quy đổi được thì nói THIẾU GÌ, không đoán số.
    khoan_thieu: list[str] = Field(default_factory=list)
    khoan_ly_do: str | None = None
    phu_thuoc_step_keys: list[str] = Field(default_factory=list)
    vat_tus: list[LsxBuocVatTuOut] = Field(default_factory=list)


class LsxGiaoNhanIn(BaseModel):
    """Ghi nhận MỘT sự kiện thực tế của bước thuê ngoài: giao hàng đi, hoặc nhận hàng về.

    Đi qua cửa THỰC THI riêng, KHÔNG qua lưu routing — xem `LsxBuocIn`. `nguoi_id` để trống thì
    server lấy người đang đăng nhập; `luc` để trống thì lấy thời điểm ghi.
    """

    su_kien: Literal["giao", "nhan"]
    nguoi_id: int | None = None
    luc: datetime | None = None
    so_luong: float | None = Field(default=None, ge=0)


class LsxListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ma: str
    loai: str
    ten: str
    # Nhãn nhóm đọc-sống từ dòng đơn: lệnh "Bìa" phải cho biết nó thuộc "Catalogue A4 - 32 trang".
    nhom: str | None = None
    trang_thai: str
    order_id: int
    order_no: str | None = None
    customer_name: str | None = None
    so_luong_dat: int
    don_vi_tinh: str
    so_to_ke_hoach: int
    han_giao_khach: date | None = None
    han_hoan_thanh_sx: date | None = None
    is_rush: bool = False
    to_dau_ten: str | None = None   # tổ của bước đầu (nhìn biết ai bắt việc)
    so_cong_doan: int = 0
    # MÃ đơn vị chặng TỜ IN của lệnh này — cột "Tờ in" liệt kê nhiều lệnh, mỗi lệnh có thể đếm
    # bằng đơn vị xưởng tự đặt. Client tra tên ở danh mục Đơn vị.
    don_vi_to: str | None = None


class LsxListOut(BaseModel):
    items: list[LsxListItem]
    total: int          # TỔNG số lệnh khớp lọc, không phải số dòng của trang
    page: int = 1
    size: int = 50
    # Số trên từng tab lọc, đếm ở máy chủ theo cùng bộ lọc TRỪ `trang_thai` (tab đang không được
    # chọn vẫn khoe số của nó). Khoá `all` = tổng. Không khai ở đây là Pydantic nuốt im lặng.
    facets: dict[str, int] = {}


class BoDauViecOut(BaseModel):
    """Một bước bị GỠ đầu việc mồ côi khi lưu routing (đầu việc đã ghim không còn thuộc công đoạn
    ∩ tổ — thường vì danh mục đổi dưới chân lệnh). KHÔNG chặn lưu; báo để mở bước chọn lại."""

    vi_tri: int          # số thứ tự bước trong routing (1-based) để người kế hoạch mở đúng chỗ
    ten: str             # tên công đoạn của bước
    dau_viec: str        # tên đầu việc đã bị gỡ


class LsxOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ma: str
    loai: str
    lsx_goc_id: int | None = None
    ten: str
    # Nhãn nhóm ĐỌC SỐNG từ dòng đơn (không lấy trong quy_cach_json — ảnh chụp cũ sẽ trống).
    nhom: str | None = None
    trang_thai: str

    order_id: int
    order_line_id: int
    order_no: str | None = None
    # Trạng thái ĐƠN (không phải trang_thai của lệnh) — client dùng để ẩn tab Công đoạn khi đơn
    # đã hủy, xem `_EXCLUDED_ORDER_STATUSES` bên customer_analytics.py cho quy ước cùng gốc.
    order_status: str | None = None
    customer_name: str | None = None
    customer_po_no: str | None = None
    sale_name: str | None = None
    quote_version_id: int | None = None
    quote_number: str | None = None
    quote_version_number: int | None = None
    phieu_thanh_phan_id: int | None = None
    ptg_id: int | None = None
    ptg_ma: str | None = None

    so_luong_dat: int
    don_vi_tinh: str
    so_to_ke_hoach: int
    so_to_nguyen: int
    so_con: int
    # MÃ đơn vị bốn CHẶNG dòng giấy của lệnh này (`dong_giay.don_vi_chuoi`). Server chấm MỘT chỗ
    # rồi gửi cho cả ba màn; client chỉ tra TÊN trong danh mục Đơn vị. None = routing không nói tới
    # chặng đó — client hiện mỗi con số, KHÔNG bịa nhãn.
    don_vi_to: str | None = None
    don_vi_to_nguyen: str | None = None
    don_vi_tp: str | None = None
    don_vi_tay: str | None = None

    ban_giao_at: datetime | None = None
    han_giao_khach: date | None = None
    han_hoan_thanh_sx: date | None = None
    is_rush: bool

    quy_cach_json: dict | None = None
    may_id: int | None = None
    may_ten: str | None = None

    nguoi_phu_trach_id: int | None = None
    nguoi_phu_trach_ten: str | None = None
    ghi_chu: str | None = None
    # "Lưu ý sản xuất (gửi xưởng)" đọc SỐNG từ đơn — nguồn ô lưu ý thợ thấy trên lệnh.
    luu_y_gui_xuong: str | None = None
    created_at: datetime
    updated_at: datetime

    cong_doans: list[LsxCongDoanOut] = Field(default_factory=list)
    # `thieu` CHẶN nút "Sẵn sàng lập kế hoạch" (§12). Rổ cảnh báo MỀM §14 (`canh_bao`) đã gỡ
    # 25/08/2026 — server vẫn tính mỗi lần mở lệnh mà không màn nào đọc.
    thieu: list[str] = Field(default_factory=list)
    lead_time: LeadTimeOut | None = None
    # Công thợ khoán DỰ KIẾN cả lệnh = Σ bước quy đổi được. Là số SÀN: bước chưa chọn đầu việc hoặc
    # thiếu số để quy đổi thì không góp vào — đừng đọc như tổng chi phí nhân công thật.
    khoan_tien_tong: float = 0
    # Chừa TÁCH CHIỀU, tính lúc đọc bằng `chua_theo_chieu` — màn lệnh chỉ hiện, không cộng lại.
    chua_dai: float = 0
    chua_rong: float = 0
    # Lệnh đang ghép chung tờ với ai. None = in riêng. Khi có, THÔNG SỐ TỜ (máy in, giấy, khổ tờ
    # in, số con) đọc theo bài — sửa ở màn lệnh không có tác dụng.
    bai_ghep: LsxBaiGhepOut | None = None
    # Bước bị GỠ đầu việc mồ côi trong LẦN LƯU routing này (rỗng ở mọi cửa đọc khác). Non-blocking:
    # lưu vẫn thành công, FE bày lưu ý để người kế hoạch mở đúng bước chọn lại đầu việc.
    bo_dau_viec: list[BoDauViecOut] = Field(default_factory=list)


class BuocBiDeOut(BaseModel):
    """Một bước của lệnh đang bị bài ghép ĐÈ — số ở đây là của CẢ LƯỢT chung, không phải của lệnh."""

    gop_step_key: str
    ten: str
    to_ten: str | None = None
    may_ten: str | None = None
    so_luong_vao: float = 0
    so_luong_ra: float = 0
    hao_hut: float = 0


class LsxBaiGhepOut(BaseModel):
    id: int
    ma: str
    trang_thai: str
    may_id: int | None = None
    may_ten: str | None = None
    giay_id: int | None = None
    kho_in_dai: int | None = None
    kho_in_rong: int | None = None
    so_con_tren_to: int = 1
    # `lsx_step_key → bước chung đang đè lên nó`. Thay `buoc_in_step_key` (giả định bước in là điểm
    # gộp duy nhất — sai, bài còn gộp CTP/cán/bế). Quên sửa model này một lần rồi: service trả
    # `buoc_bi_de` mà pydantic lọc mất, badge + hai số phía lệnh thành code chết mà không ai báo.
    buoc_bi_de: dict[str, BuocBiDeOut] = Field(default_factory=dict)


class LsxQuyCachIn(BaseModel):
    """THÔNG SỐ của lệnh mà kế hoạch sửa được tại chỗ — snapshot vẫn là snapshot.

    Lệnh KHÔNG tự bám theo phiếu tính giá; đây chỉ là mở khoá cho người kế hoạch chỉnh ảnh chụp
    mà không phải quay về phiếu rồi tạo lại lệnh (tạo lại là mất sạch routing đã chỉnh).

    Chỉ NGUYÊN NHÂN nằm ở đây. HỆ QUẢ (`so_kem` · `so_luot` · `so_manh_xa` · `so_to_ke_hoach` ·
    `so_to_nguyen`) server tính lại từ đúng bộ này, client gửi lên cũng bị bỏ — xem
    `LsxService.ap_quy_cach`.
    """

    giay_id: int | None = None
    nguon_giay: str | None = None
    kho_nguyen_dai: float | None = Field(default=None, ge=0)
    kho_nguyen_rong: float | None = Field(default=None, ge=0)
    kho_in_dai: float | None = Field(default=None, ge=0)
    kho_in_rong: float | None = Field(default=None, ge=0)
    dai_thanh_pham: float | None = Field(default=None, ge=0)
    rong_thanh_pham: float | None = Field(default=None, ge=0)
    quy_cach_in: str | None = None
    muc_a: list[str] | None = None
    muc_b: list[str] | None = None
    so_trang: int | None = Field(default=None, ge=1)
    trang_moi_tay: int | None = Field(default=None, ge=1)
    bleed_mm: float | None = Field(default=None, ge=0)
    khe_cat_mm: float | None = Field(default=None, ge=0)
    con_auto: bool | None = None


class LsxUpdateIn(BaseModel):
    ten: str | None = None
    so_luong_dat: int | None = Field(default=None, ge=0)
    don_vi_tinh: str | None = None
    # Cụm THÔNG SỐ (ảnh chụp từ phiếu) — sửa cái nào là mọi số dẫn xuất tính lại ngay.
    quy_cach: LsxQuyCachIn | None = None
    so_to_ke_hoach: int | None = Field(default=None, ge=0)
    so_to_nguyen: int | None = Field(default=None, ge=0)
    so_con: int | None = Field(default=None, ge=1)
    han_hoan_thanh_sx: date | None = None
    is_rush: bool | None = None
    may_id: int | None = None
    nguoi_phu_trach_id: int | None = None
    ghi_chu: str | None = None


class RoutingReplaceIn(BaseModel):
    cong_doans: list[LsxCongDoanIn] = Field(default_factory=list)
    # §10: routing lệch bài tính giá → ghi lý do vào nhật ký (người xác nhận đã có ở audit).
    ly_do: str | None = None


class XemTruocRoutingRow(BaseModel):
    """1 bước trong payload XEM TRƯỚC routing — các trường chuỗi ngược cần để suy số.

    KHÔNG mang vật tư / khoán / phụ thuộc (những thứ chỉ ảnh hưởng lúc LƯU, không đổi dòng chảy số
    lượng — số lượng chạy theo `thu_tu`, không theo cạnh phụ thuộc), để payload gọn và không lỡ
    chạm guard vật-tư/phụ-thuộc của `replace_routing`. Muốn bước chèn giữa ra đúng số thì đưa nó về
    đúng vị trí `thu_tu` (chèn đúng chỗ ở FE), không phải khai cạnh phụ thuộc cho xem-trước.
    """

    step_key: str | None = None
    thu_tu: int | None = None
    cong_doan_id: int | None = None
    ten: str | None = None
    nhom: str | None = None
    loai_buoc: str | None = None
    department_id: int | None = None
    may_id: int | None = None


class XemTruocRoutingIn(BaseModel):
    cong_doans: list[XemTruocRoutingRow] = Field(default_factory=list)


class XemTruocRoutingBuoc(BaseModel):
    """DÒNG CHẢY của 1 bước sau khi đổi/chèn công đoạn — khớp field `_cong_doan_dict` trả ra."""

    step_key: str | None = None
    so_luong_vao: float
    so_luong_ra: float
    don_vi_vao: str | None = None
    don_vi_ra: str | None = None
    he_so_quy_doi: float
    hao_hut: float
    hao_hut_pct: float
    tren_dong_giay: bool = True
    loi_quy_doi: str | None = None
    san_luong_dien_giai: str | None = None


class XemTruocRoutingOut(BaseModel):
    cong_doans: list[XemTruocRoutingBuoc] = Field(default_factory=list)


class TinhNguocRow(BaseModel):
    """1 dòng GỢI Ý của phép tính ngược — chưa ghi DB, người kế hoạch xem rồi mới bấm áp dụng."""

    id: int
    thu_tu: int
    ten: str
    so_luong_vao: float
    so_luong_ra: float
    don_vi_vao: str | None = None
    don_vi_ra: str | None = None


class TinhNguocOut(BaseModel):
    rows: list[TinhNguocRow] = Field(default_factory=list)
    # Số tờ bài tính giá chốt — để người dùng thấy ngay routing đang lệch báo giá bao nhiêu.
    so_to_ke_hoach: int = 0


class BuocMacDinhOut(BaseModel):
    """Bộ mặc định khi ĐỔI một bước sang công đoạn khác — client áp đè lên dòng đang sửa.

    KHÔNG có số lượng vào/ra: chúng thuộc CHUỖI chứ không thuộc công đoạn, nên giữ nguyên số người
    kế hoạch đang cân (lệch thì đã có cảnh báo `dut_chuyen` + nút "Tính ngược").
    """

    cong_doan_id: int
    ten: str
    nhom: str | None = None
    loai_buoc: str
    department_id: int | None = None
    may_id: int | None = None
    don_vi_vao: str | None = None
    don_vi_ra: str | None = None
    he_so_quy_doi: float
    #: Cặp đơn vị trên có nằm trên DÒNG GIẤY không. Đi kèm hai ô trên vì client áp cả cụm một lượt;
    #: thiếu nó thì dòng vừa đổi sang ghi kẽm (`m² → bài in`) vẫn đeo cờ của công đoạn cũ.
    tren_dong_giay: bool = True
    setup_phut: float
    nang_suat: float | None = None
    don_vi_nang_suat: str | None = None
    so_nhan_cong: int = 1
    so_nhan_cong_tieu_chuan: int = 1
    so_nhan_cong_toi_da: int | None = None


class TrangThaiIn(BaseModel):
    trang_thai: str


class LsxActivityItem(BaseModel):
    at: datetime
    actor_name: str | None = None
    action: str
    detail: str


class LsxActivityOut(BaseModel):
    items: list[LsxActivityItem]


# --- Hàng đèn tổng quan (Đợt 1 redesign 18/08/2026) ---------------------------
class DenItem(BaseModel):
    """Một chấm trên hàng đèn của bảng lệnh.

    `muc` ∈ `do` · `vang` · `ok` — FE **chỉ vẽ chấm cho `do`/`vang`**, `ok` để trống ô.
    `chu` là câu người dùng đọc được (tooltip + bản đủ chữ ở màn chi tiết).
    `nhay` = `{man, id}` để bấm chấm là tới thẳng chỗ sửa, không phải tự đi tìm màn.
    """
    muc: str
    chu: str = ""
    nhay: dict | None = None


class LsxDenOut(BaseModel):
    """Ba thứ bảng lệnh CHƯA nói. Hạn và Định mức cố ý KHÔNG có đèn — cột `Hạn` đã tô màu và cột
    `CĐ` đã đỏ khi lệnh chưa có công đoạn; đèn thứ tư chỉ nói lại chuyện cột bên cạnh vừa nói."""
    vat_tu: DenItem
    may_gio: DenItem
    nguoi: DenItem


class LsxTongQuanItem(BaseModel):
    lsx_id: int
    # Độ dư nhỏ nhất giữa các bước đã xếp (ngày làm việc, âm = đang trễ). `None` khi lệnh chưa
    # vào kế hoạch ⇒ FE lùi về `classHan` đếm ngày lịch như cũ.
    slack_ngay: int | None = None
    den: LsxDenOut


class LsxTongQuanOut(BaseModel):
    items: list[LsxTongQuanItem]
