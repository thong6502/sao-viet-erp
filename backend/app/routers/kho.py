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

from ..db import get_db
from ..deps import require_any_permission, require_permission
from ..models.user import User
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.kho_hang_repo import KhoHangRepository
from ..schemas.kho_hang import KhoHangIn, KhoHangListOut, KhoHangRow
from ..services.kho_hang_service import KhoHangNotFound, KhoHangService
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


make_catalog_router(
    router, ten="kho_hang", ServiceDep=Service, module=MODULE, doc=_doc_kho,
    InModel=KhoHangIn, RowModel=KhoHangRow, ListModel=KhoHangListOut,
    ma_goi_y=True,      # repo khai `ma_prefix = "KHO-"`
)
