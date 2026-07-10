"""Service — Đợt kiểm kê & điều chỉnh tồn (spec-13 C, DacTa ch.8).

Tạo đợt → chốt tồn HỆ THỐNG (snapshot) → nhập tồn THỰC ĐẾM → duyệt: tự sinh StockMove
điều chỉnh chênh lệch (thừa +, thiếu −), giá vốn theo bình quân.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import Session, selectinload

from ..models.material import Material
from ..models.warehouse_catalog import WhItemStatus
from ..models.warehouse_count import StockCount, StockCountLine
from ..models.warehouse_stock import StockLot, StockMove
from ..repositories.warehouse_stock_repo import StockRepo
from .stock_service import stock_unit

_VN = timezone(timedelta(hours=7))


class CountError(Exception):
    pass


class CountService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def next_code(self) -> str:
        yy = datetime.now(_VN).strftime("%y")
        prefix = f"KK-{yy}-"
        max_n = 0
        for code in self.db.execute(select(StockCount.code).where(StockCount.code.like(f"{prefix}%"))).scalars():
            try:
                max_n = max(max_n, int(code[len(prefix):]))
            except ValueError:
                continue
        return f"{prefix}{max_n + 1:04d}"

    def get(self, count_id: int) -> StockCount | None:
        return self.db.execute(
            select(StockCount).options(selectinload(StockCount.lines)).where(StockCount.id == count_id)
        ).scalars().first()

    def list(self, *, status=None, warehouse_id=None, page=1, size=50):
        conds = []
        if status:
            conds.append(StockCount.status == status)
        if warehouse_id:
            conds.append(StockCount.warehouse_id == warehouse_id)
        base = select(StockCount).options(selectinload(StockCount.lines))
        count_stmt = select(func.count()).select_from(StockCount)
        for c in conds:
            base = base.where(c)
            count_stmt = count_stmt.where(c)
        total = self.db.execute(count_stmt).scalar_one()
        base = base.order_by(desc(StockCount.created_at), StockCount.id.desc())
        page, size = max(1, page), max(1, min(size, 200))
        base = base.offset((page - 1) * size).limit(size)
        return list(self.db.execute(base).scalars()), total

    def create(self, *, warehouse_id: int, note: str | None, actor,
               participants: str | None = None, material_group: str | None = None) -> StockCount:
        """Chốt tồn hệ thống hiện tại của kho thành các dòng kiểm kê (chưa đếm).
        material_group → chỉ chốt vật tư thuộc nhóm đó (phạm vi kiểm kê)."""
        balance = StockRepo(self.db).balance(warehouse_id=warehouse_id)
        if material_group:
            mids = [b["material_id"] for b in balance]
            groups = dict(self.db.execute(
                select(Material.id, Material.material_group).where(Material.id.in_(mids))
            ).all()) if mids else {}
            balance = [b for b in balance if groups.get(b["material_id"]) == material_group]
        count = StockCount(
            code=self.next_code(), warehouse_id=warehouse_id, status="open",
            participants=participants, note=note, created_by_user_id=getattr(actor, "id", None),
        )
        for b in balance:
            count.lines.append(StockCountLine(
                material_id=b["material_id"], lot_id=b["lot_id"],
                system_qty=b["on_hand"], unit=b["unit"],
            ))
        self.db.add(count)
        self.db.commit()
        self.db.refresh(count)
        return count

    def set_counts(self, count: StockCount, lines: list[dict]) -> None:
        """Cập nhật số thực đếm + kém/mất phẩm chất + lý do. line_id → sửa dòng; không có →
        thêm dòng mới (hàng thừa, system_qty=0)."""
        if count.status != "open":
            raise CountError("Chỉ nhập đếm khi đợt đang mở.")
        by_id = {ln.id: ln for ln in count.lines}
        for row in lines:
            lid = row.get("line_id")
            if lid is not None and lid in by_id:
                ln = by_id[lid]
                ln.counted_qty = row.get("counted_qty")
                ln.defective_qty = row.get("defective_qty")
                ln.damaged_qty = row.get("damaged_qty")
                ln.note = row.get("note")
            elif row.get("material_id"):
                mat = self.db.get(Material, row["material_id"])
                unit = stock_unit(mat) if mat else None
                count.lines.append(StockCountLine(
                    material_id=row["material_id"], lot_id=row.get("lot_id"),
                    system_qty=0, counted_qty=row.get("counted_qty"),
                    defective_qty=row.get("defective_qty"), damaged_qty=row.get("damaged_qty"),
                    note=row.get("note"), unit=unit,
                ))
        self.db.commit()

    def _avg_cost(self, *, material_id, warehouse_id) -> int | None:
        rows = self.db.execute(
            select(StockMove.qty_delta, StockMove.unit_cost).where(
                StockMove.material_id == material_id, StockMove.warehouse_id == warehouse_id,
                StockMove.unit_cost.isnot(None),
            )
        ).all()
        tq = sum(float(q) for q, _c in rows)
        tv = sum(float(q) * float(c) for q, c in rows)
        return int(round(tv / tq)) if tq > 0 else None

    def post(self, count: StockCount, actor) -> int:
        """Duyệt: sinh StockMove điều chỉnh cho từng dòng có chênh lệch. Trả số dòng điều chỉnh."""
        if count.status != "open":
            raise CountError("Đợt kiểm kê không ở trạng thái mở.")
        avail = self.db.execute(
            select(WhItemStatus.id).where(WhItemStatus.code == "AVAILABLE")
        ).scalars().first()
        adjusted = 0
        for ln in count.lines:
            if ln.counted_qty is None:
                continue  # chưa đếm → không điều chỉnh
            if ln.lot_id is not None:
                lot = self.db.get(StockLot, ln.lot_id)
                if lot is None or lot.material_id != ln.material_id:
                    raise CountError("Lô không thuộc vật tư của dòng.")
            diff = float(ln.counted_qty) - float(ln.system_qty)
            if diff == 0:
                continue
            cost = self._avg_cost(material_id=ln.material_id, warehouse_id=count.warehouse_id)
            self.db.add(StockMove(
                material_id=ln.material_id, warehouse_id=count.warehouse_id, lot_id=ln.lot_id,
                status_id=avail, qty_delta=diff, unit=ln.unit or "", unit_cost=cost,
                move_type="kiem_ke", reason="Điều chỉnh kiểm kê",
                ref_type="stock_count", ref_id=count.id,
                created_by_user_id=getattr(actor, "id", None),
            ))
            adjusted += 1
        count.status = "posted"
        count.posted_by_user_id = getattr(actor, "id", None)
        count.posted_at = datetime.now(timezone.utc)
        self.db.commit()
        return adjusted

    def cancel(self, count: StockCount) -> None:
        if count.status == "posted":
            raise CountError("Đợt đã ghi sổ, không hủy được.")
        count.status = "cancelled"
        self.db.commit()
