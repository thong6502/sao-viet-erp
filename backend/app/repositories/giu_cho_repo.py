"""Truy vấn bảng GIỮ CHỖ vật tư. Không luật nghiệp vụ nào ở đây — xem `giu_cho_service`."""
from __future__ import annotations

from sqlalchemy import delete, func, select, tuple_
from sqlalchemy.orm import Session

from ..models.vat_tu_giu_cho import VatTuGiuCho

Hang = tuple[str, int]


class GiuChoRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def da_giu_map(self, hangs: list[Hang]) -> dict[Hang, float]:
        """`{(loại, id): TỔNG đang giữ}` — gộp MỌI chủ thể, MỌI nguồn.

        Đây là số bị trừ khỏi tồn để ra TỒN TỰ DO, nên phải gộp cả `dang_ve`: phần bám vào lô đang
        mua cũng đã có chủ, hàng về tới nơi là thuộc về lệnh đó rồi.
        """
        if not hangs:
            return {}
        rows = self.db.execute(
            select(VatTuGiuCho.hang_loai, VatTuGiuCho.hang_id, func.sum(VatTuGiuCho.so_luong))
            .where(tuple_(VatTuGiuCho.hang_loai, VatTuGiuCho.hang_id).in_(
                [tuple(h) for h in hangs]))
            .group_by(VatTuGiuCho.hang_loai, VatTuGiuCho.hang_id)
        )
        found = {(loai, hid): float(tong or 0) for loai, hid, tong in rows}
        return {tuple(h): found.get(tuple(h), 0.0) for h in hangs}

    def cua_chu_the(self, *, lsx_id: int | None, bai_ghep_id: int | None) -> list[VatTuGiuCho]:
        stmt = select(VatTuGiuCho)
        stmt = (stmt.where(VatTuGiuCho.lsx_id == lsx_id) if lsx_id is not None
                else stmt.where(VatTuGiuCho.bai_ghep_id == bai_ghep_id))
        return list(self.db.execute(stmt.order_by(VatTuGiuCho.id.asc())).scalars())

    def cua_nhieu_lsx(self, lsx_ids: list[int]) -> dict[int, list[VatTuGiuCho]]:
        """`{lsx_id: dòng giữ chỗ}` cho NHIỀU lệnh trong MỘT câu — bản gộp của `cua_chu_the`.

        Có mặt vì màn danh sách hỏi trạng thái giữ chỗ của cả trang lệnh một lượt; gọi
        `cua_chu_the` trong vòng lặp là đúng N+1 (mỗi lệnh một câu SELECT).

        TOÀN ÁNH trên `lsx_ids`: lệnh không có dòng nào vẫn trả `[]`, để nơi gọi khỏi phải `.get`.
        """
        ket: dict[int, list[VatTuGiuCho]] = {i: [] for i in lsx_ids}
        if not lsx_ids:
            return ket
        rows = self.db.execute(
            select(VatTuGiuCho)
            .where(VatTuGiuCho.lsx_id.in_(lsx_ids))
            .order_by(VatTuGiuCho.id.asc())
        ).scalars()
        for r in rows:
            ket[r.lsx_id].append(r)
        return ket

    def xoa_cua_chu_the(self, *, lsx_id: int | None, bai_ghep_id: int | None) -> int:
        stmt = delete(VatTuGiuCho)
        stmt = (stmt.where(VatTuGiuCho.lsx_id == lsx_id) if lsx_id is not None
                else stmt.where(VatTuGiuCho.bai_ghep_id == bai_ghep_id))
        n = self.db.execute(stmt).rowcount or 0
        self.db.commit()
        return n

    def them(self, rows: list[VatTuGiuCho]) -> None:
        if not rows:
            return
        self.db.add_all(rows)
        self.db.commit()

    def tat_ca(self) -> list[VatTuGiuCho]:
        """MỌI dòng giữ chỗ, kể cả của chủ thể đã rơi khỏi bảng cân đối.

        Cần cho danh sách "giữ lâu chưa chạy": lệnh bị kéo ngược về `nhap` biến mất khỏi bảng cân
        đối nhưng dòng giữ chỗ VẪN trừ vào tồn tự do của mọi người khác. Chỉ duyệt theo bảng cân
        đối thì đúng những chỗ giữ tệ nhất lại là chỗ không ai nhìn thấy.
        """
        return list(self.db.execute(
            select(VatTuGiuCho).order_by(VatTuGiuCho.id.asc())).scalars())

    def chu_the_da_xep_lich(self) -> tuple[set[int], set[int]]:
        """`(lsx_ids, bai_ghep_ids)` ĐÃ có dòng trên bàn xếp lịch.

        Không lọc theo trạng thái dòng lịch (`cho_xep` / `da_xep`): cửa chặn giữ chỗ nằm ở lúc ĐƯA
        VÀO kế hoạch, nên chỉ cần có dòng là chủ thể đó đã đi qua cửa — tức chỗ giữ đã dùng đúng
        việc của nó. Lọc thêm `da_xep` sẽ đếm nhầm lệnh đang chờ gán máy thành "giữ mà chưa chạy".
        """
        from ..models.xep_lich import XepLichCongDoan

        lsx = set(self.db.execute(
            select(XepLichCongDoan.lsx_id).where(XepLichCongDoan.lsx_id.isnot(None))).scalars())
        bai = set(self.db.execute(
            select(XepLichCongDoan.bai_ghep_id)
            .where(XepLichCongDoan.bai_ghep_id.isnot(None))).scalars())
        return lsx, bai

    def dang_bat(self) -> tuple[set[int], set[int]]:
        """`(lsx_ids, bai_ghep_ids)` đang BẬT công tắc — nguồn cho `nhat_them` khi hàng về."""
        from ..models.bai_ghep import BaiGhep
        from ..models.lsx import Lsx

        lsx = set(self.db.execute(
            select(Lsx.id).where(Lsx.giu_cho_bat.is_(True))).scalars())
        bai = set(self.db.execute(
            select(BaiGhep.id).where(BaiGhep.giu_cho_bat.is_(True))).scalars())
        return lsx, bai
