"""Materials router — spec-20.

Read-only surface: list / detail / cost history / toggle-active. Write/admin CRUD
(create/update/delete/add-price/convert/price-test/clone) đã gỡ — engine + Báo giá chỉ
cần đường đọc; ghi dữ liệu qua seed/service trực tiếp.
"""
from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..deps import get_material_service, require_permission
from ..models.user import User
from ..schemas.material import (
    MaterialCostOut,
    MaterialDetailOut,
    MaterialListOut,
    MaterialListStats,
    MaterialRow,
)
from ..services.material_service import (
    MaterialNotFound,
    MaterialService,
)

router = APIRouter(prefix="/api/materials", tags=["materials"])
MODULE = "dm_giay_vat_tu"

@router.get("", response_model=MaterialListOut)
def list_materials(
    svc: Annotated[MaterialService, Depends(get_material_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
    q: str | None = Query(default=None),
    material_type: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    sort: str = Query(default="code"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> MaterialListOut:
    rows, total = svc.list_materials(
        q=q, material_type=material_type, is_active=is_active, sort=sort, page=page, size=size
    )
    stats = svc.get_list_stats()
    return MaterialListOut(
        items=[MaterialRow.model_validate(r) for r in rows],
        total=total,
        page=page,
        size=size,
        stats=MaterialListStats(**stats),
    )

@router.get("/{material_id}", response_model=MaterialDetailOut)
def get_material(
    material_id: int,
    svc: Annotated[MaterialService, Depends(get_material_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> MaterialDetailOut:
    try:
        material = svc.get_material(material_id)
    except MaterialNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return MaterialDetailOut.model_validate(material)

@router.get("/{material_id}/costs/history", response_model=list[MaterialCostOut])
def cost_history(
    material_id: int,
    svc: Annotated[MaterialService, Depends(get_material_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> list[MaterialCostOut]:
    try:
        rows = svc.get_cost_history(material_id)
    except MaterialNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return [MaterialCostOut.model_validate(r) for r in rows]
