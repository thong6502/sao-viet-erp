"""Pydantic schemas — Danh mục Giấy & Vật tư (chủng loại giấy / giấy / vật tư in ấn)."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


# ---- Phiên bản giá giấy (lịch sử) ----
class GiayGiaVersionIn(BaseModel):
    ngay_hieu_luc: date | None = None
    kho_dai: int = Field(default=0, ge=0)
    kho_rong: int = Field(default=0, ge=0)
    gsm: int | None = None
    caliper_micron: int | None = None
    tho: str | None = None
    don_vi_gia: str = "kg"
    don_gia: float = Field(default=0, ge=0)
    gia_thi_truong: float | None = None
    ghi_chu: str | None = None


class GiayGiaVersionRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    giay_id: int
    version_no: int
    ngay_hieu_luc: date | None = None
    is_current: bool
    kho_dai: int
    kho_rong: int
    gsm: int | None = None
    caliper_micron: int | None = None
    tho: str | None = None
    don_vi_gia: str
    don_gia: float
    gia_thi_truong: float | None = None
    ghi_chu: str | None = None
    created_at: datetime | None = None


# ---- Chủng loại giấy ----
class ChungLoaiGiayIn(BaseModel):
    ma: str = Field(min_length=1, max_length=30)
    ten: str = Field(min_length=1, max_length=150)
    be_mat: str | None = None
    tho_mac_dinh: str | None = None
    mo_ta: str | None = None
    active: bool = True


class ChungLoaiGiayRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ma: str
    ten: str
    be_mat: str | None = None
    tho_mac_dinh: str | None = None
    mo_ta: str | None = None
    active: bool
    updated_at: datetime | None = None


# ---- Giấy ----
class GiayIn(BaseModel):
    ma: str = Field(min_length=1, max_length=30)
    ten: str = Field(min_length=1, max_length=150)
    chung_loai_giay_id: int | None = None
    gsm: int = Field(gt=0)
    caliper_micron: int | None = None
    tho: str | None = None
    # Mã đơn vị trong `don_vi_do`. None/"" = chưa chọn — KHÔNG mặc định "kg" nữa: đơn vị gốc quyết
    # định cách cộng tồn kho, điền hộ một lần là sai vĩnh viễn mà không ai để ý.
    don_vi_gia: str | None = None
    don_gia: float = Field(default=0, ge=0)
    gia_thi_truong: float | None = None
    kho_tinh_gia: bool = True
    ghi_chu: str | None = None
    cong_thuc_gia: str | None = None
    active: bool = True


class GiayRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ma: str
    ten: str
    chung_loai_giay_id: int | None = None
    gsm: int
    caliper_micron: int | None = None
    tho: str | None = None
    don_vi_gia: str | None = None
    # Tên đơn vị để BẢNG đọc được ("bản kẽm" thay vì mã `kem`) — router gán, không có trong DB.
    don_vi_ten: str | None = None
    don_gia: float
    gia_thi_truong: float | None = None
    kho_tinh_gia: bool
    ghi_chu: str | None = None
    version_no: int = 1
    cong_thuc_gia: str | None = None
    active: bool
    updated_at: datetime | None = None


# ---- Vật tư in ấn (phẳng: mã · tên · ĐVT · giá · ghi chú) ----
class VatTuIn(BaseModel):
    ma: str = Field(min_length=1, max_length=30)
    ten: str = Field(min_length=1, max_length=150)
    don_vi_gia: str | None = None
    don_gia: float = Field(default=0, ge=0)
    ghi_chu: str | None = None
    cong_thuc_gia: str | None = None
    active: bool = True


class VatTuRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ma: str
    ten: str
    don_vi_gia: str | None = None
    # Tên đơn vị cho BẢNG đọc được — router gán, không có trong DB.
    don_vi_ten: str | None = None
    don_gia: float
    ghi_chu: str | None = None
    cong_thuc_gia: str | None = None
    active: bool
    updated_at: datetime | None = None


class ListOut(BaseModel):
    items: list
    total: int
    page: int
    size: int


class VatLieuAnhOut(BaseModel):
    """Kết quả gắn/gỡ ảnh minh hoạ — đường ảnh sau thao tác (None = đã gỡ)."""
    anh_url: str | None = None


# ---- MẶT HÀNG GỐC: cửa dùng chung cho Kho + NCC ----
class MatHangRow(BaseModel):
    """1 dòng trong picker mặt hàng — gộp Giấy + Vật tư khác."""
    hang_loai: str            # 'giay' | 'vat_tu'
    hang_id: int
    nhom: str                 # nhãn hiện trên chip ("Giấy" / "Vật tư khác")
    ma: str
    ten: str
    don_vi_goc: str | None = None


class DonViDungDuocRow(BaseModel):
    ma: str
    ten: str
    # `he_so`: 1 đơn-vị-gốc = he_so <đơn vị này>. `he_so_ve_goc`: chiều ngược, dùng khi quy số
    # người dùng nhập về đơn vị gốc để cộng tồn. Trả cả hai để nơi gọi khỏi tự nghịch đảo.
    he_so: float
    he_so_ve_goc: float
    la_goc: bool
    dien_giai: str


class DonViCuaMatHangOut(BaseModel):
    hang_loai: str
    hang_id: int
    ma: str
    ten: str
    don_vi_goc: str | None = None
    don_vi_goc_ten: str | None = None
    ds: list[DonViDungDuocRow] = []
    # Vì sao danh sách rỗng — UI hiện nguyên câu này thay vì im lặng khoá ô.
    ly_do: str | None = None
