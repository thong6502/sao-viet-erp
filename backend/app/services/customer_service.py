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

from datetime import date, datetime, timezone

from ..models.customer import (
    CARE_KHAC,
    CARE_KINDS,
    CARE_TASK_STATUSES,
    CUSTOMER_DOC_KINDS,
    CUSTOMER_KINDS,
    DOC_KHAC,
    KIND_CONG_TY,
    TASK_CANCELLED,
    TASK_DONE,
    TASK_OPEN,
    Customer,
    CustomerAddress,
    CustomerAttachment,
    CustomerCareEvent,
    CustomerCareTask,
    CustomerContact,
)
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
    def _validate_pct(value: float | None, label: str) -> float | None:
        if value is None:
            return None
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise CustomerValidationError(f"{label} phải là số phần trăm.") from None
        if not 0 <= value <= 100:
            raise CustomerValidationError(f"{label} phải trong khoảng 0–100%.")
        return value

    @staticmethod
    def _validate_kind(kind: str | None) -> str:
        """Loại KH (redesign spec-06 v2). None/rỗng → mặc định 'cong_ty'."""
        kind = (kind or KIND_CONG_TY).strip()
        if kind not in CUSTOMER_KINDS:
            raise CustomerValidationError("Loại khách hàng không hợp lệ.")
        return kind

    def _validate_bounds(
        self,
        *,
        discount_min_pct: float | None,
        discount_max_pct: float | None,
        margin_min_pct: float | None,
        margin_max_pct: float | None,
    ) -> dict:
        """Rào chiết khấu/biên (spec-06 v2): mỗi % ∈ [0,100], min ≤ max; None = chưa đặt."""
        dmin = self._validate_pct(discount_min_pct, "Chiết khấu tối thiểu")
        dmax = self._validate_pct(discount_max_pct, "Chiết khấu tối đa")
        mmin = self._validate_pct(margin_min_pct, "Biên lợi nhuận tối thiểu")
        mmax = self._validate_pct(margin_max_pct, "Biên lợi nhuận tối đa")
        if dmin is not None and dmax is not None and dmin > dmax:
            raise CustomerValidationError("Chiết khấu tối thiểu không được lớn hơn tối đa.")
        if mmin is not None and mmax is not None and mmin > mmax:
            raise CustomerValidationError("Biên lợi nhuận tối thiểu không được lớn hơn tối đa.")
        return dict(
            discount_min_pct=dmin, discount_max_pct=dmax,
            margin_min_pct=mmin, margin_max_pct=mmax,
        )

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
        sale_user_id: int | None,
        actor,
        customer_kind: str | None = None,
    ) -> tuple[Customer, list[tuple[str, Customer]]]:
        """Create a customer (THÔNG TIN ĐỊNH DANH). Chính sách tài chính về default an toàn
        (credit_limit=0, chưa khai điều khoản, chưa đặt rào) — đặt sau qua `update_financial`.
        Returns (customer, duplicates) — trùng MST/tên/email = cảnh báo MỀM, vẫn tạo (§34)."""
        name = self._validate_name(name)
        tax_code = self._validate_tax_code(tax_code)
        kind = self._validate_kind(customer_kind)
        # Default owning Sale = the acting user (spec-06 KH-02).
        if sale_user_id is None:
            sale_user_id = actor.id

        email_clean = _clean(email)
        duplicates = self.customers.find_duplicates(
            tax_code=tax_code, name=name, email=email_clean
        )

        customer = self.customers.create(
            name=name,
            tax_code=tax_code,
            phone=_clean(phone),
            email=email_clean,
            address=_clean(address),
            contact_name=_clean(contact_name),
            credit_limit=0,  # default an toàn; đặt qua /financial
            sale_user_id=sale_user_id,
            customer_kind=kind,
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="create_customer",
            target=f"customer:{customer.id}",
            detail=(
                f"{customer.code} {name}"
                + (f" MST={tax_code}" if tax_code else "")
                + (" (TRÙNG " + ", ".join(f for f, _ in duplicates) + ")" if duplicates else "")
            ),
        )
        return customer, duplicates

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
        sale_user_id: int | None,
        customer_kind: str | None = None,
        allow_reassign: bool = True,
    ) -> tuple[Customer, list[tuple[str, Customer]]]:
        """Update THÔNG TIN ĐỊNH DANH (không đụng chính sách tài chính — sửa qua
        `update_financial`, endpoint riêng). Đổi NV phụ trách cần `allow_reassign` (quyền
        `reassign`); thiếu → giữ nguyên sale (tránh né quyền qua nút Sửa)."""
        customer = self.get_customer(customer_id=customer_id, scope=scope, actor=actor)

        name = self._validate_name(name)
        tax_code = self._validate_tax_code(tax_code)
        kind = self._validate_kind(customer_kind)
        if sale_user_id is None:
            sale_user_id = customer.sale_user_id
        if sale_user_id != customer.sale_user_id and not allow_reassign:
            raise ReassignForbidden(
                "Bạn không có quyền điều chuyển người phụ trách khách hàng."
            )

        email_clean = _clean(email)
        duplicates = self.customers.find_duplicates(
            tax_code=tax_code, name=name, email=email_clean, exclude_id=customer.id
        )

        old_sale = customer.sale_user_id
        self.customers.update(
            customer,
            name=name,
            tax_code=tax_code,
            phone=_clean(phone),
            email=email_clean,
            address=_clean(address),
            contact_name=_clean(contact_name),
            sale_user_id=sale_user_id,
            customer_kind=kind,
        )

        changes: list[str] = []
        if old_sale != sale_user_id:
            changes.append(f"Sale {old_sale}→{sale_user_id}")
        self.audit.create(
            actor_user_id=actor.id,
            action="update_customer",
            target=f"customer:{customer.id}",
            detail=f"{customer.code} " + ("; ".join(changes) if changes else "thông tin"),
        )
        return customer, duplicates

    def update_financial(
        self,
        *,
        customer_id: int,
        scope: str,
        actor,
        credit_limit: int | None,
        discount_min_pct: float | None = None,
        discount_max_pct: float | None = None,
        margin_min_pct: float | None = None,
        margin_max_pct: float | None = None,
    ) -> Customer:
        """Ghi ĐẦY ĐỦ chính sách tài chính (hạn mức công nợ + rào chiết khấu/biên) —
        redesign spec-06 v2. Router chỉ gọi khi caller có quyền `set_credit_terms` (chặn 403
        nếu thiếu). Ghi cả nhóm nên None = "chưa đặt rào". (Điều khoản thanh toán đã BỎ.)"""
        customer = self.get_customer(customer_id=customer_id, scope=scope, actor=actor)
        credit_limit = self._validate_credit_limit(credit_limit)
        bounds = self._validate_bounds(
            discount_min_pct=discount_min_pct, discount_max_pct=discount_max_pct,
            margin_min_pct=margin_min_pct, margin_max_pct=margin_max_pct,
        )
        old = (
            customer.credit_limit,
            customer.discount_min_pct, customer.discount_max_pct,
            customer.margin_min_pct, customer.margin_max_pct,
        )
        self.customers.update(customer, credit_limit=credit_limit, **bounds)
        new = (
            credit_limit,
            bounds["discount_min_pct"], bounds["discount_max_pct"],
            bounds["margin_min_pct"], bounds["margin_max_pct"],
        )
        if old != new:
            self.audit.create(
                actor_user_id=actor.id,
                action="update_customer",
                target=f"customer:{customer.id}",
                detail=f"{customer.code} chính sách tài chính",
            )
        return customer

    # --- người liên hệ / địa chỉ giao hàng / tài liệu (#9–#11, #21) -----------

    def _guarded(self, *, customer_id: int, scope: str, actor) -> Customer:
        """Scope guard dùng chung cho các sub-resource của một khách."""
        return self.get_customer(customer_id=customer_id, scope=scope, actor=actor)

    def list_contacts(self, *, customer_id: int, scope: str, actor) -> list[CustomerContact]:
        self._guarded(customer_id=customer_id, scope=scope, actor=actor)
        return self.customers.list_contacts(customer_id)

    def add_contact(
        self, *, customer_id: int, scope: str, actor, name: str, title: str | None,
        duty: str | None, phone: str | None, email: str | None, is_primary: bool,
    ) -> CustomerContact:
        self._guarded(customer_id=customer_id, scope=scope, actor=actor)
        name = self._validate_name(name)
        return self.customers.add_contact(
            customer_id,
            name=name, title=_clean(title), duty=_clean(duty),
            phone=_clean(phone), email=_clean(email), is_primary=bool(is_primary),
        )

    def update_contact(
        self, *, customer_id: int, contact_id: int, scope: str, actor, name: str,
        title: str | None, duty: str | None, phone: str | None, email: str | None,
        is_primary: bool,
    ) -> CustomerContact:
        self._guarded(customer_id=customer_id, scope=scope, actor=actor)
        contact = self.customers.get_contact(contact_id)
        if contact is None or contact.customer_id != customer_id:
            raise CustomerNotFound("Không tìm thấy người liên hệ.")
        name = self._validate_name(name)
        return self.customers.update_contact(
            contact,
            name=name, title=_clean(title), duty=_clean(duty),
            phone=_clean(phone), email=_clean(email), is_primary=bool(is_primary),
        )

    def delete_contact(self, *, customer_id: int, contact_id: int, scope: str, actor) -> None:
        self._guarded(customer_id=customer_id, scope=scope, actor=actor)
        contact = self.customers.get_contact(contact_id)
        if contact is None or contact.customer_id != customer_id:
            raise CustomerNotFound("Không tìm thấy người liên hệ.")
        self.customers.delete_contact(contact)

    def list_addresses(self, *, customer_id: int, scope: str, actor) -> list[CustomerAddress]:
        self._guarded(customer_id=customer_id, scope=scope, actor=actor)
        return self.customers.list_addresses(customer_id)

    def add_address(
        self, *, customer_id: int, scope: str, actor, label: str, address: str,
        phone: str | None, note: str | None, is_default: bool,
    ) -> CustomerAddress:
        self._guarded(customer_id=customer_id, scope=scope, actor=actor)
        label = (label or "").strip()
        address = (address or "").strip()
        if not label or not address:
            raise CustomerValidationError("Tên điểm giao và địa chỉ là bắt buộc.")
        return self.customers.add_address(
            customer_id,
            label=label, address=address, phone=_clean(phone), note=_clean(note),
            is_default=bool(is_default),
        )

    def update_address(
        self, *, customer_id: int, address_id: int, scope: str, actor, label: str,
        address: str, phone: str | None, note: str | None, is_default: bool,
    ) -> CustomerAddress:
        self._guarded(customer_id=customer_id, scope=scope, actor=actor)
        row = self.customers.get_address(address_id)
        if row is None or row.customer_id != customer_id:
            raise CustomerNotFound("Không tìm thấy địa chỉ giao hàng.")
        label = (label or "").strip()
        address = (address or "").strip()
        if not label or not address:
            raise CustomerValidationError("Tên điểm giao và địa chỉ là bắt buộc.")
        return self.customers.update_address(
            row,
            label=label, address=address, phone=_clean(phone), note=_clean(note),
            is_default=bool(is_default),
        )

    def delete_address(self, *, customer_id: int, address_id: int, scope: str, actor) -> None:
        self._guarded(customer_id=customer_id, scope=scope, actor=actor)
        row = self.customers.get_address(address_id)
        if row is None or row.customer_id != customer_id:
            raise CustomerNotFound("Không tìm thấy địa chỉ giao hàng.")
        self.customers.delete_address(row)

    def list_attachments(self, *, customer_id: int, scope: str, actor) -> list[CustomerAttachment]:
        self._guarded(customer_id=customer_id, scope=scope, actor=actor)
        return self.customers.list_attachments(customer_id)

    def add_attachment(
        self, *, customer_id: int, scope: str, actor, doc_kind: str, file_name: str,
        file_url: str, file_type: str | None,
    ) -> CustomerAttachment:
        self._guarded(customer_id=customer_id, scope=scope, actor=actor)
        if doc_kind not in CUSTOMER_DOC_KINDS:
            doc_kind = DOC_KHAC
        att = self.customers.add_attachment(
            customer_id,
            doc_kind=doc_kind, file_name=file_name, file_url=file_url,
            file_type=file_type, uploaded_by=actor.id,
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="update_customer",
            target=f"customer:{customer_id}",
            detail=f"Đính kèm tài liệu: {file_name}",
        )
        return att

    def delete_attachment(self, *, customer_id: int, attachment_id: int, scope: str, actor) -> None:
        self._guarded(customer_id=customer_id, scope=scope, actor=actor)
        att = self.customers.get_attachment(attachment_id)
        if att is None or att.customer_id != customer_id:
            raise CustomerNotFound("Không tìm thấy tài liệu.")
        self.customers.delete_attachment(att)
        self.audit.create(
            actor_user_id=actor.id,
            action="update_customer",
            target=f"customer:{customer_id}",
            detail=f"Xóa tài liệu: {att.file_name}",
        )

    # --- nhãn thủ công (#7: sales gán tay) ---------------------------------------

    def list_tags(self, *, customer_id: int, scope: str, actor):
        self._guarded(customer_id=customer_id, scope=scope, actor=actor)
        return self.customers.list_tags(customer_id)

    def add_tag(self, *, customer_id: int, scope: str, actor, label: str):
        """Gán nhãn. Nhãn trùng (case-insensitive) trên cùng khách → trả nhãn có sẵn,
        không tạo đúp, không lỗi (gõ lại nhãn cũ là vô hại)."""
        self._guarded(customer_id=customer_id, scope=scope, actor=actor)
        label = " ".join((label or "").strip().split())
        if not label:
            raise CustomerValidationError("Nhãn không được để trống.")
        if len(label) > 50:
            raise CustomerValidationError("Nhãn tối đa 50 ký tự.")
        existing = self.customers.find_tag_by_label(customer_id, label)
        if existing is not None:
            return existing
        tag = self.customers.add_tag(customer_id, label=label, created_by=actor.id)
        self.audit.create(
            actor_user_id=actor.id,
            action="update_customer",
            target=f"customer:{customer_id}",
            detail=f"Gán nhãn: {label}",
        )
        return tag

    def remove_tag(self, *, customer_id: int, tag_id: int, scope: str, actor) -> None:
        self._guarded(customer_id=customer_id, scope=scope, actor=actor)
        tag = self.customers.get_tag(tag_id)
        if tag is None or tag.customer_id != customer_id:
            raise CustomerNotFound("Không tìm thấy nhãn.")
        self.customers.delete_tag(tag)
        self.audit.create(
            actor_user_id=actor.id,
            action="update_customer",
            target=f"customer:{customer_id}",
            detail=f"Gỡ nhãn: {tag.label}",
        )

    # --- chăm sóc khách hàng (#20/#27/#28) --------------------------------------

    @staticmethod
    def _as_date(value) -> date:
        if isinstance(value, datetime):
            return value.date()
        return value

    @classmethod
    def remind_level(cls, due_date, today: date | None = None) -> tuple[int, int]:
        """(mức nhắc, số ngày quá hạn) TÍNH từ ngày đến hạn (#28) — không lưu, không cron:
        chưa đến hạn = 0; đến hạn/quá <2 ngày = lần 1; quá ≥2 ngày = lần 2; quá ≥5 ngày = lần 3."""
        today = today or datetime.now(timezone.utc).date()
        overdue = (today - cls._as_date(due_date)).days
        if overdue < 0:
            return 0, 0
        if overdue < 2:
            return 1, overdue
        if overdue < 5:
            return 2, overdue
        return 3, overdue

    def list_care_events(
        self, *, customer_id: int, scope: str, actor
    ) -> list[CustomerCareEvent]:
        self._guarded(customer_id=customer_id, scope=scope, actor=actor)
        return self.customers.list_care_events(customer_id)

    def add_care_event(
        self, *, customer_id: int, scope: str, actor, kind: str, note: str,
        happened_at: datetime | None = None,
    ) -> CustomerCareEvent:
        self._guarded(customer_id=customer_id, scope=scope, actor=actor)
        note = (note or "").strip()
        if not note:
            raise CustomerValidationError("Nội dung chăm sóc là bắt buộc.")
        if kind not in CARE_KINDS:
            kind = CARE_KHAC
        fields = dict(kind=kind, note=note, created_by=actor.id)
        if happened_at is not None:
            fields["happened_at"] = happened_at
        return self.customers.add_care_event(customer_id, **fields)

    def list_care_tasks(
        self, *, customer_id: int, scope: str, actor
    ) -> list[CustomerCareTask]:
        self._guarded(customer_id=customer_id, scope=scope, actor=actor)
        return self.customers.list_care_tasks(customer_id)

    def add_care_task(
        self, *, customer_id: int, scope: str, actor, note: str, due_date: datetime,
        assignee_user_id: int | None = None,
    ) -> CustomerCareTask:
        customer = self._guarded(customer_id=customer_id, scope=scope, actor=actor)
        note = (note or "").strip()
        if not note:
            raise CustomerValidationError("Nội dung việc chăm sóc là bắt buộc.")
        # Mặc định người phụ trách việc = Sale phụ trách khách, không có thì người tạo.
        if assignee_user_id is None:
            assignee_user_id = customer.sale_user_id or actor.id
        return self.customers.add_care_task(
            customer_id,
            note=note, due_date=due_date, assignee_user_id=assignee_user_id,
            created_by=actor.id,
        )

    def set_care_task_status(
        self, *, customer_id: int, task_id: int, scope: str, actor, status: str,
        log_kind: str | None = None, log_note: str | None = None,
    ) -> CustomerCareTask:
        """Đổi trạng thái việc (done/cancelled/open-lại). Hoàn thành có thể ghi kèm một
        dòng nhật ký chăm sóc (log_kind + log_note) trong cùng thao tác."""
        self._guarded(customer_id=customer_id, scope=scope, actor=actor)
        task = self.customers.get_care_task(task_id)
        if task is None or task.customer_id != customer_id:
            raise CustomerNotFound("Không tìm thấy việc chăm sóc.")
        if status not in CARE_TASK_STATUSES:
            raise CustomerValidationError("Trạng thái việc không hợp lệ.")
        fields: dict = {"status": status}
        if status == TASK_DONE:
            fields["done_at"] = datetime.now(timezone.utc)
        elif status in (TASK_OPEN, TASK_CANCELLED):
            fields["done_at"] = None
        task = self.customers.update_care_task(task, **fields)
        if status == TASK_DONE and (log_note or "").strip():
            self.add_care_event(
                customer_id=customer_id, scope=scope, actor=actor,
                kind=log_kind or CARE_KHAC, note=log_note or "",
            )
        return task

    def list_due_followups(self, *, scope: str, actor) -> list[tuple[CustomerCareTask, Customer, int, int]]:
        """Việc đang mở đã đến hạn (tính đến HẾT hôm nay) trong scope, kèm (mức nhắc,
        ngày quá hạn) — nguồn panel "Cần chăm sóc"."""
        end_of_today = datetime.now(timezone.utc).replace(
            hour=23, minute=59, second=59, microsecond=0
        )
        rows = self.customers.list_due_followups(
            scope=scope, actor=actor, due_before=end_of_today
        )
        out = []
        for task, customer in rows:
            level, overdue = self.remind_level(task.due_date)
            out.append((task, customer, level, overdue))
        return out

    def care_stats(self, tasks: list[CustomerCareTask]) -> tuple[int, int, int]:
        """(xong đúng hạn, xong trễ, đang quá hạn) — đánh giá chăm sóc (#28), số thật."""
        on_time = late = overdue_open = 0
        for t in tasks:
            if t.status == TASK_DONE and t.done_at is not None:
                if self._as_date(t.done_at) <= self._as_date(t.due_date):
                    on_time += 1
                else:
                    late += 1
            elif t.status == TASK_OPEN and self.remind_level(t.due_date)[0] >= 1:
                overdue_open += 1
        return on_time, late, overdue_open

    # --- import CSV (#23) -----------------------------------------------------

    # Cột file import (header tiếng Việt, khớp file mẫu /api/customers/import-template.csv).
    # Redesign spec-06 v2: bỏ Trạng thái + Hạn mức (chính sách tài chính đặt riêng, gated);
    # thêm Loại. Import chỉ nạp thông tin ĐỊNH DANH.
    IMPORT_COLUMNS = {
        "tên khách hàng": "name",
        "loại": "customer_kind",
        "mst": "tax_code",
        "điện thoại": "phone",
        "email": "email",
        "địa chỉ": "address",
        "người liên hệ": "contact_name",
    }

    def import_rows(
        self, *, rows: list[dict], actor, dry_run: bool
    ) -> list[tuple[int, str, str | None, Customer | None]]:
        """Import danh bạ từ các dòng đã parse (khảo sát #23 — ~2.000 khách từ Excel).
        Mỗi dòng: validate như create; TRÙNG (MST/tên/email) = cảnh báo mềm nhưng VẪN
        TẠO (nhất quán §34 — người dùng xem trước bằng dry_run rồi mới ghi). Chỉ nạp thông
        tin định danh — chính sách tài chính (hạn mức/điều khoản/rào) đặt riêng ở chi tiết.
        Trả về [(row_no, status, message, customer_or_None)]; dry_run → không ghi gì."""
        out: list[tuple[int, str, str | None, Customer | None]] = []
        for i, raw in enumerate(rows, start=1):
            name = (raw.get("name") or "").strip()
            kind_label = (raw.get("customer_kind") or "").strip().lower()
            kind = "ca_nhan" if kind_label in ("cá nhân", "ca nhan", "cá nhan") else KIND_CONG_TY
            try:
                self._validate_name(name)
                tax_code = self._validate_tax_code(raw.get("tax_code"))
            except CustomerValidationError as e:
                out.append((i, "error", str(e), None))
                continue

            dups = self.customers.find_duplicates(
                tax_code=tax_code, name=name, email=_clean(raw.get("email"))
            )
            warn = (
                "Trùng " + ", ".join({"tax_code": "MST", "name": "tên", "email": "email"}[f] for f, _ in dups)
                + f" với {dups[0][1].code}"
                if dups else None
            )
            if dry_run:
                out.append((i, "warning" if warn else "created", warn, None))
                continue
            customer, _ = self.create_customer(
                name=name,
                customer_kind=kind,
                tax_code=raw.get("tax_code"),
                phone=raw.get("phone"),
                email=raw.get("email"),
                address=raw.get("address"),
                contact_name=raw.get("contact_name"),
                sale_user_id=None,
                actor=actor,
            )
            out.append((i, "warning" if warn else "created", warn, customer))
        return out
