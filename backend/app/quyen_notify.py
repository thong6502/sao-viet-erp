"""Đẩy "quyền của bạn vừa đổi" tới đúng những người đang giữ bộ quyền đó.

Máy chủ gác quyền bằng DB ở MỖI request nên đổi quyền là có hiệu lực ngay ở phía máy chủ. Còn
giao diện chỉ hỏi bộ quyền một lần lúc vào phiên: không đẩy thì người bị rút quyền vẫn thấy menu
cũ (bấm vào mới ăn 403), người vừa được cấp thì không thấy gì tới khi F5.

Tách khỏi service vì có nhiều đường đổi quyền nằm ở ba service khác nhau: lưu ma trận vai trò ·
gán vai trò (đơn + hàng loạt) · đổi phòng trên màn Người dùng · điều chuyển nhân sự (gỡ vai trò).
"""
from __future__ import annotations

from .realtime import hub

SU_KIEN_QUYEN_DOI = "quyen_doi"


def bao_quyen_doi(user_ids) -> int:
    """Đẩy MỘT sự kiện `quyen_doi` cho mỗi tài khoản. Trả số tài khoản đã đẩy.

    ⚠️ **Gọi SAU khi đã commit.** Giao diện nhận sự kiện là hỏi lại bộ quyền ngay — bắn trước commit
    thì nó đọc đúng bộ quyền CŨ rồi đứng yên ở đó.

    Sự kiện không mang nội dung quyền: người nhận tự hỏi lại `/api/auth/permissions`, khỏi lo gói
    tin cũ đến sau gói tin mới."""
    ids = {int(u) for u in (user_ids or []) if u is not None}
    for uid in ids:
        hub.publish(uid, {"type": SU_KIEN_QUYEN_DOI})
    return len(ids)
