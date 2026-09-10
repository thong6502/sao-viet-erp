"""Truy vấn bảng `xep_lich_lenh` + nạp routing THEO LÔ cho Xếp lịch 3.

Mọi đường đọc CẮT theo cửa sổ thời gian hoặc theo tập `lsx_id` — không có đường nào trải toàn bộ
lịch sử. Routing của cả lô nạp bằng MỘT truy vấn `IN (...)`, không N+1: một lần vẽ bảng có thể
duyệt vài chục lệnh, hỏi routing từng lệnh là đúng bài N+1 đã dính một lần ở màn đơn hàng.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models.lsx import Lsx, LsxCongDoan
from ..models.xep_lich_lenh import XepLichLenh


class XepLichLenhRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ---------------------------------------------------------------- mốc

    def theo_lsx(self, lsx_id: int) -> XepLichLenh | None:
        return self.db.execute(
            select(XepLichLenh).where(XepLichLenh.lsx_id == lsx_id)
        ).scalar_one_or_none()

    def theo_nhieu_lsx(self, lsx_ids: list[int]) -> dict[int, XepLichLenh]:
        if not lsx_ids:
            return {}
        rows = self.db.execute(
            select(XepLichLenh).where(XepLichLenh.lsx_id.in_(lsx_ids))
        ).scalars()
        return {r.lsx_id: r for r in rows}

    def truoc_moc(self, den: datetime) -> list[XepLichLenh]:
        """Lệnh có mốc BẮT ĐẦU trước mép phải cửa sổ.

        Không lọc được mép trái ở SQL vì `ket_thuc` là số DẪN XUẤT (không có cột). Service trải
        lịch xong mới lọc chính xác theo giao với cửa sổ — xem `XepLich3Service.lich`.
        """
        return list(self.db.execute(
            select(XepLichLenh)
            .where(XepLichLenh.bat_dau_at <= den)
            .order_by(XepLichLenh.bat_dau_at)
        ).scalars())

    def them(self, row: XepLichLenh) -> XepLichLenh:
        self.db.add(row)
        self.db.flush()
        return row

    def xoa(self, row: XepLichLenh) -> None:
        self.db.delete(row)
        self.db.flush()

    # ---------------------------------------------------------------- lệnh

    def lsx_theo_ids(self, lsx_ids: list[int]) -> dict[int, Lsx]:
        if not lsx_ids:
            return {}
        rows = self.db.execute(select(Lsx).where(Lsx.id.in_(lsx_ids))).scalars()
        return {r.id: r for r in rows}

    def hang_cho(self, *, trang_thai: tuple[str, ...], tim: str | None,
                 trang: int, cd_trang: int) -> tuple[list[Lsx], int]:
        """Lệnh đủ điều kiện xếp mà CHƯA có mốc. Lọc + phân trang Ở MÁY CHỦ, luôn.

        Cắt trang trong JS sau khi kéo cả bảng về là đường đã bị bác một lần — thẻ hàng chờ có thể
        lên vài trăm khi xưởng dồn việc cuối tháng.
        """
        dieu_kien = [
            Lsx.trang_thai.in_(trang_thai),
            ~select(XepLichLenh.id).where(XepLichLenh.lsx_id == Lsx.id).exists(),
        ]
        if tim:
            mau = f"%{tim.strip()}%"
            dieu_kien.append(or_(Lsx.ma.ilike(mau), Lsx.ten.ilike(mau)))
        tong = self.db.execute(
            select(func.count()).select_from(Lsx).where(*dieu_kien)
        ).scalar_one()
        rows = list(self.db.execute(
            select(Lsx).where(*dieu_kien)
            # Gấp lên đầu, rồi tới hạn SX sớm nhất — đúng thứ tự người điều độ nhặt việc.
            .order_by(Lsx.is_rush.desc(), Lsx.han_hoan_thanh_sx.asc().nullslast(), Lsx.id)
            .offset(max(0, (trang - 1)) * cd_trang).limit(cd_trang)
        ).scalars())
        return rows, int(tong)

    # ---------------------------------------------------------------- routing

    def routing_theo_lo(self, lsx_ids: list[int]) -> dict[int, list[LsxCongDoan]]:
        """MỘT truy vấn cho cả lô. Gom theo `lsx_id`, sắp theo `thu_tu`."""
        if not lsx_ids:
            return {}
        rows = list(self.db.execute(
            select(LsxCongDoan)
            .where(LsxCongDoan.lsx_id.in_(lsx_ids))
            .order_by(LsxCongDoan.lsx_id, LsxCongDoan.thu_tu)
        ).scalars())
        out: dict[int, list[LsxCongDoan]] = {}
        for r in rows:
            out.setdefault(r.lsx_id, []).append(r)
        return out
