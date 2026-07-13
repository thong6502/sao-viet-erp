"""Payment (thu tiền bán) data access — Pha A. ONLY layer touching the DB for payments.
No business rules here (those live in the service). SQL via SQLAlchemy bound params.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.payment import (
    PAYMENT_DIRECTION_IN,
    PAYMENT_KIND_DEPOSIT,
    Payment,
)


class PaymentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- writes -------------------------------------------------------------

    def create(
        self,
        *,
        order_id: int,
        customer_id: int | None,
        kind: str,
        amount: int,
        method: str,
        voucher_no: str | None = None,
        note: str | None = None,
        created_by: int | None = None,
    ) -> Payment:
        p = Payment(
            order_id=order_id,
            customer_id=customer_id,
            kind=kind,
            amount=amount,
            method=method,
            voucher_no=voucher_no,
            note=note,
            created_by=created_by,
        )
        self.db.add(p)
        self.db.commit()
        self.db.refresh(p)
        return p

    # --- reads --------------------------------------------------------------

    def deposit_total(self, order_id: int) -> int:
        """Cọc đã thu của đơn = NET Σ(thu) − Σ(hoàn) trên kind=deposit (0 nếu chưa có).
        Hoàn cọc (direction=hoan) trừ ra để cổng chốt phản ánh đúng số còn giữ."""
        rows = self.db.execute(
            select(Payment.direction, func.sum(Payment.amount))
            .where(Payment.order_id == order_id, Payment.kind == PAYMENT_KIND_DEPOSIT)
            .group_by(Payment.direction)
        ).all()
        net = 0
        for direction, s in rows:
            if s is None:
                continue
            net += int(s) if direction == PAYMENT_DIRECTION_IN else -int(s)
        return net

    def paid_total(self, order_id: int) -> int:
        """Tổng đã thu của đơn (mọi kind) — dùng cho hoa hồng/công nợ sau."""
        val = self.db.execute(
            select(func.sum(Payment.amount)).where(Payment.order_id == order_id)
        ).scalar()
        return int(val) if val is not None else 0

    def customer_paid_total(self, customer_id: int) -> int:
        """Tổng khách đã trả (mọi đơn) — cơ sở chiết khấu cuối năm/công nợ (§4.7)."""
        val = self.db.execute(
            select(func.sum(Payment.amount)).where(Payment.customer_id == customer_id)
        ).scalar()
        return int(val) if val is not None else 0

    def list_by_order(self, order_id: int) -> list[Payment]:
        return list(
            self.db.execute(
                select(Payment)
                .where(Payment.order_id == order_id)
                .order_by(Payment.paid_at.asc(), Payment.id.asc())
            ).scalars()
        )
