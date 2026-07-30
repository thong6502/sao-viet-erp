"""Pydantic models cho API Đơn giá khoán (module `luong`, nhịp 2)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


# --- đơn giá khoán ----------------------------------------------------------


class RateIn(BaseModel):
    group_name: str = Field(min_length=1, max_length=40)
    department_id: int | None = None
    code: str | None = Field(default=None, max_length=20)
    name: str = Field(min_length=1, max_length=255)
    cong_doan: str | None = Field(default=None, max_length=30)   # cột CŨ (1 mã) — giữ tương thích
    # Nhiều công đoạn dùng chung 1 đầu việc; rỗng = áp cho mọi công đoạn của tổ.
    cong_doan_mas: list[str] = Field(default_factory=list)
    # Trục quy đổi SL bước → đơn vị đơn giá (bộ `PRICING_BASIS` của công đoạn). None = chưa khai.
    tinh_theo: str | None = Field(default=None, max_length=32)
    # Gõ TỰ DO — không enum. Service chuẩn hoá (trim + gộp chính tả hoa/thường) trước khi lưu.
    unit: str = Field(default="khác", max_length=24)
    unit_price: float = Field(ge=0)
    note: str | None = Field(default=None, max_length=255)
    is_active: bool = True


class RateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_name: str
    department_id: int | None = None
    code: str | None = None
    name: str
    cong_doan: str | None = None
    cong_doan_mas: list[str] = Field(default_factory=list)
    tinh_theo: str | None = None
    unit: str
    unit_price: float
    note: str | None = None
    is_active: bool

    @field_validator("cong_doan_mas", mode="before")
    @classmethod
    def _null_thanh_rong(cls, v):
        """Cột JSON mới → dòng đơn giá khai TRƯỚC migration có `NULL`, mà `default_factory` chỉ áp
        khi THIẾU key chứ không khi giá trị là None → response 500 (đã vỡ thật ở màn Lương khoán:
        3 dòng "Bài in A/B/C" của seed cũ làm cả danh sách trắng). Đổi None → [] tại cửa ra."""
        return [] if v is None else v


class RatesOut(BaseModel):
    items: list[RateOut]


class UnitsOut(BaseModel):
    """Gợi ý cho ô "Đơn vị" — KHÔNG phải whitelist, gõ ngoài danh sách vẫn lưu được."""

    items: list[str]


# --- Bậc thưởng/phạt tổ trưởng theo tỷ lệ hàng lỗi (chủ 29/07/2026) ---------


class LeaderBracketIn(BaseModel):
    """Một bậc. `up_to_defect_pct = null` = bậc CUỐI ('trở lên'), hứng mọi tỷ lệ cao hơn."""

    up_to_defect_pct: float | None = Field(default=None, ge=0, le=100)
    # DƯƠNG = thưởng · ÂM = phạt. Cho phép âm là CỐ Ý — đó là tiền phạt.
    rate_pct: float = Field(ge=-100, le=100)
    note: str | None = Field(default=None, max_length=255)


class LeaderBracketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    department_id: int
    seq: int
    up_to_defect_pct: float | None = None
    rate_pct: float
    note: str | None = None


class LeaderBracketsIn(BaseModel):
    """Thay CẢ BỘ mốc của một tổ. Danh sách RỖNG = tổ này không áp thưởng/phạt tổ trưởng."""

    department_id: int
    items: list[LeaderBracketIn] = []


class LeaderBracketsOut(BaseModel):
    department_id: int
    items: list[LeaderBracketOut]
