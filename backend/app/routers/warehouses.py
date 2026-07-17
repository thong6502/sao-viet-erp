"""Warehouses router — cấu hình kho hàng (admin master data)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from ..deps import get_db, get_warehouse_service, require_any_permission, require_permission
from ..models.user import User
from ..repositories.warehouse_stock_repo import StockRepo
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
# ĐỌC danh sách kho: người vận hành kho (kho:read) cũng cần để chọn kho khi lập phiếu.
# Quản lý (tạo/sửa/xóa) vẫn giữ dm_kho.
_read_wh = require_any_permission(("dm_kho", "read"), ("kho", "read"))


@router.get("", response_model=WarehouseListOut)
def list_warehouses(
    svc: Annotated[WarehouseService, Depends(get_warehouse_service)],
    _: Annotated[User, Depends(_read_wh)],
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
    _: Annotated[User, Depends(_read_wh)],
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
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(MODULE, "delete"))],
    confirm: str = Query(..., description="Phải nhập ĐÚNG mã kho để xác nhận xóa (mềm)."),
) -> Response:
    """Xóa MỀM (ẩn kho). Bắt nhập đúng mã kho; CHẶN nếu kho còn hàng CHỜ XỬ LÝ
    (giữ chỗ / chờ KCS / lỗi) — phải xử lý xong trước."""
    try:
        wh = svc.get_warehouse(warehouse_id)
    except WarehouseNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None

    if confirm.strip().upper() != wh.code.upper():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Nhập đúng mã kho “{wh.code}” để xác nhận xóa.",
        )

    # Guard: hàng chờ xử lý = tồn thực nhưng KHÔNG khả dụng (giữ chỗ/chờ KCS/lỗi).
    rows = StockRepo(db).balance(warehouse_id=warehouse_id)
    on_hand = sum(float(r["on_hand"]) for r in rows)
    available = sum(float(r["available"]) for r in rows)
    pending = on_hand - available
    if pending > 1e-9:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Kho còn {pending:g} đơn vị hàng CHỜ XỬ LÝ (giữ chỗ / chờ KCS / lỗi). "
                   "Xử lý xong (xuất/chuyển/hủy) mới xóa được kho.",
        )

    svc.delete_warehouse(warehouse_id=warehouse_id, actor=user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
