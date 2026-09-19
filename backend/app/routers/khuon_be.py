"""Khuôn router — CRUD danh mục KHAI BÁO nơi lưu trữ khuôn (bế · ép kim · khung lụa).

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
    # Chip lọc của màn Khuôn theo LOẠI (Khuôn bế · Khuôn ép kim · Khung lụa) từ 18/09/2026 —
    # trước đó chip theo tình trạng. Tình trạng + khách + số kệ nằm ở bảng "Lọc nâng cao"
    # (`loc_them`), ghép VÀ với chip và ô tìm. Mọi việc lọc đều ở máy chủ: bảng chỉ cầm 20 dòng.
    loc="loai",
    loc_them={"tinh_trang": str, "khach_hang_id": int, "so_ke": str},
    facets=lambda svc, kw: svc.dem_theo_loai(**kw),
    ma_goi_y=True,      # repo khai `ma_prefix = "KB-"`
)
