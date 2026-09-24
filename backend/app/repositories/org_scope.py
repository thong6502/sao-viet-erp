"""Ngữ nghĩa scope `department` = phòng mình + TOÀN BỘ cây con (khảo sát CRM #26).

Cây phòng ban đã tồn tại (departments.parent_id, spec-05/06); trước đây các repo scoped
lọc theo ĐÚNG MỘT department_id nên trưởng đơn vị cha (GĐKD) không thấy dữ liệu của các
team con. Helper này trả về tập id của cả nhánh để mọi nơi tiêu thụ SCOPE_DEPARTMENT
(khách hàng, báo giá, đơn hàng, nhân sự, nghỉ phép) lọc nhất quán:

    GĐKD (phòng KD cha)  → thấy cả các team con
    TPKD (team)          → thấy team mình
    Trợ lý team          → role scope department + ma trận chỉ bật read

Một SELECT (id, parent_id) trên toàn bảng departments (bảng nhỏ) rồi BFS trong Python —
tránh CTE đệ quy để giữ portable SQLite/Postgres.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.department import Department
from ..models.nhom_dung_chung import NhomDungChungThanhVien


def dept_subtree_ids(db: Session, root_id: int | None) -> list[int]:
    """Id của phòng `root_id` + mọi phòng con/cháu. `root_id` None → [] (caller tự
    fallback về own — người không có phòng không được thấy theo phòng)."""
    if root_id is None:
        return []
    pairs = db.execute(select(Department.id, Department.parent_id)).all()
    children: dict[int | None, list[int]] = {}
    for did, pid in pairs:
        children.setdefault(pid, []).append(did)
    ids: list[int] = []
    queue = [root_id]
    seen: set[int] = set()
    while queue:
        cur = queue.pop(0)
        if cur in seen:
            continue
        seen.add(cur)
        ids.append(cur)
        queue.extend(children.get(cur, []))
    return ids


def nhom_dung_chung_user_ids(db: Session, user_id: int) -> set[int]:
    """Tập user-id DÙNG CHUNG dữ liệu với `user_id` — gồm cả chính nó.

    NGUỒN DUY NHẤT của nghĩa "Của tôi" mở rộng ở bốn màn khối Kinh doanh (`tinh_gia_thanh` ·
    `bao_gia` · `don_hang_ban` · `khach_hang`). Không nơi nào khác được tự truy vấn hai bảng
    nhóm để lọc dữ liệu — một chỗ thì còn sửa được, bốn chỗ chép tay là bốn lần lệch.

    Một người ở được nhiều nhóm ⇒ lấy HỢP. Người không thuộc nhóm nào → `{user_id}`, tức hành
    vi y hệt trước khi có tính năng.

    CỐ Ý chỉ dùng cho nhánh `own`: `department`/`all` đã rộng hơn rồi.
    """
    tv = NhomDungChungThanhVien
    nhom_cua_toi = select(tv.nhom_id).where(tv.user_id == user_id)
    ids = db.execute(select(tv.user_id).where(tv.nhom_id.in_(nhom_cua_toi))).scalars().all()
    return set(ids) | {user_id}
