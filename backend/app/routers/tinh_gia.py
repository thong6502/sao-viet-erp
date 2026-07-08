"""Tính giá router (module MỚI) — preview giá từ danh mục rebuild + costing_engine.

Chưa nối Báo giá (chỉ tính + trả breakdown). MODULE quyền = "tinh_gia_thanh".
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_permission
from ..models.user import User
from ..schemas.tinh_gia import TinhGiaPreviewIn, TinhGiaPreviewOut
from ..services.tinh_gia_service import TinhGiaError, TinhGiaService

router = APIRouter(prefix="/api/tinh-gia", tags=["tinh-gia"])
MODULE = "tinh_gia_thanh"


def get_service(db: Annotated[Session, Depends(get_db)]) -> TinhGiaService:
    return TinhGiaService(db)


@router.post("/preview", response_model=TinhGiaPreviewOut)
def preview(
    payload: TinhGiaPreviewIn,
    svc: Annotated[TinhGiaService, Depends(get_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> TinhGiaPreviewOut:
    try:
        data = payload.model_dump()
        if data.get("quote") is None:
            data["quote"] = {}
        out = svc.preview(data)
    except TinhGiaError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from None
    return TinhGiaPreviewOut(**out)
