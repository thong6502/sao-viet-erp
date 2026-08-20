"""Lý do & lỗi SX router — CRUD danh mục lý do/lỗi sản xuất (§15).

Thân CRUD sinh từ `routers/catalog_base.make_catalog_router`. Dependency INLINE (không đụng
deps.py). MODULE quyền = "dm_ly_do_san_xuat" (mg `0221` chép quyền từ `san_xuat`).

Danh mục THAM CHIẾU: ngoài người khai chính nó, module Thực hiện sản xuất ĐỌC được (ô chọn nhóm
lỗi khi ghi hỏng batch, lý do tạm dừng/điều chỉnh bàn giao). GHI vẫn đòi đúng `dm_ly_do_san_xuat`.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_any_permission
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.san_xuat_ly_do_repo import SanXuatLyDoRepository
from ..schemas.san_xuat_ly_do import (
    SanXuatLyDoIn, SanXuatLyDoListOut, SanXuatLyDoRow,
)
from ..services.san_xuat_ly_do_service import SanXuatLyDoService
from .catalog_base import make_catalog_router

router = APIRouter(prefix="/api/san-xuat-ly-do", tags=["san-xuat-ly-do"])
MODULE = "dm_ly_do_san_xuat"

# ĐỌC: người khai danh mục HOẶC người thực hiện sản xuất (chọn nhóm lỗi/lý do khi ghi sản lượng,
# tạm dừng, điều chỉnh bàn giao). Một dependency cho CẢ list LẪN detail — mở list rộng mà khoá
# detail chặt thì liệt kê được nhưng bấm vào một dòng lại 403 giữa luồng (lỗi câm).
_DOC = require_any_permission((MODULE, "read"), ("san_xuat", "read"))


def get_service(db: Annotated[Session, Depends(get_db)]) -> SanXuatLyDoService:
    return SanXuatLyDoService(SanXuatLyDoRepository(db), AuditLogRepository(db))


Service = Annotated[SanXuatLyDoService, Depends(get_service)]


make_catalog_router(
    router, ten="san_xuat_ly_do", ServiceDep=Service, module=MODULE, doc=_DOC,
    InModel=SanXuatLyDoIn, RowModel=SanXuatLyDoRow, ListModel=SanXuatLyDoListOut,
    # Tab lọc = NHÓM. Giá trị là khoá `nhom` (`loi`, `tam_dung`…).
    loc="nhom",
    facets=lambda svc, kw: svc.repo.dem_theo_nhom(**kw),
    ma_goi_y=True,      # repo khai `ma_prefix = "LD-"`
)
