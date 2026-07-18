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
    """Bung lệnh từ đơn đã chốt (idempotent theo đơn·ấn phẩm)."""
    order_id: int


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


class GhiSanLuongIn(BaseModel):
    """Tổ trưởng ghi sản lượng 1 công đoạn (số đạt + số hỏng). Người ghi lấy từ token."""
    cong_doan_id: int | None = None
    to_id: int | None = None
    so_dat: int = Field(default=0, ge=0)
    so_hong: int = Field(default=0, ge=0)


class BanGiaoIn(BaseModel):
    cong_doan_tu_id: int | None = None
    cong_doan_toi_id: int | None = None
    so_giao: int = Field(default=0, ge=0)
    to_giao_id: int | None = None
    to_nhan_id: int | None = None


class GhiLoiQcIn(BaseModel):
    cong_doan_id: int | None = None
    to_bi_quy_id: int | None = None
    anh_url: str | None = None
    mo_ta: str | None = None


class NhapKhoIn(BaseModel):
    """`so_luong_nhap` = TỔNG SL thành phẩm đã nhập kho cho lệnh (caller cộng dồn từ phiếu Kho thật)."""
    so_luong_nhap: int = Field(ge=0)


class RoutingStepIn(BaseModel):
    """Thêm/sửa 1 bước routing (kế hoạch §13.2). Tổ mặc định = `cong_doan.department_id` (đổi được)."""
    cong_doan_id: int | None = None
    to_id: int | None = None


class RoutingReorderIn(BaseModel):
    """Đổi thứ tự routing — danh sách id bước theo thứ tự mới (chỉ khi lệnh còn nháp)."""
    step_ids: list[int] = Field(default_factory=list)


# ============================================================ RESPONSES (đọc ORM)
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
    """1 ấn phẩm sẽ được đề lệnh khi bấm 'Lên kế hoạch' (dòng đơn có `phieu_thanh_phan_id`)."""
    phieu_thanh_phan_id: int | None
    description: str
    qty: int
    don_vi_tinh: str


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


class SanLuongOut(BaseModel):
    id: int
    lenh_sx_id: int
    cong_doan_id: int | None
    to_id: int | None
    so_dat: int
    so_hong: int
    nguoi_ghi: int | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class BanGiaoOut(BaseModel):
    id: int
    lenh_sx_id: int
    cong_doan_tu_id: int | None
    cong_doan_toi_id: int | None
    so_giao: int
    to_giao_id: int | None
    to_nhan_id: int | None
    giao_at: datetime
    nhan_at: datetime | None
    model_config = ConfigDict(from_attributes=True)


class QcDefectOut(BaseModel):
    id: int
    lenh_sx_id: int
    cong_doan_id: int | None
    to_bi_quy_id: int | None
    anh_url: str | None
    mo_ta: str | None
    trang_thai: str
    created_at: datetime
    xac_nhan_at: datetime | None
    model_config = ConfigDict(from_attributes=True)


class RoutingStepOut(BaseModel):
    """1 bước routing của lệnh (§13.2) — copy từ job spec, kế hoạch sửa được khi còn `cho`."""
    id: int
    lenh_sx_id: int
    thu_tu: int
    cong_doan_id: int | None
    to_id: int | None
    ten: str
    trang_thai: str
    bat_dau_at: datetime | None
    hoan_thanh_at: datetime | None
    model_config = ConfigDict(from_attributes=True)


class LenhDetailOut(LenhOut):
    """Lệnh + routing + tờ in chứa nó + log sản lượng/bàn giao/QC + đích SL & Σ đạt (nuôi màn tracking)."""
    routing: list[RoutingStepOut] = []
    forms: list[PrintFormOut] = []
    san_luong: list[SanLuongOut] = []
    ban_giao: list[BanGiaoOut] = []
    qc: list[QcDefectOut] = []
    muc_tieu_sl: int = 0
    tong_dat: int = 0


class NhapKhoOut(BaseModel):
    """Kết quả ghi nhận nhập kho thành phẩm → suy trạng thái lệnh / đơn."""
    lenh: LenhOut
    muc_tieu_sl: int
    so_luong_nhap: int
    lenh_xong: bool
    order_production_done: bool


# ============================================================ TỔ VIEW (§13.3–13.4)
class ToNodeOut(BaseModel):
    """1 tổ/phòng thuộc khối SẢN XUẤT + đếm việc (bảng tổ §13.3). FE dựng cây từ `parent_id`."""
    id: int
    name: str
    code: str
    parent_id: int | None
    head_user_id: int | None
    la_san_xuat: bool
    so_lenh: int = 0        # số lệnh đang chạy tổ có việc
    so_den_luot: int = 0    # số lệnh ĐẾN LƯỢT tổ (bước hiện hành thuộc tổ)


class ToLenhOut(BaseModel):
    """Lệnh 'của tổ' (§13.4) — tóm tắt để tổ chọn vào màn thực thi. FE resolve tên đơn/ấn phẩm."""
    id: int
    order_id: int
    phieu_thanh_phan_id: int | None
    trang_thai: str
    den_luot: bool               # bước hiện hành thuộc tổ đang xem
    cur_thu_tu: int | None       # bước đến lượt (ai đang giữ)
    cur_ten: str | None
    cur_to_id: int | None
    so_buoc: int
    so_buoc_xong: int
    muc_tieu_sl: int
    tong_dat: int
    updated_at: datetime
