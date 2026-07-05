"""Machines router — spec-20/21.
"""
from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ..deps import get_machine_service, require_permission
from ..models.user import User
from ..schemas.machine import (
    MachineRateCreate,
    MachineRateOut,
    MachineCreate,
    MachineDetailOut,
    MachineListOut,
    MachineRow,
    MachineUpdate,
)
from ..services.machine_service import (
    MachineDuplicate,
    MachineValidationError,
    MachineNotFound,
    MachineService,
)

router = APIRouter(prefix="/api/machines", tags=["machines"])
MODULE = "dm_thiet_bi"

@router.get("", response_model=MachineListOut)
def list_machines(
    svc: Annotated[MachineService, Depends(get_machine_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
    q: str | None = Query(default=None),
    machine_type: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    sort: str = Query(default="code"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> MachineListOut:
    rows, total = svc.list_machines(
        q=q, machine_type=machine_type, is_active=is_active, sort=sort, page=page, size=size
    )
    return MachineListOut(
        items=[MachineRow.model_validate(r) for r in rows],
        total=total,
        page=page,
        size=size,
    )

@router.get("/{machine_id}", response_model=MachineDetailOut)
def get_machine(
    machine_id: int,
    svc: Annotated[MachineService, Depends(get_machine_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> MachineDetailOut:
    try:
        machine = svc.get_machine(machine_id)
    except MachineNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return MachineDetailOut.model_validate(machine)

@router.post("", response_model=MachineDetailOut, status_code=status.HTTP_201_CREATED)
def create_machine(
    payload: MachineCreate,
    svc: Annotated[MachineService, Depends(get_machine_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> MachineDetailOut:
    try:
        machine = svc.create_machine(
            name=payload.name,
            machine_type=payload.machine_type,
            process_type=payload.process_type,
            speed=payload.speed,
            speed_unit=payload.speed_unit,
            max_width_cm=payload.max_width_cm,
            max_height_cm=payload.max_height_cm,
            min_width_cm=payload.min_width_cm,
            min_height_cm=payload.min_height_cm,
            setup_time_mins=payload.setup_time_mins,
            changeover_time_mins=payload.changeover_time_mins,
            setup_waste_sheets=payload.setup_waste_sheets,
            num_ink_units=payload.num_ink_units,
            supports_perfecting=payload.supports_perfecting,
            supported_materials=payload.supported_materials,
            is_active=payload.is_active,
            actor=user,
        )
    except MachineDuplicate as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except MachineValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    return MachineDetailOut.model_validate(machine)

@router.put("/{machine_id}", response_model=MachineDetailOut)
def update_machine(
    machine_id: int,
    payload: MachineUpdate,
    svc: Annotated[MachineService, Depends(get_machine_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> MachineDetailOut:
    try:
        machine = svc.update_machine(
            machine_id=machine_id,
            name=payload.name,
            machine_type=payload.machine_type,
            process_type=payload.process_type,
            speed=payload.speed,
            speed_unit=payload.speed_unit,
            max_width_cm=payload.max_width_cm,
            max_height_cm=payload.max_height_cm,
            min_width_cm=payload.min_width_cm,
            min_height_cm=payload.min_height_cm,
            setup_time_mins=payload.setup_time_mins,
            changeover_time_mins=payload.changeover_time_mins,
            setup_waste_sheets=payload.setup_waste_sheets,
            num_ink_units=payload.num_ink_units,
            supports_perfecting=payload.supports_perfecting,
            supported_materials=payload.supported_materials,
            is_active=payload.is_active,
            actor=user,
        )
    except MachineNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except MachineDuplicate as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except MachineValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    return MachineDetailOut.model_validate(machine)

@router.delete("/{machine_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_machine(
    machine_id: int,
    svc: Annotated[MachineService, Depends(get_machine_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "delete"))],
) -> Response:
    try:
        svc.delete_machine(machine_id=machine_id, actor=user)
    except MachineNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except MachineValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.post("/{machine_id}/rates", response_model=MachineRateOut, status_code=status.HTTP_201_CREATED)
def add_machine_rate(
    machine_id: int,
    payload: MachineRateCreate,
    svc: Annotated[MachineService, Depends(get_machine_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "manage_price"))],
) -> MachineRateOut:
    try:
        rate = svc.add_machine_rate(
            machine_id=machine_id,
            hourly_rate=payload.hourly_rate,
            min_charge=payload.min_charge,
            min_run_time_mins=payload.min_run_time_mins,
            effective_from=payload.effective_from,
            actor=user,
        )
    except MachineNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except MachineValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    return MachineRateOut.model_validate(rate)
