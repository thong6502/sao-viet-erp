"""FastAPI router for Plate/Die rates API.
"""
from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status, Response
from ..deps import CurrentUser, get_plate_die_rate_service, require_permission
from ..schemas.plate_die_rate import (
    PlateDieRateCreate,
    PlateDieRateClose,
    PlateDieRateOut,
    PlateDieRateListOut,
)
from ..services.plate_die_rate_service import (
    PlateDieRateService,
    PlateDieRateValidationError,
    PlateDieRateNotFoundError,
)

router = APIRouter(prefix="/api/plate-die-rates", tags=["plate-die-rates"])

@router.get(
    "",
    response_model=PlateDieRateListOut,
    dependencies=[Depends(require_permission("dm_dinh_muc", "read"))],
)
def list_rates(
    service: Annotated[PlateDieRateService, Depends(get_plate_die_rate_service)],
    plate_type: str | None = None,
    technology: str | None = None,
    is_active: bool | None = None,
    page: int = 1,
    size: int = 50,
) -> PlateDieRateListOut:
    items, total = service.list_rates(
        plate_type=plate_type,
        technology=technology,
        is_active=is_active,
        page=page,
        size=size,
    )
    return PlateDieRateListOut(items=items, total=total, page=page, size=size)

@router.post(
    "",
    response_model=PlateDieRateOut,
    status_code=status.HTTP_201_CREATED,
)
def create_rate(
    payload: PlateDieRateCreate,
    service: Annotated[PlateDieRateService, Depends(get_plate_die_rate_service)],
    actor: Annotated[CurrentUser, Depends(require_permission("dm_dinh_muc", "create"))],
) -> PlateDieRateOut:
    try:
        return service.create_rate(
            plate_type=payload.plate_type,
            technology=payload.technology,
            unit=payload.unit,
            unit_price=payload.unit_price,
            setup_fee=payload.setup_fee,
            min_charge=payload.min_charge,
            reusable=payload.reusable,
            effective_from=payload.effective_from,
            actor=actor,
        )
    except PlateDieRateValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

@router.post(
    "/{id}/close",
    response_model=PlateDieRateOut,
)
def close_rate(
    id: int,
    payload: PlateDieRateClose,
    service: Annotated[PlateDieRateService, Depends(get_plate_die_rate_service)],
    actor: Annotated[CurrentUser, Depends(require_permission("dm_dinh_muc", "update"))],
) -> PlateDieRateOut:
    try:
        return service.close_rate(
            rate_id=id,
            effective_to=payload.effective_to,
            actor=actor,
        )
    except PlateDieRateNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PlateDieRateValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_rate(
    id: int,
    service: Annotated[PlateDieRateService, Depends(get_plate_die_rate_service)],
    actor: Annotated[CurrentUser, Depends(require_permission("dm_dinh_muc", "delete"))],
) -> Response:
    try:
        service.delete_rate(rate_id=id, actor=actor)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except PlateDieRateNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PlateDieRateValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

