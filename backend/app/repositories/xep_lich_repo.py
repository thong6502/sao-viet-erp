"""Repository Xếp lịch công đoạn — mọi truy vấn DB của bảng `xep_lich_cong_doan`.

Ngoài CRUD dòng lịch, giữ 2 truy vấn đặc thù của xếp lịch:
- HÀNG CHỜ (order-pool): nguồn đã `san_sang` mà CHƯA đưa vào kế hoạch — LSX độc lập (không thuộc bài
  ghép) + bài ghép. Đưa vào kế hoạch xong nguồn chuyển `da_lap_ke_hoach` nên tự rời hàng chờ.
- XUNG ĐỘT máy: các dòng đã xếp có máy + giờ, để service so khoảng [start, finish) theo từng máy.

Việc nạp Lsx(+công đoạn) / BaiGhep(+thành viên) tái dùng LsxRepository / BaiGhepRepository (đã test),
không lặp lại ở đây.
"""
from __future__ import annotations

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from ..models.bai_ghep import TT_SAN_SANG as BG_SAN_SANG, BaiGhep, BaiGhepThanhVien
from ..models.lsx import TT_SAN_SANG as LSX_SAN_SANG, Lsx
from ..models.xep_lich import TT_DA_XEP, XepLichCongDoan


class XepLichRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- reads ---------------------------------------------------------------

    def get(self, dong_id: int) -> XepLichCongDoan | None:
        return self.db.get(XepLichCongDoan, dong_id)

    def list_dong(self, *, may_id: int | None = None) -> list[XepLichCongDoan]:
        stmt = select(XepLichCongDoan)
        if may_id is not None:
            stmt = stmt.where(XepLichCongDoan.may_id == may_id)
        return list(
            self.db.execute(
                stmt.order_by(
                    XepLichCongDoan.lsx_id,
                    XepLichCongDoan.bai_ghep_id,
                    XepLichCongDoan.source_thu_tu,
                )
            ).scalars()
        )

    def by_lsx(self, lsx_id: int) -> list[XepLichCongDoan]:
        return list(
            self.db.execute(
                select(XepLichCongDoan)
                .where(XepLichCongDoan.lsx_id == lsx_id)
                .order_by(XepLichCongDoan.source_thu_tu)
            ).scalars()
        )

    def by_bai_ghep(self, bai_ghep_id: int) -> list[XepLichCongDoan]:
        return list(
            self.db.execute(
                select(XepLichCongDoan).where(XepLichCongDoan.bai_ghep_id == bai_ghep_id)
            ).scalars()
        )

    def exists_lsx(self, lsx_id: int) -> bool:
        return self.db.execute(
            select(XepLichCongDoan.id).where(XepLichCongDoan.lsx_id == lsx_id).limit(1)
        ).first() is not None

    def exists_bai_ghep(self, bai_ghep_id: int) -> bool:
        return self.db.execute(
            select(XepLichCongDoan.id).where(XepLichCongDoan.bai_ghep_id == bai_ghep_id).limit(1)
        ).first() is not None

    def rows_da_xep_co_may(self) -> list[XepLichCongDoan]:
        """Dòng đã xếp + có máy + có giờ — nguồn phát hiện trùng lịch máy (service so khoảng)."""
        return list(
            self.db.execute(
                select(XepLichCongDoan).where(
                    XepLichCongDoan.trang_thai == TT_DA_XEP,
                    XepLichCongDoan.may_id.is_not(None),
                    XepLichCongDoan.start_at.is_not(None),
                    XepLichCongDoan.finish_at.is_not(None),
                )
            ).scalars()
        )

    def nguon_cho_xep_lsx(self) -> list[Lsx]:
        """LSX `san_sang`, KHÔNG thuộc bài ghép nào (LSX gang lập kế hoạch qua bài ghép), mới nhất trước."""
        from sqlalchemy.orm import selectinload

        return list(
            self.db.execute(
                select(Lsx)
                .where(
                    Lsx.trang_thai == LSX_SAN_SANG,
                    ~exists(select(BaiGhepThanhVien.id).where(BaiGhepThanhVien.lsx_id == Lsx.id)),
                )
                .options(selectinload(Lsx.cong_doans))
                .order_by(Lsx.created_at.desc())
            ).scalars()
        )

    def nguon_cho_xep_bai_ghep(self) -> list[BaiGhep]:
        """Bài ghép `san_sang` (chưa lập kế hoạch), mới nhất trước."""
        from sqlalchemy.orm import selectinload

        return list(
            self.db.execute(
                select(BaiGhep)
                .where(BaiGhep.trang_thai == BG_SAN_SANG)
                .options(selectinload(BaiGhep.thanh_viens))
                .order_by(BaiGhep.created_at.desc())
            ).scalars()
        )

    # --- writes --------------------------------------------------------------

    def add(self, row: XepLichCongDoan) -> XepLichCongDoan:
        self.db.add(row)
        self.db.flush()
        return row

    def add_all(self, rows: list[XepLichCongDoan]) -> None:
        self.db.add_all(rows)
        self.db.flush()

    def delete_rows(self, rows: list[XepLichCongDoan]) -> None:
        for r in rows:
            self.db.delete(r)
        self.db.flush()

    def commit(self) -> None:
        self.db.commit()
