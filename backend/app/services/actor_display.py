"""Nhãn NGƯỜI THAO TÁC cho mọi nhật ký hoạt động — "Phòng ban · Chức vụ · Tên".

LUẬT (chủ đầu tư chốt): mỗi tài khoản đã gắn 1 hồ sơ nhân sự, mà hồ sơ mới là nơi giữ vai thật
(phòng ban + chức vụ). Nên log KHÔNG bao giờ suy vai từ HÀNH ĐỘNG ("Giám đốc KD duyệt" — sai khi
người bấm là Giám đốc công ty hay TP Kinh doanh, cả hai đều cầm `can_approve_exception`), cũng
KHÔNG in tên tài khoản ("Admin"). Chỉ đọc hồ sơ mà ghi:

    Ban giám đốc · Giám đốc · Nguyễn Văn Giám

Phần thiếu thì BỎ, không để dấu · mồ côi: hồ sơ chưa có phòng ban → "Giám đốc · Nguyễn Văn Giám".
Tài khoản chưa kịp có hồ sơ → lùi về `User.name` (lưới an toàn kỹ thuật; `backfill_employee_profiles`
đã ép mọi tài khoản có hồ sơ nên đây là đường hiếm).

Hàm THUẦN đọc: 3 truy vấn gộp cho N user (không N+1). Dùng chung Báo giá + Phiếu tính giá.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.department import Department
from ..models.employee import Employee
from ..models.user import User


def actor_labels(db: Session, user_ids: set[int]) -> dict[int, str]:
    """Map user_id → "Phòng ban · Chức vụ · Tên" (thiếu phần nào bỏ phần đó).

    Fallback `User.name` khi tài khoản chưa có hồ sơ nhân sự.
    """
    ids = {i for i in user_ids if i}
    if not ids:
        return {}

    names: dict[int, str] = dict(
        db.execute(select(User.id, User.name).where(User.id.in_(ids))).all()
    )

    rows = db.execute(
        select(Employee.user_id, Employee.full_name, Employee.position, Employee.department_id)
        .where(Employee.user_id.in_(ids))
    ).all()

    dept_ids = {r.department_id for r in rows if r.department_id}
    dept_names: dict[int, str] = (
        dict(db.execute(
            select(Department.id, Department.name).where(Department.id.in_(dept_ids))
        ).all())
        if dept_ids else {}
    )

    out: dict[int, str] = {}
    for r in rows:
        parts = [
            dept_names.get(r.department_id) if r.department_id else None,
            (r.position or "").strip() or None,
            (r.full_name or "").strip() or None,
        ]
        label = " · ".join(p for p in parts if p)
        if label:
            out[r.user_id] = label

    # Tài khoản không có hồ sơ (hoặc hồ sơ trống trơn) → tên tài khoản.
    for uid in ids:
        if uid not in out and names.get(uid):
            out[uid] = names[uid]
    return out
