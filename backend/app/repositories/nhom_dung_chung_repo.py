"""Đọc/ghi Nhóm dùng chung (khối Kinh doanh).

Lọc DỮ LIỆU theo nhóm KHÔNG đi qua đây — nó đi qua `org_scope.nhom_dung_chung_user_ids`, nguồn
duy nhất. Repo này chỉ lo việc quản trị: liệt kê, gộp, sửa, xoá nhóm.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.nhom_dung_chung import NhomDungChung, NhomDungChungThanhVien
from ..models.user import User


class TenNhomTrung(Exception):
    """Hai nhóm trùng tên thì người cấp quyền không biết mình đang thêm người vào nhóm nào."""


class NhomDungChungRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ---------------------------------------------------------------- đọc
    def list_all(self) -> list[NhomDungChung]:
        return list(
            self.db.execute(
                select(NhomDungChung).order_by(NhomDungChung.ten)
            ).scalars()
        )

    def get(self, nhom_id: int) -> NhomDungChung | None:
        return self.db.get(NhomDungChung, nhom_id)

    def thanh_viens(self, nhom_id: int) -> list[tuple[int, str, str]]:
        """(user_id, họ tên, tên đăng nhập) theo thứ tự thêm vào."""
        rows = self.db.execute(
            select(NhomDungChungThanhVien.user_id, User.name, User.username)
            .join(User, User.id == NhomDungChungThanhVien.user_id)
            .where(NhomDungChungThanhVien.nhom_id == nhom_id)
            .order_by(NhomDungChungThanhVien.id)
        ).all()
        return [(uid, ten or username, username) for uid, ten, username in rows]

    def nhom_cua_user(self, user_id: int) -> list[NhomDungChung]:
        return list(
            self.db.execute(
                select(NhomDungChung)
                .join(NhomDungChungThanhVien,
                      NhomDungChungThanhVien.nhom_id == NhomDungChung.id)
                .where(NhomDungChungThanhVien.user_id == user_id)
                .order_by(NhomDungChung.ten)
            ).scalars()
        )

    # ---------------------------------------------------------------- ghi
    def create(self, *, ten: str, user_ids: list[int], actor_id: int | None) -> NhomDungChung:
        ten = ten.strip()
        if self._trung_ten(ten, tru_id=None):
            raise TenNhomTrung(ten)
        nhom = NhomDungChung(ten=ten, created_by=actor_id)
        self.db.add(nhom)
        self.db.flush()
        self._dat_thanh_vien(nhom.id, user_ids, actor_id)
        self.db.commit()
        return nhom

    def update(
        self,
        nhom: NhomDungChung,
        *,
        ten: str | None,
        user_ids: list[int] | None,
        actor_id: int | None,
    ) -> NhomDungChung:
        if ten is not None:
            ten = ten.strip()
            if self._trung_ten(ten, tru_id=nhom.id):
                raise TenNhomTrung(ten)
            nhom.ten = ten
        if user_ids is not None:
            self._dat_thanh_vien(nhom.id, user_ids, actor_id)
        self.db.commit()
        return nhom

    def delete(self, nhom: NhomDungChung) -> None:
        # Thành viên đi theo nhờ ON DELETE CASCADE; xoá tay ở đây cho SQLite (FK có thể tắt).
        self.db.query(NhomDungChungThanhVien).filter_by(nhom_id=nhom.id).delete()
        self.db.delete(nhom)
        self.db.commit()

    # ------------------------------------------------------------- nội bộ
    def _trung_ten(self, ten: str, *, tru_id: int | None) -> bool:
        stmt = select(NhomDungChung.id).where(NhomDungChung.ten == ten)
        if tru_id is not None:
            stmt = stmt.where(NhomDungChung.id != tru_id)
        return self.db.execute(stmt).first() is not None

    def _dat_thanh_vien(self, nhom_id: int, user_ids: list[int], actor_id: int | None) -> None:
        """THAY TOÀN BỘ danh sách thành viên (không phải thêm dồn)."""
        self.db.query(NhomDungChungThanhVien).filter_by(nhom_id=nhom_id).delete()
        da_them: set[int] = set()
        for uid in user_ids:
            if uid in da_them:
                continue
            da_them.add(uid)
            self.db.add(
                NhomDungChungThanhVien(nhom_id=nhom_id, user_id=uid, added_by=actor_id)
            )
        self.db.flush()
