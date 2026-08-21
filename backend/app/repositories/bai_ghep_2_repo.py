"""Repository Bài ghép 2 - chỉ khác bài cũ ở tập trạng thái của hàng chờ."""
from __future__ import annotations

from sqlalchemy import exists, select
from sqlalchemy.orm import selectinload

from ..models.bai_ghep import BaiGhepThanhVien
from ..models.lsx import TT_CHO_BO_SUNG, TT_NHAP, TT_SAN_SANG, Lsx
from ..models.role import RolePermission
from ..models.user import User
from .bai_ghep_repo import BaiGhepRepository


class BaiGhep2Repository(BaiGhepRepository):
    def hang_cho_ghep(self) -> list[Lsx]:
        """LSX còn sửa được, chưa thuộc bài; không dùng giấy/khổ/màu/routing làm điều kiện SQL."""
        return list(
            self.db.execute(
                select(Lsx)
                .where(
                    Lsx.trang_thai.in_((TT_NHAP, TT_CHO_BO_SUNG, TT_SAN_SANG)),
                    ~exists(
                        select(BaiGhepThanhVien.id).where(BaiGhepThanhVien.lsx_id == Lsx.id)
                    ),
                )
                .options(selectinload(Lsx.cong_doans))
                .order_by(Lsx.created_at.desc())
            ).scalars()
        )

    def nguoi_phu_trach_options(self) -> list[User]:
        return list(self.db.execute(
            select(User)
            .join(RolePermission, RolePermission.role_id == User.role_id)
            .where(
                User.is_active.is_(True),
                RolePermission.module_key == "bai_ghep_2",
                RolePermission.can_update.is_(True),
            )
            .order_by(User.name, User.id)
        ).scalars())

    def user_names(self, user_ids: set[int]) -> dict[int, str]:
        if not user_ids:
            return {}
        rows = self.db.execute(select(User.id, User.name).where(User.id.in_(user_ids))).all()
        return {user_id: name for user_id, name in rows}
