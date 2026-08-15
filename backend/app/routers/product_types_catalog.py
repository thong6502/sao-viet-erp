"""Product Type Catalog router — spec-20/21.
"""
from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..deps import get_product_type_catalog_service, require_permission
from ..legacy_api import LEGACY_READONLY
from ..models.user import User
from ..schemas.product_type_catalog import (
    ProductTypeCatalogDetailOut,
    ProductTypeCatalogListOut,
    ProductTypeCatalogRow,
)
from ..services.product_type_catalog_service import (
    ProductTypeCatalogNotFound,
    ProductTypeCatalogService,
)

# `deprecated=True` → OpenAPI gạch ngang cả nhóm; client sinh code sẽ cảnh báo thay vì im lặng.
router = APIRouter(prefix="/api/product-types-catalog", tags=["product-types-catalog"],
                   deprecated=True)
# Ô quyền RIÊNG, không dùng chung `dm_loai_san_pham` của màn Loại sản phẩm nữa — xem `legacy_api.py`.
MODULE = LEGACY_READONLY

@router.get("", response_model=ProductTypeCatalogListOut)
def list_items(
    svc: Annotated[ProductTypeCatalogService, Depends(get_product_type_catalog_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
    q: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    sort: str = Query(default="product_type"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
) -> ProductTypeCatalogListOut:
    rows, total = svc.list_items(q=q, is_active=is_active, sort=sort, page=page, size=size)
    return ProductTypeCatalogListOut(
        items=[ProductTypeCatalogRow.model_validate(r) for r in rows],
        total=total,
        page=page,
        size=size,
    )

@router.get("/{item_id}", response_model=ProductTypeCatalogDetailOut)
def get_item(
    item_id: int,
    svc: Annotated[ProductTypeCatalogService, Depends(get_product_type_catalog_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> ProductTypeCatalogDetailOut:
    try:
        item = svc.get_item(item_id)
    except ProductTypeCatalogNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return ProductTypeCatalogDetailOut.model_validate(item)
