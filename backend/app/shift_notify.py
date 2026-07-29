"""Đẩy thông báo "ca làm việc của bạn vừa bị đổi" tới đúng người bị đổi.

Tách khỏi service vì có tới **5 đường** đổi ca (lưới phân ca · panel Gán ca · gán hàng loạt ·
sửa hồ sơ NV · gỡ mốc) nằm ở hai service khác nhau — mỗi chỗ tự viết một kiểu đẩy là bắt đầu
lệch nhau (chỗ gộp, chỗ bắn từng dòng; chỗ đếm, chỗ không).

Nguyên tắc sản phẩm (CLAUDE.md): thông báo NỘI BỘ phải REAL-TIME — badge tự nhảy + toast tức
thì, không bắt người ta F5.
"""
from __future__ import annotations

from .realtime import hub


def push_shift_changes(logs) -> tuple[int, int]:
    """Đẩy SSE cho các dòng `EmployeeShiftChangeLog` VỪA GHI. Trả `(đã báo, chưa báo được)`.

    ⚠️ **Gọi SAU `commit()`.** Bắn trước là báo cho người lao động một thay đổi còn có thể
    rollback ngay sau đó — mất niềm tin vào chuông nhanh hơn là không có chuông.

    Gộp theo NGƯỜI, mỗi người MỘT sự kiện dù bị đổi 30 ngày: lưới phân ca hay được bấm Lưu cả
    tháng một lần, bắn từng dòng là 30 toast liên tiếp vào mặt một người.

    `notified_user_id = None` nghĩa là nhân viên **không có tài khoản đăng nhập** (công nhân
    xưởng) ⇒ không có chỗ nào để nhận. Đếm riêng để màn Khai ca nói thẳng "N người chưa báo
    được" thay vì im lặng bỏ qua — chốt của chủ 28/07/2026.
    """
    by_user: dict[int, int] = {}
    not_notified = 0
    for log in logs:
        uid = getattr(log, "notified_user_id", None)
        if uid is None:
            not_notified += 1
            continue
        by_user[uid] = by_user.get(uid, 0) + 1
    for uid, n in by_user.items():
        hub.publish(uid, {"type": "shift_changed", "count": n})
    return sum(by_user.values()), not_notified
