"""Service — Kho P0: ghi move (có quy đổi đơn vị + guard xuất âm) + tồn, trên Material."""
from __future__ import annotations

from ..models.material import Material
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.warehouse_stock_repo import StockRepo


class StockError(Exception):
    pass


def stock_unit(material: Material) -> str:
    """Đơn vị tồn chuẩn của vật tư: base_uom nếu có, else unit."""
    return (getattr(material, "base_uom", None) or material.unit or "").strip()


_REAM = {"ream", "ram", "rim"}


def to_stock_qty(material: Material, qty: float, input_uom: str | None) -> float:
    """Quy đổi số lượng nhập (theo input_uom) về ĐƠN VỊ TỒN của vật tư.

    Xử lý các trường hợp phổ biến ngành in; không khai được thì 1:1.
    - ream → tờ: ×500.
    - kg → tờ: theo gsm × khổ (tờ = kg / (gsm/1000 × rộng×cao/10000)).
    - có conversion_factor: ×factor.
    """
    base = stock_unit(material).lower()
    src = (input_uom or "").strip().lower()
    if not src or src == base:
        return float(qty)

    is_sheet_base = base in {"to", "tờ", "to_in", "sheet"}
    if src in _REAM and is_sheet_base:
        return float(qty) * 500.0
    if src == "kg" and is_sheet_base:
        gsm = getattr(material, "gsm", None)
        w = getattr(material, "width_cm", None)
        h = getattr(material, "height_cm", None)
        if gsm and w and h:
            area_m2 = (float(w) * float(h)) / 10000.0
            kg_per_sheet = (float(gsm) / 1000.0) * area_m2
            if kg_per_sheet > 0:
                return float(qty) / kg_per_sheet
    factor = getattr(material, "conversion_factor", None)
    if factor:
        return float(qty) * float(factor)
    return float(qty)  # không khai được → 1:1


class StockService:
    def __init__(self, repo: StockRepo, audit: AuditLogRepository, db) -> None:
        self.repo = repo
        self.audit = audit
        self.db = db

    def _material(self, material_id: int) -> Material:
        m = self.db.get(Material, material_id)
        if m is None:
            raise StockError("Vật tư không tồn tại.")
        return m

    def create_move(
        self,
        *,
        material_id: int,
        warehouse_id: int,
        lot_id: int | None,
        quantity: float,
        input_uom: str | None,
        move_type: str,
        reason: str | None,
        note: str | None,
        actor,
    ):
        material = self._material(material_id)
        if lot_id is not None:
            lot = self.repo.get_lot(lot_id)
            if lot is None or lot.material_id != material_id:
                raise StockError("Lô không thuộc vật tư này.")
        base_qty = to_stock_qty(material, abs(float(quantity)), input_uom)

        # Dấu theo loại move; điều chỉnh giữ dấu người dùng nhập.
        if move_type in ("nhap", "ton_dau_ky"):
            delta = base_qty
        elif move_type == "xuat":
            delta = -base_qty
        else:  # dieu_chinh
            delta = base_qty if float(quantity) >= 0 else -base_qty

        if delta < 0:
            current = self.repo.bucket_qty(
                material_id=material_id, warehouse_id=warehouse_id, lot_id=lot_id
            )
            if current + delta < 0:
                raise StockError(f"Xuất vượt tồn: tồn hiện có {current:g}.")

        move = self.repo.create_move(
            material_id=material_id, warehouse_id=warehouse_id, lot_id=lot_id,
            qty_delta=delta, unit=stock_unit(material), move_type=move_type,
            reason=reason, note=note, created_by_user_id=getattr(actor, "id", None),
        )
        self.audit.create(
            actor_user_id=actor.id, action=f"stock_{move_type}",
            target=f"stock_move:{move.id}", detail=f"{material.code} {delta:g} {stock_unit(material)}",
        )
        return move
