"""Repository — sổ tài sản cố định & công cụ dụng cụ.

KHÔNG kế thừa `CatalogRepo`: tài sản không phải danh mục phẳng (ghi tăng kèm nhiều dòng chi phí,
sổ có trạng thái và kỳ chốt), ép vào nền chung là đẻ một loạt cờ mà mỗi cờ đúng một chỗ dùng.

Lọc + cắt trang làm ở SQL, KHÔNG kéo cả bảng về rồi cắt trong Python.
"""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..models.tai_san import KY_DA_CHOT, TaiSan, TaiSanKhauHao, TaiSanKy


class TaiSanRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- Đọc ------------------------------------------------------------------------------

    def lay(self, tai_san_id: int) -> TaiSan | None:
        return self.db.get(TaiSan, tai_san_id)

    def lay_kem_chi_tiet(self, tai_san_id: int) -> TaiSan | None:
        """Nạp sẵn dòng chi phí + chứng từ biến động — màn chi tiết đọc cả hai, tránh N+1."""
        stmt = (
            select(TaiSan)
            .options(selectinload(TaiSan.chi_phi), selectinload(TaiSan.bien_dong))
            .where(TaiSan.id == tai_san_id)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def tim_theo_ma(self, ma: str) -> TaiSan | None:
        return self.db.execute(select(TaiSan).where(TaiSan.ma == ma)).scalar_one_or_none()

    def danh_sach(
        self,
        *,
        q: str | None = None,
        loai: str | None = None,
        bo_phan_id: int | None = None,
        trang_thai: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[TaiSan], int]:
        conds = []
        if q:
            kw = f"%{q.strip()}%"
            conds.append(or_(TaiSan.ma.ilike(kw), TaiSan.ten.ilike(kw)))
        if loai:
            conds.append(TaiSan.loai == loai)
        if bo_phan_id:
            conds.append(TaiSan.bo_phan_id == bo_phan_id)
        if trang_thai:
            conds.append(TaiSan.trang_thai == trang_thai)

        tong = self.db.execute(
            select(func.count()).select_from(TaiSan).where(*conds)
        ).scalar_one()
        rows = list(
            self.db.execute(
                select(TaiSan)
                .where(*conds)
                .order_by(TaiSan.ma)
                .offset(max(int(offset), 0))
                .limit(max(int(limit), 1))
            ).scalars()
        )
        return rows, int(tong)

    def ma_lon_nhat(self, tien_to: str) -> str | None:
        """Mã lớn nhất đang có theo tiền tố — nền sinh số kế tiếp."""
        return self.db.execute(
            select(func.max(TaiSan.ma)).where(TaiSan.ma.like(f"{tien_to}%"))
        ).scalar_one_or_none()

    def dang_dung(self, *, bo_phan_id: int | None = None) -> list[TaiSan]:
        conds = []
        if bo_phan_id:
            conds.append(TaiSan.bo_phan_id == bo_phan_id)
        return list(
            self.db.execute(select(TaiSan).where(*conds).order_by(TaiSan.ma)).scalars()
        )

    # --- Kỳ chốt --------------------------------------------------------------------------

    def ky_da_chot(self, nam: int, thang: int) -> bool:
        tt = self.db.execute(
            select(TaiSanKy.trang_thai).where(TaiSanKy.ky_nam == nam, TaiSanKy.ky_thang == thang)
        ).scalar_one_or_none()
        return tt == KY_DA_CHOT

    def co_ky_chot_lien_quan(self, tai_san_id: int) -> bool:
        """Tài sản đã có số ở một kỳ ĐÃ CHỐT ⇒ cấm sửa ô ảnh hưởng sổ và cấm xoá."""
        stmt = (
            select(func.count())
            .select_from(TaiSanKhauHao)
            .join(
                TaiSanKy,
                (TaiSanKy.ky_nam == TaiSanKhauHao.ky_nam)
                & (TaiSanKy.ky_thang == TaiSanKhauHao.ky_thang),
            )
            .where(TaiSanKhauHao.tai_san_id == tai_san_id, TaiSanKy.trang_thai == KY_DA_CHOT)
        )
        return int(self.db.execute(stmt).scalar_one()) > 0

    def so_ky_da_trich(self, tai_san_id: int) -> int:
        """Đếm kỳ đã có dòng khấu hao — nền tính số tháng còn lại khi giảm một phần lô CCDC."""
        return int(
            self.db.execute(
                select(func.count())
                .select_from(TaiSanKhauHao)
                .where(TaiSanKhauHao.tai_san_id == tai_san_id)
            ).scalar_one()
        )

    # --- Ghi ------------------------------------------------------------------------------

    def them(self, obj) -> None:
        self.db.add(obj)

    def commit(self) -> None:
        self.db.commit()

    def xoa(self, obj) -> None:
        self.db.delete(obj)
