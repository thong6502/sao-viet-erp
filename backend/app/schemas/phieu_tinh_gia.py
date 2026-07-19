"""Pydantic schemas — Phiếu tính giá THEO THÀNH PHẦN (component-based costing).

Cây lồng: Phiếu → thanh_phans[] (thành phần / tờ giấy) → thanh_phams[] (dòng gia công sau in).
`PhieuTinhGiaOut` map `result_json → result`, `warnings_json → warnings`. Mọi trường đầu vào
optional (cho phép tạo nháp trắng / thành phần thiếu). SAVE = engine tính lại + ảnh chụp.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer


# ============================ THÀNH PHẨM (finishing op) ============================
class ThanhPhamIn(BaseModel):
    """1 dòng gia công sau in (đầu vào — mọi trường optional)."""
    thu_tu: int | None = None
    cong_doan_id: int | None = None
    ten: str | None = None
    don_gia: float | None = None
    so_luong: int | None = Field(default=None, ge=0)
    bu_hao: bool | None = None
    so_mat: int | None = None
    so_vi_tri: int | None = None
    dien_tich: float | None = None
    nha_cung_cap: str | None = None
    ghi_chu: str | None = None


class ThanhPhamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    thanh_phan_id: int
    thu_tu: int
    cong_doan_id: int | None = None
    ten: str
    don_gia: float
    so_luong: int
    bu_hao: bool
    so_mat: int
    so_vi_tri: int
    dien_tich: float
    nha_cung_cap: str | None = None
    ghi_chu: str | None = None


# ============================ VẬT TƯ (nguyên vật liệu thêm) ============================
class VatTuLineIn(BaseModel):
    """1 dòng vật tư in ấn thêm tay (đầu vào — mọi trường optional)."""
    thu_tu: int | None = None
    vat_tu_id: int | None = None
    ten: str | None = None
    don_gia: float | None = None
    so_luong: int | None = Field(default=None, ge=0)
    ghi_chu: str | None = None


class VatTuLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    thanh_phan_id: int
    thu_tu: int
    vat_tu_id: int | None = None
    ten: str
    don_gia: float
    so_luong: int
    ghi_chu: str | None = None


# ============================ THÀNH PHẦN (paper component) ============================
class ThanhPhanIn(BaseModel):
    """1 thành phần (tờ giấy) — đầu vào (mọi trường optional)."""
    thu_tu: int | None = None
    loai_thanh_phan: str | None = None
    ten: str | None = None
    kho_thanh_pham: str | None = None
    dai_thanh_pham: int | None = None
    rong_thanh_pham: int | None = None
    kho_mo_rong: str | None = None
    tay_gap: str | None = None
    so_to_per_sp: int | None = Field(default=None, ge=1)
    so_luong: int | None = Field(default=None, ge=0)   # SL của sản phẩm này
    don_vi_tinh: str | None = Field(default=None, max_length=30)   # ĐVT sản phẩm (text tự do)
    loai_san_pham_id: int | None = None
    # Giấy
    giay_id: int | None = None
    kho_nguyen: str | None = None
    kho_nguyen_dai: int | None = None
    kho_nguyen_rong: int | None = None
    don_gia_giay: float | None = None
    don_gia_don_vi: str | None = None
    nguon_giay: str | None = None
    bu_hao_so_to: int | None = None
    hao_so_to: int | None = None
    tinh_bu_hao_cd: bool | None = None
    chua_xen: float | None = None
    chua_tay_ke: float | None = None
    chua_nhip: float | None = None
    chua_duoi: float | None = None
    chua_ca_gay: float | None = None
    # In
    co_in: bool | None = None
    che_ban_loai: str | None = None
    che_ban_don_gia: float | None = None
    quy_cach_in: str | None = None
    kho_in_dai: int | None = None
    kho_in_rong: int | None = None
    so_con: int | None = Field(default=None, ge=1)
    con_auto: bool | None = None
    may_id: int | None = None
    don_gia_cong_in: float | None = None
    # Màu (gộp — chỉ số màu mỗi mặt)
    so_mau_a: int | None = None
    so_mau_b: int | None = None
    ghi_chu_ky_thuat: str | None = None   # note KỸ THUẬT/SX theo sản phẩm (canh màu/kẽm cũ/bù hao) → drawer lệnh
    thanh_phams: list[ThanhPhamIn] | None = None
    vat_tus: list[VatTuLineIn] | None = None


class ThanhPhanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    phieu_id: int
    thu_tu: int
    loai_thanh_phan: str
    ten: str
    kho_thanh_pham: str | None = None
    dai_thanh_pham: int
    rong_thanh_pham: int
    kho_mo_rong: str | None = None
    tay_gap: str | None = None
    so_to_per_sp: int
    so_luong: int
    don_vi_tinh: str = "cái"
    loai_san_pham_id: int | None = None
    # Giấy
    giay_id: int | None = None
    kho_nguyen: str | None = None
    kho_nguyen_dai: int = 0
    kho_nguyen_rong: int = 0
    don_gia_giay: float
    don_gia_don_vi: str
    nguon_giay: str
    bu_hao_so_to: int
    hao_so_to: int
    tinh_bu_hao_cd: bool = True
    chua_xen: float
    chua_tay_ke: float
    chua_nhip: float
    chua_duoi: float
    chua_ca_gay: float
    # In
    co_in: bool
    che_ban_loai: str | None = None
    che_ban_don_gia: float
    quy_cach_in: str
    kho_in_dai: int
    kho_in_rong: int
    so_con: int
    con_auto: bool
    may_id: int | None = None
    don_gia_cong_in: float
    # Màu (gộp)
    so_mau_a: int
    so_mau_b: int
    ghi_chu_ky_thuat: str | None = None   # note KỸ THUẬT/SX theo sản phẩm → drawer lệnh
    gia_von_tp: float
    thanh_phams: list[ThanhPhamOut] = Field(default_factory=list)
    vat_tus: list[VatTuLineOut] = Field(default_factory=list)


# ============================ PHIẾU (header) ============================
class PhieuTinhGiaCreate(BaseModel):
    """Tạo phiếu — mọi trường optional (cho phép nháp trắng)."""
    ten_san_pham: str | None = None
    kho_thanh_pham: str | None = None
    loai_san_pham_id: int | None = None
    so_luong: int | None = Field(default=None, ge=0)
    ghi_chu: str | None = None
    thanh_phans: list[ThanhPhanIn] | None = None


class PhieuTinhGiaUpdate(BaseModel):
    """Sửa phiếu — replace-all con (nếu gửi thanh_phans thì thay toàn bộ)."""
    ten_san_pham: str | None = None
    kho_thanh_pham: str | None = None
    loai_san_pham_id: int | None = None
    so_luong: int | None = Field(default=None, ge=0)
    ghi_chu: str | None = None
    thanh_phans: list[ThanhPhanIn] | None = None


class PhieuTinhGiaOut(BaseModel):
    """Phiếu đầy đủ — kèm thành phần lồng + result (ảnh chụp engine) + warnings."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    ma: str
    ten_san_pham: str
    kho_thanh_pham: str | None = None
    loai_san_pham_id: int | None = None
    so_luong: int
    tong_gia_von: float
    gia_von_don: float
    result: dict | None = Field(default=None, validation_alias="result_json")
    warnings: list[str] | None = Field(default=None, validation_alias="warnings_json")
    ktv: str | None = None
    ghi_chu: str | None = None
    thanh_phans: list[ThanhPhanOut] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PhieuTinhGiaListItem(BaseModel):
    """Dòng nhẹ cho bảng — KHÔNG kèm result_json / thành phần."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    ma: str
    ten_san_pham: str
    loai_san_pham_id: int | None = None
    kho_thanh_pham: str | None = None
    so_luong: int
    gia_von_don: float
    tong_gia_von: float
    ktv: str | None = None
    so_thanh_phan: int = 0
    ngay: datetime | None = Field(default=None, validation_alias="created_at")

    @field_serializer("ngay")
    def _ser_ngay(self, v: datetime | None) -> str | None:
        return v.date().isoformat() if v is not None else None


class PhieuTinhGiaListOut(BaseModel):
    items: list[PhieuTinhGiaListItem]
    total: int


# ============================ NHẬT KÝ HOẠT ĐỘNG ============================
class PtgActivityItem(BaseModel):
    """1 dòng nhật ký hoạt động (ai làm gì · khi nào) của 1 phiếu tính giá."""
    action: str
    actor_name: str | None = None
    detail: str
    at: datetime


class PtgActivityOut(BaseModel):
    items: list[PtgActivityItem]
