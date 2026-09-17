"""Xe giao hàng router — CRUD danh mục xe (biển số · tải trọng · mức khoán km · còn dùng).

Thân CRUD sinh từ `routers/catalog_base.make_catalog_router`. Dependency INLINE.

MODULE quyền = "dm_xe" — chỉ DANH TÍNH xe. Bảng bậc đơn giá không ở đây: nó thuộc về MỨC khoán km,
khai ở màn Cấu hình lương (`/api/giao-hang/muc-khoan-km`), vì sửa giá là việc kế toán chứ không
phải việc của người khai biển số.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_any_permission
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.xe_repo import MucKhoanKmRepository, XeRepository
from ..schemas.xe import XeIn, XeListOut, XeRow
from ..services.catalog_excel_specs import XE
from ..services.xe_service import XeService
from .catalog_base import make_catalog_router

router = APIRouter(prefix="/api/xe", tags=["xe"])
MODULE = "dm_xe"

# Ai ĐỌC được danh sách xe: người khai xe + người phân chuyến (`giao_hang`) + Cấu hình lương (màn
# khai mức có đếm số xe theo mức). GHI thì vẫn đòi đúng `dm_xe`.
#
# Vì sao phải mở: thiếu quyền đọc là ô "Xe" ở màn phân công chuyến ăn 403, mà frontend nuốt lỗi
# thành danh sách rỗng — người phân chuyến thấy ô trống và không hiểu vì sao (đúng bài học của ô
# Bù hao ở màn Công đoạn và ô Sale phụ trách ở màn Khách hàng).
_DOC = require_any_permission(
    (MODULE, "read"), ("giao_hang", "read"), ("luong", "read"),
)


def get_service(db: Annotated[Session, Depends(get_db)]) -> XeService:
    return XeService(XeRepository(db), AuditLogRepository(db), muc=MucKhoanKmRepository(db))


Service = Annotated[XeService, Depends(get_service)]

make_catalog_router(
    router, ten="xe", ServiceDep=Service, module=MODULE, doc=_DOC,
    InModel=XeIn, RowModel=XeRow, ListModel=XeListOut,
    excel_spec=XE,
    # Không mở `/ma-goi-y`: mã xe LÀ BIỂN SỐ, không có mã kế tiếp nào để gợi ý.
)
