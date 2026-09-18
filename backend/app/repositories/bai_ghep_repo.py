"""Repository Bài ghép — mọi truy vấn DB của module Bài ghép nằm ở đây.

Hàng chờ ghép = LSX `san_sang`, CÓ công đoạn in (`nhom='print'`, `loai_buoc='may'`), CHƯA thuộc bài
ghép nào. "Đã ghép chưa" suy qua `NOT EXISTS(bai_ghep_thanh_vien)` — không cột cache.
"""
from __future__ import annotations

from sqlalchemy import and_, exists, select
from sqlalchemy.orm import Session, selectinload

from ..models.bai_ghep import BaiGhep, BaiGhepThanhVien
from ..models.bai_ghep_cong_doan import BaiGhepCongDoan, BaiGhepCongDoanMap
from ..models.lsx import LB_MAY, TT_SAN_SANG as LSX_SAN_SANG, Lsx, LsxCongDoan

NHOM_PRINT = "print"


class BaiGhepRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- reads ---------------------------------------------------------------

    def get(self, bai_ghep_id: int) -> BaiGhep | None:
        return self.db.execute(
            select(BaiGhep)
            .where(BaiGhep.id == bai_ghep_id)
            .options(selectinload(BaiGhep.thanh_viens))
        ).scalar_one_or_none()

    def by_ids(self, ids: list[int]) -> dict[int, BaiGhep]:
        """id → BaiGhep (kèm thành viên) — nạp lô cho bảng xếp lịch (né N+1)."""
        if not ids:
            return {}
        rows = self.db.execute(
            select(BaiGhep).where(BaiGhep.id.in_(ids)).options(selectinload(BaiGhep.thanh_viens))
        ).scalars()
        return {r.id: r for r in rows}

    def list(self) -> list[BaiGhep]:
        return list(
            self.db.execute(
                select(BaiGhep)
                .options(selectinload(BaiGhep.thanh_viens))
                .order_by(BaiGhep.created_at.desc())
            ).scalars()
        )

    def chua_lsx(self, lsx_ids: list[int] | set[int]) -> list[BaiGhep]:
        """Bài ghép có ÍT NHẤT MỘT thành viên nằm trong `lsx_ids` — bản HẸP của `list()`.

        `list()` kéo MỌI bài ghép của xưởng về rồi lọc bằng Python; đúng cho màn Kế hoạch vật tư
        (nó vẽ cả bảng) nhưng phí cho đường chỉ hỏi vài lệnh của MỘT TRANG: số bài chỉ có tăng
        theo đà sản xuất, còn trang thì vẫn 50 dòng. Lọc đẩy xuống SQL bằng `EXISTS`.
        """
        ids = [int(i) for i in (lsx_ids or []) if i]
        if not ids:
            return []
        return list(
            self.db.execute(
                select(BaiGhep)
                .where(exists(
                    select(BaiGhepThanhVien.id).where(
                        BaiGhepThanhVien.bai_ghep_id == BaiGhep.id,
                        BaiGhepThanhVien.lsx_id.in_(ids),
                    )
                ))
                .options(selectinload(BaiGhep.thanh_viens))
                .order_by(BaiGhep.created_at.desc())
            ).scalars()
        )

    def hang_cho_ghep(self) -> list[Lsx]:
        """LSX sẵn sàng + có công đoạn in + chưa thuộc bài ghép nào (mới nhất trước)."""
        return list(
            self.db.execute(
                select(Lsx)
                .where(
                    Lsx.trang_thai == LSX_SAN_SANG,
                    Lsx.cong_doans.any(
                        and_(LsxCongDoan.nhom == NHOM_PRINT, LsxCongDoan.loai_buoc == LB_MAY)
                    ),
                    ~exists(
                        select(BaiGhepThanhVien.id).where(BaiGhepThanhVien.lsx_id == Lsx.id)
                    ),
                )
                .options(selectinload(Lsx.cong_doans))
                .order_by(Lsx.created_at.desc())
            ).scalars()
        )

    def lsx_by_ids(self, lsx_ids: list[int]) -> dict[int, Lsx]:
        """id → LSX (kèm công đoạn) cho các LSX được chọn/đang là thành viên."""
        if not lsx_ids:
            return {}
        rows = self.db.execute(
            select(Lsx).where(Lsx.id.in_(lsx_ids)).options(selectinload(Lsx.cong_doans))
        ).scalars()
        return {r.id: r for r in rows}

    # --- nạp LÔ cho đường đọc nhiều bài một lượt (bảng cân đối vật tư) -------------
    # Engine bài ghép hỏi ba thứ này TỪNG BÀI, từng thành viên — đọc một bài thì không sao, nhưng
    # bảng cân đối chạy engine cho mọi bài trong xưởng nên mỗi bài đội thêm cả chục câu.

    def buoc_chung_theo_bai(self, bai_ids: list[int]) -> dict[int, list[BaiGhepCongDoan]]:
        """bai_ghep_id → các bước chung, CÙNG thứ tự với `BaiGhepService._buoc_chungs`."""
        ids = sorted({int(i) for i in bai_ids if i})
        ket: dict[int, list[BaiGhepCongDoan]] = {i: [] for i in ids}
        if not ids:
            return ket
        for c in self.db.execute(
            select(BaiGhepCongDoan)
            .where(BaiGhepCongDoan.bai_ghep_id.in_(ids))
            .order_by(BaiGhepCongDoan.thu_tu, BaiGhepCongDoan.id)
        ).scalars():
            ket[c.bai_ghep_id].append(c)
        return ket

    def gop_theo_bai(self, bai_ids: list[int]) -> dict[int, dict[int, set[str]]]:
        """bai_ghep_id → (lsx_id → step_key của lệnh đang bị bước chung đè)."""
        ids = sorted({int(i) for i in bai_ids if i})
        ket: dict[int, dict[int, set[str]]] = {i: {} for i in ids}
        if not ids:
            return ket
        for bai_id, m in self.db.execute(
            select(BaiGhepCongDoan.bai_ghep_id, BaiGhepCongDoanMap)
            .select_from(BaiGhepCongDoanMap)
            .join(BaiGhepCongDoan, BaiGhepCongDoan.id == BaiGhepCongDoanMap.bai_ghep_cong_doan_id)
            .where(BaiGhepCongDoan.bai_ghep_id.in_(ids))
        ).all():
            ket[bai_id].setdefault(m.lsx_id, set()).add(m.lsx_step_key)
        return ket

    def ghep_theo_lsx(self, lsx_ids: list[int]) -> dict[int, tuple[BaiGhep, BaiGhepThanhVien]]:
        """lsx_id → (bài, dòng thành viên) — bản lô của `LsxService._ghep_cua`."""
        ids = sorted({int(i) for i in lsx_ids if i})
        if not ids:
            return {}
        return {
            tv.lsx_id: (bg, tv)
            for bg, tv in self.db.execute(
                select(BaiGhep, BaiGhepThanhVien)
                .join(BaiGhepThanhVien, BaiGhepThanhVien.bai_ghep_id == BaiGhep.id)
                .where(BaiGhepThanhVien.lsx_id.in_(ids))
            ).all()
        }

    def lsx_da_ghep(self, lsx_ids: list[int]) -> set[int]:
        """Tập LSX (trong `lsx_ids`) ĐÃ thuộc một bài ghép — nguồn guard '1 LSX ≤ 1 bài'."""
        if not lsx_ids:
            return set()
        rows = self.db.execute(
            select(BaiGhepThanhVien.lsx_id).where(BaiGhepThanhVien.lsx_id.in_(lsx_ids))
        ).scalars()
        return set(rows)

    # --- writes --------------------------------------------------------------

    def add(self, bg: BaiGhep) -> BaiGhep:
        self.db.add(bg)
        self.db.flush()
        return bg

    def delete(self, bg: BaiGhep) -> None:
        self.db.delete(bg)
        self.db.flush()

    def commit(self) -> None:
        self.db.commit()
