"""Machines router — spec-20/21.

Read-only surface: the admin/write CRUD has been removed. The pricing
engine and Báo giá consume machines through the list/detail endpoints below.
"""
from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..deps import get_machine_service, require_permission
from ..models.user import User
from ..schemas.machine import (
    MachineDetailOut,
    MachineListOut,
    MachineRow,
)
from ..services.machine_service import (
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
    machine_group: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    sort: str = Query(default="code"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> MachineListOut:
    rows, total = svc.list_machines(
        q=q, machine_type=machine_type, machine_group=machine_group,
        is_active=is_active, sort=sort, page=page, size=size,
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
