"""Customer data access (Khách hàng / CRM) — the ONLY layer that touches the DB for
customers. SQL goes through SQLAlchemy bound parameters (no string-formatted input).
No business rules here (those live in CustomerService).

Scope note: a customer's "department" is the department of its owning Sale
(`sale_user_id → users.department_id`), so the `department` data-scope filters on the
set of Sale ids in the actor's department rather than on a column of `customers`.
"""
from __future__ import annotations

from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.orm import Session

from ..models.customer import (
    TASK_OPEN,
    Customer,
    CustomerAddress,
    CustomerAttachment,
    CustomerCareEvent,
    CustomerCareTask,
    CustomerContact,
    CustomerNote,
    CustomerTag,
    CustomerTagCatalog,
)
from ..models.role import SCOPE_ALL, SCOPE_DEPARTMENT, SCOPE_OWN
from ..models.user import User
from .org_scope import dept_subtree_ids

# Columns a caller may sort by (whitelist — never interpolate a raw sort key).
_SORTABLE = {
    "code": Customer.code,
    "name": Customer.name,
    "tax_code": Customer.tax_code,
    "credit_limit": Customer.credit_limit,
    "created_at": Customer.created_at,
}


class CustomerRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- reads --------------------------------------------------------------

    def get_by_id(self, customer_id: int) -> Customer | None:
        return self.db.get(Customer, customer_id)

    def find_by_tax_code(self, tax_code: str) -> Customer | None:
        """First customer carrying this MST, for the soft duplicate warning. Returns
        None for an empty MST (khách lẻ). Does NOT enforce uniqueness — that is a
        deliberate soft check, not a DB constraint (§34 L885)."""
        if not tax_code:
            return None
        return self.db.execute(
            select(Customer).where(Customer.tax_code == tax_code).order_by(Customer.id)
        ).scalars().first()

    def find_duplicates(
        self,
        *,
        tax_code: str | None = None,
        name: str | None = None,
        email: str | None = None,
        exclude_id: int | None = None,
    ) -> list[tuple[str, Customer]]:
        """Soft duplicate check theo 3 tiêu chí khảo sát #15 (MST / tên cty / email).
        Trả về [(field, customer)] — mỗi khách chỉ báo MỘT lần theo tiêu chí mạnh nhất
        (tax_code > name > email). So khớp case-insensitive trong PYTHON (lower() của
        SQLite chỉ hạ ASCII — "Đại Phát" ≠ "đại phát" nếu so trong SQL), name bỏ
        khoảng trắng thừa. Quét cả bảng — chấp nhận được ở cỡ danh bạ vài nghìn khách
        (list endpoint cũng đã load whole-book)."""
        out: list[tuple[str, Customer]] = []
        seen: set[int] = set()
        name_needle = " ".join(name.strip().lower().split()) if name and name.strip() else None
        email_needle = email.strip().lower() if email and email.strip() else None
        if not (tax_code or name_needle or email_needle):
            return out

        rows = list(self.db.execute(select(Customer).order_by(Customer.id)).scalars())

        def _add(field: str, match) -> None:
            for c in rows:
                if c.id in seen or (exclude_id is not None and c.id == exclude_id):
                    continue
                if match(c):
                    seen.add(c.id)
                    out.append((field, c))

        if tax_code:
            _add("tax_code", lambda c: c.tax_code == tax_code)
        if name_needle:
            _add("name", lambda c: " ".join(c.name.lower().split()) == name_needle)
        if email_needle:
            _add("email", lambda c: (c.email or "").lower() == email_needle)
        return out

    def _scope_condition(self, *, scope: str, actor):
        """The WHERE expression narrowing customers to a data scope, or None for `all`.

        `own`        → customers whose owning Sale is the actor.
        `department` → customers whose owning Sale sits in the actor's department
                       OR any of its sub-units (subtree — khảo sát #26: GĐKD ở phòng
                       cha thấy khách của các team con).
        """
        if scope == SCOPE_ALL:
            return None
        if scope == SCOPE_OWN:
            return Customer.sale_user_id == actor.id
        if scope == SCOPE_DEPARTMENT:
            dept_ids = dept_subtree_ids(self.db, actor.department_id)
            if not dept_ids:
                # No department → can only see own (avoids leaking the whole table).
                return Customer.sale_user_id == actor.id
            dept_sales = select(User.id).where(User.department_id.in_(dept_ids))
            return Customer.sale_user_id.in_(dept_sales)
        raise ValueError(f"Unknown scope: {scope!r}")

    def can_access(self, *, customer: Customer, scope: str, actor) -> bool:
        """Whether `actor` may see this one customer under `scope` (detail/edit guard)."""
        if scope == SCOPE_ALL:
            return True
        if scope == SCOPE_OWN:
            return customer.sale_user_id == actor.id
        if scope == SCOPE_DEPARTMENT:
            if customer.sale_user_id is None:
                return False
            if customer.sale_user_id == actor.id:
                return True
            owner = self.db.get(User, customer.sale_user_id)
            if owner is None or owner.department_id is None:
                return False
            return owner.department_id in dept_subtree_ids(self.db, actor.department_id)
        raise ValueError(f"Unknown scope: {scope!r}")

    def list(
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
        """Return (rows, total) for the scoped, filtered, sorted, paginated list.

        `q` matches name / tax_code / phone (case-insensitive substring). `sale_user_id`
        is an optional additional filter (the "lọc theo Sale" control). `total` is the
        count BEFORE pagination so the UI can render page counts.
        """
        conditions = []
        scope_cond = self._scope_condition(scope=scope, actor=actor)
        if scope_cond is not None:
            conditions.append(scope_cond)

        if q:
            like = f"%{q.strip().lower()}%"
            conditions.append(
                or_(
                    func.lower(Customer.name).like(like),
                    func.lower(func.coalesce(Customer.tax_code, "")).like(like),
                    func.lower(func.coalesce(Customer.phone, "")).like(like),
                )
            )
        if sale_user_id is not None:
            conditions.append(Customer.sale_user_id == sale_user_id)

        base = select(Customer)
        count_stmt = select(func.count()).select_from(Customer)
        for c in conditions:
            base = base.where(c)
            count_stmt = count_stmt.where(c)

        total = self.db.execute(count_stmt).scalar_one()

        # Sort: "-field" for descending; unknown/blank falls back to code asc.
        direction = asc
        key = sort or "code"
        if key.startswith("-"):
            direction = desc
            key = key[1:]
        col = _SORTABLE.get(key, Customer.code)
        # Tie-break on id so pagination is stable.
        base = base.order_by(direction(col), Customer.id.asc())

        page = max(1, page)
        size = max(1, min(size, 200))
        base = base.offset((page - 1) * size).limit(size)

        rows = list(self.db.execute(base).scalars())
        return rows, total

    def list_scoped_all(self, *, scope: str, actor) -> list[Customer]:
        """Every customer visible under the caller's scope (no pagination) — for the KPI
        header roll-up which must reflect the whole book, not just the current page."""
        stmt = select(Customer)
        cond = self._scope_condition(scope=scope, actor=actor)
        if cond is not None:
            stmt = stmt.where(cond)
        return list(self.db.execute(stmt).scalars())

    # --- writes -------------------------------------------------------------

    def _next_code(self) -> str:
        """Next sequential customer code: 'KH' + zero-padded number (KH001, KH002…).

        Based on the max existing KH-number so codes stay unique even after deletions
        (no reuse), following the PB### pattern of feat-023.
        """
        max_n = 0
        for code in self.db.execute(select(Customer.code)).scalars():
            if code and code.startswith("KH"):
                try:
                    max_n = max(max_n, int(code[2:]))
                except ValueError:
                    continue
        return f"KH{max_n + 1:03d}"

    def create(
        self,
        *,
        name: str,
        tax_code: str | None,
        phone: str | None,
        email: str | None,
        address: str | None,
        contact_name: str | None,
        credit_limit: int,
        sale_user_id: int | None,
        **extra,
    ) -> Customer:
        """`extra` = các cột phụ đã được service validate (customer_kind, điều khoản thanh
        toán, rào chiết khấu/biên) — code vẫn luôn do repo tự sinh. `status` (dormant) rơi
        vào `extra` nếu caller cũ còn truyền; model default 'active' nếu không có."""
        customer = Customer(
            code=self._next_code(),
            name=name,
            tax_code=tax_code,
            phone=phone,
            email=email,
            address=address,
            contact_name=contact_name,
            credit_limit=credit_limit,
            sale_user_id=sale_user_id,
            **extra,
        )
        self.db.add(customer)
        self.db.commit()
        self.db.refresh(customer)
        return customer

    def update(self, customer: Customer, **fields) -> Customer:
        """Assign the given attributes (code is never among them) and persist."""
        for key, value in fields.items():
            setattr(customer, key, value)
        self.db.commit()
        self.db.refresh(customer)
        return customer

    def reassign_sale(
        self, *, from_sale_user_id: int, to_sale_user_id: int, scope: str, actor
    ) -> list[Customer]:
        """Move every customer owned by `from_sale_user_id` (AND visible under the actor's
        scope) to `to_sale_user_id`. Returns the moved rows. The scope filter means a
        `department`-scoped caller can only move customers whose current owner sits in their
        department — never someone else's book."""
        stmt = select(Customer).where(Customer.sale_user_id == from_sale_user_id)
        cond = self._scope_condition(scope=scope, actor=actor)
        if cond is not None:
            stmt = stmt.where(cond)
        rows = list(self.db.execute(stmt).scalars())
        for c in rows:
            c.sale_user_id = to_sale_user_id
        self.db.commit()
        return rows

    def reassign_by_ids(
        self, *, customer_ids: list[int], to_sale_user_id: int, scope: str, actor
    ) -> tuple[list[Customer], int]:
        """Reassign a specific set of customers (checkbox selection) to `to_sale_user_id`.
        Only customers the actor may access under `scope` are moved; the rest are skipped.
        Returns (moved_rows, skipped_count)."""
        moved: list[Customer] = []
        skipped = 0
        seen: set[int] = set()
        for cid in customer_ids:
            if cid in seen:
                continue
            seen.add(cid)
            c = self.db.get(Customer, cid)
            if c is None or not self.can_access(customer=c, scope=scope, actor=actor):
                skipped += 1
                continue
            if c.sale_user_id != to_sale_user_id:
                c.sale_user_id = to_sale_user_id
                moved.append(c)
        self.db.commit()
        return moved, skipped

    # --- người liên hệ (#10–#11) ---------------------------------------------

    def list_contacts(self, customer_id: int) -> list[CustomerContact]:
        return list(self.db.execute(
            select(CustomerContact)
            .where(CustomerContact.customer_id == customer_id)
            .order_by(CustomerContact.is_primary.desc(), CustomerContact.id)
        ).scalars())

    def get_contact(self, contact_id: int) -> CustomerContact | None:
        return self.db.get(CustomerContact, contact_id)

    def _clear_primary(self, customer_id: int, except_id: int | None = None) -> None:
        for c in self.list_contacts(customer_id):
            if c.is_primary and c.id != except_id:
                c.is_primary = False

    def add_contact(self, customer_id: int, **fields) -> CustomerContact:
        if fields.get("is_primary"):
            self._clear_primary(customer_id)
        contact = CustomerContact(customer_id=customer_id, **fields)
        self.db.add(contact)
        self.db.commit()
        self.db.refresh(contact)
        return contact

    def update_contact(self, contact: CustomerContact, **fields) -> CustomerContact:
        if fields.get("is_primary"):
            self._clear_primary(contact.customer_id, except_id=contact.id)
        for key, value in fields.items():
            setattr(contact, key, value)
        self.db.commit()
        self.db.refresh(contact)
        return contact

    def delete_contact(self, contact: CustomerContact) -> None:
        self.db.delete(contact)
        self.db.commit()

    # --- địa chỉ giao hàng (#9) ------------------------------------------------

    def list_addresses(self, customer_id: int) -> list[CustomerAddress]:
        return list(self.db.execute(
            select(CustomerAddress)
            .where(CustomerAddress.customer_id == customer_id)
            .order_by(CustomerAddress.is_default.desc(), CustomerAddress.id)
        ).scalars())

    def get_address(self, address_id: int) -> CustomerAddress | None:
        return self.db.get(CustomerAddress, address_id)

    def _clear_default_address(self, customer_id: int, except_id: int | None = None) -> None:
        for a in self.list_addresses(customer_id):
            if a.is_default and a.id != except_id:
                a.is_default = False

    def add_address(self, customer_id: int, **fields) -> CustomerAddress:
        if fields.get("is_default"):
            self._clear_default_address(customer_id)
        address = CustomerAddress(customer_id=customer_id, **fields)
        self.db.add(address)
        self.db.commit()
        self.db.refresh(address)
        return address

    def update_address(self, address: CustomerAddress, **fields) -> CustomerAddress:
        if fields.get("is_default"):
            self._clear_default_address(address.customer_id, except_id=address.id)
        for key, value in fields.items():
            setattr(address, key, value)
        self.db.commit()
        self.db.refresh(address)
        return address

    def delete_address(self, address: CustomerAddress) -> None:
        self.db.delete(address)
        self.db.commit()

    # --- kho nhãn dùng chung (`customer_tag_catalog`) -----------------------------

    def list_kho_nhan(self) -> list[CustomerTagCatalog]:
        return list(self.db.execute(
            select(CustomerTagCatalog).order_by(CustomerTagCatalog.label)
        ).scalars())

    def dem_khach_theo_nhan(self) -> dict[str, int]:
        """Mỗi nhãn (hạ chữ) đang được bao nhiêu khách mang — để cảnh báo TRƯỚC khi xoá.

        Gom trong Python chứ không `GROUP BY lower(label)`: `lower()` của SQLite chỉ hạ chữ ASCII
        nên "Ưu tiên" và "ưu tiên" ra hai nhóm — cùng lỗi đã ghi ở `ids_with_label`.
        """
        out: dict[str, int] = {}
        for (label,) in self.db.execute(select(CustomerTag.label)).all():
            key = label.strip().lower()
            out[key] = out.get(key, 0) + 1
        return out

    def tim_nhan_kho(self, label: str) -> CustomerTagCatalog | None:
        """Tra theo nhãn, KHÔNG phân biệt hoa-thường (so trong Python, lý do như trên)."""
        needle = label.strip().lower()
        for row in self.list_kho_nhan():
            if row.label.strip().lower() == needle:
                return row
        return None

    def get_nhan_kho(self, nhan_id: int) -> CustomerTagCatalog | None:
        return self.db.get(CustomerTagCatalog, nhan_id)

    def them_nhan_kho(self, *, label: str, created_by: int | None) -> CustomerTagCatalog:
        row = CustomerTagCatalog(label=label, created_by=created_by)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def xoa_nhan_kho(self, row: CustomerTagCatalog) -> int:
        """Xoá nhãn khỏi kho VÀ gỡ nó khỏi mọi khách đang mang. Trả số khách bị gỡ.

        Dọn luôn dòng gán chứ không để lại: nhãn đã biến khỏi kho mà chip vẫn hiện trên khách thì
        không còn đường nào gỡ chip đó ra (hộp Gắn thẻ chỉ bày nhãn có trong kho).
        """
        needle = row.label.strip().lower()
        da_gan = [
            t for t in self.db.execute(select(CustomerTag)).scalars()
            if t.label.strip().lower() == needle
        ]
        for t in da_gan:
            self.db.delete(t)
        self.db.delete(row)
        self.db.commit()
        return len(da_gan)

    # --- nhãn thủ công (#7: sales gán tay để phân loại chăm sóc) ------------------

    def list_tags(self, customer_id: int) -> list[CustomerTag]:
        return list(self.db.execute(
            select(CustomerTag)
            .where(CustomerTag.customer_id == customer_id)
            .order_by(CustomerTag.label)
        ).scalars())

    def tags_for(self, customer_ids: list[int]) -> dict[int, list[str]]:
        """Nhãn của một tập khách trong MỘT query (chips trên danh bạ, không N+1)."""
        if not customer_ids:
            return {}
        out: dict[int, list[str]] = {}
        rows = self.db.execute(
            select(CustomerTag.customer_id, CustomerTag.label)
            .where(CustomerTag.customer_id.in_(customer_ids))
            .order_by(CustomerTag.label)
        ).all()
        for cid, label in rows:
            out.setdefault(cid, []).append(label)
        return out

    def get_tag(self, tag_id: int) -> CustomerTag | None:
        return self.db.get(CustomerTag, tag_id)

    def find_tag_by_label(self, customer_id: int, label: str) -> CustomerTag | None:
        """Nhãn trùng (case-insensitive) trên cùng một khách — chống gán đúp."""
        needle = label.strip().lower()
        for t in self.list_tags(customer_id):
            if t.label.lower() == needle:
                return t
        return None

    def add_tag(self, customer_id: int, *, label: str, created_by: int | None) -> CustomerTag:
        tag = CustomerTag(customer_id=customer_id, label=label, created_by=created_by)
        self.db.add(tag)
        self.db.commit()
        self.db.refresh(tag)
        return tag

    def delete_tag(self, tag: CustomerTag) -> None:
        self.db.delete(tag)
        self.db.commit()

    def distinct_labels(self, *, scope: str, actor) -> list[str]:
        """Mọi nhãn đã dùng trên các khách trong scope (gợi ý khi gõ + option filter)."""
        stmt = (
            select(CustomerTag.label)
            .join(Customer, CustomerTag.customer_id == Customer.id)
            .distinct()
            .order_by(CustomerTag.label)
        )
        cond = self._scope_condition(scope=scope, actor=actor)
        if cond is not None:
            stmt = stmt.where(cond)
        return list(self.db.execute(stmt).scalars())

    def ids_with_label(self, label: str) -> set[int]:
        """Id các khách mang nhãn này (lọc danh bạ theo nhãn, case-insensitive).

        So sánh lower trong PYTHON, không dùng SQL lower() — lower() của SQLite chỉ hạ
        chữ ASCII nên "Đại lý" ≠ "đại lý" nếu so trong SQL (Postgres thì được, nhưng
        phải chạy đúng trên cả hai)."""
        needle = label.strip().lower()
        rows = self.db.execute(
            select(CustomerTag.customer_id, CustomerTag.label)
        ).all()
        return {cid for cid, lb in rows if lb.lower() == needle}

    # --- chăm sóc: nhật ký + lịch hẹn (#20/#27/#28) -----------------------------

    def list_care_events(self, customer_id: int) -> list[CustomerCareEvent]:
        return list(self.db.execute(
            select(CustomerCareEvent)
            .where(CustomerCareEvent.customer_id == customer_id)
            .order_by(CustomerCareEvent.happened_at.desc(), CustomerCareEvent.id.desc())
        ).scalars())

    def add_care_event(self, customer_id: int, **fields) -> CustomerCareEvent:
        ev = CustomerCareEvent(customer_id=customer_id, **fields)
        self.db.add(ev)
        self.db.commit()
        self.db.refresh(ev)
        return ev

    def list_care_tasks(self, customer_id: int) -> list[CustomerCareTask]:
        # Việc mở trước (đến hạn sớm lên đầu), việc đã xong/hủy sau (mới nhất trước).
        rows = list(self.db.execute(
            select(CustomerCareTask).where(CustomerCareTask.customer_id == customer_id)
        ).scalars())
        rows.sort(key=lambda t: (t.status != TASK_OPEN, t.due_date, t.id))
        return rows

    def get_care_task(self, task_id: int) -> CustomerCareTask | None:
        return self.db.get(CustomerCareTask, task_id)

    def add_care_task(self, customer_id: int, **fields) -> CustomerCareTask:
        task = CustomerCareTask(customer_id=customer_id, **fields)
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def update_care_task(self, task: CustomerCareTask, **fields) -> CustomerCareTask:
        for key, value in fields.items():
            setattr(task, key, value)
        self.db.commit()
        self.db.refresh(task)
        return task

    def list_due_followups(
        self, *, scope: str, actor, due_before
    ) -> list[tuple[CustomerCareTask, Customer]]:
        """Việc chăm sóc ĐANG MỞ đã đến hạn (due_date ≤ due_before) trên các khách trong
        scope của người gọi — nguồn của panel "Cần chăm sóc" (#28). Đến hạn sớm nhất trước."""
        stmt = (
            select(CustomerCareTask, Customer)
            .join(Customer, CustomerCareTask.customer_id == Customer.id)
            .where(CustomerCareTask.status == TASK_OPEN)
            .where(CustomerCareTask.due_date <= due_before)
        )
        cond = self._scope_condition(scope=scope, actor=actor)
        if cond is not None:
            stmt = stmt.where(cond)
        stmt = stmt.order_by(CustomerCareTask.due_date.asc(), CustomerCareTask.id.asc())
        return [(t, c) for t, c in self.db.execute(stmt).all()]

    def list_due_in_window(self, *, after, until) -> list[tuple[CustomerCareTask, Customer]]:
        """Hẹn ĐANG MỞ có giờ hẹn vừa rơi vào (after, until] và CÓ người phụ trách — nguồn ticker
        đẩy "ting" real-time. Cửa sổ hở-trái/đóng-phải để mỗi hẹn chỉ lọt ĐÚNG 1 LẦN (không nhắc lặp)."""
        stmt = (
            select(CustomerCareTask, Customer)
            .join(Customer, CustomerCareTask.customer_id == Customer.id)
            .where(CustomerCareTask.status == TASK_OPEN)
            .where(CustomerCareTask.assignee_user_id.is_not(None))
            .where(CustomerCareTask.due_date > after)
            .where(CustomerCareTask.due_date <= until)
        )
        return [(t, c) for t, c in self.db.execute(stmt).all()]

    # --- ghi chú tự do (tab Ghi chú) ---------------------------------------------

    def list_notes(self, customer_id: int) -> list[CustomerNote]:
        """Ghim lên đầu; trong mỗi nhóm mới-nhất-trước (theo created_at, tie-break id)."""
        return list(self.db.execute(
            select(CustomerNote)
            .where(CustomerNote.customer_id == customer_id)
            .order_by(
                CustomerNote.pinned.desc(),
                CustomerNote.created_at.desc(),
                CustomerNote.id.desc(),
            )
        ).scalars())

    def get_note(self, note_id: int) -> CustomerNote | None:
        return self.db.get(CustomerNote, note_id)

    def add_note(self, customer_id: int, **fields) -> CustomerNote:
        note = CustomerNote(customer_id=customer_id, **fields)
        self.db.add(note)
        self.db.commit()
        self.db.refresh(note)
        return note

    def update_note(self, note: CustomerNote, **fields) -> CustomerNote:
        for key, value in fields.items():
            setattr(note, key, value)
        self.db.commit()
        self.db.refresh(note)
        return note

    def delete_note(self, note: CustomerNote) -> None:
        self.db.delete(note)
        self.db.commit()

    # --- tài liệu đính kèm (#21) -------------------------------------------------

    def list_attachments(self, customer_id: int) -> list[CustomerAttachment]:
        return list(self.db.execute(
            select(CustomerAttachment)
            .where(CustomerAttachment.customer_id == customer_id)
            .order_by(CustomerAttachment.id.desc())
        ).scalars())

    def get_attachment(self, attachment_id: int) -> CustomerAttachment | None:
        return self.db.get(CustomerAttachment, attachment_id)

    def add_attachment(self, customer_id: int, **fields) -> CustomerAttachment:
        att = CustomerAttachment(customer_id=customer_id, **fields)
        self.db.add(att)
        self.db.commit()
        self.db.refresh(att)
        return att

    def delete_attachment(self, att: CustomerAttachment) -> None:
        self.db.delete(att)
        self.db.commit()
