"""Repository — Lô kho + ngưỡng tồn (spec-kho-de-nghi §6–§7).

Nguyên tắc: **không có bảng "tồn"**. Tồn luôn được TÍNH bằng Σ `sl_con_lai` của các lô,
nên tồn không thể lệch với lịch sử nhập/xuất. Mọi câu hỏi về tồn đều đi qua đây.

Mặt hàng được nhận diện bằng CẶP `(hang_loai, hang_id)` trỏ `giay_nguyen`/`vat_tu_in_an`
(mg 0171) — dùng nguyên cặp làm khoá dict luôn, tuple hashable nên khỏi bịa chuỗi khoá.
Mọi `sl_*` ở đây đã ở ĐƠN VỊ GỐC của mặt hàng; quy đổi xảy ra ở service trước khi ghi.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session

from ..models.stock_lot import LOT_EMPTY, LOT_ISSUABLE, StockLot, StockThreshold

# (hang_loai, hang_id) — một mặt hàng gốc.
Hang = tuple[str, int]


class StockLotRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, lot_id: int) -> StockLot | None:
        return self.db.get(StockLot, lot_id)

    def set_vi_tri(self, lot_id: int, vi_tri: str | None) -> StockLot | None:
        """Sửa vị trí cất lô. Trả None nếu không có lô."""
        lot = self.get(lot_id)
        if lot is None:
            return None
        lot.vi_tri = vi_tri
        self.db.commit()
        self.db.refresh(lot)
        return lot

    def by_ids(self, ids) -> dict[int, StockLot]:
        """Nạp NHIỀU lô trong 1 query — tránh N+1 khi serialize danh sách phiếu xuất."""
        ids = [i for i in set(ids) if i is not None]
        if not ids:
            return {}
        rows = self.db.execute(select(StockLot).where(StockLot.id.in_(ids))).scalars()
        return {lot.id: lot for lot in rows}

    def next_ma_lo(self, ma_hang: str, ngay: date) -> str:
        """Mã lô LOT-<mã hàng>-<yymmdd>-<seq>. `seq` đếm trong NGÀY của mã hàng đó nên
        mã đọc được bằng mắt; `ma_lo` unique nên va chạm sẽ nổ ở DB chứ không âm thầm.

        `ma_hang` giờ là mã trong danh mục gốc (GY001 / VT004), không phải mã `materials` cũ.
        """
        prefix = f"LOT-{ma_hang.strip().upper()}-{ngay:%y%m%d}-"
        n = self.db.execute(
            select(func.count()).select_from(StockLot).where(StockLot.ma_lo.like(f"{prefix}%"))
        ).scalar_one()
        return f"{prefix}{n + 1:02d}"

    def create(self, **data) -> StockLot:
        lot = StockLot(**data)
        self.db.add(lot)
        self.db.flush()
        return lot

    def issuable_lots(self, hang: Hang, kho_id: int) -> list[StockLot]:
        """Các lô còn hàng và được phép xuất, xếp theo gợi ý **FEFO rồi FIFO**: lô có hạn
        dùng gần nhất đi trước (tránh để quá date), hết hạn dùng thì tới lô nhập trước.

        Đây chỉ là GỢI Ý — thủ kho vẫn đổi được lô, vì BRD §3.19 chốt giá xuất là đích danh.
        """
        stmt = (
            select(StockLot)
            .where(
                StockLot.hang_loai == hang[0],
                StockLot.hang_id == hang[1],
                StockLot.kho_id == kho_id,
                StockLot.sl_con_lai > 0,
                StockLot.trang_thai.in_(LOT_ISSUABLE),
            )
            # NULL hsd xuống cuối: lô không có hạn thì không việc gì phải ưu tiên xuất.
            .order_by(
                (StockLot.hsd.is_(None)).asc(),
                StockLot.hsd.asc(),
                StockLot.ngay_nhap.asc(),
                StockLot.id.asc(),
            )
        )
        return list(self.db.execute(stmt).scalars())

    def consume(self, lot: StockLot, qty: float) -> None:
        """Trừ `qty` khỏi lô. Lô hết hàng thì đánh dấu `empty` để khỏi lọt vào gợi ý xuất.

        KHÔNG kiểm tra đủ/thiếu ở đây — service đã chặn trước; repo chỉ ghi.
        """
        lot.sl_con_lai = float(lot.sl_con_lai) - qty
        if float(lot.sl_con_lai) <= 0:
            lot.sl_con_lai = 0
            lot.trang_thai = LOT_EMPTY

    def on_hand(self, hang: Hang, kho_id: int | None = None) -> float:
        """**Tồn khả dụng** = Σ sl_con_lai của lô ở trạng thái xuất được, theo ĐƠN VỊ GỐC.

        Cố tình KHÔNG trả tồn thực tế: hàng chờ KCS / hàng lỗi nằm trong kho nhưng không
        dùng được, cộng vào là hứa suông với người đề nghị (BRD §1.5).
        """
        stmt = select(func.coalesce(func.sum(StockLot.sl_con_lai), 0)).where(
            StockLot.hang_loai == hang[0],
            StockLot.hang_id == hang[1],
            StockLot.trang_thai.in_(LOT_ISSUABLE),
        )
        if kho_id is not None:
            stmt = stmt.where(StockLot.kho_id == kho_id)
        return float(self.db.execute(stmt).scalar_one() or 0)

    def on_hand_map(self, hangs: list[Hang], kho_id: int | None = None) -> dict[Hang, float]:
        """Tồn khả dụng của NHIỀU mặt hàng trong 1 query — dùng khi vẽ đèn tín hiệu cho cả
        danh sách đề nghị (tránh N+1). Khoá dict là chính cặp `(hang_loai, hang_id)`."""
        if not hangs:
            return {}
        stmt = (
            select(StockLot.hang_loai, StockLot.hang_id,
                   func.coalesce(func.sum(StockLot.sl_con_lai), 0))
            .where(
                # `tuple_(...).in_(...)` để lọc đúng CẶP: lọc rời hai cột sẽ quét nhầm sang tổ hợp
                # không ai hỏi (giay#3 hỏi cùng vat_tu#7 thì kéo luôn vat_tu#3).
                tuple_(StockLot.hang_loai, StockLot.hang_id).in_([tuple(h) for h in hangs]),
                StockLot.trang_thai.in_(LOT_ISSUABLE),
            )
            .group_by(StockLot.hang_loai, StockLot.hang_id)
        )
        if kho_id is not None:
            stmt = stmt.where(StockLot.kho_id == kho_id)
        found = {(loai, hid): float(total or 0) for loai, hid, total in self.db.execute(stmt)}
        return {tuple(h): found.get(tuple(h), 0.0) for h in hangs}

    def list_lots(self, *, hang: Hang | None = None, kho_id: int | None = None,
                  con_hang: bool = True) -> list[StockLot]:
        stmt = select(StockLot)
        if hang is not None:
            stmt = stmt.where(StockLot.hang_loai == hang[0], StockLot.hang_id == hang[1])
        if kho_id is not None:
            stmt = stmt.where(StockLot.kho_id == kho_id)
        if con_hang:
            stmt = stmt.where(StockLot.sl_con_lai > 0)
        return list(self.db.execute(stmt.order_by(StockLot.ngay_nhap.asc(), StockLot.id.asc())).scalars())


class StockThresholdRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_for(self, hang: Hang, kho_id: int) -> StockThreshold | None:
        return self.db.execute(
            select(StockThreshold).where(
                StockThreshold.hang_loai == hang[0],
                StockThreshold.hang_id == hang[1],
                StockThreshold.kho_id == kho_id,
            )
        ).scalars().first()

    def map_for(self, hangs: list[Hang], kho_id: int) -> dict[Hang, StockThreshold]:
        if not hangs:
            return {}
        rows = self.db.execute(
            select(StockThreshold).where(
                tuple_(StockThreshold.hang_loai, StockThreshold.hang_id)
                .in_([tuple(h) for h in hangs]),
                StockThreshold.kho_id == kho_id,
            )
        ).scalars()
        return {(r.hang_loai, r.hang_id): r for r in rows}

    def list_active(self) -> list[StockThreshold]:
        """Mọi ngưỡng đang bật cảnh báo — nguồn quét để đẩy nhắc realtime (spec §8)."""
        return list(self.db.execute(
            select(StockThreshold).where(StockThreshold.canh_bao.is_(True))
        ).scalars())

    def upsert(self, *, hang: Hang, kho_id: int, **data) -> StockThreshold:
        obj = self.get_for(hang, kho_id)
        if obj is None:
            obj = StockThreshold(hang_loai=hang[0], hang_id=hang[1], kho_id=kho_id, nguong_ton=0)
            self.db.add(obj)
        for k, v in data.items():
            setattr(obj, k, v)
        self.db.commit()
        self.db.refresh(obj)
        return obj
