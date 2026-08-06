"""Đơn hàng bán (Order + OrderLine) data access — spec-10-don-hang-ban. The ONLY layer that
touches the DB for orders. SQL goes through SQLAlchemy bound parameters (no string-formatted
input). No business rules here (those live in OrderService).

Scope note: an order is owned by its Sale (``sale_user_id → users.department_id``), so the
``department`` data-scope filters on the set of Sale ids in the actor's department, mirroring
the Customer/Quotation repositories (feat-006 apply_scope pattern).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import BigInteger, asc, cast, desc, func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..models.customer import Customer
from ..models.order import Order, OrderLine
from ..models.role import SCOPE_ALL, SCOPE_DEPARTMENT, SCOPE_OWN
from ..models.user import User
from .org_scope import dept_subtree_ids

# Columns a caller may sort by (whitelist — never interpolate a raw sort key).
def _line_total_with_vat():
    """`line_total · (100 + vat_pct)` — ép 64-bit TRƯỚC khi nhân.

    Cả hai cột đều là `Integer` (int32). Postgres nhân int32×int32 ra int32 nên tràn ngay khi
    `line_total` vượt ~19,5 triệu VND (2.147.483.647 ÷ 110) — cỡ đơn thường ngày của xưởng in.
    SQLite dùng số nguyên 64-bit động nên không lộ, lỗi chỉ nổ trên Postgres.
    Gọi hàm mới mỗi lần vì biểu thức SQLAlchemy không nên dùng chung giữa các câu lệnh.
    """
    return cast(OrderLine.line_total, BigInteger) * (100 + OrderLine.vat_pct_estimate)


_SORTABLE = {
    "order_no": Order.order_no,
    "status": Order.status,
    "order_type": Order.order_type,
    "order_kind": Order.order_kind,
    "created_at": Order.created_at,
}


class OrderRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- reads --------------------------------------------------------------

    def get_by_id(self, order_id: int) -> Order | None:
        return self.db.get(Order, order_id)

    def get_with_lines(self, order_id: int) -> Order | None:
        return self.db.execute(
            select(Order).where(Order.id == order_id).options(selectinload(Order.lines))
        ).scalar_one_or_none()

    def _scope_condition(self, *, scope: str, actor):
        """WHERE expression narrowing orders to a data scope, or None for `all`."""
        if scope == SCOPE_ALL:
            return None
        if scope == SCOPE_OWN:
            return Order.sale_user_id == actor.id
        if scope == SCOPE_DEPARTMENT:
            # Subtree semantics (#26): phòng mình + mọi đơn vị con (GĐKD thấy các team).
            dept_ids = dept_subtree_ids(self.db, actor.department_id)
            if not dept_ids:
                return Order.sale_user_id == actor.id
            dept_sales = select(User.id).where(User.department_id.in_(dept_ids))
            return Order.sale_user_id.in_(dept_sales)
        raise ValueError(f"Unknown scope: {scope!r}")

    def can_access(self, *, order: Order, scope: str, actor) -> bool:
        """Whether `actor` may see this one order under `scope` (detail/edit guard)."""
        if scope == SCOPE_ALL:
            return True
        if scope == SCOPE_OWN:
            return order.sale_user_id == actor.id
        if scope == SCOPE_DEPARTMENT:
            if order.sale_user_id is None:
                return False
            if order.sale_user_id == actor.id:
                return True
            owner = self.db.get(User, order.sale_user_id)
            if owner is None or owner.department_id is None:
                return False
            return owner.department_id in dept_subtree_ids(self.db, actor.department_id)
        raise ValueError(f"Unknown scope: {scope!r}")

    def drafts_in_scope(self, *, scope: str, actor) -> list[Order]:
        """Đơn còn NHÁP trong phạm vi — nuôi badge 'việc chờ TÔI' (tập nháp nhỏ, bounded)."""
        stmt = select(Order).where(Order.status == "draft")
        cond = self._scope_condition(scope=scope, actor=actor)
        if cond is not None:
            stmt = stmt.where(cond)
        return list(self.db.execute(stmt).scalars().all())

    def line_total_sum(self, order_id: int) -> int | None:
        """Tổng dự kiến = Σ line_total (None if no priced line)."""
        val = self.db.execute(
            select(func.sum(OrderLine.line_total)).where(OrderLine.order_id == order_id)
        ).scalar()
        return int(val) if val is not None else None

    def unpriced_line_count(self, order_id: int) -> int:
        """Số dòng đơn CHƯA có giá (line_total IS NULL) — chặn chốt khi còn dòng chưa định giá
        (nếu không, tổng cọc yêu cầu bị thiếu vì Σ bỏ qua dòng null)."""
        val = self.db.execute(
            select(func.count())
            .select_from(OrderLine)
            .where(OrderLine.order_id == order_id, OrderLine.line_total.is_(None))
        ).scalar()
        return int(val or 0)

    def order_cost_sum(self, order_id: int) -> int | None:
        """Tổng giá vốn snapshot của đơn = Σ OrderLine.cost_snapshot (A2, soi biên). None nếu
        MỌI dòng đều thiếu giá vốn (đơn cũ trước A2 / báo giá không có cost) → không soi được biên.
        Dòng có cost + dòng None lẫn lộn: func.sum bỏ qua None → trả tổng phần có (chấp nhận được;
        đơn A2 thật thì mọi dòng đều có cost)."""
        val = self.db.execute(
            select(func.sum(OrderLine.cost_snapshot)).where(OrderLine.order_id == order_id)
        ).scalar()
        return int(val) if val is not None else None

    def total_with_vat(self, order_id: int) -> int:
        """Tổng đơn GỒM VAT ước = Σ line_total·(1 + vat_pct_estimate/100) — base tính cọc (cọc là
        tiền mặt thật khách đưa, gồm VAT). Dòng chưa định giá (line_total NULL) bỏ qua như
        line_total_sum. Số nguyên (floor) — đủ cho ngưỡng cọc."""
        val = self.db.execute(
            select(func.sum(_line_total_with_vat()))
            .where(OrderLine.order_id == order_id)
        ).scalar()
        return int(val) // 100 if val is not None else 0

    def money_sums(self, order_ids: list[int]) -> dict[int, dict]:
        """Batch của `line_total_sum` + `total_with_vat` + `order_cost_sum` — MỘT câu cho cả trang.

        Màn danh sách trước đây gọi ba hàm lẻ đó cho TỪNG đơn (N+1: 3 câu × số dòng hiển thị).
        Ở đây gom một câu `GROUP BY order_id`.

        Đơn KHÔNG có dòng nào sẽ vắng mặt trong map — caller phải mặc định đúng như bản lẻ:
        `total=None`, `order_cost=None`, `total_with_vat=0`.
        """
        if not order_ids:
            return {}
        stmt = (
            select(
                OrderLine.order_id,
                func.sum(OrderLine.line_total),
                func.sum(_line_total_with_vat()),
                func.sum(OrderLine.cost_snapshot),
            )
            .where(OrderLine.order_id.in_(order_ids))
            .group_by(OrderLine.order_id)
        )
        out: dict[int, dict] = {}
        for oid, total, with_vat, cost in self.db.execute(stmt):
            out[int(oid)] = {
                "total": int(total) if total is not None else None,
                # //100 vì biểu thức nhân với (100 + vat_pct) — khớp total_with_vat() bản lẻ.
                "total_with_vat": int(with_vat) // 100 if with_vat is not None else 0,
                "order_cost": int(cost) if cost is not None else None,
            }
        return out

    def list(
        self,
        *,
        scope: str,
        actor,
        q: str | None = None,
        status: str | None = None,
        order_kind: str | None = None,
        sort: str = "-created_at",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Order], int, dict[int, str], dict[int, int | None]]:
        """Return (rows, total, customer_names, totals). `q` matches order_no + customer
        name (case-insensitive substring). `status`/`order_kind` are exact filters. `total`
        is the count BEFORE pagination. `customer_names` maps order_id → customer name and
        `totals` maps order_id → tổng dự kiến, both for the page only (no N+1)."""
        conditions = []
        scope_cond = self._scope_condition(scope=scope, actor=actor)
        if scope_cond is not None:
            conditions.append(scope_cond)

        base = select(Order)
        count_stmt = select(func.count()).select_from(Order)
        if q:
            like = f"%{q.strip().lower()}%"
            cust_ids = select(Customer.id).where(func.lower(Customer.name).like(like))
            conditions.append(
                or_(
                    func.lower(Order.order_no).like(like),
                    Order.customer_id.in_(cust_ids),
                )
            )
        if status:
            conditions.append(Order.status == status)
        if order_kind:
            conditions.append(Order.order_kind == order_kind)

        for c in conditions:
            base = base.where(c)
            count_stmt = count_stmt.where(c)

        total = self.db.execute(count_stmt).scalar_one()

        direction = asc
        key = sort or "-created_at"
        if key.startswith("-"):
            direction = desc
            key = key[1:]
        col = _SORTABLE.get(key, Order.created_at)
        base = base.order_by(direction(col), Order.id.asc())

        page = max(1, page)
        size = max(1, min(size, 200))
        base = base.offset((page - 1) * size).limit(size)

        rows = list(self.db.execute(base).scalars())

        names: dict[int, str] = {}
        cust_ids_on_page = [r.customer_id for r in rows if r.customer_id is not None]
        if cust_ids_on_page:
            for oid, name in self.db.execute(
                select(Order.id, Customer.name)
                .join(Customer, Customer.id == Order.customer_id)
                .where(Order.id.in_([r.id for r in rows]))
            ):
                names[oid] = name

        totals: dict[int, int | None] = {}
        if rows:
            for oid, s in self.db.execute(
                select(OrderLine.order_id, func.sum(OrderLine.line_total))
                .where(OrderLine.order_id.in_([r.id for r in rows]))
                .group_by(OrderLine.order_id)
            ):
                totals[oid] = int(s) if s is not None else None

        return rows, total, names, totals

    # --- writes -------------------------------------------------------------

    def _next_order_no(self) -> str:
        """Next sequential order number: 'DH' + zero-padded number (DH001, DH002…). NOT
        `PB###` (mã phòng ban). Pattern chưa xác nhận với SVN — DH### is the working default."""
        max_n = 0
        for no in self.db.execute(select(Order.order_no)).scalars():
            if no and no.startswith("DH"):
                try:
                    max_n = max(max_n, int(no[2:]))
                except ValueError:
                    continue
        return f"DH{max_n + 1:03d}"

    def create(self, *, lines: list[dict], **order_fields) -> Order:
        """Tạo đơn + dòng. `order_fields` = giá trị các cột `orders` do OrderService chuẩn bị
        (source_type/customer_id/quotation_*/deposit_pct/cost_basis/needs_approval/... — service
        kiểm hợp lệ). `order_no` tự sinh (DH###). Mỗi phần tử `lines` là dict cột `order_lines`."""
        order = Order(order_no=self._next_order_no(), **order_fields)
        for ln in lines:
            order.lines.append(
                OrderLine(
                    description=ln.get("description", ""),
                    qty=ln.get("qty", 1),
                    unit_price_snapshot=ln.get("unit_price_snapshot"),
                    norm_snapshot=ln.get("norm_snapshot"),
                    vat_pct_estimate=ln.get("vat_pct_estimate", 0),
                    line_total=ln.get("line_total"),
                    cost_snapshot=ln.get("cost_snapshot"),  # giá vốn dòng (soi biên)
                    phieu_thanh_phan_id=ln.get("phieu_thanh_phan_id"),  # pin ấn phẩm (soft)
                    nhom=ln.get("nhom"),   # nhãn gộp dòng khi in xác nhận đơn (khớp bản báo giá)
                    don_vi_tinh=ln.get("don_vi_tinh", "cái"),   # ĐVT dòng (kéo từ báo giá / gõ tay)
                )
            )
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def stats(self, *, scope: str, actor) -> dict[str, int]:
        """Đếm đơn theo trạng thái (cho thanh tab), tôn trọng data-scope."""
        from ..models.order import STATUS_CANCELLED, STATUS_DRAFT, STATUS_ORDERED

        base = self._scope_condition(scope=scope, actor=actor)

        def cnt(*extra) -> int:
            stmt = select(func.count()).select_from(Order)
            if base is not None:
                stmt = stmt.where(base)
            for c in extra:
                stmt = stmt.where(c)
            return int(self.db.execute(stmt).scalar_one())

        return {
            "all": cnt(),
            "draft": cnt(Order.status == STATUS_DRAFT),
            "ordered": cnt(Order.status == STATUS_ORDERED),
            "cancelled": cnt(Order.status == STATUS_CANCELLED),
        }

    def value_rows(self, *, scope: str, actor, statuses: tuple[str, ...]) -> dict[int, dict]:
        """Nguyên liệu tính KPI tiền cho từng đơn trong phạm vi (status ∈ statuses):
        `{order_id: {status, deposit_pct, total_with_vat}}`. total_with_vat khớp ĐÚNG helper
        `total_with_vat` (Σ line_total·(100+vat) rồi //100 theo TỪNG đơn) → KPI = tổng số per-row,
        không lệch. 1 truy vấn GROUP BY, không N+1."""
        base = self._scope_condition(scope=scope, actor=actor)
        stmt = (
            select(
                Order.id,
                Order.status,
                Order.deposit_pct,
                func.coalesce(func.sum(_line_total_with_vat()), 0),
            )
            .select_from(Order)
            .join(OrderLine, OrderLine.order_id == Order.id, isouter=True)
            .where(Order.status.in_(statuses))
            .group_by(Order.id, Order.status, Order.deposit_pct)
        )
        if base is not None:
            stmt = stmt.where(base)
        out: dict[int, dict] = {}
        for oid, status, pct, num in self.db.execute(stmt):
            out[int(oid)] = {"status": status, "deposit_pct": pct, "total_with_vat": int(num) // 100}
        return out

    # V5: Σ cọc đã thu chuyển sang AccountingRepository.received_deposit_sum (cọc = PaymentReceipt).

    def active_order_for_quotation(self, quotation_id: int) -> Order | None:
        """Đơn CHƯA hủy đang tham chiếu báo giá này (guard 1 báo giá → 1 đơn)."""
        from ..models.order import STATUS_CANCELLED

        return self.db.execute(
            select(Order)
            .where(Order.quotation_id == quotation_id, Order.status != STATUS_CANCELLED)
            .limit(1)
        ).scalar_one_or_none()

    def update(self, order: Order, **fields) -> Order:
        for key, value in fields.items():
            setattr(order, key, value)
        self.db.commit()
        self.db.refresh(order)
        return order
