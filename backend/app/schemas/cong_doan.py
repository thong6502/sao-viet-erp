"""Pydantic schemas — Công đoạn (danh mục)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CongDoanVatTuIn(BaseModel):
    """MỘT món vật tư công đoạn tiêu thụ, kèm định mức của riêng nó (spec 18/09/2026 §3.1).

    ⚠️ ĐỔI HÌNH 18/09/2026 (mg `0316`): trước đây vật tư treo dưới từng ĐẦU VIỆC của công đoạn
    (`cong_doan_dau_viec_vat_tu`). Tầng đầu việc đã gỡ (mg `0320`) nên vật tư về thẳng CÔNG ĐOẠN:
    một công đoạn khai nhiều món, mỗi món một công thức định mức ra LƯỢNG theo ĐVT của món đó.
    Hai món cùng ĐVT vẫn ăn theo hai trục khác hẳn (mực theo số tờ, dung môi theo số màu) nên
    công thức phải nằm ở TỪNG DÒNG, không phải ở món hàng."""

    vat_tu_id: int
    cong_thuc_luong: str | None = None


class CongDoanVatTuRow(CongDoanVatTuIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    # Chỉ trả ID, không trả mã/tên/đơn vị: form đã nạp sẵn danh mục Vật tư khác cho dropdown nên tự
    # tra được — trả kèm ở đây là N+1 query cho mọi công đoạn trong danh sách.



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


class CongDoanKhoanPhatSinhIn(BaseModel):
    id: int | None = None
    ten: str = Field(default="", max_length=255)
    don_gia: float | None = None
    don_vi: str | None = Field(default=None, max_length=24)


class CongDoanKhoanPhatSinhRow(CongDoanKhoanPhatSinhIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class CongDoanKhoanIn(BaseModel):
    unit: str | None = Field(default=None, max_length=24)
    unit_price: float | None = None
    cong_thuc_khoan: str | None = None
    viec_phat_sinh: list[CongDoanKhoanPhatSinhIn] = Field(default_factory=list)


class CongDoanKhoanRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    unit: str
    unit_price: float
    cong_thuc_khoan: str | None = None
    viec_phat_sinh: list[CongDoanKhoanPhatSinhRow] = Field(default_factory=list)


class CongDoanIn(BaseModel):
    ma: str = Field(min_length=1, max_length=30)
    ten: str = Field(min_length=1, max_length=150)
    ten_hien_thi: str | None = None
    # Đơn vị vào/ra trên dòng giấy (hệ số quy đổi lấy từ phiếu, không khai ở đây). None = bước
    # không chạm giấy. Cặp hợp lệ do `cong_doan_service` kiểm.
    don_vi_vao: str | None = None
    don_vi_ra: str | None = None
    # GỠ 18/09/2026 (mg `0324`): `cong_thuc_san_luong` + `don_vi_san_luong` — số của bước ngoài dòng
    # giấy nay do người lập lệnh tự khai ở bước.
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
    # Tổ phụ trách — NHIỀU tổ (18/09/2026, mg `0312`), đúng thứ tự chọn: tổ đầu là mặc định của bước
    # lệnh. `None` = giữ nguyên danh sách đang lưu, `[]` = gỡ hết.
    department_ids: list[int] | None = None
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
    # Vật tư công đoạn tiêu thụ, đúng thứ tự chọn (§3.1) — `[]` = gỡ hết.
    vat_tus: list[CongDoanVatTuIn] = Field(default_factory=list)
    # Vắng = giữ nguyên khi cập nhật; null/khối rỗng = gỡ cấu hình; object đủ = thay cấu hình.
    khoan: CongDoanKhoanIn | None = None


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
    kieu_bu_hao: str = "khong"
    bu_hao_id: int | None = None
    so_to_bu_hao: int = 50
    nhom: str
    nhom_may_cho_phep: list[str] | None = None
    department_ids: list[int] = Field(default_factory=list)
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
    vat_tus: list[CongDoanVatTuRow] = Field(default_factory=list)
    may_lam_duoc: list[CongDoanMayRow] = Field(default_factory=list)
    khoan: CongDoanKhoanRow | None = None
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
