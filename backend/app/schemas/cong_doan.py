"""Pydantic schemas — Công đoạn (danh mục)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CongDoanDauViecVatTuIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    vat_tu_id: int
    # ĐỊNH MỨC của CHÍNH món này trong CHÍNH đầu việc này — ra LƯỢNG theo ĐVT của vật tư.
    cong_thuc_luong: str | None = None


class CongDoanDauViecIn(BaseModel):
    piece_rate_id: int
    # `nang_suat_nguoi_gio` = mức TRUNG BÌNH (số chảy vào công thức thời lượng); min/max chỉ để ra
    # khoảng nhanh–chậm, để trống thì ba mức bằng nhau. `don_vi_nang_suat` là ĐƠN VỊ ĐÍCH mà
    # `cong_thuc_gio` phải quy về (mã `<đơn vị>_gio`); trống = lùi về đơn vị của đơn giá khoán.
    nang_suat_nguoi_gio: float = Field(gt=0)
    nang_suat_nguoi_gio_min: float | None = Field(default=None, gt=0)
    nang_suat_nguoi_gio_max: float | None = Field(default=None, gt=0)
    don_vi_nang_suat: str | None = Field(default=None, max_length=32)
    # Kíp chuẩn của công đoạn — MỘT số duy nhất về nhân lực (mg `0270`).
    so_nguoi_tieu_chuan: int = Field(ge=1)
    # CÔNG THỨC TÍNH TIỀN CÔNG của đầu việc này trong công đoạn này (06/09/2026) — ra LƯỢNG theo
    # đơn vị đơn giá khoán, engine nhân đơn giá sau. Ghim vào bước lệnh lúc chọn đầu việc.
    cong_thuc_khoan: str | None = None
    # CÁCH ĐO GIỜ CHẠY của đầu việc này trong công đoạn này (07/09/2026) — ra LƯỢNG theo đơn vị
    # NĂNG SUẤT khoán, engine chia cho năng suất sau. Tách khỏi `cong_thuc_khoan` ngay trên vì
    # tiền và giờ không cùng một cách đếm: in trở 2 lượt thì tiền nhân đôi mà giờ thì không.
    cong_thuc_gio: str | None = None
    # VẬT TƯ đầu việc tiêu thụ (mg 0191). Trước 06/09/2026 chỉ là `vat_tu_ids: list[int]` (danh
    # sách thuần, công thức treo ở món hàng); nay mỗi dòng mang công thức định mức của riêng nó vì
    # hai món cùng ĐVT ăn theo hai trục khác hẳn (mực theo số tờ, dung môi theo số màu).
    vat_tus: list[CongDoanDauViecVatTuIn] = Field(default_factory=list)


class CongDoanDauViecRow(CongDoanDauViecIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    # Chỉ trả ID, không trả mã/tên/đơn vị: form đã nạp sẵn danh mục Vật tư khác cho dropdown nên tự
    # tra được — trả kèm ở đây là N+1 query cho mỗi đầu việc của mỗi công đoạn trong danh sách.


class CongDoanMayIn(BaseModel):
    may_id: int
    # Ra LƯỢNG theo đơn vị TỐC ĐỘ của máy (không ra giờ — engine vẫn chia tốc độ). Trống = lùi về
    # cầu quy đổi, đúng hành vi của ô "Cách đo lượng" cũ trên máy khi để trống.
    cong_thuc_gio: str | None = None
    # Ra TIỀN, GHI ĐÈ `cong_doan.cong_thuc_gia` khi phiếu tính giá có chọn đúng máy này.
    cong_thuc_gia: str | None = None


class CongDoanMayRow(CongDoanMayIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class CongDoanIn(BaseModel):
    ma: str = Field(min_length=1, max_length=30)
    ten: str = Field(min_length=1, max_length=150)
    ten_hien_thi: str | None = None
    # Đơn vị vào/ra trên dòng giấy (hệ số quy đổi lấy từ phiếu, không khai ở đây). None = bước
    # không chạm giấy. Cặp hợp lệ do `cong_doan_service` kiểm.
    don_vi_vao: str | None = None
    don_vi_ra: str | None = None
    # Công thức SẢN LƯỢNG RA của bước NGOÀI dòng giấy (mg `0214`) — vd Ghi kẽm khai `so_kem`. Vế VÀO
    # KHÔNG khai: nó suy ngược từ RA qua CẦU quy đổi `vào → ra` (module Đơn vị & quy đổi) + bù hao —
    # chốt cứng cả hai đầu thì hao hết chỗ nhét. Hệ số KHÔNG khai ở đây (bỏ `he_so_ngoai_dong`
    # 20/08/2026: nguồn thứ hai gây sai), lấy thẳng từ `don_vi_quy_doi`. Bước trên dòng bỏ qua cột này.
    cong_thuc_san_luong: str | None = Field(default=None, max_length=200)
    kieu_bu_hao: str = "khong"
    bu_hao_id: int | None = None
    so_to_bu_hao: int = Field(default=50, ge=0)
    nhom: str
    # Nhóm máy (tên ở danh mục `nhom_may`) làm được công đoạn này — chặn gán máy sai loại ở bài
    # ghép. None/[] = không ràng buộc.
    nhom_may_cho_phep: list[str] | None = None
    # Máy CỤ THỂ chạy được công đoạn, mỗi dòng mang công thức giờ + công thức giá của riêng nó
    # (06/09/2026). `nhom_may_cho_phep` ngay trên nay chỉ còn là BỘ LỌC để chọn máy trong drawer.
    may_lam_duoc: list[CongDoanMayIn] = Field(default_factory=list)
    department_id: int | None = None
    khoan_ghi_theo: str = "khong"
    allowed_defect_pct: float = Field(default=0, ge=0, le=1)
    allowed_defect_abs: float = Field(default=0, ge=0)
    che_do_tinh: str = "theo_san_luong"
    pricing_basis: str | None = None
    setup_cost: float = Field(default=0, ge=0)
    setup_time: float = Field(default=0, ge=0)
    # Năng suất mặc định lúc lên lệnh SX (output/giờ) — đơn vị theo đầu vào của bước, không lưu.
    nang_suat: float | None = Field(default=None, gt=0)
    run_rate: float | None = None
    rate_tiers: list | None = None
    size_tiers: list | None = None
    first_unit_floor: float | None = None
    min_charge: float | None = None
    requires_tooling: bool = False
    tooling_type: str | None = None
    spoilage_pct: float = Field(default=0, ge=0, le=100)
    inline_flag: bool = False
    ghi_chu: str | None = None
    cong_thuc_gia: str | None = None
    active: bool = True
    dau_viec_dinh_muc: list[CongDoanDauViecIn] = Field(default_factory=list)


class CongDoanRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ma: str
    ten: str
    ten_hien_thi: str | None = None
    don_vi_vao: str | None = None
    don_vi_ra: str | None = None
    # GỠ 08/09/2026: `don_vi_vao_ten` / `don_vi_ra_ten`. Hai ô này lưu MÃ CHẶNG của dòng giấy
    # (`to_nguyen · to · con · tay · cai`), không phải mã đơn vị kho — nhãn của chúng là
    # `models/don_vi_do.TRAM_NHAN`, hằng trong code, không phải thứ tra ở danh mục. Lý do đầy đủ:
    # xem khối chú thích chỗ `cong_doan_service.gan_ten_don_vi` cũ.
    #: Công thức SẢN LƯỢNG RA của bước NGOÀI dòng giấy (mg `0214`). Bước trên dòng giấy bỏ qua
    #: — số của chúng đến từ chuỗi bù hao ngược.
    cong_thuc_san_luong: str | None = None
    # "Lần trước công thức" (mục 3+7) — router gán từ `cong_thuc_lich_su`, không có trong DB.
    cong_thuc_san_luong_truoc: str | None = None
    cong_thuc_san_luong_sua_luc: datetime | None = None
    kieu_bu_hao: str = "khong"
    bu_hao_id: int | None = None
    so_to_bu_hao: int = 50
    nhom: str
    nhom_may_cho_phep: list[str] | None = None
    department_id: int | None = None
    khoan_ghi_theo: str = "khong"
    allowed_defect_pct: float = 0
    allowed_defect_abs: float = 0
    che_do_tinh: str
    pricing_basis: str | None = None
    setup_cost: float
    setup_time: float
    nang_suat: float | None = None
    run_rate: float | None = None
    rate_tiers: list | None = None
    size_tiers: list | None = None
    first_unit_floor: float | None = None
    min_charge: float | None = None
    requires_tooling: bool
    tooling_type: str | None = None
    spoilage_pct: float
    inline_flag: bool
    ghi_chu: str | None = None
    cong_thuc_gia: str | None = None
    active: bool
    dau_viec_dinh_muc: list[CongDoanDauViecRow] = Field(default_factory=list)
    may_lam_duoc: list[CongDoanMayRow] = Field(default_factory=list)
    updated_at: datetime | None = None


class CongDoanListOut(BaseModel):
    items: list[CongDoanRow]
    total: int
    page: int
    size: int
    # Số công đoạn theo giai đoạn — nuôi số trên tab lọc (màn chỉ cầm 20 dòng, không tự đếm được).
    facets: dict[str, int] = {}


class RefOption(BaseModel):
    """Một mục cho dropdown 'ref' của màn cấu hình (khớp {id, ma, ten})."""
    id: int
    ma: str
    ten: str


class RefOptionListOut(BaseModel):
    items: list[RefOption]
