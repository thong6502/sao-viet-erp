"""Repository — Danh sách VỊ TRÍ cất của từng kho (`kho_vi_tri`).

Danh sách nhẹ, chỉ để khai lô chọn từ dropdown thay vì gõ tay. Không ràng buộc cứng lên
`stock_lots.vi_tri` (cột đó vẫn là chuỗi tự do) nên xoá một vị trí KHÔNG mồ côi gì — vẫn xoá MỀM
(`active=false`) để giữ ràng buộc UNIQUE(kho_id, ma) sạch và cho phép bật lại.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.kho_hang import KhoViTri


class KhoViTriRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_by_kho(self, kho_id: int, chi_active: bool = True) -> list[KhoViTri]:
        stmt = select(KhoViTri).where(KhoViTri.kho_id == kho_id)
        if chi_active:
            stmt = stmt.where(KhoViTri.active.is_(True))
        stmt = stmt.order_by(KhoViTri.ma.asc())
        return list(self.db.execute(stmt).scalars().all())

    def get(self, vi_tri_id: int) -> KhoViTri | None:
        return self.db.get(KhoViTri, vi_tri_id)

    def find_by_ma(self, kho_id: int, ma: str) -> KhoViTri | None:
        """Tìm theo (kho, mã) KỂ CẢ dòng đã xoá mềm — để `create` bật lại thay vì đụng UNIQUE."""
        return self.db.execute(
            select(KhoViTri).where(KhoViTri.kho_id == kho_id, KhoViTri.ma == ma)
        ).scalar_one_or_none()

    def create(self, kho_id: int, ma: str, ghi_chu: str | None) -> KhoViTri:
        obj = KhoViTri(kho_id=kho_id, ma=ma, ghi_chu=ghi_chu, active=True)
        self.db.add(obj)
        self.db.flush()
        return obj

    def reactivate(self, obj: KhoViTri, ghi_chu: str | None) -> KhoViTri:
        obj.active = True
        obj.ghi_chu = ghi_chu
        self.db.flush()
        return obj

    def soft_delete(self, obj: KhoViTri) -> None:
        obj.active = False
        self.db.flush()
