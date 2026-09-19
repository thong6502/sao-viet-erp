"""Repository Xếp lịch công đoạn — mọi truy vấn DB của bảng `xep_lich_cong_doan`.

Ngoài CRUD dòng lịch, giữ 2 truy vấn đặc thù của xếp lịch:
- HÀNG CHỜ (order-pool): nguồn đã `san_sang` mà CHƯA đưa vào kế hoạch — LSX độc lập (không thuộc bài
  ghép) + bài ghép. Đưa vào kế hoạch xong nguồn chuyển `da_lap_ke_hoach` nên tự rời hàng chờ.
- XUNG ĐỘT máy: các dòng đã xếp có máy + giờ, để service so khoảng [start, finish) theo từng máy.

Việc nạp Lsx(+công đoạn) / BaiGhep(+thành viên) tái dùng LsxRepository / BaiGhepRepository (đã test),
không lặp lại ở đây.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Session

from ..models.bai_ghep import TT_SAN_SANG as BG_SAN_SANG, BaiGhep, BaiGhepThanhVien
from ..models.lsx import TT_SAN_SANG as LSX_SAN_SANG, Lsx
from ..models.xep_lich import TT_DA_XEP, XepLichCongDoan

# Hai khoảng của cùng một máy/tổ cách nhau không quá chừng này thì gộp làm một vế SQL.
_GOP_KHOANG = timedelta(days=1)


def _co_mui(dt: datetime) -> datetime:
    """SQLite trả giờ naive, Postgres trả aware — đưa về một loại để so/gộp được với nhau."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _gop_khoang(ks: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    ra: list[list[datetime]] = []
    for lo, hi in sorted(ks):
        if ra and lo <= ra[-1][1] + _GOP_KHOANG:
            ra[-1][1] = max(ra[-1][1], hi)
        else:
            ra.append([lo, hi])
    return [(lo, hi) for lo, hi in ra]


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

    def dong_quanh(self, lsx_ids) -> list[XepLichCongDoan]:
        """Phần bàn lịch đủ để tính ĐÚNG KHÍT dòng + vấn đề của `lsx_ids` — không nạp cả bàn.

        Ba vòng, mỗi vòng vì một bộ phận của engine:
          1. Dòng của chính các lệnh đó và của mọi lệnh CÙNG ĐƠN. `_do_thi` (sớm nhất / muộn nhất /
             độ dư) đi theo cạnh `lsx_cong_doan_phu_thuoc`, mà cạnh xuyên lệnh chỉ được nối trong
             một đơn (`LsxService` chặn cứng) ⇒ ngoài đơn không có gì đẩy được mốc của lệnh này.
             Bài ghép nối lệnh khác đơn nhưng đi qua `_gang_finish_map`, vốn tự hỏi DB, không cần dòng.
          2. Dòng CÙNG MÁY chồng khoảng giờ với dòng của `lsx_ids` — nguồn của `trung_may` và cờ
             `co_xung_dot`. Hai việc trùng máy thì khoảng giờ phải chạm nhau, nên việc ở xa không
             bao giờ đổi được kết luận.
          3. Dòng CÙNG TỔ chồng khoảng giờ — nguồn của `qua_tai_to`. Quét mốc chỉ cắt khoảng tại
             mốc của việc CHẠM khoảng đang xét, nên cũng chỉ cần hàng xóm chạm giờ.

        Vì vậy KHÔNG cần chọn "xét bao nhiêu ngày gần đây": phạm vi đi theo chính khoảng giờ của
        lệnh được hỏi. Khoảng của cùng một máy/tổ được gộp khi cách nhau ≤ 1 ngày để câu SQL
        gọn — gộp chỉ nạp THỪA, không bao giờ nạp thiếu. Index `(may_id, finish_at)` và
        `(department_id, finish_at)` (mg `0323`) để mỗi vế quét từ mốc `lo` trở đi thay vì cả lịch sử.

        Dòng hàng xóm trả kèm để bộ dò có cái mà so; số của CHÍNH chúng (độ dư, cờ chờ tiền đề…)
        không đủ dữ liệu để đúng — bên gọi chỉ được đọc kết quả của `lsx_ids`.
        """
        ids = {int(i) for i in (lsx_ids or ()) if i}
        if not ids:
            return []
        X = XepLichCongDoan
        cung_don = select(Lsx.id).where(Lsx.order_id.in_(
            select(Lsx.order_id).where(Lsx.id.in_(ids), Lsx.order_id.is_not(None))
        ))
        goc = list(self.db.execute(
            select(X).where(or_(X.lsx_id.in_(ids), X.lsx_id.in_(cung_don)))
        ).scalars())

        khoang: dict[tuple[str, int], list[tuple[datetime, datetime]]] = {}
        for r in goc:
            if r.lsx_id not in ids or r.start_at is None or r.finish_at is None:
                continue
            k = (_co_mui(r.start_at), _co_mui(r.finish_at))
            if r.may_id:
                khoang.setdefault(("may", r.may_id), []).append(k)
            if r.department_id:
                khoang.setdefault(("to", r.department_id), []).append(k)
        dk = []
        for (loai, rid), ks in khoang.items():
            cot = X.may_id if loai == "may" else X.department_id
            for lo, hi in _gop_khoang(ks):
                dk.append(and_(cot == rid, X.finish_at >= lo, X.start_at <= hi))

        da_co = {r.id for r in goc}
        ke = [r for r in self.db.execute(select(X).where(or_(*dk))).scalars()
              if r.id not in da_co] if dk else []
        # Cùng thứ tự với `list_dong` (NULL xếp CUỐI như Postgres) — bộ dò gom theo thứ tự dòng.
        return sorted(goc + ke, key=lambda r: (
            r.lsx_id is None, r.lsx_id or 0, r.bai_ghep_id is None, r.bai_ghep_id or 0,
            r.source_thu_tu or 0,
        ))

    def rows_da_xep_theo_to(self, department_id: int) -> list[XepLichCongDoan]:
        """Dòng đã xếp + có giờ của MỘT tổ — nền kiểm quân số lúc xem trước.

        Khác `rows_da_xep_co_may` (kéo cả bàn lịch để dò trùng máy): xem trước chỉ hỏi về ĐÚNG tổ
        của dòng đang kéo, mà thao tác đó chạy mỗi lần thả chuột.
        """
        return list(
            self.db.execute(
                select(XepLichCongDoan).where(
                    XepLichCongDoan.trang_thai == TT_DA_XEP,
                    XepLichCongDoan.department_id == department_id,
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
