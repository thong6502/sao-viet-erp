"""`may_id` ở MỌI bảng phải là khoá MỀM (Integer trần), không FK cứng.

⚠️ ĐÃ VỠ THẬT — 25/08/2026, `san_xuat_cong_viec.may_id`.

Hệ có HAI danh mục máy sống chung: `machines` (đời tính giá, ít dòng) và `may_thiet_bi` (danh
mục ĐANG CHẠY, id chạy xa hơn hẳn). Máy của một bước lấy từ `may_thiet_bi`, nên bảng nào khai
FK cứng `ForeignKey("machines.id")` cho `may_id` là tự đặt mìn: bước nào chạy máy có id ngoài
dải của `machines` thì INSERT nổ `ForeignKeyViolation`.

Vụ thật: phát hành LSX26-0029 nổ giữa giao dịch (`Key (may_id)=(27) is not present in table
"machines"`) và để lại lệnh KẸT — `da_phat_hanh` nhưng không sinh nổi một công việc nào; người
dùng thấy màn báo "đủ điều kiện phát hành" mà bấm gì cũng chửi. Test cũ không đỡ được vì fixture
dựng máy thẳng vào `machines` nên id luôn khớp, còn SQLite thì không siết FK.

Guard này rẻ (đọc metadata, không chạy app) và bắt đúng lúc ai đó khai lại FK cứng.
"""
from __future__ import annotations

import app.models  # noqa: F401  -- import để đăng ký mọi bảng lên Base.metadata
from app.db import Base


def test_may_id_luon_la_khoa_mem():
    pham = []
    for bang in Base.metadata.tables.values():
        cot = bang.columns.get("may_id")
        if cot is not None and cot.foreign_keys:
            dich = ", ".join(sorted(fk.target_fullname for fk in cot.foreign_keys))
            pham.append(f"`{bang.name}.may_id` đang FK cứng → {dich}")

    assert not pham, (
        "may_id phải neo MỀM (Integer trần + ghi chú `# → may_thiet_bi.id`) vì hệ có hai danh "
        "mục máy lệch id — xem docstring đầu file:\n  " + "\n  ".join(pham)
    )
