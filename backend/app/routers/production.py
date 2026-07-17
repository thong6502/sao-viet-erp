"""Router — Sản xuất: Lệnh sản xuất (LSX) P1/MVP. Gate module `san_xuat`.

LSX là thực thể độc lập; kho tham chiếu qua ref_type='lsx' + ref_id. Ở đây chỉ CRUD tối thiểu
(list / options / create / đóng-hủy). Định mức/công đoạn/tiến độ là P2.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..deps import get_db, require_permission
from ..models.customer import Customer
from ..models.product import Product
from ..models.production import ProductionOrder, ProductionOrderAttachment
from ..models.user import User
from ..repositories.audit_repo import AuditLogRepository
from ..schemas.production import (
    ProductionAttachmentListOut,
    ProductionAttachmentRow,
    ProductionOrderIn,
    ProductionOrderListOut,
    ProductionOrderOption,
    ProductionOrderRow,
)

router = APIRouter(prefix="/api/san-xuat", tags=["san-xuat"])

MODULE = "san_xuat"
_read = require_permission(MODULE, "read")
_create = require_permission(MODULE, "create")
_approve = require_permission(MODULE, "approve")

_VN_TZ = timezone(timedelta(hours=7))
# Tập tin đính kèm LSX → <backend>/static/san-xuat/<id>/.
_STATIC_DIR = Path(__file__).resolve().parents[2] / "static"


def _next_code(db: Session) -> str:
    """Mã LSX theo năm: LSX-{YY}-{NNNN}."""
    yy = datetime.now(_VN_TZ).strftime("%y")
    prefix = f"LSX-{yy}-"
    max_n = 0
    for code in db.execute(
        select(ProductionOrder.code).where(ProductionOrder.code.like(f"{prefix}%"))
    ).scalars():
        try:
            max_n = max(max_n, int(code[len(prefix):]))
        except ValueError:
            continue
    return f"{prefix}{max_n + 1:04d}"


def _name_map(db: Session, user_ids: set[int]) -> dict[int, str]:
    ids = {i for i in user_ids if i}
    if not ids:
        return {}
    rows = db.execute(select(User.id, User.name, User.username).where(User.id.in_(ids))).all()
    return {i: (name or username) for i, name, username in rows}


def _row(db: Session, o: ProductionOrder) -> ProductionOrderRow:
    row = ProductionOrderRow.model_validate(o)
    names = _name_map(db, {o.created_by_user_id, o.updated_by_user_id, o.approved_by_user_id})
    row.created_by_name = names.get(o.created_by_user_id)
    row.updated_by_name = names.get(o.updated_by_user_id)
    row.approved_by_name = names.get(o.approved_by_user_id)
    # Nếu có customer_id → hiển thị tên khách thật (không đè customer_name text nếu đã có).
    if o.customer_id and not o.customer_name:
        cust = db.get(Customer, o.customer_id)
        if cust is not None:
            row.customer_name = cust.name
    # Mã LSX gốc (lệnh bù).
    if o.parent_order_id:
        parent = db.get(ProductionOrder, o.parent_order_id)
        if parent is not None:
            row.parent_code = parent.code
    return row


def _label(o: ProductionOrder, product_name: str | None) -> str:
    name = product_name or o.product_name
    return f"{o.code} · {name}" if name else o.code


@router.get("/orders", response_model=ProductionOrderListOut)
def list_orders(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(_read)],
    q: str | None = Query(default=None, description="Tìm theo mã LSX / tên sản phẩm"),
    status_f: str | None = Query(default=None, alias="status"),
    order_kind: str | None = Query(default=None, description="thuong / bu"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
):
    stmt = select(ProductionOrder)
    if q:
        like = f"%{q.strip().lower()}%"
        from sqlalchemy import func
        stmt = stmt.where(or_(
            func.lower(ProductionOrder.code).like(like),
            func.lower(ProductionOrder.product_name).like(like),
        ))
    if status_f:
        stmt = stmt.where(ProductionOrder.status == status_f)
    if order_kind:
        stmt = stmt.where(ProductionOrder.order_kind == order_kind)
    total = len(db.execute(stmt).scalars().all())
    rows = db.execute(
        stmt.order_by(ProductionOrder.created_at.desc()).offset((page - 1) * size).limit(size)
    ).scalars().all()
    return ProductionOrderListOut(items=[_row(db, o) for o in rows], total=total, page=page, size=size)


@router.get("/orders/options", response_model=list[ProductionOrderOption])
def order_options(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(_read)],
    q: str | None = Query(default=None),
    include_all: bool = Query(default=False, description="True = gồm cả LSX đã đóng (chọn LSX gốc cho lệnh bù)"),
):
    """LSX cho dropdown. Mặc định chỉ LSX đang mở (xuất/nhập theo LSX); include_all=True gồm mọi LSX."""
    stmt = select(ProductionOrder)
    if not include_all:
        stmt = stmt.where(ProductionOrder.status == "open")
    if q:
        like = f"%{q.strip().lower()}%"
        from sqlalchemy import func
        stmt = stmt.where(or_(
            func.lower(ProductionOrder.code).like(like),
            func.lower(ProductionOrder.product_name).like(like),
        ))
    orders = db.execute(stmt.order_by(ProductionOrder.created_at.desc()).limit(500)).scalars().all()
    # Tên sản phẩm từ product_id nếu có.
    pids = {o.product_id for o in orders if o.product_id}
    pmap = {}
    if pids:
        pmap = {p.id: p.name for p in db.execute(select(Product).where(Product.id.in_(pids))).scalars()}
    return [
        ProductionOrderOption(id=o.id, code=o.code, label=_label(o, pmap.get(o.product_id)))
        for o in orders
    ]


@router.get("/orders/{order_id}", response_model=ProductionOrderRow)
def get_order(
    order_id: int, db: Annotated[Session, Depends(get_db)], _: Annotated[User, Depends(_read)]
):
    o = db.get(ProductionOrder, order_id)
    if o is None:
        raise HTTPException(404, detail="Không tìm thấy lệnh sản xuất.")
    return _row(db, o)


@router.post("/orders", response_model=ProductionOrderRow, status_code=201)
def create_order(
    payload: ProductionOrderIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(_create)],
):
    if payload.product_id is None and not (payload.product_name and payload.product_name.strip()):
        raise HTTPException(422, detail="Cần chọn sản phẩm hoặc nhập tên sản phẩm.")
    o = ProductionOrder(
        code=_next_code(db),
        order_id=payload.order_id,
        contract_no=payload.contract_no,
        customer_id=payload.customer_id,
        customer_name=(payload.customer_name or None),
        product_id=payload.product_id,
        product_name=(payload.product_name or None),
        quantity=payload.quantity,
        order_date=payload.order_date,
        delivery_request_date=payload.delivery_request_date,
        doc_date=payload.doc_date,
        due_date=payload.due_date,
        order_kind="bu" if payload.order_kind == "bu" else "thuong",
        parent_order_id=payload.parent_order_id,
        bu_reason=payload.bu_reason,
        tech_note_print=payload.tech_note_print,
        tech_note_finishing=payload.tech_note_finishing,
        note=payload.note,
        status="open",
        created_by_user_id=user.id,
        updated_by_user_id=user.id,
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    AuditLogRepository(db).create(
        actor_user_id=user.id, action="create_production_order",
        target=f"production_order:{o.id}", detail=o.code,
    )
    return _row(db, o)


@router.put("/orders/{order_id}", response_model=ProductionOrderRow)
def update_order(
    order_id: int,
    payload: ProductionOrderIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(_create)],
):
    o = db.get(ProductionOrder, order_id)
    if o is None:
        raise HTTPException(404, detail="Không tìm thấy lệnh sản xuất.")
    if payload.product_id is None and not (payload.product_name and payload.product_name.strip()):
        raise HTTPException(422, detail="Cần chọn sản phẩm hoặc nhập tên sản phẩm.")
    for field, val in payload.model_dump().items():
        setattr(o, field, val)
    o.updated_by_user_id = user.id
    db.commit()
    db.refresh(o)
    AuditLogRepository(db).create(
        actor_user_id=user.id, action="update_production_order",
        target=f"production_order:{o.id}", detail=o.code,
    )
    return _row(db, o)


# --- Tập tin đính kèm LSX ---------------------------------------------------
@router.get("/orders/{order_id}/attachments", response_model=ProductionAttachmentListOut)
def list_attachments(
    order_id: int, db: Annotated[Session, Depends(get_db)], _: Annotated[User, Depends(_read)]
):
    if db.get(ProductionOrder, order_id) is None:
        raise HTTPException(404, detail="Không tìm thấy lệnh sản xuất.")
    rows = db.execute(
        select(ProductionOrderAttachment)
        .where(ProductionOrderAttachment.order_id == order_id)
        .order_by(ProductionOrderAttachment.uploaded_at)
    ).scalars().all()
    return ProductionAttachmentListOut(items=[ProductionAttachmentRow.model_validate(a) for a in rows])


@router.post("/orders/{order_id}/attachments", response_model=ProductionAttachmentRow, status_code=201)
def upload_attachment(
    order_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(_create)],
    file: UploadFile = File(...),
):
    if db.get(ProductionOrder, order_id) is None:
        raise HTTPException(404, detail="Không tìm thấy lệnh sản xuất.")
    safe_name = Path(file.filename or "file").name
    token = secrets.token_hex(4)
    dest_dir = _STATIC_DIR / "san-xuat" / str(order_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{token}_{safe_name}"
    with dest.open("wb") as f:
        f.write(file.file.read())
    att = ProductionOrderAttachment(
        order_id=order_id, file_name=safe_name,
        file_url=f"/static/san-xuat/{order_id}/{token}_{safe_name}",
        file_type=file.content_type, uploaded_by=user.id,
    )
    db.add(att)
    db.commit()
    db.refresh(att)
    return ProductionAttachmentRow.model_validate(att)


@router.delete("/orders/{order_id}/attachments/{attachment_id}", status_code=204, response_class=Response)
def delete_attachment(
    order_id: int,
    attachment_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(_create)],
):
    att = db.get(ProductionOrderAttachment, attachment_id)
    if att is None or att.order_id != order_id:
        raise HTTPException(404, detail="Không tìm thấy tập tin.")
    try:
        (_STATIC_DIR.parent / att.file_url.lstrip("/")).unlink(missing_ok=True)
    except OSError:
        pass
    db.delete(att)
    db.commit()
    return Response(status_code=204)


@router.post("/orders/{order_id}/close", response_model=ProductionOrderRow)
def close_order(
    order_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(_create)],
    to_status: str = Query(default="done", pattern="^(done|cancelled|open)$"),
):
    o = db.get(ProductionOrder, order_id)
    if o is None:
        raise HTTPException(404, detail="Không tìm thấy lệnh sản xuất.")
    o.status = to_status
    db.commit()
    db.refresh(o)
    AuditLogRepository(db).create(
        actor_user_id=user.id, action="update_production_order_status",
        target=f"production_order:{o.id}", detail=f"{o.code} · {to_status}",
    )
    return _row(db, o)


@router.post("/orders/{order_id}/approve", response_model=ProductionOrderRow)
def approve_order(
    order_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(_approve)],
    approve: bool = Query(default=True, description="True=duyệt, False=bỏ duyệt"),
):
    """Duyệt / bỏ duyệt LSX (BRD §2.5). Chỉ LSX đã duyệt mới sinh được phiếu kho."""
    o = db.get(ProductionOrder, order_id)
    if o is None:
        raise HTTPException(404, detail="Không tìm thấy lệnh sản xuất.")
    if approve:
        o.approved_at = datetime.now(_VN_TZ)
        o.approved_by_user_id = user.id
    else:
        o.approved_at = None
        o.approved_by_user_id = None
    db.commit()
    db.refresh(o)
    AuditLogRepository(db).create(
        actor_user_id=user.id, action="approve_production_order" if approve else "unapprove_production_order",
        target=f"production_order:{o.id}", detail=o.code,
    )
    return _row(db, o)
