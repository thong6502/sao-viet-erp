"""Thu mua API — suppliers + purchase requests."""
from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)

from ..deps import CurrentUser, get_purchase_service, require_any_permission, require_permission
from ..models.user import User
from ..realtime import hub
from ..schemas.purchase import (
    DepartmentPurchaseRequestIn,
    DepartmentPurchaseRequestListOut,
    DepartmentPurchaseRequestOut,
    PurchaseContractIn,
    PurchaseDeliveryIn,
    PurchaseInvoiceAssignIn,
    PurchaseNotifySummaryOut,
    PurchaseRequestBatchIn,
    PurchaseRequestIn,
    PurchaseRequestListOut,
    PurchaseRequestOut,
    ReasonIn,
    ReceivedLinesIn,
    SupplierCreditOut,
    SupplierIn,
    SoGiaOut,
    SupplierItemCatalogOut,
    SupplierItemImportOut,
    SupplierListOut,
    SupplierRow,
)
from ..services.purchase_service import (
    DEPARTMENT_REQUEST_READER_MODULES,
    PurchaseConflict,
    # Bắt LỚP CHA `PurchaseError` ở mọi route: trước đây 14/18 chỗ chỉ liệt kê 3 loại lỗi và bỏ sót
    # `PurchaseForbidden`, nên mọi lỗi QUYỀN rơi ra ngoài thành **500** thay vì 403 — người dùng
    # thấy "lỗi hệ thống" trong khi thật ra là "bạn không được phép". `_map_error` vốn đã phân loại
    # đủ cả bốn, thiếu chỉ là ở chỗ `except`.
    PurchaseError,
    PurchaseForbidden,
    PurchaseNotFound,
    PurchaseService,
    PurchaseValidationError,
)

router = APIRouter(tags=["purchases"])
MODULE = "thu_mua"
# Cổng quyền đọc YCMH dựng từ CHÍNH danh sách mà service dùng để quyết định có co danh sách về
# phòng ban hay không — thêm/bớt một vai chỉ phải sửa một chỗ, không còn cảnh cấp quyền vào được
# màn nhưng lại bị lọc ra rỗng. (Kế toán truy vết YCMH nguồn khi duyệt PMH / lập Phiếu chi: SEAM-25.)
DEPARTMENT_REQUEST_READERS = tuple(
    (module, "read") for module in DEPARTMENT_REQUEST_READER_MODULES
)


def _notify_purchase_changed(code: str | None = None, *, event_type: str = "purchase_changed", **extra) -> None:
    """Tín hiệu nhẹ cho các màn Thu mua/Kế toán tự refetch qua SSE."""
    hub.broadcast({"type": event_type, "code": code, **extra})


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PurchaseNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, PurchaseValidationError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if isinstance(exc, PurchaseConflict):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, PurchaseForbidden):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/api/department-purchase-requests", response_model=DepartmentPurchaseRequestListOut)
def list_department_purchase_requests(
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: CurrentUser,
    q: str | None = Query(default=None),
    status_: str | None = Query(default=None, alias="status"),
    source_type: str | None = Query(default=None),
    sort: str = Query(default="-created_at"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> DepartmentPurchaseRequestListOut:
    rows, total = svc.list_department_requests(
        actor=user, q=q, status=status_, source_type=source_type, sort=sort, page=page, size=size
    )
    return DepartmentPurchaseRequestListOut(items=rows, total=total, page=page, size=size)


@router.get("/api/department-purchase-requests/can-create")
def can_create_department_purchase_request(
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: CurrentUser,
) -> dict[str, bool]:
    return {"can_create": svc.can_create_department_request(user)}


@router.get("/api/department-purchase-requests/{request_id}", response_model=DepartmentPurchaseRequestOut)
def get_department_purchase_request(
    request_id: int,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: CurrentUser,
) -> DepartmentPurchaseRequestOut:
    try:
        return DepartmentPurchaseRequestOut(**svc.get_department_request(request_id, actor=user))
    except PurchaseError as exc:
        raise _map_error(exc) from None


@router.post(
    "/api/department-purchase-requests",
    response_model=DepartmentPurchaseRequestOut,
    status_code=status.HTTP_201_CREATED,
)
def create_department_purchase_request(
    payload: DepartmentPurchaseRequestIn,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: CurrentUser,
) -> DepartmentPurchaseRequestOut:
    try:
        row = svc.create_department_request(actor=user, **payload.model_dump())
    except PurchaseError as exc:
        raise _map_error(exc) from None
    _notify_purchase_changed(row.get("code"))
    return DepartmentPurchaseRequestOut(**row)


@router.put("/api/department-purchase-requests/{request_id}", response_model=DepartmentPurchaseRequestOut)
def update_department_purchase_request(
    request_id: int,
    payload: DepartmentPurchaseRequestIn,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: CurrentUser,
) -> DepartmentPurchaseRequestOut:
    try:
        row = svc.update_department_request(request_id, actor=user, **payload.model_dump())
    except PurchaseError as exc:
        raise _map_error(exc) from None
    _notify_purchase_changed(row.get("code"))
    return DepartmentPurchaseRequestOut(**row)


@router.post("/api/department-purchase-requests/{request_id}/cancel", response_model=DepartmentPurchaseRequestOut)
def cancel_department_purchase_request(
    request_id: int,
    payload: ReasonIn,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: CurrentUser,
) -> DepartmentPurchaseRequestOut:
    try:
        row = svc.cancel_department_request(request_id, reason=payload.reason, actor=user)
    except PurchaseError as exc:
        raise _map_error(exc) from None
    _notify_purchase_changed(row.get("code"))
    return DepartmentPurchaseRequestOut(**row)


@router.get("/api/suppliers", response_model=SupplierListOut)
def list_suppliers(
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    _: Annotated[
        User,
        Depends(require_any_permission((MODULE, "read"), ("ke_toan", "read"))),
    ],
    q: str | None = Query(default=None),
    status_: str | None = Query(default=None, alias="status"),
    supplier_group: str | None = Query(default=None),
    sort: str = Query(default="name"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> SupplierListOut:
    rows, total = svc.list_suppliers(
        q=q, status=status_, supplier_group=supplier_group, sort=sort, page=page, size=size
    )
    return SupplierListOut(
        items=[SupplierRow.model_validate(row) for row in rows],
        total=total,
        page=page,
        size=size,
    )


@router.get("/api/supplier-items/catalog", response_model=SupplierItemCatalogOut)
def supplier_item_catalog(
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    _: CurrentUser,
) -> SupplierItemCatalogOut:
    return SupplierItemCatalogOut(items=svc.list_supplier_item_catalog())


@router.get("/api/supplier-items/so-gia", response_model=SoGiaOut)
def so_gia_ncc(
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    _: CurrentUser,
    hang_loai: str = Query(..., pattern="^(giay|vat_tu)$"),
    hang_id: int = Query(..., gt=0),
) -> SoGiaOut:
    """Các NCC bán mặt hàng này, GIÁ QUY VỀ ĐƠN VỊ GỐC để so ngang.

    "1.020.000 đ/ram" và "24.500 đ/kg" không so trực tiếp được — quy về cùng đơn vị mới biết ai
    rẻ. Dòng không quy đổi được vẫn hiện (NCC đó có bán thật) nhưng xếp cuối kèm lý do.
    """
    try:
        return SoGiaOut(**svc.so_gia_ncc(hang_loai, hang_id))
    except VatLieuKhoError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None

def _xlsx_response(data: bytes, filename: str) -> Response:
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# Mẫu + xuất dùng quyền ĐỌC, nhập dùng quyền SỬA: hai file kia chỉ bày lại đúng thứ người ta đã
# nhìn thấy trên màn, còn nhập là thay bảng giá của NCC.
@router.get("/api/suppliers/items/template.xlsx")
def supplier_items_template(
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> Response:
    return _xlsx_response(svc.mau_vat_tu_xlsx(), "mau-vat-tu-nha-cung-cap.xlsx")


@router.get("/api/suppliers/{supplier_id}/items/export.xlsx")
def supplier_items_export(
    supplier_id: int,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> Response:
    try:
        data, filename = svc.xuat_vat_tu_xlsx(supplier_id)
    except PurchaseError as exc:
        raise _map_error(exc) from None
    return _xlsx_response(data, filename)


@router.post("/api/suppliers/items/import", response_model=SupplierItemImportOut)
async def supplier_items_import(
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "update"))],
    file: UploadFile = File(...),
) -> SupplierItemImportOut:
    """ĐỌC file .xlsx → trả danh sách mặt hàng + lỗi từng dòng. KHÔNG ghi DB.

    Không nhận `supplier_id`: bảng giá được lưu bằng cú `PUT /api/suppliers/{id}` của form, nên
    ghi ở đây là đẻ đường ghi thứ hai — và NCC chưa lưu (đang tạo mới) thì cũng chưa có id để mà
    nhập vào."""
    data = await file.read()
    if not data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="File rỗng."
        )
    try:
        ket_qua = svc.doc_vat_tu_xlsx(data)
    except PurchaseError as exc:
        raise _map_error(exc) from None
    return SupplierItemImportOut(**ket_qua)

@router.post("/api/suppliers", response_model=SupplierRow, status_code=status.HTTP_201_CREATED)
def create_supplier(
    payload: SupplierIn,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> SupplierRow:
    try:
        row = svc.create_supplier(actor=user, **payload.model_dump())
    except PurchaseError as exc:
        raise _map_error(exc) from None
    _notify_purchase_changed()
    return SupplierRow.model_validate(row)


@router.put("/api/suppliers/{supplier_id}", response_model=SupplierRow)
def update_supplier(
    supplier_id: int,
    payload: SupplierIn,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> SupplierRow:
    try:
        row = svc.update_supplier(supplier_id, actor=user, **payload.model_dump())
    except PurchaseError as exc:
        raise _map_error(exc) from None
    _notify_purchase_changed()
    return SupplierRow.model_validate(row)


@router.patch("/api/suppliers/{supplier_id}/toggle-active", response_model=SupplierRow)
def toggle_supplier(
    supplier_id: int,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> SupplierRow:
    try:
        row = svc.toggle_supplier_active(supplier_id, actor=user)
    except PurchaseError as exc:
        raise _map_error(exc) from None
    _notify_purchase_changed()
    return SupplierRow.model_validate(row)


@router.get("/api/purchase-requests", response_model=PurchaseRequestListOut)
def list_purchase_requests(
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[
        User,
        Depends(require_any_permission((MODULE, "read"), ("ke_toan", "read"))),
    ],
    q: str | None = Query(default=None),
    status_: str | None = Query(default=None, alias="status"),
    supplier_id: int | None = Query(default=None),
    created_from: date | None = Query(default=None),
    created_to: date | None = Query(default=None),
    needed_from: date | None = Query(default=None),
    needed_to: date | None = Query(default=None),
    expected_receipt_from: date | None = Query(default=None),
    expected_receipt_to: date | None = Query(default=None),
    deposit_status: str | None = Query(default=None),
    sort: str = Query(default="-created_at"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> PurchaseRequestListOut:
    rows, total = svc.list_requests(
        q=q,
        status=status_,
        supplier_id=supplier_id,
        created_from=created_from,
        created_to=created_to,
        needed_from=needed_from,
        needed_to=needed_to,
        expected_receipt_from=expected_receipt_from,
        expected_receipt_to=expected_receipt_to,
        deposit_status=deposit_status,
        sort=sort,
        page=page,
        size=size,
        actor=user,
    )
    return PurchaseRequestListOut(items=rows, total=total, page=page, size=size)


@router.get("/api/purchase-requests/notify-summary", response_model=PurchaseNotifySummaryOut)
def purchase_notify_summary(
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> PurchaseNotifySummaryOut:
    """Badge Thu mua trên sidebar — ba con số việc-phải-làm, đã lọc theo phạm vi người gọi.

    ⚠️ PHẢI khai TRƯỚC `/{request_id}`: FastAPI khớp route theo thứ tự đăng ký, để sau thì
    "notify-summary" rơi vào `{request_id}` và chết 422 vì không ép được về int.

    Rẻ: hai con số YCMH/PMH là COUNT ở DB. Con số công nợ chỉ chạy cho người có `ke_toan:read`
    (xem `notify_summary`)."""
    return PurchaseNotifySummaryOut(**svc.notify_summary(actor=user))


@router.get("/api/purchase-requests/{request_id}", response_model=PurchaseRequestOut)
def get_purchase_request(
    request_id: int,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[
        User,
        Depends(require_any_permission((MODULE, "read"), ("ke_toan", "read"))),
    ],
) -> PurchaseRequestOut:
    try:
        # Truyền `actor`: lọc ở danh sách mà để chi tiết mở là biết id đọc được hết.
        return PurchaseRequestOut(**svc.get_request(request_id, actor=user))
    except PurchaseError as exc:
        raise _map_error(exc) from None


@router.post("/api/purchase-requests", response_model=PurchaseRequestOut, status_code=status.HTTP_201_CREATED)
def create_purchase_request(
    payload: PurchaseRequestIn,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> PurchaseRequestOut:
    try:
        row = svc.create_request(actor=user, **payload.model_dump())
    except PurchaseError as exc:
        raise _map_error(exc) from None
    _notify_purchase_changed(row.get("code"), event_type="purchase_pending_approval")
    return PurchaseRequestOut(**row)


@router.post("/api/purchase-requests/batch", response_model=PurchaseRequestListOut,
             status_code=status.HTTP_201_CREATED)
def create_purchase_requests_batch(
    payload: PurchaseRequestBatchIn,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "create"))],
) -> PurchaseRequestListOut:
    """Yêu cầu chứa hàng của nhiều NCC → tách thành nhiều phiếu, mỗi NCC một phiếu, TRONG MỘT LẦN.

    Không để giao diện gọi endpoint tạo phiếu nhiều lần: lần đầu là yêu cầu nguồn bị giữ chỗ, lần
    sau bị chặn ngay. Và hỏng thì phải hỏng cả mẻ, không để lại phiếu mồ côi đang giữ chỗ."""
    try:
        rows = svc.create_requests_batch(actor=user, **payload.model_dump())
    except PurchaseError as exc:
        raise _map_error(exc) from None
    _notify_purchase_changed(event_type="purchase_pending_approval")
    return PurchaseRequestListOut(items=[PurchaseRequestOut(**row) for row in rows],
                                  total=len(rows), page=1, size=len(rows) or 1)


@router.put("/api/purchase-requests/{request_id}", response_model=PurchaseRequestOut)
def update_purchase_request(
    request_id: int,
    payload: PurchaseRequestIn,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> PurchaseRequestOut:
    try:
        row = svc.update_request(request_id, actor=user, **payload.model_dump())
    except PurchaseError as exc:
        raise _map_error(exc) from None
    _notify_purchase_changed(row.get("code"))
    return PurchaseRequestOut(**row)


@router.delete("/api/purchase-requests/{request_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_purchase_request(
    request_id: int,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "delete"))],
) -> Response:
    try:
        svc.delete_request(request_id, actor=user)
    except PurchaseError as exc:
        raise _map_error(exc) from None
    _notify_purchase_changed()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/api/purchase-requests/{request_id}/submit", response_model=PurchaseRequestOut)
def submit_purchase_request(
    request_id: int,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> PurchaseRequestOut:
    try:
        row = svc.submit(request_id, actor=user)
    except PurchaseError as exc:
        raise _map_error(exc) from None
    _notify_purchase_changed(row.get("code"), event_type="purchase_pending_approval")
    return PurchaseRequestOut(**row)


@router.post("/api/purchase-requests/{request_id}/approve", response_model=PurchaseRequestOut)
def approve_purchase_request(
    request_id: int,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "approve"))],
) -> PurchaseRequestOut:
    try:
        row = svc.approve(request_id, actor=user)
    except PurchaseError as exc:
        raise _map_error(exc) from None
    _notify_purchase_changed(row.get("code"), event_type="purchase_decision", decision="approved")
    return PurchaseRequestOut(**row)


@router.post("/api/purchase-requests/{request_id}/reject", response_model=PurchaseRequestOut)
def reject_purchase_request(
    request_id: int,
    payload: ReasonIn,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "approve"))],
) -> PurchaseRequestOut:
    try:
        row = svc.reject(request_id, reason=payload.reason, actor=user)
    except PurchaseError as exc:
        raise _map_error(exc) from None
    _notify_purchase_changed(row.get("code"), event_type="purchase_decision", decision="rejected")
    return PurchaseRequestOut(**row)


@router.post("/api/purchase-requests/{request_id}/mark-purchased", response_model=PurchaseRequestOut)
def mark_purchase_request_purchased(
    request_id: int,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> PurchaseRequestOut:
    try:
        row = svc.mark_purchased(request_id, actor=user)
    except PurchaseError as exc:
        raise _map_error(exc) from None
    _notify_purchase_changed(row.get("code"))
    return PurchaseRequestOut(**row)


@router.post("/api/purchase-requests/{request_id}/mark-received", response_model=PurchaseRequestOut)
def mark_purchase_request_received(
    request_id: int,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
    payload: ReceivedLinesIn | None = None,
) -> PurchaseRequestOut:
    # Body TUỲ CHỌN: gọi không kèm gì = nhận đủ như đặt, y hệt trước 05/08/2026.
    lines = [item.model_dump() for item in payload.lines] if payload is not None else None
    try:
        row = svc.mark_received(request_id, received_lines=lines, actor=user)
    except PurchaseError as exc:
        raise _map_error(exc) from None
    _notify_purchase_changed(row.get("code"))
    return PurchaseRequestOut(**row)


@router.put(
    "/api/purchase-requests/{request_id}/received-quantities", response_model=PurchaseRequestOut
)
def update_purchase_request_received_quantities(
    request_id: int,
    payload: ReceivedLinesIn,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> PurchaseRequestOut:
    # Cổng `update` để vào module; service thu về `thu_mua:approve` vì sửa số này là ĐỔI SỐ NỢ.
    try:
        row = svc.update_received_quantities(
            request_id, received_lines=[i.model_dump() for i in payload.lines], actor=user
        )
    except PurchaseError as exc:
        raise _map_error(exc) from None
    _notify_purchase_changed(row.get("code"))
    return PurchaseRequestOut(**row)


@router.post("/api/purchase-requests/{request_id}/undo-received", response_model=PurchaseRequestOut)
def undo_purchase_request_received(
    request_id: int,
    payload: ReasonIn,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> PurchaseRequestOut:
    # Cổng ở đây chỉ là `update` (vào được module); service mới thu về `thu_mua:approve` — cùng lối
    # đã dùng cho `cancel`, để người thiếu quyền nhận đúng câu báo thay vì 403 trống.
    try:
        row = svc.undo_received(request_id, reason=payload.reason, actor=user)
    except PurchaseError as exc:
        raise _map_error(exc) from None
    _notify_purchase_changed(row.get("code"))
    return PurchaseRequestOut(**row)


@router.post("/api/purchase-requests/{request_id}/cancel", response_model=PurchaseRequestOut)
def cancel_purchase_request(
    request_id: int,
    payload: ReasonIn,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "cancel"))],
) -> PurchaseRequestOut:
    try:
        row = svc.cancel(request_id, reason=payload.reason, actor=user)
    except PurchaseError as exc:
        raise _map_error(exc) from None
    _notify_purchase_changed(row.get("code"))
    return PurchaseRequestOut(**row)


# --- đợt giao ---------------------------------------------------------------
#
# Cổng ở router là `thu_mua:update` cho mọi thao tác ghi đợt giao. Riêng "Đóng đơn" service tự thu
# về `thu_mua:approve` — nó cắt phần hàng chưa về ra khỏi công nợ nên là quyết định về TIỀN, cùng
# lằn ranh đã áp cho `undo-received` và `cancel`.


@router.post("/api/purchase-requests/{request_id}/deliveries", response_model=PurchaseRequestOut)
def create_purchase_delivery(
    request_id: int,
    payload: PurchaseDeliveryIn,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> PurchaseRequestOut:
    body = payload.model_dump()
    lines = body.pop("lines") or []
    try:
        row = svc.ghi_dot_giao(request_id, lines=lines, actor=user, **body)
    except PurchaseError as exc:
        raise _map_error(exc) from None
    seq_no = row.get("deliveries", [{}])[-1].get("seq_no") if row.get("deliveries") else None
    _notify_purchase_changed(row.get("code"), event_type="purchase_delivery_created", seq_no=seq_no)
    return PurchaseRequestOut(**row)


@router.put(
    "/api/purchase-requests/{request_id}/deliveries/{delivery_id}",
    response_model=PurchaseRequestOut,
)
def update_purchase_delivery(
    request_id: int,
    delivery_id: int,
    payload: PurchaseDeliveryIn,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> PurchaseRequestOut:
    body = payload.model_dump()
    lines = body.pop("lines")
    try:
        row = svc.sua_dot_giao(request_id, delivery_id, lines=lines, actor=user, **body)
    except PurchaseError as exc:
        raise _map_error(exc) from None
    _notify_purchase_changed(row.get("code"))
    return PurchaseRequestOut(**row)


@router.delete(
    "/api/purchase-requests/{request_id}/deliveries/{delivery_id}",
    response_model=PurchaseRequestOut,
)
def delete_purchase_delivery(
    request_id: int,
    delivery_id: int,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> PurchaseRequestOut:
    try:
        row = svc.xoa_dot_giao(request_id, delivery_id, actor=user)
    except PurchaseError as exc:
        raise _map_error(exc) from None
    _notify_purchase_changed(row.get("code"))
    return PurchaseRequestOut(**row)


@router.post("/api/purchase-requests/{request_id}/invoice", response_model=PurchaseRequestOut)
def assign_purchase_invoice(
    request_id: int,
    payload: PurchaseInvoiceAssignIn,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> PurchaseRequestOut:
    try:
        row = svc.gan_hoa_don(
            request_id,
            delivery_ids=payload.delivery_ids,
            invoice_number=payload.invoice_number,
            invoice_date=payload.invoice_date,
            actor=user,
        )
    except PurchaseError as exc:
        raise _map_error(exc) from None
    _notify_purchase_changed(row.get("code"))
    return PurchaseRequestOut(**row)


@router.post("/api/purchase-requests/{request_id}/close", response_model=PurchaseRequestOut)
def close_purchase_request(
    request_id: int,
    payload: ReasonIn,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> PurchaseRequestOut:
    # Cổng `update` chỉ để vào module; service thu về `thu_mua:approve` + bắt lý do.
    try:
        row = svc.dong_don(request_id, reason=payload.reason, actor=user)
    except PurchaseError as exc:
        raise _map_error(exc) from None
    _notify_purchase_changed(row.get("code"))
    return PurchaseRequestOut(**row)


@router.put("/api/purchase-requests/{request_id}/contract", response_model=PurchaseRequestOut)
def update_purchase_contract(
    request_id: int,
    payload: PurchaseContractIn,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> PurchaseRequestOut:
    try:
        row = svc.cap_nhat_hop_dong(
            request_id,
            contract_number=payload.contract_number,
            deposit_expected=payload.deposit_expected,
            actor=user,
        )
    except PurchaseError as exc:
        raise _map_error(exc) from None
    _notify_purchase_changed(row.get("code"))
    return PurchaseRequestOut(**row)


@router.get(
    "/api/purchase-requests/{request_id}/supplier-credit", response_model=SupplierCreditOut
)
def get_purchase_supplier_credit(
    request_id: int,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
) -> SupplierCreditOut:
    """Nợ hiện tại của NCC so với hạn mức — CẢNH BÁO MỀM, không chặn gì (Đ6)."""
    try:
        row = svc.get_request(request_id, actor=user)
        data = svc.han_muc_ncc(row.get("supplier_id"))
    except PurchaseError as exc:
        raise _map_error(exc) from None
    return SupplierCreditOut(**data)


@router.post(
    "/api/purchase-requests/{request_id}/attachments",
    response_model=PurchaseRequestOut,
    status_code=status.HTTP_201_CREATED,
)
def upload_purchase_attachment(
    request_id: int,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
    kind: str = Query(default="khac"),
    delivery_id: int | None = Query(default=None),
    file: UploadFile = File(...),
) -> PurchaseRequestOut:
    data = file.file.read()
    try:
        row = svc.them_dinh_kem(
            request_id,
            delivery_id=delivery_id,
            kind=kind,
            file_name=file.filename,
            content_type=file.content_type,
            data=data,
            actor=user,
        )
    except PurchaseError as exc:
        raise _map_error(exc) from None
    _notify_purchase_changed(row.get("code"))
    return PurchaseRequestOut(**row)


@router.delete(
    "/api/purchase-requests/{request_id}/attachments/{attachment_id}",
    response_model=PurchaseRequestOut,
)
def delete_purchase_attachment(
    request_id: int,
    attachment_id: int,
    svc: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
) -> PurchaseRequestOut:
    try:
        row = svc.xoa_dinh_kem(request_id, attachment_id, actor=user)
    except PurchaseError as exc:
        raise _map_error(exc) from None
    _notify_purchase_changed(row.get("code"))
    return PurchaseRequestOut(**row)
