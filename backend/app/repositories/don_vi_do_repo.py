"""Repository — Danh mục Đơn vị đo + CẶP quy đổi. CRUD + tra theo mã + liệt kê loại đo đã dùng."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased

from ..models.don_vi_do import DonViDo, DonViQuyDoi

_FIELDS = ("ten", "ho", "hieu_luc_tu", "ghi_chu", "active", "dung_lam_toc_do",
           "tram_dong_giay", "cong_thuc")
# `cong_thuc` KHÔNG còn trong danh sách ghi được của CẶP (14/08/2026) — cặp chỉ mang hệ số cố định.
# Cột `don_vi_do.cong_thuc` ở `_FIELDS` là chuyện khác: đó là CÁCH ĐO của chính đơn vị, trả LƯỢNG.
_CAP_FIELDS = ("tu_id", "den_id", "he_so", "ghi_chu")


@dataclass
class CapRow:
    """1 cặp quy đổi KÈM MÃ hai đầu — `quy_doi_service` là hàm thuần nên không tự truy DB được."""

    id: int
    tu_id: int
    den_id: int
    tu_ma: str
    den_ma: str
    tu_ten: str
    den_ten: str
    he_so: float
    ghi_chu: str | None = None


class DonViDoRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, item_id: int):
        return self.db.get(DonViDo, item_id)

    def find_by_ma(self, ma: str):
        ma = (ma or "").strip().lower()
        if not ma:
            return None
        return self.db.execute(
            select(DonViDo).where(func.lower(DonViDo.ma) == ma)
        ).scalars().first()

    def all_active(self) -> list[DonViDo]:
        """Toàn bộ đơn vị đang dùng — nguồn cho `quy_doi_service` (bảng nhỏ, nạp cả bảng là đủ)."""
        return list(
            self.db.execute(
                select(DonViDo).where(DonViDo.active.is_(True)).order_by(DonViDo.ho, DonViDo.ma)
            ).scalars()
        )

    def distinct_ho(self) -> list[str]:
        """Họ đã có trong dữ liệu — gợi ý cho ô "Họ" (form MỞ, không phải whitelist)."""
        rows = self.db.execute(
            select(DonViDo.ho).where(DonViDo.ho.is_not(None)).distinct()
        ).scalars()
        return sorted({(h or "").strip() for h in rows if (h or "").strip()})

    def list(self, *, q: str | None = None, ho: str | None = None, active: bool | None = None,
             page: int = 1, size: int = 50):
        conds = []
        if q:
            like = f"%{q.strip().lower()}%"
            conds.append(or_(func.lower(DonViDo.ma).like(like), func.lower(DonViDo.ten).like(like)))
        if ho:
            conds.append(func.lower(DonViDo.ho) == ho.strip().lower())
        if active is not None:
            conds.append(DonViDo.active.is_(active))
        base = select(DonViDo)
        count_stmt = select(func.count()).select_from(DonViDo)
        for c in conds:
            base = base.where(c)
            count_stmt = count_stmt.where(c)
        total = self.db.execute(count_stmt).scalar_one()
        page, size = max(1, page), max(1, min(size, 200))
        base = base.order_by(DonViDo.ho.asc(), DonViDo.ma.asc())
        base = base.offset((page - 1) * size).limit(size)
        return list(self.db.execute(base).scalars()), total

    def create(self, data: dict):
        obj = DonViDo(ma=data["ma"].strip().lower())
        for k in _FIELDS:
            if k in data:
                setattr(obj, k, data[k])
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def update(self, obj, data: dict):
        if data.get("ma"):
            obj.ma = data["ma"].strip().lower()
        for k in _FIELDS:
            if k in data:
                setattr(obj, k, data[k])
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def delete(self, obj) -> None:
        self.db.delete(obj)
        self.db.commit()

    # --- cặp quy đổi ---------------------------------------------------------

    def cap_rows(self, *, bo_qua_id: int | None = None) -> list[CapRow]:
        """Mọi cặp kèm mã/tên hai đầu. `bo_qua_id` để dò đường KHÔNG tính cặp đang sửa (nếu tính,
        nó tự mâu thuẫn với chính bản cũ của mình)."""
        tu, den = aliased(DonViDo), aliased(DonViDo)
        stmt = (
            select(DonViQuyDoi.id, DonViQuyDoi.tu_id, DonViQuyDoi.den_id,
                   tu.ma, den.ma, tu.ten, den.ten, DonViQuyDoi.he_so, DonViQuyDoi.ghi_chu)
            .join(tu, tu.id == DonViQuyDoi.tu_id)
            .join(den, den.id == DonViQuyDoi.den_id)
            .order_by(tu.ma.asc(), den.ma.asc())
        )
        if bo_qua_id is not None:
            stmt = stmt.where(DonViQuyDoi.id != bo_qua_id)
        return [
            CapRow(id=r[0], tu_id=r[1], den_id=r[2], tu_ma=r[3], den_ma=r[4],
                   tu_ten=r[5], den_ten=r[6], he_so=float(r[7]), ghi_chu=r[8])
            for r in self.db.execute(stmt).all()
        ]

    def list_cap(self, *, q: str | None = None, page: int = 1, size: int = 50):
        rows = self.cap_rows()
        if q:
            needle = q.strip().lower()
            rows = [r for r in rows
                    if needle in f"{r.tu_ma} {r.den_ma} {r.tu_ten} {r.den_ten}".lower()]
        total = len(rows)
        page, size = max(1, page), max(1, min(size, 200))
        return rows[(page - 1) * size: (page - 1) * size + size], total

    def get_cap(self, cap_id: int):
        return self.db.get(DonViQuyDoi, cap_id)

    def find_cap(self, tu_id: int, den_id: int):
        """Cặp giữa hai đơn vị theo CHIỀU NÀO CŨNG TÍNH — khai `tấn → kg` rồi khai tiếp `kg → tấn`
        là hai dòng nói cùng một chuyện, sớm muộn lệch nhau."""
        return self.db.execute(
            select(DonViQuyDoi).where(
                or_(
                    (DonViQuyDoi.tu_id == tu_id) & (DonViQuyDoi.den_id == den_id),
                    (DonViQuyDoi.tu_id == den_id) & (DonViQuyDoi.den_id == tu_id),
                )
            )
        ).scalars().first()

    # 🔴 `dong_ve()` ĐÃ GỠ 14/08/2026 cùng quy đổi động — nó tìm "dòng công thức trỏ về đơn vị này",
    # mà cặp nay không mang công thức nữa.

    def cong_doan_lay_lam_don_vi_ra(self, ma: str) -> list[str]:
        """Tên công đoạn đang lấy `ma` làm ĐƠN VỊ RA, và CẢ HAI vế đều ngoài dòng giấy.

        Dùng để chặn chiều ngược của luật vòng tròn: công đoạn khai xong xuôi rồi mới có người vào
        sửa công thức của đơn vị thêm `sl_vao`. Chỉ kể ca hai-vế-ngoài-dòng vì chỉ ở đó công thức
        của đơn vị RA mới được đọc.
        """
        from ..models.cong_doan import CongDoan
        from ..models.don_vi_do import DonViDo

        if not ma:
            return []
        tram = {d.ma: d.tram_dong_giay for d in self.db.execute(select(DonViDo)).scalars()}
        ra: list[str] = []
        for cd in self.db.execute(
            select(CongDoan).where(CongDoan.don_vi_ra == ma)
        ).scalars():
            if tram.get(cd.don_vi_vao) is None and tram.get(cd.don_vi_ra) is None:
                ra.append(cd.ten)
        return ra

    def create_cap(self, data: dict):
        obj = DonViQuyDoi(tu_id=data["tu_id"], den_id=data["den_id"], he_so=data["he_so"])
        if "ghi_chu" in data:
            obj.ghi_chu = data["ghi_chu"]
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def update_cap(self, obj, data: dict):
        for k in _CAP_FIELDS:
            if k in data:
                setattr(obj, k, data[k])
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def delete_cap(self, obj) -> None:
        self.db.delete(obj)
        self.db.commit()
