"""Pydantic schemas — sổ tài sản cố định & công cụ dụng cụ.

⚠️ Service trả DICT cho bảng kỳ và kết quả kiểm kê: field nào không khai ở schema Out thì
Pydantic bỏ IM LẶNG, frontend nhận `undefined` mà không có lỗi nào bật ra. Thêm field phải đi
hết chuỗi dict → schema → type TS.
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ChiPhiIn(BaseModel):
    dien_giai: str = Field(default="Nguyên giá", max_length=255)
    so_tien: int = 0


class ChiPhiOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    dien_giai: str
    so_tien: int


class TaiSanIn(BaseModel):
    ma: str | None = Field(default=None, max_length=32)  # bỏ trống → server sinh TS-#### / CC-####
    ten: str = Field(min_length=1, max_length=255)
    loai: str = "tscd"
    so_luong: int = 1
    don_gia: int | None = None
    so_thang: int
    ngay_su_dung: date
    #: `ghi_tang` (mua mới) | `dau_ky` (số dư mang sang lúc lên phần mềm).
    nguon_vao: str = "ghi_tang"
    #: Chỉ `dau_ky`: tháng đầu tiên phần mềm chịu trách nhiệm tính.
    moc_tu_ngay: date | None = None
    hao_mon_dau_ky: int = 0
    thang_da_trich_dau_ky: int = 0
    chi_phi: list[ChiPhiIn] = []
    bo_phan_id: int | None = None
    nguoi_quan_ly: str | None = None
    vi_tri: str | None = None
    so_hoa_don: str | None = None
    nha_cung_cap: str | None = None
    #: Chữ tự do, kể cả định khoản. Hệ KHÔNG đọc nội dung — xem docstring `models/tai_san.py`.
    ghi_chu: str | None = None


class TaiSanSuaIn(BaseModel):
    """Sửa: mọi ô đều tuỳ chọn — chỉ gửi lên ô thật sự đổi.

    Ô ảnh hưởng số bị máy chủ chặn khi tài sản đã có số ở kỳ đã chốt (409).
    """

    ten: str | None = None
    loai: str | None = None
    so_luong: int | None = None
    don_gia: int | None = None
    so_thang: int | None = None
    ngay_su_dung: date | None = None
    moc_tu_ngay: date | None = None
    hao_mon_dau_ky: int | None = None
    thang_da_trich_dau_ky: int | None = None
    chi_phi: list[ChiPhiIn] | None = None
    bo_phan_id: int | None = None
    nguoi_quan_ly: str | None = None
    vi_tri: str | None = None
    so_hoa_don: str | None = None
    nha_cung_cap: str | None = None
    ghi_chu: str | None = None


class TaiSanRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ma: str
    ten: str
    loai: str
    so_luong: int
    don_gia: int | None = None
    nguyen_gia: int
    so_thang: int
    so_thang_con: int
    ngay_su_dung: date
    moc_tu_ngay: date
    hao_mon_luy_ke: int
    co_so_trich: int
    nguon_vao: str
    bo_phan_id: int | None = None
    #: Tên bộ phận — server ghép sẵn để bảng khỏi tra danh mục cho từng dòng.
    bo_phan_ten: str | None = None
    nguoi_quan_ly: str | None = None
    vi_tri: str | None = None
    so_hoa_don: str | None = None
    nha_cung_cap: str | None = None
    ghi_chu: str | None = None
    trang_thai: str
    ngay_giam: date | None = None
    #: Nguyên giá − hao mòn lũy kế (chốt tại kỳ đã chốt gần nhất).
    con_lai: int = 0


class BienDongOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    loai: str
    ngay: date
    so_tien: int | None = None
    bo_phan_moi_id: int | None = None
    so_thang_con_lai: int | None = None
    so_luong_giam: int | None = None
    ly_do: str | None = None
    created_at: datetime | None = None


class KhauHaoDongOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ky_nam: int
    ky_thang: int
    muc_trich: int
    luy_ke: int
    con_lai: int


class TaiSanDetailOut(TaiSanRow):
    chi_phi: list[ChiPhiOut] = []
    bien_dong: list[BienDongOut] = []
    khau_hao: list[KhauHaoDongOut] = []
    #: Giá bán − giá trị còn lại của chứng từ ghi giảm mới nhất. None nếu chưa/không khai giá bán.
    chenh_lech_thanh_ly: int | None = None


class TaiSanListOut(BaseModel):
    items: list[TaiSanRow]
    total: int


class DongDuKienOut(BaseModel):
    nam: int
    thang: int
    muc_trich: int
    luy_ke: int
    con_lai: int


class BienDongIn(BaseModel):
    """Một chứng từ biến động. `loai` quyết định ô nào bắt buộc — máy chủ kiểm, không phải FE."""

    loai: str  # dieu_chuyen | nang_cap | ghi_giam
    ngay: date
    bo_phan_moi_id: int | None = None       # dieu_chuyen
    so_tien: int | None = None              # nang_cap: chi phí
    so_thang_con_lai: int | None = None     # nang_cap
    gia_ban: int | None = None              # ghi_giam
    so_luong_giam: int | None = None        # ghi_giam CCDC theo lô
    ly_do: str | None = None


class KyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ky_nam: int
    ky_thang: int
    trang_thai: str
    ngay_chot: datetime | None = None


class HangBangKyOut(BaseModel):
    tai_san_id: int
    ma: str
    ten: str
    loai: str
    bo_phan_ten: str | None = None
    nguyen_gia: int
    muc_trich: int
    luy_ke: int
    con_lai: int


class VetKyOut(BaseModel):
    """Một lần chốt hoặc mở lại kỳ. `so_tien` là độ lớn, hướng đọc ở `hanh_dong`."""

    id: int
    hanh_dong: str          # chot | mo
    so_tien: int
    so_mon: int
    nguoi_ten: str | None = None
    thoi_diem: datetime


class BangKyOut(BaseModel):
    nam: int
    thang: int
    trang_thai: str
    tong_muc_trich: int
    items: list[HangBangKyOut]
    #: Vết chốt/mở của chính kỳ này — đi kèm bảng, không bắt màn hình gọi thêm một lượt.
    lich_su: list[VetKyOut] = []


# --- Kiểm kê -----------------------------------------------------------------------------


class KiemKeIn(BaseModel):
    ngay: date
    bo_phan_id: int | None = None
    ghi_chu: str | None = None


class KiemKeDongIn(BaseModel):
    ket_qua: str | None = None       # co | khong_thay
    tinh_trang: str | None = None
    ghi_chu: str | None = None


class PhatHienIn(BaseModel):
    ten_phat_hien: str = Field(min_length=1, max_length=255)
    tinh_trang: str | None = None
    ghi_chu: str | None = None


class KiemKeDongOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tai_san_id: int | None = None
    ma: str | None = None
    ten: str | None = None
    ket_qua: str | None = None
    ten_phat_hien: str | None = None
    tinh_trang: str | None = None
    ghi_chu: str | None = None


class KiemKeRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ma: str
    ngay: date
    bo_phan_id: int | None = None
    trang_thai: str
    ghi_chu: str | None = None


class KiemKeDetailOut(KiemKeRow):
    dong: list[KiemKeDongOut] = []


class KiemKeListOut(BaseModel):
    items: list[KiemKeRow]
    total: int


class KetQuaKiemKeOut(BaseModel):
    thieu: list[KiemKeDongOut]
    thua: list[KiemKeDongOut]
