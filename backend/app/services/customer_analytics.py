"""CRM-360 analytics — spec-06 (Khách hàng "hub of information").

All figures here are COMPUTED FROM REAL ROWS in the same app (``orders`` + ``order_lines``
+ ``quotations``) — never fabricated. When a customer has no orders/quotations the numbers
come back as honest zeros / empty series and the frontend renders an explicit empty state
(§PRODUCT_SENSE #4: "thà trống trung thực còn hơn số giả").

Two surfaces:
  - **List analytics** (:class:`CustomerListStats`): the KPI header strip (tổng KH · thân
    thiết · KH mới trong tháng · TB đơn) + a per-customer derived tier / LTV / order-count,
    all rolled up over the scoped set in ONE pass (no N+1).
  - **Detail analytics** (:class:`CustomerDashboard`): the Object-page Dashboard — doanh số
    12 tháng (bar), số đơn 12T, TB/đơn, công nợ (SEAM-16 read-only), cơ cấu sản phẩm (donut
    from order-line descriptions), tần suất đặt (heatmap 12T × weekday) — plus the two history
    tables (Lịch sử mua hàng from orders, Lịch sử báo giá from quotations).

Tier is a *behavioural* classification derived from real history (spend + tenure + recency),
NOT an invented master field — the domain (§DOMAIN L333) only speaks of "khách VIP" for the
volume discount, so a spend-based tier is the honest, data-grounded reading:
  - ``new``      — mới tạo trong 30 ngày HOẶC chưa có đơn nào.
  - ``loyal``    — doanh số 12T ≥ ``LOYAL_REVENUE_VND`` (khách thân thiết / VIP theo chi tiêu).
  - ``partner``  — khách từ > 365 ngày trước và có ≥1 đơn (đối tác lâu năm).
  - ``regular``  — còn lại (đang giao dịch, chưa đạt ngưỡng thân thiết).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.customer import Customer
from ..models.order import STATUS_CANCELLED as ORDER_CANCELLED
from ..models.order import Order, OrderLine
from ..models.quotation import Quotation

# --- Tier thresholds (SVN-input, ⚠️ chưa xác nhận — documented default) ---------
LOYAL_REVENUE_VND = 50_000_000   # doanh số 12T ≥ 50tr → "thân thiết"
PARTNER_TENURE_DAYS = 365        # khách > 1 năm + có đơn → "đối tác lâu năm"
NEW_WINDOW_DAYS = 30             # tạo trong 30 ngày → "mới"

TIER_NEW = "new"
TIER_LOYAL = "loyal"
TIER_PARTNER = "partner"
TIER_REGULAR = "regular"

# Orders in these statuses are excluded from realised revenue (đã hủy).
_EXCLUDED_ORDER_STATUSES = (ORDER_CANCELLED,)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    return value


@dataclass
class CustomerStat:
    """Per-customer derived numbers for a list row (all from real orders)."""

    customer_id: int
    revenue_12m: int = 0
    orders_12m: int = 0
    orders_total: int = 0
    last_order_at: date | None = None
    tier: str = TIER_REGULAR


@dataclass
class CustomerListStats:
    total_customers: int = 0
    loyal_count: int = 0
    new_this_month: int = 0
    avg_order_value: int = 0        # TB/đơn trên toàn tập scoped (0 nếu chưa có đơn)
    per_customer: dict[int, CustomerStat] = field(default_factory=dict)


@dataclass
class MonthPoint:
    month: str          # "YYYY-MM"
    label: str          # "T7" (tháng 7)
    revenue: int
    orders: int


@dataclass
class ProductSlice:
    label: str
    revenue: int
    orders: int


@dataclass
class HeatCell:
    month_index: int    # 0..11 (oldest→newest, aligns with revenue_12m order)
    weekday: int        # 0=Mon .. 6=Sun
    count: int


@dataclass
class OrderHistoryRow:
    id: int
    order_no: str
    status: str
    order_kind: str
    summary: str        # mô tả gộp các dòng đơn (đối ngoại), "SP A, SP B"
    total: int | None
    created_at: datetime


@dataclass
class QuoteHistoryRow:
    id: int
    code: str
    version: int
    status: str
    total: int | None
    valid_until: date | None
    created_at: datetime


@dataclass
class CustomerDashboard:
    revenue_12m: int
    orders_12m: int
    avg_order_value: int | None
    orders_total: int
    quotes_total: int
    win_rate_pct: int | None        # đơn / báo giá đã gửi (tỉ lệ chốt), None nếu chưa có BG
    first_order_at: date | None
    last_order_at: date | None
    tier: str
    months: list[MonthPoint]
    product_mix: list[ProductSlice]
    heatmap: list[HeatCell]
    has_data: bool


class CustomerAnalyticsService:
    """Read-only analytics over the live sales tables. Framework-agnostic (takes a Session)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # --- tier classification ------------------------------------------------

    @staticmethod
    def classify_tier(
        *,
        created_at: datetime | None,
        revenue_12m: int,
        orders_total: int,
        now: datetime | None = None,
    ) -> str:
        now = now or _utcnow()
        created = created_at
        # created_at may be naive (SQLite) — normalise to aware UTC for the delta.
        if created is not None and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age_days = (now - created).days if created is not None else 0
        # Spend wins first (VIP theo chi tiêu), then tenure, then recency.
        if revenue_12m >= LOYAL_REVENUE_VND:
            return TIER_LOYAL
        if orders_total > 0 and age_days > PARTNER_TENURE_DAYS:
            return TIER_PARTNER
        # "Mới" = vừa vào sổ (≤30 ngày) và chưa phát sinh giao dịch (hoặc chưa có đơn nào).
        if orders_total == 0 or age_days <= NEW_WINDOW_DAYS:
            return TIER_NEW
        return TIER_REGULAR

    # --- list roll-up -------------------------------------------------------

    def list_stats(self, customers: list[Customer]) -> CustomerListStats:
        """Roll up KPIs + per-customer tier over the given (already scoped+paged? no —
        WHOLE scoped set for the header) list of customers, in a bounded number of
        queries. `customers` should be the full scoped set so the KPI strip reflects the
        whole book, not just the current page."""
        stats = CustomerListStats(total_customers=len(customers))
        if not customers:
            return stats

        ids = [c.id for c in customers]
        since = _utcnow() - timedelta(days=365)

        # Realised revenue + order count per customer over trailing 12 months (non-cancelled).
        rev_rows = self.db.execute(
            select(
                Order.customer_id,
                func.coalesce(func.sum(OrderLine.line_total), 0),
                func.count(func.distinct(Order.id)),
            )
            .join(OrderLine, OrderLine.order_id == Order.id)
            .where(
                Order.customer_id.in_(ids),
                Order.status.notin_(_EXCLUDED_ORDER_STATUSES),
                Order.created_at >= since,
            )
            .group_by(Order.customer_id)
        ).all()
        rev_by_cust: dict[int, tuple[int, int]] = {
            cid: (int(rev or 0), int(cnt or 0)) for cid, rev, cnt in rev_rows
        }

        # Total order count + last order date per customer (all time, non-cancelled).
        tot_rows = self.db.execute(
            select(
                Order.customer_id,
                func.count(func.distinct(Order.id)),
                func.max(Order.created_at),
            )
            .where(
                Order.customer_id.in_(ids),
                Order.status.notin_(_EXCLUDED_ORDER_STATUSES),
            )
            .group_by(Order.customer_id)
        ).all()
        tot_by_cust: dict[int, tuple[int, date | None]] = {
            cid: (int(cnt or 0), _as_date(last) if last else None)
            for cid, cnt, last in tot_rows
        }

        now = _utcnow()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        total_rev_12m = 0
        total_orders_12m = 0
        for c in customers:
            rev_12m, orders_12m = rev_by_cust.get(c.id, (0, 0))
            orders_total, last_order = tot_by_cust.get(c.id, (0, None))
            tier = self.classify_tier(
                created_at=c.created_at,
                revenue_12m=rev_12m,
                orders_total=orders_total,
                now=now,
            )
            stats.per_customer[c.id] = CustomerStat(
                customer_id=c.id,
                revenue_12m=rev_12m,
                orders_12m=orders_12m,
                orders_total=orders_total,
                last_order_at=last_order,
                tier=tier,
            )
            if tier == TIER_LOYAL:
                stats.loyal_count += 1
            created = c.created_at
            if created is not None and created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if created is not None and created >= month_start:
                stats.new_this_month += 1
            total_rev_12m += rev_12m
            total_orders_12m += orders_12m

        stats.avg_order_value = (
            round(total_rev_12m / total_orders_12m) if total_orders_12m else 0
        )
        return stats

    # --- detail dashboard ---------------------------------------------------

    def dashboard(self, customer: Customer) -> CustomerDashboard:
        now = _utcnow()
        cid = customer.id

        # 12-month window aligned to calendar months (oldest → newest).
        months: list[tuple[int, int]] = []  # (year, month)
        y, m = now.year, now.month
        for _ in range(12):
            months.append((y, m))
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        months.reverse()
        index_of: dict[tuple[int, int], int] = {ym: i for i, ym in enumerate(months)}

        # All non-cancelled orders for this customer with line totals + created_at.
        order_rows = self.db.execute(
            select(
                Order.id,
                Order.created_at,
                func.coalesce(func.sum(OrderLine.line_total), 0),
            )
            .join(OrderLine, OrderLine.order_id == Order.id, isouter=True)
            .where(
                Order.customer_id == cid,
                Order.status.notin_(_EXCLUDED_ORDER_STATUSES),
            )
            .group_by(Order.id, Order.created_at)
        ).all()

        revenue_by_month = [0] * 12
        orders_by_month = [0] * 12
        heat: dict[tuple[int, int], int] = {}
        revenue_12m = 0
        orders_12m = 0
        orders_total = 0
        first_order_at: date | None = None
        last_order_at: date | None = None
        for _oid, created, total in order_rows:
            orders_total += 1
            created_dt = created
            if isinstance(created_dt, datetime) and created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=timezone.utc)
            d = _as_date(created)
            if first_order_at is None or d < first_order_at:
                first_order_at = d
            if last_order_at is None or d > last_order_at:
                last_order_at = d
            key = (d.year, d.month)
            idx = index_of.get(key)
            if idx is not None:
                revenue_by_month[idx] += int(total or 0)
                orders_by_month[idx] += 1
                revenue_12m += int(total or 0)
                orders_12m += 1
                heat_key = (idx, d.weekday())
                heat[heat_key] = heat.get(heat_key, 0) + 1

        month_points = [
            MonthPoint(
                month=f"{yy:04d}-{mm:02d}",
                label=f"T{mm}",
                revenue=revenue_by_month[i],
                orders=orders_by_month[i],
            )
            for i, (yy, mm) in enumerate(months)
        ]
        heatmap = [
            HeatCell(month_index=mi, weekday=wd, count=cnt)
            for (mi, wd), cnt in sorted(heat.items())
        ]

        # Cơ cấu sản phẩm (donut): group non-cancelled order lines by description over 12T.
        since = now - timedelta(days=365)
        mix_rows = self.db.execute(
            select(
                OrderLine.description,
                func.coalesce(func.sum(OrderLine.line_total), 0),
                func.count(OrderLine.id),
            )
            .join(Order, Order.id == OrderLine.order_id)
            .where(
                Order.customer_id == cid,
                Order.status.notin_(_EXCLUDED_ORDER_STATUSES),
                Order.created_at >= since,
            )
            .group_by(OrderLine.description)
            .order_by(func.coalesce(func.sum(OrderLine.line_total), 0).desc())
        ).all()
        product_mix = [
            ProductSlice(
                label=(desc or "Khác").strip() or "Khác",
                revenue=int(rev or 0),
                orders=int(cnt or 0),
            )
            for desc, rev, cnt in mix_rows
            if int(rev or 0) > 0
        ]

        # Quotation totals (đã gửi trở lên) for the win-rate + count.
        quotes_total = self.db.execute(
            select(func.count(Quotation.id)).where(Quotation.customer_id == cid)
        ).scalar_one()
        sent_quotes = self.db.execute(
            select(func.count(Quotation.id)).where(
                Quotation.customer_id == cid,
                Quotation.status.in_(("sent", "approved", "rejected", "expired")),
            )
        ).scalar_one()

        avg_order_value = round(revenue_12m / orders_12m) if orders_12m else None
        win_rate = (
            round(orders_total / sent_quotes * 100) if sent_quotes else None
        )
        tier = self.classify_tier(
            created_at=customer.created_at,
            revenue_12m=revenue_12m,
            orders_total=orders_total,
            now=now,
        )
        has_data = orders_total > 0 or quotes_total > 0

        return CustomerDashboard(
            revenue_12m=revenue_12m,
            orders_12m=orders_12m,
            avg_order_value=avg_order_value,
            orders_total=orders_total,
            quotes_total=quotes_total,
            win_rate_pct=win_rate,
            first_order_at=first_order_at,
            last_order_at=last_order_at,
            tier=tier,
            months=month_points,
            product_mix=product_mix,
            heatmap=heatmap,
            has_data=has_data,
        )

    # --- history tables -----------------------------------------------------

    def order_history(self, customer_id: int, *, limit: int = 200) -> list[OrderHistoryRow]:
        rows = self.db.execute(
            select(
                Order.id,
                Order.order_no,
                Order.status,
                Order.order_kind,
                func.sum(OrderLine.line_total),
                Order.created_at,
            )
            .join(OrderLine, OrderLine.order_id == Order.id, isouter=True)
            .where(Order.customer_id == customer_id)
            .group_by(
                Order.id, Order.order_no, Order.status, Order.order_kind, Order.created_at
            )
            .order_by(Order.created_at.desc(), Order.id.desc())
            .limit(limit)
        ).all()
        # Line descriptions per order (đối ngoại summary) — one query, no N+1.
        order_ids = [r[0] for r in rows]
        desc_by_order: dict[int, list[str]] = {}
        if order_ids:
            for oid, desc in self.db.execute(
                select(OrderLine.order_id, OrderLine.description)
                .where(OrderLine.order_id.in_(order_ids))
                .order_by(OrderLine.id)
            ):
                if desc:
                    desc_by_order.setdefault(oid, []).append(desc.strip())
        return [
            OrderHistoryRow(
                id=oid,
                order_no=no,
                status=status,
                order_kind=kind,
                summary=", ".join(desc_by_order.get(oid, [])) or "—",
                total=int(total) if total is not None else None,
                created_at=created,
            )
            for oid, no, status, kind, total, created in rows
        ]

    def quote_history(self, customer_id: int, *, limit: int = 200) -> list[QuoteHistoryRow]:
        rows = self.db.execute(
            select(Quotation)
            .where(Quotation.customer_id == customer_id)
            .order_by(Quotation.created_at.desc(), Quotation.id.desc())
            .limit(limit)
        ).scalars().all()
        return [
            QuoteHistoryRow(
                id=q.id,
                code=q.code,
                version=q.version,
                status=q.status,
                total=q.total,
                valid_until=q.valid_until,
                created_at=q.created_at,
            )
            for q in rows
        ]
