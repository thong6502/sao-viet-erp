"""FastAPI router for Plate/Die rates API — Đơn giá kẽm & khuôn (catalog #5)."""
from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, status, Response
from ..deps import CurrentUser, get_plate_die_rate_service, require_permission
from ..schemas.plate_die_rate import (
    PlateDieRateCreate,
    PlateDieRateVersion,
    PlateDieRateClose,
    PlateDieRateOut,
    PlateDieRateListOut,
)
from ..services.plate_die_rate_service import (
    PlateDieRateService,
    PlateDieRateValidationError,
    PlateDieRateDuplicate,
    PlateDieRateNotFoundError,
)

router = APIRouter(prefix="/api/plate-die-rates", tags=["plate-die-rates"])
MODULE = "dm_dinh_muc"


@router.get("", response_model=PlateDieRateListOut,
            dependencies=[Depends(require_permission(MODULE, "read"))])
def list_rates(
    service: Annotated[PlateDieRateService, Depends(get_plate_die_rate_service)],
    q: str | None = Query(default=None),
    plate_type: str | None = Query(default=None),
    technology: str | None = Query(default=None),
    machine_id: int | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    current_only: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
) -> PlateDieRateListOut:
    items, total = service.list_rates(
        q=q, plate_type=plate_type, technology=technology, machine_id=machine_id,
        is_active=is_active, current_only=current_only, page=page, size=size,
    )
    return PlateDieRateListOut(items=items, total=total, page=page, size=size)


@router.get("/{id}", response_model=PlateDieRateOut,
            dependencies=[Depends(require_permission(MODULE, "read"))])
def get_rate(
    id: int,
    service: Annotated[PlateDieRateService, Depends(get_plate_die_rate_service)],
) -> PlateDieRateOut:
    try:
        return service.get_rate(id)
    except PlateDieRateNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/{id}/history", response_model=PlateDieRateListOut,
            dependencies=[Depends(require_permission(MODULE, "read"))])
def get_history(
    id: int,
    service: Annotated[PlateDieRateService, Depends(get_plate_die_rate_service)],
) -> PlateDieRateListOut:
    try:
        rows = service.history(id)
    except PlateDieRateNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return PlateDieRateListOut(items=rows, total=len(rows), page=1, size=len(rows) or 1)


@router.post("", response_model=PlateDieRateOut, status_code=status.HTTP_201_CREATED)
def create_rate(
    payload: PlateDieRateCreate,
    service: Annotated[PlateDieRateService, Depends(get_plate_die_rate_service)],
    actor: Annotated[CurrentUser, Depends(require_permission(MODULE, "create"))],
) -> PlateDieRateOut:
    try:
        return service.create_rate(payload.model_dump(), actor=actor)
    except PlateDieRateDuplicate as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except PlateDieRateValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.post("/{id}/version", response_model=PlateDieRateOut, status_code=status.HTTP_201_CREATED)
def create_version(
    id: int,
    payload: PlateDieRateVersion,
    service: Annotated[PlateDieRateService, Depends(get_plate_die_rate_service)],
    actor: Annotated[CurrentUser, Depends(require_permission(MODULE, "update"))],
) -> PlateDieRateOut:
    try:
        return service.create_version(id, payload.model_dump(), actor=actor)
    except PlateDieRateNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PlateDieRateValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.post("/{id}/clone", response_model=PlateDieRateOut, status_code=status.HTTP_201_CREATED)
def clone_rate(
    id: int,
    service: Annotated[PlateDieRateService, Depends(get_plate_die_rate_service)],
    actor: Annotated[CurrentUser, Depends(require_permission(MODULE, "create"))],
) -> PlateDieRateOut:
    try:
        return service.clone_rate(id, actor=actor)
    except PlateDieRateNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{id}/close", response_model=PlateDieRateOut)
def close_rate(
    id: int,
    payload: PlateDieRateClose,
    service: Annotated[PlateDieRateService, Depends(get_plate_die_rate_service)],
    actor: Annotated[CurrentUser, Depends(require_permission(MODULE, "update"))],
) -> PlateDieRateOut:
    try:
        return service.close_rate(rate_id=id, effective_to=payload.effective_to, actor=actor)
    except PlateDieRateNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PlateDieRateValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_rate(
    id: int,
    service: Annotated[PlateDieRateService, Depends(get_plate_die_rate_service)],
    actor: Annotated[CurrentUser, Depends(require_permission(MODULE, "delete"))],
) -> Response:
    try:
        service.delete_rate(rate_id=id, actor=actor)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except PlateDieRateNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PlateDieRateValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
