"""Báo giá (Quotation / Quote) repository — Header-Version-Item (H-V-I) pattern.
"""
from __future__ import annotations

from datetime import date
from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.orm import Session

from ..models.customer import Customer
from ..models.quotation import (
    STATUS_ACCEPTED,
    STATUS_CANCELLED,
    STATUS_EXPIRED,
    STATUS_PENDING_APPROVAL,
    STATUS_REJECTED,
    Quote,
    QuoteApproval,
    QuoteItem,
    QuoteVersion,
)
from ..models.role import SCOPE_ALL, SCOPE_DEPARTMENT, SCOPE_OWN
from ..models.user import User
from .org_scope import dept_subtree_ids

# Whitelist of sortable fields in Quote
_SORTABLE = {
    "quote_number": Quote.quote_number,
    "status": Quote.status,
    "valid_until": Quote.valid_until,
    "created_at": Quote.created_at,
}


class QuotationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, quote_id: int) -> Quote | None:
        return self.db.get(Quote, quote_id)

    # --- BG-2: quote_approvals (GĐ duyệt báo giá đặc thù) -------------------

    def latest_approval(self, quote_id: int) -> QuoteApproval | None:
        """Bản duyệt GẦN NHẤT của báo giá (quyết định cổng 'gửi khách')."""
        return self.db.execute(
            select(QuoteApproval)
            .where(QuoteApproval.quote_id == quote_id)
            .order_by(desc(QuoteApproval.decided_at), desc(QuoteApproval.id))
            .limit(1)
        ).scalar_one_or_none()

    def list_approvals(self, quote_id: int) -> list[QuoteApproval]:
        return list(
            self.db.execute(
                select(QuoteApproval)
                .where(QuoteApproval.quote_id == quote_id)
                .order_by(desc(QuoteApproval.decided_at), desc(QuoteApproval.id))
            ).scalars()
        )

    def create_approval(self, **fields) -> QuoteApproval:
        row = QuoteApproval(**fields)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def active_for_phieu(self, phieu_tinh_gia_id: int) -> Quote | None:
        """BG-1: báo giá ĐANG HIỆU LỰC của 1 Phiếu tính giá (draft/sent/accepted/converted). Báo giá
        rejected/expired/cancelled = NHẢ chỗ (cho báo giá lại / repeat order). Guard '1 PTG → 1 BG'."""
        return self.db.execute(
            select(Quote)
            .where(
                Quote.phieu_tinh_gia_id == phieu_tinh_gia_id,
                Quote.status.notin_([STATUS_REJECTED, STATUS_EXPIRED, STATUS_CANCELLED]),
            )
            .order_by(Quote.id.desc())
            .limit(1)
        ).scalar_one_or_none()

    def list_approved_selectable(
        self, *, scope: str, actor, today: date, limit: int = 50
    ) -> tuple[list[Quote], dict[int, str]]:
        """Select accepted quotes for orders."""
        stmt = select(Quote).where(Quote.status == STATUS_ACCEPTED)
        scope_cond = self._scope_condition(scope=scope, actor=actor)
        if scope_cond is not None:
            stmt = stmt.where(scope_cond)
        stmt = stmt.where(
            or_(Quote.valid_until.is_(None), Quote.valid_until >= today)
        ).order_by(Quote.quote_number.asc()).limit(limit)
        
        rows = list(self.db.execute(stmt).scalars())
        names: dict[int, str] = {}
        if rows:
            for qid, name in self.db.execute(
                select(Quote.id, Customer.name)
                .join(Customer, Customer.id == Quote.customer_id)
                .where(Quote.id.in_([r.id for r in rows]))
            ):
                names[qid] = name
        return rows, names

    def versions_of(self, quote_number: str) -> list[QuoteVersion]:
        return list(
            self.db.execute(
                select(QuoteVersion)
                .join(Quote, Quote.id == QuoteVersion.quote_id)
                .where(Quote.quote_number == quote_number)
                .order_by(QuoteVersion.version_number.asc())
            ).scalars()
        )

    def _scope_condition(self, *, scope: str, actor):
        if scope == SCOPE_ALL:
            return None
        if scope == SCOPE_OWN:
            return Quote.salesperson_id == actor.id
        if scope == SCOPE_DEPARTMENT:
            # Subtree semantics (#26): phòng mình + mọi đơn vị con (GĐKD thấy các team).
            dept_ids = dept_subtree_ids(self.db, actor.department_id)
            if not dept_ids:
                return Quote.salesperson_id == actor.id
            dept_sales = select(User.id).where(User.department_id.in_(dept_ids))
            return Quote.salesperson_id.in_(dept_sales)
        raise ValueError(f"Unknown scope: {scope!r}")

    def count_pending_approval(self, *, scope: str, actor) -> int:
        """Số báo giá đang 'Chờ duyệt' TRONG PHẠM VI của người duyệt (badge nav 'chờ tôi duyệt')."""
        stmt = select(func.count()).select_from(Quote).where(
            Quote.status == STATUS_PENDING_APPROVAL
        )
        cond = self._scope_condition(scope=scope, actor=actor)
        if cond is not None:
            stmt = stmt.where(cond)
        return int(self.db.execute(stmt).scalar_one())

    def can_access(self, *, quote: Quote, scope: str, actor) -> bool:
        if scope == SCOPE_ALL:
            return True
        if scope == SCOPE_OWN:
            return quote.salesperson_id == actor.id
        if scope == SCOPE_DEPARTMENT:
            if quote.salesperson_id is None:
                return False
            if quote.salesperson_id == actor.id:
                return True
            owner = self.db.get(User, quote.salesperson_id)
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
        status: str | None = None,
        sort: str = "-created_at",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Quote], int, dict[int, str]]:
        conditions = []
        scope_cond = self._scope_condition(scope=scope, actor=actor)
        if scope_cond is not None:
            conditions.append(scope_cond)

        base = select(Quote)
        count_stmt = select(func.count()).select_from(Quote)
        if q:
            like = f"%{q.strip().lower()}%"
            cust_ids = select(Customer.id).where(
                func.lower(Customer.name).like(like)
            )
            q_cond = or_(
                func.lower(Quote.quote_number).like(like),
                Quote.customer_id.in_(cust_ids),
            )
            conditions.append(q_cond)
        if status == "need_action":
            # Tab "Cần xử lý": soạn tiếp (draft) + đã gửi chờ khách (sent)
            conditions.append(Quote.status.in_(("draft", "sent")))
        elif status:
            conditions.append(Quote.status == status)

        for c in conditions:
            base = base.where(c)
            count_stmt = count_stmt.where(c)

        total = self.db.execute(count_stmt).scalar_one()

        direction = asc
        key = sort or "-created_at"
        if key.startswith("-"):
            direction = desc
            key = key[1:]
            
        # Map sort key if needed (compatibility mapping)
        if key == "code":
            key = "quote_number"
            
        col = _SORTABLE.get(key, Quote.created_at)
        base = base.order_by(direction(col), Quote.id.asc())

        page = max(1, page)
        size = max(1, min(size, 200))
        base = base.offset((page - 1) * size).limit(size)

        rows = list(self.db.execute(base).scalars())

        names: dict[int, str] = {}
        cust_ids_on_page = [r.customer_id for r in rows if r.customer_id is not None]
        if cust_ids_on_page:
            for qid, name in self.db.execute(
                select(Quote.id, Customer.name)
                .join(Customer, Customer.id == Quote.customer_id)
                .where(Quote.id.in_([r.id for r in rows]))
            ):
                names[qid] = name
        return rows, total, names

    def stats(self) -> dict:
        """Số đếm theo trạng thái cho thanh tab list."""
        by_status = dict(
            self.db.execute(select(Quote.status, func.count()).group_by(Quote.status)).all()
        )
        get = lambda s: int(by_status.get(s, 0))  # noqa: E731
        return {
            "total": sum(int(v) for v in by_status.values()),
            "draft": get("draft"),
            "pending_approval": get("pending_approval"),
            "sent": get("sent"),
            "accepted": get("accepted"),
            "rejected": get("rejected"),
            "expired": get("expired"),
            "converted_to_order": get("converted_to_order"),
            "cancelled": get("cancelled"),
            "need_action": get("draft") + get("sent"),
        }

    def create(self, quote: Quote) -> Quote:
        self.db.add(quote)
        self.db.commit()
        self.db.refresh(quote)
        return quote

    def update(self, quote: Quote) -> Quote:
        self.db.commit()
        self.db.refresh(quote)
        return quote
