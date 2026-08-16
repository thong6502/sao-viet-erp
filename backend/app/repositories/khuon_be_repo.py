"""Repository — Danh mục Khuôn bế. CRUD + tìm theo mã/tên + sinh mã tự động KB-####."""
from __future__ import annotations

from sqlalchemy import func, select

from ..models.khuon_be import KhuonBe
from .catalog_base import CatalogRepo


class KhuonBeRepository(CatalogRepo):
    model = KhuonBe
    fields = ("ten", "khach_hang_id", "loai", "so_ke", "tinh_trang",
              "ngay_ve_du_kien", "ghi_chu", "active")
    # Tìm theo TÊN ẤN PHẨM và SỐ KỆ: người tìm dao nhớ "dao cái hộp bánh" / "để kệ nào" chứ hiếm
    # khi nhớ mã KB-####. Lọc theo KHÁCH đi đường riêng (`extra_conds`) vì nay là FK, không phải
    # chuỗi để `LIKE` — trước 16/08 nó là chuỗi và nằm trong danh sách này.
    search_fields = ("ma", "ten", "so_ke")
    ma_prefix = "KB-"
    commit_on_write = False   # `KhuonBeService` chốt sau khi đã ghi nhật ký — xem `catalog_base`

    def extra_conds(self, *, tinh_trang: str | None = None, khach_hang_id: int | None = None,
                    loai: str | None = None, **_) -> list:
        """Ba bộ lọc. `khach_hang_id` + `loai` là hai chiều mà ô chọn khuôn ở bước lệnh dùng —
        mở ra chỉ thấy dao CỦA KHÁCH NÀY, ĐÚNG LOẠI của bước, thay vì cả kho."""
        conds = []
        if tinh_trang:
            conds.append(KhuonBe.tinh_trang == tinh_trang)
        if khach_hang_id:
            conds.append(KhuonBe.khach_hang_id == khach_hang_id)
        if loai:
            conds.append(KhuonBe.loai == loai)
        return conds

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
