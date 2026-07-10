"""Repositories for Thu mua (suppliers + purchase requests)."""
from __future__ import annotations

from datetime import date
from typing import Sequence

from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..models.purchase import (
    DPR_IN_PURCHASE,
    DPR_OPEN,
    DPR_PENDING_APPROVAL,
    DepartmentPurchaseRequest,
    DepartmentPurchaseRequestLine,
    PR_DRAFT,
    SUPPLIER_ACTIVE,
    PurchaseRequest,
    PurchaseRequestLine,
    PurchaseRequestSource,
    Supplier,
)


_SUPPLIER_SORTABLE = {
    "name": Supplier.name,
    "tax_code": Supplier.tax_code,
    "created_at": Supplier.created_at,
}

_REQUEST_SORTABLE = {
    "code": PurchaseRequest.code,
    "status": PurchaseRequest.status,
    "needed_date": PurchaseRequest.needed_date,
    "created_at": PurchaseRequest.created_at,
}

_DEPARTMENT_REQUEST_SORTABLE = {
    "code": DepartmentPurchaseRequest.code,
    "status": DepartmentPurchaseRequest.status,
    "needed_date": DepartmentPurchaseRequest.needed_date,
    "created_at": DepartmentPurchaseRequest.created_at,
}


class SupplierRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, supplier_id: int) -> Supplier | None:
        return self.db.get(Supplier, supplier_id)

    def find_by_name(self, name: str) -> Supplier | None:
        name = (name or "").strip()
        if not name:
            return None
        return self.db.execute(
            select(Supplier).where(func.lower(Supplier.name) == name.lower())
        ).scalars().first()

    def list(
        self,
        *,
        q: str | None = None,
        status: str | None = None,
        supplier_group: str | None = None,
        sort: str = "name",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Supplier], int]:
        conditions = []
        if q:
            like = f"%{q.strip().lower()}%"
            conditions.append(
                or_(
                    func.lower(Supplier.name).like(like),
                    func.lower(Supplier.tax_code).like(like),
                    func.lower(Supplier.phone).like(like),
                )
            )
        if status:
            conditions.append(Supplier.status == status)
        if supplier_group:
            conditions.append(Supplier.supplier_group == supplier_group)

        stmt = select(Supplier)
        count_stmt = select(func.count()).select_from(Supplier)
        for c in conditions:
            stmt = stmt.where(c)
            count_stmt = count_stmt.where(c)

        total = self.db.execute(count_stmt).scalar_one()
        direction = asc
        key = sort or "name"
        if key.startswith("-"):
            direction = desc
            key = key[1:]
        stmt = stmt.order_by(direction(_SUPPLIER_SORTABLE.get(key, Supplier.name)), Supplier.id.asc())
        page = max(1, page)
        size = max(1, min(size, 200))
        rows = list(self.db.execute(stmt.offset((page - 1) * size).limit(size)).scalars())
        return rows, total

    def create(
        self,
        *,
        name: str,
        tax_code: str | None = None,
        phone: str | None = None,
        email: str | None = None,
        address: str | None = None,
        contact_name: str | None = None,
        supplier_group: str | None = None,
        payment_terms: str | None = None,
        status: str = SUPPLIER_ACTIVE,
        note: str | None = None,
    ) -> Supplier:
        row = Supplier(
            name=name,
            tax_code=tax_code,
            phone=phone,
            email=email,
            address=address,
            contact_name=contact_name,
            supplier_group=supplier_group,
            payment_terms=payment_terms,
            status=status,
            note=note,
        )
        self.db.add(row)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.db.refresh(row)
        return row

    def update(self, supplier: Supplier, **values) -> Supplier:
        for key, value in values.items():
            setattr(supplier, key, value)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.db.refresh(supplier)
        return supplier


class PurchaseRequestLineInput:
    def __init__(
        self,
        *,
        item_name: str,
        unit: str,
        quantity: float,
        expected_unit_price: int,
        discount_percent: float = 0,
        vat_percent: float = 0,
        note: str | None = None,
    ) -> None:
        self.item_name = item_name
        self.unit = unit
        self.quantity = quantity
        self.expected_unit_price = expected_unit_price
        self.discount_percent = discount_percent
        self.vat_percent = vat_percent
        self.note = note


class DepartmentPurchaseRequestLineInput:
    def __init__(
        self,
        *,
        item_name: str,
        unit: str,
        quantity: float,
        expected_unit_price: int = 0,
        note: str | None = None,
    ) -> None:
        self.item_name = item_name
        self.unit = unit
        self.quantity = quantity
        self.expected_unit_price = expected_unit_price
        self.note = note


class DepartmentPurchaseRequestRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, request_id: int) -> DepartmentPurchaseRequest | None:
        return self.db.execute(
            select(DepartmentPurchaseRequest)
            .options(
                selectinload(DepartmentPurchaseRequest.lines),
                selectinload(DepartmentPurchaseRequest.requesting_department),
                selectinload(DepartmentPurchaseRequest.requested_by),
            )
            .where(DepartmentPurchaseRequest.id == request_id)
        ).scalars().first()

    def get_by_code(self, code: str) -> DepartmentPurchaseRequest | None:
        return self.db.execute(
            select(DepartmentPurchaseRequest).where(DepartmentPurchaseRequest.code == code)
        ).scalars().first()

    def get_many(self, ids: Sequence[int]) -> list[DepartmentPurchaseRequest]:
        if not ids:
            return []
        return list(
            self.db.execute(
                select(DepartmentPurchaseRequest)
                .options(
                    selectinload(DepartmentPurchaseRequest.lines),
                    selectinload(DepartmentPurchaseRequest.requesting_department),
                    selectinload(DepartmentPurchaseRequest.requested_by),
                )
                .where(DepartmentPurchaseRequest.id.in_(list(ids)))
            ).scalars()
        )

    def list(
        self,
        *,
        q: str | None = None,
        status: str | None = None,
        source_type: str | None = None,
        sort: str = "-created_at",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[DepartmentPurchaseRequest], int]:
        conditions = []
        if q:
            like = f"%{q.strip().lower()}%"
            conditions.append(
                or_(
                    func.lower(DepartmentPurchaseRequest.code).like(like),
                    func.lower(DepartmentPurchaseRequest.purpose).like(like),
                    func.lower(DepartmentPurchaseRequest.related_document_code).like(like),
                    func.lower(DepartmentPurchaseRequest.note).like(like),
                )
            )
        if status:
            conditions.append(DepartmentPurchaseRequest.status == status)
        if source_type:
            conditions.append(DepartmentPurchaseRequest.source_type == source_type)

        stmt = select(DepartmentPurchaseRequest).options(
            selectinload(DepartmentPurchaseRequest.lines),
            selectinload(DepartmentPurchaseRequest.requesting_department),
            selectinload(DepartmentPurchaseRequest.requested_by),
        )
        count_stmt = select(func.count()).select_from(DepartmentPurchaseRequest)
        for c in conditions:
            stmt = stmt.where(c)
            count_stmt = count_stmt.where(c)

        total = self.db.execute(count_stmt).scalar_one()
        direction = asc
        key = sort or "-created_at"
        if key.startswith("-"):
            direction = desc
            key = key[1:]
        stmt = stmt.order_by(
            direction(_DEPARTMENT_REQUEST_SORTABLE.get(key, DepartmentPurchaseRequest.created_at)),
            DepartmentPurchaseRequest.id.desc(),
        )
        page = max(1, page)
        size = max(1, min(size, 200))
        rows = list(self.db.execute(stmt.offset((page - 1) * size).limit(size)).scalars())
        return rows, total

    def create(
        self,
        *,
        code: str,
        source_type: str,
        requesting_department_id: int | None,
        requested_by_user_id: int | None,
        related_document_type: str | None,
        related_document_code: str | None,
        purpose: str,
        needed_date: date,
        note: str | None,
        lines: Sequence[DepartmentPurchaseRequestLineInput],
    ) -> DepartmentPurchaseRequest:
        row = DepartmentPurchaseRequest(
            code=code,
            status=DPR_OPEN,
            source_type=source_type,
            requesting_department_id=requesting_department_id,
            requested_by_user_id=requested_by_user_id,
            related_document_type=related_document_type,
            related_document_code=related_document_code,
            purpose=purpose,
            needed_date=needed_date,
            note=note,
        )
        row.lines = [
            DepartmentPurchaseRequestLine(
                item_name=line.item_name,
                unit=line.unit,
                quantity=line.quantity,
                expected_unit_price=line.expected_unit_price,
                note=line.note,
            )
            for line in lines
        ]
        self.db.add(row)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.db.refresh(row)
        return self.get_by_id(row.id) or row

    def save(self, request: DepartmentPurchaseRequest) -> DepartmentPurchaseRequest:
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.db.refresh(request)
        return self.get_by_id(request.id) or request


class PurchaseRequestRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, request_id: int) -> PurchaseRequest | None:
        return self.db.execute(
            select(PurchaseRequest)
            .options(
                selectinload(PurchaseRequest.lines),
                selectinload(PurchaseRequest.supplier),
                selectinload(PurchaseRequest.sources).selectinload(PurchaseRequestSource.department_request),
                selectinload(PurchaseRequest.payment_vouchers),
            )
            .where(PurchaseRequest.id == request_id)
        ).scalars().first()

    def get_by_code(self, code: str) -> PurchaseRequest | None:
        return self.db.execute(
            select(PurchaseRequest).where(PurchaseRequest.code == code)
        ).scalars().first()

    def list(
        self,
        *,
        q: str | None = None,
        status: str | None = None,
        supplier_id: int | None = None,
        sort: str = "-created_at",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[PurchaseRequest], int]:
        conditions = []
        if q:
            like = f"%{q.strip().lower()}%"
            conditions.append(
                or_(
                    func.lower(PurchaseRequest.code).like(like),
                    func.lower(PurchaseRequest.purpose).like(like),
                    func.lower(PurchaseRequest.note).like(like),
                    PurchaseRequest.supplier.has(func.lower(Supplier.name).like(like)),
                    PurchaseRequest.sources.any(
                        func.lower(PurchaseRequestSource.source_code_snapshot).like(like)
                    ),
                )
            )
        if status:
            conditions.append(PurchaseRequest.status == status)
        if supplier_id is not None:
            conditions.append(PurchaseRequest.supplier_id == supplier_id)

        stmt = select(PurchaseRequest).options(
            selectinload(PurchaseRequest.lines),
            selectinload(PurchaseRequest.supplier),
            selectinload(PurchaseRequest.sources).selectinload(PurchaseRequestSource.department_request),
            selectinload(PurchaseRequest.payment_vouchers),
        )
        count_stmt = select(func.count()).select_from(PurchaseRequest)
        for c in conditions:
            stmt = stmt.where(c)
            count_stmt = count_stmt.where(c)

        total = self.db.execute(count_stmt).scalar_one()
        direction = asc
        key = sort or "-created_at"
        if key.startswith("-"):
            direction = desc
            key = key[1:]
        stmt = stmt.order_by(direction(_REQUEST_SORTABLE.get(key, PurchaseRequest.created_at)), PurchaseRequest.id.desc())
        page = max(1, page)
        size = max(1, min(size, 200))
        rows = list(self.db.execute(stmt.offset((page - 1) * size).limit(size)).scalars())
        return rows, total

    def create(
        self,
        *,
        code: str,
        supplier_id: int | None,
        purpose: str | None,
        needed_date: date | None,
        created_by_user_id: int | None,
        note: str | None,
        lines: Sequence[PurchaseRequestLineInput],
        source_requests: Sequence[DepartmentPurchaseRequest],
    ) -> PurchaseRequest:
        row = PurchaseRequest(
            code=code,
            status=PR_DRAFT,
            supplier_id=supplier_id,
            purpose=purpose,
            needed_date=needed_date,
            created_by_user_id=created_by_user_id,
            note=note,
        )
        row.lines = [
            PurchaseRequestLine(
                item_name=line.item_name,
                unit=line.unit,
                quantity=line.quantity,
                expected_unit_price=line.expected_unit_price,
                discount_percent=line.discount_percent,
                vat_percent=line.vat_percent,
                note=line.note,
            )
            for line in lines
        ]
        self._replace_sources(row, source_requests)
        self.db.add(row)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.db.refresh(row)
        return self.get_by_id(row.id) or row

    def update_header_and_lines(
        self,
        request: PurchaseRequest,
        *,
        supplier_id: int | None,
        purpose: str | None,
        needed_date: date | None,
        note: str | None,
        lines: Sequence[PurchaseRequestLineInput],
        source_requests: Sequence[DepartmentPurchaseRequest],
    ) -> PurchaseRequest:
        request.supplier_id = supplier_id
        request.purpose = purpose
        request.needed_date = needed_date
        request.note = note
        request.lines = [
            PurchaseRequestLine(
                item_name=line.item_name,
                unit=line.unit,
                quantity=line.quantity,
                expected_unit_price=line.expected_unit_price,
                discount_percent=line.discount_percent,
                vat_percent=line.vat_percent,
                note=line.note,
            )
            for line in lines
        ]
        self._replace_sources(request, source_requests)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.db.refresh(request)
        return self.get_by_id(request.id) or request

    def save(self, request: PurchaseRequest) -> PurchaseRequest:
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.db.refresh(request)
        return request

    def delete(self, request: PurchaseRequest) -> None:
        self.db.delete(request)
        self.db.commit()

    def _replace_sources(
        self,
        request: PurchaseRequest,
        source_requests: Sequence[DepartmentPurchaseRequest],
    ) -> None:
        old_sources = {
            link.department_request_id: link.department_request
            for link in getattr(request, "sources", [])
            if link.department_request is not None
        }
        new_ids = {source.id for source in source_requests}
        for source_id, source in old_sources.items():
            if source_id not in new_ids and source.status in (DPR_PENDING_APPROVAL, DPR_IN_PURCHASE):
                source.status = DPR_OPEN
        for source in source_requests:
            source.status = DPR_PENDING_APPROVAL
        request.sources = [
            PurchaseRequestSource(
                department_request_id=source.id,
                source_code_snapshot=source.code,
            )
            for source in source_requests
        ]
