"""Phạm vi dữ liệu của hai màn chỉ-đọc — bám `orders.sale_user_id`.

KHÁC `routers/lsx.py::_owner_ids_for_scope`, và khác một cách CỐ Ý. Ở đó phạm vi tính theo
`lsx.nguoi_phu_trach_id` / `lsx.created_by` — "lệnh này ai LÀM". Ở đây là "lệnh này bán cho
ai, ai bán" — câu hỏi của Sale, Trưởng phòng KD, Giám đốc. Dùng chung một hàm cho cả hai
nghĩa thì một trong hai bên sai âm thầm.

Lệnh CHƯA phát hành không thuộc phạm vi của bất kỳ ai ở đây: hai màn này nói về việc đã thả
xuống xưởng. Lệnh nháp/đang lập vẫn xem ở màn Kế hoạch sản xuất.
"""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models.lsx import TT_DA_PHAT_HANH, Lsx
from ...models.order import Order
from ...models.role import SCOPE_ALL, SCOPE_DEPARTMENT, SCOPE_OWN
from ...models.user import User
from ...repositories.org_scope import dept_subtree_ids


def sale_ids_theo_pham_vi(db: Session, user: User, authz, module_key: str) -> set[int] | None:
    """Tập `users.id` của người BÁN mà `user` được nhìn lệnh. `None` = thấy tất cả.

    Thiếu khai scope ⇒ hẹp nhất (`own`), không phải rộng nhất — mở nhầm còn tệ hơn khoá nhầm.
    """
    scope = authz.scope_for(user, module_key) or SCOPE_OWN
    if scope == SCOPE_ALL:
        return None
    if scope == SCOPE_DEPARTMENT:
        dept_ids = dept_subtree_ids(db, user.department_id)
        if dept_ids:
            ids = db.execute(select(User.id).where(User.department_id.in_(dept_ids))).scalars().all()
            return set(ids) | {user.id}
    return {user.id}


def loc_lsx_da_phat_hanh(stmt, sale_ids: set[int] | None):
    """Gắn hai điều kiện vào một `select(Lsx)`: đã phát hành + trong phạm vi người bán.

    `sale_ids is None` ⇒ chỉ lọc trạng thái. Đơn KHÔNG có người bán (`sale_user_id IS NULL`)
    rơi ra ngoài mọi phạm vi hẹp — chỉ `all` thấy, đúng chủ ý: không gán bừa cho ai.
    """
    stmt = stmt.where(Lsx.trang_thai == TT_DA_PHAT_HANH)
    if sale_ids is None:
        return stmt
    return stmt.join(Order, Order.id == Lsx.order_id).where(Order.sale_user_id.in_(sale_ids))


def chan_ngoai_pham_vi(db: Session, lsx: Lsx | None, sale_ids: set[int] | None) -> None:
    """403 khi người dùng gõ thẳng id ngoài phạm vi (hoặc lệnh chưa phát hành).

    Dùng 403 chứ không 404: hai màn này là bàn tra cứu, người dùng CẦN biết "có lệnh đó nhưng
    không thuộc phần việc của bạn" để đi hỏi đúng người, thay vì tưởng gõ nhầm mã.
    """
    if lsx is None or lsx.trang_thai != TT_DA_PHAT_HANH:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy lệnh sản xuất đã phát hành")
    if sale_ids is None:
        return
    order = db.get(Order, lsx.order_id)
    if order is not None and order.sale_user_id in sale_ids:
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Lệnh sản xuất ngoài phạm vi của bạn")
