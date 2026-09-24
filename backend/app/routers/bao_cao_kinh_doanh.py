"""Báo cáo kinh doanh theo khách hàng (24/09/2026) — xem trên màn + xuất Excel.

Gác bằng ô quyền RIÊNG `bao_cao_kinh_doanh` (mục menu riêng trong nhóm Kinh doanh): Xem = xem báo
cáo + xuất Excel. Phạm vi dữ liệu lấy từ CHÍNH ô này (own / department / all theo người bán).
"""
from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ..deps import (
    get_accounting_repository,
    get_authorization_service,
    get_order_repository,
    require_permission,
)
from ..models.user import User
from ..repositories.accounting_repo import AccountingRepository
from ..repositories.order_repo import OrderRepository
from ..services import bao_cao_kinh_doanh, bao_cao_kinh_doanh_excel
from ..services.rbac_service import AuthorizationService

router = APIRouter(prefix="/api/bao-cao-kinh-doanh", tags=["bao-cao-kinh-doanh"])
MODULE = "bao_cao_kinh_doanh"

Orders = Annotated[OrderRepository, Depends(get_order_repository)]
Accounting = Annotated[AccountingRepository, Depends(get_accounting_repository)]
Authz = Annotated[AuthorizationService, Depends(get_authorization_service)]
Nguoi = Annotated[User, Depends(require_permission(MODULE, "read"))]


def _lap(orders, accounting, authz, user, tu_ngay: date, den_ngay: date,
         customer_id: int | None) -> dict:
    if tu_ngay > den_ngay:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Từ ngày phải trước hoặc bằng đến ngày.")
    if (den_ngay - tu_ngay).days > 366 * 3:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Khoảng ngày tối đa 3 năm.")
    return bao_cao_kinh_doanh.lap_bao_cao(
        orders, accounting, tu_ngay=tu_ngay, den_ngay=den_ngay,
        scope=authz.scope_for(user, MODULE) or "own", actor=user, customer_id=customer_id,
    )


@router.get("")
def xem_bao_cao(
    orders: Orders, accounting: Accounting, authz: Authz, user: Nguoi,
    tu_ngay: date = Query(...),
    den_ngay: date = Query(...),
    customer_id: int | None = Query(default=None),
) -> dict:
    return _lap(orders, accounting, authz, user, tu_ngay, den_ngay, customer_id)


@router.get("/export.xlsx")
def xuat_excel(
    orders: Orders, accounting: Accounting, authz: Authz, user: Nguoi,
    tu_ngay: date = Query(...),
    den_ngay: date = Query(...),
    customer_id: int | None = Query(default=None),
) -> Response:
    bc = _lap(orders, accounting, authz, user, tu_ngay, den_ngay, customer_id)
    ma = None
    if customer_id is not None and bc["khach"]:
        ma = bc["khach"][0]["ma"] or bc["khach"][0]["ten"]
    return Response(
        content=bao_cao_kinh_doanh_excel.xuat_xlsx(bc),
        media_type=bao_cao_kinh_doanh_excel.MEDIA_XLSX,
        headers={"Content-Disposition":
                 f'attachment; filename="{bao_cao_kinh_doanh_excel.ten_file(bc, ma_khach=ma)}"'},
    )
