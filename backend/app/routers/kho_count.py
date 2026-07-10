"""Router — Đợt kiểm kê & điều chỉnh tồn (spec-13 C). Gate `kho`; duyệt gate `kho:approve`."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from sqlalchemy import select

from ..deps import get_db, require_permission
from ..models.user import User
from ..models.warehouse_count import StockCount
from ..repositories.audit_repo import AuditLogRepository
from ..schemas.warehouse_count import (
    CountCreateIn,
    CountLineRow,
    CountListOut,
    CountRow,
    CountSetIn,
)
from ..services.warehouse_count_service import CountError, CountService

router = APIRouter(prefix="/api/kho", tags=["kho-count"])

_read = require_permission("kho", "read")
_create = require_permission("kho", "create")
_approve = require_permission("kho", "approve")


def _row(db: Session, count: StockCount) -> CountRow:
    row = CountRow.model_validate(count)
    for lr, ln in zip(row.lines, count.lines):
        lr.diff = (float(ln.counted_qty) - float(ln.system_qty)) if ln.counted_qty is not None else None
    ids = {i for i in (count.created_by_user_id, count.posted_by_user_id) if i}
    if ids:
        names = {i: (n or u) for i, n, u in db.execute(
            select(User.id, User.name, User.username).where(User.id.in_(ids))
        ).all()}
        row.created_by_name = names.get(count.created_by_user_id)
        row.posted_by_name = names.get(count.posted_by_user_id)
    return row


def _audit(db, user, action, c):
    AuditLogRepository(db).create(actor_user_id=user.id, action=action, target=f"stock_count:{c.id}", detail=f"{c.code} · {c.status}")


@router.get("/counts", response_model=CountListOut)
def list_counts(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(_read)],
    status_f: str | None = Query(default=None, alias="status"),
    warehouse_id: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
):
    rows, total = CountService(db).list(status=status_f, warehouse_id=warehouse_id, page=page, size=size)
    return CountListOut(items=[_row(db, c) for c in rows], total=total, page=page, size=size)


@router.get("/counts/{count_id}", response_model=CountRow)
def get_count(count_id: int, db: Annotated[Session, Depends(get_db)], _: Annotated[User, Depends(_read)]):
    c = CountService(db).get(count_id)
    if c is None:
        raise HTTPException(404, detail="Không tìm thấy đợt kiểm kê.")
    return _row(db, c)


@router.post("/counts", response_model=CountRow, status_code=201)
def create_count(payload: CountCreateIn, db: Annotated[Session, Depends(get_db)], user: Annotated[User, Depends(_create)]):
    svc = CountService(db)
    c = svc.create(
        warehouse_id=payload.warehouse_id, note=payload.note, actor=user,
        participants=payload.participants, material_group=payload.material_group,
    )
    _audit(db, user, "create_stock_count", c)
    return _row(db, c)


@router.put("/counts/{count_id}/lines", response_model=CountRow)
def set_counts(count_id: int, payload: CountSetIn, db: Annotated[Session, Depends(get_db)], user: Annotated[User, Depends(_create)]):
    svc = CountService(db)
    c = svc.get(count_id)
    if c is None:
        raise HTTPException(404, detail="Không tìm thấy đợt kiểm kê.")
    try:
        svc.set_counts(c, [ln.model_dump() for ln in payload.lines])
    except CountError as e:
        raise HTTPException(409, detail=str(e)) from None
    _audit(db, user, "count_lines", c)
    return _row(db, svc.get(count_id))


@router.post("/counts/{count_id}/post", response_model=CountRow)
def post_count(count_id: int, db: Annotated[Session, Depends(get_db)], user: Annotated[User, Depends(_approve)]):
    svc = CountService(db)
    c = svc.get(count_id)
    if c is None:
        raise HTTPException(404, detail="Không tìm thấy đợt kiểm kê.")
    try:
        svc.post(c, user)
    except CountError as e:
        db.rollback()
        raise HTTPException(409, detail=str(e)) from None
    _audit(db, user, "post_stock_count", c)
    return _row(db, svc.get(count_id))


@router.post("/counts/{count_id}/cancel", response_model=CountRow)
def cancel_count(count_id: int, db: Annotated[Session, Depends(get_db)], user: Annotated[User, Depends(_create)]):
    svc = CountService(db)
    c = svc.get(count_id)
    if c is None:
        raise HTTPException(404, detail="Không tìm thấy đợt kiểm kê.")
    try:
        svc.cancel(c)
    except CountError as e:
        raise HTTPException(409, detail=str(e)) from None
    _audit(db, user, "cancel_stock_count", c)
    return _row(db, svc.get(count_id))
