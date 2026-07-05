"""Warehouses router — cấu hình kho hàng (admin master data)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ..deps import get_warehouse_service, require_permission
from ..models.user import User
from ..schemas.warehouse import (
    WarehouseCreate,
    WarehouseListOut,
    WarehouseRow,
    WarehouseUpdate,
)
from ..services.warehouse_service import (
    WarehouseDuplicate,
    WarehouseNotFound,
    WarehouseService,
    WarehouseValidationError,
)

router = APIRouter(prefix="/api/warehouses", tags=["warehouses"])
MODULE = "dm_kho"


@router.get("", response_model=WarehouseListOut)
def list_warehouses(
    svc: Annotated[WarehouseService, Depends(get_warehouse_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
    q: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    sort: str = Query(default="code"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> WarehouseListOut:
    rows, total = svc.list_warehouses(q=q, is_active=is_active, sort=sort, page=page, size=size)
    return WarehouseListOut(
        items=[WarehouseRow.model_validate(r) for r in rows],
        total=total,
        page=page,
        size=size,
    )


@router.get("/{warehouse_id}", response_model=WarehouseRow)
def get_warehouse(
    warehouse_id: int,
    svc: Annotated[WarehouseService, Depends(get_warehouse_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> WarehouseRow:
    try:
        warehouse = svc.get_warehouse(warehouse_id)
    except WarehouseNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return WarehouseRow.model_validate(warehouse)


@router.post("", response_model=WarehouseRow, status_code=status.HTTP_201_CREATED)
def create_warehouse(
    payload: WarehouseCreate,
    svc: Annotated[WarehouseService, Depends(get_warehouse_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> WarehouseRow:
    try:
        warehouse = svc.create_warehouse(
            name=payload.name,
            description=payload.description,
            notes=payload.notes,
            is_active=payload.is_active,
            actor=user,
        )
    except WarehouseDuplicate as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except WarehouseValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    return WarehouseRow.model_validate(warehouse)


@router.put("/{warehouse_id}", response_model=WarehouseRow)
def update_warehouse(
    warehouse_id: int,
    payload: WarehouseUpdate,
    svc: Annotated[WarehouseService, Depends(get_warehouse_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> WarehouseRow:
    try:
        warehouse = svc.update_warehouse(
            warehouse_id=warehouse_id,
            name=payload.name,
            description=payload.description,
            notes=payload.notes,
            is_active=payload.is_active,
            actor=user,
        )
    except WarehouseNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except WarehouseDuplicate as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except WarehouseValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    return WarehouseRow.model_validate(warehouse)


@router.delete("/{warehouse_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_warehouse(
    warehouse_id: int,
    svc: Annotated[WarehouseService, Depends(get_warehouse_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "delete"))],
) -> Response:
    try:
        svc.delete_warehouse(warehouse_id=warehouse_id, actor=user)
    except WarehouseNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
