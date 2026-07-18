"""Kế hoạch & Lệnh sản xuất — API schemas (Chunk 3), spec `docs/spec-ke-hoach-san-xuat.md`.

DTO đọc (`*Out`) map thẳng ORM (`from_attributes`) — máy CHỈ GHI NHẬN, không nặn thêm.
Request (`*In`) chỉ nhận field người NHẬP (số con nhập tay, quy cách ẢNH CHỤP đọc từ PTG ở FE
truyền vào ghép). Actor (người ghi / người duyệt) LẤY TỪ TOKEN ở router — không nhận qua body.
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


# ============================================================ REQUESTS (người nhập)
class BungIn(BaseModel):
    """Bung lệnh từ đơn đã chốt (idempotent theo đơn·ấn phẩm) — "mỗi ấn phẩm 1 lệnh"."""
    order_id: int


class TaoLenhIn(BaseModel):
    """Tạo 1 LỆNH từ nhóm ấn phẩm người kế hoạch PICK (cùng 1 đơn). Máy CHỈ GHI — không phán 'đủ giống'."""
    order_id: int
    phieu_thanh_phan_ids: list[int] = Field(default_factory=list)


class PlacementIn(BaseModel):
    """1 dòng xếp bài khi tạo tờ (ghép) — số con NHẬP TAY."""
    lenh_sx_id: int
    so_con: int = Field(default=0, ge=0)


class GhepIn(BaseModel):
    """Tạo 1 TỜ IN + các dòng xếp bài. Giấy/khổ/màu là ẢNH CHỤP (FE đọc gợi ý từ PTG truyền vào)."""
    giay_id: int | None = None
    giay_label: str | None = None
    kho_in_dai: int = Field(default=0, ge=0)
    kho_in_rong: int = Field(default=0, ge=0)
    so_mau: int = Field(default=0, ge=0)
    may_id: int | None = None
    so_to_chay: int = Field(default=0, ge=0)
    so_kem: int = Field(default=0, ge=0)
    placements: list[PlacementIn] = Field(default_factory=list)


class PlacementAddIn(BaseModel):
    lenh_sx_id: int
    so_con: int = Field(default=0, ge=0)


class PlacementUpdateIn(BaseModel):
    so_con: int = Field(ge=0)


class GanMayIn(BaseModel):
    may_id: int | None = None


class RoutingStepIn(BaseModel):
    """Thêm/sửa 1 bước routing (kế hoạch §13.2). Tổ mặc định = `cong_doan.department_id` (đổi được)."""
    cong_doan_id: int | None = None
    to_id: int | None = None


class RoutingReorderIn(BaseModel):
    """Đổi thứ tự routing — danh sách id bước theo thứ tự mới (chỉ khi lệnh còn nháp)."""
    step_ids: list[int] = Field(default_factory=list)


# ============================================================ RESPONSES (đọc ORM)
class LenhItemOut(BaseModel):
    """1 BÀI CON của lệnh (ấn phẩm được pick vào lệnh) — giữ chi tiết để không mất khi gom."""
    id: int | None = None            # id bài con (để mở drawer cấu hình override); None = lệnh cũ chưa có bài con
    phieu_thanh_phan_id: int | None
    ten: str
    qty: int
    don_vi_tinh: str


class LenhOut(BaseModel):
    id: int
    order_id: int
    phieu_thanh_phan_id: int | None
    may_id: int | None
    trang_thai: str
    mau_approved_at: datetime | None
    mau_approved_by: int | None
    mau_approved_snapshot: dict | None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class LenhListOut(BaseModel):
    items: list[LenhOut]
    total: int
    page: int
    size: int


# ---------- Handoff: đơn chốt CHỜ lên kế hoạch (§5.1) ----------
class HangChoAnPhamOut(BaseModel):
    """1 ấn phẩm (bản ghi) trong sổ chờ — người kế hoạch PICK. `spec_tom_tat` = quy cách rút gọn (kỹ thuật)."""
    phieu_thanh_phan_id: int | None
    description: str
    qty: int
    don_vi_tinh: str
    spec_tom_tat: str = ""


class HangChoOut(BaseModel):
    """1 đơn đã chốt chờ kế hoạch nhận — kèm ngữ cảnh để kế hoạch cấu hình (đọc sống từ Đơn)."""
    order_id: int
    order_no: str
    khach: str | None = None
    is_rush: bool = False
    delivery_committed_date: date | None = None
    production_note: str | None = None
    an_pham: list[HangChoAnPhamOut] = []


class PlacementOut(BaseModel):
    id: int
    print_form_id: int
    lenh_sx_id: int
    so_con: int
    model_config = ConfigDict(from_attributes=True)


class PrintFormOut(BaseModel):
    id: int
    giay_id: int | None
    giay_label: str | None
    kho_in_dai: int
    kho_in_rong: int
    so_mau: int
    may_id: int | None
    so_to_chay: int
    so_kem: int
    trang_thai: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class PrintFormListOut(BaseModel):
    items: list[PrintFormOut]
    total: int
    page: int
    size: int


class PrintFormDetailOut(PrintFormOut):
    """Tờ in + danh sách xếp bài + các lệnh trên tờ (nuôi màn ghép bài / theo máy)."""
    placements: list[PlacementOut] = []
    lenhs: list[LenhOut] = []


class RoutingStepOut(BaseModel):
    """1 bước routing của lệnh (§13.2) — copy từ job spec, kế hoạch sửa được."""
    id: int
    lenh_sx_id: int
    thu_tu: int
    cong_doan_id: int | None
    to_id: int | None
    ten: str
    model_config = ConfigDict(from_attributes=True)


class LenhDetailOut(LenhOut):
    """Lệnh + bài con + routing + tờ in chứa nó + đích SL."""
    items: list[LenhItemOut] = []
    routing: list[RoutingStepOut] = []
    forms: list[PrintFormOut] = []
    muc_tieu_sl: int = 0


# ---------- Chi tiết ấn phẩm cho DRAWER kế hoạch (CÔ LẬP THƯƠNG MẠI — đã lọc mọi trường giá) ----------
class RoutingGocOut(BaseModel):
    """1 công đoạn routing GỐC của ấn phẩm (đọc từ Tính giá) — không có đơn giá."""
    thu_tu: int
    cong_doan_id: int | None
    ten: str
    nha_cung_cap: str | None = None
    ghi_chu: str | None = None


class VatTuGocOut(BaseModel):
    """1 vật tư thêm của ấn phẩm (vecni bóng/mờ · cán màng…) — tên + ghi chú, KHÔNG giá."""
    ten: str
    ghi_chu: str | None = None


class QuyCachOverrideIn(BaseModel):
    """Override quy cách in tại lệnh (kế thừa báo giá làm mặc định; None = gỡ override, kế thừa lại).
    Chỉ field quy cách in được đổi — KHÔNG có trường giá, KHÔNG đụng báo giá."""
    giay_id: int | None = None
    dai_thanh_pham: int | None = None
    rong_thanh_pham: int | None = None
    kho_thanh_pham: str | None = None
    kho_mo_rong: str | None = None
    tay_gap: str | None = None
    so_to_per_sp: int | None = None
    kho_nguyen_dai: int | None = None
    kho_nguyen_rong: int | None = None
    nguon_giay: str | None = None
    quy_cach_in: str | None = None
    kho_in_dai: int | None = None
    kho_in_rong: int | None = None
    so_con: int | None = None
    con_auto: bool | None = None
    che_ban_loai: str | None = None
    so_mau_a: int | None = None
    so_mau_b: int | None = None


class AnPhamChiTietOut(BaseModel):
    """Chi tiết ĐẦY ĐỦ ấn phẩm cho drawer (mirror phiếu công đoạn) — CHỈ KỸ THUẬT, đã lọc sạch giá.
    Giá trị HIỆU LỰC = báo giá + override tại lệnh. `editable` = mở từ lệnh NHÁP (được sửa)."""
    phieu_thanh_phan_id: int
    lenh_item_id: int | None = None
    editable: bool = False
    overridden: list[str] = []
    # nhận dạng / thành phẩm
    ten: str
    loai_thanh_phan: str
    kho_thanh_pham: str | None = None
    dai_thanh_pham: int
    rong_thanh_pham: int
    kho_mo_rong: str | None = None
    tay_gap: str | None = None
    so_to_per_sp: int
    so_luong: int
    don_vi_tinh: str
    # giấy (đã resolve tên + chủng loại)
    giay_id: int | None = None
    giay_ten: str | None = None
    chung_loai_ten: str | None = None
    gsm: int | None = None
    kho_nguyen: str | None = None
    kho_nguyen_dai: int
    kho_nguyen_rong: int
    nguon_giay: str
    # in & màu
    co_in: bool
    che_ban_loai: str | None = None
    quy_cach_in: str
    kho_in_dai: int
    kho_in_rong: int
    so_con: int
    con_auto: bool
    may_id: int | None = None
    so_mau_a: int
    so_mau_b: int
    so_kem: int
    # số lượng (engine snapshot — None nếu phiếu chưa tính)
    so_luong_can: int | None = None
    so_to_thuc_te: int | None = None
    so_to_sau_in: int | None = None
    so_to_nguyen: int | None = None
    con_tren_to: int | None = None
    bu_hao_auto: int | None = None
    bu_hao_so_to: int
    hao_so_to: int
    tinh_bu_hao_cd: bool
    # note kỹ thuật theo sản phẩm + vật tư + routing
    ghi_chu_ky_thuat: str | None = None
    vat_tu: list[VatTuGocOut] = []
    routing: list[RoutingGocOut] = []


