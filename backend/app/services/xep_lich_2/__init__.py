"""Gói Xếp lịch 2 — engine v2 độc lập, LƯU CHUNG một bảng `xep_lich_cong_doan` với màn cũ.

Chia tầng theo spec §9.2:
- `constraint`  — luật thời gian THUẦN (không DB): chạy liên tục · ngoài ca · đè khoá · trùng máy ·
  vượt quân số · trước ngày vật tư.
- `context`     — bóc dữ liệu sống (ca, vùng khoá, việc đã xếp, quân số, ngày lễ) cho `constraint`.
- `release`     — cửa phát hành DÙNG CHUNG (vật tư đủ mới phát hành).
- `suggestion`  — gợi ý máy (bọc mỏng engine cũ, không lọc năng lực).
- `service`     — điều phối: ráp ba tầng trên, khoá lạc quan theo `updated_at`, chặn theo mức.
"""
from . import constraint
from .constraint import MUC_CANH_BAO, MUC_CHAN_DAT_LICH, MUC_CHAN_PHAT_HANH
from .service import (
    XepLich2Blocked, XepLich2Conflict, XepLich2Error, XepLich2Service,
)

__all__ = [
    "constraint",
    "MUC_CANH_BAO", "MUC_CHAN_DAT_LICH", "MUC_CHAN_PHAT_HANH",
    "XepLich2Blocked", "XepLich2Conflict", "XepLich2Error", "XepLich2Service",
]
