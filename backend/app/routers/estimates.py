"""Official routes for Estimate API — spec-08 / Phase 2A.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ..deps import get_estimate_service, require_permission
from ..models.user import User
from ..schemas.estimate import (
    EstimateCreate,
    EstimateListOut,
    EstimateOut,
    EstimateRow,
    EstimateUpdate,
)
from ..services.estimate_service import (
    EstimateInUse,
    EstimateNotFound,
    EstimateService,
    EstimateValidationError,
)

router = APIRouter(prefix="/api/estimates", tags=["estimates"])

MODULE = "tinh_gia_thanh"

@router.get("", response_model=EstimateListOut)
def list_estimates(
    svc: Annotated[EstimateService, Depends(get_estimate_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
    q: str | None = Query(default=None),
    product_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    sort: str = "estimate_number",
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> EstimateListOut:
    rows, total = svc.list_estimates(
        q=q,
        product_type=product_type,
        status=status,
        sort=sort,
        page=page,
        size=size
    )

    items = []
    for est in rows:
        # compute min and max cost from options
        costs = [float(opt.total_cost) for opt in est.options]
        min_cost = min(costs) if costs else None
        max_cost = max(costs) if costs else None

        # count warnings and blocking errors
        warnings_count = 0
        blocking_error_count = 0
        for opt in est.options:
            if opt.warnings_json:
                for w in opt.warnings_json:
                    if w.get("severity") == "blocking_error":
                        blocking_error_count += 1
                    else:
                        warnings_count += 1

        items.append(EstimateRow(
            id=est.id,
            estimate_number=est.estimate_number,
            product_type=est.product_type,
            product_name=est.product_name,
            status=est.status,
            quantity_list_json=est.quantity_list_json,
            total_cost_min=min_cost,
            total_cost_max=max_cost,
            warnings_count=warnings_count,
            blocking_error_count=blocking_error_count,
            created_at=est.created_at,
            updated_at=est.updated_at,
        ))

    return EstimateListOut(
        items=items,
        total=total,
        page=page,
        size=size
    )


@router.post("", response_model=EstimateOut, status_code=status.HTTP_201_CREATED)
def create_estimate(
    payload: EstimateCreate,
    svc: Annotated[EstimateService, Depends(get_estimate_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> EstimateOut:
    try:
        est = svc.create_estimate(
            product_type=payload.product_type,
            product_name=payload.product_name,
            quantity_list=payload.quantity_list,
            input_spec=payload.input_spec,
            customer_id=payload.customer_id,
            actor_id=user.id,
            status=payload.status
        )
    except EstimateValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        ) from None
    
    return est


@router.get("/{estimate_id}", response_model=EstimateOut)
def get_estimate(
    estimate_id: int,
    svc: Annotated[EstimateService, Depends(get_estimate_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> EstimateOut:
    try:
        est = svc.get_estimate(estimate_id)
    except EstimateNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy phương án tính giá."
        ) from None
    return est


@router.put("/{estimate_id}", response_model=EstimateOut)
def update_estimate(
    estimate_id: int,
    payload: EstimateUpdate,
    svc: Annotated[EstimateService, Depends(get_estimate_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> EstimateOut:
    try:
        est = svc.update_estimate(
            estimate_id=estimate_id,
            product_type=payload.product_type,
            product_name=payload.product_name,
            quantity_list=payload.quantity_list,
            input_spec=payload.input_spec,
            customer_id=payload.customer_id,
            actor_id=user.id,
            status=payload.status
        )
    except EstimateNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy phương án tính giá."
        ) from None
    except EstimateValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        ) from None
    except EstimateInUse as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        ) from None
    return est


@router.delete("/{estimate_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_estimate(
    estimate_id: int,
    svc: Annotated[EstimateService, Depends(get_estimate_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "delete"))],
) -> Response:
    try:
        svc.delete_estimate(estimate_id=estimate_id, actor_id=user.id)
    except EstimateNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy phương án tính giá."
        ) from None
    except EstimateInUse as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        ) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
