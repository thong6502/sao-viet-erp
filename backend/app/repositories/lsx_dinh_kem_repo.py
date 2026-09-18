"""Truy vấn bảng `lsx_dinh_kem` — tệp đính kèm của lệnh sản xuất."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.lsx import LsxDinhKem
from ..models.user import User


class LsxDinhKemRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_by_lsx(self, lsx_id: int) -> list[LsxDinhKem]:
        """Mới tải lên đứng đầu — người mở tab thường tìm tệp vừa được gửi thêm."""
        return list(
            self.db.execute(
                select(LsxDinhKem)
                .where(LsxDinhKem.lsx_id == lsx_id)
                .order_by(LsxDinhKem.tai_luc.desc(), LsxDinhKem.id.desc())
            ).scalars()
        )

    def list_by_lsx_ids(self, lsx_ids: set[int]) -> list[LsxDinhKem]:
        """Như `list_by_lsx` cho nhiều lệnh một lượt (bài ghép) — người gọi tự gom theo `lsx_id`."""
        if not lsx_ids:
            return []
        return list(
            self.db.execute(
                select(LsxDinhKem)
                .where(LsxDinhKem.lsx_id.in_(lsx_ids))
                .order_by(LsxDinhKem.tai_luc.desc(), LsxDinhKem.id.desc())
            ).scalars()
        )

    def urls_by_lsx(self, lsx_id: int) -> list[str]:
        return list(
            self.db.execute(select(LsxDinhKem.file_url).where(LsxDinhKem.lsx_id == lsx_id)).scalars()
        )

    def ten_nguoi(self, user_ids: set[int]) -> dict[int, str]:
        """Tên ngắn (không kèm phòng ban/chức vụ) — một dòng tệp chỉ đủ chỗ cho tên."""
        if not user_ids:
            return {}
        return dict(self.db.execute(select(User.id, User.name).where(User.id.in_(user_ids))).all())

    def get(self, dinh_kem_id: int) -> LsxDinhKem | None:
        return self.db.get(LsxDinhKem, dinh_kem_id)

    def add(self, row: LsxDinhKem) -> LsxDinhKem:
        self.db.add(row)
        self.db.flush()
        return row

    def delete(self, row: LsxDinhKem) -> None:
        self.db.delete(row)
        self.db.flush()
