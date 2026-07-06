"""FastAPI router for Norms configuration API (danh mục #7 — Định mức & Bù hao)."""
from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status, Response
from ..deps import CurrentUser, get_norm_service, require_permission
from ..schemas.norm import (
    NormCreate, NormClose, NormDuplicate, NormOut, NormListOut,
    NormTestInput, NormTestOutput, NormUsageOut, NormUsageEstimate,
    NormConflictsOut,
)
from ..models.norm import GROUP_TO_KEY
from ..services.norm_service import NormService, NormValidationError, NormNotFoundError

router = APIRouter(prefix="/api/norms", tags=["norms"])


@router.get(
    "",
    response_model=NormListOut,
    dependencies=[Depends(require_permission("dm_dinh_muc", "read"))],
)
def list_norms(
    service: Annotated[NormService, Depends(get_norm_service)],
    q: str | None = None,
    norm_key: str | None = None,
    waste_group: str | None = None,
    product_type: str | None = None,
    machine_id: int | None = None,
    operation_id: int | None = None,
    only_current: bool = False,
    page: int = 1,
    size: int = 50,
) -> NormListOut:
    # Lọc theo nhóm (waste_group) quy về norm_key nội bộ.
    if not norm_key and waste_group:
        norm_key = GROUP_TO_KEY.get(waste_group, waste_group)
    items, total = service.list_norms(
        q=q,
        norm_key=norm_key,
        product_type=product_type,
        machine_id=machine_id,
        operation_id=operation_id,
        only_current=only_current,
        page=page,
        size=size,
    )
    # "Đang dùng trong" — đếm 1 lượt, gán vào từng dòng.
    counts = service.estimate_counts()
    out_items = []
    for it in items:
        row = NormOut.model_validate(it)
        row.estimate_count = counts.get(it.id, 0)
        out_items.append(row)
    return NormListOut(items=out_items, total=total, page=page, size=size)


@router.get(
    "/conflicts",
    response_model=NormConflictsOut,
    dependencies=[Depends(require_permission("dm_dinh_muc", "read"))],
)
def norm_conflicts(
    service: Annotated[NormService, Depends(get_norm_service)],
) -> NormConflictsOut:
    data = service.detect_conflicts()
    return NormConflictsOut(conflicts=data["conflicts"], labels=data["labels"])


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
            waste_group=payload.waste_group,
            calculation_method=payload.calculation_method,
            value=payload.value,
            code=payload.code,
            name=payload.name,
            product_type=payload.product_type,
            machine_id=payload.machine_id,
            operation_id=payload.operation_id,
            operation_key=payload.operation_key,
            applicable_product_types=payload.applicable_product_types,
            applicable_machine_ids=payload.applicable_machine_ids,
            qty_min=payload.qty_min,
            qty_max=payload.qty_max,
            context=payload.context,
            setup_waste_qty=payload.setup_waste_qty,
            setup_waste_per_color=payload.setup_waste_per_color,
            setup_waste_per_side=payload.setup_waste_per_side,
            min_waste_qty=payload.min_waste_qty,
            max_waste_qty=payload.max_waste_qty,
            paper_add_to_purchase=payload.paper_add_to_purchase,
            priority=payload.priority,
            effective_from=payload.effective_from,
            note=payload.note,
            actor=actor,
        )
    except NormValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.post("/test", response_model=NormTestOutput)
def test_norm(
    payload: NormTestInput,
    service: Annotated[NormService, Depends(get_norm_service)],
    actor: Annotated[CurrentUser, Depends(require_permission("dm_dinh_muc", "read"))],
) -> NormTestOutput:
    return NormTestOutput(**service.simulate(payload))


@router.get("/{id}", response_model=NormOut)
def get_norm(
    id: int,
    service: Annotated[NormService, Depends(get_norm_service)],
    actor: Annotated[CurrentUser, Depends(require_permission("dm_dinh_muc", "read"))],
) -> NormOut:
    try:
        return service.get_norm_by_id(id)
    except NormNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/{id}/usage", response_model=NormUsageOut)
def norm_usage(
    id: int,
    service: Annotated[NormService, Depends(get_norm_service)],
    actor: Annotated[CurrentUser, Depends(require_permission("dm_dinh_muc", "read"))],
) -> NormUsageOut:
    try:
        data = service.usage(id)
    except NormNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return NormUsageOut(
        norm_id=data["norm_id"],
        code=data["code"],
        estimate_count=data["estimate_count"],
        estimates=[NormUsageEstimate.model_validate(e) for e in data["estimates"]],
    )


@router.get("/{id}/history", response_model=NormListOut)
def norm_history(
    id: int,
    service: Annotated[NormService, Depends(get_norm_service)],
    actor: Annotated[CurrentUser, Depends(require_permission("dm_dinh_muc", "read"))],
) -> NormListOut:
    try:
        items = service.get_history(id)
    except NormNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    counts = service.estimate_counts()
    out_items = []
    for it in items:
        row = NormOut.model_validate(it)
        row.estimate_count = counts.get(it.id, 0)
        out_items.append(row)
    return NormListOut(items=out_items, total=len(out_items), page=1, size=len(out_items) or 1)


@router.post("/{id}/duplicate", response_model=NormOut, status_code=status.HTTP_201_CREATED)
def duplicate_norm(
    id: int,
    payload: NormDuplicate,
    service: Annotated[NormService, Depends(get_norm_service)],
    actor: Annotated[CurrentUser, Depends(require_permission("dm_dinh_muc", "create"))],
) -> NormOut:
    try:
        return service.duplicate_norm(
            norm_id=id, effective_from=payload.effective_from, code=payload.code, actor=actor
        )
    except NormNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
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
