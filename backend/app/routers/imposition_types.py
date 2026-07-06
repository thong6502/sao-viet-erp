"""Imposition Type router — imposition/bình bài types master data (kiểu bình bài).
"""
from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ..deps import get_imposition_type_service, require_permission
from ..models.user import User
from ..schemas.imposition_type import (
    ImpositionPreviewOut,
    ImpositionPreviewRequest,
    ImpositionTypeCreate,
    ImpositionTypeListOut,
    ImpositionTypeRow,
    ImpositionTypeUpdate,
    ImpositionUsageEstimate,
    ImpositionUsageOut,
)
from ..services.imposition_type_service import (
    ImpositionTypeDuplicate,
    ImpositionTypeValidationError,
    ImpositionTypeNotFound,
    ImpositionTypeError,
    ImpositionTypeService,
)

router = APIRouter(prefix="/api/imposition-types", tags=["imposition-types"])
MODULE = "dm_dinh_muc"


@router.get("", response_model=ImpositionTypeListOut)
def list_items(
    svc: Annotated[ImpositionTypeService, Depends(get_imposition_type_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
    q: str | None = Query(default=None),
    code: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    # current_only=true → chỉ phiên bản đang hiệu lực của mỗi mã (cho dropdown Tính giá).
    current_only: bool = Query(default=False),
    sort: str = Query(default="priority"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
) -> ImpositionTypeListOut:
    rows, total = svc.list_items(
        q=q, code=code, is_active=is_active, current_only=current_only,
        sort=sort, page=page, size=size,
    )
    # "Đang dùng trong" = số tính giá (estimates) theo mã bình bài. Tính 1 lần, gán vào từng dòng.
    counts = svc.estimate_counts()
    items = []
    for r in rows:
        row = ImpositionTypeRow.model_validate(r)
        row.estimate_count = counts.get((r.code or "").upper(), 0)
        items.append(row)
    return ImpositionTypeListOut(items=items, total=total, page=page, size=size)


@router.post("/preview", response_model=ImpositionPreviewOut)
def preview(
    payload: ImpositionPreviewRequest,
    svc: Annotated[ImpositionTypeService, Depends(get_imposition_type_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> ImpositionPreviewOut:
    try:
        result = svc.preview(payload.model_dump())
    except ImpositionTypeValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    return ImpositionPreviewOut(**result)


@router.get("/{item_id}/usage", response_model=ImpositionUsageOut)
def usage(
    item_id: int,
    svc: Annotated[ImpositionTypeService, Depends(get_imposition_type_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> ImpositionUsageOut:
    try:
        data = svc.usage(item_id)
    except ImpositionTypeNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return ImpositionUsageOut(
        code=data["code"],
        estimate_count=data["estimate_count"],
        estimates=[ImpositionUsageEstimate.model_validate(e) for e in data["estimates"]],
    )


@router.get("/{item_id}", response_model=ImpositionTypeRow)
def get_item(
    item_id: int,
    svc: Annotated[ImpositionTypeService, Depends(get_imposition_type_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> ImpositionTypeRow:
    try:
        item = svc.get_item(item_id)
    except ImpositionTypeNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return ImpositionTypeRow.model_validate(item)


@router.post("", response_model=ImpositionTypeRow, status_code=status.HTTP_201_CREATED)
def create_item(
    payload: ImpositionTypeCreate,
    svc: Annotated[ImpositionTypeService, Depends(get_imposition_type_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> ImpositionTypeRow:
    try:
        item = svc.create_item(payload.model_dump(), actor=user)
    except ImpositionTypeDuplicate as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except ImpositionTypeValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    return ImpositionTypeRow.model_validate(item)


@router.put("/{item_id}", response_model=ImpositionTypeRow)
def update_item(
    item_id: int,
    payload: ImpositionTypeUpdate,
    svc: Annotated[ImpositionTypeService, Depends(get_imposition_type_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> ImpositionTypeRow:
    try:
        item = svc.update_item(item_id, payload.model_dump(), actor=user)
    except ImpositionTypeNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except ImpositionTypeDuplicate as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except ImpositionTypeValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    return ImpositionTypeRow.model_validate(item)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_item(
    item_id: int,
    svc: Annotated[ImpositionTypeService, Depends(get_imposition_type_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "delete"))],
) -> Response:
    try:
        svc.delete_item(item_id=item_id, actor=user)
    except ImpositionTypeNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except ImpositionTypeValidationError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except ImpositionTypeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
