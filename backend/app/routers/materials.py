"""Materials router — spec-20.
"""
from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from ..deps import get_material_service, require_permission
from ..models.user import User
from ..schemas.material import (
    MaterialCostCreate,
    MaterialCostOut,
    MaterialCreate,
    MaterialDetailOut,
    MaterialListOut,
    MaterialListStats,
    MaterialRow,
    MaterialUpdate,
)
from ..services.material_service import (
    MaterialDuplicate,
    MaterialValidationError,
    MaterialNotFound,
    MaterialError,
    MaterialService,
)

router = APIRouter(prefix="/api/materials", tags=["materials"])
MODULE = "dm_giay_vat_tu"

class ClonePaperPayload(BaseModel):
    gsm: int = Field(ge=0)
    width_cm: float = Field(ge=0)
    height_cm: float = Field(ge=0)

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

@router.post("", response_model=MaterialDetailOut, status_code=status.HTTP_201_CREATED)
def create_material(
    payload: MaterialCreate,
    svc: Annotated[MaterialService, Depends(get_material_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> MaterialDetailOut:
    try:
        material = svc.create_material(
            name=payload.name,
            material_type=payload.material_type,
            unit=payload.unit,
            min_fee=payload.min_fee,
            width_cm=payload.width_cm,
            height_cm=payload.height_cm,
            gsm=payload.gsm,
            thickness_mm=payload.thickness_mm,
            default_waste_pct=payload.default_waste_pct,
            min_purchase_qty=payload.min_purchase_qty,
            paper_family=payload.paper_family,
            surface=payload.surface,
            is_active=payload.is_active,
            actor=user,
        )
    except MaterialDuplicate as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except MaterialValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    return MaterialDetailOut.model_validate(material)

@router.put("/{material_id}", response_model=MaterialDetailOut)
def update_material(
    material_id: int,
    payload: MaterialUpdate,
    svc: Annotated[MaterialService, Depends(get_material_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> MaterialDetailOut:
    try:
        material = svc.update_material(
            material_id=material_id,
            name=payload.name,
            material_type=payload.material_type,
            unit=payload.unit,
            min_fee=payload.min_fee,
            width_cm=payload.width_cm,
            height_cm=payload.height_cm,
            gsm=payload.gsm,
            thickness_mm=payload.thickness_mm,
            default_waste_pct=payload.default_waste_pct,
            min_purchase_qty=payload.min_purchase_qty,
            paper_family=payload.paper_family,
            surface=payload.surface,
            is_active=payload.is_active,
            actor=user,
        )
    except MaterialNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except MaterialDuplicate as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except MaterialValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    return MaterialDetailOut.model_validate(material)

@router.delete("/{material_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_material(
    material_id: int,
    svc: Annotated[MaterialService, Depends(get_material_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "delete"))],
) -> Response:
    try:
        svc.delete_material(material_id=material_id, actor=user)
    except MaterialNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except MaterialValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.patch("/{material_id}/toggle-active", response_model=MaterialDetailOut)
def toggle_active(
    material_id: int,
    svc: Annotated[MaterialService, Depends(get_material_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> MaterialDetailOut:
    try:
        material = svc.toggle_active(material_id=material_id, actor=user)
    except MaterialNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return MaterialDetailOut.model_validate(material)

@router.post("/{material_id}/costs", response_model=MaterialCostOut, status_code=status.HTTP_201_CREATED)
def add_material_price(
    material_id: int,
    payload: MaterialCostCreate,
    svc: Annotated[MaterialService, Depends(get_material_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> MaterialCostOut:
    try:
        cost = svc.add_material_price(
            material_id=material_id,
            price_unit=payload.price_unit,
            unit_price=payload.unit_price,
            effective_from=payload.effective_from,
            actor=user,
        )
    except MaterialNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except MaterialValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    return MaterialCostOut.model_validate(cost)

@router.post("/{material_id}/clone", response_model=MaterialDetailOut, status_code=status.HTTP_201_CREATED)
def clone_paper(
    material_id: int,
    payload: ClonePaperPayload,
    svc: Annotated[MaterialService, Depends(get_material_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> MaterialDetailOut:
    try:
        material = svc.clone_paper(
            material_id=material_id,
            gsm=payload.gsm,
            width_cm=payload.width_cm,
            height_cm=payload.height_cm,
            actor=user,
        )
    except MaterialNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except MaterialDuplicate as e:
        # #17 — clone tạo tên trùng (đã có "Couche 100gsm 79.0x109.0") → 409 như create/update,
        # không để lọt ra 500. MaterialDuplicate là sibling của MaterialValidationError nên phải bắt riêng.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except MaterialValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    return MaterialDetailOut.model_validate(material)
