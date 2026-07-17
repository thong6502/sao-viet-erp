"""Router — cỗ máy chứng từ kho: loại phiếu + trạng thái hàng (catalog) + phiếu (spec-13).

Catalog gate `dm_kho`; phiếu gate `kho`; duyệt gate `kho:approve`.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..deps import get_db, require_any_permission, require_permission
from ..models.user import User
from ..models.warehouse_catalog import WhItemStatus, WhVoucherType
from ..models.warehouse_voucher import StockVoucher, StockVoucherAttachment
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.warehouse_voucher_repo import VoucherRepo
from ..schemas.warehouse_voucher import (
    ItemStatusIn,
    ItemStatusListOut,
    ItemStatusRow,
    VoucherAttachmentListOut,
    VoucherAttachmentRow,
    VoucherCancelIn,
    VoucherIn,
    VoucherListOut,
    VoucherRow,
    VoucherTypeIn,
    VoucherTypeListOut,
    VoucherTypeRow,
)

# File đính kèm phiếu → <backend>/static/kho/<voucher_id>/, phục vụ read-only ở /static.
_STATIC_DIR = Path(__file__).resolve().parents[2] / "static"
from ..services.warehouse_voucher_service import VoucherError, VoucherService

router = APIRouter(prefix="/api/kho", tags=["kho-voucher"])

_dm_read = require_permission("dm_kho", "read")
# ĐỌC danh mục (loại phiếu, trạng thái hàng) để VẬN HÀNH: người có kho:read cũng cần.
_dm_or_kho_read = require_any_permission(("dm_kho", "read"), ("kho", "read"))
_dm_create = require_permission("dm_kho", "create")
_dm_update = require_permission("dm_kho", "update")
_dm_delete = require_permission("dm_kho", "delete")
_kho_read = require_permission("kho", "read")
_kho_create = require_permission("kho", "create")
_kho_approve = require_permission("kho", "approve")


# ============ Danh mục Trạng thái hàng (DacTa 3.15) ============
@router.get("/item-statuses", response_model=ItemStatusListOut)
def list_statuses(db: Annotated[Session, Depends(get_db)], _: Annotated[User, Depends(_dm_or_kho_read)]):
    rows = db.execute(select(WhItemStatus).order_by(WhItemStatus.display_order, WhItemStatus.id)).scalars().all()
    return ItemStatusListOut(items=[ItemStatusRow.model_validate(r) for r in rows], total=len(rows))


@router.post("/item-statuses", response_model=ItemStatusRow, status_code=201)
def create_status(payload: ItemStatusIn, db: Annotated[Session, Depends(get_db)], user: Annotated[User, Depends(_dm_create)]):
    if db.execute(select(WhItemStatus).where(WhItemStatus.code == payload.code)).scalars().first():
        raise HTTPException(409, detail=f"Mã '{payload.code}' đã tồn tại.")
    obj = WhItemStatus(**payload.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    AuditLogRepository(db).create(actor_user_id=user.id, action="create_item_status", target=f"wh_item_status:{obj.id}", detail=obj.code)
    return ItemStatusRow.model_validate(obj)


@router.put("/item-statuses/{obj_id}", response_model=ItemStatusRow)
def update_status(obj_id: int, payload: ItemStatusIn, db: Annotated[Session, Depends(get_db)], user: Annotated[User, Depends(_dm_update)]):
    obj = db.get(WhItemStatus, obj_id)
    if obj is None:
        raise HTTPException(404, detail="Không tìm thấy trạng thái.")
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    db.commit(); db.refresh(obj)
    return ItemStatusRow.model_validate(obj)


@router.delete("/item-statuses/{obj_id}", status_code=204, response_class=Response)
def delete_status(obj_id: int, db: Annotated[Session, Depends(get_db)], _: Annotated[User, Depends(_dm_delete)]):
    obj = db.get(WhItemStatus, obj_id)
    if obj is None:
        raise HTTPException(404, detail="Không tìm thấy trạng thái.")
    if obj.is_system:
        raise HTTPException(409, detail="Trạng thái hệ thống chỉ được Ngừng dùng, không xóa.")
    db.delete(obj); db.commit()
    return Response(status_code=204)


# ============ Danh mục Loại phiếu (DacTa 3.16) ============
@router.get("/voucher-types", response_model=VoucherTypeListOut)
def list_vtypes(db: Annotated[Session, Depends(get_db)], _: Annotated[User, Depends(_dm_or_kho_read)]):
    rows = db.execute(select(WhVoucherType).order_by(WhVoucherType.code)).scalars().all()
    return VoucherTypeListOut(items=[VoucherTypeRow.model_validate(r) for r in rows], total=len(rows))


@router.post("/voucher-types", response_model=VoucherTypeRow, status_code=201)
def create_vtype(payload: VoucherTypeIn, db: Annotated[Session, Depends(get_db)], user: Annotated[User, Depends(_dm_create)]):
    if db.execute(select(WhVoucherType).where(WhVoucherType.code == payload.code)).scalars().first():
        raise HTTPException(409, detail=f"Mã '{payload.code}' đã tồn tại.")
    obj = WhVoucherType(**payload.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    AuditLogRepository(db).create(actor_user_id=user.id, action="create_voucher_type", target=f"wh_voucher_type:{obj.id}", detail=obj.code)
    return VoucherTypeRow.model_validate(obj)


@router.put("/voucher-types/{obj_id}", response_model=VoucherTypeRow)
def update_vtype(obj_id: int, payload: VoucherTypeIn, db: Annotated[Session, Depends(get_db)], user: Annotated[User, Depends(_dm_update)]):
    obj = db.get(WhVoucherType, obj_id)
    if obj is None:
        raise HTTPException(404, detail="Không tìm thấy loại phiếu.")
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    db.commit(); db.refresh(obj)
    return VoucherTypeRow.model_validate(obj)


@router.delete("/voucher-types/{obj_id}", status_code=204, response_class=Response)
def delete_vtype(obj_id: int, db: Annotated[Session, Depends(get_db)], _: Annotated[User, Depends(_dm_delete)]):
    obj = db.get(WhVoucherType, obj_id)
    if obj is None:
        raise HTTPException(404, detail="Không tìm thấy loại phiếu.")
    used = db.execute(select(StockVoucher.id).where(StockVoucher.voucher_type_id == obj_id).limit(1)).first()
    if used:
        raise HTTPException(409, detail="Loại phiếu đã phát sinh phiếu, không xóa được.")
    db.delete(obj); db.commit()
    return Response(status_code=204)


# ============ Phiếu (cỗ máy chứng từ) ============
def _audit(db, user, action, v):
    AuditLogRepository(db).create(actor_user_id=user.id, action=action, target=f"stock_voucher:{v.id}", detail=f"{v.code} · {v.status}")


def _name_map(db: Session, user_ids: set[int]) -> dict[int, str]:
    """id người dùng → tên hiển thị (name, fallback username)."""
    ids = {i for i in user_ids if i}
    if not ids:
        return {}
    rows = db.execute(select(User.id, User.name, User.username).where(User.id.in_(ids))).all()
    return {i: (name or username) for i, name, username in rows}


def _vrow(db: Session, v) -> VoucherRow:
    row = VoucherRow.model_validate(v)
    names = _name_map(db, {v.created_by_user_id, v.handover_by_user_id})
    row.created_by_name = names.get(v.created_by_user_id)
    row.handover_by_name = names.get(v.handover_by_user_id)
    return row


@router.get("/vouchers", response_model=VoucherListOut)
def list_vouchers(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(_kho_read)],
    voucher_type_id: int | None = Query(default=None),
    status_f: str | None = Query(default=None, alias="status"),
    warehouse_id: int | None = Query(default=None),
    partner_ref: str | None = Query(default=None, description="Lọc theo NCC/đối tượng (chứa)"),
    created_by_user_id: int | None = Query(default=None, description="Lọc theo người nhập"),
    ref_type: str | None = Query(default=None, description="Lọc theo chứng từ gốc, VD 'lsx'"),
    ref_id: int | None = Query(default=None, description="ID chứng từ gốc (VD id LSX)"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
):
    rows, total = VoucherRepo(db).list(
        voucher_type_id=voucher_type_id, status=status_f, warehouse_id=warehouse_id,
        partner_ref=partner_ref, created_by_user_id=created_by_user_id,
        ref_type=ref_type, ref_id=ref_id, page=page, size=size,
    )
    names = _name_map(db, {r.created_by_user_id for r in rows})
    out = []
    for r in rows:
        row = VoucherRow.model_validate(r)
        row.created_by_name = names.get(r.created_by_user_id)
        out.append(row)
    return VoucherListOut(items=out, total=total, page=page, size=size)


@router.get("/vouchers/{voucher_id}", response_model=VoucherRow)
def get_voucher(voucher_id: int, db: Annotated[Session, Depends(get_db)], _: Annotated[User, Depends(_kho_read)]):
    v = VoucherRepo(db).get(voucher_id)
    if v is None:
        raise HTTPException(404, detail="Không tìm thấy phiếu.")
    return _vrow(db, v)


@router.post("/vouchers", response_model=VoucherRow, status_code=201)
def create_voucher(payload: VoucherIn, db: Annotated[Session, Depends(get_db)], user: Annotated[User, Depends(_kho_create)]):
    vt = db.get(WhVoucherType, payload.voucher_type_id)
    if vt is None:
        raise HTTPException(422, detail="Loại phiếu không tồn tại.")
    # BRD §2.5 — phiếu kho gắn LSX chỉ lập được khi LSX đã DUYỆT.
    if payload.ref_type == "lsx" and payload.ref_id:
        from ..models.production import ProductionOrder
        lsx = db.get(ProductionOrder, payload.ref_id)
        if lsx is None:
            raise HTTPException(422, detail="Lệnh sản xuất tham chiếu không tồn tại.")
        if lsx.approved_at is None:
            raise HTTPException(409, detail=f"Lệnh sản xuất {lsx.code} chưa được duyệt — cần duyệt lệnh trước khi lập phiếu kho.")
    repo = VoucherRepo(db)
    header = payload.model_dump(exclude={"lines"})
    header["created_by_user_id"] = user.id
    header["status"] = "draft"
    v = repo.create(code=repo.next_code(vt.code), header=header, lines=[ln.model_dump() for ln in payload.lines])
    _audit(db, user, "create_stock_voucher", v)
    return _vrow(db, v)


@router.put("/vouchers/{voucher_id}", response_model=VoucherRow)
def update_voucher(voucher_id: int, payload: VoucherIn, db: Annotated[Session, Depends(get_db)], user: Annotated[User, Depends(_kho_create)]):
    repo = VoucherRepo(db)
    v = repo.get(voucher_id)
    if v is None:
        raise HTTPException(404, detail="Không tìm thấy phiếu.")
    if v.status != "draft":
        raise HTTPException(409, detail="Chỉ sửa được phiếu ở trạng thái Nháp.")
    for k, val in payload.model_dump(exclude={"lines"}).items():
        setattr(v, k, val)
    repo.replace_lines(v, [ln.model_dump() for ln in payload.lines])
    _audit(db, user, "update_stock_voucher", repo.get(voucher_id))
    return _vrow(db, repo.get(voucher_id))


@router.post("/vouchers/{voucher_id}/submit", response_model=VoucherRow)
def submit_voucher(voucher_id: int, db: Annotated[Session, Depends(get_db)], user: Annotated[User, Depends(_kho_create)]):
    repo = VoucherRepo(db)
    v = repo.get(voucher_id)
    if v is None:
        raise HTTPException(404, detail="Không tìm thấy phiếu.")
    if v.status != "draft":
        raise HTTPException(409, detail="Phiếu không ở trạng thái Nháp.")
    vt = db.get(WhVoucherType, v.voucher_type_id)
    if vt is not None and vt.require_approval:
        v.status = "pending"
        repo.save(v)
        _audit(db, user, "submit_stock_voucher", v)
    else:
        try:
            VoucherService(db).post(v, user)
        except VoucherError as e:
            db.rollback()
            raise HTTPException(422, detail=str(e)) from None
        _audit(db, user, "post_stock_voucher", v)
    return _vrow(db, repo.get(voucher_id))


@router.post("/vouchers/{voucher_id}/approve", response_model=VoucherRow)
def approve_voucher(voucher_id: int, db: Annotated[Session, Depends(get_db)], user: Annotated[User, Depends(_kho_approve)]):
    repo = VoucherRepo(db)
    v = repo.get(voucher_id)
    if v is None:
        raise HTTPException(404, detail="Không tìm thấy phiếu.")
    if v.status != "pending":
        raise HTTPException(409, detail="Chỉ duyệt được phiếu đang Chờ duyệt.")
    try:
        VoucherService(db).post(v, user)
    except VoucherError as e:
        db.rollback()
        raise HTTPException(422, detail=str(e)) from None
    _audit(db, user, "approve_stock_voucher", v)
    return _vrow(db, repo.get(voucher_id))


def _release_request(db: Session, v) -> None:
    """Phiếu sinh từ đề nghị bị hủy/xóa → trả đề nghị về 'Đã duyệt' để có thể lập phiếu lại."""
    if v.ref_type != "stock_request" or not v.ref_id:
        return
    from ..models.stock_request import StockRequest
    req = db.get(StockRequest, v.ref_id)
    if req is not None and req.voucher_id == v.id:
        req.voucher_id = None
        req.status = "approved"


@router.post("/vouchers/{voucher_id}/cancel", response_model=VoucherRow)
def cancel_voucher(
    voucher_id: int, db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(_kho_create)], payload: VoucherCancelIn | None = None,
):
    repo = VoucherRepo(db)
    v = repo.get(voucher_id)
    if v is None:
        raise HTTPException(404, detail="Không tìm thấy phiếu.")
    if v.status == "posted":
        raise HTTPException(409, detail="Phiếu đã ghi sổ — không hủy; hãy lập phiếu điều chỉnh.")
    if v.status == "cancelled":
        raise HTTPException(409, detail="Phiếu đã hủy.")
    reason = (payload.reason or "").strip() if payload else ""
    if reason:
        v.note = f"{v.note} | Hủy: {reason}" if v.note else f"Hủy: {reason}"
    v.status = "cancelled"
    _release_request(db, v)
    repo.save(v)
    _audit(db, user, "cancel_stock_voucher", v)
    return _vrow(db, repo.get(voucher_id))


@router.delete("/vouchers/{voucher_id}", status_code=204, response_class=Response)
def delete_voucher(voucher_id: int, db: Annotated[Session, Depends(get_db)], user: Annotated[User, Depends(_kho_create)]):
    """Xóa hẳn phiếu — CHỈ khi còn Nháp. Phiếu đã nộp/ghi sổ/hủy không xóa được."""
    repo = VoucherRepo(db)
    v = repo.get(voucher_id)
    if v is None:
        raise HTTPException(404, detail="Không tìm thấy phiếu.")
    if v.status != "draft":
        raise HTTPException(409, detail="Chỉ xóa được phiếu ở trạng thái Nháp. Phiếu đã nộp/ghi sổ hãy dùng Hủy.")
    _release_request(db, v)
    _audit(db, user, "delete_stock_voucher", v)
    db.delete(v)
    db.commit()
    return Response(status_code=204)


@router.post("/vouchers/{voucher_id}/confirm-receipt", response_model=VoucherRow)
def confirm_receipt(
    voucher_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_any_permission(("kho", "manage_status"), ("kho", "create")))],
):
    """Xác nhận đã bàn giao/nhận vật tư (BRD §2.5 bước 10) — chỉ phiếu xuất theo LSX, đã ghi sổ.
    Quyền: `kho:manage_status` (cờ 'Xác nhận nhận vật tư') hoặc `kho:create` (người lập phiếu)."""
    repo = VoucherRepo(db)
    v = repo.get(voucher_id)
    if v is None:
        raise HTTPException(404, detail="Không tìm thấy phiếu.")
    if v.ref_type != "lsx":
        raise HTTPException(409, detail="Chỉ xác nhận nhận vật tư cho phiếu xuất theo lệnh sản xuất.")
    if v.status != "posted":
        raise HTTPException(409, detail="Phiếu chưa ghi sổ — chưa thể xác nhận bàn giao.")
    if v.handover_at is not None:
        raise HTTPException(409, detail="Phiếu đã được xác nhận bàn giao.")
    v.handover_at = datetime.now(timezone(timedelta(hours=7)))
    v.handover_by_user_id = user.id
    repo.save(v)
    AuditLogRepository(db).create(
        actor_user_id=user.id, action="confirm_voucher_receipt",
        target=f"stock_voucher:{v.id}", detail=f"{v.code} · handover",
    )
    return _vrow(db, repo.get(voucher_id))


# ============ File đính kèm phiếu (chứng từ) ============
@router.get("/vouchers/{voucher_id}/attachments", response_model=VoucherAttachmentListOut)
def list_attachments(
    voucher_id: int, db: Annotated[Session, Depends(get_db)], _: Annotated[User, Depends(_kho_read)]
):
    if db.get(StockVoucher, voucher_id) is None:
        raise HTTPException(404, detail="Không tìm thấy phiếu.")
    rows = db.execute(
        select(StockVoucherAttachment)
        .where(StockVoucherAttachment.voucher_id == voucher_id)
        .order_by(StockVoucherAttachment.uploaded_at)
    ).scalars().all()
    return VoucherAttachmentListOut(items=[VoucherAttachmentRow.model_validate(a) for a in rows])


@router.post("/vouchers/{voucher_id}/attachments", response_model=VoucherAttachmentRow, status_code=201)
def upload_attachment(
    voucher_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(_kho_create)],
    file: UploadFile = File(...),
):
    v = db.get(StockVoucher, voucher_id)
    if v is None:
        raise HTTPException(404, detail="Không tìm thấy phiếu.")
    if v.status in ("posted", "cancelled"):
        raise HTTPException(409, detail="Phiếu đã ghi sổ/đã hủy — không đính kèm thêm.")

    safe_name = Path(file.filename or "file").name
    token = secrets.token_hex(4)
    dest_dir = _STATIC_DIR / "kho" / str(voucher_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{token}_{safe_name}"
    with dest.open("wb") as f:
        f.write(file.file.read())

    att = StockVoucherAttachment(
        voucher_id=voucher_id, file_name=safe_name,
        file_url=f"/static/kho/{voucher_id}/{token}_{safe_name}",
        file_type=file.content_type, uploaded_by=user.id,
    )
    db.add(att)
    db.commit()
    db.refresh(att)
    _audit(db, user, "upload_voucher_attachment", v)
    return VoucherAttachmentRow.model_validate(att)


@router.delete("/vouchers/{voucher_id}/attachments/{attachment_id}", status_code=204, response_class=Response)
def delete_attachment(
    voucher_id: int,
    attachment_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(_kho_create)],
):
    att = db.get(StockVoucherAttachment, attachment_id)
    if att is None or att.voucher_id != voucher_id:
        raise HTTPException(404, detail="Không tìm thấy file đính kèm.")
    # Xóa file trên đĩa (best-effort) rồi xóa bản ghi.
    try:
        rel = att.file_url.lstrip("/")
        (_STATIC_DIR.parent / rel).unlink(missing_ok=True)
    except OSError:
        pass
    db.delete(att)
    db.commit()
    v = db.get(StockVoucher, voucher_id)
    if v is not None:
        _audit(db, user, "delete_voucher_attachment", v)
    return Response(status_code=204)
