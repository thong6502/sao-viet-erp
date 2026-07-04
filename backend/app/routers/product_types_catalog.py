"""Product Type Catalog router — spec-20/21.
"""
from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ..deps import get_product_type_catalog_service, require_permission
from ..models.user import User
from pydantic import BaseModel, Field
from ..schemas.product_type_catalog import (
    ProductTypeCatalogCreate,
    ProductTypeCatalogDetailOut,
    ProductTypeCatalogListOut,
    ProductTypeCatalogRow,
    ProductTypeCatalogUpdate,
    ProductTypePreviewOut,
)
from ..services.product_type_catalog_service import (
    ProductTypeCatalogDuplicate,
    ProductTypeCatalogValidationError,
    ProductTypeCatalogNotFound,
    ProductTypeCatalogInUse,
    ProductTypeCatalogError,
    ProductTypeCatalogService,
)


class ProductTypeCloneIn(BaseModel):
    new_product_type: str = Field(min_length=1, max_length=32)
    new_name: str = Field(min_length=1, max_length=100)

router = APIRouter(prefix="/api/product-types-catalog", tags=["product-types-catalog"])
MODULE = "dm_giay_vat_tu"

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

@router.post("", response_model=ProductTypeCatalogDetailOut, status_code=status.HTTP_201_CREATED)
def create_item(
    payload: ProductTypeCatalogCreate,
    svc: Annotated[ProductTypeCatalogService, Depends(get_product_type_catalog_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> ProductTypeCatalogDetailOut:
    try:
        data = payload.model_dump()
        item = svc.create_item(
            product_type=data.pop("product_type"),
            name=data.pop("name"),
            is_active=data.pop("is_active", True),
            actor=user,
            **data,
        )
    except ProductTypeCatalogDuplicate as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except ProductTypeCatalogValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    return ProductTypeCatalogDetailOut.model_validate(item)

@router.put("/{item_id}", response_model=ProductTypeCatalogDetailOut)
def update_item(
    item_id: int,
    payload: ProductTypeCatalogUpdate,
    svc: Annotated[ProductTypeCatalogService, Depends(get_product_type_catalog_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> ProductTypeCatalogDetailOut:
    try:
        data = payload.model_dump()
        item = svc.update_item(
            item_id=item_id,
            name=data.pop("name"),
            is_active=data.pop("is_active", None),
            actor=user,
            **data,
        )
    except ProductTypeCatalogNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except ProductTypeCatalogDuplicate as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except ProductTypeCatalogValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    return ProductTypeCatalogDetailOut.model_validate(item)

@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_item(
    item_id: int,
    svc: Annotated[ProductTypeCatalogService, Depends(get_product_type_catalog_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "delete"))],
) -> Response:
    try:
        svc.delete_item(item_id=item_id, actor=user)
    except ProductTypeCatalogNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except ProductTypeCatalogInUse as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except ProductTypeCatalogError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{item_id}/preview", response_model=ProductTypePreviewOut)
def preview_item(
    item_id: int,
    svc: Annotated[ProductTypeCatalogService, Depends(get_product_type_catalog_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> ProductTypePreviewOut:
    """Tab 'Test nhanh' — mô phỏng form/routing/quy tắc khi chọn loại SP này ở màn Tính giá."""
    try:
        result = svc.preview_config(item_id=item_id)
    except ProductTypeCatalogNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return ProductTypePreviewOut(**result)


@router.post("/{item_id}/clone", response_model=ProductTypeCatalogDetailOut, status_code=status.HTTP_201_CREATED)
def clone_item(
    item_id: int,
    payload: ProductTypeCloneIn,
    svc: Annotated[ProductTypeCatalogService, Depends(get_product_type_catalog_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> ProductTypeCatalogDetailOut:
    """spec §5.1 — Sao chép / Tạo version mới sang mã mới."""
    try:
        item = svc.clone_item(
            item_id=item_id,
            new_product_type=payload.new_product_type,
            new_name=payload.new_name,
            actor=user,
        )
    except ProductTypeCatalogNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except ProductTypeCatalogDuplicate as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except ProductTypeCatalogValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from None
    return ProductTypeCatalogDetailOut.model_validate(item)
