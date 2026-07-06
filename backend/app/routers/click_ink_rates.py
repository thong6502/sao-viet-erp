"""FastAPI router for Click/Ink rates API.
"""
from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status, Response
from ..deps import CurrentUser, get_click_ink_rate_service, require_permission
from ..schemas.click_ink_rate import (
    ClickInkRateCreate,
    ClickInkRateClose,
    ClickInkRateOut,
    ClickInkRateListOut,
)
from ..services.click_ink_rate_service import (
    ClickInkRateService,
    ClickInkRateValidationError,
    ClickInkRateNotFoundError,
)

router = APIRouter(prefix="/api/click-ink-rates", tags=["click-ink-rates"])

@router.get(
    "",
    response_model=ClickInkRateListOut,
    dependencies=[Depends(require_permission("dm_gia_click", "read"))],
)
def list_rates(
    service: Annotated[ClickInkRateService, Depends(get_click_ink_rate_service)],
    technology: str | None = None,
    machine_id: int | None = None,
    is_active: bool | None = None,
    page: int = 1,
    size: int = 50,
) -> ClickInkRateListOut:
    items, total = service.list_rates(
        technology=technology,
        machine_id=machine_id,
        is_active=is_active,
        page=page,
        size=size,
    )
    return ClickInkRateListOut(items=items, total=total, page=page, size=size)

@router.post(
    "",
    response_model=ClickInkRateOut,
    status_code=status.HTTP_201_CREATED,
)
def create_rate(
    payload: ClickInkRateCreate,
    service: Annotated[ClickInkRateService, Depends(get_click_ink_rate_service)],
    actor: Annotated[CurrentUser, Depends(require_permission("dm_gia_click", "create"))],
) -> ClickInkRateOut:
    try:
        return service.create_rate(
            technology=payload.technology,
            color_type=payload.color_type,
            machine_id=payload.machine_id,
            unit=payload.unit,
            unit_price=payload.unit_price,
            setup_fee=payload.setup_fee,
            min_charge=payload.min_charge,
            effective_from=payload.effective_from,
            actor=actor,
        )
    except ClickInkRateValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

@router.post(
    "/{id}/close",
    response_model=ClickInkRateOut,
)
def close_rate(
    id: int,
    payload: ClickInkRateClose,
    service: Annotated[ClickInkRateService, Depends(get_click_ink_rate_service)],
    actor: Annotated[CurrentUser, Depends(require_permission("dm_gia_click", "update"))],
) -> ClickInkRateOut:
    try:
        return service.close_rate(
            rate_id=id,
            effective_to=payload.effective_to,
            actor=actor,
        )
    except ClickInkRateNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ClickInkRateValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_rate(
    id: int,
    service: Annotated[ClickInkRateService, Depends(get_click_ink_rate_service)],
    actor: Annotated[CurrentUser, Depends(require_permission("dm_gia_click", "delete"))],
) -> Response:
    try:
        service.delete_rate(rate_id=id, actor=actor)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ClickInkRateNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ClickInkRateValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

