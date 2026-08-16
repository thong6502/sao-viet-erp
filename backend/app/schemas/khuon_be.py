"""Pydantic schemas — Danh mục Khuôn bế (khai báo nơi lưu trữ)."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class KhuonBeIn(BaseModel):
    ma: str | None = Field(default=None, max_length=30)  # tạo mới: bỏ trống → backend tự sinh KB-####
    ten: str = Field(min_length=1, max_length=200)
    #: Khách đặt con dao + loại dao (mg 0205) — hai chiều lọc của ô chọn khuôn ở bước lệnh.
    khach_hang_id: int | None = None
    loai: str | None = None
    so_ke: str | None = None
    tinh_trang: str = "dang_dung"
    #: Chỉ có nghĩa với `tinh_trang='dang_dat_lam'` (mg 0177) — ngày này hiện ngay tại bước dùng
    #: khuôn ở lệnh sản xuất để người xếp việc biết chưa chạy được.
    ngay_ve_du_kien: date | None = None
    ghi_chu: str | None = None
    active: bool = True


class KhuonBeRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ma: str
    ten: str
    khach_hang_id: int | None = None
    #: Tên khách — server ghép sẵn để màn khỏi phải tra danh mục Khách hàng cho từng dòng.
    khach_hang_ten: str | None = None
    loai: str | None = None
    so_ke: str | None = None
    tinh_trang: str
    ngay_ve_du_kien: date | None = None
    ghi_chu: str | None = None
    active: bool
    updated_at: datetime | None = None


class KhuonBeListOut(BaseModel):
    items: list[KhuonBeRow]
    total: int
    page: int
    size: int
    # Số khuôn theo tình trạng — nuôi số trên tab lọc (màn chỉ cầm 20 dòng, không tự đếm được).
    facets: dict[str, int] = {}
