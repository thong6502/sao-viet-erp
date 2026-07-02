"""FastAPI router for Norms configuration API.
"""
from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status, Response
from ..deps import CurrentUser, get_norm_service, require_permission
from ..schemas.norm import NormCreate, NormClose, NormOut, NormListOut
from ..services.norm_service import NormService, NormValidationError, NormNotFoundError

router = APIRouter(prefix="/api/norms", tags=["norms"])

@router.get(
    "",
    response_model=NormListOut,
    dependencies=[Depends(require_permission("dm_dinh_muc", "read"))],
)
def list_norms(
    service: Annotated[NormService, Depends(get_norm_service)],
    norm_key: str | None = None,
    product_type: str | None = None,
    machine_id: int | None = None,
    operation_id: int | None = None,
    only_current: bool = False,
    page: int = 1,
    size: int = 50,
) -> NormListOut:
    items, total = service.list_norms(
        norm_key=norm_key,
        product_type=product_type,
        machine_id=machine_id,
        operation_id=operation_id,
        only_current=only_current,
        page=page,
        size=size,
    )
    return NormListOut(items=items, total=total, page=page, size=size)

@router.post(
    "",
    response_model=NormOut,
    status_code=status.HTTP_201_CREATED,
)
def create_norm(
    payload: NormCreate,
    service: Annotated[NormService, Depends(get_norm_service)],
    actor: Annotated[CurrentUser, Depends(require_permission("dm_dinh_muc", "create"))],
) -> NormOut:
    try:
        return service.create_norm(
            norm_key=payload.norm_key,
            value=payload.value,
            product_type=payload.product_type,
            machine_id=payload.machine_id,
            operation_id=payload.operation_id,
            operation_key=payload.operation_key,
            qty_min=payload.qty_min,
            qty_max=payload.qty_max,
            context=payload.context,
            effective_from=payload.effective_from,
            note=payload.note,
            actor=actor,
        )
    except NormValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

@router.post(
    "/{id}/close",
    response_model=NormOut,
)
def close_norm(
    id: int,
    payload: NormClose,
    service: Annotated[NormService, Depends(get_norm_service)],
    actor: Annotated[CurrentUser, Depends(require_permission("dm_dinh_muc", "update"))],
) -> NormOut:
    try:
        return service.close_norm(
            norm_id=id,
            effective_to=payload.effective_to,
            actor=actor,
        )
    except NormNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except NormValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_norm(
    id: int,
    service: Annotated[NormService, Depends(get_norm_service)],
    actor: Annotated[CurrentUser, Depends(require_permission("dm_dinh_muc", "delete"))],
) -> Response:
    try:
        service.delete_norm(norm_id=id, actor=actor)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except NormNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except NormValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

