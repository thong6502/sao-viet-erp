"""Bù hao router — CRUD danh mục bù hao (bảng tra số tờ theo bài in × bậc SL).

Thân CRUD sinh từ `routers/catalog_base.make_catalog_router`. Dependency INLINE.

MODULE quyền = "dm_bu_hao" — quyền RIÊNG, không đi ké `dm_cong_doan` nữa: bù hao là % hao giấy,
đổi một con số là giá thành đổi theo, nên phải cấp được tách khỏi việc thêm/sửa bước công đoạn.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_any_permission
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.bu_hao_repo import BuHaoRepository
from ..schemas.bu_hao import BuHaoIn, BuHaoListOut, BuHaoRow
from ..services.bu_hao_service import BuHaoService
from .catalog_base import make_catalog_router

router = APIRouter(prefix="/api/bu-hao", tags=["bu-hao"])
MODULE = "dm_bu_hao"

# Ai ĐỌC được bảng bù hao: người khai bù hao + người khai Công đoạn (ô "Bù hao" của bước trỏ thẳng
# sang đây) + Tính giá và Sản xuất (bù hao vào thẳng số tờ chạy). GHI thì vẫn đòi đúng `dm_bu_hao`.
#
# Vì sao phải mở: thiếu quyền đọc là ô chọn bù hao ở màn Công đoạn ăn 403, mà frontend nuốt lỗi
# thành danh sách rỗng (`.catch(() => [])`) — người khai thấy dropdown trống và không hiểu vì sao.
#
# MỘT dependency dùng cho CẢ list LẪN detail: trước 15/08/2026 nhiều router mở list bằng OR-gate
# nhưng khoá detail bằng quyền chặt, nên người ta liệt kê được mà bấm vào thì 403.
_DOC = require_any_permission(
    (MODULE, "read"), ("dm_cong_doan", "read"), ("tinh_gia_thanh", "read"), ("san_xuat", "read"),
)


def get_service(db: Annotated[Session, Depends(get_db)]) -> BuHaoService:
    return BuHaoService(BuHaoRepository(db), AuditLogRepository(db))


Service = Annotated[BuHaoService, Depends(get_service)]

make_catalog_router(
    router, ten="bu_hao", ServiceDep=Service, module=MODULE, doc=_DOC,
    InModel=BuHaoIn, RowModel=BuHaoRow, ListModel=BuHaoListOut,
    # Không mở `/ma-goi-y`: mã bù hao do người khai tự đặt (BH-GIAY, BH-MANG…), repo không khai
    # `ma_prefix` nên chẳng có mã kế tiếp nào để gợi ý.
)
