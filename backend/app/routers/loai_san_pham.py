"""Loại sản phẩm router — CRUD template.

Thân CRUD sinh từ `routers/catalog_base.make_catalog_router`. Dependency INLINE (không đụng
deps.py). MODULE quyền = "dm_loai_san_pham".
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_any_permission
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.loai_san_pham_repo import LoaiSanPhamRepository
from ..schemas.loai_san_pham import LoaiSanPhamIn, LoaiSanPhamListOut, LoaiSanPhamRow
from ..services.loai_san_pham_service import LoaiSanPhamService
from ..services.catalog_excel_specs import LOAI_SAN_PHAM
from .catalog_base import make_catalog_router

router = APIRouter(prefix="/api/loai-san-pham", tags=["loai-san-pham"])
MODULE = "dm_loai_san_pham"

# Danh mục THAM CHIẾU: đọc được nếu có quyền cấu hình danh mục HOẶC quyền Tính giá (màn Tính giá
# cần đổ dropdown Loại SP mà không phải mở màn cấu hình).
#
# MỘT dependency đọc dùng cho CẢ list LẪN detail. Trước 15/08/2026 list mở bằng OR-gate còn detail
# khoá bằng quyền chặt, nên người Tính giá liệt kê được nhưng bấm vào một dòng thì ăn 403 giữa
# luồng — lỗi câm, không ai đoán ra thiếu quyền gì.
_DOC = require_any_permission((MODULE, "read"), ("tinh_gia_thanh", "read"))


def get_service(db: Annotated[Session, Depends(get_db)]) -> LoaiSanPhamService:
    return LoaiSanPhamService(LoaiSanPhamRepository(db), AuditLogRepository(db))


Service = Annotated[LoaiSanPhamService, Depends(get_service)]

make_catalog_router(
    router, ten="loai_san_pham", ServiceDep=Service, module=MODULE, doc=_DOC,
    InModel=LoaiSanPhamIn, RowModel=LoaiSanPhamRow, ListModel=LoaiSanPhamListOut,
    excel_spec=LOAI_SAN_PHAM,
    loc="structural_type",
    ma_goi_y=True,      # repo khai `ma_prefix = "LSP-"`
)
