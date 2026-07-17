"""Phiếu sản lượng công đoạn (Pha 5b) — API.

Quyền `san_luong`: tổ trưởng/Sản xuất GHI phiếu. Chốt sổ (materialize vào lương) thuộc quyền `luong`
(HCNS) — tách bạch ghi vs chốt. Bật 'tính khoán' cho LSX bù cần quyền `luong.update`.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..deps import get_authorization_service, get_production_output_service, require_permission
from ..models.user import User
from ..schemas.production_output import (
    DefectReportOut,
    DefectReportRow,
    OutputIn,
    OutputOut,
    OutputsOut,
    OutputUpdateIn,
)
from ..services.rbac_service import AuthorizationService
from ..services.production_output_service import (
    OutputError,
    OutputNotFound,
    OutputValidationError,
    ProductionOutputService,
)

router = APIRouter(prefix="/api/san-luong", tags=["san-luong"])
MODULE = "san_luong"

Svc = Annotated[ProductionOutputService, Depends(get_production_output_service)]
Authz = Annotated[AuthorizationService, Depends(get_authorization_service)]


def _raise(exc: OutputError):
    if isinstance(exc, OutputNotFound):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, OutputValidationError):
        raise HTTPException(status_code=400, detail=str(exc))
    raise exc


def _out(o) -> OutputOut:
    r = OutputOut.model_validate(o)
    r.amount = float(round(float(o.unit_price) * float(o.quantity)))
    r.net_amount = max(0.0, r.amount - float(getattr(o, "defect_deduction", 0) or 0))
    return r


@router.get("/outputs", response_model=OutputsOut)
def list_outputs(svc: Svc, user: Annotated[User, Depends(require_permission(MODULE, "read"))],
                 order_id: int = Query(...)) -> OutputsOut:
    return OutputsOut(items=[_out(o) for o in svc.list_by_order(order_id)])


@router.post("/outputs", response_model=OutputOut, status_code=status.HTTP_201_CREATED)
def create_output(body: OutputIn, svc: Svc, authz: Authz,
                  user: Annotated[User, Depends(require_permission(MODULE, "create"))]) -> OutputOut:
    can_set = authz.can(user, "luong", "update")   # bật 'tính khoán' LSX bù cần quyền lương
    try:
        o = svc.create(actor=user, can_set_tinh_khoan=can_set, **body.model_dump())
    except OutputError as exc:
        _raise(exc)
    return _out(o)


@router.put("/outputs/{output_id}", response_model=OutputOut)
def update_output(output_id: int, body: OutputUpdateIn, svc: Svc, authz: Authz,
                  user: Annotated[User, Depends(require_permission(MODULE, "update"))]) -> OutputOut:
    can_set = authz.can(user, "luong", "update")
    try:
        o = svc.update(output_id, can_set_tinh_khoan=can_set, **body.model_dump())
    except OutputError as exc:
        _raise(exc)
    return _out(o)


@router.delete("/outputs/{output_id}", status_code=204)
def delete_output(output_id: int, svc: Svc,
                  user: Annotated[User, Depends(require_permission(MODULE, "delete"))]):
    try:
        svc.delete(output_id)
    except OutputError as exc:
        _raise(exc)


@router.get("/defect-report", response_model=DefectReportOut)
def defect_report(svc: Svc, user: Annotated[User, Depends(require_permission(MODULE, "read"))],
                  year: int = Query(...), month: int = Query(...)) -> DefectReportOut:
    return DefectReportOut(items=[DefectReportRow(**r) for r in svc.defect_report(year, month)])
