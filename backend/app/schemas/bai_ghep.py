"""Pydantic schemas — Bài ghép (print gang).

Service trả DICT (đã tính số tờ/dư + kiểm tương thích + checklist); response model chỉ để validate
+ tài liệu OpenAPI. Số dẫn xuất gói trong `so_to`; bảng so sánh trong `tuong_thich` (giữ `dict` cho
gọn — UI đọc trực tiếp).
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


# ============================ Request ============================
class TaoBaiGhepIn(BaseModel):
    lsx_ids: list[int] = Field(default_factory=list)


class ThemThanhVienIn(BaseModel):
    lsx_ids: list[int] = Field(default_factory=list)


class SuaThanhVienIn(BaseModel):
    # `con/tờ` CHỈ GHI NHẬN (người bình bài bằng phần mềm khác), nhưng là khoá chia mọi thứ sau
    # điểm toả — sản lượng từng lệnh và phần giấy đều chia theo con.
    so_con_tren_to: int


class GopBuocIn(BaseModel):
    """Gộp N bước CÙNG công đoạn ở N lệnh thành một lượt chạy chung."""

    step_keys: list[str] = Field(default_factory=list)


class UngVienGopIn(BaseModel):
    """Đang chọn những bước này thì còn gộp thêm được bước nào (canvas hỏi trước khi cho bấm)."""

    step_keys: list[str] = Field(default_factory=list)


class BuocChungUpdateIn(BaseModel):
    """Kế hoạch của lượt chạy chung. Số lượng/hao/thời lượng KHÔNG có ở đây — chúng là dẫn xuất."""

    department_id: int | None = None
    may_id: int | None = None
    loai_buoc: str | None = None
    so_nhan_cong: int | None = None
    # Đầu việc khoán ghim theo ID, KHÔNG nhận `khoan_json` thô: ảnh chụp đơn giá là thứ server
    # chụp từ bảng giá của tổ. Cho client gửi thẳng là mở cửa cho đơn giá bịa vào phiếu lương.
    # 0 / null = bỏ chọn. Luật kiểm dùng chung với bước lệnh (`_dau_viec_cua_cong_doan`).
    piece_rate_id: int | None = None
    nang_suat: float | None = None
    don_vi_nang_suat: str | None = None
    # Ô DUY NHẤT còn gõ được: chuẩn bị + tốc độ kế thừa SỐNG từ máy (2026-08-04).
    phat_sinh_phut: float | None = None
    so_luot_chay: int | None = None
    ghi_chu: str | None = None
    vat_tus: list[dict] | None = None
    # Bước chung thuê ngoài → cả bài đi MỘT phiếu, MỘT nhà cung cấp (bước chung nằm trước điểm
    # toả nên cả giao lẫn nhận đều ở tầng bài).
    nha_cung_cap: str | None = None
    sl_gui: float | None = None
    ngay_gui_dk: date | None = None
    van_chuyen_ngay: float | None = None
    gia_cong_ngay: float | None = None
    ngay_nhan_dk: date | None = None
    hao_hut_cho_phep: float | None = None
    don_gia_gia_cong: float | None = None
    yeu_cau_ky_thuat: str | None = None


class BaiGhepUpdateIn(BaseModel):
    giay_id: int | None = None
    kho_in_dai: int | None = None
    kho_in_rong: int | None = None
    may_id: int | None = None
    hao_hut_setup: int | None = None
    hao_hut_chay: int | None = None
    ghi_chu: str | None = None


class TrangThaiIn(BaseModel):
    trang_thai: str


# ============================ Hàng chờ ghép ============================
class HangChoGhepItem(BaseModel):
    lsx_id: int
    ma: str
    ten: str | None = None
    so_luong_dat: int = 0
    don_vi_tinh: str | None = None
    so_con: int = 1
    han_hoan_thanh_sx: date | None = None
    is_rush: bool = False
    order_id: int | None = None
    customer_name: str | None = None
    giay_id: int | None = None
    giay_ten: str | None = None
    gsm: int | None = None
    so_mau_a: int | None = None
    so_mau_b: int | None = None
    quy_cach_in: str | None = None
    kho_tp: str | None = None
    kho_in: str | None = None


class HangChoGhepOut(BaseModel):
    items: list[HangChoGhepItem]
    total: int


# ============================ Danh sách bài ghép ============================
class BaiGhepListItem(BaseModel):
    id: int
    ma: str
    trang_thai: str
    so_lsx: int = 0
    giay_ten: str | None = None
    kho_in: str | None = None
    so_to_tot: int = 0            # TỜ IN cần — sản phẩm của lượt in chung
    tong_to: int = 0
    # Hao của các LƯỢT CHUNG, tra ở bậc số tờ của bài. Tên phải khớp khoá service trả
    # (`hao_de_xuat`) — khai lệch một chữ là pydantic lọc mất và cột luôn hiện 0.
    hao_de_xuat: int = 0
    to_nguyen_can: int = 0        # giấy phải LĨNH KHO = tờ in + hao lượt chung (khác tờ in!)
    so_buoc_chung: int = 0        # 0 = chưa gộp gì, mới chỉ là N lệnh rời
    han_in_muon_nhat: date | None = None
    so_canh_bao: int = 0


class BaiGhepListOut(BaseModel):
    items: list[BaiGhepListItem]
    total: int


# ============================ Chi tiết ============================
class ThanhVienOut(BaseModel):
    thanh_vien_id: int
    lsx_id: int
    lsx_ma: str | None = None
    lsx_ten: str | None = None
    so_luong_dat: int = 0
    don_vi_tinh: str | None = None
    is_rush: bool = False
    trang_thai_lsx: str | None = None
    so_con_tren_to: int = 1
    toa_step_key: str | None = None    # bước gộp cuối cùng; None = lệnh chưa gộp bước nào
    # Số tờ lệnh này THẬT SỰ cần — đã gồm hao các bước riêng, khác `ceil(SL đặt / con)`.
    nhu_cau_to: int = 0
    du_to: int = 0            # dư TỜ ngay tại điểm toả — khác dư con ở cuối chuỗi
    # Phần giấy lệnh này gánh, chia theo CON (cùng khoá chia sản lượng). Tờ dùng chung nên không
    # có "tờ của lệnh nào" — chia được là CHI PHÍ giấy, theo diện tích chiếm trên tờ.
    phan_giay_to: int = 0
    ty_le_giay: float = 0
    san_luong_du_kien: int = 0
    du: int = 0
    giay_id: int | None = None
    giay_ten: str | None = None
    so_mau_a: int | None = None
    so_mau_b: int | None = None
    quy_cach_in: str | None = None
    kho_tp: str | None = None
    han_hoan_thanh_sx: date | None = None


class BaiGhepDetailOut(BaseModel):
    id: int
    ma: str
    trang_thai: str
    giay_id: int | None = None
    giay_ten: str | None = None
    kho_in_dai: int | None = None
    kho_in_rong: int | None = None
    may_id: int | None = None
    may_ten: str | None = None
    # None = CHƯA KHAI (bài dùng số máy đề xuất) · 0 = khai "chạy đúng số, không bù". Khai
    # `int = 0` ở đây là ép NULL thành 0 ngay tại response model — form sẽ hiện 0 và người dùng
    # tưởng đã khai không-hao, trong khi bài vẫn đang cộng hao đề xuất.
    hao_hut_setup: int | None = None
    hao_hut_chay: int | None = None
    ghi_chu: str | None = None
    thanh_vien: list[ThanhVienOut] = Field(default_factory=list)
    so_to: dict = Field(default_factory=dict)          # so_to_tot · tong_to · fill_pct · han · rows
    tuong_thich: dict = Field(default_factory=dict)    # bảng so sánh thuộc tính × thành viên
    thieu: list[str] = Field(default_factory=list)     # checklist CHẶN sẵn sàng
    canh_bao: list[str] = Field(default_factory=list)  # cảnh báo MỀM


# ============================ Nhật ký ============================
class BaiGhepActivityItem(BaseModel):
    at: datetime | None = None
    actor: str | None = None
    action: str
    detail: str | None = None


class BaiGhepActivityOut(BaseModel):
    items: list[BaiGhepActivityItem]


# ============================ Sơ đồ (dẫn xuất) ============================
# Routing ĐẦY ĐỦ của từng lệnh + các bước NGƯỜI đã khai là chạy chung. Không lưu cạnh nào: hình
# tụ-rồi-toả rơi ra từ phép co nút trên đồ thị phụ thuộc sẵn có.
class SoDoNode(BaseModel):
    step_key: str
    # Sau điểm toả là số của LƯỢT ĐI (bài chạy bao nhiêu thì bước này thật sự nhận/ra bấy nhiêu);
    # trước đó là lượt về của chính lệnh. None ở bước ngoài dòng giấy (chế bản đếm kẽm).
    so_luong_vao: float | None = None
    so_luong_ra: float | None = None
    don_vi_vao: str | None = None
    don_vi_ra: str | None = None
    hao_hut: float | None = None
    ten: str
    nhom: str | None = None
    cong_doan_id: int | None = None    # khoá điều kiện gộp: cùng công đoạn mới gộp được
    loai_buoc: str
    thu_tu: int
    gop_step_key: str | None = None    # khác None = đang bị một bước chung ĐÈ
    to_ten: str | None = None
    may_ten: str | None = None
    nha_cung_cap: str | None = None
    tong_phut: float = 0
    chiem_may_phut: float = 0
    # Dải nhanh/chậm nhất (tốc độ tối đa / tối thiểu của máy). Máy chưa khai dải ⇒ = TB.
    chiem_may_phut_min: float = 0
    chiem_may_phut_max: float = 0
    phu_thuoc_step_keys: list[str] = Field(default_factory=list)


class SoDoBuocChung(BaseModel):
    """Một lượt chạy chung — thẻ trải ngang, nhánh tụ vào trái và toả ra phải."""

    step_key: str
    ten: str
    nhom: str | None = None
    cong_doan_id: int | None = None
    loai_buoc: str
    thu_tu: int
    # Số của CẢ LƯỢT, tính bằng TỜ ghép: một lượt chạy thì đếm tờ, con là chuyện của điểm toả.
    so_luong_vao: float = 0
    so_luong_ra: float = 0
    don_vi_vao: str | None = None
    don_vi_ra: str | None = None
    hao_hut: float = 0          # đếm ĐÚNG MỘT LẦN cho cả lượt, ở ĐƠN VỊ VÀO
    hao_hut_pct: float = 0
    # `ra` quy về đơn vị VÀO + hệ số đã dùng — cùng bộ số `bu_hao_chi_tiet` của tính giá. Không có
    # hai số này thì dòng đổi đơn vị đọc lên vô lý và người xem không kiểm được.
    he_so_quy_doi: float = 1
    so_luong_ra_quy: float | None = None
    canh_bao_don_vi: list[str] = Field(default_factory=list)
    # ID + TÊN: <select> cần id để chọn đúng, nhãn cần tên. Chỉ trả tên là form phải lấy tên làm
    # `value` rồi so chuỗi với id — tổ đã gán vẫn hiện "— chọn tổ —".
    department_id: int | None = None
    to_ten: str | None = None
    may_id: int | None = None
    may_ten: str | None = None
    nha_cung_cap: str | None = None
    tong_phut: float = 0
    chiem_may_phut: float = 0
    # Dải nhanh/chậm nhất (tốc độ tối đa / tối thiểu của máy). Máy chưa khai dải ⇒ = TB.
    chiem_may_phut_min: float = 0
    chiem_may_phut_max: float = 0
    # Giá trị NGƯỜI đã khai — form phải mồi lại được, không thì mở drawer là ô trống và lưu đè mất.
    so_nhan_cong: int = 1
    nang_suat: float | None = None
    don_vi_nang_suat: str | None = None
    chay_phut: float | None = None      # dẫn xuất: SL vào × 60 ÷ tốc độ máy × số lượt
    setup_phut: float = 0               # kế thừa từ máy (read-only)
    phat_sinh_phut: float = 0
    so_luot_chay: int = 1
    # Khoán: phần GHIM (đầu việc đã chọn, ảnh chụp) + danh sách chọn được của TỔ đang gán + phần
    # DẪN XUẤT (SL quy đổi · tiền · diễn giải) — cùng hợp đồng với bước lệnh ở màn KHSX.
    khoan_rate_id: int | None = None
    khoan_ten: str | None = None
    khoan_don_vi: str | None = None
    khoan_don_gia: float | None = None
    khoan_chon_duoc: list[dict] = Field(default_factory=list)
    khoan_sl: float | None = None
    khoan_don_vi_sl: str | None = None
    khoan_tien: float | None = None
    khoan_dien_giai: str | None = None
    khoan_thieu: list[str] = Field(default_factory=list)
    khoan_ly_do: str | None = None
    vat_tus: list[dict] = Field(default_factory=list)
    # Gia công ngoài (DỰ KIẾN) — bước chung thuê ngoài thì cả bài đi MỘT phiếu, MỘT nhà cung cấp.
    sl_gui: float | None = None
    ngay_gui_dk: date | None = None
    van_chuyen_ngay: float | None = None
    gia_cong_ngay: float | None = None
    ngay_nhan_dk: date | None = None
    hao_hut_cho_phep: float | None = None
    don_gia_gia_cong: float | None = None
    yeu_cau_ky_thuat: str | None = None
    ghi_chu: str | None = None
    ma_bai_ghep: str | None = None
    # Lệnh nào bị đè + ghi chú kỹ thuật của lệnh đó (GOM, không đè — thợ chạy chung một lượt phải
    # đọc được yêu cầu của mọi khách trên tờ).
    thanh_vien: list[dict] = Field(default_factory=list)
    thieu: list[str] = Field(default_factory=list)
    # Đã khai gì đó cho lượt chung chưa — tách ra thì mất. Cờ THẬT, đừng để FE dò chuỗi `thieu`.
    da_lap_ke_hoach: bool = False


class SoDoNhanh(BaseModel):
    thanh_vien_id: int
    lsx_id: int
    lsx_ma: str | None = None
    lsx_ten: str | None = None
    customer_name: str | None = None
    han_hoan_thanh_sx: date | None = None
    is_rush: bool = False
    mau: int = 0                       # chỉ số màu của nhánh (FE tự map sang bảng màu)
    so_con_tren_to: int = 1
    toa_step_key: str | None = None    # bước gộp cuối cùng; None = lệnh chưa gộp bước nào
    nhu_cau_to: int = 0
    du_to: int = 0            # dư TỜ ngay tại điểm toả — khác dư con ở cuối chuỗi
    # Phần giấy lệnh này gánh, chia theo CON (cùng khoá chia sản lượng). Tờ dùng chung nên không
    # có "tờ của lệnh nào" — chia được là CHI PHÍ giấy, theo diện tích chiếm trên tờ.
    phan_giay_to: int = 0
    ty_le_giay: float = 0
    du: int = 0
    san_luong_du_kien: int = 0
    buoc: list[SoDoNode] = Field(default_factory=list)   # routing ĐẦY ĐỦ, theo thứ tự


class SoDoNgoai(BaseModel):
    step_key: str
    ten: str
    lsx_ma: str | None = None


class SoDoOut(BaseModel):
    bai_ghep: dict = Field(default_factory=dict)
    nhanh: list[SoDoNhanh] = Field(default_factory=list)
    gop: list[SoDoBuocChung] = Field(default_factory=list)
    # Tiền nhiệm NGOÀI bài (vd ruột sách cùng đơn) → node bóng mờ.
    ngoai: list[SoDoNgoai] = Field(default_factory=list)


class UngVienGopOut(BaseModel):
    """`step_key → gộp thêm vào được không, không thì vì sao`."""

    ung_vien: dict = Field(default_factory=dict)
