"""Pydantic models cho API Thưởng/phạt tổ trưởng (module `luong`, nhịp 2).

⚠️ `RateIn` · `RateOut` · `RatesOut` · `UnitsOut` gỡ ngày 17/08/2026 cùng năm route `/khoan/rates`
và `/khoan/units`: bảng đơn giá thành danh mục "Công việc khoán", schema của nó ở
`schemas/cong_viec_khoan.py` (tên field theo cột mới `ma` · `ten` · `active`).
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


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
    # Ngưỡng SẢN LƯỢNG của tổ trong kỳ để được xét thưởng/phạt. `0` = không gác.
    # Đi CÙNG GÓI với `items` vì màn chỉ có một nút Lưu — tách ra là lưu được nửa này mất nửa kia.
    min_output_qty: float = 0
    items: list[LeaderBracketIn] = []


class LeaderBracketsOut(BaseModel):
    department_id: int
    min_output_qty: float = 0
    items: list[LeaderBracketOut]
