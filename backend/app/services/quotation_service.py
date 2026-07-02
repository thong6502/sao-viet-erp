"""Báo giá (Quotation) business logic — spec-09-bao-gia.

Framework-agnostic: raises domain errors the router maps to HTTP. Enforces the spec's
rules (F1..F7):
  - **F2 giá bán** = ``cost_von_total + margin − discount``; margin/discount ≥ 0,
    discount ≤ (giá vốn + margin) (chiết khấu > 100% chặn); recomputed on every save.
  - Edit only when ``status == draft`` (sửa phiếu khác draft → chặn; đổi giá → change_order).
  - ``valid_until`` ≥ hôm nay on save.
  - **F3 snapshot copy-on-write (P0)**: at Chốt giá / Gửi we freeze ``unit_price_snapshot``
    AND ``norm_snapshot`` + ``price_effective_from/to`` — NO live FK to the price/norm
    tables; a later price change never rewrites a sent phiếu.
  - **F4 vòng đời/version**: transitions go through the state machine; ``change_order``
    creates a NEW version (same code) and supersedes the current one; ``row_version``
    optimistic locking (stale → 409).
  - **F5 duyệt**: approve/reject need the approver permission (ngưỡng X/Y — SVN-input,
    ⚠️ chưa xác nhận; at P0 = manager scope of ``bao_gia``); past ``valid_until`` → expired
    (chặn duyệt).

SEAM reads (owned by this consumer per DIP):
  - **SEAM-13** ``EstimateCostingAdapter`` (Tính giá) — CLOSED: a quotation referencing a
    *calculated* estimate pulls cost_von_total + copy-on-write price/norm snapshots for the
    chosen quantity point (bậc SL). Without the injected repo the port still raises →
    "Tính giá chưa sẵn sàng" (never a fabricated cost).
  - **SEAM-14** ``CustomerRefAdapter`` (CRM) — CLOSED: resolves the live customer name /
    credit display (read-only, no block).
"""
from __future__ import annotations

from datetime import date

from ..models.quotation import (
    QUOTATION_STATUSES,
    STATUS_APPROVED,
    STATUS_CANCELLED,
    STATUS_CHANGE_ORDER,
    STATUS_DRAFT,
    STATUS_EXPIRED,
    STATUS_SENT,
    Quotation,
)
from ..models.role import SCOPE_ALL, SCOPE_DEPARTMENT
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.quotation_repo import QuotationRepository
from ..services import quotation_ports
from ..services.quotation_state import transition_for


class QuotationError(Exception):
    """Base for quotation domain errors."""


class QuotationValidationError(QuotationError):
    """A field failed validation (negative amount, discount > cost+margin, past date…)."""


class QuotationNotFound(QuotationError):
    """No quotation with that id (or not visible under the caller's scope)."""


class QuotationForbidden(QuotationError):
    """The quotation exists but is outside the caller's data scope, OR the caller lacks
    the approver permission for an approve/reject."""


class QuotationConflict(QuotationError):
    """Optimistic-lock clash (stale row_version) or an illegal state transition."""


class QuotationLocked(QuotationError):
    """Attempt to edit a quotation that is not in `draft` (dùng change_order để đổi giá)."""


class CostingUnavailable(QuotationError):
    """The referenced Tính giá can't yield a frozen cost (repo not wired / not found / not
    calculated / blocking errors). Carries the user-facing message — never a fake cost."""


class QuotationService:
    def __init__(
        self,
        quotations: QuotationRepository,
        audit: AuditLogRepository,
        customers=None,
        estimates=None,
    ) -> None:
        self.quotations = quotations
        self.audit = audit
        # SEAM-14 CLOSED: the CRM adapter (read-only). Injectable for tests.
        self._customers = customers
        # SEAM-13 CLOSED: the Tính giá (Estimate) repository. Injectable for tests; when
        # absent the port raises and every costing read surfaces CostingUnavailable.
        self._estimates = estimates

    def _costing_result(
        self,
        costing_id: int,
        quantity: int | None = None,
        cost_hint: int | None = None,
    ) -> quotation_ports.CostingResult:
        """Pull the frozen Tính giá result via SEAM-13. Raises CostingUnavailable with the
        user-facing reason when the result can't be produced (never a fabricated cost)."""
        try:
            return quotation_ports.get_costing_result(
                costing_id, quantity=quantity, cost_hint=cost_hint, estimates=self._estimates
            )
        except (NotImplementedError, quotation_ports.CostingLookupError) as exc:
            raise CostingUnavailable(str(exc)) from exc

    def costing_picker(
        self, costing_id: int, quantity: int | None = None
    ) -> quotation_ports.CostingResult:
        """Picker read for the Báo giá form: frozen giá vốn + the quantity points (bậc SL)
        of the referenced Tính giá."""
        return self._costing_result(costing_id, quantity=quantity)

    # --- validation helpers -------------------------------------------------

    @staticmethod
    def _validate_amount(value, label: str) -> int:
        if value is None:
            return 0
        if not isinstance(value, int) or isinstance(value, bool):
            raise QuotationValidationError(f"{label} phải là số nguyên (VND).")
        if value < 0:
            raise QuotationValidationError(f"{label} không được âm.")
        return value

    @staticmethod
    def _validate_valid_until(valid_until: date | None) -> date | None:
        if valid_until is None:
            return None
        if valid_until < date.today():
            raise QuotationValidationError("Hạn hiệu lực không được ở quá khứ.")
        return valid_until

    @staticmethod
    def compute_total(cost_von_total: int | None, margin: int, discount: int) -> int | None:
        """Giá bán = giá vốn + lãi − chiết khấu (F2). None when giá vốn is not yet known
        (SEAM-13 chưa nạp) so the UI shows "—" rather than a wrong number."""
        if cost_von_total is None:
            return None
        return cost_von_total + margin - discount

    def _validate_pricing(
        self, *, cost_von_total: int | None, margin: int, discount: int
    ) -> tuple[int | None, int, int, int | None]:
        cost = None if cost_von_total is None else self._validate_amount(
            cost_von_total, "Giá vốn"
        )
        margin = self._validate_amount(margin, "Lãi")
        discount = self._validate_amount(discount, "Chiết khấu")
        if cost is not None and discount > cost + margin:
            # chiết khấu > 100% của (giá vốn + lãi) → tổng âm; chặn.
            raise QuotationValidationError(
                "Chiết khấu không được vượt quá giá vốn cộng lãi."
            )
        total = self.compute_total(cost, margin, discount)
        return cost, margin, discount, total

    def _customer_ref(self, customer_id: int | None):
        """Resolve the customer display via SEAM-14 (CLOSED). None when no customer/repo."""
        if customer_id is None or self._customers is None:
            return None
        return quotation_ports.CustomerRefAdapter(self._customers).get_customer(customer_id)

    # --- reads --------------------------------------------------------------

    def list_quotations(
        self,
        *,
        scope: str,
        actor,
        q: str | None = None,
        status: str | None = None,
        sort: str = "-created_at",
        page: int = 1,
        size: int = 20,
    ):
        return self.quotations.list(
            scope=scope, actor=actor, q=q, status=status, sort=sort, page=page, size=size
        )

    def get_quotation(self, *, quotation_id: int, scope: str, actor) -> Quotation:
        quotation = self.quotations.get_by_id(quotation_id)
        if quotation is None:
            raise QuotationNotFound("Không tìm thấy báo giá.")
        if not self.quotations.can_access(quotation=quotation, scope=scope, actor=actor):
            raise QuotationForbidden("Bạn không có quyền xem báo giá này.")
        return quotation

    def version_history(self, quotation: Quotation) -> list[Quotation]:
        return self.quotations.versions_of(quotation.code)

    def customer_display(self, quotation: Quotation):
        return self._customer_ref(quotation.customer_id)

    # --- writes: create / update (draft only) -------------------------------

    def create_quotation(
        self,
        *,
        customer_id: int | None,
        costing_id: int | None,
        cost_von_total: int | None,
        margin: int,
        discount: int,
        valid_until: date | None,
        actor,
    ) -> Quotation:
        cost, margin, discount, total = self._validate_pricing(
            cost_von_total=cost_von_total, margin=margin, discount=discount
        )
        valid_until = self._validate_valid_until(valid_until)

        quotation = self.quotations.create(
            customer_id=customer_id,
            costing_id=costing_id,
            cost_von_total=cost,
            margin=margin,
            discount=discount,
            total=total,
            valid_until=valid_until,
            sale_user_id=actor.id,
            status=STATUS_DRAFT,
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="create_quote",
            target=f"quotation:{quotation.id}",
            detail=f"{quotation.code} v{quotation.version} (KH={customer_id}, CG={costing_id})",
        )
        return quotation

    def update_quotation(
        self,
        *,
        quotation_id: int,
        scope: str,
        actor,
        customer_id: int | None,
        costing_id: int | None,
        cost_von_total: int | None,
        margin: int,
        discount: int,
        valid_until: date | None,
        row_version: int,
    ) -> Quotation:
        quotation = self.get_quotation(quotation_id=quotation_id, scope=scope, actor=actor)
        if quotation.status != STATUS_DRAFT:
            raise QuotationLocked(
                "Chỉ sửa được báo giá ở trạng thái nháp. Dùng Re-quote để đổi giá."
            )
        if row_version != quotation.row_version:
            raise QuotationConflict("Phiếu vừa được thay đổi, vui lòng tải lại.")

        cost, margin, discount, total = self._validate_pricing(
            cost_von_total=cost_von_total, margin=margin, discount=discount
        )
        valid_until = self._validate_valid_until(valid_until)

        self.quotations.update(
            quotation,
            customer_id=customer_id,
            costing_id=costing_id,
            cost_von_total=cost,
            margin=margin,
            discount=discount,
            total=total,
            valid_until=valid_until,
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="update_quote",
            target=f"quotation:{quotation.id}",
            detail=f"{quotation.code} v{quotation.version}",
        )
        return quotation

    # --- writes: lifecycle transitions --------------------------------------

    def _can_approve(self, actor, scope: str) -> bool:
        """Whether the actor may approve/reject (ngưỡng X/Y — SVN-input, ⚠️ chưa xác nhận).
        At P0: a manager (bao_gia scope department|all), not a Sale (own)."""
        return scope in (SCOPE_DEPARTMENT, SCOPE_ALL)

    def _apply_expiry(self, quotation: Quotation) -> None:
        """Flip a sent/on_hold quotation to expired if past valid_until (observable guard,
        chặn duyệt). Idempotent."""
        if (
            quotation.status in (STATUS_SENT,)
            and quotation.valid_until is not None
            and quotation.valid_until < date.today()
        ):
            quotation.status = STATUS_EXPIRED

    def transition(
        self,
        *,
        quotation_id: int,
        to_status: str,
        scope: str,
        actor,
        row_version: int | None = None,
        cancel_reason: str | None = None,
    ) -> Quotation:
        """Move a quotation to `to_status` per the state machine. Freezes the snapshot on
        Chốt giá / Gửi (draft→sent). Approve/reject need the approver permission; cancel
        needs a reason. Illegal transitions → QuotationConflict."""
        quotation = self.get_quotation(quotation_id=quotation_id, scope=scope, actor=actor)

        if to_status not in QUOTATION_STATUSES:
            raise QuotationValidationError("Trạng thái đích không hợp lệ.")

        # Time guard: a past-hạn sent phiếu is expired before any approve attempt.
        self._apply_expiry(quotation)

        if row_version is not None and row_version != quotation.row_version:
            raise QuotationConflict("Phiếu vừa được thay đổi, vui lòng tải lại.")

        rule = transition_for(quotation.status, to_status)
        if rule is None:
            raise QuotationConflict(
                f"Không thể chuyển '{quotation.status}' → '{to_status}'."
            )

        if rule.requires_approval and not self._can_approve(actor, scope):
            raise QuotationForbidden("Bạn không có quyền duyệt báo giá.")

        reason = (cancel_reason or "").strip() if rule.requires_reason else None
        if rule.requires_reason and not reason:
            raise QuotationValidationError("Cần nêu lý do hủy.")

        fields: dict = {"status": to_status}
        if rule.snapshots:
            fields.update(self._freeze_snapshot(quotation))
        if to_status == STATUS_CANCELLED:
            fields["cancel_reason"] = reason
            fields["cancelled_at_state"] = quotation.status

        self.quotations.update(quotation, **fields)
        self.audit.create(
            actor_user_id=actor.id,
            action=rule.action,
            target=f"quotation:{quotation.id}",
            detail=f"{quotation.code} v{quotation.version}: {quotation.status}→{to_status}"
            + (f" ({reason})" if reason else ""),
        )
        return quotation

    def _freeze_snapshot(self, quotation: Quotation) -> dict:
        """P0 copy-on-write freeze (§34 L877-879): store unit_price_snapshot AND
        norm_snapshot + the source price window. Both vế phải có mặt — a snapshot thiếu vế
        định mức = cùng lỗ như FK giá sống.

        Prefers the frozen Tính giá result via SEAM-13 (cost_hint = giá vốn phiếu đang giữ,
        để snapshot đúng mức bậc-SL KD đã chọn). When the costing can't be read (repo not
        wired / estimate gone / not calculated) we freeze a self-contained snapshot of the
        numbers the quotation already holds (giá vốn / lãi / chiết khấu the KD entered) —
        an explicit, honest copy, NOT a fabricated cost pulled from a live price table."""
        try:
            result = (
                self._costing_result(
                    quotation.costing_id, cost_hint=quotation.cost_von_total
                )
                if quotation.costing_id
                else None
            )
        except CostingUnavailable:
            result = None

        if result is not None:
            return {
                "unit_price_snapshot": dict(result.unit_price_snapshot),
                "norm_snapshot": dict(result.norm_snapshot),
                "price_effective_from": result.price_effective_from,
                "price_effective_to": result.price_effective_to,
            }

        # Self-contained freeze from the entered numbers (P0 shape preserved: BOTH vế).
        today = date.today()
        return {
            "unit_price_snapshot": {
                "cost_von_total": quotation.cost_von_total,
                "margin": quotation.margin,
                "discount": quotation.discount,
                "total": quotation.total,
                "source": "manual" if quotation.costing_id is None else "costing_ref",
                "costing_id": quotation.costing_id,
            },
            "norm_snapshot": {
                # Định mức vế: at P0 the Tính giá norm engine is TREO (SEAM-09), so the
                # captured norms are the reference itself — recorded so the pair is never
                # half-frozen. Real norms fill in when SEAM-13/09 close.
                "costing_id": quotation.costing_id,
                "frozen_at": today.isoformat(),
                "note": "norm engine TREO (SEAM-09); snapshot giữ tham chiếu để không nửa vời",
            },
            "price_effective_from": today,
            "price_effective_to": quotation.valid_until,
        }

    # --- writes: re-quote (change_order → new version) ----------------------

    def requote(self, *, quotation_id: int, scope: str, actor) -> Quotation:
        """Re-quote (change_order, F4): supersede the current phiếu (→ change_order) and
        create a NEW draft version (same code, version+1) so the old phiếu stays traceable.
        Returns the NEW version."""
        current = self.get_quotation(quotation_id=quotation_id, scope=scope, actor=actor)

        rule = transition_for(current.status, STATUS_CHANGE_ORDER)
        if rule is None:
            raise QuotationConflict(
                f"Không thể re-quote từ trạng thái '{current.status}'."
            )

        new_version = self.quotations.create(
            customer_id=current.customer_id,
            costing_id=current.costing_id,
            cost_von_total=current.cost_von_total,
            margin=current.margin,
            discount=current.discount,
            total=current.total,
            valid_until=current.valid_until,
            sale_user_id=actor.id,
            code=current.code,
            version=current.version + 1,
            status=STATUS_DRAFT,
        )
        # Supersede the old one (keeps its history).
        self.quotations.update(current, status=STATUS_CHANGE_ORDER)
        self.audit.create(
            actor_user_id=actor.id,
            action="change_order",
            target=f"quotation:{new_version.id}",
            detail=f"{current.code}: v{current.version}→v{new_version.version} (re-quote)",
        )
        return new_version
