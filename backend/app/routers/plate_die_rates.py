"""FastAPI router for Plate/Die rates API — Đơn giá kẽm & khuôn (catalog #5).

Read-only: the admin/write surface was removed. GET endpoints remain so the
pricing engine and read-only consumers keep working.
"""
from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, status
from ..deps import get_plate_die_rate_service, require_permission
from ..schemas.plate_die_rate import (
    PlateDieRateOut,
    PlateDieRateListOut,
    PlateDieRateUsageOut,
)
from ..services.plate_die_rate_service import (
    PlateDieRateService,
    PlateDieRateNotFoundError,
)

router = APIRouter(prefix="/api/plate-die-rates", tags=["plate-die-rates"])
# Quyền chi tiết: catalog Bảng giá kẽm & khuôn có module quyền riêng (RBAC feature #6).
MODULE = "dm_gia_khuon_ban"

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
    # "Đang dùng trong": kẽm = số phiếu, khuôn = số công đoạn. Tính 1 lần cho cả trang.
    est_counts, op_counts = service.usage_counts([r.id for r in items])
    rows = []
    for r in items:
        row = PlateDieRateOut.model_validate(r)
        row.used_in_estimates = est_counts.get(r.id, 0)
        row.used_in_operations = op_counts.get(r.id, 0)
        rows.append(row)
    return PlateDieRateListOut(items=rows, total=total, page=page, size=size)


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


@router.get("/{id}/usage", response_model=PlateDieRateUsageOut,
            dependencies=[Depends(require_permission(MODULE, "read"))])
def get_usage(
    id: int,
    service: Annotated[PlateDieRateService, Depends(get_plate_die_rate_service)],
) -> PlateDieRateUsageOut:
    """Nơi đang dùng bảng giá này — kẽm → phiếu tính giá; khuôn → công đoạn."""
    try:
        return PlateDieRateUsageOut(**service.usage(id))
    except PlateDieRateNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
