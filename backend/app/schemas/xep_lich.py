"""Pydantic schemas — Xếp lịch công đoạn.

Service trả DICT đã tính sẵn (thời lượng · sớm-nhất/muộn-nhất · độ dư · nhãn nguy cơ · cờ xung đột);
response model chỉ để validate + tài liệu OpenAPI. Request dùng `exclude_unset` (router) để phân biệt
"không gửi" với "gửi null" khi gán từng phần.
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


# ============================ Request ============================
class GanIn(BaseModel):
    """Gán tài nguyên + giờ cho 1 dòng. Trường nào không gửi thì giữ nguyên (router `exclude_unset`)."""
    may_id: int | None = None
    department_id: int | None = None
    nha_cung_cap: str | None = None
    work_shift_id: int | None = None
    start_at: datetime | None = None


class GanLoatRow(GanIn):
    id: int


class GanLoatIn(BaseModel):
    rows: list[GanLoatRow] = Field(default_factory=list)


class KhoaIn(BaseModel):
    khoa: bool = True


# ============================ Hàng chờ (order-pool) ============================
class HangChoItem(BaseModel):
    nguon: str                       # lsx | in_ghep
    id: int
    ma: str
    ten: str | None = None
    so_cong_doan: int = 0
    is_rush: bool = False
    han_hoan_thanh_sx: date | None = None


class HangChoOut(BaseModel):
    items: list[HangChoItem] = Field(default_factory=list)
    total: int = 0


# ============================ Bảng dòng lịch ============================
class XepLichDongOut(BaseModel):
    id: int
    nguon: str
    lsx_id: int | None = None
    bai_ghep_id: int | None = None
    lsx_ma: str | None = None
    cong_doan_ten: str | None = None
    loai_buoc: str | None = None
    so_luong_vao: float | None = None
    don_vi_vao: str | None = None
    # Tài nguyên gán
    may_id: int | None = None
    may_ten: str | None = None
    department_id: int | None = None
    department_ten: str | None = None
    nha_cung_cap: str | None = None
    work_shift_id: int | None = None
    # Lịch (theo giờ) + dẫn xuất
    som_nhat: datetime | None = None
    muon_nhat: datetime | None = None
    start_at: datetime | None = None
    finish_at: datetime | None = None
    chiem_may_phut: float = 0
    tong_phut: float = 0
    slack_ngay: int | None = None
    nhan_rui_ro: str | None = None      # an_toan | sap_toi_han | nguy_co_tre | da_tre | chua_co_han
    # Trạng thái
    trang_thai: str
    is_locked: bool = False
    co_xung_dot: bool = False
    blocked_reason: str | None = None
    is_rush: bool = False


class XepLichDongListOut(BaseModel):
    items: list[XepLichDongOut] = Field(default_factory=list)
    total: int = 0


# ============================ Gợi ý ============================
class GoiYOut(BaseModel):
    may_id: int | None = None
    khe_trong: datetime | None = None       # khe trống sớm nhất trên máy
    finish_neu_xep: datetime | None = None  # kết thúc nếu xếp vào khe đó
    han_lui: datetime | None = None         # bắt đầu muộn nhất còn kịp hạn
