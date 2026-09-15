"""Cấp DÒNG QUYỀN THEO TỔ cho test (mg 0302, 14/09/2026).

Trước đây test qua cổng ghi của Bàn tổ bằng `Department.head_user_id = admin.id`. Luật cứng "phải
đứng tên trưởng tổ" đã gỡ — quyền nay nằm ở dòng `to_sx_<id phòng ban>` của VAI người dùng. Helper
này làm đúng việc quản trị bấm trên ma trận: đồng bộ dòng theo cây rồi bật ô cho vai.
"""
from __future__ import annotations

from app.models.role import SCOPE_ALL, Role
from app.repositories.rbac_repo import RoleRepository
from app.services.quyen_to import COT_VIEC, dong_bo_dong_quyen_to, khoa_to

BON_VIEC = ("run_order", "confirm_output", "qc", "warehouse")


def cap_quyen_to(db, user, dept, *, scope: str = SCOPE_ALL, viec=BON_VIEC, xem: bool = True):
    """Bật Xem + `viec` (mặc định cả bốn quyền chi tiết) trên dòng tổ `dept` cho vai của `user`.

    User chưa có vai thì dựng một vai riêng ở phòng của họ (hoặc chính tổ) rồi gán — y như quản trị
    tạo vai trước khi cấp quyền. Trả lại `user` để viết gọn trong fixture."""
    db.flush()
    dong_bo_dong_quyen_to(db)
    roles = RoleRepository(db)
    if user.role_id is None:
        phong = user.department_id or dept.id
        vai = Role(name=f"Vai test {user.id}", department_id=phong)
        db.add(vai)
        db.flush()
        user.role_id = vai.id
    cu = roles.get_permission(user.role_id, khoa_to(dept.id))
    co = {c: bool(getattr(cu, c)) for c in COT_VIEC.values()} if cu is not None else {}
    co["can_read"] = xem or co.get("can_read", False)
    for v in viec:
        co[COT_VIEC[v]] = True
    roles.set_permission(role_id=user.role_id, module_key=khoa_to(dept.id), scope=scope, **co)
    return user
