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
    APPROVAL_DECISION_APPROVED,
    APPROVAL_DECISIONS,
    ORDER_KIND_BO_SUNG,
    ORDER_KINDS,
    ORDER_TYPES,
    STATUS_CANCELLED,
    STATUS_CHANGE_ORDER,
    STATUS_DRAFT,
    STATUS_ORDERED,
    Order,
)
from ..models.payment import PAYMENT_KIND_DEPOSIT, PAYMENT_METHODS
from ..models.quotation import STATUS_ACCEPTED as QUOTE_STATUS_ACCEPTED
from ..models.quotation import STATUS_CONVERTED_TO_ORDER as QUOTE_STATUS_CONVERTED
from ..models.role import SCOPE_ALL, SCOPE_DEPARTMENT
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.order_repo import OrderRepository
from ..services import order_ports
from ..services.exception_gate import (
    approval_status as _exc_approval_status,
    evaluate as _exc_evaluate,
)
from ..services.order_state import transition_for

# Mặc định CHUNG % cọc mở SX khi khách CHƯA đặt điều khoản riêng. Khách có % riêng qua hồ sơ CRM
# (`customers.prepay_pct` — điều khoản trả trước) → `_deposit_pct()` ưu tiên số của khách. Chỉnh
# được KHÔNG cần sửa code (đổi ở hồ sơ khách, hoặc đổi mặc định chung). Số chờ SVN chốt cuối.
DEFAULT_MIN_DEPOSIT_PCT = 50

# A2 — ngưỡng "đơn đặc thù" giờ ở module CHUNG `exception_gate` (dùng chung Đơn hàng + Báo giá,
# một nguồn định nghĩa). Re-import DEFAULT_MIN_MARGIN_PCT / DEFAULT_HIGH_VALUE_THRESHOLD ở trên.


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
        payments=None,
        approvals=None,
    ) -> None:
        self.orders = orders
        self.audit = audit
        # SEAM-04 quotation_ref half CLOSED-live: the Báo giá repo (read-only). Injectable.
        self._quotations = quotations
        # CRM repo (read-only) to resolve the customer display name (kéo từ báo giá).
        self._customers = customers
        # SEAM-04 deposit half CLOSED-live (feat-048): Payment repo — ghi/đọc cọc. None = mis-wire
        # → deposit_total raises DepositUnavailable (never a fabricated paid amount).
        self._payments = payments
        # A2: OrderApproval repo — duyệt "đơn đặc thù". None = mis-wire → coi như CHƯA có bản duyệt
        # (đơn đặc thù bị chặn chốt) thay vì ngầm cho qua.
        self._approvals = approvals

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

    def _deposit_pct(self, order: Order) -> float:
        """% cọc áp cho đơn: ưu tiên điều khoản trả trước của KHÁCH (hồ sơ CRM `prepay_pct`);
        khách chưa đặt (hoặc đơn chưa gắn khách) → mặc định CHUNG. Chỉnh được không cần sửa code."""
        if self._customers is not None and order.customer_id is not None:
            c = self._customers.get_by_id(order.customer_id)
            pct = getattr(c, "prepay_pct", None) if c is not None else None
            if pct is not None and pct > 0:
                return float(pct)
        return float(DEFAULT_MIN_DEPOSIT_PCT)

    def deposit_total(self, order_id: int) -> int:
        """Cọc đã thu (VND, NET thu−hoàn) qua bảng Payment — SEAM-04 (deposit) LIVE (feat-048).
        Mis-wired (không inject repo Payment) → DepositUnavailable, never a fabricated amount."""
        if self._payments is None:
            raise DepositUnavailable("SEAM-04 (deposit_payment) cần repository Payment")
        return self._payments.deposit_total(order_id)

    def gate_status(self, order: Order) -> dict:
        """Compute the ③→④ gate view (F3): tổng, tổng-gồm-VAT (base cọc), ngưỡng cọc, cọc đã thu,
        còn thiếu, chốt được chưa. % cọc theo KHÁCH (`prepay_pct`) hoặc mặc định chung. Base cọc =
        GỒM VAT (cọc là tiền mặt thật khách đưa). Chặn chốt khi còn dòng CHƯA định giá."""
        total = self.orders.line_total_sum(order.id) or 0
        # Base cọc = giá trị đơn GỒM VAT; % theo khách/mặc định.
        total_payment = self.orders.total_with_vat(order.id)
        pct = self._deposit_pct(order)
        required = int(total_payment * pct / 100)
        all_lines_priced = self.orders.unpriced_line_count(order.id) == 0
        try:
            paid = self.deposit_total(order.id)
            deposit_available = True
        except DepositUnavailable:
            paid = 0
            deposit_available = False
        approved = order.quotation_id is not None  # pinned only from an approved quotation
        shortfall = max(0, required - paid)
        # A2: soi "đơn đặc thù" + tình trạng duyệt của GĐ. can_confirm phải thêm điều kiện đã cleared.
        exc = self._exception_eval(order)
        appr = self._approval_status(order, exc)
        can_confirm = (
            approved
            and deposit_available
            and all_lines_priced
            and total > 0
            and paid >= required
            and appr["cleared"]
        )
        return {
            "total": total,
            "total_payment": total_payment,
            "min_deposit_pct": int(round(pct)),
            "deposit_required": required,
            "deposit_paid": paid if deposit_available else None,
            "deposit_available": deposit_available,
            "deposit_shortfall": shortfall,
            "quotation_approved": approved,
            "all_lines_priced": all_lines_priced,
            # A2 — đơn đặc thù (GĐ duyệt). `exceptions` = nhãn định tính (an toàn cho mọi vai);
            # `margin_pct` là số nhạy cảm (router STRIP nếu người xem không có quyền duyệt đặc thù).
            "exception_required": appr["required"],
            "exception_status": appr["status"],       # none|pending|approved|rejected|stale
            "exception_cleared": appr["cleared"],
            "exceptions": exc["triggers"],             # [{key,label}]
            "exception_note": appr["note"],
            "margin_pct": exc["margin_pct"],
            "can_confirm": can_confirm,
        }

    # --- A2: "đơn đặc thù" — soi điều kiện + tình trạng duyệt của Giám đốc -------

    def _exception_eval(self, order: Order) -> dict:
        """Soi 3 điều kiện 'đơn đặc thù' trên số HIỆN TẠI của đơn — DELEGATE về `exception_gate` (logic
        THUẦN dùng chung với Báo giá). subtotal = Σ line_total (trước VAT); total_gross = gồm VAT; cost =
        Σ cost_snapshot (None = không soi được biên)."""
        return _exc_evaluate(
            subtotal=self.orders.line_total_sum(order.id) or 0,
            total_gross=self.orders.total_with_vat(order.id),
            cost=self.orders.order_cost_sum(order.id),
        )

    def _approval_status(self, order: Order, exc: dict) -> dict:
        """Tình trạng duyệt 'đơn đặc thù' — DELEGATE về `exception_gate.approval_status`. Build `latest`
        từ bản duyệt gần nhất của ĐƠN (order_approvals)."""
        row = self._approvals.latest_for_order(order.id) if self._approvals is not None else None
        latest = None if row is None else {
            "decision": row.decision, "total": row.order_total, "subtotal": row.order_subtotal,
            "cost": row.order_cost, "note": row.note, "decided_at": row.decided_at,
        }
        return _exc_approval_status(exc, latest)

    def record_approval(
        self, *, order_id: int, decision: str, note: str | None, scope: str, actor
    ):
        """GĐ DUYỆT / TỪ CHỐI 'đơn đặc thù'. Chỉ khi đơn còn `draft` (trước chốt). Chặn nếu đơn KHÔNG
        thuộc diện đặc thù (không tạo bản duyệt vô nghĩa). Ghim số + ngưỡng hiện tại (audit); duyệt
        'bao phủ' → mở khóa chốt; đơn sau đó xấu đi → tự thành 'stale' (phải trình lại)."""
        if decision not in APPROVAL_DECISIONS:
            raise OrderValidationError("Quyết định không hợp lệ (chỉ 'approved' / 'rejected').")
        order = self.get_order(order_id=order_id, scope=scope, actor=actor)  # scope guard + load
        if order.status == STATUS_CANCELLED:
            raise OrderValidationError("Đơn đã hủy — không duyệt.")
        if order.status != STATUS_DRAFT:
            raise OrderValidationError("Chỉ duyệt 'đơn đặc thù' khi đơn còn nháp (trước chốt).")
        exc = self._exception_eval(order)
        if not exc["triggers"]:
            raise OrderValidationError("Đơn không thuộc diện đặc thù — không cần Giám đốc duyệt.")
        if self._approvals is None:
            raise NotImplementedError("A2 (order_approvals) cần repository OrderApproval")
        row = self._approvals.create(
            order_id=order.id,
            decision=decision,
            triggers=[t["key"] for t in exc["triggers"]],
            order_total=exc["total_gross"],
            order_subtotal=exc["subtotal"],
            order_cost=exc["cost"],
            margin_pct_snapshot=exc["margin_pct"],
            min_margin_pct=exc["min_margin_pct"],
            high_value_threshold=exc["high_value_threshold"],
            note=note,
            decided_by=actor.id,
        )
        verb = "duyệt" if decision == APPROVAL_DECISION_APPROVED else "từ chối"
        self.audit.create(
            actor_user_id=actor.id,
            action=f"order_exception_{decision}",
            target=f"order:{order.id}",
            detail=f"{order.order_no}: GĐ {verb} đơn đặc thù "
            f"({', '.join(t['key'] for t in exc['triggers'])})",
        )
        return row

    def list_approvals(self, *, order_id: int, scope: str, actor) -> list:
        """Lịch sử duyệt/từ chối 'đơn đặc thù' của đơn (scope-guarded)."""
        order = self.get_order(order_id=order_id, scope=scope, actor=actor)
        if self._approvals is None:
            return []
        return self._approvals.list_for_order(order.id)

    # --- deposit write (SEAM-04 deposit, LIVE) ------------------------------

    def record_deposit(
        self, *, order_id: int, amount: int, method: str, note: str | None, scope: str, actor
    ):
        """Ghi một khoản CỌC (Payment kind=deposit) cho đơn — mở khóa cổng chốt (③→④). Chỉ ghi
        khi đơn còn `draft` (trước chốt); cọc KHÔNG sinh hóa đơn (N5). Thu đợt sau chốt = Pha D."""
        if self._payments is None:
            raise DepositUnavailable("SEAM-04 (deposit_payment) cần repository Payment")
        order = self.get_order(order_id=order_id, scope=scope, actor=actor)  # scope guard + load
        if order.status == STATUS_CANCELLED:
            raise OrderValidationError("Đơn đã hủy — không ghi cọc.")
        if order.status != STATUS_DRAFT:
            raise OrderValidationError(
                "Chỉ ghi cọc khi đơn đang ở trạng thái nháp (trước chốt); thu đợt sau để phân hệ Công nợ."
            )
        amt = int(amount or 0)
        if amt <= 0:
            raise OrderValidationError("Số tiền cọc phải lớn hơn 0.")
        if method not in PAYMENT_METHODS:
            raise OrderValidationError("Hình thức thu không hợp lệ.")
        # customer_id LẤY TỪ ĐƠN (không nhận từ client) — tránh ghi nhầm sang khách khác.
        payment = self._payments.create(
            order_id=order.id,
            customer_id=order.customer_id,
            kind=PAYMENT_KIND_DEPOSIT,
            amount=amt,
            method=method,
            note=(note or None),
            created_by=actor.id,
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="record_deposit",
            target=f"order:{order.id}",
            detail=f"{order.order_no}: cọc {amt:,} đ ({method})".replace(",", "."),
        )
        return payment

    def list_payments(self, *, order_id: int, scope: str, actor) -> list:
        """Các khoản thu của đơn (scope-guarded). Rỗng nếu chưa thu."""
        order = self.get_order(order_id=order_id, scope=scope, actor=actor)
        if self._payments is None:
            raise DepositUnavailable("SEAM-04 (deposit_payment) cần repository Payment")
        return self._payments.list_by_order(order.id)

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
                    # A2: giá vốn TỔNG dòng snapshot copy-on-write từ báo giá (soi biên).
                    "cost_snapshot": ln.cost_snapshot,
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
        self._auto_clear_from_quote(order)
        self._lock_source_quote(order)
        return order

    def _lock_source_quote(self, order: Order) -> None:
        """B7 (redesign-bao-gia §3): khóa BÁO GIÁ GỐC sau khi lên đơn — `accepted → converted_to_order`
        — để KHÔNG tạo được đơn thứ 2 từ cùng báo giá (picker chỉ chọn báo giá `accepted`). Read-write
        qua repo Báo giá (cùng session). Chỉ khóa khi báo giá còn `accepted` (idempotent, an toàn)."""
        if order.quotation_id is None or self._quotations is None:
            return
        quote = self._quotations.get_by_id(order.quotation_id)
        if quote is not None and quote.status == QUOTE_STATUS_ACCEPTED:
            quote.status = QUOTE_STATUS_CONVERTED
            self._quotations.update(quote)

    def _auto_clear_from_quote(self, order: Order) -> None:
        """BG-2 "đơn tự thông": đơn tạo từ báo giá ĐÃ được GĐ duyệt (bao phủ) → materialize 1 bản duyệt
        A2 `approved` GHIM SỐ CỦA ĐƠN (không copy số báo giá — tránh lệch VAT chặn oan). A2 tự cleared,
        không hỏi GĐ lại phần giá. Chỉ khi đơn thuộc diện đặc thù + báo giá có bản duyệt gần nhất là
        `approved` (báo giá 'accepted' bắt buộc đã qua cổng §14.3 nên bản duyệt của nó bao phủ)."""
        if order.quotation_id is None or self._approvals is None or self._quotations is None:
            return
        exc = self._exception_eval(order)
        if not exc["triggers"]:
            return
        qa = self._quotations.latest_approval(order.quotation_id)
        if qa is None or qa.decision != APPROVAL_DECISION_APPROVED:
            return
        self._approvals.create(
            order_id=order.id,
            decision=APPROVAL_DECISION_APPROVED,
            triggers=[t["key"] for t in exc["triggers"]],
            order_total=exc["total_gross"],
            order_subtotal=exc["subtotal"],
            order_cost=exc["cost"],
            margin_pct_snapshot=exc["margin_pct"],
            min_margin_pct=exc["min_margin_pct"],
            high_value_threshold=exc["high_value_threshold"],
            note=f"Tự thông từ báo giá đã duyệt (BG-approval #{qa.id})",
            decided_by=qa.decided_by,
        )

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
                    # Mis-wire only (repo Payment không inject); bình thường cọc LIVE.
                    raise DepositUnavailable(
                        "SEAM-04 (deposit_payment) cần repository Payment — không chốt được."
                    )
                if not gate["all_lines_priced"]:
                    raise OrderValidationError(
                        "Còn dòng đơn chưa định giá — không thể chốt (tổng cọc yêu cầu sẽ thiếu)."
                    )
                # A2: đơn đặc thù chưa được GĐ duyệt (hoặc bị từ chối / đã đổi cần trình lại).
                if gate["exception_required"] and not gate["exception_cleared"]:
                    raise OrderValidationError(
                        {
                            "pending": "Đơn thuộc diện đặc thù — cần Giám đốc duyệt trước khi chốt.",
                            "rejected": "Đơn đặc thù đã bị Giám đốc TỪ CHỐI — không thể chốt.",
                            "stale": "Đơn đã đổi so với lúc Giám đốc duyệt — cần trình duyệt lại.",
                        }.get(gate["exception_status"], "Đơn đặc thù cần Giám đốc duyệt.")
                    )
                raise OrderValidationError(
                    "Chưa đủ điều kiện chốt đơn: cần báo giá đã duyệt và cọc đạt ngưỡng "
                    f"(còn thiếu {gate['deposit_shortfall']:,} đ).".replace(",", ".")
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
