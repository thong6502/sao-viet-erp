"""Đơn hàng bán (Order) business logic — spec-10-don-hang-ban (bước ④ CHỐT ĐƠN).

Framework-agnostic: raises domain errors the router maps to HTTP. Enforces the spec's rules
(F1..F8), làm-ngay slice (feat-046 model + feat-047 F1/F2; gate/chốt/đổi/hủy scaffolded):

  - **F1 nguồn = Báo giá đã duyệt (KHÔNG Tính giá)**: create requires an ``approved`` quotation
    còn hạn (read via SEAM-04 ``quotation_ref``, Báo giá LIVE); pins ``quotation_id +
    quotation_version + quotation_effective_from`` (C1) and snapshots the priced lines
    copy-on-write (``unit_price_snapshot`` + ``norm_snapshot``) — NO live FK to a price row.
  - **F2 loại đơn**: ``order_type ∈ {noi_bo, theo_yc}``, ``order_kind ∈ {moi, bo_sung}``;
    **đơn bổ sung BẮT BUỘC ``parent_order_id``** (thiếu → chặn). ``parent_order_id`` chỉ dùng
    cho bổ sung; đổi (change_order) giữ lịch sử qua Quotation-version (decision #5).
  - **Ẩn field vật lý**: no khổ/màu/kẽm/imposition/PrintForm ever enters an order-line (§29 P0).
  - **F3 gate ③→④** (chốt): ``quotation.approved AND deposit >= total*min_deposit_pct`` — the
    arithmetic (còn thiếu) runs now; the *deposit write/read* is TREO behind SEAM-04 (Payment),
    so at P0 ``deposit`` is treated as 0 (ghi cọc chưa mở) → chốt bị chặn cho tới feat-048.
  - **F8 đổi/hủy**: transitions through the state machine; ``change_order`` (đổi) + ``cancelled``
    (+cancel_reason, +cancelled_at_state) — AuditEntry ``cancel_job`` on cancel.

SEAM reads (owned by this consumer per DIP):
  - **SEAM-04** ``quotation_ref`` — CLOSED-live (Báo giá built): read approved quotation.
    ``deposit_payment`` — STILL raising (Payment chưa build): ghi cọc TREO (feat-048).
  - **SEAM-05** proof_gate · **SEAM-06** customer_paper_lot · **SEAM-01/02** progress/delivery
    — all raising (F4/F6/F7 TREO, feat-049).
"""
from __future__ import annotations

from ..models.order import (
    ORDER_KIND_BO_SUNG,
    ORDER_KINDS,
    ORDER_TYPES,
    STATUS_CANCELLED,
    STATUS_CHANGE_ORDER,
    STATUS_DRAFT,
    STATUS_ORDERED,
    Order,
)
from ..models.role import SCOPE_ALL, SCOPE_DEPARTMENT
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.order_repo import OrderRepository
from ..services import order_ports
from ..services.order_state import transition_for

# ngưỡng cọc mở SX — versioned, SVN nhập (⚠️ CHƯA XÁC NHẬN). At P0 a working default so the
# gate is observable; the real value comes from a versioned config when SVN confirms it.
DEFAULT_MIN_DEPOSIT_PCT = 30


class OrderError(Exception):
    """Base for order domain errors."""


class OrderValidationError(OrderError):
    """A field failed validation (bad enum, đơn bổ sung thiếu parent, báo giá không hợp lệ…)."""


class OrderNotFound(OrderError):
    """No order with that id (or not visible under the caller's scope)."""


class OrderForbidden(OrderError):
    """The order exists but is outside the caller's data scope."""


class OrderConflict(OrderError):
    """An illegal state transition or a locked-snapshot edit."""


class QuotationNotSelectable(OrderError):
    """The referenced quotation is not ``approved`` / còn hạn / not found — chặn chọn + lý do.
    Carries the reason so the UI can explain (F1 edge case)."""


class DepositUnavailable(OrderError):
    """SEAM-04 (deposit_payment) chưa back-fill — ghi/đọc cọc TREO (Payment chưa build)."""


class OrderService:
    def __init__(
        self,
        orders: OrderRepository,
        audit: AuditLogRepository,
        quotations=None,
        customers=None,
    ) -> None:
        self.orders = orders
        self.audit = audit
        # SEAM-04 quotation_ref half CLOSED-live: the Báo giá repo (read-only). Injectable.
        self._quotations = quotations
        # CRM repo (read-only) to resolve the customer display name (kéo từ báo giá).
        self._customers = customers

    # --- SEAM-04 quotation_ref (LIVE) ---------------------------------------

    def quotation_ref(self, quotation_id: int) -> order_ports.QuotationRef | None:
        """Read an approved quotation via SEAM-04 (quotation_ref half, Báo giá LIVE)."""
        if self._quotations is None:
            # Mis-wired composition root must fail loudly, never fabricate.
            raise NotImplementedError("SEAM-04 (quotation_ref) cần repository Báo giá")
        return order_ports.QuotationRefAdapter(self._quotations).get_quotation_ref(quotation_id)

    def approved_quotations(self, *, scope: str, actor):
        """F1 picker: approved quotations còn hạn choosable for an order (read live via
        SEAM-04 quotation_ref underlying repo). Returns (rows, customer_names)."""
        from datetime import date

        if self._quotations is None:
            raise NotImplementedError("SEAM-04 (quotation_ref) cần repository Báo giá")
        return self._quotations.list_approved_selectable(
            scope=scope, actor=actor, today=date.today()
        )

    def customer_display(self, order: Order):
        """Read-only customer display (kéo từ báo giá). None when no customer/repo (CRM read;
        never blocks). Display credit status shows the LIMIT side only — no fabricated AR."""
        if order.customer_id is None or self._customers is None:
            return None
        customer = self._customers.get_by_id(order.customer_id)
        if customer is None:
            return None
        if customer.credit_limit and customer.credit_limit > 0:
            credit = f"Hạn mức {customer.credit_limit:,} đ".replace(",", ".")
        else:
            credit = "Chưa đặt hạn mức"
        return {
            "customer_id": customer.id,
            "name": customer.name,
            "tax_code": customer.tax_code,
            "credit_status_display": credit,
        }

    # --- deposit / gate (F3) ------------------------------------------------

    @staticmethod
    def min_deposit_pct() -> int:
        return DEFAULT_MIN_DEPOSIT_PCT

    def deposit_total(self, order_id: int) -> int:
        """Cọc đã thu (VND). SEAM-04 (deposit_payment) TREO → raises DepositUnavailable; the
        caller treats an unavailable deposit as 0 for the gate math (chốt bị chặn), never a
        fabricated paid amount."""
        try:
            # SEAM-04: chờ Tài chính (Payment)
            return order_ports.deposit_total(order_id)
        except NotImplementedError as exc:
            raise DepositUnavailable(str(exc)) from exc

    def gate_status(self, order: Order) -> dict:
        """Compute the ③→④ gate view (F3): total dự kiến, ngưỡng, cọc đã thu (or unavailable),
        còn thiếu, and whether chốt is allowed. Pure arithmetic; deposit write is TREO."""
        total = self.orders.line_total_sum(order.id) or 0
        pct = self.min_deposit_pct()
        required = (total * pct) // 100
        try:
            paid = self.deposit_total(order.id)
            deposit_available = True
        except DepositUnavailable:
            paid = 0
            deposit_available = False
        approved = order.quotation_id is not None  # pinned only from an approved quotation
        shortfall = max(0, required - paid)
        can_confirm = approved and deposit_available and paid >= required and total > 0
        return {
            "total": total,
            "min_deposit_pct": pct,
            "deposit_required": required,
            "deposit_paid": paid if deposit_available else None,
            "deposit_available": deposit_available,
            "deposit_shortfall": shortfall,
            "quotation_approved": approved,
            "can_confirm": can_confirm,
        }

    # --- validation helpers -------------------------------------------------

    @staticmethod
    def _validate_enums(order_type: str, order_kind: str) -> None:
        if order_type not in ORDER_TYPES:
            raise OrderValidationError("Loại đơn (order_type) không hợp lệ.")
        if order_kind not in ORDER_KINDS:
            raise OrderValidationError("Loại đơn (order_kind) không hợp lệ.")

    def _validate_parent(self, *, order_kind: str, parent_order_id: int | None) -> int | None:
        """Đơn bổ sung BẮT BUỘC parent; đơn mới KHÔNG mang parent (F2)."""
        if order_kind == ORDER_KIND_BO_SUNG:
            if parent_order_id is None:
                raise OrderValidationError("Đơn bổ sung bắt buộc chọn đơn/job gốc.")
            parent = self.orders.get_by_id(parent_order_id)
            if parent is None:
                raise OrderValidationError("Không tìm thấy đơn gốc cho đơn bổ sung.")
            return parent_order_id
        # Đơn mới: ignore any parent sent by mistake.
        return None

    # --- reads --------------------------------------------------------------

    def list_orders(
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
    ):
        return self.orders.list(
            scope=scope, actor=actor, q=q, status=status, order_kind=order_kind,
            sort=sort, page=page, size=size,
        )

    def get_order(self, *, order_id: int, scope: str, actor) -> Order:
        order = self.orders.get_with_lines(order_id)
        if order is None:
            raise OrderNotFound("Không tìm thấy đơn hàng.")
        if not self.orders.can_access(order=order, scope=scope, actor=actor):
            raise OrderForbidden("Bạn không có quyền xem đơn hàng này.")
        return order

    # --- writes: create from an approved quotation (F1/F2) ------------------

    def create_order(
        self,
        *,
        quotation_id: int,
        order_type: str,
        order_kind: str,
        parent_order_id: int | None,
        has_customer_paper: bool,
        vat_pct_estimate: int,
        actor,
    ) -> Order:
        self._validate_enums(order_type, order_kind)
        parent_order_id = self._validate_parent(
            order_kind=order_kind, parent_order_id=parent_order_id
        )

        # F1: pull the quotation via SEAM-04 (quotation_ref LIVE). Only approved + còn hạn.
        ref = self.quotation_ref(quotation_id)
        if ref is None:
            raise QuotationNotSelectable("Không tìm thấy báo giá.")
        if not ref.approved:
            raise QuotationNotSelectable(
                "Chỉ chọn được báo giá đã duyệt (approved). Báo giá này chưa được duyệt "
                "hoặc đã bị từ chối/hết hạn."
            )

        vat = max(0, int(vat_pct_estimate or 0))
        # Snapshot copy-on-write the priced lines from the quotation (no FK to a live price).
        lines = []
        for ln in ref.lines:
            unit = ln.unit_price_snapshot
            line_total = None if unit is None else unit * ln.qty
            lines.append(
                {
                    "description": ln.description,
                    "qty": ln.qty,
                    "unit_price_snapshot": unit,
                    "norm_snapshot": ln.norm_snapshot,
                    "vat_pct_estimate": vat,
                    "line_total": line_total,
                }
            )

        order = self.orders.create(
            customer_id=ref.customer_id,           # khách kéo từ báo giá (read-only)
            quotation_id=ref.quotation_id,
            quotation_version=ref.version,          # C1 pin exact version
            quotation_effective_from=ref.effective_from,
            order_type=order_type,
            order_kind=order_kind,
            parent_order_id=parent_order_id,
            sale_user_id=actor.id,
            status=STATUS_DRAFT,
            has_customer_paper=has_customer_paper,
            vat_pct_estimate=vat,
            lines=lines,
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="create_order",
            target=f"order:{order.id}",
            detail=f"{order.order_no} ← BG#{ref.quotation_id} v{ref.version} "
            f"({order_type}/{order_kind})",
        )
        return order

    # --- writes: lifecycle transitions (F8) ---------------------------------

    def transition(
        self,
        *,
        order_id: int,
        to_status: str,
        scope: str,
        actor,
        cancel_reason: str | None = None,
    ) -> Order:
        """Move an order to `to_status` per the state machine. draft→ordered enforces the
        ③→④ gate + locks the snapshot; cancel needs a reason (+captures cancelled_at_state).
        Illegal transitions → OrderConflict."""
        order = self.get_order(order_id=order_id, scope=scope, actor=actor)

        rule = transition_for(order.status, to_status)
        if rule is None:
            raise OrderConflict(f"Không thể chuyển '{order.status}' → '{to_status}'.")

        if rule.gated:
            gate = self.gate_status(order)
            if not gate["can_confirm"]:
                if not gate["deposit_available"]:
                    raise DepositUnavailable(
                        "Chưa ghi được cọc — chờ phân hệ Tài chính (Payment). Không thể chốt đơn."
                    )
                raise OrderValidationError(
                    "Chưa đủ điều kiện chốt đơn: cần báo giá đã duyệt và cọc đạt ngưỡng "
                    f"(còn thiếu {gate['deposit_shortfall']:,} đ)."
                )

        reason = (cancel_reason or "").strip() if rule.requires_reason else None
        if rule.requires_reason and not reason:
            raise OrderValidationError("Cần nêu lý do hủy.")

        fields: dict = {"status": to_status}
        if to_status == STATUS_CANCELLED:
            fields["cancel_reason"] = reason
            fields["cancelled_at_state"] = order.status

        prev_status = order.status
        self.orders.update(order, **fields)
        self.audit.create(
            actor_user_id=actor.id,
            action=rule.action,
            target=f"order:{order.id}",
            detail=f"{order.order_no}: {prev_status}→{to_status}"
            + (f" ({reason})" if reason else ""),
        )
        return order
