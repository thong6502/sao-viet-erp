"""Repository — Danh mục "Lý do & lỗi SX" (bảng `san_xuat_ly_do`). CRUD + lọc theo nhóm + đếm tab.

Danh mục CHUẨN HOÁ dùng chung (§15): hỏng batch · lỗi KCS · lý do tạm dừng · bắt đầu trễ · điều
chỉnh bàn giao… Mỗi ô chọn ở FE lọc theo cột `nhom`, nên bảng này đọc THEO NHÓM (như `cong_doan`
đọc theo nhóm công đoạn), không đọc theo thứ tự mã. Đi vào nền `CatalogRepo` như 9 repo danh mục kia.
"""
from __future__ import annotations

from sqlalchemy import func, select

from ..models.san_xuat_ly_do import SanXuatLyDo
from .catalog_base import CatalogRepo

ASSIGNABLE = ("nhom", "ten", "mo_ta", "thu_tu", "active")


class SanXuatLyDoRepository(CatalogRepo):
    model = SanXuatLyDo
    fields = ASSIGNABLE
    commit_on_write = False   # service chốt sau khi ghi nhật ký — xem `catalog_base`
    # Mã do MÁY cấp (`LD-0001`…) — xưởng không gõ mã cho từng lý do.
    ma_prefix = "LD-"
    search_fields = ("ma", "ten", "mo_ta")
    # Gom theo NHÓM rồi tới thứ tự khai tay, cuối cùng mới tới mã: người ta đọc "nhóm lỗi có những
    # gì" và tự xếp thứ tự hiện ra ô chọn bằng `thu_tu`.
    order_cols = ("nhom", "thu_tu", "ma")

    def extra_conds(self, *, nhom: str | None = None, **_) -> list:
        """Lọc theo NHÓM — giá trị đúng một khoá trong `NHOM_LY_DO` (`loi`, `tam_dung`…). Đây là
        dạng của TAB LỌC trên màn và cũng là cách mỗi ô chọn ở FE gọi (`?nhom=loi`)."""
        s = str(nhom).strip() if nhom else ""
        return [SanXuatLyDo.nhom == s] if s else []

    def dem_theo_nhom(self, *, q: str | None = None, active: bool | None = None) -> dict[str, int]:
        """Số dòng của TỪNG nhóm — số hiện trên tab lọc. Không áp điều kiện `nhom` (tab đang không
        được chọn vẫn phải khoe số của nó), nhưng CÓ áp `q`/`active` để số trên tab và số dòng trong
        bảng không bao giờ nói hai chuyện khác nhau."""
        stmt = select(SanXuatLyDo.nhom, func.count()).group_by(SanXuatLyDo.nhom)
        loc = self._loc_q(q)
        if loc is not None:
            stmt = stmt.where(loc)
        if active is not None:
            stmt = stmt.where(SanXuatLyDo.active.is_(active))
        return {(str(g).strip() if g is not None else ""): int(n)
                for g, n in self.db.execute(stmt)}
