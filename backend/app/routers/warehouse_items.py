"""Kho hàng (warehouse items) router — module vận hành `kho`.

Nhân viên / trưởng phòng / chức vụ khác (có quyền `kho`) nhập mặt hàng cơ bản vào
các kho mà admin đã cấu hình (bảng warehouses / module dm_kho).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ..deps import get_warehouse_item_service, require_permission
from ..models.user import User
from ..schemas.warehouse_item import (
    WarehouseItemCreate,
    WarehouseItemListOut,
    WarehouseItemRow,
    WarehouseItemUpdate,
    WarehouseOption,
)
from ..services.warehouse_item_service import (
    WarehouseItemNotFound,
    WarehouseItemService,
    WarehouseItemValidationError,
    WarehouseNotConfigured,
)

router = APIRouter(prefix="/api/warehouse-items", tags=["warehouse-items"])
MODULE = "kho"


@router.get("/warehouse-options", response_model=list[WarehouseOption])
def warehouse_options(
    svc: Annotated[WarehouseItemService, Depends(get_warehouse_item_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> list[WarehouseOption]:
    # Danh sách kho admin đã cấu hình (đang kích hoạt) để nhân viên chọn — gated bằng `kho`
    # nên không cần quyền cấu hình `dm_kho`.
    return [WarehouseOption(**o) for o in svc.active_warehouse_options()]


@router.get("", response_model=WarehouseItemListOut)
def list_items(
    svc: Annotated[WarehouseItemService, Depends(get_warehouse_item_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
    warehouse_id: int | None = Query(default=None),
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> WarehouseItemListOut:
    rows, total = svc.list_items(warehouse_id=warehouse_id, q=q, page=page, size=size)
    return WarehouseItemListOut(
        items=[WarehouseItemRow(**r) for r in rows],
        total=total,
        page=page,
        size=size,
    )


@router.post("", response_model=WarehouseItemRow, status_code=status.HTTP_201_CREATED)
def create_item(
    payload: WarehouseItemCreate,
    svc: Annotated[WarehouseItemService, Depends(get_warehouse_item_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> WarehouseItemRow:
    try:
        row = svc.create_item(
            warehouse_id=payload.warehouse_id,
            name=payload.name,
            quantity=payload.quantity,
            unit=payload.unit,
            notes=payload.notes,
            actor=user,
        )
    except WarehouseNotConfigured as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except WarehouseItemValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    return WarehouseItemRow(**row)


@router.put("/{item_id}", response_model=WarehouseItemRow)
def update_item(
    item_id: int,
    payload: WarehouseItemUpdate,
    svc: Annotated[WarehouseItemService, Depends(get_warehouse_item_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> WarehouseItemRow:
    try:
        row = svc.update_item(
            item_id=item_id,
            warehouse_id=payload.warehouse_id,
            name=payload.name,
            quantity=payload.quantity,
            unit=payload.unit,
            notes=payload.notes,
            actor=user,
        )
    except WarehouseItemNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except WarehouseNotConfigured as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except WarehouseItemValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    return WarehouseItemRow(**row)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_item(
    item_id: int,
    svc: Annotated[WarehouseItemService, Depends(get_warehouse_item_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "delete"))],
) -> Response:
    try:
        svc.delete_item(item_id=item_id, actor=user)
    except WarehouseItemNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
