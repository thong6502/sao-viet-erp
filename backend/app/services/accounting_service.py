"""Business rules for Accounting purchase approvals and payment vouchers."""
from __future__ import annotations

import re
import secrets
import string
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from sqlalchemy.exc import IntegrityError

from ..models.accounting import (
    BANK_FEE_BEARERS,
    BANK_FEE_PAYER,
    PAYMENT_RECEIPT_CANCELLED,
    PAYMENT_RECEIPT_RECEIVED,
    PAYMENT_RECEIPT_WAITING,
    PAYMENT_STAGES,
    PAYMENT_VOUCHER_CANCELLED,
    PAYMENT_VOUCHER_PAID,
    PAYMENT_VOUCHER_STATUSES,
    PAYMENT_VOUCHER_TYPES,
    PAYMENT_VOUCHER_WAITING,
    VOUCHER_BANK_TRANSFER,
    VOUCHER_CASH,
    CompanyBankAccount,
    PaymentReceipt,
    PaymentReceiptAttachment,
    PaymentVoucher,
    PaymentVoucherAttachment,
    SupplierBankAccount,
)
from ..models.purchase import (
    DPR_CANCELLED,
    DPR_DONE,
    DPR_IN_PURCHASE,
    PR_APPROVED,
    PR_PENDING,
    PR_PURCHASED,
    PR_RECEIVED,
    PurchaseRequest,
)
from ..repositories.accounting_repo import AccountingRepository
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.purchase_repo import PurchaseRequestRepository, SupplierRepository
from ..repositories.user_repo import UserRepository
from .purchase_service import _purchase_line_amounts


class AccountingError(Exception):
    pass


class AccountingValidationError(AccountingError):
    pass


class AccountingNotFound(AccountingError):
    pass


class AccountingConflict(AccountingError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


# File đính kèm phiếu chi: bytes nằm dưới <backend>/static (cùng gốc mount
# /static của main.py) — /static là public nên giới hạn loại + cỡ file.
_STATIC_DIR = Path(__file__).resolve().parents[2] / "static"
_ATTACHMENT_SUBDIR = "ke-toan"
_RECEIPT_ATTACHMENT_SUBDIR = "ke-toan-thu"
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_ATTACHMENTS_PER_VOUCHER = 20


def _safe_attachment_name(file_name: str | None) -> str:
    """Chặn traversal (kể cả Windows "\\") + thay ký tự cấm; cắt 180 ký tự."""
    name = Path((file_name or "file").replace("\\", "/")).name
    return re.sub(r'[<>:"|?*\x00-\x1f]', "_", name)[:180].strip(" .") or "file"


def _text(value, *, label: str, required: bool = False, max_length: int | None = None):
    cleaned = (value or "").strip()
    if required and not cleaned:
        raise AccountingValidationError(f"{label} không được để trống.")
    if max_length is not None and len(cleaned) > max_length:
        raise AccountingValidationError(f"{label} vượt quá {max_length} ký tự.")
    return cleaned or None


class AccountingService:
    def __init__(
        self,
        repo: AccountingRepository,
        purchases: PurchaseRequestRepository,
        suppliers: SupplierRepository,
        users: UserRepository,
        audit: AuditLogRepository,
    ) -> None:
        self.repo = repo
        self.purchases = purchases
        self.suppliers = suppliers
        self.users = users
        self.audit = audit

    # --- bank accounts ----------------------------------------------------

    def list_company_accounts(self, *, active_only: bool = False):
        return self.repo.list_company_accounts(active_only=active_only)

    def create_company_account(self, *, actor, **values):
        cleaned = self._clean_bank_account(values)
        make_default = bool(cleaned.pop("is_default")) or self.repo.company_account_count() == 0
        row = CompanyBankAccount(**cleaned, is_default=make_default)
        try:
            saved = self.repo.save_company_account(row, make_default=make_default)
        except IntegrityError as exc:
            raise AccountingConflict("Tài khoản ngân hàng công ty đã tồn tại.") from exc
        self.audit.create(
            actor_user_id=actor.id,
            action="create_company_bank_account",
            target=f"company_bank_account:{saved.id}",
            detail=f"{saved.bank_name} - {saved.account_number}",
        )
        return saved

    def update_company_account(self, account_id: int, *, actor, **values):
        row = self.repo.get_company_account(account_id)
        if row is None:
            raise AccountingNotFound("Không tìm thấy tài khoản ngân hàng công ty.")
        cleaned = self._clean_bank_account(values)
        make_default = bool(cleaned.pop("is_default"))
        for key, value in cleaned.items():
            setattr(row, key, value)
        row.is_default = make_default
        try:
            saved = self.repo.save_company_account(row, make_default=make_default)
        except IntegrityError as exc:
            raise AccountingConflict("Tài khoản ngân hàng công ty đã tồn tại.") from exc
        self.audit.create(
            actor_user_id=actor.id,
            action="update_company_bank_account",
            target=f"company_bank_account:{saved.id}",
            detail=f"{saved.bank_name} - {saved.account_number}",
        )
        return saved

    def toggle_company_account(self, account_id: int, *, actor):
        row = self.repo.get_company_account(account_id)
        if row is None:
            raise AccountingNotFound("Không tìm thấy tài khoản ngân hàng công ty.")
        row.is_active = not row.is_active
        if not row.is_active:
            row.is_default = False
        saved = self.repo.save_company_account(row, make_default=False)
        self.audit.create(
            actor_user_id=actor.id,
            action="toggle_company_bank_account",
            target=f"company_bank_account:{saved.id}",
            detail="active" if saved.is_active else "inactive",
        )
        return saved

    def list_supplier_accounts(self, *, supplier_id: int | None = None, active_only: bool = False):
        return [
            self._supplier_account_out(row)
            for row in self.repo.list_supplier_accounts(
                supplier_id=supplier_id, active_only=active_only
            )
        ]

    def create_supplier_account(self, *, actor, supplier_id: int, **values):
        supplier = self.suppliers.get_by_id(supplier_id)
        if supplier is None:
            raise AccountingNotFound("Không tìm thấy nhà cung cấp.")
        cleaned = self._clean_bank_account(values)
        make_default = bool(cleaned.pop("is_default")) or self.repo.supplier_account_count(supplier_id) == 0
        row = SupplierBankAccount(
            supplier_id=supplier_id, **cleaned, is_default=make_default
        )
        try:
            saved = self.repo.save_supplier_account(row, make_default=make_default)
        except IntegrityError as exc:
            raise AccountingConflict("Tài khoản ngân hàng nhà cung cấp đã tồn tại.") from exc
        self.audit.create(
            actor_user_id=actor.id,
            action="create_supplier_bank_account",
            target=f"supplier_bank_account:{saved.id}",
            detail=f"{supplier.name} - {saved.account_number}",
        )
        return self._supplier_account_out(saved)

    def update_supplier_account(self, account_id: int, *, actor, supplier_id: int, **values):
        row = self.repo.get_supplier_account(account_id)
        if row is None:
            raise AccountingNotFound("Không tìm thấy tài khoản ngân hàng nhà cung cấp.")
        supplier = self.suppliers.get_by_id(supplier_id)
        if supplier is None:
            raise AccountingNotFound("Không tìm thấy nhà cung cấp.")
        cleaned = self._clean_bank_account(values)
        make_default = bool(cleaned.pop("is_default"))
        row.supplier_id = supplier_id
        for key, value in cleaned.items():
            setattr(row, key, value)
        row.is_default = make_default
        try:
            saved = self.repo.save_supplier_account(row, make_default=make_default)
        except IntegrityError as exc:
            raise AccountingConflict("Tài khoản ngân hàng nhà cung cấp đã tồn tại.") from exc
        self.audit.create(
            actor_user_id=actor.id,
            action="update_supplier_bank_account",
            target=f"supplier_bank_account:{saved.id}",
            detail=f"{supplier.name} - {saved.account_number}",
        )
        return self._supplier_account_out(saved)

    def toggle_supplier_account(self, account_id: int, *, actor):
        row = self.repo.get_supplier_account(account_id)
        if row is None:
            raise AccountingNotFound("Không tìm thấy tài khoản ngân hàng nhà cung cấp.")
        row.is_active = not row.is_active
        if not row.is_active:
            row.is_default = False
        saved = self.repo.save_supplier_account(row, make_default=False)
        self.audit.create(
            actor_user_id=actor.id,
            action="toggle_supplier_bank_account",
            target=f"supplier_bank_account:{saved.id}",
            detail="active" if saved.is_active else "inactive",
        )
        return self._supplier_account_out(saved)

    # --- vouchers ---------------------------------------------------------

    def list_vouchers(self, **filters):
        rows, total, totals = self.repo.list_vouchers(**filters)
        return [self._voucher_out(row) for row in rows], total, totals

    def get_voucher(self, voucher_id: int):
        return self._voucher_out(self._voucher(voucher_id))

    def create_voucher(self, *, actor, purchase_request_id: int, **values):
        purchase = self._purchase(purchase_request_id)
        prepared = self._prepare_voucher(
            purchase, values, allow_pending_purchase=False, exclude_voucher_id=None
        )
        voucher = self._new_voucher(purchase, prepared, actor.id)
        saved = self.repo.save_voucher(voucher)
        self.audit.create(
            actor_user_id=actor.id,
            action="create_payment_voucher",
            target=f"payment_voucher:{saved.id}",
            detail=f"{saved.code} <- {purchase.code}",
        )
        return self._voucher_out(saved)

    def approve_and_create_voucher(self, request_id: int, *, actor, **values):
        purchase = self._purchase(request_id)
        if purchase.status != PR_PENDING:
            raise AccountingConflict("Chỉ phiếu mua đang chờ duyệt mới được duyệt.")
        prepared = self._prepare_voucher(
            purchase, values, allow_pending_purchase=True, exclude_voucher_id=None
        )
        purchase.status = PR_APPROVED
        purchase.approved_by_user_id = actor.id
        purchase.approved_at = _now()
        for link in purchase.sources:
            if link.department_request and link.department_request.status not in (DPR_DONE, DPR_CANCELLED):
                link.department_request.status = DPR_IN_PURCHASE
        voucher = self._new_voucher(purchase, prepared, actor.id)
        saved = self.repo.save_voucher(voucher)
        self.audit.create(
            actor_user_id=actor.id,
            action="approve_purchase_and_create_payment_voucher",
            target=f"purchase_request:{purchase.id}",
            detail=f"{purchase.code} -> {saved.code}",
        )
        return self._voucher_out(saved)

    def update_voucher(self, voucher_id: int, *, actor, purchase_request_id: int, **values):
        voucher = self._voucher(voucher_id)
        if voucher.status != PAYMENT_VOUCHER_WAITING:
            raise AccountingConflict("Chỉ chứng từ đang chờ chi mới được sửa.")
        if purchase_request_id != voucher.purchase_request_id:
            raise AccountingConflict("Không được đổi phiếu mua nguồn của chứng từ.")
        if values.get("voucher_type") != voucher.voucher_type:
            raise AccountingConflict("Không được đổi loại Phiếu chi/UNC sau khi đã lập.")
        purchase = self._purchase(purchase_request_id)
        prepared = self._prepare_voucher(
            purchase, values, allow_pending_purchase=False, exclude_voucher_id=voucher.id
        )
        self._apply_voucher(voucher, purchase, prepared)
        saved = self.repo.save_voucher(voucher)
        self.audit.create(
            actor_user_id=actor.id,
            action="update_payment_voucher",
            target=f"payment_voucher:{saved.id}",
            detail=saved.code,
        )
        return self._voucher_out(saved)

    def mark_paid(self, voucher_id: int, *, actor, bank_reference: str | None):
        voucher = self._voucher(voucher_id)
        if voucher.status != PAYMENT_VOUCHER_WAITING:
            raise AccountingConflict("Chỉ chứng từ đang chờ chi mới được xác nhận đã chi.")
        reference = _text(bank_reference, label="Mã giao dịch", max_length=64)
        if voucher.voucher_type == VOUCHER_BANK_TRANSFER and not reference:
            raise AccountingValidationError("UNC phải có mã giao dịch hoặc số báo nợ.")
        voucher.status = PAYMENT_VOUCHER_PAID
        voucher.bank_reference = reference
        voucher.paid_by_user_id = actor.id
        voucher.paid_at = _now()
        saved = self.repo.save_voucher(voucher)
        self.audit.create(
            actor_user_id=actor.id,
            action="mark_payment_voucher_paid",
            target=f"payment_voucher:{saved.id}",
            detail=saved.code,
        )
        return self._voucher_out(saved)

    def cancel_voucher(self, voucher_id: int, *, actor, reason: str):
        voucher = self._voucher(voucher_id)
        if voucher.status != PAYMENT_VOUCHER_WAITING:
            raise AccountingConflict("Chỉ chứng từ đang chờ chi mới được hủy.")
        cleaned_reason = _text(reason, label="Lý do hủy", required=True, max_length=2000)
        voucher.status = PAYMENT_VOUCHER_CANCELLED
        voucher.cancel_reason = cleaned_reason
        voucher.cancelled_by_user_id = actor.id
        voucher.cancelled_at = _now()
        saved = self.repo.save_voucher(voucher)
        self.audit.create(
            actor_user_id=actor.id,
            action="cancel_payment_voucher",
            target=f"payment_voucher:{saved.id}",
            detail=f"{saved.code}: {cleaned_reason}",
        )
        return self._voucher_out(saved)

    # --- payment receipts ---------------------------------------------------

    def list_receipts(
        self,
        *,
        q: str | None = None,
        status: str | None = None,
        payment_voucher_id: int | None = None,
        sort: str = "-created_at",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict], int]:
        rows, total = self.repo.list_receipts(
            q=q,
            status=status,
            payment_voucher_id=payment_voucher_id,
            sort=sort,
            page=page,
            size=size,
        )
        return [self._receipt_out(row) for row in rows], total

    def create_receipt(self, payment_voucher_id: int, *, actor, **values):
        voucher = self._voucher(payment_voucher_id)
        if voucher.status != PAYMENT_VOUCHER_PAID:
            raise AccountingConflict("Chỉ Phiếu chi/UNC đã chi mới được lập phiếu thu.")
        prepared = self._prepare_receipt(voucher, values, exclude_receipt_id=None)
        receipt = PaymentReceipt(
            code=self._new_receipt_code(),
            payment_voucher_id=voucher.id,
            purchase_request_id=voucher.purchase_request_id,
            status=PAYMENT_RECEIPT_WAITING,
            created_by_user_id=actor.id,
        )
        self._apply_receipt(receipt, voucher, prepared)
        saved = self.repo.save_receipt(receipt)
        self.audit.create(
            actor_user_id=actor.id,
            action="create_payment_receipt",
            target=f"payment_receipt:{saved.id}",
            detail=f"{saved.code} <- {voucher.code}",
        )
        return self._receipt_out(saved)

    def update_receipt(self, receipt_id: int, *, actor, **values):
        receipt = self._receipt(receipt_id)
        if receipt.status != PAYMENT_RECEIPT_WAITING:
            raise AccountingConflict("Chỉ phiếu thu đang chờ thu mới được sửa.")
        voucher = receipt.payment_voucher
        prepared = self._prepare_receipt(voucher, values, exclude_receipt_id=receipt.id)
        self._apply_receipt(receipt, voucher, prepared)
        saved = self.repo.save_receipt(receipt)
        self.audit.create(
            actor_user_id=actor.id,
            action="update_payment_receipt",
            target=f"payment_receipt:{saved.id}",
            detail=saved.code,
        )
        return self._receipt_out(saved)

    def mark_receipt_received(self, receipt_id: int, *, actor, bank_reference: str | None):
        receipt = self._receipt(receipt_id)
        if receipt.status != PAYMENT_RECEIPT_WAITING:
            raise AccountingConflict("Chỉ phiếu thu đang chờ thu mới được xác nhận đã thu.")
        reference = _text(bank_reference, label="Mã giao dịch", max_length=64)
        if receipt.receipt_method == VOUCHER_BANK_TRANSFER and not reference:
            raise AccountingValidationError(
                "Thu qua ngân hàng phải có mã giao dịch hoặc số báo có."
            )
        receipt.status = PAYMENT_RECEIPT_RECEIVED
        receipt.bank_reference = reference
        receipt.received_by_user_id = actor.id
        receipt.received_at = _now()
        saved = self.repo.save_receipt(receipt)
        self.audit.create(
            actor_user_id=actor.id,
            action="mark_payment_receipt_received",
            target=f"payment_receipt:{saved.id}",
            detail=saved.code,
        )
        return self._receipt_out(saved)

    def cancel_receipt(self, receipt_id: int, *, actor, reason: str):
        receipt = self._receipt(receipt_id)
        if receipt.status != PAYMENT_RECEIPT_WAITING:
            raise AccountingConflict("Chỉ phiếu thu đang chờ thu mới được hủy.")
        cleaned_reason = _text(reason, label="Lý do hủy", required=True, max_length=2000)
        receipt.status = PAYMENT_RECEIPT_CANCELLED
        receipt.cancel_reason = cleaned_reason
        receipt.cancelled_by_user_id = actor.id
        receipt.cancelled_at = _now()
        saved = self.repo.save_receipt(receipt)
        self.audit.create(
            actor_user_id=actor.id,
            action="cancel_payment_receipt",
            target=f"payment_receipt:{saved.id}",
            detail=f"{saved.code}: {cleaned_reason}",
        )
        return self._receipt_out(saved)

    def _prepare_receipt(
        self, voucher: PaymentVoucher, values: dict, *, exclude_receipt_id: int | None
    ) -> dict:
        receipt_method = (values.get("receipt_method") or "").strip()
        if receipt_method not in PAYMENT_VOUCHER_TYPES:
            raise AccountingValidationError("Hình thức thu không hợp lệ.")
        payer_name = _text(
            values.get("payer_name"), label="Người nộp tiền", required=True, max_length=255
        )

        amount = int(values.get("amount") or 0)
        if amount <= 0:
            raise AccountingValidationError("Số tiền thu phải lớn hơn 0.")
        # Thu bằng đúng loại tiền của phiếu chi gốc — không nhận currency từ payload.
        currency = voucher.currency
        exchange_rate = float(values.get("exchange_rate") or voucher.exchange_rate)
        if exchange_rate <= 0:
            raise AccountingValidationError("Tỷ giá phải lớn hơn 0.")
        if currency == "VND" and exchange_rate != 1:
            raise AccountingValidationError("Tỷ giá của VND phải bằng 1.")
        amount_vnd = int(
            (Decimal(amount) * Decimal(str(exchange_rate))).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )
        reserved = self.repo.receipt_reserved_amount(voucher.id, exclude_id=exclude_receipt_id)
        remaining = int(voucher.amount_vnd) - reserved
        if amount_vnd > remaining:
            raise AccountingValidationError(
                f"Số tiền thu vượt quá phần còn được thu ({remaining:,} đ)."
            )
        content = _text(values.get("content"), label="Nội dung thu", required=True, max_length=500)

        company_account = None
        if receipt_method == VOUCHER_BANK_TRANSFER:
            account_id = values.get("company_bank_account_id")
            company_account = (
                self.repo.get_company_account(int(account_id)) if account_id else None
            )
            if company_account is None or not company_account.is_active:
                raise AccountingValidationError(
                    "Vui lòng chọn tài khoản công ty đang hoạt động."
                )
            if company_account.currency != currency:
                raise AccountingValidationError(
                    "Loại tiền phiếu thu phải khớp tài khoản nhận."
                )

        return {
            "payer_name": payer_name,
            "receipt_method": receipt_method,
            "receipt_date": values.get("receipt_date"),
            "amount": amount,
            "amount_vnd": amount_vnd,
            "currency": currency,
            "exchange_rate": exchange_rate,
            "content": content,
            "note": _text(values.get("note"), label="Ghi chú", max_length=2000),
            "company_account": company_account,
        }

    def _apply_receipt(
        self, receipt: PaymentReceipt, voucher: PaymentVoucher, prepared: dict
    ) -> None:
        account = prepared.pop("company_account")
        for key, value in prepared.items():
            setattr(receipt, key, value)
        receipt.company_bank_account_id = account.id if account else None
        receipt.voucher_code_snapshot = voucher.code
        receipt.purchase_code_snapshot = voucher.source_code_snapshot
        receipt.supplier_name_snapshot = voucher.supplier_name_snapshot
        receipt.company_account_holder_snapshot = account.account_holder if account else None
        receipt.company_account_number_snapshot = account.account_number if account else None
        receipt.company_bank_name_snapshot = account.bank_name if account else None
        receipt.company_bank_branch_snapshot = account.bank_branch if account else None

    def _new_receipt_code(self) -> str:
        alphabet = string.ascii_uppercase + string.digits
        date_part = _now().strftime("%y%m%d")
        for _ in range(30):
            suffix = "".join(secrets.choice(alphabet) for _ in range(4))
            code = f"PT-{date_part}-{suffix}"
            if self.repo.get_receipt_by_code(code) is None:
                return code
        raise AccountingConflict("Không sinh được mã chứng từ duy nhất, vui lòng thử lại.")

    def _receipt(self, receipt_id: int) -> PaymentReceipt:
        row = self.repo.get_receipt(receipt_id)
        if row is None:
            raise AccountingNotFound("Không tìm thấy phiếu thu.")
        return row

    def _receipt_out(self, row: PaymentReceipt) -> dict:
        return {
            "id": row.id,
            "code": row.code,
            "payment_voucher_id": row.payment_voucher_id,
            "payment_voucher_code": row.voucher_code_snapshot,
            "purchase_request_id": row.purchase_request_id,
            "purchase_request_code": row.purchase_code_snapshot,
            "supplier_name": row.supplier_name_snapshot,
            "payer_name": row.payer_name,
            "receipt_method": row.receipt_method,
            "status": row.status,
            "receipt_date": row.receipt_date,
            "amount": int(row.amount),
            "amount_vnd": int(row.amount_vnd),
            "currency": row.currency,
            "exchange_rate": float(row.exchange_rate),
            "content": row.content,
            "company_bank_account_id": row.company_bank_account_id,
            "company_account_holder": row.company_account_holder_snapshot,
            "company_account_number": row.company_account_number_snapshot,
            "company_bank_name": row.company_bank_name_snapshot,
            "company_bank_branch": row.company_bank_branch_snapshot,
            "bank_reference": row.bank_reference,
            "created_by_user_id": row.created_by_user_id,
            "created_by_name": self._user_name(row.created_by_user_id),
            "received_by_user_id": row.received_by_user_id,
            "received_by_name": self._user_name(row.received_by_user_id),
            "received_at": row.received_at,
            "cancelled_by_user_id": row.cancelled_by_user_id,
            "cancelled_by_name": self._user_name(row.cancelled_by_user_id),
            "cancelled_at": row.cancelled_at,
            "cancel_reason": row.cancel_reason,
            "note": row.note,
            "attachment_count": len(row.attachments),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    # --- voucher attachments -----------------------------------------------

    def list_voucher_attachments(self, voucher_id: int) -> list[dict]:
        self._voucher(voucher_id)
        return [self._attachment_out(row) for row in self.repo.list_attachments(voucher_id)]

    def add_voucher_attachment(
        self,
        voucher_id: int,
        *,
        actor,
        file_name: str | None,
        content_type: str | None,
        data: bytes,
    ) -> dict:
        voucher = self._voucher(voucher_id)
        if voucher.status == PAYMENT_VOUCHER_CANCELLED:
            raise AccountingConflict("Chứng từ đã hủy — không đính kèm thêm.")
        ct = (content_type or "").lower()
        if not (ct.startswith("image/") or ct == "application/pdf"):
            raise AccountingValidationError("Chỉ nhận ảnh (image/*) hoặc PDF.")
        if not data:
            raise AccountingValidationError("Tệp rỗng.")
        if len(data) > MAX_ATTACHMENT_BYTES:
            raise AccountingValidationError("Tệp vượt quá 10 MB.")
        if len(voucher.attachments) >= MAX_ATTACHMENTS_PER_VOUCHER:
            raise AccountingValidationError(
                f"Mỗi chứng từ tối đa {MAX_ATTACHMENTS_PER_VOUCHER} file đính kèm."
            )
        safe_name = _safe_attachment_name(file_name)
        token = secrets.token_hex(4)
        dest_dir = _STATIC_DIR / _ATTACHMENT_SUBDIR / str(voucher.id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / f"{token}_{safe_name}").write_bytes(data)
        attachment = PaymentVoucherAttachment(
            payment_voucher_id=voucher.id,
            file_name=safe_name,
            file_url=f"/static/{_ATTACHMENT_SUBDIR}/{voucher.id}/{token}_{safe_name}",
            file_type=content_type,
            uploaded_by=actor.id,
        )
        saved = self.repo.save_attachment(attachment)
        self.audit.create(
            actor_user_id=actor.id,
            action="upload_payment_voucher_attachment",
            target=f"payment_voucher:{voucher.id}",
            detail=f"{voucher.code} + {safe_name}",
        )
        return self._attachment_out(saved)

    def delete_voucher_attachment(self, voucher_id: int, attachment_id: int, *, actor) -> None:
        voucher = self._voucher(voucher_id)
        attachment = self.repo.get_attachment(attachment_id)
        if attachment is None or attachment.payment_voucher_id != voucher_id:
            raise AccountingNotFound("Không tìm thấy file đính kèm.")
        try:
            (_STATIC_DIR.parent / attachment.file_url.lstrip("/")).unlink(missing_ok=True)
        except OSError:
            pass  # gỡ file đĩa best-effort — row vẫn phải xóa
        file_name = attachment.file_name
        self.repo.delete_attachment(attachment)
        self.audit.create(
            actor_user_id=actor.id,
            action="delete_payment_voucher_attachment",
            target=f"payment_voucher:{voucher.id}",
            detail=f"{voucher.code} - {file_name}",
        )

    @staticmethod
    def _attachment_out(row: PaymentVoucherAttachment) -> dict:
        return {
            "id": row.id,
            "payment_voucher_id": row.payment_voucher_id,
            "file_name": row.file_name,
            "file_url": row.file_url,
            "file_type": row.file_type,
            "uploaded_by": row.uploaded_by,
            "uploaded_at": row.uploaded_at,
        }

    # --- receipt attachments -----------------------------------------------

    def list_receipt_attachments(self, receipt_id: int) -> list[dict]:
        self._receipt(receipt_id)
        return [
            self._receipt_attachment_out(row)
            for row in self.repo.list_receipt_attachments(receipt_id)
        ]

    def add_receipt_attachment(
        self,
        receipt_id: int,
        *,
        actor,
        file_name: str | None,
        content_type: str | None,
        data: bytes,
    ) -> dict:
        receipt = self._receipt(receipt_id)
        if receipt.status == PAYMENT_RECEIPT_CANCELLED:
            raise AccountingConflict("Phiếu thu đã hủy — không đính kèm thêm.")
        ct = (content_type or "").lower()
        if not (ct.startswith("image/") or ct == "application/pdf"):
            raise AccountingValidationError("Chỉ nhận ảnh (image/*) hoặc PDF.")
        if not data:
            raise AccountingValidationError("Tệp rỗng.")
        if len(data) > MAX_ATTACHMENT_BYTES:
            raise AccountingValidationError("Tệp vượt quá 10 MB.")
        if len(receipt.attachments) >= MAX_ATTACHMENTS_PER_VOUCHER:
            raise AccountingValidationError(
                f"Mỗi phiếu thu tối đa {MAX_ATTACHMENTS_PER_VOUCHER} file đính kèm."
            )
        safe_name = _safe_attachment_name(file_name)
        token = secrets.token_hex(4)
        dest_dir = _STATIC_DIR / _RECEIPT_ATTACHMENT_SUBDIR / str(receipt.id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / f"{token}_{safe_name}").write_bytes(data)
        attachment = PaymentReceiptAttachment(
            payment_receipt_id=receipt.id,
            file_name=safe_name,
            file_url=f"/static/{_RECEIPT_ATTACHMENT_SUBDIR}/{receipt.id}/{token}_{safe_name}",
            file_type=content_type,
            uploaded_by=actor.id,
        )
        saved = self.repo.save_receipt_attachment(attachment)
        self.audit.create(
            actor_user_id=actor.id,
            action="upload_payment_receipt_attachment",
            target=f"payment_receipt:{receipt.id}",
            detail=f"{receipt.code} + {safe_name}",
        )
        return self._receipt_attachment_out(saved)

    def delete_receipt_attachment(self, receipt_id: int, attachment_id: int, *, actor) -> None:
        receipt = self._receipt(receipt_id)
        attachment = self.repo.get_receipt_attachment(attachment_id)
        if attachment is None or attachment.payment_receipt_id != receipt_id:
            raise AccountingNotFound("Không tìm thấy file đính kèm.")
        try:
            (_STATIC_DIR.parent / attachment.file_url.lstrip("/")).unlink(missing_ok=True)
        except OSError:
            pass  # gỡ file đĩa best-effort — row vẫn phải xóa
        file_name = attachment.file_name
        self.repo.delete_receipt_attachment(attachment)
        self.audit.create(
            actor_user_id=actor.id,
            action="delete_payment_receipt_attachment",
            target=f"payment_receipt:{receipt.id}",
            detail=f"{receipt.code} - {file_name}",
        )

    @staticmethod
    def _receipt_attachment_out(row: PaymentReceiptAttachment) -> dict:
        return {
            "id": row.id,
            "payment_receipt_id": row.payment_receipt_id,
            "file_name": row.file_name,
            "file_url": row.file_url,
            "file_type": row.file_type,
            "uploaded_by": row.uploaded_by,
            "uploaded_at": row.uploaded_at,
        }

    # --- validation/output ------------------------------------------------

    def _clean_bank_account(self, values: dict) -> dict:
        cleaned = {
            "account_holder": _text(values.get("account_holder"), label="Chủ tài khoản", required=True, max_length=255),
            "account_number": _text(values.get("account_number"), label="Số tài khoản", required=True, max_length=64),
            "bank_name": _text(values.get("bank_name"), label="Ngân hàng", required=True, max_length=255),
            "bank_branch": _text(values.get("bank_branch"), label="Chi nhánh ngân hàng", required=True, max_length=255),
            "currency": (values.get("currency") or "VND").strip().upper(),
            "is_default": bool(values.get("is_default")),
            "is_active": bool(values.get("is_active", True)),
            "note": _text(values.get("note"), label="Ghi chú", max_length=2000),
        }
        if len(cleaned["currency"]) != 3:
            raise AccountingValidationError("Loại tiền phải gồm 3 ký tự, ví dụ VND.")
        if cleaned["is_default"] and not cleaned["is_active"]:
            raise AccountingValidationError("Tài khoản mặc định phải đang hoạt động.")
        return cleaned

    def _prepare_voucher(
        self,
        purchase: PurchaseRequest,
        values: dict,
        *,
        allow_pending_purchase: bool,
        exclude_voucher_id: int | None,
    ) -> dict:
        allowed_statuses = (PR_APPROVED, PR_PURCHASED, PR_RECEIVED)
        if purchase.status not in allowed_statuses and not (
            allow_pending_purchase and purchase.status == PR_PENDING
        ):
            raise AccountingConflict("Phiếu mua chưa đủ điều kiện lập Phiếu chi/UNC.")
        if purchase.supplier_id is None or purchase.supplier is None:
            raise AccountingValidationError("Phiếu mua chưa có nhà cung cấp.")

        voucher_type = (values.get("voucher_type") or "").strip()
        if voucher_type not in PAYMENT_VOUCHER_TYPES:
            raise AccountingValidationError("Loại chứng từ không hợp lệ.")
        stage = (values.get("payment_stage") or "").strip()
        if stage not in PAYMENT_STAGES:
            raise AccountingValidationError("Đợt thanh toán không hợp lệ.")
        amount = int(values.get("amount") or 0)
        if amount <= 0:
            raise AccountingValidationError("Số tiền thanh toán phải lớn hơn 0.")
        currency = (values.get("currency") or "VND").strip().upper()
        if len(currency) != 3:
            raise AccountingValidationError("Loại tiền phải gồm 3 ký tự, ví dụ VND.")
        exchange_rate = float(values.get("exchange_rate") or 0)
        if exchange_rate <= 0:
            raise AccountingValidationError("Tỷ giá phải lớn hơn 0.")
        if currency == "VND" and exchange_rate != 1:
            raise AccountingValidationError("Tỷ giá của VND phải bằng 1.")
        amount_vnd = int(
            (Decimal(amount) * Decimal(str(exchange_rate))).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )
        total = self._purchase_total(purchase)
        reserved = self.repo.reserved_amount(purchase.id, exclude_id=exclude_voucher_id)
        available = max(0, total - reserved)
        if amount_vnd > available:
            raise AccountingValidationError(
                f"Số tiền quy đổi vượt quá số còn được phép lập ({available:,} đ)."
            )
        content = _text(values.get("content"), label="Nội dung chi", required=True, max_length=500)

        company_account = None
        supplier_account = None
        cash_recipient_name = _text(
            values.get("cash_recipient_name"), label="Người nhận tiền", max_length=255
        )
        bank_fee_bearer = _text(
            values.get("bank_fee_bearer"), label="Bên chịu phí", max_length=16
        )
        if voucher_type == VOUCHER_CASH:
            if not cash_recipient_name:
                raise AccountingValidationError("Phiếu chi phải có người nhận tiền.")
        else:
            company_id = values.get("company_bank_account_id")
            supplier_account_id = values.get("supplier_bank_account_id")
            company_account = self.repo.get_company_account(int(company_id)) if company_id else None
            supplier_account = self.repo.get_supplier_account(int(supplier_account_id)) if supplier_account_id else None
            if company_account is None or not company_account.is_active:
                raise AccountingValidationError("Vui lòng chọn tài khoản công ty đang hoạt động.")
            if supplier_account is None or not supplier_account.is_active:
                raise AccountingValidationError("Vui lòng chọn tài khoản nhà cung cấp đang hoạt động.")
            if supplier_account.supplier_id != purchase.supplier_id:
                raise AccountingValidationError("Tài khoản thụ hưởng không thuộc nhà cung cấp của PMH.")
            if company_account.currency != currency or supplier_account.currency != currency:
                raise AccountingValidationError("Loại tiền của chứng từ phải khớp với hai tài khoản ngân hàng.")
            bank_fee_bearer = bank_fee_bearer or BANK_FEE_PAYER
            if bank_fee_bearer not in BANK_FEE_BEARERS:
                raise AccountingValidationError("Bên chịu phí ngân hàng không hợp lệ.")

        return {
            "voucher_type": voucher_type,
            "payment_stage": stage,
            "voucher_date": values.get("voucher_date"),
            "planned_payment_date": values.get("planned_payment_date"),
            "amount": amount,
            "amount_vnd": amount_vnd,
            "currency": currency,
            "exchange_rate": exchange_rate,
            "content": content,
            "invoice_number": _text(values.get("invoice_number"), label="Số hóa đơn", max_length=64),
            "invoice_date": values.get("invoice_date"),
            "contract_number": _text(values.get("contract_number"), label="Số hợp đồng", max_length=64),
            "company_account": company_account,
            "supplier_account": supplier_account,
            "cash_recipient_name": cash_recipient_name,
            "cash_recipient_address": _text(values.get("cash_recipient_address"), label="Địa chỉ người nhận", max_length=500),
            "cash_recipient_identity": _text(values.get("cash_recipient_identity"), label="Giấy tờ người nhận", max_length=64),
            "bank_fee_bearer": bank_fee_bearer,
            "note": _text(values.get("note"), label="Ghi chú", max_length=2000),
        }

    def _new_voucher(self, purchase: PurchaseRequest, prepared: dict, actor_id: int) -> PaymentVoucher:
        voucher = PaymentVoucher(
            code=self._new_voucher_code(prepared["voucher_type"]),
            purchase_request_id=purchase.id,
            supplier_id=purchase.supplier_id,
            status=PAYMENT_VOUCHER_WAITING,
            created_by_user_id=actor_id,
        )
        self._apply_voucher(voucher, purchase, prepared)
        return voucher

    def _apply_voucher(self, voucher: PaymentVoucher, purchase: PurchaseRequest, prepared: dict) -> None:
        company = prepared.pop("company_account")
        beneficiary = prepared.pop("supplier_account")
        for key, value in prepared.items():
            setattr(voucher, key, value)
        voucher.company_bank_account_id = company.id if company else None
        voucher.supplier_bank_account_id = beneficiary.id if beneficiary else None
        voucher.source_code_snapshot = purchase.code
        voucher.supplier_id = purchase.supplier_id
        voucher.supplier_name_snapshot = purchase.supplier.name
        voucher.supplier_tax_code_snapshot = purchase.supplier.tax_code
        voucher.supplier_address_snapshot = purchase.supplier.address
        voucher.company_account_holder_snapshot = company.account_holder if company else None
        voucher.company_account_number_snapshot = company.account_number if company else None
        voucher.company_bank_name_snapshot = company.bank_name if company else None
        voucher.company_bank_branch_snapshot = company.bank_branch if company else None
        voucher.beneficiary_account_holder_snapshot = beneficiary.account_holder if beneficiary else None
        voucher.beneficiary_account_number_snapshot = beneficiary.account_number if beneficiary else None
        voucher.beneficiary_bank_name_snapshot = beneficiary.bank_name if beneficiary else None
        voucher.beneficiary_bank_branch_snapshot = beneficiary.bank_branch if beneficiary else None

    def _new_voucher_code(self, voucher_type: str) -> str:
        prefix = "PC" if voucher_type == VOUCHER_CASH else "UNC"
        alphabet = string.ascii_uppercase + string.digits
        date_part = _now().strftime("%y%m%d")
        for _ in range(30):
            suffix = "".join(secrets.choice(alphabet) for _ in range(4))
            code = f"{prefix}-{date_part}-{suffix}"
            if self.repo.get_voucher_by_code(code) is None:
                return code
        raise AccountingConflict("Không sinh được mã chứng từ duy nhất, vui lòng thử lại.")

    def _purchase(self, request_id: int) -> PurchaseRequest:
        row = self.purchases.get_by_id(request_id)
        if row is None:
            raise AccountingNotFound("Không tìm thấy phiếu mua hàng.")
        return row

    def _voucher(self, voucher_id: int) -> PaymentVoucher:
        row = self.repo.get_voucher(voucher_id)
        if row is None:
            raise AccountingNotFound("Không tìm thấy Phiếu chi/UNC.")
        return row

    @staticmethod
    def _purchase_total(purchase: PurchaseRequest) -> int:
        return sum(
            _purchase_line_amounts(
                quantity=float(line.quantity),
                unit_price=int(line.expected_unit_price),
                discount_percent=float(line.discount_percent or 0),
                vat_percent=float(line.vat_percent or 0),
            )[3]
            for line in purchase.lines
        )

    def _supplier_account_out(self, row: SupplierBankAccount) -> dict:
        return {
            "id": row.id,
            "supplier_id": row.supplier_id,
            "supplier_name": row.supplier.name if row.supplier else None,
            "account_holder": row.account_holder,
            "account_number": row.account_number,
            "bank_name": row.bank_name,
            "bank_branch": row.bank_branch,
            "currency": row.currency,
            "is_default": row.is_default,
            "is_active": row.is_active,
            "note": row.note,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    def _user_name(self, user_id: int | None) -> str | None:
        if user_id is None:
            return None
        user = self.users.get_by_id(user_id)
        return user.name if user else None

    def _voucher_out(self, row: PaymentVoucher) -> dict:
        purchase = row.purchase_request
        source_codes = [
            link.department_request.code if link.department_request else link.source_code_snapshot
            for link in purchase.sources
        ] if purchase else []
        purchase_total = self._purchase_total(purchase) if purchase else None
        # Tổng ĐÃ CHI của cả PMH (mọi phiếu chi anh em) — hiện trên dải nhóm.
        purchase_paid_amount = (
            sum(
                int(sibling.amount_vnd)
                for sibling in purchase.payment_vouchers
                if sibling.status == PAYMENT_VOUCHER_PAID
            )
            if purchase
            else None
        )
        receipt_received_amount = sum(
            int(receipt.amount_vnd)
            for receipt in row.receipts
            if receipt.status == PAYMENT_RECEIPT_RECEIVED
        )
        receipt_pending_amount = sum(
            int(receipt.amount_vnd)
            for receipt in row.receipts
            if receipt.status == PAYMENT_RECEIPT_WAITING
        )
        return {
            "id": row.id,
            "code": row.code,
            "receipt_received_amount": receipt_received_amount,
            "receipt_pending_amount": receipt_pending_amount,
            "attachment_count": len(row.attachments),
            "purchase_request_id": row.purchase_request_id,
            "purchase_request_code": purchase.code if purchase else row.source_code_snapshot,
            "purchase_request_total": purchase_total,
            "purchase_paid_amount": purchase_paid_amount,
            # Người phụ trách mua (lập PMH) — mặc định "Người nộp tiền" của phiếu thu.
            "purchase_created_by_name": (
                self._user_name(purchase.created_by_user_id) if purchase else None
            ),
            "source_request_codes": source_codes,
            "supplier_id": row.supplier_id,
            "supplier_name": row.supplier_name_snapshot,
            "supplier_tax_code": row.supplier_tax_code_snapshot,
            "supplier_address": row.supplier_address_snapshot,
            "voucher_type": row.voucher_type,
            "payment_stage": row.payment_stage,
            "status": row.status,
            "voucher_date": row.voucher_date,
            "planned_payment_date": row.planned_payment_date,
            "amount": int(row.amount),
            "amount_vnd": int(row.amount_vnd),
            "currency": row.currency,
            "exchange_rate": float(row.exchange_rate),
            "content": row.content,
            "invoice_number": row.invoice_number,
            "invoice_date": row.invoice_date,
            "contract_number": row.contract_number,
            "company_bank_account_id": row.company_bank_account_id,
            "supplier_bank_account_id": row.supplier_bank_account_id,
            "cash_recipient_name": row.cash_recipient_name,
            "cash_recipient_address": row.cash_recipient_address,
            "cash_recipient_identity": row.cash_recipient_identity,
            "bank_fee_bearer": row.bank_fee_bearer,
            "bank_reference": row.bank_reference,
            "company_account_holder": row.company_account_holder_snapshot,
            "company_account_number": row.company_account_number_snapshot,
            "company_bank_name": row.company_bank_name_snapshot,
            "company_bank_branch": row.company_bank_branch_snapshot,
            "beneficiary_account_holder": row.beneficiary_account_holder_snapshot,
            "beneficiary_account_number": row.beneficiary_account_number_snapshot,
            "beneficiary_bank_name": row.beneficiary_bank_name_snapshot,
            "beneficiary_bank_branch": row.beneficiary_bank_branch_snapshot,
            "created_by_user_id": row.created_by_user_id,
            "created_by_name": self._user_name(row.created_by_user_id),
            "paid_by_user_id": row.paid_by_user_id,
            "paid_by_name": self._user_name(row.paid_by_user_id),
            "paid_at": row.paid_at,
            "cancelled_by_user_id": row.cancelled_by_user_id,
            "cancelled_by_name": self._user_name(row.cancelled_by_user_id),
            "cancelled_at": row.cancelled_at,
            "cancel_reason": row.cancel_reason,
            "note": row.note,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
