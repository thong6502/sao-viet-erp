"""Khuôn bế router — CRUD danh mục KHAI BÁO nơi lưu trữ khuôn bế.

Thân CRUD sinh từ `routers/catalog_base.make_catalog_router`. Dependency INLINE.
MODULE quyền RIÊNG = "khuon_be" (tích quyền độc lập trong ma trận).
Chỉ khai báo (mã / tên / khách / số kệ / ngày làm / tình trạng / ghi chú).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.khuon_be_repo import KhuonBeRepository
from ..schemas.khuon_be import KhuonBeIn, KhuonBeListOut, KhuonBeRow
from ..services.khuon_be_service import KhuonBeService
from ..services.catalog_excel_specs import KHUON_BE
from .catalog_base import make_catalog_router

router = APIRouter(prefix="/api/khuon-be", tags=["khuon-be"])
MODULE = "khuon_be"


def get_service(db: Annotated[Session, Depends(get_db)]) -> KhuonBeService:
    return KhuonBeService(KhuonBeRepository(db), AuditLogRepository(db))


Service = Annotated[KhuonBeService, Depends(get_service)]

make_catalog_router(
    router, ten="khuon_be", ServiceDep=Service, module=MODULE,
    InModel=KhuonBeIn, RowModel=KhuonBeRow, ListModel=KhuonBeListOut,
    excel_spec=KHUON_BE,
    # Tab lọc của màn Khuôn bế (Còn dùng · Hỏng · Trả khách…). Trước 14/08/2026 màn tự lọc trong
    # JS trên toàn bộ danh mục đã tải về; nay bảng chỉ cầm 20 dòng nên việc lọc phải về máy chủ.
    loc="tinh_trang",
    facets=lambda svc, kw: svc.dem_theo_tinh_trang(**kw),
    ma_goi_y=True,      # repo khai `ma_prefix = "KB-"`
)
