"""Router — Quy tắc bình bài. `/api/quy-tac-binh-bai`.

Service factory định nghĩa LOCAL (dùng get_db + AuditLogRepository sẵn có) để KHÔNG phải
sửa deps.py lúc này (deps.py đang bị session khác cầm). Có thể dời vào deps.py ở pha wiring.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from ..deps import get_db, require_permission
from ..models.user import User
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.quy_tac_binh_bai_repo import QuyTacBinhBaiRepository
from ..schemas.quy_tac_binh_bai import (
    PreviewOut,
    PreviewRequest,
    RuleCreate,
    RuleDetailOut,
    RuleHeaderUpdate,
    RuleListOut,
    RuleRow,
    VersionCreate,
    VersionRow,
)
from ..services.quy_tac_binh_bai_service import (
    DuplicateError,
    NotFoundError,
    QuyTacBinhBaiService,
    ValidationError,
)

router = APIRouter(prefix="/api/quy-tac-binh-bai", tags=["quy-tac-binh-bai"])
MODULE = "dm_binh_bai"


def get_service(db: Annotated[Session, Depends(get_db)]) -> QuyTacBinhBaiService:
    return QuyTacBinhBaiService(QuyTacBinhBaiRepository(db), AuditLogRepository(db))


def _row(svc: QuyTacBinhBaiService, header) -> RuleRow:
    cur = svc.current_version(header.id)
    row = RuleRow.model_validate(header)
    row.current_version = VersionRow.model_validate(cur) if cur else None
    row.version_count = svc.version_count(header.id)
    return row


@router.get("", response_model=RuleListOut)
def list_items(
    svc: Annotated[QuyTacBinhBaiService, Depends(get_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
    q: str | None = Query(default=None),
    trang_thai: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
) -> RuleListOut:
    rows, total = svc.list_items(q=q, trang_thai=trang_thai, page=page, size=size)
    return RuleListOut(items=[_row(svc, h) for h in rows], total=total, page=page, size=size)


@router.post("/preview", response_model=PreviewOut)
def preview(
    payload: PreviewRequest,
    svc: Annotated[QuyTacBinhBaiService, Depends(get_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> PreviewOut:
    try:
        result = svc.preview(payload.config.model_dump(), payload.bench.model_dump())
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from None
    return PreviewOut(**result)


@router.get("/{rule_id}", response_model=RuleDetailOut)
def get_item(
    rule_id: int,
    svc: Annotated[QuyTacBinhBaiService, Depends(get_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> RuleDetailOut:
    try:
        header = svc.get_header(rule_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    base = _row(svc, header)
    detail = RuleDetailOut(**base.model_dump())
    detail.versions = [VersionRow.model_validate(v) for v in svc.versions_of(rule_id)]
    return detail


@router.get("/{rule_id}/versions", response_model=list[VersionRow])
def list_versions(
    rule_id: int,
    svc: Annotated[QuyTacBinhBaiService, Depends(get_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> list[VersionRow]:
    try:
        svc.get_header(rule_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return [VersionRow.model_validate(v) for v in svc.versions_of(rule_id)]


@router.post("", response_model=RuleRow, status_code=status.HTTP_201_CREATED)
def create_item(
    payload: RuleCreate,
    svc: Annotated[QuyTacBinhBaiService, Depends(get_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> RuleRow:
    try:
        header = svc.create_item(payload.model_dump(), actor=user)
    except DuplicateError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from None
    return _row(svc, header)


@router.put("/{rule_id}", response_model=RuleRow)
def update_item(
    rule_id: int,
    payload: RuleHeaderUpdate,
    svc: Annotated[QuyTacBinhBaiService, Depends(get_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> RuleRow:
    try:
        header = svc.update_header(rule_id, payload.model_dump(), actor=user)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from None
    return _row(svc, header)


@router.post("/{rule_id}/versions", response_model=VersionRow, status_code=status.HTTP_201_CREATED)
def create_version(
    rule_id: int,
    payload: VersionCreate,
    svc: Annotated[QuyTacBinhBaiService, Depends(get_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> VersionRow:
    try:
        nv = svc.create_version(rule_id, payload.model_dump(), actor=user)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from None
    return VersionRow.model_validate(nv)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_item(
    rule_id: int,
    svc: Annotated[QuyTacBinhBaiService, Depends(get_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "delete"))],
) -> Response:
    try:
        svc.delete_item(rule_id=rule_id, actor=user)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
