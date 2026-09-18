"""Repository — Danh mục Khuôn. CRUD + tìm theo mã/tên/khách/số kệ + sinh mã tự động KB-####."""
from __future__ import annotations

from sqlalchemy import func, or_, select

from ..models.customer import Customer
from ..models.khuon_be import KhuonBe
from .catalog_base import CatalogRepo


class KhuonBeRepository(CatalogRepo):
    model = KhuonBe
    fields = ("ten", "khach_hang_id", "loai", "so_ke", "tinh_trang", "ghi_chu", "active")
    # Tìm theo TÊN ẤN PHẨM và SỐ KỆ: người tìm dao nhớ "dao cái hộp bánh" / "để kệ nào" chứ hiếm
    # khi nhớ mã KB-####. TÊN KHÁCH cũng tìm được (18/09/2026) nhưng đi đường riêng ở `_loc_q` vì
    # nó là FK sang `customers`, không phải chuỗi nằm trên bảng này để `LIKE` thẳng.
    search_fields = ("ma", "ten", "so_ke")
    ma_prefix = "KB-"
    commit_on_write = False   # `KhuonBeService` chốt sau khi đã ghi nhật ký — xem `catalog_base`

    def _loc_q(self, q: str | None):
        """Ô tìm = mã · tên · số kệ · TÊN KHÁCH. Gõ "minh long" ra mọi khuôn của khách đó.

        Khách khớp bằng `IN (subquery)` chứ không `JOIN`: câu đếm `total` và các hàm đếm tab dùng
        chung điều kiện này mà không biết gì về bảng `customers` — JOIN thì phải sửa từng câu một.
        """
        goc = super()._loc_q(q)
        if goc is None:
            return None
        like = f"%{q.strip().lower()}%"
        khach = select(Customer.id).where(func.lower(Customer.name).like(like))
        return or_(goc, KhuonBe.khach_hang_id.in_(khach))

    def extra_conds(self, *, tinh_trang: str | None = None, khach_hang_id: int | None = None,
                    loai: str | None = None, so_ke: str | None = None, **_) -> list:
        """Bốn bộ lọc, ghép VÀ với nhau. Chip trên màn lọc theo `loai`; bảng "Lọc nâng cao" lọc
        theo `khach_hang_id` + `tinh_trang` + `so_ke`. `khach_hang_id` + `loai` cũng là hai chiều
        mà ô chọn khuôn ở bước lệnh dùng — mở ra chỉ thấy dao CỦA KHÁCH NÀY, ĐÚNG LOẠI của bước.

        `so_ke` khớp CHỨA, không phân hoa thường: ô số kệ là chữ gõ tự do ("Kệ B3 — xưởng sau in"),
        người đi tìm chỉ nhớ "B3" — bắt khớp nguyên chuỗi là lọc ra trống."""
        conds = []
        if so_ke and so_ke.strip():
            conds.append(func.lower(KhuonBe.so_ke).like(f"%{so_ke.strip().lower()}%"))
        if tinh_trang:
            conds.append(KhuonBe.tinh_trang == tinh_trang)
        if khach_hang_id:
            conds.append(KhuonBe.khach_hang_id == khach_hang_id)
        if loai:
            conds.append(KhuonBe.loai == loai)
        return conds

    def _dem_theo(self, cot, *, q: str | None = None, active: bool | None = None,
                  **loc) -> dict[str, int]:
        """Đếm theo từng giá trị của `cot`, dưới ĐÚNG bộ lọc đang áp (ô tìm · đang dùng · lọc nâng
        cao) — trừ chính bộ lọc theo `cot`, việc đó router đã bỏ ra khỏi `loc` trước khi gọi.
        Nhóm khuyết gom vào khoá rỗng "" (xem `may_thiet_bi_repo.dem_theo_loai`)."""
        stmt = select(cot, func.count()).group_by(cot)
        for c in self._dieu_kien(q=q, active=active, **loc):
            stmt = stmt.where(c)
        return {(str(v).strip() if v is not None else ""): int(n)
                for v, n in self.db.execute(stmt)}

    def dem_theo_loai(self, **kw) -> dict[str, int]:
        """Số khuôn theo TỪNG loại — số trên chip lọc. Chip đang không được chọn vẫn phải khoe số
        của nó, nên `loai` không có trong `kw`; khách + tình trạng của lọc nâng cao thì CÓ áp."""
        return self._dem_theo(KhuonBe.loai, **kw)

    def dem_theo_tinh_trang(self, **kw) -> dict[str, int]:
        """Số khuôn theo TỪNG tình trạng, cùng luật với `dem_theo_loai`."""
        return self._dem_theo(KhuonBe.tinh_trang, **kw)
