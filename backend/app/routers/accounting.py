"""Accounting API: purchase inbox, bank accounts, Phiếu chi and UNC."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status

from ..deps import (
    get_accounting_service,
    get_purchase_service,
    require_any_permission,
    require_permission,
)
from ..models.purchase import PR_DRAFT
from ..models.user import User
from ..schemas.accounting import (
    ApproveAndCreateVoucherIn,
    CancelPaymentReceiptIn,
    CancelPaymentVoucherIn,
    CompanyBankAccountIn,
    CompanyBankAccountOut,
    MarkPaymentReceiptReceivedIn,
    MarkPaymentVoucherPaidIn,
    PaymentReceiptAttachmentListOut,
    PaymentReceiptAttachmentOut,
    PaymentReceiptIn,
    PaymentReceiptListOut,
    PaymentReceiptOut,
    PaymentVoucherAttachmentListOut,
    PaymentVoucherAttachmentOut,
    PaymentVoucherIn,
    PaymentVoucherListOut,
    PaymentVoucherOut,
    SupplierBankAccountIn,
    SupplierBankAccountOut,
)
from ..schemas.purchase import PurchaseRequestListOut
from ..services.accounting_service import (
    AccountingConflict,
    AccountingNotFound,
    AccountingService,
    AccountingValidationError,
)
from ..services.purchase_service import PurchaseService


router = APIRouter(tags=["accounting"])
MODULE = "ke_toan"


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AccountingNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, AccountingValidationError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if isinstance(exc, AccountingConflict):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/api/accounting/inbox", response_model=PurchaseRequestListOut)
def accounting_inbox(
    purchases: Annotated[PurchaseService, Depends(get_purchase_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "read"))],
    q: str | None = Query(default=None),
    status_: str | None = Query(default=None, alias="status"),
    supplier_id: int | None = Query(default=None),
    sort: str = Query(default="-created_at"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> PurchaseRequestListOut:
    # Kế toán có `ke_toan` scope `all` ⇒ `_purchase_scope` trả `all` ⇒ thấy HẾT đơn mua, đúng như
    # họ cần để lập phiếu chi. Truyền `actor` để chính lối này không thành lỗ nhìn xuyên phạm vi.
    rows, total = purchases.list_requests(
        q=q, status=status_, supplier_id=supplier_id, sort=sort, page=page, size=size,
        actor=user,
        # Đơn NHÁP là thu mua còn đang sửa, CHƯA gửi duyệt — không thuộc hộp thư kế toán (chủ
        # 04/08/2026). Chặn ở API chứ không chỉ giấu ở giao diện.
        exclude_statuses=[PR_DRAFT],
    )
    return PurchaseRequestListOut(items=rows, total=total, page=page, size=size)


@router.get("/api/accounting/company-bank-accounts", response_model=list[CompanyBankAccountOut])
def list_company_bank_accounts(
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
    active_only: bool = Query(default=False),
):
    return svc.list_company_accounts(active_only=active_only)


@router.post(
    "/api/accounting/company-bank-accounts",
    response_model=CompanyBankAccountOut,
    status_code=status.HTTP_201_CREATED,
)
def create_company_bank_account(
    payload: CompanyBankAccountIn,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
):
    try:
        return svc.create_company_account(actor=user, **payload.model_dump())
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None


@router.put("/api/accounting/company-bank-accounts/{account_id}", response_model=CompanyBankAccountOut)
def update_company_bank_account(
    account_id: int,
    payload: CompanyBankAccountIn,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
):
    try:
        return svc.update_company_account(account_id, actor=user, **payload.model_dump())
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None


@router.patch("/api/accounting/company-bank-accounts/{account_id}/toggle-active", response_model=CompanyBankAccountOut)
def toggle_company_bank_account(
    account_id: int,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "update"))],
):
    try:
        return svc.toggle_company_account(account_id, actor=user)
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None


@router.get("/api/accounting/supplier-bank-accounts", response_model=list[SupplierBankAccountOut])
def list_supplier_bank_accounts(
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    _: Annotated[
        User,
        Depends(require_any_permission((MODULE, "read"), ("thu_mua", "read"))),
    ],
    supplier_id: int | None = Query(default=None),
    active_only: bool = Query(default=False),
):
    return svc.list_supplier_accounts(supplier_id=supplier_id, active_only=active_only)


@router.post(
    "/api/accounting/supplier-bank-accounts",
    response_model=SupplierBankAccountOut,
    status_code=status.HTTP_201_CREATED,
)
def create_supplier_bank_account(
    payload: SupplierBankAccountIn,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[
        User,
        Depends(require_any_permission((MODULE, "approve"), ("thu_mua", "update"))),
    ],
):
    try:
        return svc.create_supplier_account(actor=user, **payload.model_dump())
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None


@router.put("/api/accounting/supplier-bank-accounts/{account_id}", response_model=SupplierBankAccountOut)
def update_supplier_bank_account(
    account_id: int,
    payload: SupplierBankAccountIn,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[
        User,
        Depends(require_any_permission((MODULE, "approve"), ("thu_mua", "update"))),
    ],
):
    try:
        return svc.update_supplier_account(account_id, actor=user, **payload.model_dump())
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None


@router.patch("/api/accounting/supplier-bank-accounts/{account_id}/toggle-active", response_model=SupplierBankAccountOut)
def toggle_supplier_bank_account(
    account_id: int,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[
        User,
        Depends(require_any_permission((MODULE, "approve"), ("thu_mua", "update"))),
    ],
):
    try:
        return svc.toggle_supplier_account(account_id, actor=user)
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None


@router.get("/api/accounting/payment-vouchers", response_model=PaymentVoucherListOut)
def list_payment_vouchers(
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
    q: str | None = Query(default=None),
    status_: str | None = Query(default=None, alias="status"),
    voucher_type: str | None = Query(default=None),
    supplier_id: int | None = Query(default=None),
    purchase_request_id: int | None = Query(default=None),
    sort: str = Query(default="-created_at"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
):
    rows, total, totals = svc.list_vouchers(
        q=q,
        status=status_,
        voucher_type=voucher_type,
        supplier_id=supplier_id,
        purchase_request_id=purchase_request_id,
        sort=sort,
        page=page,
        size=size,
    )
    return PaymentVoucherListOut(items=rows, total=total, page=page, size=size, **totals)


@router.get("/api/accounting/payment-vouchers/{voucher_id}", response_model=PaymentVoucherOut)
def get_payment_voucher(
    voucher_id: int,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
):
    try:
        return PaymentVoucherOut(**svc.get_voucher(voucher_id))
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None


@router.post(
    "/api/accounting/payment-vouchers",
    response_model=PaymentVoucherOut,
    status_code=status.HTTP_201_CREATED,
)
def create_payment_voucher(
    payload: PaymentVoucherIn,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "approve"))],
):
    try:
        return PaymentVoucherOut(**svc.create_voucher(actor=user, **payload.model_dump()))
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None


@router.put("/api/accounting/payment-vouchers/{voucher_id}", response_model=PaymentVoucherOut)
def update_payment_voucher(
    voucher_id: int,
    payload: PaymentVoucherIn,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "approve"))],
):
    try:
        return PaymentVoucherOut(
            **svc.update_voucher(voucher_id, actor=user, **payload.model_dump())
        )
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None


# ĐÃ GỠ 04/08/2026 — `POST .../approve-and-create-voucher` (duyệt PMH và lập phiếu chi trong
# MỘT cú bấm). Nó cho kế toán tự duyệt khoản chi rồi tự viết phiếu chi, phá tách vai. Nay đúng
# hai bước: giám đốc duyệt ở `/api/purchase-requests/{id}/approve`, kế toán lập phiếu chi ở
# `POST /api/accounting/payment-vouchers` (vốn đã đòi PMH từ 'đã duyệt' trở lên).


@router.post("/api/accounting/payment-vouchers/{voucher_id}/mark-paid", response_model=PaymentVoucherOut)
def mark_payment_voucher_paid(
    voucher_id: int,
    payload: MarkPaymentVoucherPaidIn,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "manage_status"))],
):
    try:
        return PaymentVoucherOut(
            **svc.mark_paid(voucher_id, actor=user, bank_reference=payload.bank_reference)
        )
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None


@router.post("/api/accounting/payment-vouchers/{voucher_id}/cancel", response_model=PaymentVoucherOut)
def cancel_payment_voucher(
    voucher_id: int,
    payload: CancelPaymentVoucherIn,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "cancel"))],
):
    try:
        return PaymentVoucherOut(
            **svc.cancel_voucher(voucher_id, actor=user, reason=payload.reason)
        )
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None


@router.get(
    "/api/accounting/payment-vouchers/{voucher_id}/attachments",
    response_model=PaymentVoucherAttachmentListOut,
)
def list_payment_voucher_attachments(
    voucher_id: int,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
):
    try:
        items = svc.list_voucher_attachments(voucher_id)
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None
    return PaymentVoucherAttachmentListOut(
        items=[PaymentVoucherAttachmentOut(**item) for item in items]
    )


@router.post(
    "/api/accounting/payment-vouchers/{voucher_id}/attachments",
    response_model=PaymentVoucherAttachmentOut,
    status_code=status.HTTP_201_CREATED,
)
def upload_payment_voucher_attachment(
    voucher_id: int,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "approve"))],
    file: UploadFile = File(...),
):
    data = file.file.read()
    try:
        return PaymentVoucherAttachmentOut(
            **svc.add_voucher_attachment(
                voucher_id,
                actor=user,
                file_name=file.filename,
                content_type=file.content_type,
                data=data,
            )
        )
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None


@router.delete(
    "/api/accounting/payment-vouchers/{voucher_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_payment_voucher_attachment(
    voucher_id: int,
    attachment_id: int,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "approve"))],
) -> Response:
    try:
        svc.delete_voucher_attachment(voucher_id, attachment_id, actor=user)
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/api/accounting/payment-receipts", response_model=PaymentReceiptListOut)
def list_payment_receipts(
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
    q: str | None = Query(default=None),
    status_: str | None = Query(default=None, alias="status"),
    payment_voucher_id: int | None = Query(default=None),
    sort: str = Query(default="-created_at"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
):
    rows, total = svc.list_receipts(
        q=q,
        status=status_,
        payment_voucher_id=payment_voucher_id,
        sort=sort,
        page=page,
        size=size,
    )
    return PaymentReceiptListOut(items=rows, total=total, page=page, size=size)


@router.post(
    "/api/accounting/payment-vouchers/{voucher_id}/receipts",
    response_model=PaymentReceiptOut,
    status_code=status.HTTP_201_CREATED,
)
def create_payment_receipt(
    voucher_id: int,
    payload: PaymentReceiptIn,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "approve"))],
):
    try:
        return PaymentReceiptOut(**svc.create_receipt(voucher_id, actor=user, **payload.model_dump()))
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None


@router.put("/api/accounting/payment-receipts/{receipt_id}", response_model=PaymentReceiptOut)
def update_payment_receipt(
    receipt_id: int,
    payload: PaymentReceiptIn,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "approve"))],
):
    try:
        return PaymentReceiptOut(
            **svc.update_receipt(receipt_id, actor=user, **payload.model_dump())
        )
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None


@router.post(
    "/api/accounting/payment-receipts/{receipt_id}/mark-received",
    response_model=PaymentReceiptOut,
)
def mark_payment_receipt_received(
    receipt_id: int,
    payload: MarkPaymentReceiptReceivedIn,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "manage_status"))],
):
    try:
        return PaymentReceiptOut(
            **svc.mark_receipt_received(
                receipt_id, actor=user, bank_reference=payload.bank_reference
            )
        )
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None


@router.post("/api/accounting/payment-receipts/{receipt_id}/cancel", response_model=PaymentReceiptOut)
def cancel_payment_receipt(
    receipt_id: int,
    payload: CancelPaymentReceiptIn,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "cancel"))],
):
    try:
        return PaymentReceiptOut(
            **svc.cancel_receipt(receipt_id, actor=user, reason=payload.reason)
        )
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None


@router.get(
    "/api/accounting/payment-receipts/{receipt_id}/attachments",
    response_model=PaymentReceiptAttachmentListOut,
)
def list_payment_receipt_attachments(
    receipt_id: int,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    _: Annotated[User, Depends(require_permission(MODULE, "read"))],
):
    try:
        items = svc.list_receipt_attachments(receipt_id)
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None
    return PaymentReceiptAttachmentListOut(
        items=[PaymentReceiptAttachmentOut(**item) for item in items]
    )


@router.post(
    "/api/accounting/payment-receipts/{receipt_id}/attachments",
    response_model=PaymentReceiptAttachmentOut,
    status_code=status.HTTP_201_CREATED,
)
def upload_payment_receipt_attachment(
    receipt_id: int,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "approve"))],
    file: UploadFile = File(...),
):
    data = file.file.read()
    try:
        return PaymentReceiptAttachmentOut(
            **svc.add_receipt_attachment(
                receipt_id,
                actor=user,
                file_name=file.filename,
                content_type=file.content_type,
                data=data,
            )
        )
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None


@router.delete(
    "/api/accounting/payment-receipts/{receipt_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_payment_receipt_attachment(
    receipt_id: int,
    attachment_id: int,
    svc: Annotated[AccountingService, Depends(get_accounting_service)],
    user: Annotated[User, Depends(require_permission(MODULE, "approve"))],
) -> Response:
    try:
        svc.delete_receipt_attachment(receipt_id, attachment_id, actor=user)
    except (AccountingValidationError, AccountingConflict, AccountingNotFound) as exc:
        raise _map_error(exc) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
