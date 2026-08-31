"""Kho hàng router — CRUD danh mục KHAI BÁO kho.

Thân CRUD sinh từ `routers/catalog_base.make_catalog_router`. Dependency INLINE.

MODULE quyền = "dm_kho_hang" — quyền RIÊNG, tách khỏi `kho`: dựng danh sách kho là việc cấu hình,
chạy nhập/xuất hàng ngày là việc khác. ĐỌC thì vẫn mở cho `kho` (mọi màn nghiệp vụ đều phải chọn
kho trong dropdown).
Chỉ khai báo kho (mã / tên / vị trí / ghi chú); vận hành nhập/xuất/tồn ở router khác.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from fastapi import HTTPException

from ..db import get_db
from ..deps import require_any_permission, require_permission
from ..models.user import User
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.kho_hang_repo import KhoHangRepository
from ..repositories.kho_vi_tri_repo import KhoViTriRepository
from ..schemas.kho_hang import (
    KhoHangIn, KhoHangListOut, KhoHangRow, KhoViTriIn, KhoViTriListOut, KhoViTriRow,
)
from ..services.kho_hang_service import KhoHangNotFound, KhoHangService
from ..services.kho_vi_tri_service import (
    KhoViTriDuplicate, KhoViTriKhoNotFound, KhoViTriNotFound, KhoViTriService,
    KhoViTriValidationError,
)
from ..services.catalog_excel_specs import KHO_HANG
from .catalog_base import loi_http, make_catalog_router

router = APIRouter(prefix="/api/kho", tags=["kho"])
MODULE = "dm_kho_hang"
# Đọc danh sách kho: người khai (module này) + mọi vai làm nghiệp vụ kho / mua hàng / sản xuất —
# họ phải chọn kho ở phiếu, không thì dropdown rỗng mà không hiểu vì sao.
_doc_kho = require_any_permission(
    (MODULE, "read"), ("kho", "read"), ("thu_mua", "read"), ("san_xuat", "read"))


def get_service(db: Annotated[Session, Depends(get_db)]) -> KhoHangService:
    return KhoHangService(KhoHangRepository(db), AuditLogRepository(db))


Service = Annotated[KhoHangService, Depends(get_service)]


@router.get("/{kho_id}/delete-check")
def delete_check(kho_id: int, svc: Service,
                 _: Annotated[User, Depends(require_permission(MODULE, "delete"))]):
    """Soi kho trước khi xóa: liệt kê lý do chặn (còn tồn / phiếu chờ ghi sổ / đề nghị dở).

    Giữ THỦ CÔNG, KHÔNG nhét vào factory: chỉ màn Kho có hộp thoại này, mà cửa "kiểm trước khi
    xoá" dùng chung cho mọi danh mục đang được dựng riêng ở `routers/danh_muc_xoa.py`.
    """
    try:
        blockers = svc.delete_blockers(kho_id)
    except KhoHangNotFound as e:
        raise loi_http(e) from None
    return {"can_delete": not blockers, "blockers": blockers}


# ── Vị trí cất trong kho (`kho_vi_tri`) ─────────────────────────────────────────────────────
# Danh sách vị trí (kệ/ô) khai cho TỪNG kho → để khai lô chọn dropdown thay vì gõ tay. ĐỌC mở cho
# mọi vai chọn kho (`_doc_kho`); THÊM/XÓA là việc khai báo nên gác `dm_kho_hang`.
def get_vi_tri_service(db: Annotated[Session, Depends(get_db)]) -> KhoViTriService:
    return KhoViTriService(
        KhoViTriRepository(db), KhoHangRepository(db), AuditLogRepository(db))


ViTriService = Annotated[KhoViTriService, Depends(get_vi_tri_service)]


@router.get("/{kho_id}/vi-tri", response_model=KhoViTriListOut)
def list_vi_tri(kho_id: int, svc: ViTriService, _: Annotated[User, Depends(_doc_kho)]):
    try:
        items = svc.list(kho_id)
    except KhoViTriKhoNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    return {"items": [KhoViTriRow.model_validate(v) for v in items]}


@router.post("/{kho_id}/vi-tri", response_model=KhoViTriRow, status_code=201)
def create_vi_tri(kho_id: int, body: KhoViTriIn, svc: ViTriService,
                  user: Annotated[User, Depends(require_permission(MODULE, "create"))]):
    try:
        obj = svc.create(kho_id, body.ma, body.ghi_chu, actor_id=user.id)
    except KhoViTriKhoNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except KhoViTriValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    except KhoViTriDuplicate as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    return KhoViTriRow.model_validate(obj)


@router.delete("/vi-tri/{vi_tri_id}", status_code=204)
def delete_vi_tri(vi_tri_id: int, svc: ViTriService,
                  user: Annotated[User, Depends(require_permission(MODULE, "delete"))]):
    try:
        svc.delete(vi_tri_id, actor_id=user.id)
    except KhoViTriNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


make_catalog_router(
    router, ten="kho_hang", ServiceDep=Service, module=MODULE, doc=_doc_kho,
    InModel=KhoHangIn, RowModel=KhoHangRow, ListModel=KhoHangListOut,
    excel_spec=KHO_HANG,
    ma_goi_y=True,      # repo khai `ma_prefix = "KHO-"`
)
