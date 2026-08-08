"""Pydantic schemas — Công đoạn (danh mục)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CongDoanDauViecIn(BaseModel):
    piece_rate_id: int
    # `nang_suat_nguoi_gio` = mức TRUNG BÌNH (số chảy vào công thức thời lượng); min/max chỉ để ra
    # khoảng nhanh–chậm, để trống thì ba mức bằng nhau. `don_vi_nang_suat` là nhãn khai báo.
    nang_suat_nguoi_gio: float = Field(gt=0)
    nang_suat_nguoi_gio_min: float | None = Field(default=None, gt=0)
    nang_suat_nguoi_gio_max: float | None = Field(default=None, gt=0)
    don_vi_nang_suat: str | None = Field(default=None, max_length=32)
    # Ba mốc nhân lực phải xếp đúng thứ tự: tối thiểu ≤ tiêu chuẩn ≤ tối đa (service kiểm).
    so_nguoi_toi_thieu: int = Field(default=1, ge=1)
    so_nguoi_tieu_chuan: int = Field(ge=1)
    so_nguoi_toi_da: int = Field(ge=1)
    is_default: bool = False


class CongDoanDauViecRow(CongDoanDauViecIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class CongDoanIn(BaseModel):
    ma: str = Field(min_length=1, max_length=30)
    ten: str = Field(min_length=1, max_length=150)
    ten_hien_thi: str | None = None
    # Đơn vị vào/ra trên dòng giấy (hệ số quy đổi lấy từ phiếu, không khai ở đây). None = bước
    # không chạm giấy. Cặp hợp lệ do `cong_doan_service` kiểm.
    don_vi_vao: str | None = None
    don_vi_ra: str | None = None
    kieu_bu_hao: str = "khong"
    bu_hao_id: int | None = None
    so_to_bu_hao: int = Field(default=50, ge=0)
    nhom: str
    # Nhóm máy (tên ở danh mục `nhom_may`) làm được công đoạn này — chặn gán máy sai loại ở bài
    # ghép. None/[] = không ràng buộc.
    nhom_may_cho_phep: list[str] | None = None
    department_id: int | None = None
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
    dau_viec_dinh_muc: list[CongDoanDauViecIn] = Field(default_factory=list)


class CongDoanRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ma: str
    ten: str
    ten_hien_thi: str | None = None
    don_vi_vao: str | None = None
    don_vi_ra: str | None = None
    kieu_bu_hao: str = "khong"
    bu_hao_id: int | None = None
    so_to_bu_hao: int = 50
    nhom: str
    nhom_may_cho_phep: list[str] | None = None
    department_id: int | None = None
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
    dau_viec_dinh_muc: list[CongDoanDauViecRow] = Field(default_factory=list)
    updated_at: datetime | None = None


class CongDoanListOut(BaseModel):
    items: list[CongDoanRow]
    total: int
    page: int
    size: int


class RefOption(BaseModel):
    """Một mục cho dropdown 'ref' của màn cấu hình (khớp {id, ma, ten})."""
    id: int
    ma: str
    ten: str


class RefOptionListOut(BaseModel):
    items: list[RefOption]
