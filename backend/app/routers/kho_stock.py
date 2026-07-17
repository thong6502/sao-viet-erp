"""Router — Kho P0: lô tồn + nhập/xuất/điều chỉnh + tồn (trên Material). Gate module `kho`."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..deps import get_authorization_service, get_db, require_permission
from ..models.user import User
from ..realtime import kho_event_stream
from ..security import decode_access_token
from ..services.rbac_service import AuthorizationService
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.warehouse_stock_repo import StockRepo
from ..schemas.warehouse_stock import (
    LedgerOut,
    LedgerRow,
    LocationStockOut,
    LocationStockRow,
    LowStockOut,
    LowStockRow,
    ItemOverviewRow,
    ItemOverviewWh,
    KhoItemIn,
    MaterialOption,
    MinLevelIn,
    MinLevelListOut,
    MinLevelRow,
    NxtReportOut,
    NxtRow,
    PartnerOption,
    StockBalanceListOut,
    StockBalanceRow,
    StockLotIn,
    StockLotListOut,
    StockLotRow,
    StockMoveIn,
    StockMoveListOut,
    StockMoveRow,
)
from ..services.stock_service import StockError, StockService

MODULE = "kho"
router = APIRouter(prefix="/api/kho", tags=["kho-stock"])

_read = require_permission(MODULE, "read")
_create = require_permission(MODULE, "create")
_update = require_permission(MODULE, "update")
_delete = require_permission(MODULE, "delete")


def _svc(db: Session) -> StockService:
    return StockService(StockRepo(db), AuditLogRepository(db), db)


def _lot_row(repo: StockRepo, lot, qty_map=None) -> StockLotRow:
    row = StockLotRow.model_validate(lot)
    row.qty_on_hand = (qty_map or repo.lot_qty_map([lot.id])).get(lot.id, 0.0)
    return row


# --- Lô ---------------------------------------------------------------------
@router.get("/lots", response_model=StockLotListOut)
def list_lots(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(_read)],
    material_id: int | None = Query(default=None),
    warehouse_id: int | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
):
    repo = StockRepo(db)
    rows, total = repo.list_lots(
        material_id=material_id, warehouse_id=warehouse_id, is_active=is_active, page=page, size=size
    )
    qmap = repo.lot_qty_map([r.id for r in rows])
    return StockLotListOut(
        items=[_lot_row(repo, r, qmap) for r in rows], total=total, page=page, size=size
    )


@router.post("/lots", response_model=StockLotRow, status_code=status.HTTP_201_CREATED)
def create_lot(payload: StockLotIn, db: Annotated[Session, Depends(get_db)], user: Annotated[User, Depends(_create)]):
    repo = StockRepo(db)
    lot = repo.create_lot(**payload.model_dump())
    AuditLogRepository(db).create(
        actor_user_id=user.id, action="create_stock_lot", target=f"stock_lot:{lot.id}", detail=lot.code
    )
    return _lot_row(repo, lot)


@router.put("/lots/{lot_id}", response_model=StockLotRow)
def update_lot(lot_id: int, payload: StockLotIn, db: Annotated[Session, Depends(get_db)], user: Annotated[User, Depends(_update)]):
    repo = StockRepo(db)
    lot = repo.get_lot(lot_id)
    if lot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Không tìm thấy lô.")
    lot = repo.update_lot(lot, **payload.model_dump())
    AuditLogRepository(db).create(
        actor_user_id=user.id, action="update_stock_lot", target=f"stock_lot:{lot.id}", detail=lot.code
    )
    return _lot_row(repo, lot)


@router.delete("/lots/{lot_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_lot(lot_id: int, db: Annotated[Session, Depends(get_db)], user: Annotated[User, Depends(_delete)]):
    repo = StockRepo(db)
    lot = repo.get_lot(lot_id)
    if lot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Không tìm thấy lô.")
    if repo.lot_qty_map([lot_id]).get(lot_id, 0.0) != 0:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Lô còn tồn, không thể xóa.")
    repo.delete_lot(lot)
    AuditLogRepository(db).create(
        actor_user_id=user.id, action="delete_stock_lot", target=f"stock_lot:{lot_id}", detail=lot.code
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Nhập / xuất / điều chỉnh (ghi move) ------------------------------------
@router.post("/moves", response_model=StockMoveRow, status_code=status.HTTP_201_CREATED)
def create_move(payload: StockMoveIn, db: Annotated[Session, Depends(get_db)], user: Annotated[User, Depends(_create)]):
    try:
        move = _svc(db).create_move(
            material_id=payload.material_id, warehouse_id=payload.warehouse_id,
            lot_id=payload.lot_id, quantity=payload.quantity, input_uom=payload.input_uom,
            move_type=payload.move_type, reason=payload.reason, note=payload.note, actor=user,
        )
    except StockError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from None
    return StockMoveRow.model_validate(move)


@router.get("/moves", response_model=StockMoveListOut)
def list_moves(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(_read)],
    material_id: int | None = Query(default=None),
    warehouse_id: int | None = Query(default=None),
    lot_id: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
):
    rows, total = StockRepo(db).list_moves(
        material_id=material_id, warehouse_id=warehouse_id, lot_id=lot_id, page=page, size=size
    )
    return StockMoveListOut(
        items=[StockMoveRow.model_validate(r) for r in rows], total=total, page=page, size=size
    )


# --- Option vật tư cho dropdown (gate `kho`) --------------------------------
@router.get("/material-options", response_model=list[MaterialOption])
def material_options(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(_read)],
    q: str | None = Query(default=None),
    warehouse_id: int | None = Query(default=None, description="Chỉ vật tư thuộc kho này"),
):
    from sqlalchemy import func, or_, select as _select

    from ..models.material import Material

    stmt = _select(Material).where(Material.is_active.is_(True))
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(Material.code).like(like), func.lower(Material.name).like(like)))
    # Vật tư thuộc kho này; vật tư CŨ chưa gán kho (null) vẫn cho chọn để không kẹt dữ liệu cũ.
    if warehouse_id is not None:
        stmt = stmt.where(or_(Material.warehouse_id == warehouse_id, Material.warehouse_id.is_(None)))
    stmt = stmt.order_by(Material.code).limit(500)
    return [
        MaterialOption(
            id=m.id, code=m.code, name=m.name,
            unit=(getattr(m, "base_uom", None) or m.unit or ""),
            warehouse_id=m.warehouse_id, note=m.note,
            default_supplier=getattr(m, "default_supplier", None),
        )
        for m in db.execute(stmt).scalars()
    ]


# --- Gợi ý đối tượng phiếu (NCC / Khách hàng) — gated `kho` để thủ kho dùng được -----
@router.get("/partner-options", response_model=list[PartnerOption])
def partner_options(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(_read)],
    kind: str = Query(..., description="ncc = nhà cung cấp, khach = khách hàng"),
    q: str | None = Query(default=None),
):
    from sqlalchemy import func, select as _select

    if kind == "ncc":
        from ..models.purchase import Supplier as Model
    elif kind == "khach":
        from ..models.customer import Customer as Model
    else:
        return []

    stmt = _select(Model.id, Model.name)
    if q:
        stmt = stmt.where(func.lower(Model.name).like(f"%{q.strip().lower()}%"))
    stmt = stmt.order_by(Model.name).limit(500)
    return [PartnerOption(id=i, name=n) for i, n in db.execute(stmt).all()]


# --- Danh mục hàng nhìn từ kho: mặt hàng + kho đang có tồn (gated `kho:read`) ------------
@router.get("/items-overview", response_model=list[ItemOverviewRow])
def items_overview(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(_read)],
    q: str | None = Query(default=None),
):
    from sqlalchemy import func, or_, select as _select

    from ..models.material import Material
    from ..models.warehouse import Warehouse

    # (material_id, warehouse_id) -> tồn thực tế; gom kho có tồn > 0 theo mặt hàng.
    onhand = StockRepo(db).onhand_by_material_warehouse()
    wh = {w.id: w for w in db.execute(_select(Warehouse)).scalars()}
    mat_wh: dict[int, list[int]] = {}
    for (mid, wid), qty in onhand.items():
        if abs(float(qty)) > 1e-9 and wid in wh:
            mat_wh.setdefault(mid, []).append(wid)

    stmt = _select(Material)
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(Material.code).like(like), func.lower(Material.name).like(like)))
    stmt = stmt.order_by(Material.code)

    out: list[ItemOverviewRow] = []
    for m in db.execute(stmt).scalars():
        whs = [ItemOverviewWh(id=w, code=wh[w].code) for w in sorted(mat_wh.get(m.id, []))]
        out.append(ItemOverviewRow(
            id=m.id, code=m.code, name=m.name,
            unit=(getattr(m, "base_uom", None) or m.unit or ""),
            material_type=m.material_type, material_group=m.material_group,
            is_active=m.is_active, warehouses=whs,
        ))
    return out


# --- Tạo nhanh mặt hàng ngay tại phiếu (popup tìm-hoặc-tạo, gated `kho:create`) -----------
# kind → (material_type, material_group). NVL & thành phẩm/BTP đều tạo self-service tại phiếu.
_ITEM_KIND_MAP = {
    "nvl": ("vat_tu", "auxiliary"),
    "thanh_pham": ("thanh_pham", "thanh_pham"),
    "ban_thanh_pham": ("ban_thanh_pham", "ban_thanh_pham"),
}


@router.post("/items", response_model=MaterialOption, status_code=status.HTTP_201_CREATED)
def create_kho_item(
    payload: KhoItemIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(_create)],
):
    """Người vận hành (Kho/Sản xuất) tạo mặt hàng ngay khi lập phiếu — mã tự sinh VT###/TP###/BTP###.
    KHÔNG chặn trùng tên; định danh bằng mã. Popup có tìm hàng có sẵn nên hạn chế trùng."""
    from ..repositories.material_repo import MaterialRepository

    name = payload.name.strip()
    unit = payload.unit.strip()
    if not name or not unit:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Cần Tên + Đơn vị tính.")
    mt, grp = _ITEM_KIND_MAP.get(payload.kind, _ITEM_KIND_MAP["nvl"])
    m = MaterialRepository(db).create(
        name=name, material_type=mt, unit=unit, material_group=grp, is_active=True,
    )
    AuditLogRepository(db).create(
        actor_user_id=user.id, action="create_kho_item",
        target=f"material:{m.id}", detail=f"{m.code} {m.name}",
    )
    return MaterialOption(
        id=m.id, code=m.code, name=m.name,
        unit=(getattr(m, "base_uom", None) or m.unit or ""),
        warehouse_id=m.warehouse_id, note=m.note,
        default_supplier=getattr(m, "default_supplier", None),
    )


# --- Báo cáo Nhập–Xuất–Tồn (DacTa Table 7) ----------------------------------
@router.get("/reports/nxt", response_model=NxtReportOut)
def report_nxt(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(_read)],
    authz: Annotated[AuthorizationService, Depends(get_authorization_service)],
    date_from: str = Query(..., alias="from", description="YYYY-MM-DD"),
    date_to: str = Query(..., alias="to", description="YYYY-MM-DD"),
    material_id: int | None = Query(default=None),
    warehouse_id: int | None = Query(default=None),
):
    from datetime import date as _date, datetime, time, timedelta, timezone

    try:
        d_from = _date.fromisoformat(date_from)
        d_to = _date.fromisoformat(date_to)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Ngày không hợp lệ (YYYY-MM-DD).") from None
    if d_to < d_from:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="'Đến ngày' phải >= 'Từ ngày'.")

    # Biên ngày theo giờ VN (UTC+7) → quy về UTC để so với created_at (UTC).
    vn = timezone(timedelta(hours=7))
    dt_from = datetime.combine(d_from, time.min, tzinfo=vn).astimezone(timezone.utc)
    dt_to = datetime.combine(d_to, time.max, tzinfo=vn).astimezone(timezone.utc)

    rows = StockRepo(db).nxt_report(
        date_from=dt_from, date_to=dt_to, material_id=material_id, warehouse_id=warehouse_id
    )
    # Giá vốn chỉ hiện với người có quyền (DacTa 2.3): dùng action manage_price trên `kho`.
    if not authz.can(user, "kho", "manage_price"):
        for r in rows:
            r["opening_value"] = r["in_value"] = r["out_value"] = r["closing_value"] = 0
    return NxtReportOut(
        items=[NxtRow(**r) for r in rows], total=len(rows),
        date_from=date_from, date_to=date_to,
    )


# --- Thẻ kho / Sổ chi tiết vật tư -------------------------------------------
@router.get("/reports/ledger", response_model=LedgerOut)
def report_ledger(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(_read)],
    authz: Annotated[AuthorizationService, Depends(get_authorization_service)],
    material_id: int = Query(..., description="Vật tư cần xem thẻ kho"),
    warehouse_id: int | None = Query(default=None),
    lot_id: int | None = Query(default=None),
    date_from: str | None = Query(default=None, alias="from", description="YYYY-MM-DD (tùy chọn)"),
    date_to: str | None = Query(default=None, alias="to", description="YYYY-MM-DD (tùy chọn)"),
):
    from datetime import date as _date, datetime, time, timedelta, timezone

    vn = timezone(timedelta(hours=7))
    dt_from = dt_to = None
    try:
        if date_from:
            dt_from = datetime.combine(_date.fromisoformat(date_from), time.min, tzinfo=vn).astimezone(timezone.utc)
        if date_to:
            dt_to = datetime.combine(_date.fromisoformat(date_to), time.max, tzinfo=vn).astimezone(timezone.utc)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Ngày không hợp lệ (YYYY-MM-DD).") from None
    if dt_from and dt_to and dt_to < dt_from:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="'Đến ngày' phải >= 'Từ ngày'.")

    opening, opening_val, unit, moves = StockRepo(db).ledger(
        material_id=material_id, warehouse_id=warehouse_id, lot_id=lot_id, date_from=dt_from, date_to=dt_to
    )
    can_price = authz.can(user, "kho", "manage_price")

    bal, val, total_in, total_out = opening, opening_val, 0.0, 0.0
    items: list[LedgerRow] = []
    for m in moves:
        q = float(m.qty_delta)
        uc = float(m.unit_cost or 0)
        bal += q
        val += q * uc
        qin = q if q > 0 else 0.0
        qout = -q if q < 0 else 0.0
        total_in += qin
        total_out += qout
        items.append(LedgerRow(
            move_id=m.id, created_at=m.created_at, move_type=m.move_type,
            reason=m.reason, note=m.note, lot_id=m.lot_id, warehouse_id=m.warehouse_id,
            qty_in=qin, qty_out=qout, balance=bal,
            unit_cost=uc if can_price else 0, value=(q * uc) if can_price else 0,
        ))

    return LedgerOut(
        material_id=material_id, unit=unit, opening=opening, closing=bal,
        total_in=total_in, total_out=total_out,
        opening_value=opening_val if can_price else 0,
        closing_value=val if can_price else 0,
        items=items, total=len(items), date_from=date_from, date_to=date_to,
    )


# --- Tồn --------------------------------------------------------------------
@router.get("/stock", response_model=StockBalanceListOut)
def stock_balance(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(_read)],
    authz: Annotated[AuthorizationService, Depends(get_authorization_service)],
    material_id: int | None = Query(default=None),
    warehouse_id: int | None = Query(default=None),
):
    rows = StockRepo(db).balance(material_id=material_id, warehouse_id=warehouse_id)
    if not authz.can(user, "kho", "manage_price"):
        for r in rows:
            r["value"] = 0
    return StockBalanceListOut(items=[StockBalanceRow(**r) for r in rows], total=len(rows))


# --- Ngưỡng tồn tối thiểu ----------------------------------------------------
@router.get("/min-levels", response_model=MinLevelListOut)
def list_min_levels(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(_read)],
    warehouse_id: int | None = Query(default=None),
):
    rows = StockRepo(db).list_min_levels(warehouse_id=warehouse_id)
    return MinLevelListOut(items=[MinLevelRow.model_validate(r) for r in rows], total=len(rows))


@router.put("/min-levels", response_model=MinLevelRow)
def upsert_min_level(payload: MinLevelIn, db: Annotated[Session, Depends(get_db)], user: Annotated[User, Depends(_update)]):
    row = StockRepo(db).upsert_min_level(
        material_id=payload.material_id, warehouse_id=payload.warehouse_id,
        min_qty=payload.min_qty, near_min_qty=payload.near_min_qty, note=payload.note,
    )
    AuditLogRepository(db).create(
        actor_user_id=user.id, action="upsert_min_level",
        target=f"min_level:{row.id}", detail=f"mat={row.material_id} wh={row.warehouse_id} min={row.min_qty}",
    )
    return MinLevelRow.model_validate(row)


@router.delete("/min-levels/{level_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_min_level(level_id: int, db: Annotated[Session, Depends(get_db)], user: Annotated[User, Depends(_delete)]):
    from ..models.warehouse_stock import StockMinLevel

    row = db.get(StockMinLevel, level_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Không tìm thấy ngưỡng.")
    StockRepo(db).delete_min_level(row)
    AuditLogRepository(db).create(
        actor_user_id=user.id, action="delete_min_level", target=f"min_level:{level_id}", detail=""
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Cảnh báo tồn thấp -------------------------------------------------------
@router.get("/reports/low-stock", response_model=LowStockOut)
def report_low_stock(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(_read)],
    warehouse_id: int | None = Query(default=None),
    only_below: bool = Query(default=True, description="True = chỉ dòng dưới ngưỡng"),
):
    rows = StockRepo(db).low_stock(warehouse_id=warehouse_id, only_below=only_below)
    return LowStockOut(items=[LowStockRow(**r) for r in rows], total=len(rows))


# --- Cập nhật tức thời (SSE) -------------------------------------------------
@router.get("/events")
async def kho_events(
    token: str = Query(..., description="JWT — EventSource không gửi header được"),
    warehouse_id: int | None = Query(default=None),
):
    """Luồng SSE đẩy tín hiệu khi dữ liệu kho (đề nghị/phiếu) thay đổi → client tải lại ngay.
    Xác thực qua query token vì trình duyệt EventSource không đặt được header Authorization."""
    if decode_access_token(token) is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token không hợp lệ")
    return StreamingResponse(
        kho_event_stream(warehouse_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


# --- Tồn theo vị trí ---------------------------------------------------------
@router.get("/reports/by-location", response_model=LocationStockOut)
def report_by_location(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(_read)],
    warehouse_id: int | None = Query(default=None),
    material_id: int | None = Query(default=None),
):
    rows = StockRepo(db).stock_by_location(warehouse_id=warehouse_id, material_id=material_id)
    return LocationStockOut(items=[LocationStockRow(**r) for r in rows], total=len(rows))
