"""Pydantic models cho API Thưởng/phạt tổ trưởng (module `luong`, nhịp 2).

⚠️ `RateIn` · `RateOut` · `RatesOut` · `UnitsOut` gỡ ngày 17/08/2026 cùng năm route `/khoan/rates`
và `/khoan/units`: bảng đơn giá thành danh mục "Công việc khoán", schema của nó ở
`schemas/cong_viec_khoan.py` (tên field theo cột mới `ma` · `ten` · `active`).
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


# --- Bậc thưởng/phạt tổ trưởng: KHOẢNG SẢN LƯỢNG × tỷ lệ hàng lỗi (chủ 04/09/2026) ---
#
# Hai điều kiện trên cùng một dòng (chủ: *"nó phải sét 2 điều kiện 1 là khoảng sản lượng, 2 là tỷ
# lệ lỗi"*). `min_output_qty` GỠ cùng bảng `piece_leader_bonus_settings` (mg `0262`): khoảng sản
# lượng thấp nhất khai `rate_pct = 0` đã thay đúng việc của cửa chặn cũ.


class LeaderBracketIn(BaseModel):
    """Một bậc = một ô của lưới (khoảng sản lượng × trần tỷ lệ lỗi).

    `sl_den = null` = khoảng sản lượng cuối (∞) · `up_to_defect_pct = null` = dòng 'trở lên' của
    khoảng đó, hứng mọi tỷ lệ lỗi cao hơn."""

    # Khoảng nửa mở `sl_tu < sản lượng <= sl_den` — cùng quy ước với bậc bù hao.
    sl_tu: float = Field(default=0, ge=0)
    sl_den: float | None = Field(default=None, ge=0)
    up_to_defect_pct: float | None = Field(default=None, ge=0, le=100)
    # DƯƠNG = thưởng · ÂM = phạt. Cho phép âm là CỐ Ý — đó là tiền phạt.
    rate_pct: float = Field(ge=-100, le=100)
    note: str | None = Field(default=None, max_length=255)


class LeaderBracketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    department_id: int
    seq: int
    sl_tu: float = 0
    sl_den: float | None = None
    up_to_defect_pct: float | None = None
    rate_pct: float
    note: str | None = None


class LeaderBracketsIn(BaseModel):
    """Thay CẢ BỘ bậc của một tổ. Danh sách RỖNG = tổ này không áp thưởng/phạt tổ trưởng."""

    department_id: int
    items: list[LeaderBracketIn] = []


class LeaderBracketsOut(BaseModel):
    department_id: int
    items: list[LeaderBracketOut]
