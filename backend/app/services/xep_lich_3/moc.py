"""Cầu MỘT CHIỀU từ Xếp lịch 3 sang bốn chỗ tiêu thụ lịch ngoài màn xếp lịch.

Màn 3 chỉ lưu MỘT con số cho cả lệnh (`xep_lich_lenh.bat_dau_at`) — không có dòng `xep_lich_cong_doan`
nào. Nhưng bốn nơi dưới đây vẫn cần mốc TỪNG BƯỚC, và chúng có thật chứ không phải nhu cầu bịa:

- `giu_cho_repo.chu_the_da_xep_lich` — cửa chặn nhả chỗ giữ vật tư.
- `ke_hoach_vat_tu_service` — "ngày cần" của từng dòng giấy suy ngược từ giờ bước dùng nó.
- `may_trang_thai.lenh_dang_chay` — cột Trạng thái ở màn Máy: máy này đang chạy lệnh nào.
- `san_xuat/snapshot` — `du_kien_bat_dau` / `du_kien_ket_thuc` của thẻ việc dưới xưởng.

LUẬT chung cho cả bốn: **có dòng trong `xep_lich_lenh` thì tin mốc dẫn xuất; không có thì giữ
nguyên đường cũ** (`xep_lich_cong_doan`). Nhờ vậy hai màn chạy song song được — lệnh xếp ở màn nào
thì nơi tiêu thụ đọc theo màn đó, không có lệnh nào rơi vào khoảng giữa.

Dẫn xuất chứ KHÔNG lưu: mốc bước là hàm của (giờ bắt đầu × routing × lịch xưởng), lưu thêm một bản
là đẻ ra nguồn thứ hai sẽ lệch ngay lần đầu ai đó sửa routing.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models.xep_lich_lenh import XepLichLenh


def lsx_da_xep(db: Session, lsx_ids: list[int] | None = None) -> set[int]:
    """`lsx_id` ĐÃ có mốc ở màn 3. Truyền `lsx_ids` để cắt bớt, bỏ trống = tất cả."""
    q = select(XepLichLenh.lsx_id)
    if lsx_ids is not None:
        if not lsx_ids:
            return set()
        q = q.where(XepLichLenh.lsx_id.in_(lsx_ids))
    return set(db.execute(q).scalars())


def moc_theo_buoc(db: Session, lsx_ids: list[int]) -> dict[int, tuple[datetime, datetime]]:
    """`{lsx_cong_doan_id: (bắt_đầu, kết_thúc)}` cho các lệnh ĐÃ xếp ở màn 3.

    Lệnh chưa xếp không có mặt trong kết quả — chỗ gọi cứ `.get()` rồi rơi về đường cũ.
    """
    if not lsx_ids:
        return {}
    from ...repositories.xep_lich_lenh_repo import XepLichLenhRepository
    from .service import XepLich3Service

    svc = XepLich3Service(db, XepLichLenhRepository(db))
    ra: dict[int, tuple[datetime, datetime]] = {}
    for buocs in svc.moc_cong_doan(list(lsx_ids)).values():
        for b in buocs:
            ra[b.lsx_cong_doan_id] = (b.bat_dau, b.ket_thuc)
    return ra
