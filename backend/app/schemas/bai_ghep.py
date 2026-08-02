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
    so_con_tren_to: int
    # Lệnh có ≥2 lượt in thì phải chỉ đích danh lượt nào chạy chung tờ này.
    buoc_in_step_key: str | None = None


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
    so_to_tot: int = 0
    tong_to: int = 0
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
    # Bước in chạy chung tờ + các lượt in chọn được (lệnh in 2 lượt thì phải chỉ đích danh).
    buoc_in_step_key: str | None = None
    buoc_in_chon_duoc: list[dict] = Field(default_factory=list)
    # Số tờ lệnh này THẬT SỰ cần — đã gồm hao các bước sau in, khác `ceil(SL đặt / con)`.
    nhu_cau_to: int = 0
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
    hao_hut_setup: int = 0
    hao_hut_chay: int = 0
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
# N nhánh vào → MỘT node IN → N nhánh ra. Không lưu cạnh nào: dựng lúc đọc từ thành viên bài +
# routing từng lệnh + vị trí bước in. Xem `docs/spec-bai-ghep-dag.md` §2.
class SoDoNode(BaseModel):
    step_key: str
    ten: str
    nhom: str | None = None
    loai_buoc: str
    thu_tu: int
    to_ten: str | None = None
    may_ten: str | None = None
    nha_cung_cap: str | None = None
    tong_phut: float = 0
    chiem_may_phut: float = 0
    phu_thuoc_step_keys: list[str] = Field(default_factory=list)


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
    buoc_in_step_key: str | None = None
    buoc_in_chon_duoc: list[dict] = Field(default_factory=list)
    nhu_cau_to: int = 0
    du: int = 0
    truoc_in: list[SoDoNode] = Field(default_factory=list)
    sau_in: list[SoDoNode] = Field(default_factory=list)


class SoDoNgoai(BaseModel):
    step_key: str
    ten: str
    lsx_ma: str | None = None


class SoDoOut(BaseModel):
    bai_ghep: dict = Field(default_factory=dict)
    nhanh: list[SoDoNhanh] = Field(default_factory=list)
    # Tiền nhiệm NGOÀI bài (vd ruột sách cùng đơn) → node bóng mờ ở nhánh sau in.
    ngoai: list[SoDoNgoai] = Field(default_factory=list)
