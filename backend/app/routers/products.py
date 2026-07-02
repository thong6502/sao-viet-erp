"""Sản phẩm in (Product catalog) routes — spec-07-san-pham.

Thin HTTP shell over ProductService. Every route is guarded by
`require_permission('san_pham', <action>)`. The product catalog is a global reusable
master (not scoped own/department). The paper picker is a SEAM-03 seam: when Danh mục
Giấy (`dm_giay_vat_tu`) is not built the port raises and we return an explicit
"unavailable" picker (never a fabricated paper list).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ..deps import get_product_service, require_permission
from ..models.product import (
    BINDING_TYPES,
    COMPONENT_TYPES,
    GRAIN_DIRECTIONS,
    PRODUCT_TYPES,
    Product,
)
from ..models.user import User
from ..schemas.product import (
    ComponentOut,
    EnumOption,
    PaperPickerOut,
    ProductCreate,
    ProductDetailOut,
    ProductEnumsOut,
    ProductListOut,
    ProductRow,
    ProductUpdate,
)
from ..services.product_service import (
    ProductDuplicateName,
    ProductInUse,
    ProductNotFound,
    ProductService,
    ProductValidationError,
)

router = APIRouter(prefix="/api/products", tags=["products"])

MODULE = "san_pham"

Service = Annotated[ProductService, Depends(get_product_service)]

# Human labels (Vietnamese) for the form selects. Keys must match the model enums.
PRODUCT_TYPE_LABELS = {
    "catalogue": "Catalogue",
    "brochure": "Brochure",
    "tem_nhan": "Tem / Nhãn",
    "hop": "Hộp giấy",
    "sach": "Sách",
    "to_roi": "Tờ rơi",
    "name_card": "Name card",
}
BINDING_LABELS = {
    "none": "Không gáy",
    "perfect": "Keo nhiệt (perfect)",
    "saddle": "Đóng kim (saddle)",
    "sewn": "Khâu chỉ (sewn)",
}
COMPONENT_LABELS = {
    "cover": "Bìa",
    "body": "Ruột",
    "insert": "Tay đệm",
}
GRAIN_LABELS = {
    "long": "Thớ dọc (long)",
    "short": "Thớ ngang (short)",
}


def _row(product: Product, count: int) -> ProductRow:
    return ProductRow(
        id=product.id,
        code=product.code,
        name=product.name,
        product_type=product.product_type,
        binding_type=product.binding_type,
        component_count=count,
    )


def _detail(product: Product) -> ProductDetailOut:
    return ProductDetailOut(
        id=product.id,
        code=product.code,
        name=product.name,
        product_type=product.product_type,
        binding_type=product.binding_type,
        note=product.note,
        components=[
            ComponentOut(
                id=c.id,
                sequence=c.sequence,
                component_type=c.component_type,
                paper_master_id=c.paper_master_id,
                # SEAM-03: no live paper label until Danh mục Giấy is built.
                paper_display=None,
                colors_front=c.colors_front,
                colors_back=c.colors_back,
                page_count=c.page_count,
                finished_w=float(c.finished_w),
                finished_h=float(c.finished_h),
                bleed=float(c.bleed),
                grain_direction=c.grain_direction,
            )
            for c in product.components
        ],
    )


@router.get("/enums", response_model=ProductEnumsOut)
def product_enums(
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> ProductEnumsOut:
    """Enum vocab for the form selects (loại SP §7, kiểu đóng §5, loại cấu phần, canh thớ)."""
    return ProductEnumsOut(
        product_types=[
            EnumOption(value=v, label=PRODUCT_TYPE_LABELS.get(v, v)) for v in PRODUCT_TYPES
        ],
        binding_types=[
            EnumOption(value=v, label=BINDING_LABELS.get(v, v)) for v in BINDING_TYPES
        ],
        component_types=[
            EnumOption(value=v, label=COMPONENT_LABELS.get(v, v)) for v in COMPONENT_TYPES
        ],
        grain_directions=[
            EnumOption(value=v, label=GRAIN_LABELS.get(v, v)) for v in GRAIN_DIRECTIONS
        ],
    )


@router.get("/papers", response_model=PaperPickerOut)
def list_papers(
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
    q: str | None = Query(default=None),
) -> PaperPickerOut:
    """Paper picker for the component editor. SEAM-03: when Danh mục Giấy is not built the
    port raises → explicit "unavailable" (never a fabricated list)."""
    try:
        papers = svc.list_papers(q)
    except NotImplementedError:
        # SEAM-03: chờ dm_giay_vat_tu (PaperMaster)
        return PaperPickerOut(
            available=False,
            message="Danh mục Giấy chưa sẵn sàng",
        )
    return PaperPickerOut(
        available=True,
        items=[
            {
                "paper_master_id": p.paper_master_id,
                "family": p.family,
                "gsm": p.gsm,
                "sheet_w_cm": p.sheet_w_cm,
                "sheet_h_cm": p.sheet_h_cm,
                "display_name": p.display_name,
            }
            for p in papers
        ],
    )


@router.get("", response_model=ProductListOut)
def list_products(
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
    q: str | None = Query(default=None),
    product_type: str | None = Query(default=None),
    sort: str = Query(default="code"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> ProductListOut:
    rows, total, counts = svc.list_products(
        q=q, product_type=product_type, sort=sort, page=page, size=size
    )
    return ProductListOut(
        items=[_row(p, counts.get(p.id, 0)) for p in rows],
        total=total,
        page=page,
        size=size,
    )


@router.post("", response_model=ProductDetailOut, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreate,
    svc: Service,
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> ProductDetailOut:
    try:
        product = svc.create_product(
            name=payload.name,
            product_type=payload.product_type,
            binding_type=payload.binding_type,
            note=payload.note,
            components=[c.model_dump() for c in payload.components],
            actor=user,
        )
    except ProductDuplicateName as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except ProductValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    return _detail(product)


@router.get("/{product_id}", response_model=ProductDetailOut)
def get_product(
    product_id: int,
    svc: Service,
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> ProductDetailOut:
    try:
        product = svc.get_product(product_id)
    except ProductNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy sản phẩm."
        ) from None
    return _detail(product)


@router.put("/{product_id}", response_model=ProductDetailOut)
def update_product(
    product_id: int,
    payload: ProductUpdate,
    svc: Service,
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> ProductDetailOut:
    try:
        product = svc.update_product(
            product_id=product_id,
            name=payload.name,
            product_type=payload.product_type,
            binding_type=payload.binding_type,
            note=payload.note,
            components=[c.model_dump() for c in payload.components],
            actor=user,
        )
    except ProductNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy sản phẩm."
        ) from None
    except ProductDuplicateName as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except ProductValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    return _detail(product)


@router.delete(
    "/{product_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
def delete_product(
    product_id: int,
    svc: Service,
    user: Annotated[User, Depends(require_permission(MODULE, "delete"))],
) -> Response:
    try:
        svc.delete_product(product_id=product_id, actor=user)
    except ProductNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy sản phẩm."
        ) from None
    except ProductInUse as e:
        # Reserved for when Kinh doanh/Job references products (spec-07 F4).
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
