"""Đơn vị & quy đổi router — CRUD đơn vị + CRUD cặp quy đổi + thử một phép đổi.

Dependency INLINE (bám `routers/bu_hao.py`). MODULE quyền = "dm_don_vi" — quyền RIÊNG. Trước đây
đi ké `dm_cong_doan`, nghĩa là muốn cho kế toán khai "1 thùng = 24 hộp" thì phải mở luôn cho họ
danh mục công đoạn. Đơn vị dùng chung cho kho · mua hàng · khoán lương, không thuộc riêng ai.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_any_permission, require_permission
from ..models.user import User
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.don_vi_do_repo import DonViDoRepository
from ..schemas.don_vi_do import (
    BienListOut, CapIn, CapListOut, CapRowOut, DonViDoIn, DonViDoListOut, DonViDoRow, HoListOut,
    QuyDoiIn, QuyDoiOut,
)
from ..services.don_vi_do_service import (
    DonViDoDuplicate, DonViDoNotFound, DonViDoService, DonViDoValidationError, cong_thuc_chu,
)
from ..services.quy_doi_service import BIEN, _so, don_vi_map, doi_theo_quy_cach

router = APIRouter(prefix="/api/don-vi", tags=["don-vi"])
MODULE = "dm_don_vi"


def get_service(db: Annotated[Session, Depends(get_db)]) -> DonViDoService:
    return DonViDoService(DonViDoRepository(db), AuditLogRepository(db))


Service = Annotated[DonViDoService, Depends(get_service)]


def _err(e: Exception):
    if isinstance(e, DonViDoNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    if isinstance(e, DonViDoDuplicate):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


def _row(svc: DonViDoService, obj) -> DonViDoRow:
    row = DonViDoRow.model_validate(obj)
    row.canh_bao = svc.canh_bao(obj)
    # Dựng MỘT lần rồi rút chuỗi phẳng ra từ đó — gọi cả `quy_doi_text` lẫn `quy_doi_chips` là quét
    # bảng cặp hai lượt cho mỗi dòng (20 đơn vị → 40 lượt) mà ra đúng cùng một thứ.
    row.quy_doi_chips = svc.quy_doi_chips(obj)
    row.quy_doi_text = (" · ".join(c["text"] for c in row.quy_doi_chips)
                        if row.quy_doi_chips else "Chưa khai quy đổi")
    if (hl := svc.cong_thuc_hieu_luc(obj)):
        row.cong_thuc_hieu_luc, row.cong_thuc_chu_ma, row.cong_thuc_chu_ten = hl
    # Cách đo dịch sang chữ để màn danh sách khỏi nhúng bảng nhãn biến thứ hai.
    row.cong_thuc_text = cong_thuc_chu(obj.cong_thuc) if obj.cong_thuc else None
    return row


def _cap_row(c) -> CapRowOut:
    row = CapRowOut.model_validate(c)
    row.cau = f"1 {c.tu_ten} = {_so(float(c.he_so))} {c.den_ten}"
    row.ma = f"{c.tu_ma} → {c.den_ma}"
    row.ten = row.cau
    return row


# ĐỌC danh sách đơn vị: quyền RỘNG hơn phần khai (`MODULE`). Từ 2026-08-08 ô ĐVT của Giấy · Vật tư
# khác · Kho · NCC đều chọn từ danh mục này, mà mấy màn đó gác bằng module KHÁC — để nguyên
# `dm_cong_doan` thì người dùng kho mở drawer sẽ ăn 403, và `RebuildCatalogPage` NUỐT lỗi thành
# danh sách rỗng (`.catch(() => [])`) nên họ chỉ thấy ô tìm không ra gì, không thấy báo lỗi nào.
_doc_don_vi = require_any_permission(
    (MODULE, "read"), ("kho", "read"), ("thu_mua", "read"),
    ("tinh_gia_thanh", "read"), ("san_xuat", "read"),
    # Các màn danh mục có ô ĐVT trong form: Giấy · Vật tư khác · Công đoạn (đơn vị năng suất) ·
    # Máy (ô "Đơn vị tốc độ" nay đọc động từ danh mục này thay danh sách viết cứng).
    ("dm_giay", "read"), ("dm_vat_tu", "read"), ("dm_cong_doan", "read"), ("dm_thiet_bi", "read"))


@router.get("", response_model=DonViDoListOut)
def list_items(
    svc: Service,
    _: Annotated[User, Depends(_doc_don_vi)],
    q: str | None = Query(default=None),
    ho: str | None = Query(default=None),
    active: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
) -> DonViDoListOut:
    rows, total = svc.list(q=q, ho=ho, active=active, page=page, size=size)
    return DonViDoListOut(
        items=[_row(svc, r) for r in rows], total=total, page=page, size=size,
    )


@router.get("/ho", response_model=HoListOut)
def list_ho(svc: Service, _: Annotated[User, Depends(require_permission(MODULE, "read"))]) -> HoListOut:
    return HoListOut(items=svc.ho_goi_y())


@router.get("/bien", response_model=BienListOut)
def list_bien(_: Annotated[User, Depends(require_permission(MODULE, "read"))]) -> BienListOut:
    """Biến dùng được trong công thức quy đổi — màn khai phải LIỆT KÊ, không bắt người ta đoán tên."""
    return BienListOut(items=[{"ma": k, "nhan": v} for k, v in BIEN.items()])


@router.get("/quy-doi", response_model=CapListOut)
def list_cap(
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
) -> CapListOut:
    rows, total = svc.list_cap(q=q, page=page, size=size)
    return CapListOut(items=[_cap_row(r) for r in rows], total=total, page=page, size=size)


@router.post("/quy-doi", response_model=CapRowOut, status_code=status.HTTP_201_CREATED)
def create_cap(payload: CapIn, svc: Service,
               current_user: Annotated[User, Depends(require_permission(MODULE, "create"))]) -> CapRowOut:
    try:
        obj = svc.create_cap(payload.model_dump(exclude_unset=True), actor_id=current_user.id)
    except (DonViDoDuplicate, DonViDoValidationError, DonViDoNotFound) as e:
        raise _err(e) from None
    row = next((c for c in svc.repo.cap_rows() if c.id == obj.id), None)
    return _cap_row(row)


@router.put("/quy-doi/{cap_id}", response_model=CapRowOut)
def update_cap(cap_id: int, payload: CapIn, svc: Service,
               current_user: Annotated[User, Depends(require_permission(MODULE, "update"))]) -> CapRowOut:
    try:
        obj = svc.update_cap(cap_id, payload.model_dump(exclude_unset=True), actor_id=current_user.id)
    except (DonViDoNotFound, DonViDoDuplicate, DonViDoValidationError) as e:
        raise _err(e) from None
    row = next((c for c in svc.repo.cap_rows() if c.id == obj.id), None)
    return _cap_row(row)


@router.delete("/quy-doi/{cap_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_cap(cap_id: int, svc: Service,
               current_user: Annotated[User, Depends(require_permission(MODULE, "delete"))]):
    try:
        svc.delete_cap(cap_id, actor_id=current_user.id)
    except DonViDoNotFound as e:
        raise _err(e) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/thu", response_model=QuyDoiOut)
def thu_quy_doi(
    payload: QuyDoiIn,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> QuyDoiOut:
    """Thử một phép đổi — trả kèm DIỄN GIẢI cách tính, hoặc nói rõ thiếu gì (không đoán)."""
    dvs = don_vi_map(svc.repo.all_active())
    kq = doi_theo_quy_cach(payload.gia_tri, payload.tu, payload.den, payload.quy_cach, dvs,
                           svc.repo.cap_rows())
    return QuyDoiOut(**kq)


@router.get("/{dv_id}", response_model=DonViDoRow)
def get_item(dv_id: int, svc: Service,
             _: Annotated[User, Depends(require_permission(MODULE, "read"))]) -> DonViDoRow:
    try:
        return _row(svc, svc.get(dv_id))
    except DonViDoNotFound as e:
        raise _err(e) from None


@router.post("", response_model=DonViDoRow, status_code=status.HTTP_201_CREATED)
def create_item(payload: DonViDoIn, svc: Service,
                current_user: Annotated[User, Depends(require_permission(MODULE, "create"))]) -> DonViDoRow:
    try:
        obj = svc.create(payload.model_dump(exclude_unset=True), actor_id=current_user.id)
        return _row(svc, obj)
    except (DonViDoDuplicate, DonViDoValidationError, DonViDoNotFound) as e:
        raise _err(e) from None


@router.put("/{dv_id}", response_model=DonViDoRow)
def update_item(dv_id: int, payload: DonViDoIn, svc: Service,
                current_user: Annotated[User, Depends(require_permission(MODULE, "update"))]) -> DonViDoRow:
    try:
        obj = svc.update(dv_id, payload.model_dump(exclude_unset=True), actor_id=current_user.id)
        return _row(svc, obj)
    except (DonViDoNotFound, DonViDoDuplicate, DonViDoValidationError) as e:
        raise _err(e) from None


@router.delete("/{dv_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_item(dv_id: int, svc: Service,
                current_user: Annotated[User, Depends(require_permission(MODULE, "delete"))]):
    try:
        svc.delete(dv_id, actor_id=current_user.id)
    except DonViDoNotFound as e:
        raise _err(e) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
