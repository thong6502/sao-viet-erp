"""Business service for Thu mua MVP."""
from __future__ import annotations

import secrets
import string
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from ..models.purchase import (
    DEPARTMENT_PURCHASE_SOURCE_TYPES,
    DPR_CANCELLED,
    DPR_DONE,
    DPR_IN_PURCHASE,
    DPR_OPEN,
    DPR_PENDING_APPROVAL,
    DepartmentPurchaseRequest,
    PR_APPROVED,
    PR_CANCELLED,
    PR_DRAFT,
    PR_PENDING,
    PR_PURCHASED,
    PR_RECEIVED,
    PR_REJECTED,
    SUPPLIER_ACTIVE,
    SUPPLIER_INACTIVE,
    SUPPLIER_STATUSES,
    PurchaseRequest,
    Supplier,
)
from ..models.accounting import (
    PAYMENT_RECEIPT_RECEIVED,
    PAYMENT_VOUCHER_PAID,
    PAYMENT_VOUCHER_WAITING,
)
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.purchase_repo import (
    DepartmentPurchaseRequestLineInput,
    DepartmentPurchaseRequestRepository,
    PurchaseRequestLineInput,
    PurchaseRequestRepository,
    SupplierRepository,
)
from ..repositories.user_repo import UserRepository
from .rbac_service import AuthorizationService


class PurchaseError(Exception):
    pass


class PurchaseValidationError(PurchaseError):
    pass


class PurchaseNotFound(PurchaseError):
    pass


class PurchaseConflict(PurchaseError):
    pass


class PurchaseForbidden(PurchaseError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _money_round(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _purchase_line_amounts(
    *,
    quantity: float,
    unit_price: int,
    discount_percent: float,
    vat_percent: float,
) -> tuple[int, int, int, int]:
    gross = _money_round(Decimal(str(quantity)) * Decimal(unit_price))
    discount = _money_round(Decimal(gross) * Decimal(str(discount_percent)) / Decimal(100))
    taxable = max(0, gross - discount)
    vat = _money_round(Decimal(taxable) * Decimal(str(vat_percent)) / Decimal(100))
    return gross, discount, vat, taxable + vat


class PurchaseService:
    def __init__(
        self,
        suppliers: SupplierRepository,
        department_requests: DepartmentPurchaseRequestRepository,
        requests: PurchaseRequestRepository,
        users: UserRepository,
        audit: AuditLogRepository,
        authz: AuthorizationService,
    ) -> None:
        self.suppliers = suppliers
        self.department_requests = department_requests
        self.requests = requests
        self.users = users
        self.audit = audit
        self.authz = authz

    # --- suppliers ---------------------------------------------------------

    def list_suppliers(
        self,
        *,
        q: str | None = None,
        status: str | None = None,
        supplier_group: str | None = None,
        sort: str = "name",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Supplier], int]:
        return self.suppliers.list(
            q=q, status=status, supplier_group=supplier_group, sort=sort, page=page, size=size
        )

    def get_supplier(self, supplier_id: int) -> Supplier:
        supplier = self.suppliers.get_by_id(supplier_id)
        if supplier is None:
            raise PurchaseNotFound("Không tìm thấy nhà cung cấp.")
        return supplier

    def _clean_supplier_values(self, **values) -> dict:
        name = (values.get("name") or "").strip()
        if not name:
            raise PurchaseValidationError("Tên nhà cung cấp không được trống.")
        tax_code = (values.get("tax_code") or "").strip()
        phone = (values.get("phone") or "").strip()
        email = (values.get("email") or "").strip()
        address = (values.get("address") or "").strip()
        contact_name = (values.get("contact_name") or "").strip()
        supplier_group = (values.get("supplier_group") or "").strip()
        required = [
            (tax_code, "Mã số thuế"),
            (phone, "Số điện thoại"),
            (email, "Email"),
            (address, "Địa chỉ"),
            (contact_name, "Người liên hệ"),
            (supplier_group, "Nhóm nhà cung cấp"),
        ]
        missing = [label for value, label in required if not value]
        if missing:
            raise PurchaseValidationError(
                "Nhà cung cấp thiếu thông tin bắt buộc: " + ", ".join(missing) + "."
            )
        status = values.get("status") or SUPPLIER_ACTIVE
        if status not in SUPPLIER_STATUSES:
            raise PurchaseValidationError("Trạng thái nhà cung cấp không hợp lệ.")
        return {
            "name": name,
            "tax_code": tax_code,
            "phone": phone,
            "email": email,
            "address": address,
            "contact_name": contact_name,
            "supplier_group": supplier_group,
            "payment_terms": (values.get("payment_terms") or "").strip() or None,
            "status": status,
            "note": (values.get("note") or "").strip() or None,
        }

    def create_supplier(self, *, actor, **values) -> Supplier:
        cleaned = self._clean_supplier_values(**values)
        existing = self.suppliers.find_by_name(cleaned["name"])
        if existing is not None:
            raise PurchaseConflict("Nhà cung cấp đã tồn tại.")
        supplier = self.suppliers.create(**cleaned)
        self.audit.create(
            actor_user_id=actor.id,
            action="create_supplier",
            target=f"supplier:{supplier.id}",
            detail=supplier.name,
        )
        return supplier

    def update_supplier(self, supplier_id: int, *, actor, **values) -> Supplier:
        supplier = self.get_supplier(supplier_id)
        cleaned = self._clean_supplier_values(**values)
        existing = self.suppliers.find_by_name(cleaned["name"])
        if existing is not None and existing.id != supplier.id:
            raise PurchaseConflict("Nhà cung cấp đã tồn tại.")
        supplier = self.suppliers.update(supplier, **cleaned)
        self.audit.create(
            actor_user_id=actor.id,
            action="update_supplier",
            target=f"supplier:{supplier.id}",
            detail=supplier.name,
        )
        return supplier

    def toggle_supplier_active(self, supplier_id: int, *, actor) -> Supplier:
        supplier = self.get_supplier(supplier_id)
        next_status = SUPPLIER_INACTIVE if supplier.status == SUPPLIER_ACTIVE else SUPPLIER_ACTIVE
        supplier = self.suppliers.update(supplier, status=next_status)
        self.audit.create(
            actor_user_id=actor.id,
            action="toggle_supplier",
            target=f"supplier:{supplier.id}",
            detail=f"{supplier.name} -> {supplier.status}",
        )
        return supplier

    # --- department purchase requests -------------------------------------

    def list_department_requests(
        self,
        *,
        q: str | None = None,
        status: str | None = None,
        source_type: str | None = None,
        sort: str = "-created_at",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict], int]:
        rows, total = self.department_requests.list(
            q=q, status=status, source_type=source_type, sort=sort, page=page, size=size
        )
        return [self._to_department_request_out(row) for row in rows], total

    def _department_request(self, request_id: int) -> DepartmentPurchaseRequest:
        row = self.department_requests.get_by_id(request_id)
        if row is None:
            raise PurchaseNotFound("Khong tim thay phieu yeu cau mua tu phong ban.")
        return row

    def get_department_request(self, request_id: int) -> dict:
        return self._to_department_request_out(self._department_request(request_id))

    def _clean_department_request_header(
        self,
        *,
        source_type: str | None,
        purpose: str | None,
        needed_date: date | None,
    ) -> tuple[str, str, date]:
        cleaned_source_type = (source_type or "").strip()
        if cleaned_source_type not in DEPARTMENT_PURCHASE_SOURCE_TYPES:
            raise PurchaseValidationError("Nguon yeu cau mua khong hop le.")
        cleaned_purpose = (purpose or "").strip()
        if not cleaned_purpose:
            raise PurchaseValidationError("Muc dich yeu cau mua khong duoc trong.")
        if needed_date is None:
            raise PurchaseValidationError("Ngay can hang la thong tin bat buoc.")
        return cleaned_source_type, cleaned_purpose, needed_date

    def _clean_department_lines(self, raw_lines) -> list[DepartmentPurchaseRequestLineInput]:
        if not raw_lines:
            raise PurchaseValidationError("Yeu cau mua phai co it nhat mot dong vat tu.")
        lines: list[DepartmentPurchaseRequestLineInput] = []
        for line in raw_lines:
            get = line.get if isinstance(line, dict) else lambda key, default=None: getattr(line, key, default)
            item_name = (get("item_name") or "").strip()
            if not item_name:
                raise PurchaseValidationError("Ten vat tu khong duoc trong.")
            unit = (get("unit") or "").strip()
            if not unit:
                raise PurchaseValidationError("Don vi tinh khong duoc trong.")
            quantity = float(get("quantity"))
            if quantity <= 0:
                raise PurchaseValidationError("So luong phai lon hon 0.")
            lines.append(
                DepartmentPurchaseRequestLineInput(
                    item_name=item_name,
                    unit=unit,
                    quantity=quantity,
                    expected_unit_price=0,
                    note=(get("note") or "").strip() or None,
                )
            )
        return lines

    def _new_department_request_code(self) -> str:
        today = datetime.now().strftime("%y%m%d")
        alphabet = string.ascii_uppercase + string.digits
        for _ in range(20):
            rand = "".join(secrets.choice(alphabet) for _ in range(4))
            code = f"YCMH-{today}-{rand}"
            if self.department_requests.get_by_code(code) is None:
                return code
        raise PurchaseConflict("Khong sinh duoc ma yeu cau mua duy nhat, vui long thu lai.")

    def create_department_request(
        self,
        *,
        source_type: str | None,
        related_document_type: str | None,
        related_document_code: str | None,
        purpose: str | None,
        needed_date: date | None,
        note: str | None,
        lines,
        actor,
    ) -> dict:
        source_type, cleaned_purpose, needed_date = self._clean_department_request_header(
            source_type=source_type, purpose=purpose, needed_date=needed_date
        )
        row = self.department_requests.create(
            code=self._new_department_request_code(),
            source_type=source_type,
            requesting_department_id=actor.department_id,
            requested_by_user_id=actor.id,
            related_document_type=(related_document_type or "").strip() or None,
            related_document_code=(related_document_code or "").strip() or None,
            purpose=cleaned_purpose,
            needed_date=needed_date,
            note=(note or "").strip() or None,
            lines=self._clean_department_lines(lines),
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="create_department_purchase_request",
            target=f"department_purchase_request:{row.id}",
            detail=row.code,
        )
        return self._to_department_request_out(row)

    def cancel_department_request(self, request_id: int, *, reason: str | None, actor) -> dict:
        row = self._department_request(request_id)
        if row.status != DPR_OPEN:
            raise PurchaseConflict("Chi yeu cau dang cho mua moi duoc huy.")
        can_cancel_any = self.authz.can(actor, "thu_mua", "cancel")
        if row.requested_by_user_id != actor.id and not can_cancel_any:
            raise PurchaseForbidden("Chi nguoi tao yeu cau hoac admin moi duoc huy.")
        row.status = DPR_CANCELLED
        row.note = (reason or "").strip() or row.note
        saved = self.department_requests.save(row)
        self.audit.create(
            actor_user_id=actor.id,
            action="cancel_department_purchase_request",
            target=f"department_purchase_request:{row.id}",
            detail=row.code,
        )
        return self._to_department_request_out(saved)

    # --- purchase requests -------------------------------------------------

    def list_requests(
        self,
        *,
        q: str | None = None,
        status: str | None = None,
        supplier_id: int | None = None,
        sort: str = "-created_at",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict], int]:
        rows, total = self.requests.list(
            q=q, status=status, supplier_id=supplier_id, sort=sort, page=page, size=size
        )
        return [self._to_request_out(r) for r in rows], total

    def get_request(self, request_id: int) -> dict:
        return self._to_request_out(self._request(request_id))

    def _request(self, request_id: int) -> PurchaseRequest:
        row = self.requests.get_by_id(request_id)
        if row is None:
            raise PurchaseNotFound("Không tìm thấy phiếu yêu cầu mua hàng.")
        return row

    def _require_supplier_active(self, supplier_id: int | None) -> None:
        if supplier_id is None:
            raise PurchaseValidationError("Nhà cung cấp là thông tin bắt buộc.")
        supplier = self.suppliers.get_by_id(supplier_id)
        if supplier is None:
            raise PurchaseValidationError("Nhà cung cấp không tồn tại.")
        if supplier.status != SUPPLIER_ACTIVE:
            raise PurchaseValidationError("Nhà cung cấp đang ngừng hợp tác.")

    def _clean_request_header(
        self,
        *,
        supplier_id: int | None,
        purpose: str | None,
        needed_date: date | None,
    ) -> tuple[int, str, date]:
        if supplier_id is None:
            raise PurchaseValidationError("Nhà cung cấp là thông tin bắt buộc.")
        cleaned_purpose = (purpose or "").strip()
        if not cleaned_purpose:
            raise PurchaseValidationError("Mục đích mua hàng không được trống.")
        if needed_date is None:
            raise PurchaseValidationError("Ngày cần hàng là thông tin bắt buộc.")
        return supplier_id, cleaned_purpose, needed_date

    def _clean_lines(self, raw_lines) -> list[PurchaseRequestLineInput]:
        if not raw_lines:
            raise PurchaseValidationError("Phiếu phải có ít nhất một dòng hàng.")
        lines: list[PurchaseRequestLineInput] = []
        for line in raw_lines:
            get = line.get if isinstance(line, dict) else lambda key, default=None: getattr(line, key, default)
            item_name = (get("item_name") or "").strip()
            if not item_name:
                raise PurchaseValidationError("Tên hàng không được trống.")
            unit = (get("unit") or "").strip()
            if not unit:
                raise PurchaseValidationError("Đơn vị tính không được trống.")
            quantity = float(get("quantity"))
            expected_unit_price = int(get("expected_unit_price"))
            discount_percent = float(get("discount_percent") or 0)
            vat_percent = float(get("vat_percent") or 0)
            if quantity <= 0:
                raise PurchaseValidationError("Số lượng phải lớn hơn 0.")
            if expected_unit_price <= 0:
                raise PurchaseValidationError("Đơn giá dự kiến phải lớn hơn 0.")
            if discount_percent < 0 or discount_percent > 100:
                raise PurchaseValidationError("Giảm giá (%) phải trong khoảng 0 đến 100.")
            if vat_percent < 0 or vat_percent > 100:
                raise PurchaseValidationError("Thuế GTGT (%) phải trong khoảng 0 đến 100.")
            lines.append(
                PurchaseRequestLineInput(
                    item_name=item_name,
                    unit=unit,
                    quantity=quantity,
                    expected_unit_price=expected_unit_price,
                    discount_percent=discount_percent,
                    vat_percent=vat_percent,
                    note=(get("note") or "").strip() or None,
                )
            )
        return lines

    def _new_purchase_code(self) -> str:
        today = datetime.now().strftime("%y%m%d")
        alphabet = string.ascii_uppercase + string.digits
        for _ in range(20):
            rand = "".join(secrets.choice(alphabet) for _ in range(4))
            code = f"PMH-{today}-{rand}"
            if self.requests.get_by_code(code) is None:
                return code
        raise PurchaseConflict("Không sinh được mã phiếu duy nhất, vui lòng thử lại.")

    def _resolve_source_requests(
        self,
        source_request_ids,
        *,
        allow_in_purchase: bool = True,
        allowed_reserved_ids: set[int] | None = None,
    ) -> list[DepartmentPurchaseRequest]:
        allowed_reserved_ids = allowed_reserved_ids or set()
        ids: list[int] = []
        seen: set[int] = set()
        for raw_id in source_request_ids or []:
            source_id = int(raw_id)
            if source_id not in seen:
                ids.append(source_id)
                seen.add(source_id)
        if not ids:
            raise PurchaseValidationError("Phieu mua phai gan it nhat mot yeu cau mua tu phong ban.")
        rows = self.department_requests.get_many(ids)
        by_id = {row.id: row for row in rows}
        missing = [str(source_id) for source_id in ids if source_id not in by_id]
        if missing:
            raise PurchaseValidationError("Yeu cau mua khong ton tai: " + ", ".join(missing) + ".")
        blocked = [
            row.code
            for row in rows
            if row.status in (DPR_DONE, DPR_CANCELLED)
            or (
                row.status in (DPR_PENDING_APPROVAL, DPR_IN_PURCHASE)
                and row.id not in allowed_reserved_ids
                and not allow_in_purchase
            )
        ]
        if blocked:
            raise PurchaseValidationError(
                "Yeu cau mua khong con o trang thai cho mua: " + ", ".join(blocked) + "."
            )
        return [by_id[source_id] for source_id in ids]

    def create_request(
        self,
        *,
        supplier_id: int | None,
        purpose: str | None,
        needed_date: date | None,
        expected_receipt_date: date | None = None,
        note: str | None,
        lines,
        source_request_ids,
        actor,
    ) -> dict:
        supplier_id, cleaned_purpose, needed_date = self._clean_request_header(
            supplier_id=supplier_id, purpose=purpose, needed_date=needed_date
        )
        self._require_supplier_active(supplier_id)
        cleaned_lines = self._clean_lines(lines)
        source_requests = self._resolve_source_requests(source_request_ids, allow_in_purchase=False)
        row = self.requests.create(
            code=self._new_purchase_code(),
            supplier_id=supplier_id,
            purpose=cleaned_purpose,
            needed_date=needed_date,
            expected_receipt_date=expected_receipt_date,
            created_by_user_id=actor.id,
            note=(note or "").strip() or None,
            lines=cleaned_lines,
            source_requests=source_requests,
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="create_purchase_request",
            target=f"purchase_request:{row.id}",
            detail=row.code,
        )
        return self._to_request_out(row)

    def update_request(
        self,
        request_id: int,
        *,
        actor,
        supplier_id,
        source_request_ids,
        purpose,
        needed_date,
        expected_receipt_date=None,
        note,
        lines,
    ) -> dict:
        row = self._request(request_id)
        if row.status not in (PR_DRAFT, PR_REJECTED):
            raise PurchaseConflict("Chỉ phiếu nháp hoặc bị từ chối mới được sửa.")
        supplier_id, cleaned_purpose, needed_date = self._clean_request_header(
            supplier_id=supplier_id, purpose=purpose, needed_date=needed_date
        )
        self._require_supplier_active(supplier_id)
        row = self.requests.update_header_and_lines(
            row,
            supplier_id=supplier_id,
            purpose=cleaned_purpose,
            needed_date=needed_date,
            expected_receipt_date=expected_receipt_date,
            note=(note or "").strip() or None,
            lines=self._clean_lines(lines),
            source_requests=self._resolve_source_requests(
                source_request_ids,
                allow_in_purchase=False,
                allowed_reserved_ids={link.department_request_id for link in row.sources},
            ),
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="update_purchase_request",
            target=f"purchase_request:{row.id}",
            detail=row.code,
        )
        return self._to_request_out(row)

    def delete_request(self, request_id: int, *, actor) -> None:
        row = self._request(request_id)
        if row.status != PR_DRAFT:
            raise PurchaseConflict("Chỉ phiếu nháp mới được xóa.")
        code = row.code
        for link in row.sources:
            if link.department_request and link.department_request.status in (DPR_PENDING_APPROVAL, DPR_IN_PURCHASE):
                link.department_request.status = DPR_OPEN
        self.requests.delete(row)
        self.audit.create(
            actor_user_id=actor.id,
            action="delete_purchase_request",
            target=f"purchase_request:{request_id}",
            detail=code,
        )

    def submit(self, request_id: int, *, actor) -> dict:
        row = self._request(request_id)
        if row.status not in (PR_DRAFT, PR_REJECTED):
            raise PurchaseConflict("Chỉ phiếu nháp hoặc bị từ chối mới được gửi duyệt.")
        row.status = PR_PENDING
        row.submitted_at = _now()
        row.approved_by_user_id = None
        row.approved_at = None
        for link in row.sources:
            if link.department_request and link.department_request.status not in (DPR_DONE, DPR_CANCELLED):
                link.department_request.status = DPR_PENDING_APPROVAL
        saved = self.requests.save(row)
        self.audit.create(actor_user_id=actor.id, action="submit_purchase_request", target=f"purchase_request:{row.id}", detail=row.code)
        return self._to_request_out(saved)

    def approve(self, request_id: int, *, actor) -> dict:
        row = self._request(request_id)
        if row.status != PR_PENDING:
            raise PurchaseConflict("Chỉ phiếu đang chờ duyệt mới được duyệt.")
        row.status = PR_APPROVED
        row.approved_by_user_id = actor.id
        row.approved_at = _now()
        for link in row.sources:
            if link.department_request and link.department_request.status not in (DPR_DONE, DPR_CANCELLED):
                link.department_request.status = DPR_IN_PURCHASE
        saved = self.requests.save(row)
        self.audit.create(actor_user_id=actor.id, action="approve_purchase_request", target=f"purchase_request:{row.id}", detail=row.code)
        return self._to_request_out(saved)

    def reject(self, request_id: int, *, reason: str | None, actor) -> dict:
        row = self._request(request_id)
        if row.status != PR_PENDING:
            raise PurchaseConflict("Chỉ phiếu đang chờ duyệt mới được từ chối.")
        row.status = PR_REJECTED
        row.approved_by_user_id = actor.id
        row.approved_at = _now()
        row.note = (reason or "").strip() or row.note
        for link in row.sources:
            if link.department_request and link.department_request.status in (DPR_PENDING_APPROVAL, DPR_IN_PURCHASE):
                link.department_request.status = DPR_OPEN
        saved = self.requests.save(row)
        self.audit.create(actor_user_id=actor.id, action="reject_purchase_request", target=f"purchase_request:{row.id}", detail=row.code)
        return self._to_request_out(saved)

    def mark_purchased(self, request_id: int, *, actor) -> dict:
        row = self._request(request_id)
        if row.status != PR_APPROVED:
            raise PurchaseConflict("Chỉ phiếu đã duyệt mới được đánh dấu đã mua.")
        row.status = PR_PURCHASED
        saved = self.requests.save(row)
        self.audit.create(actor_user_id=actor.id, action="mark_purchase_request_purchased", target=f"purchase_request:{row.id}", detail=row.code)
        return self._to_request_out(saved)

    def mark_received(self, request_id: int, *, actor) -> dict:
        row = self._request(request_id)
        if row.status != PR_PURCHASED:
            raise PurchaseConflict("Chỉ phiếu đã mua mới được đánh dấu đã nhận hàng.")
        row.status = PR_RECEIVED
        for link in row.sources:
            if link.department_request and link.department_request.status != DPR_CANCELLED:
                link.department_request.status = DPR_DONE
        saved = self.requests.save(row)
        self.audit.create(actor_user_id=actor.id, action="mark_purchase_request_received", target=f"purchase_request:{row.id}", detail=row.code)
        return self._to_request_out(saved)

    def cancel(self, request_id: int, *, reason: str | None, actor) -> dict:
        row = self._request(request_id)
        if row.status in (PR_RECEIVED, PR_CANCELLED):
            raise PurchaseConflict("Phiếu đã nhận hàng hoặc đã hủy thì không thể hủy tiếp.")
        if any(
            voucher.status in (PAYMENT_VOUCHER_WAITING, PAYMENT_VOUCHER_PAID)
            for voucher in row.payment_vouchers
        ):
            raise PurchaseConflict("Phiếu đã có chứng từ thanh toán nên không thể hủy.")
        row.status = PR_CANCELLED
        row.note = (reason or "").strip() or row.note
        for link in row.sources:
            if link.department_request and link.department_request.status in (DPR_PENDING_APPROVAL, DPR_IN_PURCHASE):
                link.department_request.status = DPR_OPEN
        saved = self.requests.save(row)
        self.audit.create(actor_user_id=actor.id, action="cancel_purchase_request", target=f"purchase_request:{row.id}", detail=row.code)
        return self._to_request_out(saved)

    # --- output helpers ----------------------------------------------------

    def _user_name(self, user_id: int | None) -> str | None:
        if user_id is None:
            return None
        u = self.users.get_by_id(user_id)
        return u.name if u is not None else None

    def _to_request_out(self, row: PurchaseRequest) -> dict:
        total = 0
        lines = []
        for line in row.lines:
            qty = float(line.quantity)
            unit_price = int(line.expected_unit_price)
            discount_percent = float(line.discount_percent or 0)
            vat_percent = float(line.vat_percent or 0)
            _, discount_amount, vat_amount, line_total = _purchase_line_amounts(
                quantity=qty,
                unit_price=unit_price,
                discount_percent=discount_percent,
                vat_percent=vat_percent,
            )
            total += line_total
            lines.append(
                {
                    "id": line.id,
                    "item_name": line.item_name,
                    "unit": line.unit,
                    "quantity": qty,
                    "expected_unit_price": unit_price,
                    "discount_percent": discount_percent,
                    "discount_amount": discount_amount,
                    "vat_percent": vat_percent,
                    "vat_amount": vat_amount,
                    "line_total": line_total,
                    "note": line.note,
                }
            )
        sources = []
        for link in row.sources:
            source = link.department_request
            sources.append(
                {
                    "id": link.id,
                    "department_request_id": link.department_request_id,
                    "code": source.code if source is not None else link.source_code_snapshot,
                    "status": source.status if source is not None else None,
                    "source_type": source.source_type if source is not None else None,
                    "purpose": source.purpose if source is not None else None,
                    "needed_date": source.needed_date if source is not None else None,
                    "requesting_department_name": (
                        source.requesting_department.name
                        if source is not None and source.requesting_department is not None
                        else None
                    ),
                    "requested_by_name": (
                        source.requested_by.name
                        if source is not None and source.requested_by is not None
                        else None
                    ),
                }
            )
        pending_amount = sum(
            int(voucher.amount_vnd)
            for voucher in row.payment_vouchers
            if voucher.status == PAYMENT_VOUCHER_WAITING
        )
        paid_amount = sum(
            int(voucher.amount_vnd)
            for voucher in row.payment_vouchers
            if voucher.status == PAYMENT_VOUCHER_PAID
        )
        # Tiền ĐÃ THU về (phiếu thu received) làm giảm số đã chi thực;
        # paid_amount giữ số thô để UI hiện tách bạch "đã chi X, đã thu Y".
        receipt_received_amount = sum(
            int(receipt.amount_vnd)
            for voucher in row.payment_vouchers
            for receipt in voucher.receipts
            if receipt.status == PAYMENT_RECEIPT_RECEIVED
        )
        net_paid = paid_amount - receipt_received_amount
        outstanding_amount = max(0, total - net_paid)
        available_amount = max(0, total - net_paid - pending_amount)
        if total > 0 and net_paid >= total:
            payment_status = "paid"
        elif net_paid > 0 or pending_amount > 0:
            payment_status = "partial"
        else:
            payment_status = "unpaid"
        return {
            "id": row.id,
            "code": row.code,
            "status": row.status,
            "supplier_id": row.supplier_id,
            "supplier_name": row.supplier.name if row.supplier else None,
            "purpose": row.purpose,
            "needed_date": row.needed_date,
            "expected_receipt_date": row.expected_receipt_date,
            "created_by_user_id": row.created_by_user_id,
            "created_by_name": self._user_name(row.created_by_user_id),
            "submitted_at": row.submitted_at,
            "approved_by_user_id": row.approved_by_user_id,
            "approved_by_name": self._user_name(row.approved_by_user_id),
            "approved_at": row.approved_at,
            "note": row.note,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "total_estimate": total,
            "pending_amount": pending_amount,
            "paid_amount": paid_amount,
            "receipt_received_amount": receipt_received_amount,
            "outstanding_amount": outstanding_amount,
            "available_amount": available_amount,
            "payment_status": payment_status,
            "payment_voucher_count": len(row.payment_vouchers),
            "sources": sources,
            "lines": lines,
        }

    def _to_department_request_out(self, row: DepartmentPurchaseRequest) -> dict:
        total = 0
        lines = []
        for line in row.lines:
            qty = float(line.quantity)
            unit_price = int(line.expected_unit_price)
            line_total = int(round(qty * unit_price))
            total += line_total
            lines.append(
                {
                    "id": line.id,
                    "item_name": line.item_name,
                    "unit": line.unit,
                    "quantity": qty,
                    "expected_unit_price": unit_price,
                    "line_total": line_total,
                    "note": line.note,
                }
            )
        return {
            "id": row.id,
            "code": row.code,
            "status": row.status,
            "source_type": row.source_type,
            "requesting_department_id": row.requesting_department_id,
            "requesting_department_name": (
                row.requesting_department.name if row.requesting_department is not None else None
            ),
            "requested_by_user_id": row.requested_by_user_id,
            "requested_by_name": row.requested_by.name if row.requested_by is not None else None,
            "related_document_type": row.related_document_type,
            "related_document_code": row.related_document_code,
            "purpose": row.purpose,
            "needed_date": row.needed_date,
            "note": row.note,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "total_estimate": total,
            "lines": lines,
        }
