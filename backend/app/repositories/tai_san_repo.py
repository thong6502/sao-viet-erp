"""Repository — sổ tài sản cố định & công cụ dụng cụ.

KHÔNG kế thừa `CatalogRepo`: tài sản không phải danh mục phẳng (ghi tăng kèm nhiều dòng chi phí,
sổ có trạng thái và bảng mốc cơ sở), ép vào nền chung là đẻ một loạt cờ mà mỗi cờ đúng một chỗ.

Lọc + cắt trang làm ở SQL, KHÔNG kéo cả bảng về rồi cắt trong Python. Truy vấn trả danh sách
tài sản nạp sẵn `moc`: hao mòn lũy kế của từng dòng tính từ bảng mốc, không nạp sẵn là N+1.
"""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..models.department import Department
from ..models.employee import Employee
from ..models.tai_san import TaiSan


class TaiSanRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- Đọc ------------------------------------------------------------------------------

    def lay(self, tai_san_id: int) -> TaiSan | None:
        return self.db.get(TaiSan, tai_san_id)

    def lay_kem_chi_tiet(self, tai_san_id: int) -> TaiSan | None:
        """Nạp sẵn dòng chi phí + chứng từ + mốc — màn chi tiết đọc cả ba, tránh N+1."""
        stmt = (
            select(TaiSan)
            .options(
                selectinload(TaiSan.chi_phi),
                selectinload(TaiSan.bien_dong),
                selectinload(TaiSan.moc),
            )
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
                .options(selectinload(TaiSan.moc))
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

    def ten_bo_phan(self, bo_phan_id: int) -> str | None:
        bp = self.db.get(Department, bo_phan_id)
        return bp.name if bp is not None else None

    # --- Nhân viên (người quản lý) --------------------------------------------------------

    def nhan_vien(self, nhan_vien_id: int) -> Employee | None:
        return self.db.get(Employee, nhan_vien_id)

    def nhan_vien_bo_phan(self, bo_phan_id: int, trang_thai) -> list[Employee]:
        """Nhân viên của một bộ phận đang ở các trạng thái `trang_thai`, xếp theo tên."""
        return list(
            self.db.execute(
                select(Employee)
                .where(
                    Employee.department_id == bo_phan_id,
                    Employee.status.in_(list(trang_thai)),
                )
                .order_by(Employee.full_name, Employee.id)
            ).scalars()
        )

    # --- Ghi ------------------------------------------------------------------------------

    def them(self, obj) -> None:
        self.db.add(obj)

    def commit(self) -> None:
        self.db.commit()

    def xoa(self, obj) -> None:
        self.db.delete(obj)
