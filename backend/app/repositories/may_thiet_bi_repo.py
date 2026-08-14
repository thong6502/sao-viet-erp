"""Repository — Máy thiết bị. CRUD + list/filter + find_by_ma."""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models.may_thiet_bi import MayThietBi

# Field client được phép gán (ma chuẩn hoá riêng; id/created/updated do server quản).
# Dọn 11/08/2026: chỉ còn cột CÓ Ô NHẬP trên form Máy. Xem docstring `models/may_thiet_bi.py`
# cho danh sách đã gỡ và lý do.
ASSIGNABLE = (
    "ten", "loai_may", "hang_san_xuat", "model", "so_seri", "ghi_chu",
    "toc_do", "toc_do_min", "toc_do_max", "don_vi_toc_do", "makeready_time_default",
    "so_nhan_cong",
    "kho_max_dai", "kho_max_rong", "kho_min_dai", "kho_min_rong",
    "kho_kem_dai", "kho_kem_rong", "vung_in_dai", "vung_in_rong", "gripper_mm", "nhip_giay_mm",
    "le_hong_mm", "duoi_thang_mau_mm",
    "fields_theo_loai",
)


class MayThietBiRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, may_id: int) -> MayThietBi | None:
        return self.db.get(MayThietBi, may_id)

    def find_by_ma(self, ma: str) -> MayThietBi | None:
        ma = (ma or "").strip().upper()
        if not ma:
            return None
        return self.db.execute(
            select(MayThietBi).where(func.upper(MayThietBi.ma) == ma)
        ).scalars().first()

    def _loc_q(self, q: str | None):
        """Điều kiện tìm theo mã/tên — dùng chung cho `list` và `dem_theo_loai` để hai con số
        (dòng trong bảng · số trên tab) không bao giờ nói hai chuyện khác nhau."""
        if not q:
            return None
        like = f"%{q.strip().lower()}%"
        return or_(func.lower(MayThietBi.ma).like(like), func.lower(MayThietBi.ten).like(like))

    def dem_theo_loai(self, *, q: str | None = None) -> dict[str, int]:
        """Số máy của TỪNG loại — số hiện trên tab lọc của màn Thiết bị.

        Cố ý KHÔNG áp điều kiện `loai_may`: tab nào cũng phải khoe số của nó, kể cả tab đang
        không được chọn. `q` thì CÓ áp — đang tìm "KOMORI" mà tab vẫn khoe số cả danh mục là
        nói dối. Một câu GROUP BY thay cho cách cũ (màn kéo cả bảng về rồi tự đếm trong JS).
        """
        stmt = select(MayThietBi.loai_may, func.count()).group_by(MayThietBi.loai_may)
        loc = self._loc_q(q)
        if loc is not None:
            stmt = stmt.where(loc)
        # Máy CHƯA khai loại gom vào khoá rỗng "" thay vì bị loại: màn cộng các số này ra tổng
        # cho tab "Tất cả", bỏ nhóm khuyết đi là tab đó hụt số mà không ai biết vì sao.
        return {(str(loai).strip() if loai is not None else ""): int(n)
                for loai, n in self.db.execute(stmt)}

    def list(self, *, q: str | None = None, loai_may: str | None = None,
             page: int = 1, size: int = 50):
        conds = []
        loc_q = self._loc_q(q)
        if loc_q is not None:
            conds.append(loc_q)
        if loai_may:
            conds.append(MayThietBi.loai_may == loai_may)
        base = select(MayThietBi)
        count_stmt = select(func.count()).select_from(MayThietBi)
        for c in conds:
            base = base.where(c)
            count_stmt = count_stmt.where(c)
        total = self.db.execute(count_stmt).scalar_one()
        page = max(1, page)
        size = max(1, min(size, 200))
        base = base.order_by(MayThietBi.ma.asc()).offset((page - 1) * size).limit(size)
        return list(self.db.execute(base).scalars()), total

    # -- writes --
    def _apply(self, may: MayThietBi, data: dict) -> None:
        for k in ASSIGNABLE:
            if k in data:
                setattr(may, k, data[k])

    def create(self, data: dict) -> MayThietBi:
        may = MayThietBi(ma=data["ma"].strip().upper())
        self._apply(may, data)
        self.db.add(may)
        self.db.commit()
        self.db.refresh(may)
        return may

    def update(self, may: MayThietBi, data: dict) -> MayThietBi:
        if data.get("ma"):
            may.ma = data["ma"].strip().upper()
        self._apply(may, data)
        self.db.commit()
        self.db.refresh(may)
        return may

    def delete(self, may: MayThietBi) -> None:
        self.db.delete(may)
        self.db.commit()
