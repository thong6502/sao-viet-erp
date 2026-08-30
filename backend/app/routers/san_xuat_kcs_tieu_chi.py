"""Tiêu chí KCS router — CRUD danh mục checklist kiểm tra chất lượng (module KCS kiêm nhiệm).

Thân CRUD sinh từ `routers/catalog_base.make_catalog_router`. Dependency INLINE.

MODULE quyền = "dm_kcs_tieu_chi".
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_any_permission
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.san_xuat_kcs_tieu_chi_repo import SanXuatKcsTieuChiRepository
from ..schemas.san_xuat_kcs_tieu_chi import (
    SanXuatKcsTieuChiIn, SanXuatKcsTieuChiListOut, SanXuatKcsTieuChiRow,
)
from ..services.san_xuat_kcs_tieu_chi_service import SanXuatKcsTieuChiService
from .catalog_base import make_catalog_router

router = APIRouter(prefix="/api/san-xuat-kcs-tieu-chi", tags=["san-xuat-kcs-tieu-chi"])
MODULE = "dm_kcs_tieu_chi"

# Ai ĐỌC được danh mục này: người khai tiêu chí + Sản xuất (board KCS Task 4/5 cần hiển thị
# checklist) — cùng lý do `bu_hao.py:35-37` mở đọc cho Tính giá/Sản xuất.
_DOC = require_any_permission((MODULE, "read"), ("san_xuat", "read"))


def get_service(db: Annotated[Session, Depends(get_db)]) -> SanXuatKcsTieuChiService:
    return SanXuatKcsTieuChiService(SanXuatKcsTieuChiRepository(db), AuditLogRepository(db))


Service = Annotated[SanXuatKcsTieuChiService, Depends(get_service)]

make_catalog_router(
    router, ten="san_xuat_kcs_tieu_chi", ServiceDep=Service, module=MODULE, doc=_DOC,
    InModel=SanXuatKcsTieuChiIn, RowModel=SanXuatKcsTieuChiRow, ListModel=SanXuatKcsTieuChiListOut,
    # KHÔNG truyền excel_spec= — v1 không mở import/export cho danh mục này (cấu hình con
    # nhiều-nhiều qua ref-multi không có cột phẳng để map vào một dòng Excel).
)
