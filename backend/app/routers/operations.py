"""Operations router — spec-20/21.
"""
from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ..deps import get_operation_service, require_permission
from ..models.user import User
from ..schemas.operation import (
    OperationRateCreate,
    OperationRateOut,
    OperationCreate,
    OperationDetailOut,
    OperationListOut,
    OperationPreviewIn,
    OperationPreviewOut,
    OperationRow,
    OperationUpdate,
)
from ..services.operation_service import (
    OperationDuplicate,
    OperationInUse,
    OperationValidationError,
    OperationNotFound,
    OperationService,
)

router = APIRouter(prefix="/api/operations", tags=["operations"])
MODULE = "dm_giay_vat_tu"

@router.get("", response_model=OperationListOut)
def list_operations(
    svc: Annotated[OperationService, Depends(get_operation_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
    q: str | None = Query(default=None),
    operation_type: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    sort: str = Query(default="code"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> OperationListOut:
    rows, total = svc.list_operations(
        q=q, operation_type=operation_type, is_active=is_active, sort=sort, page=page, size=size
    )
    return OperationListOut(
        items=[OperationRow.model_validate(r) for r in rows],
        total=total,
        page=page,
        size=size,
    )

@router.get("/{operation_id}", response_model=OperationDetailOut)
def get_operation(
    operation_id: int,
    svc: Annotated[OperationService, Depends(get_operation_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> OperationDetailOut:
    try:
        operation = svc.get_operation(operation_id)
    except OperationNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return OperationDetailOut.model_validate(operation)

@router.post("", response_model=OperationDetailOut, status_code=status.HTTP_201_CREATED)
def create_operation(
    payload: OperationCreate,
    svc: Annotated[OperationService, Depends(get_operation_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> OperationDetailOut:
    try:
        operation = svc.create_operation(
            actor=user,
            **payload.model_dump(),
        )
    except OperationDuplicate as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except OperationValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    return OperationDetailOut.model_validate(operation)

@router.put("/{operation_id}", response_model=OperationDetailOut)
def update_operation(
    operation_id: int,
    payload: OperationUpdate,
    svc: Annotated[OperationService, Depends(get_operation_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> OperationDetailOut:
    try:
        operation = svc.update_operation(
            operation_id=operation_id,
            actor=user,
            **payload.model_dump(),
        )
    except OperationNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except OperationDuplicate as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except OperationValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    return OperationDetailOut.model_validate(operation)

@router.delete("/{operation_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_operation(
    operation_id: int,
    svc: Annotated[OperationService, Depends(get_operation_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "delete"))],
) -> Response:
    try:
        svc.delete_operation(operation_id=operation_id, actor=user)
    except OperationNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except OperationInUse as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except OperationValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.post("/{operation_id}/rates", response_model=OperationRateOut, status_code=status.HTTP_201_CREATED)
def add_operation_rate(
    operation_id: int,
    payload: OperationRateCreate,
    svc: Annotated[OperationService, Depends(get_operation_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> OperationRateOut:
    try:
        rate = svc.add_operation_rate(
            operation_id=operation_id,
            effective_from=payload.effective_from,
            actor=user,
            **payload.model_dump(exclude={"effective_from"}),
        )
    except OperationNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except OperationValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    return OperationRateOut.model_validate(rate)


@router.post("/{operation_id}/preview", response_model=OperationPreviewOut)
def preview_operation_cost(
    operation_id: int,
    payload: OperationPreviewIn,
    svc: Annotated[OperationService, Depends(get_operation_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> OperationPreviewOut:
    """Tab 'Test nhanh' — mô phỏng chi phí công đoạn theo lượng nhập & cách làm."""
    try:
        result = svc.preview_cost(operation_id=operation_id, preview=payload)
    except OperationNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return OperationPreviewOut(**result)
