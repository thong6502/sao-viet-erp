"""Data access for operational accounting and purchase payments."""
from __future__ import annotations

from sqlalchemy import asc, case, desc, func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from ..models.accounting import (
    PAYMENT_RECEIPT_RECEIVED,
    PAYMENT_RECEIPT_WAITING,
    PAYMENT_VOUCHER_PAID,
    RECEIPT_SOURCE_ORDER,
    CompanyBankAccount,
    PaymentReceipt,
    PaymentReceiptAttachment,
    PaymentVoucher,
    PaymentVoucherAttachment,
    SupplierBankAccount,
)
from ..models.purchase import PurchaseRequest, PurchaseRequestSource, Supplier


_VOUCHER_SORTABLE = {
    "code": PaymentVoucher.code,
    "status": PaymentVoucher.status,
    "voucher_date": PaymentVoucher.voucher_date,
    "amount": PaymentVoucher.amount_vnd,
    "created_at": PaymentVoucher.created_at,
}

_RECEIPT_SORTABLE = {
    "code": PaymentReceipt.code,
    "status": PaymentReceipt.status,
    "amount": PaymentReceipt.amount_vnd,
    "created_at": PaymentReceipt.created_at,
}


class AccountingRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- company bank accounts -------------------------------------------

    def list_company_accounts(
        self, *, active_only: bool = False, usage: str | None = None
    ) -> list[CompanyBankAccount]:
        stmt = select(CompanyBankAccount)
        if active_only:
            stmt = stmt.where(CompanyBankAccount.is_active.is_(True))
        if usage == "receive":
            stmt = stmt.where(CompanyBankAccount.use_for_receipts.is_(True))
        elif usage == "pay":
            stmt = stmt.where(CompanyBankAccount.use_for_payments.is_(True))
        return list(
            self.db.execute(
                stmt.order_by(CompanyBankAccount.is_default.desc(), CompanyBankAccount.bank_name, CompanyBankAccount.id)
            ).scalars()
        )

    def get_company_account(self, account_id: int) -> CompanyBankAccount | None:
        return self.db.get(CompanyBankAccount, account_id)

    def save_company_account(
        self, account: CompanyBankAccount, *, make_default: bool = False
    ) -> CompanyBankAccount:
        if make_default:
            self.db.execute(
                update(CompanyBankAccount)
                .where(CompanyBankAccount.id != (account.id or -1))
                .values(is_default=False)
            )
            account.is_default = True
        self.db.add(account)
        self._commit()
        self.db.refresh(account)
        return account

    def company_account_count(self) -> int:
        return self.db.execute(select(func.count()).select_from(CompanyBankAccount)).scalar_one()

    # --- supplier bank accounts ------------------------------------------

    def list_supplier_accounts(
        self, *, supplier_id: int | None = None, active_only: bool = False
    ) -> list[SupplierBankAccount]:
        stmt = select(SupplierBankAccount).options(selectinload(SupplierBankAccount.supplier))
        if supplier_id is not None:
            stmt = stmt.where(SupplierBankAccount.supplier_id == supplier_id)
        if active_only:
            stmt = stmt.where(SupplierBankAccount.is_active.is_(True))
        return list(
            self.db.execute(
                stmt.order_by(
                    SupplierBankAccount.supplier_id,
                    SupplierBankAccount.is_default.desc(),
                    SupplierBankAccount.bank_name,
                    SupplierBankAccount.id,
                )
            ).scalars()
        )

    def get_supplier_account(self, account_id: int) -> SupplierBankAccount | None:
        return self.db.execute(
            select(SupplierBankAccount)
            .options(selectinload(SupplierBankAccount.supplier))
            .where(SupplierBankAccount.id == account_id)
        ).scalars().first()

    def save_supplier_account(
        self, account: SupplierBankAccount, *, make_default: bool = False
    ) -> SupplierBankAccount:
        if make_default:
            self.db.execute(
                update(SupplierBankAccount)
                .where(
                    SupplierBankAccount.supplier_id == account.supplier_id,
                    SupplierBankAccount.id != (account.id or -1),
                )
                .values(is_default=False)
            )
            account.is_default = True
        self.db.add(account)
        self._commit()
        self.db.refresh(account)
        return self.get_supplier_account(account.id) or account

    def supplier_account_count(self, supplier_id: int) -> int:
        return self.db.execute(
            select(func.count())
            .select_from(SupplierBankAccount)
            .where(SupplierBankAccount.supplier_id == supplier_id)
        ).scalar_one()

    # --- vouchers ---------------------------------------------------------

    def get_voucher(self, voucher_id: int) -> PaymentVoucher | None:
        return self.db.execute(self._voucher_stmt().where(PaymentVoucher.id == voucher_id)).scalars().first()

    def get_voucher_by_code(self, code: str) -> PaymentVoucher | None:
        return self.db.execute(
            select(PaymentVoucher).where(PaymentVoucher.code == code)
        ).scalars().first()

    def list_vouchers(
        self,
        *,
        q: str | None = None,
        status: str | None = None,
        source_type: str | None = None,
        voucher_type: str | None = None,
        supplier_id: int | None = None,
        purchase_request_id: int | None = None,
        sort: str = "-created_at",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[PaymentVoucher], int]:
        conditions = []
        if q:
            like = f"%{q.strip().lower()}%"
            conditions.append(
                or_(
                    func.lower(PaymentVoucher.code).like(like),
                    func.lower(func.coalesce(PaymentVoucher.doc_no, "")).like(like),
                    func.lower(PaymentVoucher.source_code_snapshot).like(like),
                    func.lower(PaymentVoucher.supplier_name_snapshot).like(like),
                    func.lower(func.coalesce(PaymentVoucher.cash_recipient_name, "")).like(like),
                    func.lower(func.coalesce(PaymentVoucher.beneficiary_account_holder_snapshot, "")).like(like),
                    func.lower(PaymentVoucher.content).like(like),
                    PaymentVoucher.purchase_request.has(func.lower(PurchaseRequest.code).like(like)),
                    PaymentVoucher.purchase_request.has(
                        PurchaseRequest.sources.any(
                            func.lower(PurchaseRequestSource.source_code_snapshot).like(like)
                        )
                    ),
                )
            )
        if status:
            conditions.append(PaymentVoucher.status == status)
        if source_type:
            conditions.append(PaymentVoucher.source_type == source_type)
        if voucher_type:
            conditions.append(PaymentVoucher.voucher_type == voucher_type)
        if supplier_id is not None:
            conditions.append(PaymentVoucher.supplier_id == supplier_id)
        if purchase_request_id is not None:
            conditions.append(PaymentVoucher.purchase_request_id == purchase_request_id)

        stmt = self._voucher_stmt()
        count_stmt = select(func.count()).select_from(PaymentVoucher)
        for condition in conditions:
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        total = self.db.execute(count_stmt).scalar_one()
        direction = asc
        key = sort or "-created_at"
        if key.startswith("-"):
            direction = desc
            key = key[1:]
        if key == "group":
            # Gom phiếu cùng PMH đứng cạnh nhau; nhóm có phiếu MỚI NHẤT lên đầu
            # (vừa chi bổ sung cho PMH cũ → cả nhóm nổi lên trang 1), trong nhóm
            # đọc theo trình tự lập: tạm ứng → bổ sung → quyết toán.
            latest_in_group = func.max(PaymentVoucher.created_at).over(
                partition_by=PaymentVoucher.purchase_request_id
            )
            stmt = stmt.order_by(
                direction(latest_in_group),
                direction(PaymentVoucher.purchase_request_id),
                PaymentVoucher.created_at.asc(),
                PaymentVoucher.id.asc(),
            )
        else:
            stmt = stmt.order_by(
                direction(_VOUCHER_SORTABLE.get(key, PaymentVoucher.created_at)),
                PaymentVoucher.id.desc(),
            )
        page = max(1, page)
        size = max(1, min(size, 200))
        rows = list(self.db.execute(stmt.offset((page - 1) * size).limit(size)).scalars())
        return rows, total, self._voucher_totals(conditions)

    def _voucher_totals(self, conditions) -> dict:
        """Tổng tiền trên TOÀN BỘ kết quả khớp bộ lọc (không chỉ trang hiện tại) —
        kế toán chi nhiều đợt không phải cộng tay.

        `total_waiting_amount` giữ lại và luôn = 0 kể từ khi bỏ trạng thái "Chờ chi" (06/08/2026):
        phiếu cũ đã được migration `0169` chuyển hết sang `paid`, và không đường nào sinh phiếu
        `waiting` nữa. Giữ khoá để hợp đồng API không vỡ, KHÔNG giữ phép cộng — cộng một thứ luôn
        rỗng chỉ tốn một lần quét bảng mỗi lần mở màn."""
        sums_stmt = select(
            func.coalesce(
                func.sum(
                    case(
                        (PaymentVoucher.status == PAYMENT_VOUCHER_PAID, PaymentVoucher.amount_vnd),
                        else_=0,
                    )
                ),
                0,
            ),
        ).select_from(PaymentVoucher)
        receipts_stmt = (
            select(func.coalesce(func.sum(PaymentReceipt.amount_vnd), 0))
            .join(PaymentVoucher, PaymentReceipt.payment_voucher_id == PaymentVoucher.id)
            .where(PaymentReceipt.status == PAYMENT_RECEIPT_RECEIVED)
        )
        for condition in conditions:
            sums_stmt = sums_stmt.where(condition)
            receipts_stmt = receipts_stmt.where(condition)
        (paid_sum,) = self.db.execute(sums_stmt).one()
        received_sum = self.db.execute(receipts_stmt).scalar_one()
        return {
            "total_paid_amount": int(paid_sum),
            "total_waiting_amount": 0,
            "total_receipt_received_amount": int(received_sum),
        }

    # `reserved_amount` ĐÃ GỠ 06/08/2026: trần lập phiếu chi nay tính trong `purchase_money`
    # (`outstanding_amount` / `tran_dat_coc`) trên đúng tập quan hệ đã eager-load, nên không cần
    # query riêng — và quan trọng hơn: một nguồn số, không phải hai chỗ tự cộng lấy.

    # --- payment receipts ---------------------------------------------------

    def list_receipts(
        self,
        *,
        q: str | None = None,
        status: str | None = None,
        payment_voucher_id: int | None = None,
        source_type: str | None = None,
        sort: str = "-created_at",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[PaymentReceipt], int]:
        conditions = []
        if source_type is not None:
            conditions.append(PaymentReceipt.source_type == source_type)
        if q:
            like = f"%{q.strip().lower()}%"
            conditions.append(
                or_(
                    func.lower(PaymentReceipt.code).like(like),
                    func.lower(func.coalesce(PaymentReceipt.doc_no, "")).like(like),
                    func.lower(PaymentReceipt.voucher_code_snapshot).like(like),
                    func.lower(PaymentReceipt.purchase_code_snapshot).like(like),
                    func.lower(PaymentReceipt.supplier_name_snapshot).like(like),
                    func.lower(PaymentReceipt.order_no_snapshot).like(like),
                    func.lower(PaymentReceipt.customer_name_snapshot).like(like),
                    func.lower(PaymentReceipt.payer_name).like(like),
                    func.lower(PaymentReceipt.content).like(like),
                )
            )
        if status:
            conditions.append(PaymentReceipt.status == status)
        if payment_voucher_id is not None:
            conditions.append(PaymentReceipt.payment_voucher_id == payment_voucher_id)

        stmt = self._receipt_stmt()
        count_stmt = select(func.count()).select_from(PaymentReceipt)
        for condition in conditions:
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        total = self.db.execute(count_stmt).scalar_one()
        direction = asc
        key = sort or "-created_at"
        if key.startswith("-"):
            direction = desc
            key = key[1:]
        stmt = stmt.order_by(
            direction(_RECEIPT_SORTABLE.get(key, PaymentReceipt.created_at)),
            PaymentReceipt.id.desc(),
        )
        page = max(1, page)
        size = max(1, min(size, 200))
        rows = list(self.db.execute(stmt.offset((page - 1) * size).limit(size)).scalars())
        return rows, total

    def get_receipt(self, receipt_id: int) -> PaymentReceipt | None:
        return self.db.execute(
            self._receipt_stmt().where(PaymentReceipt.id == receipt_id)
        ).scalar_one_or_none()

    def get_receipt_by_code(self, code: str) -> PaymentReceipt | None:
        return self.db.execute(
            select(PaymentReceipt).where(PaymentReceipt.code == code)
        ).scalar_one_or_none()

    def receipt_reserved_amount(self, payment_voucher_id: int, *, exclude_id: int | None = None) -> int:
        """Tổng thu đang chiếm chỗ trên một phiếu chi (chờ thu + đã thu)."""
        stmt = select(func.coalesce(func.sum(PaymentReceipt.amount_vnd), 0)).where(
            PaymentReceipt.payment_voucher_id == payment_voucher_id,
            PaymentReceipt.status.in_((PAYMENT_RECEIPT_WAITING, PAYMENT_RECEIPT_RECEIVED)),
        )
        if exclude_id is not None:
            stmt = stmt.where(PaymentReceipt.id != exclude_id)
        return int(self.db.execute(stmt).scalar_one())

    def receipt_received_amount(self, purchase_request_id: int) -> int:
        stmt = select(func.coalesce(func.sum(PaymentReceipt.amount_vnd), 0)).where(
            PaymentReceipt.purchase_request_id == purchase_request_id,
            PaymentReceipt.status == PAYMENT_RECEIPT_RECEIVED,
        )
        return int(self.db.execute(stmt).scalar_one())

    def receipt_received_sum_for_order(self, order_id: int) -> int:
        """Σ phiếu thu ĐÃ THU của một đơn bán (cổng chốt đơn đọc số này)."""
        stmt = select(func.coalesce(func.sum(PaymentReceipt.amount_vnd), 0)).where(
            PaymentReceipt.order_id == order_id,
            PaymentReceipt.status == PAYMENT_RECEIPT_RECEIVED,
        )
        return int(self.db.execute(stmt).scalar_one())

    def list_receipts_for_order(self, order_id: int) -> list[PaymentReceipt]:
        """Các phiếu thu (mọi trạng thái) của một đơn bán, mới nhất trước."""
        stmt = (
            self._receipt_stmt()
            .where(PaymentReceipt.order_id == order_id)
            .order_by(PaymentReceipt.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    # --- Cầu nối cho module Đơn hàng (erp V5) — cọc = phiếu thu source=order --
    # order_service (bản erp) đọc cọc qua 3 hàm này; giữ ĐÚNG ngữ nghĩa erp (lọc theo
    # source_type=order, dùng `amount`, list theo id tăng dần) để không phải sửa order_service.
    def received_deposit_sum(self, order_id: int) -> int:
        """Σ tiền THỰC thu của phiếu thu cọc (source=order, đã 'received') gắn đơn —
        base cổng đủ cọc. 0 nếu chưa có phiếu received."""
        stmt = select(func.coalesce(func.sum(PaymentReceipt.amount), 0)).where(
            PaymentReceipt.order_id == order_id,
            PaymentReceipt.source_type == RECEIPT_SOURCE_ORDER,
            PaymentReceipt.status == PAYMENT_RECEIPT_RECEIVED,
        )
        return int(self.db.execute(stmt).scalar_one())

    def received_deposit_sums(self, order_ids: list[int]) -> dict[int, int]:
        """Batch của received_deposit_sum: `{order_id: Σ tiền đã thu}` cho nhiều đơn (KPI, tránh
        N+1). Chỉ đơn có phiếu 'received' mới xuất hiện trong map."""
        if not order_ids:
            return {}
        stmt = (
            select(PaymentReceipt.order_id, func.coalesce(func.sum(PaymentReceipt.amount), 0))
            .where(
                PaymentReceipt.order_id.in_(order_ids),
                PaymentReceipt.source_type == RECEIPT_SOURCE_ORDER,
                PaymentReceipt.status == PAYMENT_RECEIPT_RECEIVED,
            )
            .group_by(PaymentReceipt.order_id)
        )
        return {int(oid): int(s) for oid, s in self.db.execute(stmt)}

    def list_order_receipts(self, order_id: int) -> list[PaymentReceipt]:
        """Mọi phiếu thu cọc của một đơn (mọi trạng thái) — FE hiện danh sách + đi tới màn
        Phiếu thu Kế toán. Sắp theo thứ tự lập (id tăng dần)."""
        return list(
            self.db.execute(
                select(PaymentReceipt)
                .where(
                    PaymentReceipt.order_id == order_id,
                    PaymentReceipt.source_type == RECEIPT_SOURCE_ORDER,
                )
                .order_by(PaymentReceipt.id.asc())
            ).scalars()
        )

    def save_receipt(self, receipt: PaymentReceipt) -> PaymentReceipt:
        self.db.add(receipt)
        self._commit()
        self.db.refresh(receipt)
        return self.get_receipt(receipt.id) or receipt

    def _receipt_stmt(self):
        return select(PaymentReceipt).options(
            selectinload(PaymentReceipt.payment_voucher),
            selectinload(PaymentReceipt.company_bank_account),
            selectinload(PaymentReceipt.attachments),
        )

    # --- receipt attachments ------------------------------------------------

    def list_receipt_attachments(self, payment_receipt_id: int) -> list[PaymentReceiptAttachment]:
        return list(
            self.db.execute(
                select(PaymentReceiptAttachment)
                .where(PaymentReceiptAttachment.payment_receipt_id == payment_receipt_id)
                .order_by(
                    PaymentReceiptAttachment.uploaded_at,
                    PaymentReceiptAttachment.id,
                )
            ).scalars()
        )

    def get_receipt_attachment(self, attachment_id: int) -> PaymentReceiptAttachment | None:
        return self.db.get(PaymentReceiptAttachment, attachment_id)

    def save_receipt_attachment(
        self, attachment: PaymentReceiptAttachment
    ) -> PaymentReceiptAttachment:
        self.db.add(attachment)
        self._commit()
        self.db.refresh(attachment)
        return attachment

    def delete_receipt_attachment(self, attachment: PaymentReceiptAttachment) -> None:
        self.db.delete(attachment)
        self._commit()

    def save_voucher(self, voucher: PaymentVoucher) -> PaymentVoucher:
        self.db.add(voucher)
        self._commit()
        self.db.refresh(voucher)
        return self.get_voucher(voucher.id) or voucher

    # --- voucher attachments ------------------------------------------------

    def list_attachments(self, payment_voucher_id: int) -> list[PaymentVoucherAttachment]:
        return list(
            self.db.execute(
                select(PaymentVoucherAttachment)
                .where(PaymentVoucherAttachment.payment_voucher_id == payment_voucher_id)
                .order_by(
                    PaymentVoucherAttachment.uploaded_at,
                    PaymentVoucherAttachment.id,
                )
            ).scalars()
        )

    def get_attachment(self, attachment_id: int) -> PaymentVoucherAttachment | None:
        return self.db.get(PaymentVoucherAttachment, attachment_id)

    def save_attachment(self, attachment: PaymentVoucherAttachment) -> PaymentVoucherAttachment:
        self.db.add(attachment)
        self._commit()
        self.db.refresh(attachment)
        return attachment

    def delete_attachment(self, attachment: PaymentVoucherAttachment) -> None:
        self.db.delete(attachment)
        self._commit()

    def _voucher_stmt(self):
        return select(PaymentVoucher).options(
            selectinload(PaymentVoucher.purchase_request).selectinload(PurchaseRequest.lines),
            selectinload(PaymentVoucher.purchase_request)
            .selectinload(PurchaseRequest.sources)
            .selectinload(PurchaseRequestSource.department_request),
            # Các phiếu chi anh em cùng PMH — tính "PMH đã chi" cho dải nhóm.
            selectinload(PaymentVoucher.purchase_request).selectinload(
                PurchaseRequest.payment_vouchers
            ),
            selectinload(PaymentVoucher.supplier),
            selectinload(PaymentVoucher.company_bank_account),
            selectinload(PaymentVoucher.supplier_bank_account),
            selectinload(PaymentVoucher.receipts),
            selectinload(PaymentVoucher.attachments),
        )

    def _commit(self) -> None:
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
