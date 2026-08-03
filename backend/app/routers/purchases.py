"""Thu mua API — suppliers + purchase requests."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ..deps import CurrentUser, get_purchase_service, require_any_permission, require_permission
from ..models.user import User
from ..schemas.purchase import (
    DepartmentPurchaseRequestIn,
    DepartmentPurchaseRequestListOut,
    DepartmentPurchaseRequestOut,
    PurchaseRequestIn,
    PurchaseRequestListOut,
    PurchaseRequestOut,
    ReasonIn,
    SupplierIn,
    SupplierItemCatalogOut,
    SupplierListOut,
    SupplierRow,
)
from ..services.purchase_service import (
    PurchaseConflict,
    PurchaseForbidden,
    PurchaseNotFound,
    PurchaseService,
    PurchaseValidationError,
)

router = APIRouter(tags=["purchases"])
MODULE = "thu_mua"
DEPARTMENT_REQUEST_READERS = (
    ("thu_mua", "read"),
    ("bao_gia", "read"),
    ("kho", "read"),
    ("san_xuat", "read"),
    ("dm_giay_vat_tu", "read"),
    # Kế toán truy vết YCMH nguồn khi duyệt PMH / lập Phiếu chi (SEAM-25).
    ("ke_toan", "read"),
)


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PurchaseNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, PurchaseValidationError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if isinstance(exc, PurchaseConflict):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, PurchaseForbidden):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/api/department-purchase-requests", response_model=DepartmentPurchaseRequestListOut)
def list_department_purchase_requests(
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: CurrentUser,
    q: str | None = Query(default=None),
    status_: str | None = Query(default=None, alias="status"),
    source_type: str | None = Query(default=None),
    sort: str = Query(default="-created_at"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> DepartmentPurchaseRequestListOut:
    rows, total = svc.list_department_requests(
        actor=user, q=q, status=status_, source_type=source_type, sort=sort, page=page, size=size
    )
    return DepartmentPurchaseRequestListOut(items=rows, total=total, page=page, size=size)


@router.get("/api/department-purchase-requests/can-create")
def can_create_department_purchase_request(
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: CurrentUser,
) -> dict[str, bool]:
    return {"can_create": svc.can_create_department_request(user)}


@router.get("/api/department-purchase-requests/{request_id}", response_model=DepartmentPurchaseRequestOut)
def get_department_purchase_request(
    request_id: int,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: CurrentUser,
) -> DepartmentPurchaseRequestOut:
    try:
        return DepartmentPurchaseRequestOut(**svc.get_department_request(request_id, actor=user))
    except (PurchaseValidationError, PurchaseConflict, PurchaseForbidden, PurchaseNotFound) as exc:
        raise _map_error(exc) from None


@router.post(
    "/api/department-purchase-requests",
    response_model=DepartmentPurchaseRequestOut,
    status_code=status.HTTP_201_CREATED,
)
def create_department_purchase_request(
    payload: DepartmentPurchaseRequestIn,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: CurrentUser,
) -> DepartmentPurchaseRequestOut:
    try:
        return DepartmentPurchaseRequestOut(
            **svc.create_department_request(actor=user, **payload.model_dump())
        )
    except (PurchaseValidationError, PurchaseConflict, PurchaseForbidden, PurchaseNotFound) as exc:
        raise _map_error(exc) from None


@router.put("/api/department-purchase-requests/{request_id}", response_model=DepartmentPurchaseRequestOut)
def update_department_purchase_request(
    request_id: int,
    payload: DepartmentPurchaseRequestIn,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: CurrentUser,
) -> DepartmentPurchaseRequestOut:
    try:
        return DepartmentPurchaseRequestOut(
            **svc.update_department_request(request_id, actor=user, **payload.model_dump())
        )
    except (PurchaseValidationError, PurchaseConflict, PurchaseForbidden, PurchaseNotFound) as exc:
        raise _map_error(exc) from None


@router.post("/api/department-purchase-requests/{request_id}/cancel", response_model=DepartmentPurchaseRequestOut)
def cancel_department_purchase_request(
    request_id: int,
    payload: ReasonIn,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: CurrentUser,
) -> DepartmentPurchaseRequestOut:
    try:
        return DepartmentPurchaseRequestOut(
            **svc.cancel_department_request(request_id, reason=payload.reason, actor=user)
        )
    except (PurchaseValidationError, PurchaseConflict, PurchaseForbidden, PurchaseNotFound) as exc:
        raise _map_error(exc) from None


@router.get("/api/suppliers", response_model=SupplierListOut)
def list_suppliers(
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    _: Annotated[
        User,
        Depends(require_any_permission((MODULE, "read"), ("ke_toan", "read"))),
    ],
    q: str | None = Query(default=None),
    status_: str | None = Query(default=None, alias="status"),
    supplier_group: str | None = Query(default=None),
    sort: str = Query(default="name"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> SupplierListOut:
    rows, total = svc.list_suppliers(
        q=q, status=status_, supplier_group=supplier_group, sort=sort, page=page, size=size
    )
    return SupplierListOut(
        items=[SupplierRow.model_validate(row) for row in rows],
        total=total,
        page=page,
        size=size,
    )


@router.get("/api/supplier-items/catalog", response_model=SupplierItemCatalogOut)
def supplier_item_catalog(
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    _: CurrentUser,
) -> SupplierItemCatalogOut:
    return SupplierItemCatalogOut(items=svc.list_supplier_item_catalog())


@router.post("/api/suppliers", response_model=SupplierRow, status_code=status.HTTP_201_CREATED)
def create_supplier(
    payload: SupplierIn,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> SupplierRow:
    try:
        return SupplierRow.model_validate(svc.create_supplier(actor=user, **payload.model_dump()))
    except (PurchaseValidationError, PurchaseConflict, PurchaseNotFound) as exc:
        raise _map_error(exc) from None


@router.put("/api/suppliers/{supplier_id}", response_model=SupplierRow)
def update_supplier(
    supplier_id: int,
    payload: SupplierIn,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> SupplierRow:
    try:
        return SupplierRow.model_validate(
            svc.update_supplier(supplier_id, actor=user, **payload.model_dump())
        )
    except (PurchaseValidationError, PurchaseConflict, PurchaseNotFound) as exc:
        raise _map_error(exc) from None


@router.patch("/api/suppliers/{supplier_id}/toggle-active", response_model=SupplierRow)
def toggle_supplier(
    supplier_id: int,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> SupplierRow:
    try:
        return SupplierRow.model_validate(svc.toggle_supplier_active(supplier_id, actor=user))
    except (PurchaseValidationError, PurchaseConflict, PurchaseNotFound) as exc:
        raise _map_error(exc) from None


@router.get("/api/purchase-requests", response_model=PurchaseRequestListOut)
def list_purchase_requests(
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    _: Annotated[
        User,
        Depends(require_any_permission((MODULE, "read"), ("ke_toan", "read"))),
    ],
    q: str | None = Query(default=None),
    status_: str | None = Query(default=None, alias="status"),
    supplier_id: int | None = Query(default=None),
    sort: str = Query(default="-created_at"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> PurchaseRequestListOut:
    rows, total = svc.list_requests(
        q=q, status=status_, supplier_id=supplier_id, sort=sort, page=page, size=size
    )
    return PurchaseRequestListOut(items=rows, total=total, page=page, size=size)


@router.get("/api/purchase-requests/{request_id}", response_model=PurchaseRequestOut)
def get_purchase_request(
    request_id: int,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    _: Annotated[
        User,
        Depends(require_any_permission((MODULE, "read"), ("ke_toan", "read"))),
    ],
) -> PurchaseRequestOut:
    try:
        return PurchaseRequestOut(**svc.get_request(request_id))
    except (PurchaseValidationError, PurchaseConflict, PurchaseNotFound) as exc:
        raise _map_error(exc) from None


@router.post("/api/purchase-requests", response_model=PurchaseRequestOut, status_code=status.HTTP_201_CREATED)
def create_purchase_request(
    payload: PurchaseRequestIn,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> PurchaseRequestOut:
    try:
        return PurchaseRequestOut(**svc.create_request(actor=user, **payload.model_dump()))
    except (PurchaseValidationError, PurchaseConflict, PurchaseNotFound) as exc:
        raise _map_error(exc) from None


@router.put("/api/purchase-requests/{request_id}", response_model=PurchaseRequestOut)
def update_purchase_request(
    request_id: int,
    payload: PurchaseRequestIn,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> PurchaseRequestOut:
    try:
        return PurchaseRequestOut(
            **svc.update_request(request_id, actor=user, **payload.model_dump())
        )
    except (PurchaseValidationError, PurchaseConflict, PurchaseNotFound) as exc:
        raise _map_error(exc) from None


@router.delete("/api/purchase-requests/{request_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_purchase_request(
    request_id: int,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "delete"))],
) -> Response:
    try:
        svc.delete_request(request_id, actor=user)
    except (PurchaseValidationError, PurchaseConflict, PurchaseNotFound) as exc:
        raise _map_error(exc) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/api/purchase-requests/{request_id}/submit", response_model=PurchaseRequestOut)
def submit_purchase_request(
    request_id: int,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> PurchaseRequestOut:
    try:
        return PurchaseRequestOut(**svc.submit(request_id, actor=user))
    except (PurchaseValidationError, PurchaseConflict, PurchaseNotFound) as exc:
        raise _map_error(exc) from None


@router.post("/api/purchase-requests/{request_id}/approve", response_model=PurchaseRequestOut)
def approve_purchase_request(
    request_id: int,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "approve"))],
) -> PurchaseRequestOut:
    try:
        return PurchaseRequestOut(**svc.approve(request_id, actor=user))
    except (PurchaseValidationError, PurchaseConflict, PurchaseNotFound) as exc:
        raise _map_error(exc) from None


@router.post("/api/purchase-requests/{request_id}/reject", response_model=PurchaseRequestOut)
def reject_purchase_request(
    request_id: int,
    payload: ReasonIn,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "approve"))],
) -> PurchaseRequestOut:
    try:
        return PurchaseRequestOut(**svc.reject(request_id, reason=payload.reason, actor=user))
    except (PurchaseValidationError, PurchaseConflict, PurchaseNotFound) as exc:
        raise _map_error(exc) from None


@router.post("/api/purchase-requests/{request_id}/mark-purchased", response_model=PurchaseRequestOut)
def mark_purchase_request_purchased(
    request_id: int,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> PurchaseRequestOut:
    try:
        return PurchaseRequestOut(**svc.mark_purchased(request_id, actor=user))
    except (PurchaseValidationError, PurchaseConflict, PurchaseNotFound) as exc:
        raise _map_error(exc) from None


@router.post("/api/purchase-requests/{request_id}/mark-received", response_model=PurchaseRequestOut)
def mark_purchase_request_received(
    request_id: int,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> PurchaseRequestOut:
    try:
        return PurchaseRequestOut(**svc.mark_received(request_id, actor=user))
    except (PurchaseValidationError, PurchaseConflict, PurchaseNotFound) as exc:
        raise _map_error(exc) from None


@router.post("/api/purchase-requests/{request_id}/cancel", response_model=PurchaseRequestOut)
def cancel_purchase_request(
    request_id: int,
    payload: ReasonIn,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "cancel"))],
) -> PurchaseRequestOut:
    try:
        return PurchaseRequestOut(**svc.cancel(request_id, reason=payload.reason, actor=user))
    except (PurchaseValidationError, PurchaseConflict, PurchaseNotFound) as exc:
        raise _map_error(exc) from None
