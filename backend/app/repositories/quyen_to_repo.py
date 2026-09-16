"""Dòng quyền THEO TỔ — tầng truy vấn (mg 0302, 14/09/2026).

Mỗi phòng ban thuộc khối Sản xuất có một dòng `modules` khoá `to_sx_<id phòng ban>` và các dòng
`role_permissions` cùng khoá. Luật tính quyền nằm ở `services/quyen_to.py`; ở đây chỉ đọc/ghi.
"""
from __future__ import annotations

from sqlalchemy import delete, select, true
from sqlalchemy.orm import Session

from ..models.department import Department
from ..models.module import Module
from ..models.role import RolePermission
from ..models.user import User

KHOA_TIEN_TO = "to_sx_"


class QuyenToRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def cay_phong_ban(self) -> list[tuple[int, int | None, str, bool, bool]]:
        """(id, parent_id, tên, la_san_xuat, is_kcs) của MỌI phòng ban — bảng nhỏ, đọc một lượt."""
        return [
            (r.id, r.parent_id, r.name, bool(r.la_san_xuat), bool(r.is_kcs))
            for r in self.db.execute(
                select(
                    Department.id, Department.parent_id, Department.name,
                    Department.la_san_xuat, Department.is_kcs,
                ).order_by(Department.id)
            ).all()
        ]

    def module_to(self) -> dict[str, str]:
        """`{khoá: nhãn}` của các dòng quyền theo tổ đang có."""
        return {
            k: nhan
            for k, nhan in self.db.execute(
                select(Module.key, Module.label).where(Module.key.like(f"{KHOA_TIEN_TO}%"))
            ).all()
        }

    def tao_module(self, key: str, label: str) -> None:
        self.db.add(Module(key=key, label=label))

    def doi_nhan_module(self, key: str, label: str) -> None:
        m = self.db.execute(select(Module).where(Module.key == key)).scalar_one_or_none()
        if m is not None:
            m.label = label

    def xoa_module(self, key: str) -> None:
        """Gỡ dòng quyền cùng mọi ô đã cấp trên nó (khoá ngoại `role_permissions.module_key`)."""
        self.db.execute(delete(RolePermission).where(RolePermission.module_key == key))
        self.db.execute(delete(Module).where(Module.key == key))

    def dong_quyen_cua_vai(self, role_id: int) -> list[RolePermission]:
        return list(
            self.db.execute(
                select(RolePermission).where(
                    RolePermission.role_id == role_id,
                    RolePermission.module_key.like(f"{KHOA_TIEN_TO}%"),
                )
            ).scalars()
        )

    def nguoi_giu_quyen(self, cot: str) -> list[tuple[int, int | None, str, str]]:
        """(user_id, phòng của user, khoá dòng, phạm vi) cho mọi tài khoản đang hoạt động có bật
        cột `cot` trên một dòng quyền theo tổ. Người gọi tự lọc theo vùng + phạm vi."""
        cot_attr = getattr(RolePermission, cot)
        return [
            (uid, dept, key, scope)
            for uid, dept, key, scope in self.db.execute(
                select(User.id, User.department_id, RolePermission.module_key, RolePermission.scope)
                .join(RolePermission, RolePermission.role_id == User.role_id)
                .where(
                    RolePermission.module_key.like(f"{KHOA_TIEN_TO}%"),
                    cot_attr == true(),
                    User.is_active == true(),
                )
            ).all()
        ]
