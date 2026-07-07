"""Operations router — spec-20/21.

Read-only surface: the admin/write endpoints were removed; the pricing engine
and Báo giá only need to list/read operations. Write methods still live on the
service/repo (used by the seed).
"""
from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..deps import get_operation_service, require_permission
from ..models.user import User
from ..schemas.operation import (
    OperationDetailOut,
    OperationListOut,
    OperationRow,
)
from ..services.operation_service import (
    OperationNotFound,
    OperationService,
)

router = APIRouter(prefix="/api/operations", tags=["operations"])
MODULE = "dm_cong_doan"

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
