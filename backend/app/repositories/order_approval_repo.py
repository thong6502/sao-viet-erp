"""Duyệt "đơn đặc thù" (order_approvals) data access — A2 (spec-10 mở rộng). The ONLY layer
that touches the DB for order approvals. No business rules here (những cái đó ở OrderService).

Một hàng = một QUYẾT ĐỊNH (duyệt/từ chối) của Giám đốc, GHIM số tại thời điểm đó. `latest_for_order`
lấy quyết định GẦN NHẤT (theo decided_at, tie-break id) — nó quyết định đơn có được chốt không.
"""
from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..models.order import OrderApproval


class OrderApprovalRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def latest_for_order(self, order_id: int) -> OrderApproval | None:
        """Quyết định GẦN NHẤT của đơn (None nếu chưa có). Quyết định này quyết định cổng."""
        return self.db.execute(
            select(OrderApproval)
            .where(OrderApproval.order_id == order_id)
            .order_by(desc(OrderApproval.decided_at), desc(OrderApproval.id))
            .limit(1)
        ).scalar_one_or_none()

    def list_for_order(self, order_id: int) -> list[OrderApproval]:
        """Toàn bộ lịch sử duyệt/từ chối của đơn, mới nhất trước."""
        return list(
            self.db.execute(
                select(OrderApproval)
                .where(OrderApproval.order_id == order_id)
                .order_by(desc(OrderApproval.decided_at), desc(OrderApproval.id))
            ).scalars()
        )

    def create(
        self,
        *,
        order_id: int,
        decision: str,
        triggers: list[str],
        order_total: int,
        order_subtotal: int,
        order_cost: int | None,
        margin_pct_snapshot: int | None,
        min_margin_pct: int,
        high_value_threshold: int,
        note: str | None,
        decided_by: int | None,
    ) -> OrderApproval:
        row = OrderApproval(
            order_id=order_id,
            decision=decision,
            triggers_json=list(triggers),
            order_total=order_total,
            order_subtotal=order_subtotal,
            order_cost=order_cost,
            margin_pct_snapshot=margin_pct_snapshot,
            min_margin_pct=min_margin_pct,
            high_value_threshold=high_value_threshold,
            note=(note or None),
            decided_by=decided_by,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row
