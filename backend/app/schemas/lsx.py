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
    department_id: int | None = None
    department_ten: str | None = None
    thue_ngoai: bool = False
    nha_cung_cap: str | None = None


class PreviewLine(BaseModel):
    order_line_id: int
    ten: str
    so_luong_dat: int
    don_vi_tinh: str
    phieu_thanh_phan_id: int | None = None
    ptg_ma: str | None = None
    # Số của engine chạy lại theo SL của ĐƠN (không lấy số lúc tính giá).
    bu_hao_to: int = 0
    so_to_ke_hoach: int = 0
    so_to_nguyen: int = 0
    so_con: int = 1
    so_kem: int = 0
    so_luot: int = 0
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
class LsxCongDoanIn(BaseModel):
    thu_tu: int | None = None
    cong_doan_id: int | None = None
    ten: str | None = None
    nhom: str | None = None
    department_id: int | None = None
    may_id: int | None = None
    so_luong_vao: float | None = None
    so_luong_ra: float | None = None
    don_vi: str | None = None
    hao_hut: float | None = None
    thue_ngoai: bool | None = None
    nha_cung_cap: str | None = None
    ghi_chu: str | None = None


class LsxCongDoanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    thu_tu: int
    cong_doan_id: int | None = None
    ten: str
    nhom: str | None = None
    department_id: int | None = None
    department_ten: str | None = None
    may_id: int | None = None
    may_ten: str | None = None
    so_luong_vao: float
    so_luong_ra: float
    don_vi: str
    hao_hut: float
    thue_ngoai: bool
    nha_cung_cap: str | None = None
    ghi_chu: str | None = None


class LsxListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ma: str
    loai: str
    ten: str
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
    thieu: list[str] = Field(default_factory=list)


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


class TrangThaiIn(BaseModel):
    trang_thai: str


class LsxActivityItem(BaseModel):
    at: datetime
    actor_name: str | None = None
    action: str
    detail: str


class LsxActivityOut(BaseModel):
    items: list[LsxActivityItem]
