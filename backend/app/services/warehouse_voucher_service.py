"""Service — cỗ máy chứng từ: vòng đời phiếu + ghi sổ (post) → StockMove (spec-13)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.material import Material
from ..models.warehouse_catalog import WhItemStatus, WhVoucherType
from ..models.warehouse_stock import StockLot, StockMove
from ..models.warehouse_voucher import StockVoucher
from .stock_service import stock_unit, to_stock_qty


class VoucherError(Exception):
    pass


class VoucherService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- helpers -----------------------------------------------------------
    def _default_status_id(self) -> int | None:
        row = self.db.execute(
            select(WhItemStatus.id).where(WhItemStatus.code == "AVAILABLE")
        ).scalars().first()
        return row

    def _bucket_qty(self, *, material_id, warehouse_id, lot_id) -> float:
        stmt = select(func.coalesce(func.sum(StockMove.qty_delta), 0)).where(
            StockMove.material_id == material_id, StockMove.warehouse_id == warehouse_id
        )
        stmt = stmt.where(
            StockMove.lot_id == lot_id if lot_id is not None else StockMove.lot_id.is_(None)
        )
        return float(self.db.execute(stmt).scalar_one())

    def _add_move(self, *, material, warehouse_id, lot_id, status_id, qty_delta, move_type, voucher, unit_cost=None):
        self.db.add(StockMove(
            material_id=material.id, warehouse_id=warehouse_id, lot_id=lot_id,
            status_id=status_id, qty_delta=qty_delta, unit=stock_unit(material),
            unit_cost=unit_cost, move_type=move_type, voucher_id=voucher.id,
            ref_type="voucher", ref_id=voucher.id,
            created_by_user_id=voucher.approved_by_user_id or voucher.created_by_user_id,
        ))
        self.db.flush()

    def _avg_cost(self, *, material_id, warehouse_id) -> int | None:
        """Giá vốn bình quân gia quyền của tồn hiện có (material×kho): Σ(qty×cost)/Σqty.
        Dùng khi xuất KHÔNG chỉ định lô (đích danh cần lô). None nếu chưa có giá."""
        rows = self.db.execute(
            select(StockMove.qty_delta, StockMove.unit_cost).where(
                StockMove.material_id == material_id,
                StockMove.warehouse_id == warehouse_id,
                StockMove.unit_cost.isnot(None),
            )
        ).all()
        tot_qty = sum(float(q) for q, _c in rows)
        tot_val = sum(float(q) * float(c) for q, c in rows)
        if tot_qty <= 0:
            return None
        return int(round(tot_val / tot_qty))

    def _guard_out(self, *, material_id, warehouse_id, lot_id, delta):
        current = self._bucket_qty(material_id=material_id, warehouse_id=warehouse_id, lot_id=lot_id)
        if current + delta < 0:
            raise VoucherError(f"Xuất vượt tồn: tồn hiện có {current:g} (không cho xuất âm).")

    # --- validate loại phiếu -----------------------------------------------
    def _validate_header(self, voucher: StockVoucher, vt: WhVoucherType) -> None:
        if vt.require_src_wh and not voucher.src_warehouse_id:
            raise VoucherError("Loại phiếu này bắt buộc Kho nguồn.")
        if vt.require_dst_wh and not voucher.dst_warehouse_id:
            raise VoucherError("Loại phiếu này bắt buộc Kho đích.")
        if not voucher.lines:
            raise VoucherError("Phiếu chưa có dòng nào.")

    # --- ghi sổ (post) -----------------------------------------------------
    def post(self, voucher: StockVoucher, actor) -> None:
        vt = self.db.get(WhVoucherType, voucher.voucher_type_id)
        if vt is None:
            raise VoucherError("Loại phiếu không tồn tại.")
        self._validate_header(voucher, vt)
        effect = vt.stock_effect
        default_status = self._default_status_id()
        src = voucher.src_warehouse_id
        dst = voucher.dst_warehouse_id

        for ln in voucher.lines:
            material = self.db.get(Material, ln.material_id)
            if material is None:
                raise VoucherError(f"Vật tư dòng #{ln.id} không tồn tại.")
            lot = None
            if ln.lot_id is not None:
                lot = self.db.get(StockLot, ln.lot_id)
                if lot is None or lot.material_id != ln.material_id:
                    raise VoucherError("Lô không thuộc vật tư của dòng.")
            base = to_stock_qty(material, float(ln.quantity), ln.uom)
            status_id = ln.status_id or default_status
            line_cost = int(ln.unit_cost) if ln.unit_cost else None

            if effect == "tang":
                wh = dst or src
                # Nhập: giá vốn = đơn giá nhập; ghi luôn vào lô (đích danh) nếu có lô.
                if lot is not None and line_cost is not None:
                    lot.unit_cost = line_cost
                self._add_move(material=material, warehouse_id=wh, lot_id=ln.lot_id,
                               status_id=status_id, qty_delta=base, move_type="nhap",
                               voucher=voucher, unit_cost=line_cost)
            elif effect == "giam":
                self._guard_out(material_id=ln.material_id, warehouse_id=src, lot_id=ln.lot_id, delta=-base)
                # Xuất: đích danh theo lô nếu có; không thì bình quân gia quyền.
                cost = (int(lot.unit_cost) if lot is not None and lot.unit_cost else None)
                if cost is None:
                    cost = self._avg_cost(material_id=ln.material_id, warehouse_id=src)
                self._add_move(material=material, warehouse_id=src, lot_id=ln.lot_id,
                               status_id=status_id, qty_delta=-base, move_type="xuat",
                               voucher=voucher, unit_cost=cost)
            elif effect == "chuyen_vi_tri":
                self._guard_out(material_id=ln.material_id, warehouse_id=src, lot_id=ln.lot_id, delta=-base)
                # Điều chuyển: giá vốn theo hàng KHÔNG đổi khi qua kho khác.
                cost = (int(lot.unit_cost) if lot is not None and lot.unit_cost else None)
                if cost is None:
                    cost = self._avg_cost(material_id=ln.material_id, warehouse_id=src)
                self._add_move(material=material, warehouse_id=src, lot_id=ln.lot_id,
                               status_id=status_id, qty_delta=-base, move_type="dieu_chuyen_out",
                               voucher=voucher, unit_cost=cost)
                self._add_move(material=material, warehouse_id=dst, lot_id=ln.lot_id,
                               status_id=status_id, qty_delta=base, move_type="dieu_chuyen_in",
                               voucher=voucher, unit_cost=cost)
            elif effect == "khong_tac_dong":
                pass
            else:
                raise VoucherError(f"Chiều tác động tồn không hỗ trợ: {effect}")

        voucher.status = "posted"
        voucher.approved_by_user_id = getattr(actor, "id", None)
        voucher.approved_at = datetime.now(timezone.utc)
        self.db.commit()
