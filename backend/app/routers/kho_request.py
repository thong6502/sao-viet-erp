"""Router — phiếu ĐỀ NGHỊ nhập/xuất kho (bước trước phiếu kho, BRD sơ đồ luồng).

Phân quyền (tái dùng quyền `kho` hiện có, không thêm cột mới):
  - XEM đề nghị (list/chi tiết):   `kho:read`
  - Lập / sửa / gửi / hủy đề nghị: `kho:create` (siết: chỉ người được cấp quyền tạo mới đề xuất)
  - Duyệt / từ chối đề nghị:       `kho:approve`
  - Lập phiếu kho từ đề nghị:      `kho:create` (thủ kho / quản lý kho)
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_db, require_permission
from ..models.user import User
from ..models.warehouse import Warehouse
from ..models.warehouse_catalog import WhVoucherType
from ..models.warehouse_voucher import StockVoucher
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.stock_request_repo import StockRequestRepo
from ..repositories.warehouse_voucher_repo import VoucherRepo
from ..services.warehouse_voucher_service import VoucherError, VoucherService
from ..schemas.stock_request import (
    FulfillIn,
    RejectIn,
    RequestIn,
    RequestListOut,
    RequestRow,
)

router = APIRouter(prefix="/api/kho", tags=["kho-request"])

_kho_read = require_permission("kho", "read")
_kho_create = require_permission("kho", "create")
_kho_approve = require_permission("kho", "approve")

_VN_TZ = timezone(timedelta(hours=7))


def _name_map(db: Session, user_ids: set[int]) -> dict[int, str]:
    ids = {i for i in user_ids if i}
    if not ids:
        return {}
    rows = db.execute(select(User.id, User.name, User.username).where(User.id.in_(ids))).all()
    return {i: (name or username) for i, name, username in rows}


def _row(db: Session, r) -> RequestRow:
    row = RequestRow.model_validate(r)
    names = _name_map(db, {r.requested_by_user_id, r.approved_by_user_id})
    row.requested_by_name = names.get(r.requested_by_user_id)
    row.approved_by_name = names.get(r.approved_by_user_id)
    wh = db.get(Warehouse, r.warehouse_id)
    if wh is not None:
        row.warehouse_code = wh.code
        row.warehouse_name = wh.name
    if r.voucher_type_id:
        vt = db.get(WhVoucherType, r.voucher_type_id)
        row.voucher_type_name = vt.name if vt else None
    if r.voucher_id:
        v = db.get(StockVoucher, r.voucher_id)
        row.voucher_code = v.code if v else None
    return row


def _audit(db, user, action, r):
    AuditLogRepository(db).create(
        actor_user_id=user.id, action=action,
        target=f"stock_request:{r.id}", detail=f"{r.code} · {r.status}",
    )


@router.get("/requests", response_model=RequestListOut)
def list_requests(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(_kho_read)],
    request_type: str | None = Query(default=None),
    status_f: str | None = Query(default=None, alias="status"),
    warehouse_id: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
):
    rows, total = StockRequestRepo(db).list(
        request_type=request_type, status=status_f, warehouse_id=warehouse_id,
        page=page, size=size,
    )
    return RequestListOut(items=[_row(db, r) for r in rows], total=total, page=page, size=size)


@router.get("/requests/{request_id}", response_model=RequestRow)
def get_request(request_id: int, db: Annotated[Session, Depends(get_db)], _: Annotated[User, Depends(_kho_read)]):
    r = StockRequestRepo(db).get(request_id)
    if r is None:
        raise HTTPException(404, detail="Không tìm thấy đề nghị.")
    return _row(db, r)


@router.post("/requests", response_model=RequestRow, status_code=201)
def create_request(payload: RequestIn, db: Annotated[Session, Depends(get_db)], user: Annotated[User, Depends(_kho_create)]):
    if not payload.lines:
        raise HTTPException(422, detail="Đề nghị phải có ít nhất 1 dòng vật tư.")
    if db.get(Warehouse, payload.warehouse_id) is None:
        raise HTTPException(422, detail="Kho không tồn tại.")
    if payload.voucher_type_id is not None:
        vt = db.get(WhVoucherType, payload.voucher_type_id)
        if vt is None:
            raise HTTPException(422, detail="Loại phiếu không tồn tại.")
        if vt.voucher_group != payload.request_type:
            raise HTTPException(422, detail=f"Loại phiếu '{vt.name}' không khớp chiều {payload.request_type}.")
    repo = StockRequestRepo(db)
    header = payload.model_dump(exclude={"lines"})
    header["requested_by_user_id"] = user.id
    header["status"] = "draft"
    r = repo.create(
        code=repo.next_code(payload.request_type), header=header,
        lines=[ln.model_dump() for ln in payload.lines],
    )
    _audit(db, user, "create_stock_request", r)
    return _row(db, r)


@router.put("/requests/{request_id}", response_model=RequestRow)
def update_request(request_id: int, payload: RequestIn, db: Annotated[Session, Depends(get_db)], user: Annotated[User, Depends(_kho_create)]):
    repo = StockRequestRepo(db)
    r = repo.get(request_id)
    if r is None:
        raise HTTPException(404, detail="Không tìm thấy đề nghị.")
    if r.status != "draft":
        raise HTTPException(409, detail="Chỉ sửa được đề nghị ở trạng thái Nháp.")
    for k, val in payload.model_dump(exclude={"lines"}).items():
        setattr(r, k, val)
    repo.replace_lines(r, [ln.model_dump() for ln in payload.lines])
    _audit(db, user, "update_stock_request", repo.get(request_id))
    return _row(db, repo.get(request_id))


@router.delete("/requests/{request_id}", status_code=204, response_class=Response)
def delete_request(request_id: int, db: Annotated[Session, Depends(get_db)], user: Annotated[User, Depends(_kho_create)]):
    """Xóa hẳn đề nghị — CHỈ khi còn Nháp (chưa gửi duyệt). Đã gửi/duyệt/lập phiếu thì Hủy, không xóa."""
    repo = StockRequestRepo(db)
    r = repo.get(request_id)
    if r is None:
        raise HTTPException(404, detail="Không tìm thấy đề nghị.")
    if r.status != "draft":
        raise HTTPException(409, detail="Chỉ xóa được đề nghị ở trạng thái Nháp. Đề nghị đã gửi/duyệt hãy dùng Hủy.")
    _audit(db, user, "delete_stock_request", r)
    db.delete(r)
    db.commit()
    return Response(status_code=204)


@router.post("/requests/{request_id}/submit", response_model=RequestRow)
def submit_request(request_id: int, db: Annotated[Session, Depends(get_db)], user: Annotated[User, Depends(_kho_create)]):
    repo = StockRequestRepo(db)
    r = repo.get(request_id)
    if r is None:
        raise HTTPException(404, detail="Không tìm thấy đề nghị.")
    if r.status != "draft":
        raise HTTPException(409, detail="Đề nghị không ở trạng thái Nháp.")
    r.status = "pending"
    repo.save(r)
    _audit(db, user, "submit_stock_request", r)
    return _row(db, repo.get(request_id))


@router.post("/requests/{request_id}/approve", response_model=RequestRow)
def approve_request(request_id: int, db: Annotated[Session, Depends(get_db)], user: Annotated[User, Depends(_kho_approve)]):
    repo = StockRequestRepo(db)
    r = repo.get(request_id)
    if r is None:
        raise HTTPException(404, detail="Không tìm thấy đề nghị.")
    if r.status != "pending":
        raise HTTPException(409, detail="Chỉ duyệt được đề nghị đang Chờ duyệt.")
    r.status = "approved"
    r.approved_by_user_id = user.id
    r.approved_at = datetime.now(_VN_TZ)
    r.rejected_reason = None
    repo.save(r)
    _audit(db, user, "approve_stock_request", r)
    return _row(db, repo.get(request_id))


@router.post("/requests/{request_id}/reject", response_model=RequestRow)
def reject_request(request_id: int, payload: RejectIn, db: Annotated[Session, Depends(get_db)], user: Annotated[User, Depends(_kho_approve)]):
    repo = StockRequestRepo(db)
    r = repo.get(request_id)
    if r is None:
        raise HTTPException(404, detail="Không tìm thấy đề nghị.")
    if r.status != "pending":
        raise HTTPException(409, detail="Chỉ từ chối được đề nghị đang Chờ duyệt.")
    r.status = "rejected"
    r.approved_by_user_id = user.id
    r.approved_at = datetime.now(_VN_TZ)
    r.rejected_reason = payload.reason.strip() or None
    repo.save(r)
    _audit(db, user, "reject_stock_request", r)
    return _row(db, repo.get(request_id))


@router.post("/requests/{request_id}/cancel", response_model=RequestRow)
def cancel_request(request_id: int, db: Annotated[Session, Depends(get_db)], user: Annotated[User, Depends(_kho_create)]):
    repo = StockRequestRepo(db)
    r = repo.get(request_id)
    if r is None:
        raise HTTPException(404, detail="Không tìm thấy đề nghị.")
    if r.status in ("fulfilled", "cancelled"):
        raise HTTPException(409, detail="Đề nghị đã lập phiếu hoặc đã hủy.")
    r.status = "cancelled"
    repo.save(r)
    _audit(db, user, "cancel_stock_request", r)
    return _row(db, repo.get(request_id))


@router.post("/requests/{request_id}/create-voucher", response_model=RequestRow)
def create_voucher_from_request(
    request_id: int, payload: FulfillIn,
    db: Annotated[Session, Depends(get_db)], user: Annotated[User, Depends(_kho_create)],
):
    """Lập phiếu kho từ đề nghị ĐÃ DUYỆT — copy dòng hàng, gắn ref 2 chiều, rồi GHI SỔ LUÔN.
    Đề nghị đã qua duyệt nên phiếu không cần nộp + duyệt lại (bỏ 1 vòng phê duyệt)."""
    repo = StockRequestRepo(db)
    r = repo.get(request_id)
    if r is None:
        raise HTTPException(404, detail="Không tìm thấy đề nghị.")
    if r.status != "approved":
        raise HTTPException(409, detail="Chỉ lập phiếu từ đề nghị đã DUYỆT.")
    if r.voucher_id:
        raise HTTPException(409, detail="Đề nghị này đã lập phiếu.")
    type_id = payload.voucher_type_id or r.voucher_type_id
    if type_id is None:
        raise HTTPException(422, detail="Chưa chọn loại phiếu để lập.")
    vt = db.get(WhVoucherType, type_id)
    if vt is None:
        raise HTTPException(422, detail="Loại phiếu không tồn tại.")
    # Loại phiếu phải khớp chiều đề nghị (nhập ↔ voucher_group nhap, xuất ↔ xuat).
    if vt.voucher_group != r.request_type:
        raise HTTPException(422, detail=f"Loại phiếu '{vt.name}' không khớp đề nghị {r.request_type}.")

    vrepo = VoucherRepo(db)
    header = {
        "voucher_type_id": vt.id,
        "doc_date": date.today(),
        "partner_ref": r.partner_ref,
        "reason": r.reason,
        "note": None,
        "ref_type": "stock_request",
        "ref_id": r.id,
        "status": "draft",
        "created_by_user_id": user.id,
    }
    if r.request_type == "nhap":
        header["dst_warehouse_id"] = r.warehouse_id
    else:
        header["src_warehouse_id"] = r.warehouse_id
    lines = [
        {"material_id": ln.material_id, "quantity": ln.quantity, "uom": ln.uom, "note": ln.note}
        for ln in r.lines
    ]
    v = vrepo.create(code=vrepo.next_code(vt.code), header=header, lines=lines)

    # Đề nghị đã DUYỆT → ghi sổ phiếu ngay (bỏ bước nộp + duyệt phiếu).
    try:
        VoucherService(db).post(v, user)
    except VoucherError as e:
        db.rollback()
        raise HTTPException(422, detail=str(e)) from None

    r.voucher_id = v.id
    r.status = "fulfilled"
    repo.save(r)
    AuditLogRepository(db).create(
        actor_user_id=user.id, action="fulfill_stock_request",
        target=f"stock_request:{r.id}", detail=f"{r.code} → {v.code} (ghi sổ)",
    )
    return _row(db, repo.get(request_id))
