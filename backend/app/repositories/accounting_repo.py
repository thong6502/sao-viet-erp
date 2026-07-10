"""Data access for operational accounting and purchase payments."""
from __future__ import annotations

from sqlalchemy import asc, desc, func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from ..models.accounting import (
    PAYMENT_VOUCHER_PAID,
    PAYMENT_VOUCHER_WAITING,
    CompanyBankAccount,
    PaymentVoucher,
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


class AccountingRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- company bank accounts -------------------------------------------

    def list_company_accounts(self, *, active_only: bool = False) -> list[CompanyBankAccount]:
        stmt = select(CompanyBankAccount)
        if active_only:
            stmt = stmt.where(CompanyBankAccount.is_active.is_(True))
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
                    func.lower(PaymentVoucher.source_code_snapshot).like(like),
                    func.lower(PaymentVoucher.supplier_name_snapshot).like(like),
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
        stmt = stmt.order_by(
            direction(_VOUCHER_SORTABLE.get(key, PaymentVoucher.created_at)),
            PaymentVoucher.id.desc(),
        )
        page = max(1, page)
        size = max(1, min(size, 200))
        rows = list(self.db.execute(stmt.offset((page - 1) * size).limit(size)).scalars())
        return rows, total

    def reserved_amount(self, purchase_request_id: int, *, exclude_id: int | None = None) -> int:
        stmt = select(func.coalesce(func.sum(PaymentVoucher.amount_vnd), 0)).where(
            PaymentVoucher.purchase_request_id == purchase_request_id,
            PaymentVoucher.status.in_((PAYMENT_VOUCHER_WAITING, PAYMENT_VOUCHER_PAID)),
        )
        if exclude_id is not None:
            stmt = stmt.where(PaymentVoucher.id != exclude_id)
        return int(self.db.execute(stmt).scalar_one())

    def save_voucher(self, voucher: PaymentVoucher) -> PaymentVoucher:
        self.db.add(voucher)
        self._commit()
        self.db.refresh(voucher)
        return self.get_voucher(voucher.id) or voucher

    def _voucher_stmt(self):
        return select(PaymentVoucher).options(
            selectinload(PaymentVoucher.purchase_request).selectinload(PurchaseRequest.lines),
            selectinload(PaymentVoucher.purchase_request)
            .selectinload(PurchaseRequest.sources)
            .selectinload(PurchaseRequestSource.department_request),
            selectinload(PaymentVoucher.supplier),
            selectinload(PaymentVoucher.company_bank_account),
            selectinload(PaymentVoucher.supplier_bank_account),
        )

    def _commit(self) -> None:
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
