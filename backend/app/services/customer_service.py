"""Customer (Khách hàng / CRM) business logic — spec-06-khach-hang.

Framework-agnostic: raises domain errors the router maps to HTTP. Enforces the spec's
rules:
  - name is required (non-blank);
  - MST (tax_code) is optional, but if present must be 10 or 13 digits (suy luận VN);
  - a duplicate MST is a SOFT warning — the customer is STILL created (§34 L885, §41
    L1133 "check trùng" ≠ hard block);
  - credit_limit ≥ 0 (VND integer);
  - default sale = the acting user;
  - every create/update writes an AuditLog (đổi Sale/hạn mức ghi rõ before→after).

The receivable side of the credit picture (dư nợ) is NOT owned here — it is read via
SEAM-16 (`CustomerReceivablePort`), which currently RAISES (chưa back-fill). The
service surfaces that as an explicit "unavailable" flag; it NEVER fabricates a 0
balance (a fake 0 would hide an over-limit customer).
"""
from __future__ import annotations

import re

from ..models.customer import CUSTOMER_STATUSES, STATUS_ACTIVE, Customer
from ..models.role import SCOPE_OWN
from ..ports.customer_finance_port import (
    CustomerReceivablePort,
    default_receivable_port,
)
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.customer_repo import CustomerRepository

# MST is 10 digits (doanh nghiệp) or 13 digits (đơn vị trực thuộc: 10 + '-' + 3, but we
# store digits only) — suy luận theo chuẩn VN, chưa xác nhận với người giao.
_MST_RE = re.compile(r"^\d{10}$|^\d{13}$")


class CustomerError(Exception):
    """Base for customer domain errors."""


class CustomerValidationError(CustomerError):
    """A field failed validation (name blank, MST format, negative limit…)."""


class CustomerNotFound(CustomerError):
    """No customer with that id (or not visible under the caller's scope)."""


class CustomerForbidden(CustomerError):
    """The customer exists but is outside the caller's data scope."""


class ReassignForbidden(CustomerError):
    """Đổi NV phụ trách qua nút Sửa khi không có quyền chi tiết `reassign` (Cách B).

    Chốt ở service để endpoint Sửa chung không thành đường vòng né quyền Điều chuyển."""


class ReceivableUnavailable(Exception):
    """The AR balance could not be read because Công nợ (SEAM-16) is not built yet.

    Carries the credit_limit so the UI can still show the limit side of the card.
    """


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


class CustomerService:
    def __init__(
        self,
        customers: CustomerRepository,
        audit: AuditLogRepository,
        receivable_port: CustomerReceivablePort | None = None,
    ) -> None:
        self.customers = customers
        self.audit = audit
        # DIP: the consumer owns the port; default is the raising stub until Công nợ
        # back-fills SEAM-16. Injectable so a test / real provider can swap it in.
        self.receivable = receivable_port or default_receivable_port()

    # --- validation helpers -------------------------------------------------

    @staticmethod
    def _validate_name(name: str | None) -> str:
        name = (name or "").strip()
        if not name:
            raise CustomerValidationError("Tên khách hàng là bắt buộc.")
        return name

    @staticmethod
    def _validate_tax_code(tax_code: str | None) -> str | None:
        tax_code = _clean(tax_code)
        if tax_code is None:
            return None
        if not _MST_RE.match(tax_code):
            raise CustomerValidationError("MST phải gồm 10 hoặc 13 chữ số.")
        return tax_code

    @staticmethod
    def _validate_credit_limit(credit_limit: int | None) -> int:
        if credit_limit is None:
            return 0
        if not isinstance(credit_limit, int) or isinstance(credit_limit, bool):
            raise CustomerValidationError("Hạn mức phải là số nguyên (VND).")
        if credit_limit < 0:
            raise CustomerValidationError("Hạn mức không được âm.")
        return credit_limit

    @staticmethod
    def _validate_status(status: str | None) -> str:
        status = (status or STATUS_ACTIVE).strip()
        if status not in CUSTOMER_STATUSES:
            raise CustomerValidationError("Trạng thái không hợp lệ.")
        return status

    # --- reads --------------------------------------------------------------

    def list_customers(
        self,
        *,
        scope: str,
        actor,
        q: str | None = None,
        sale_user_id: int | None = None,
        sort: str = "code",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Customer], int]:
        return self.customers.list(
            scope=scope,
            actor=actor,
            q=q,
            sale_user_id=sale_user_id,
            sort=sort,
            page=page,
            size=size,
        )

    def list_scoped_all(self, *, scope: str, actor) -> list[Customer]:
        """Whole scoped book (unpaginated) — for the CRM-360 KPI header roll-up."""
        return self.customers.list_scoped_all(scope=scope, actor=actor)

    def get_customer(self, *, customer_id: int, scope: str, actor) -> Customer:
        customer = self.customers.get_by_id(customer_id)
        if customer is None:
            raise CustomerNotFound("Không tìm thấy khách hàng.")
        if not self.customers.can_access(customer=customer, scope=scope, actor=actor):
            # Outside scope: treat as not-found so a Sale can't probe ids of others.
            raise CustomerForbidden("Bạn không có quyền xem khách hàng này.")
        return customer

    def receivable_balance(self, customer_id: int) -> int:
        """AR balance via SEAM-16. Raises ReceivableUnavailable when Công nợ is not
        built (the port stub raises NotImplementedError). NEVER returns a fake 0."""
        try:
            return self.receivable.get_ar_balance(customer_id)
        except NotImplementedError as exc:
            # SEAM-16: chờ Tài chính–Kế toán (cong_no)
            raise ReceivableUnavailable(str(exc)) from exc

    def find_duplicate_tax_code(self, tax_code: str | None) -> Customer | None:
        """The existing customer that already carries this MST, if any (soft warning)."""
        tax_code = _clean(tax_code)
        if tax_code is None:
            return None
        return self.customers.find_by_tax_code(tax_code)

    # --- writes -------------------------------------------------------------

    def create_customer(
        self,
        *,
        name: str,
        tax_code: str | None,
        phone: str | None,
        email: str | None,
        address: str | None,
        contact_name: str | None,
        credit_limit: int | None,
        sale_user_id: int | None,
        actor,
    ) -> tuple[Customer, Customer | None]:
        """Create a customer. Returns (customer, duplicate_or_None). A duplicate MST does
        NOT block creation — it is reported so the UI can warn + link (§34 L885)."""
        name = self._validate_name(name)
        tax_code = self._validate_tax_code(tax_code)
        credit_limit = self._validate_credit_limit(credit_limit)
        # Default owning Sale = the acting user (spec-06 KH-02).
        if sale_user_id is None:
            sale_user_id = actor.id

        duplicate = self.customers.find_by_tax_code(tax_code) if tax_code else None

        customer = self.customers.create(
            name=name,
            tax_code=tax_code,
            phone=_clean(phone),
            email=_clean(email),
            address=_clean(address),
            contact_name=_clean(contact_name),
            credit_limit=credit_limit,
            sale_user_id=sale_user_id,
            status=STATUS_ACTIVE,
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="create_customer",
            target=f"customer:{customer.id}",
            detail=(
                f"{customer.code} {name}"
                + (f" MST={tax_code}" if tax_code else "")
                + (" (MST TRÙNG)" if duplicate else "")
            ),
        )
        return customer, duplicate

    def _audit_reassign(self, *, moved: list[Customer], to_sale_user_id: int, actor, summary: str) -> None:
        """Ghi lịch sử điều chuyển: MỘT dòng cho mỗi khách (target=customer:<id> → hiện trong
        Nhật ký hồ sơ khách) + MỘT dòng tổng (target=user:<đích>)."""
        for c in moved:
            self.audit.create(
                actor_user_id=actor.id,
                action="reassign_customer",
                target=f"customer:{c.id}",
                detail=f"Điều chuyển phụ trách → Sale {to_sale_user_id}",
            )
        self.audit.create(
            actor_user_id=actor.id,
            action="reassign_customers",
            target=f"user:{to_sale_user_id}",
            detail=summary,
        )

    def reassign_customers(
        self, *, from_sale_user_id: int, to_sale_user_id: int, scope: str, actor
    ) -> int:
        """Điều chuyển TOÀN BỘ khách hàng của một Sale sang Sale khác (bàn giao khi nhân sự
        thay đổi). Chỉ cho phép ở scope `department`/`all`; Sale (scope `own`) bị chặn."""
        if scope == SCOPE_OWN:
            raise CustomerForbidden(
                "Bạn không có quyền điều chuyển khách hàng (chỉ trưởng phòng / quản lý)."
            )
        if from_sale_user_id == to_sale_user_id:
            raise CustomerValidationError("Sale nguồn và Sale đích phải khác nhau.")

        moved = self.customers.reassign_sale(
            from_sale_user_id=from_sale_user_id,
            to_sale_user_id=to_sale_user_id,
            scope=scope,
            actor=actor,
        )
        self._audit_reassign(
            moved=moved,
            to_sale_user_id=to_sale_user_id,
            actor=actor,
            summary=f"Điều chuyển {len(moved)} khách hàng: Sale {from_sale_user_id}→{to_sale_user_id}",
        )
        return len(moved)

    def reassign_selected(
        self, *, customer_ids: list[int], to_sale_user_id: int, scope: str, actor
    ) -> tuple[int, int]:
        """Điều chuyển các khách ĐƯỢC CHỌN (checkbox) sang một Sale. Chỉ cho phép ở scope
        `department`/`all`. Trả về (số đã chuyển, số bị bỏ qua vì ngoài phạm vi)."""
        if scope == SCOPE_OWN:
            raise CustomerForbidden(
                "Bạn không có quyền điều chuyển khách hàng (chỉ trưởng phòng / quản lý)."
            )
        if not customer_ids:
            raise CustomerValidationError("Chưa chọn khách hàng nào để điều chuyển.")

        moved, skipped = self.customers.reassign_by_ids(
            customer_ids=customer_ids,
            to_sale_user_id=to_sale_user_id,
            scope=scope,
            actor=actor,
        )
        self._audit_reassign(
            moved=moved,
            to_sale_user_id=to_sale_user_id,
            actor=actor,
            summary=f"Điều chuyển {len(moved)} khách hàng đã chọn → Sale {to_sale_user_id}",
        )
        return len(moved), skipped

    def update_customer(
        self,
        *,
        customer_id: int,
        scope: str,
        actor,
        name: str,
        tax_code: str | None,
        phone: str | None,
        email: str | None,
        address: str | None,
        contact_name: str | None,
        credit_limit: int | None,
        sale_user_id: int | None,
        status: str | None,
        allow_reassign: bool = True,
    ) -> tuple[Customer, Customer | None]:
        """Update every field except the code. Records a before→after audit line for
        Sale-owner and credit-limit changes. Returns (customer, duplicate_or_None).

        Đổi NV phụ trách là quyền chi tiết `reassign` — thiếu `allow_reassign` thì
        sale_user_id phải giữ nguyên, tránh né quyền Điều chuyển qua nút Sửa."""
        customer = self.get_customer(customer_id=customer_id, scope=scope, actor=actor)

        name = self._validate_name(name)
        tax_code = self._validate_tax_code(tax_code)
        credit_limit = self._validate_credit_limit(credit_limit)
        status = self._validate_status(status)
        if sale_user_id is None:
            sale_user_id = customer.sale_user_id
        if sale_user_id != customer.sale_user_id and not allow_reassign:
            raise ReassignForbidden(
                "Bạn không có quyền điều chuyển người phụ trách khách hàng."
            )

        duplicate = self.customers.find_by_tax_code(tax_code) if tax_code else None
        if duplicate is not None and duplicate.id == customer.id:
            duplicate = None  # its own MST is not a "trùng"

        old_sale = customer.sale_user_id
        old_limit = customer.credit_limit

        self.customers.update(
            customer,
            name=name,
            tax_code=tax_code,
            phone=_clean(phone),
            email=_clean(email),
            address=_clean(address),
            contact_name=_clean(contact_name),
            credit_limit=credit_limit,
            sale_user_id=sale_user_id,
            status=status,
        )

        changes: list[str] = []
        if old_sale != sale_user_id:
            changes.append(f"Sale {old_sale}→{sale_user_id}")
        if old_limit != credit_limit:
            changes.append(f"hạn mức {old_limit}→{credit_limit}")
        self.audit.create(
            actor_user_id=actor.id,
            action="update_customer",
            target=f"customer:{customer.id}",
            detail=f"{customer.code} " + ("; ".join(changes) if changes else "thông tin"),
        )
        return customer, duplicate
