"""Pydantic schemas — sổ tài sản cố định & công cụ dụng cụ.

⚠️ Service trả DICT cho bảng tháng: field nào không khai ở schema Out thì
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
    #: Chỉ `dau_ky`: tháng đầu tiên phần mềm chịu trách nhiệm tính (ép về ngày 1).
    moc_tu_ngay: date | None = None
    hao_mon_dau_ky: int = 0
    thang_da_trich_dau_ky: int = 0
    chi_phi: list[ChiPhiIn] = []
    bo_phan_id: int | None = None
    #: Một nhân viên của bộ phận `bo_phan_id` (máy chủ kiểm). Có id thì tên `nguoi_quan_ly` do
    #: máy chủ chụp từ hồ sơ, chữ gửi lên bị bỏ qua.
    nguoi_quan_ly_id: int | None = None
    nguoi_quan_ly: str | None = None
    vi_tri: str | None = None
    so_hoa_don: str | None = None
    nha_cung_cap: str | None = None
    #: Chữ tự do, kể cả định khoản. Hệ KHÔNG đọc nội dung — xem docstring `models/tai_san.py`.
    ghi_chu: str | None = None


class TaiSanSuaIn(BaseModel):
    """Sửa: mọi ô đều tuỳ chọn — chỉ gửi lên ô thật sự đổi.

    Ô ảnh hưởng số bị máy chủ chặn khi tài sản đã có chứng từ biến động (409).
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
    nguoi_quan_ly_id: int | None = None
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
    co_so_trich: int
    nguon_vao: str
    hao_mon_dau_ky: int = 0
    thang_da_trich_dau_ky: int = 0
    bo_phan_id: int | None = None
    #: Tên bộ phận — server ghép sẵn để bảng khỏi tra danh mục cho từng dòng.
    bo_phan_ten: str | None = None
    nguoi_quan_ly_id: int | None = None
    #: Tên người quản lý (chụp từ hồ sơ nhân viên; dòng cũ có thể là chữ tự gõ).
    nguoi_quan_ly: str | None = None
    vi_tri: str | None = None
    so_hoa_don: str | None = None
    nha_cung_cap: str | None = None
    ghi_chu: str | None = None
    trang_thai: str
    ngay_giam: date | None = None
    #: Hao mòn lũy kế TÍNH RA từ lịch, tới hết tháng `luy_ke_den` (tháng trước tháng hiện tại;
    #: món đã ghi giảm thì tới ngày giảm).
    hao_mon_luy_ke: int = 0
    #: "YYYY-MM" — tháng cuối đã gộp vào `hao_mon_luy_ke`.
    luy_ke_den: str = ""
    #: Nguyên giá − hao mòn lũy kế; món đã ghi giảm = 0 (đã ra khỏi sổ).
    con_lai: int = 0


class BienDongOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    loai: str
    ngay: date
    so_tien: int | None = None
    bo_phan_moi_id: int | None = None
    so_thang_con_lai: int | None = None
    #: Chỉ dòng CŨ (ghi giảm theo lô, nghiệp vụ đã bỏ 08/09/2026).
    so_luong_giam: int | None = None
    ly_do: str | None = None
    created_at: datetime | None = None


class KhauHaoDongOut(BaseModel):
    """Một tháng trong lịch khấu hao của một tài sản."""

    nam: int
    thang: int
    muc_trich: int
    luy_ke: int
    con_lai: int


class TaiSanDetailOut(TaiSanRow):
    chi_phi: list[ChiPhiOut] = []
    bien_dong: list[BienDongOut] = []
    #: Phần lịch đã vào lũy kế (tới hết tháng trước). Phần sắp tới xem `/du-kien`.
    khau_hao: list[KhauHaoDongOut] = []


class TaiSanListOut(BaseModel):
    items: list[TaiSanRow]
    total: int


class SuKienOut(BaseModel):
    """Một chuyện của tháng: nhãn ngắn (chip trên bảng) + câu đầy đủ (tooltip, ngăn chi tiết)."""

    #: `dau` | `dau_ky` | `nang_cap` | `bot` | `giam` | `chuyen` | `cuoi`.
    loai: str
    nhan: str
    chi_tiet: str


class DongDuKienOut(BaseModel):
    nam: int
    thang: int
    muc_trich: int
    luy_ke: int
    #: Tháng ghi giảm = 0 (món đã ra khỏi sổ; giá trị lúc bỏ nằm trong sự kiện `giam`).
    con_lai: int
    su_kien: list[SuKienOut] = []
    #: Các câu `chi_tiet` nối bằng "; " — để Excel và chỗ nào chỉ cần một chuỗi.
    dien_giai: str | None = None


class BienDongIn(BaseModel):
    """Một chứng từ biến động. `loai` quyết định ô nào bắt buộc — máy chủ kiểm, không phải FE."""

    loai: str  # dieu_chuyen | nang_cap  (ghi_giam đã bỏ 08/09/2026 — món không dùng nữa thì xoá)
    ngay: date
    bo_phan_moi_id: int | None = None       # dieu_chuyen
    #: dieu_chuyen: người quản lý mới (nhân viên của bộ phận nhận). Không gửi ⇒ bỏ trống.
    nguoi_quan_ly_id: int | None = None
    so_tien: int | None = None              # nang_cap: chi phí
    so_thang_con_lai: int | None = None     # nang_cap
    ly_do: str | None = None


class NhanVienChonOut(BaseModel):
    """Một nhân viên đang làm của bộ phận — để chọn làm người quản lý tài sản."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    full_name: str


class HangBangThangOut(BaseModel):
    tai_san_id: int
    ma: str
    ten: str
    loai: str
    #: Lô CCDC còn mấy cái (TSCĐ = 1) — bớt cái là nguyên giá đổi, số này nói vì sao.
    so_luong: int = 1
    bo_phan_ten: str | None = None
    nguyen_gia: int
    muc_trich: int
    luy_ke: int
    #: Tháng ghi giảm = 0 (món đã ra khỏi sổ).
    con_lai: int
    su_kien: list[SuKienOut] = []
    #: Các câu `chi_tiet` nối bằng "; " (cột Diễn giải trên Excel); None nếu tháng bình thường.
    dien_giai: str | None = None


class BangThangOut(BaseModel):
    """Bảng khấu hao một tháng — tính tại chỗ từ sổ, không có trạng thái chốt/mở."""

    nam: int
    thang: int
    tong_muc_trich: int
    items: list[HangBangThangOut]
