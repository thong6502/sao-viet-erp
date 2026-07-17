"""Repository — Kho P0: lô tồn + sổ cái (trên Material)."""
from __future__ import annotations

from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import Session

from ..models.warehouse_stock import StockLot, StockMinLevel, StockMove

_LOT_SORT = {"code": StockLot.code, "created_at": StockLot.created_at}


class StockRepo:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- Lô -----------------------------------------------------------------
    def next_lot_code(self) -> str:
        max_n = 0
        for code in self.db.execute(
            select(StockLot.code).where(StockLot.code.like("LO%"))
        ).scalars():
            try:
                max_n = max(max_n, int(code[2:]))
            except ValueError:
                continue
        return f"LO{max_n + 1:06d}"

    def get_lot(self, lot_id: int) -> StockLot | None:
        return self.db.get(StockLot, lot_id)

    def create_lot(self, **fields) -> StockLot:
        lot = StockLot(code=self.next_lot_code(), **fields)
        self.db.add(lot)
        self.db.commit()
        self.db.refresh(lot)
        return lot

    def update_lot(self, lot: StockLot, **fields) -> StockLot:
        for k, v in fields.items():
            setattr(lot, k, v)
        self.db.commit()
        self.db.refresh(lot)
        return lot

    def delete_lot(self, lot: StockLot) -> None:
        self.db.delete(lot)
        self.db.commit()

    def list_lots(
        self,
        *,
        material_id: int | None = None,
        warehouse_id: int | None = None,
        is_active: bool | None = None,
        sort: str = "-created_at",
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[StockLot], int]:
        conds = []
        if material_id:
            conds.append(StockLot.material_id == material_id)
        if warehouse_id:
            conds.append(StockLot.warehouse_id == warehouse_id)
        if is_active is not None:
            conds.append(StockLot.is_active == is_active)
        base = select(StockLot)
        count_stmt = select(func.count()).select_from(StockLot)
        for c in conds:
            base = base.where(c)
            count_stmt = count_stmt.where(c)
        total = self.db.execute(count_stmt).scalar_one()
        direction, key = (desc, sort[1:]) if sort.startswith("-") else (asc, sort)
        base = base.order_by(direction(_LOT_SORT.get(key, StockLot.created_at)), StockLot.id.desc())
        page, size = max(1, page), max(1, min(size, 200))
        base = base.offset((page - 1) * size).limit(size)
        return list(self.db.execute(base).scalars()), total

    # --- Move ---------------------------------------------------------------
    def create_move(self, **fields) -> StockMove:
        move = StockMove(**fields)
        self.db.add(move)
        self.db.commit()
        self.db.refresh(move)
        return move

    def list_moves(
        self,
        *,
        material_id: int | None = None,
        warehouse_id: int | None = None,
        lot_id: int | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[StockMove], int]:
        conds = []
        if material_id:
            conds.append(StockMove.material_id == material_id)
        if warehouse_id:
            conds.append(StockMove.warehouse_id == warehouse_id)
        if lot_id:
            conds.append(StockMove.lot_id == lot_id)
        base = select(StockMove)
        count_stmt = select(func.count()).select_from(StockMove)
        for c in conds:
            base = base.where(c)
            count_stmt = count_stmt.where(c)
        total = self.db.execute(count_stmt).scalar_one()
        base = base.order_by(StockMove.created_at.desc(), StockMove.id.desc())
        page, size = max(1, page), max(1, min(size, 200))
        base = base.offset((page - 1) * size).limit(size)
        return list(self.db.execute(base).scalars()), total

    # --- Tồn (tính từ sổ cái) -----------------------------------------------
    def bucket_qty(self, *, material_id: int, warehouse_id: int, lot_id: int | None) -> float:
        stmt = select(func.coalesce(func.sum(StockMove.qty_delta), 0)).where(
            StockMove.material_id == material_id, StockMove.warehouse_id == warehouse_id
        )
        stmt = stmt.where(
            StockMove.lot_id == lot_id if lot_id is not None else StockMove.lot_id.is_(None)
        )
        return float(self.db.execute(stmt).scalar_one())

    def lot_qty_map(self, lot_ids: list[int]) -> dict[int, float]:
        if not lot_ids:
            return {}
        rows = self.db.execute(
            select(StockMove.lot_id, func.coalesce(func.sum(StockMove.qty_delta), 0))
            .where(StockMove.lot_id.in_(lot_ids))
            .group_by(StockMove.lot_id)
        ).all()
        return {int(lid): float(s) for lid, s in rows}

    def balance(self, *, material_id: int | None = None, warehouse_id: int | None = None) -> list[dict]:
        """Tồn tổng hợp theo (material×kho×lô): on_hand (trạng thái count_on_hand) +
        available (trạng thái count_available). Move không gắn trạng thái (null) coi như khả dụng."""
        from ..models.warehouse_catalog import WhItemStatus

        value_expr = func.coalesce(
            func.sum(StockMove.qty_delta * func.coalesce(StockMove.unit_cost, 0)), 0
        )
        stmt = (
            select(
                StockMove.material_id, StockMove.warehouse_id, StockMove.lot_id,
                StockMove.status_id, StockMove.unit,
                WhItemStatus.count_on_hand, WhItemStatus.count_available,
                func.coalesce(func.sum(StockMove.qty_delta), 0).label("qty"),
                value_expr.label("value"),
            )
            .join(WhItemStatus, WhItemStatus.id == StockMove.status_id, isouter=True)
            .group_by(
                StockMove.material_id, StockMove.warehouse_id, StockMove.lot_id,
                StockMove.status_id, StockMove.unit,
                WhItemStatus.count_on_hand, WhItemStatus.count_available,
            )
        )
        if material_id:
            stmt = stmt.where(StockMove.material_id == material_id)
        if warehouse_id:
            stmt = stmt.where(StockMove.warehouse_id == warehouse_id)

        buckets: dict[tuple, dict] = {}
        for mid, wid, lid, _sid, unit, on_flag, av_flag, qty, value in self.db.execute(stmt).all():
            key = (mid, wid, lid)
            b = buckets.setdefault(key, {
                "material_id": mid, "warehouse_id": wid, "lot_id": lid,
                "on_hand": 0.0, "available": 0.0, "value": 0.0, "unit": unit or "",
            })
            q = float(qty)
            if on_flag is None or on_flag:      # null trạng thái = tính tồn thực tế
                b["on_hand"] += q
                b["value"] += float(value)      # giá trị tồn theo hàng thực tế
            if av_flag is None or av_flag:      # null trạng thái = khả dụng
                b["available"] += q
            if unit and not b["unit"]:
                b["unit"] = unit
        return [b for b in buckets.values() if b["on_hand"] != 0 or b["available"] != 0]

    def nxt_report(
        self, *, date_from, date_to, material_id: int | None = None, warehouse_id: int | None = None,
    ) -> list[dict]:
        """Báo cáo Nhập–Xuất–Tồn theo (material×kho) trong kỳ [date_from, date_to] (datetime).
        Tồn đầu = SUM trước kỳ; Nhập/Xuất = biến động dương/âm trong kỳ; Tồn cuối = đầu + nhập − xuất."""
        from sqlalchemy import case

        in_period = (StockMove.created_at >= date_from) & (StockMove.created_at <= date_to)
        cost = func.coalesce(StockMove.unit_cost, 0)
        opening = func.coalesce(func.sum(case((StockMove.created_at < date_from, StockMove.qty_delta), else_=0)), 0)
        in_qty = func.coalesce(func.sum(case((in_period & (StockMove.qty_delta > 0), StockMove.qty_delta), else_=0)), 0)
        out_qty = func.coalesce(func.sum(case((in_period & (StockMove.qty_delta < 0), -StockMove.qty_delta), else_=0)), 0)
        # Giá trị (đồng)
        opening_val = func.coalesce(func.sum(case((StockMove.created_at < date_from, StockMove.qty_delta * cost), else_=0)), 0)
        in_val = func.coalesce(func.sum(case((in_period & (StockMove.qty_delta > 0), StockMove.qty_delta * cost), else_=0)), 0)
        out_val = func.coalesce(func.sum(case((in_period & (StockMove.qty_delta < 0), -StockMove.qty_delta * cost), else_=0)), 0)

        stmt = (
            select(
                StockMove.material_id, StockMove.warehouse_id,
                func.max(StockMove.unit).label("unit"),
                opening.label("opening"), in_qty.label("in_qty"), out_qty.label("out_qty"),
                opening_val.label("opening_val"), in_val.label("in_val"), out_val.label("out_val"),
            )
            .group_by(StockMove.material_id, StockMove.warehouse_id)
        )
        if material_id:
            stmt = stmt.where(StockMove.material_id == material_id)
        if warehouse_id:
            stmt = stmt.where(StockMove.warehouse_id == warehouse_id)

        out = []
        for mid, wid, unit, op, inq, outq, opv, inv, outv in self.db.execute(stmt).all():
            op, inq, outq = float(op), float(inq), float(outq)
            opv, inv, outv = float(opv), float(inv), float(outv)
            closing = op + inq - outq
            if op == 0 and inq == 0 and outq == 0 and closing == 0:
                continue
            out.append({
                "material_id": mid, "warehouse_id": wid, "unit": unit or "",
                "opening": op, "in_qty": inq, "out_qty": outq, "closing": closing,
                "opening_value": opv, "in_value": inv, "out_value": outv,
                "closing_value": opv + inv - outv,
            })
        return out

    def ledger(
        self, *, material_id: int, warehouse_id: int | None = None, lot_id: int | None = None,
        date_from=None, date_to=None,
    ) -> tuple[float, float, str, list[StockMove]]:
        """Thẻ kho: tồn đầu (trước date_from) + danh sách move trong kỳ theo thứ tự thời gian.
        Trả (opening_qty, opening_value, unit, moves[]). Không lọc ngày → opening = 0."""
        conds = [StockMove.material_id == material_id]
        if warehouse_id:
            conds.append(StockMove.warehouse_id == warehouse_id)
        if lot_id:
            conds.append(StockMove.lot_id == lot_id)

        opening = opening_val = 0.0
        if date_from is not None:
            op, opv = self.db.execute(
                select(
                    func.coalesce(func.sum(StockMove.qty_delta), 0),
                    func.coalesce(func.sum(StockMove.qty_delta * func.coalesce(StockMove.unit_cost, 0)), 0),
                ).where(*conds, StockMove.created_at < date_from)
            ).one()
            opening, opening_val = float(op), float(opv)

        unit = self.db.execute(select(func.max(StockMove.unit)).where(*conds)).scalar() or ""

        stmt = select(StockMove).where(*conds)
        if date_from is not None:
            stmt = stmt.where(StockMove.created_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(StockMove.created_at <= date_to)
        stmt = stmt.order_by(StockMove.created_at.asc(), StockMove.id.asc())
        return opening, opening_val, unit, list(self.db.execute(stmt).scalars())

    # --- Ngưỡng tồn tối thiểu + cảnh báo ------------------------------------
    def list_min_levels(self, *, warehouse_id: int | None = None) -> list[StockMinLevel]:
        stmt = select(StockMinLevel)
        if warehouse_id:
            stmt = stmt.where(StockMinLevel.warehouse_id == warehouse_id)
        stmt = stmt.order_by(StockMinLevel.warehouse_id, StockMinLevel.material_id)
        return list(self.db.execute(stmt).scalars())

    def get_min_level(self, material_id: int, warehouse_id: int) -> StockMinLevel | None:
        return self.db.execute(
            select(StockMinLevel).where(
                StockMinLevel.material_id == material_id,
                StockMinLevel.warehouse_id == warehouse_id,
            )
        ).scalar_one_or_none()

    def upsert_min_level(self, *, material_id: int, warehouse_id: int, min_qty: float, near_min_qty: float = 0, note: str | None) -> StockMinLevel:
        row = self.get_min_level(material_id, warehouse_id)
        if row is None:
            row = StockMinLevel(material_id=material_id, warehouse_id=warehouse_id, min_qty=min_qty, near_min_qty=near_min_qty, note=note)
            self.db.add(row)
        else:
            row.min_qty = min_qty
            row.near_min_qty = near_min_qty
            row.note = note
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete_min_level(self, row: StockMinLevel) -> None:
        self.db.delete(row)
        self.db.commit()

    def onhand_by_material_warehouse(self) -> dict[tuple[int, int], float]:
        """Tồn thực tế (on_hand) gộp theo (material×kho), gộp mọi lô. Dùng logic trạng thái
        như balance() để đồng nhất."""
        agg: dict[tuple[int, int], float] = {}
        for b in self.balance():
            key = (b["material_id"], b["warehouse_id"])
            agg[key] = agg.get(key, 0.0) + b["on_hand"]
        return agg

    def low_stock(self, *, warehouse_id: int | None = None, only_below: bool = True) -> list[dict]:
        """Cảnh báo tồn: mỗi ngưỡng (material×kho), so tồn với min_qty và near_min_qty.
        level: 'below' (tồn < min → đỏ), 'near' (min ≤ tồn < near_min → vàng), 'ok'.
        only_below=True → chỉ trả dòng có cảnh báo (below HOẶC near)."""
        onhand = self.onhand_by_material_warehouse()
        out = []
        for r in self.list_min_levels(warehouse_id=warehouse_id):
            cur = onhand.get((r.material_id, r.warehouse_id), 0.0)
            mn = float(r.min_qty)
            near = float(r.near_min_qty or 0)
            if cur < mn:
                level = "below"
            elif near > mn and cur < near:
                level = "near"
            else:
                level = "ok"
            if only_below and level == "ok":
                continue
            out.append({
                "material_id": r.material_id, "warehouse_id": r.warehouse_id,
                "min_qty": mn, "near_min_qty": near, "on_hand": cur,
                "shortfall": max(0.0, mn - cur), "below": cur < mn, "level": level,
                "note": r.note,
            })
        return out

    def stock_by_location(self, *, warehouse_id: int | None = None, material_id: int | None = None) -> list[dict]:
        """Tồn theo vị trí: gộp tồn còn lại của các lô theo (kho × vị trí × vật tư)."""
        # list_lots phân trang; gom tất cả lô liên quan (dev-scale).
        all_lots: list[StockLot] = []
        page = 1
        while True:
            chunk, total = self.list_lots(warehouse_id=warehouse_id, material_id=material_id, size=200, page=page)
            all_lots.extend(chunk)
            if page * 200 >= total or not chunk:
                break
            page += 1
        qmap = self.lot_qty_map([lot.id for lot in all_lots])
        buckets: dict[tuple, dict] = {}
        for lot in all_lots:
            qty = qmap.get(lot.id, 0.0)
            if qty == 0:
                continue
            loc = lot.location or "(chưa gán)"
            key = (lot.warehouse_id, loc, lot.material_id)
            b = buckets.setdefault(key, {
                "warehouse_id": lot.warehouse_id, "location": loc,
                "material_id": lot.material_id, "on_hand": 0.0,
            })
            b["on_hand"] += qty
        return [b for b in buckets.values() if b["on_hand"] != 0]

    def material_has_stock(self, material_id: int) -> bool:
        """SEAM-22: vật tư có bất kỳ move/lô tồn nào không."""
        m = self.db.execute(
            select(StockMove.id).where(StockMove.material_id == material_id).limit(1)
        ).first()
        if m is not None:
            return True
        return self.db.execute(
            select(StockLot.id).where(StockLot.material_id == material_id).limit(1)
        ).first() is not None
