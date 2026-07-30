"""Pydantic schemas — Lệnh sản xuất (LSX).

3 nhóm: (a) HÀNG CHỜ = đơn Sale đã chuyển xuống SX còn dòng chưa lên lệnh; (b) PREVIEW = danh sách
lệnh DỰ KIẾN dẫn xuất tại chỗ từ dòng đơn + phiếu tính giá (chưa ghi DB); (c) LSX = lệnh đã tạo
(kèm routing + checklist thiếu).
"""
from __future__ import annotations

from datetime import date, datetime

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
    total: int


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


class LsxCongDoanIn(BaseModel):
    """1 dòng routing client gửi lên (REPLACE-ALL). Field nào bỏ trống thì server điền mặc định
    từ danh mục — không bắt người dùng khai lại thứ đã có."""

    thu_tu: int | None = None
    cong_doan_id: int | None = None
    ten: str | None = None
    nhom: str | None = None
    loai_buoc: str | None = None
    bat_buoc: bool | None = None
    department_id: int | None = None
    may_id: int | None = None
    may_thay_the_ids: list[int] | None = None
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
    setup_phut: float | None = Field(default=None, ge=0)
    nang_suat: float | None = Field(default=None, ge=0)
    don_vi_nang_suat: str | None = None
    chay_phut: float | None = Field(default=None, ge=0)
    ve_sinh_phut: float | None = Field(default=None, ge=0)
    cho_phut: float | None = Field(default=None, ge=0)
    di_chuyen_phut: float | None = Field(default=None, ge=0)
    # Điều kiện bắt đầu (§4.5)
    dieu_kien_json: list[str] | None = None
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
    nguoi_giao_nhan_id: int | None = None
    ghi_chu: str | None = None


class LsxCongDoanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    thu_tu: int
    cong_doan_id: int | None = None
    ten: str
    nhom: str | None = None
    loai_buoc: str
    bat_buoc: bool = True
    department_id: int | None = None
    department_ten: str | None = None
    may_id: int | None = None
    may_ten: str | None = None
    may_thay_the_ids: list[int] = Field(default_factory=list)

    so_luong_vao: float
    so_luong_ra: float
    don_vi_vao: str
    don_vi_ra: str
    he_so_quy_doi: float
    hao_hut: float
    hao_hut_pct: float
    ty_le_hao_hut: float = 0      # derived = hao_hut / so_luong_vao
    so_luot_chay: int = 1

    so_nhan_cong: int = 1
    setup_phut: float = 0
    nang_suat: float | None = None
    don_vi_nang_suat: str | None = None
    chay_phut: float | None = None      # None = để máy tính từ năng suất
    ve_sinh_phut: float = 0
    cho_phut: float = 0
    di_chuyen_phut: float = 0
    # derived — chiếm máy ĂN capacity; tổng thêm chờ + di chuyển (KHÔNG ăn capacity)
    chiem_may_phut: float = 0
    tong_phut: float = 0

    dieu_kien_json: list[str] = Field(default_factory=list)

    nha_cung_cap: str | None = None
    sl_gui: float | None = None
    ngay_gui_dk: date | None = None
    van_chuyen_ngay: float | None = None
    gia_cong_ngay: float | None = None
    ngay_nhan_dk: date | None = None
    hao_hut_cho_phep: float | None = None
    don_gia_gia_cong: float | None = None
    yeu_cau_ky_thuat: str | None = None
    nguoi_giao_nhan_id: int | None = None
    nguoi_giao_nhan_ten: str | None = None
    ghi_chu: str | None = None

    # --- Khoán theo đầu việc ---------------------------------------------------
    # GHIM (snapshot lúc chọn, xưởng lên giá sau không xê dịch lệnh đã phát):
    khoan_rate_id: int | None = None
    khoan_ten: str | None = None
    khoan_don_vi: str | None = None
    khoan_don_gia: float | None = None
    khoan_tinh_theo: str | None = None
    # Các đầu việc CHỌN ĐƯỢC cho bước (theo tổ + công đoạn) — nuôi dropdown ở drawer.
    khoan_chon_duoc: list[dict] = Field(default_factory=list)
    # DẪN XUẤT (tính lúc đọc, không lưu): SL đã quy đổi · tiền dự kiến · diễn giải cách tính.
    khoan_sl: float | None = None
    khoan_don_vi_sl: str | None = None
    khoan_tien: float | None = None
    khoan_dien_giai: str | None = None
    # Không quy đổi được thì nói THIẾU GÌ, không đoán số.
    khoan_thieu: list[str] = Field(default_factory=list)
    khoan_ly_do: str | None = None


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


class LsxListOut(BaseModel):
    items: list[LsxListItem]
    total: int


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
    bu_hao_to: int
    so_to_ke_hoach: int
    so_to_nguyen: int
    so_con: int

    ban_giao_at: datetime | None = None
    han_giao_khach: date | None = None
    han_hoan_thanh_sx: date | None = None
    is_rush: bool

    quy_cach_json: dict | None = None
    khuon_be_id: int | None = None
    khuon_be_ten: str | None = None
    may_id: int | None = None
    may_ten: str | None = None

    nguoi_phu_trach_id: int | None = None
    nguoi_phu_trach_ten: str | None = None
    ghi_chu: str | None = None
    created_at: datetime
    updated_at: datetime

    cong_doans: list[LsxCongDoanOut] = Field(default_factory=list)
    # Hai rổ TÁCH BẠCH: `thieu` CHẶN "Sẵn sàng lập kế hoạch" (§12); `canh_bao` chỉ tô màu (§14).
    thieu: list[str] = Field(default_factory=list)
    canh_bao: list[str] = Field(default_factory=list)
    lead_time: LeadTimeOut | None = None
    # Công thợ khoán DỰ KIẾN cả lệnh = Σ bước quy đổi được. Là số SÀN: bước chưa chọn đầu việc hoặc
    # thiếu số để quy đổi thì không góp vào — đừng đọc như tổng chi phí nhân công thật.
    khoan_tien_tong: float = 0


class LsxUpdateIn(BaseModel):
    ten: str | None = None
    so_luong_dat: int | None = Field(default=None, ge=0)
    don_vi_tinh: str | None = None
    bu_hao_to: int | None = Field(default=None, ge=0)
    so_to_ke_hoach: int | None = Field(default=None, ge=0)
    so_to_nguyen: int | None = Field(default=None, ge=0)
    so_con: int | None = Field(default=None, ge=1)
    han_hoan_thanh_sx: date | None = None
    is_rush: bool | None = None
    khuon_be_id: int | None = None
    may_id: int | None = None
    nguoi_phu_trach_id: int | None = None
    ghi_chu: str | None = None


class RoutingReplaceIn(BaseModel):
    cong_doans: list[LsxCongDoanIn] = Field(default_factory=list)
    # §10: routing lệch bài tính giá → ghi lý do vào nhật ký (người xác nhận đã có ở audit).
    ly_do: str | None = None


class TinhNguocRow(BaseModel):
    """1 dòng GỢI Ý của phép tính ngược — chưa ghi DB, người kế hoạch xem rồi mới bấm áp dụng."""

    id: int
    thu_tu: int
    ten: str
    so_luong_vao: float
    so_luong_ra: float
    don_vi_vao: str
    don_vi_ra: str


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
    don_vi_vao: str
    don_vi_ra: str
    he_so_quy_doi: float
    setup_phut: float
    nang_suat: float | None = None
    don_vi_nang_suat: str | None = None
    ve_sinh_phut: float


class TrangThaiIn(BaseModel):
    trang_thai: str


class LsxActivityItem(BaseModel):
    at: datetime
    actor_name: str | None = None
    action: str
    detail: str


class LsxActivityOut(BaseModel):
    items: list[LsxActivityItem]
