"""Lịch làm việc & Ngày lễ routes (module `nhan_su`, Pha 1 — nền dùng chung).

- Xem cấu hình tuần / ngày lễ / lịch tháng: gated `nhan_su.read`.
- Sửa cấu hình tuần + khai/sửa/xóa ngày đặc biệt: gated `nhan_su.update` (nhất quán "Khai ca").
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..deps import get_calendar_service, require_permission
from ..models.user import User
from ..schemas.calendar import (
    ConfigIn,
    ConfigOut,
    MonthCalendarOut,
    SpecialDayIn,
    SpecialDayOut,
    SpecialDaysOut,
)
from ..services.calendar_service import (
    STATUTORY_PAID_HOLIDAYS,
    CalendarError,
    CalendarNotFound,
    CalendarService,
    CalendarValidationError,
)

router = APIRouter(prefix="/api/calendar", tags=["calendar"])

MODULE = "nhan_su"

Service = Annotated[CalendarService, Depends(get_calendar_service)]


def _raise(exc: Exception) -> None:
    if isinstance(exc, CalendarNotFound):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, CalendarValidationError):
        raise HTTPException(status_code=400, detail=str(exc))
    raise exc


# --- cấu hình tuần làm việc --------------------------------------------------


@router.get("/config", response_model=ConfigOut)
def get_config(svc: Service, user: Annotated[User, Depends(require_permission(MODULE, "read"))]) -> ConfigOut:
    return ConfigOut.model_validate(svc.get_config())


@router.put("/config", response_model=ConfigOut)
def update_config(body: ConfigIn, svc: Service,
                  user: Annotated[User, Depends(require_permission(MODULE, "update"))]) -> ConfigOut:
    try:
        c = svc.update_config(actor=user, **body.model_dump(exclude_none=True))
    except CalendarError as exc:
        _raise(exc)
    return ConfigOut.model_validate(c)


# --- ngày đặc biệt (lễ / làm bù) --------------------------------------------


@router.get("/special-days", response_model=SpecialDaysOut)
def list_special_days(svc: Service,
                      user: Annotated[User, Depends(require_permission(MODULE, "read"))],
                      year: int = Query(..., ge=2000, le=2100)) -> SpecialDaysOut:
    items = svc.list_special_days(year)
    return SpecialDaysOut(
        year=year,
        items=[SpecialDayOut.model_validate(s) for s in items],
        paid_off_count=svc.paid_off_count(year),
        statutory_paid=STATUTORY_PAID_HOLIDAYS,
    )


@router.post("/special-days", response_model=SpecialDayOut, status_code=status.HTTP_201_CREATED)
def create_special_day(body: SpecialDayIn, svc: Service,
                       user: Annotated[User, Depends(require_permission(MODULE, "update"))]) -> SpecialDayOut:
    try:
        s = svc.create_special_day(actor=user, day=body.day, kind=body.kind, name=body.name,
                                   is_paid=body.is_paid, note=body.note)
    except CalendarError as exc:
        _raise(exc)
    return SpecialDayOut.model_validate(s)


@router.put("/special-days/{special_id}", response_model=SpecialDayOut)
def update_special_day(special_id: int, body: SpecialDayIn, svc: Service,
                       user: Annotated[User, Depends(require_permission(MODULE, "update"))]) -> SpecialDayOut:
    try:
        s = svc.update_special_day(actor=user, special_id=special_id, day=body.day, kind=body.kind,
                                   name=body.name, is_paid=body.is_paid, note=body.note)
    except CalendarError as exc:
        _raise(exc)
    return SpecialDayOut.model_validate(s)


@router.delete("/special-days/{special_id}", status_code=204)
def delete_special_day(special_id: int, svc: Service,
                       user: Annotated[User, Depends(require_permission(MODULE, "update"))]):
    try:
        svc.delete_special_day(actor=user, special_id=special_id)
    except CalendarError as exc:
        _raise(exc)


# --- lịch tháng (xem trước) --------------------------------------------------


@router.get("/month", response_model=MonthCalendarOut)
def month_calendar(svc: Service,
                   user: Annotated[User, Depends(require_permission(MODULE, "read"))],
                   year: int = Query(..., ge=2000, le=2100),
                   month: int = Query(..., ge=1, le=12)) -> MonthCalendarOut:
    try:
        data = svc.month_calendar(year, month)
    except CalendarError as exc:
        _raise(exc)
    return MonthCalendarOut(**data)
