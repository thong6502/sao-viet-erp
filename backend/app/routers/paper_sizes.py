"""Paper Size router — standard paper sizes master data (khổ giấy tiêu chuẩn).
"""
from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ..deps import get_paper_size_service, require_permission
from ..models.user import User
from ..schemas.paper_size import (
    PaperSizeCreate,
    PaperSizeListOut,
    PaperSizeRow,
    PaperSizeUpdate,
)
from ..services.paper_size_service import (
    PaperSizeDuplicate,
    PaperSizeValidationError,
    PaperSizeNotFound,
    PaperSizeError,
    PaperSizeService,
)

router = APIRouter(prefix="/api/paper-sizes", tags=["paper-sizes"])
MODULE = "dm_giay_vat_tu"


@router.get("", response_model=PaperSizeListOut)
def list_items(
    svc: Annotated[PaperSizeService, Depends(get_paper_size_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
    q: str | None = Query(default=None),
    size_type: str | None = Query(default=None),
    size_group: str | None = Query(default=None),
    machine_id: int | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    # current_only=true → chỉ phiên bản đang hiệu lực của mỗi mã (cho dropdown Tính giá).
    current_only: bool = Query(default=False),
    sort: str = Query(default="code"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
) -> PaperSizeListOut:
    rows, total = svc.list_items(
        q=q, size_type=size_type, size_group=size_group, machine_id=machine_id,
        is_active=is_active, current_only=current_only, sort=sort, page=page, size=size,
    )
    return PaperSizeListOut(
        items=[PaperSizeRow.model_validate(r) for r in rows],
        total=total,
        page=page,
        size=size,
    )


@router.get("/{item_id}", response_model=PaperSizeRow)
def get_item(
    item_id: int,
    svc: Annotated[PaperSizeService, Depends(get_paper_size_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> PaperSizeRow:
    try:
        item = svc.get_item(item_id)
    except PaperSizeNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return PaperSizeRow.model_validate(item)


@router.get("/{item_id}/history", response_model=PaperSizeListOut)
def get_history(
    item_id: int,
    svc: Annotated[PaperSizeService, Depends(get_paper_size_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> PaperSizeListOut:
    """Toàn bộ phiên bản của cùng mã khổ (lịch sử), mới nhất trước."""
    try:
        rows = svc.history(item_id)
    except PaperSizeNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return PaperSizeListOut(
        items=[PaperSizeRow.model_validate(r) for r in rows],
        total=len(rows), page=1, size=len(rows) or 1,
    )


@router.post("", response_model=PaperSizeRow, status_code=status.HTTP_201_CREATED)
def create_item(
    payload: PaperSizeCreate,
    svc: Annotated[PaperSizeService, Depends(get_paper_size_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> PaperSizeRow:
    try:
        item = svc.create_item(payload.model_dump(), actor=user)
    except PaperSizeDuplicate as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except PaperSizeValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    return PaperSizeRow.model_validate(item)


@router.put("/{item_id}", response_model=PaperSizeRow)
def update_item(
    item_id: int,
    payload: PaperSizeUpdate,
    svc: Annotated[PaperSizeService, Depends(get_paper_size_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> PaperSizeRow:
    try:
        item = svc.update_item(item_id, payload.model_dump(), actor=user)
    except PaperSizeNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except PaperSizeDuplicate as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except PaperSizeValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    return PaperSizeRow.model_validate(item)


@router.post("/{item_id}/version", response_model=PaperSizeRow, status_code=status.HTTP_201_CREATED)
def create_version(
    item_id: int,
    payload: PaperSizeUpdate,
    svc: Annotated[PaperSizeService, Depends(get_paper_size_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> PaperSizeRow:
    """Tạo phiên bản mới thủ công (đóng băng bản cũ)."""
    try:
        item = svc.create_version_item(item_id, payload.model_dump(), actor=user)
    except PaperSizeNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except PaperSizeDuplicate as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except PaperSizeValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from None
    return PaperSizeRow.model_validate(item)


@router.post("/{item_id}/clone", response_model=PaperSizeRow, status_code=status.HTTP_201_CREATED)
def clone_item(
    item_id: int,
    svc: Annotated[PaperSizeService, Depends(get_paper_size_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> PaperSizeRow:
    """Sao chép thành khổ mới (mã mới)."""
    try:
        item = svc.clone_item(item_id, actor=user)
    except PaperSizeNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except PaperSizeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    return PaperSizeRow.model_validate(item)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_item(
    item_id: int,
    svc: Annotated[PaperSizeService, Depends(get_paper_size_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "delete"))],
) -> Response:
    try:
        svc.delete_item(item_id=item_id, actor=user)
    except PaperSizeNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except PaperSizeValidationError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except PaperSizeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
