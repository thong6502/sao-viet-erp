"""Lọc danh sách đơn theo THÁNG TẠO (chủ 23/09/2026: *"lọc theo tháng là lọc theo ngày tạo nha"*).

`created_at` lưu UTC, còn "tháng 9" của người dùng là tháng 9 GIỜ VIỆT NAM: đơn gửi lúc 6h sáng
01/10 giờ VN vẫn là 23h 30/09 UTC — cắt theo UTC là đơn đó rơi nhầm sang tháng 9. Nên đổi mốc
đầu/cuối tháng giờ VN ra UTC rồi mới so.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

_VN = timezone(timedelta(hours=7))
_THANG = re.compile(r"^(\d{4})-(\d{2})$")


def khoang_tao_theo_thang(thang: str | None) -> tuple[datetime, datetime] | None:
    """`"2026-09"` → (00:00 01/09 giờ VN, 00:00 01/10 giờ VN) đổi ra UTC, nửa mở [tu, den).
    Trống ⇒ None (không lọc). Sai dạng ⇒ ValueError — service tự đổi ra lỗi 400 của mình."""
    if not thang:
        return None
    m = _THANG.match(thang.strip())
    if not m or not 1 <= int(m.group(2)) <= 12:
        raise ValueError("Tháng phải có dạng YYYY-MM, vd 2026-09.")
    nam, th = int(m.group(1)), int(m.group(2))
    tu = datetime(nam, th, 1, tzinfo=_VN)
    den = datetime(nam + (th == 12), th % 12 + 1, 1, tzinfo=_VN)
    return tu.astimezone(timezone.utc), den.astimezone(timezone.utc)
