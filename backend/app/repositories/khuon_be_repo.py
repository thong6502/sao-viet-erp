"""Repository — Danh mục Khuôn bế. CRUD + tìm theo mã/tên + sinh mã tự động KB-####."""
from __future__ import annotations

from sqlalchemy import func, select

from ..models.khuon_be import KhuonBe
from .catalog_base import CatalogRepo


class KhuonBeRepository(CatalogRepo):
    model = KhuonBe
    fields = ("ten", "khach_hang", "so_ke", "ngay_lam_khuon", "tinh_trang", "ghi_chu", "active")
    # Tìm cả theo KHÁCH HÀNG và SỐ KỆ: người tìm khuôn thường nhớ "khuôn của ai" / "để kệ nào"
    # chứ hiếm khi nhớ mã KB-####.
    search_fields = ("ma", "ten", "khach_hang", "so_ke")
    ma_prefix = "KB-"
    commit_on_write = False   # `KhuonBeService` chốt sau khi đã ghi nhật ký — xem `catalog_base`

    def extra_conds(self, *, tinh_trang: str | None = None, **_) -> list:
        return [KhuonBe.tinh_trang == tinh_trang] if tinh_trang else []

    def dem_theo_tinh_trang(self, *, q: str | None = None,
                            active: bool | None = None) -> dict[str, int]:
        """Số khuôn theo TỪNG tình trạng — số hiện trên tab lọc. Không áp điều kiện
        `tinh_trang` (tab nào cũng phải có số của nó), nhưng CÓ áp `q` và `active`."""
        stmt = select(KhuonBe.tinh_trang, func.count()).group_by(KhuonBe.tinh_trang)
        loc = self._loc_q(q)
        if loc is not None:
            stmt = stmt.where(loc)
        if active is not None:
            stmt = stmt.where(KhuonBe.active.is_(active))
        # Nhóm khuyết gom vào khoá rỗng "" (xem `may_thiet_bi_repo.dem_theo_loai`).
        return {(str(tt).strip() if tt is not None else ""): int(n)
                for tt, n in self.db.execute(stmt)}
