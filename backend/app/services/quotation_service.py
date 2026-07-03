"""Báo giá (Quotation / Quote) business logic — Header-Version-Item (H-V-I) pattern.
"""
from __future__ import annotations

import math
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from ..models.quotation import (
    Quote,
    QuoteVersion,
    QuoteItem,
    STATUS_DRAFT,
    STATUS_SENT,
    STATUS_ACCEPTED,
    STATUS_REJECTED,
    STATUS_EXPIRED,
    STATUS_CONVERTED_TO_ORDER,
    STATUS_CANCELLED,
    VERSION_STATUS_DRAFT,
    VERSION_STATUS_LOCKED,
    VERSION_STATUS_SENT,
    VERSION_STATUS_ACCEPTED,
    VERSION_STATUS_REJECTED,
    VERSION_STATUS_SUPERSEDED,
    VERSION_STATUS_CANCELLED,
)
from ..models.role import SCOPE_ALL, SCOPE_DEPARTMENT
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.quotation_repo import QuotationRepository
from ..services import quotation_ports
from ..services.sequence_service import SequenceService


class QuotationError(Exception):
    """Base for quotation domain errors."""
    pass


class QuotationValidationError(QuotationError):
    """A field failed validation."""
    pass


class QuotationNotFound(QuotationError):
    """No quotation with that id."""
    pass


class QuotationForbidden(QuotationError):
    """The quotation exists but is outside the caller's data scope."""
    pass


class QuotationConflict(QuotationError):
    """Optimistic-lock or illegal state transition."""
    pass


class QuotationLocked(QuotationError):
    """Attempt to edit a locked quotation."""
    pass


class CostingUnavailable(QuotationError):
    """The referenced Estimate is not available or not calculated."""
    pass


class QuotationService:
    def __init__(
        self,
        quotations: QuotationRepository,
        audit: AuditLogRepository,
        customers=None,
        estimates=None,
        sequence: SequenceService | None = None,
    ) -> None:
        self.quotations = quotations
        self.audit = audit
        self._customers = customers
        self._estimates = estimates
        self.sequence = sequence

    def _customer_display_name(self, customer_id: int | None) -> str | None:
        if customer_id is None or self._customers is None:
            return None
        c = self._customers.get_by_id(customer_id)
        return c.name if c else None

    # --- Pricing calculation engine (Phase 2B) --------------------------------
    @staticmethod
    def calculate_pricing(
        total_cost: float,
        margin_percent: float,
        manual_selling_price: float | None = None,
        manual_unit_price: float | None = None,
        discount_amount: float = 0.0,
        discount_percent: float = 0.0,
        vat_percent: float = 0.0,
        rounding: str = "no_rounding",
        quantity: int = 1,
    ) -> dict[str, Any]:
        """Compute prices based on standard rules (Phase 2B)."""
        quantity = max(1, quantity)
        total_cost = float(total_cost)

        # 1. Base selling price
        if manual_selling_price is not None and manual_selling_price > 0:
            selling_price = float(manual_selling_price)
        elif manual_unit_price is not None and manual_unit_price > 0:
            selling_price = float(manual_unit_price) * quantity
        else:
            m_pct = min(99.99, max(0.0, float(margin_percent)))
            selling_price = total_cost / (1.0 - m_pct / 100.0)

        # 2. Rounding
        if rounding == "round_up_1000":
            selling_price = float(math.ceil(selling_price / 1000.0) * 1000)
        elif rounding == "round_up_5000":
            selling_price = float(math.ceil(selling_price / 5000.0) * 5000)
        elif rounding == "round_up_10000":
            selling_price = float(math.ceil(selling_price / 10000.0) * 10000)

        # 3. actual margin
        if selling_price > 0:
            actual_margin = ((selling_price - total_cost) / selling_price) * 100.0
        else:
            actual_margin = 0.0

        # 4. Discount
        if discount_percent > 0:
            item_discount = selling_price * (float(discount_percent) / 100.0)
        else:
            item_discount = float(discount_amount)
        item_discount = min(selling_price, max(0.0, item_discount))

        # 5. Price after discount
        subtotal = max(0.0, selling_price - item_discount)

        # 6. VAT
        vat_val = max(0.0, float(vat_percent))
        vat_amount = subtotal * (vat_val / 100.0)

        # 7. Final amount
        final_amount = subtotal + vat_amount
        unit_price = selling_price / quantity

        return {
            "selling_price": selling_price,
            "unit_price": unit_price,
            "actual_margin": actual_margin,
            "discount_amount": item_discount,
            "subtotal": subtotal,
            "vat_amount": vat_amount,
            "final_amount": final_amount,
        }

    # --- reads ----------------------------------------------------------------
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

    def get_quotation(self, *, quotation_id: int, scope: str, actor) -> Quote:
        quote = self.quotations.get_by_id(quotation_id)
        if quote is None:
            raise QuotationNotFound("Không tìm thấy báo giá.")
        if not self.quotations.can_access(quote=quote, scope=scope, actor=actor):
            raise QuotationForbidden("Bạn không có quyền xem báo giá này.")
        return quote

    def stats(self) -> dict:
        return self.quotations.stats()

    def estimate_numbers(self, estimate_ids: set[int]) -> dict[int, str]:
        """Map estimate_id → estimate_number cho hiển thị ↳ tham chiếu (bulk, tránh N+1)."""
        ids = {i for i in estimate_ids if i}
        if not ids:
            return {}
        from sqlalchemy import select as _select
        from ..models.estimate import Estimate
        return dict(
            self.quotations.db.execute(
                _select(Estimate.id, Estimate.estimate_number).where(Estimate.id.in_(ids))
            ).all()
        )

    def user_names(self, user_ids: set[int]) -> dict[int, str]:
        """Map user_id → tên hiển thị (người phụ trách trên list)."""
        ids = {i for i in user_ids if i}
        if not ids:
            return {}
        from sqlalchemy import select as _select
        from ..models.user import User as _User
        return dict(
            self.quotations.db.execute(
                _select(_User.id, _User.name).where(_User.id.in_(ids))
            ).all()
        )

    def version_history(self, quote: Quote) -> list[QuoteVersion]:
        return self.quotations.versions_of(quote.quote_number)

    def customer_display(self, quote: Quote):
        if quote.customer_id is None or self._customers is None:
            return None
        return quotation_ports.CustomerRefAdapter(self._customers).get_customer(quote.customer_id)

    # --- writes ---------------------------------------------------------------
    @staticmethod
    def _spec_text(spec: dict | None) -> str | None:
        """Dòng spec đọc được cho item ('21×29,7 cm · 4 màu/2 mặt') thay vì dump JSON."""
        if not spec:
            return None
        parts: list[str] = []
        try:
            w, h = spec.get("finished_width"), spec.get("finished_height")
            if w and h:
                fmt = lambda v: (str(int(float(v))) if float(v).is_integer() else f"{float(v):g}".replace(".", ","))  # noqa: E731
                parts.append(f"{fmt(w)}×{fmt(h)} cm")
        except (TypeError, ValueError):
            pass
        colors = spec.get("colors")
        if colors:
            sides = spec.get("sides")
            parts.append(f"{colors} màu" + (f"/{sides} mặt" if sides else ""))
        return " · ".join(parts) or None

    def create_quotation(
        self,
        *,
        customer_id: int | None,
        estimate_id: int | None,
        selected_option_ids: list[int] | None = None,
        picks: list[dict] | None = None,
        margin_percent: float | None = None,
        valid_until: date | None = None,
        payment_terms: str | None = None,
        delivery_terms: str | None = None,
        delivery_address: str | None = None,
        customer_note: str | None = None,
        internal_note: str | None = None,
        actor,
    ) -> Quote:
        if valid_until and valid_until < date.today():
            raise QuotationValidationError("Hạn hiệu lực không được ở quá khứ.")

        # Chuẩn hóa: đường mới `picks` (đa phiếu) ưu tiên; đường cũ 1 phiếu = 1 pick.
        pick_list: list[tuple[int, list[int] | None]] = []
        if picks:
            pick_list = [(int(p["estimate_id"]), list(p["option_ids"])) for p in picks]
        elif estimate_id:
            pick_list = [(estimate_id, selected_option_ids)]

        # Header giữ phiếu đầu tiên cho tương thích cũ; tham chiếu thật nằm per dòng item.
        header_estimate_id = estimate_id or (pick_list[0][0] if pick_list else None)

        # Generate unique code
        quote_number = self.sequence.generate_code("quotation") if self.sequence else "BG26-0001"
        cust_name = self._customer_display_name(customer_id)

        # Create Header
        quote = Quote(
            quote_number=quote_number,
            customer_id=customer_id,
            customer_name_snapshot=cust_name,
            estimate_id=header_estimate_id,
            salesperson_id=actor.id,
            status=STATUS_DRAFT,
            valid_until=valid_until,
            payment_terms=payment_terms,
            delivery_terms=delivery_terms,
            delivery_address=delivery_address,
            customer_note=customer_note,
            internal_note=internal_note,
            created_by=actor.id,
        )
        self.quotations.create(quote)

        # Create Version 1
        version = QuoteVersion(
            quote_id=quote.id,
            version_number=1,
            status=VERSION_STATUS_DRAFT,
            created_by=actor.id,
        )
        self.quotations.db.add(version)
        self.quotations.db.flush()

        # Build Items from Estimate Options — mỗi pick = 1 phiếu tính giá
        subtotal = 0.0
        discount = 0.0
        vat = 0.0
        final = 0.0
        total_cost = 0.0
        line_no = 1
        strict = picks is not None  # đường mới: phiếu không hợp lệ phải chặn, không im lặng

        for est_id, option_ids in pick_list:
            if not self._estimates:
                break
            estimate = self._estimates.get_by_id(est_id)
            if not estimate or estimate.status != "calculated":
                if strict:
                    raise QuotationValidationError(
                        f"Phiếu tính giá #{est_id} không tồn tại hoặc chưa ở trạng thái 'Đã tính' — không thể đưa vào báo giá."
                    )
                continue

            matched = 0
            for opt in estimate.options:
                if option_ids is None or opt.id in option_ids:
                    m_pct = float(margin_percent) if margin_percent is not None else float(opt.margin_percent or 20.0)
                    pricing = self.calculate_pricing(
                        total_cost=float(opt.total_cost),
                        margin_percent=m_pct,
                        vat_percent=float(opt.vat_percent or 10.0),
                        quantity=opt.quantity,
                    )

                    item = QuoteItem(
                        quote_version_id=version.id,
                        estimate_id=estimate.id,
                        estimate_option_id=opt.id,
                        line_no=line_no,
                        product_type=estimate.product_type,
                        product_name=estimate.product_name,
                        product_spec_text=self._spec_text(estimate.input_spec_json),
                        product_spec_snapshot_json=estimate.input_spec_json,
                        quantity=opt.quantity,
                        unit="cái",
                        total_cost_snapshot=float(opt.total_cost),
                        margin_percent=m_pct,
                        selling_price=pricing["selling_price"],
                        unit_price=pricing["unit_price"],
                        discount_amount=pricing["discount_amount"],
                        vat_percent=opt.vat_percent or 10.0,
                        vat_amount=pricing["vat_amount"],
                        final_amount=pricing["final_amount"],
                    )
                    self.quotations.db.add(item)
                    subtotal += pricing["selling_price"]
                    discount += pricing["discount_amount"]
                    vat += pricing["vat_amount"]
                    final += pricing["final_amount"]
                    total_cost += float(opt.total_cost)
                    line_no += 1
                    matched += 1

            if strict and matched == 0:
                raise QuotationValidationError(
                    f"Phiếu {estimate.estimate_number}: không mức số lượng nào khớp lựa chọn."
                )

            # Lock the estimate to quote
            estimate.status = "converted_to_quote"

        # Update Version Totals
        version.total_cost_snapshot = total_cost
        version.subtotal_amount = subtotal
        version.discount_amount = discount
        version.vat_amount = vat
        version.final_amount = final

        quote.current_version_id = version.id
        self.quotations.update(quote)

        self.audit.create(
            actor_user_id=actor.id,
            action="create_quote",
            target=f"quote:{quote.id}",
            detail=f"Tạo báo giá {quote.quote_number} v1 (KH={customer_id}, {line_no - 1} dòng từ {len(pick_list)} phiếu tính giá)",
        )
        return quote

    def update_quotation(
        self,
        *,
        quotation_id: int,
        scope: str,
        actor,
        customer_id: int | None,
        valid_until: date | None,
        payment_terms: str | None = None,
        delivery_terms: str | None = None,
        delivery_address: str | None = None,
        customer_note: str | None = None,
        internal_note: str | None = None,
        items_payload: list[dict] | None = None,
    ) -> Quote:
        quote = self.get_quotation(quotation_id=quotation_id, scope=scope, actor=actor)
        if quote.status not in (STATUS_DRAFT,):
            raise QuotationLocked("Chỉ chỉnh sửa được báo giá ở trạng thái nháp.")

        if valid_until and valid_until < date.today():
            raise QuotationValidationError("Hạn hiệu lực không được ở quá khứ.")

        # Update Header
        quote.customer_id = customer_id
        quote.customer_name_snapshot = self._customer_display_name(customer_id)
        quote.valid_until = valid_until
        quote.payment_terms = payment_terms
        quote.delivery_terms = delivery_terms
        quote.delivery_address = delivery_address
        quote.customer_note = customer_note
        quote.internal_note = internal_note

        # Find Draft Version
        version = self.quotations.db.get(QuoteVersion, quote.current_version_id)
        if not version or version.status != VERSION_STATUS_DRAFT:
            raise QuotationLocked("Phiên bản hiện tại không ở trạng thái nháp để chỉnh sửa.")

        # Update Items and Recalculate
        subtotal = 0.0
        discount = 0.0
        vat = 0.0
        final = 0.0
        total_cost = 0.0

        if items_payload is not None:
            # We map the submitted array of items to the DB
            item_map = {item.id: item for item in version.items}
            for ip in items_payload:
                item_id = ip.get("id")
                if item_id and item_id in item_map:
                    db_item = item_map[item_id]
                    pricing = self.calculate_pricing(
                        total_cost=float(db_item.total_cost_snapshot),
                        margin_percent=float(ip.get("margin_percent", db_item.margin_percent)),
                        manual_selling_price=ip.get("manual_selling_price"),
                        manual_unit_price=ip.get("manual_unit_price"),
                        discount_amount=float(ip.get("discount_amount", 0.0)),
                        discount_percent=float(ip.get("discount_percent", 0.0)),
                        vat_percent=float(ip.get("vat_percent", db_item.vat_percent)),
                        rounding=ip.get("rounding", "no_rounding"),
                        quantity=db_item.quantity,
                    )
                    db_item.margin_percent = ip.get("margin_percent", db_item.margin_percent)
                    db_item.selling_price = pricing["selling_price"]
                    db_item.unit_price = pricing["unit_price"]
                    db_item.discount_amount = pricing["discount_amount"]
                    db_item.vat_percent = ip.get("vat_percent", db_item.vat_percent)
                    db_item.vat_amount = pricing["vat_amount"]
                    db_item.final_amount = pricing["final_amount"]
                    db_item.note = ip.get("note", db_item.note)

                    subtotal += pricing["selling_price"]
                    discount += pricing["discount_amount"]
                    vat += pricing["vat_amount"]
                    final += pricing["final_amount"]
                    total_cost += float(db_item.total_cost_snapshot)
        else:
            # Just sum up existing items
            for db_item in version.items:
                subtotal += float(db_item.selling_price)
                discount += float(db_item.discount_amount)
                vat += float(db_item.vat_amount)
                final += float(db_item.final_amount)
                total_cost += float(db_item.total_cost_snapshot)

        version.total_cost_snapshot = total_cost
        version.subtotal_amount = subtotal
        version.discount_amount = discount
        version.vat_amount = vat
        version.final_amount = final

        self.quotations.update(quote)

        self.audit.create(
            actor_user_id=actor.id,
            action="update_quote",
            target=f"quote:{quote.id}",
            detail=f"Cập nhật báo giá {quote.quote_number} v{version.version_number}",
        )
        return quote

    # --- Writes: Transition (Phase 2C) ----------------------------------------
    def transition(
        self,
        *,
        quotation_id: int,
        to_status: str,
        scope: str,
        actor,
        cancel_reason: str | None = None,
    ) -> Quote:
        quote = self.get_quotation(quotation_id=quotation_id, scope=scope, actor=actor)
        version = self.quotations.db.get(QuoteVersion, quote.current_version_id)

        if to_status == STATUS_SENT:
            # Gửi khách: khóa phiên bản
            if quote.status != STATUS_DRAFT:
                raise QuotationConflict(f"Không thể chuyển trạng thái {quote.status} -> sent")
            
            # Freeze snapshot copy-on-write
            if version:
                version.status = VERSION_STATUS_SENT
                version.sent_at = datetime.now(timezone.utc)
                # Copy estimate specs & cost breakdown as snapshots
                if quote.estimate_id and self._estimates:
                    est = self._estimates.get_by_id(quote.estimate_id)
                    if est:
                        version.estimate_snapshot_json = est.input_spec_json
                        # Map costing lines
                        lines_data = []
                        for opt in est.options:
                            opt_items = []
                            for line in opt.cost_lines:
                                opt_items.append({
                                    "category": line.category,
                                    "description": line.description,
                                    "total_cost": float(line.total_cost),
                                    "quantity": float(line.quantity),
                                    "unit": line.unit,
                                    "unit_cost": float(line.unit_cost),
                                })
                            lines_data.append({"quantity": opt.quantity, "lines": opt_items})
                        version.internal_cost_snapshot_json = {"options": lines_data}
            
            quote.status = STATUS_SENT
            if quote.valid_until is None:
                quote.valid_until = date.today()

        elif to_status == STATUS_ACCEPTED:
            # Khách duyệt
            if quote.status not in (STATUS_SENT, STATUS_DRAFT):
                raise QuotationConflict(f"Không thể duyệt báo giá đang ở trạng thái {quote.status}")
            if quote.valid_until and quote.valid_until < date.today():
                quote.status = STATUS_EXPIRED
                self.quotations.update(quote)
                raise QuotationConflict("Báo giá đã hết hạn hiệu lực, không thể duyệt.")

            quote.status = STATUS_ACCEPTED
            if version:
                version.status = VERSION_STATUS_ACCEPTED
                version.accepted_at = datetime.now(timezone.utc)

        elif to_status == STATUS_REJECTED:
            # Từ chối
            if quote.status != STATUS_SENT:
                raise QuotationConflict(f"Không thể từ chối báo giá đang ở trạng thái {quote.status}")
            quote.status = STATUS_REJECTED
            if version:
                version.status = VERSION_STATUS_REJECTED
                version.rejected_at = datetime.now(timezone.utc)

        elif to_status == STATUS_CANCELLED:
            # Hủy
            if not cancel_reason or not cancel_reason.strip():
                raise QuotationValidationError("Cần nêu lý do hủy.")
            quote.status = STATUS_CANCELLED
            quote.cancel_reason = cancel_reason
            if version:
                version.status = VERSION_STATUS_CANCELLED

        else:
            raise QuotationValidationError("Trạng thái đích không hợp lệ.")

        self.quotations.update(quote)
        self.audit.create(
            actor_user_id=actor.id,
            action=f"transition_{to_status}",
            target=f"quote:{quote.id}",
            detail=f"{quote.quote_number}: chuyển sang {to_status}" + (f" ({cancel_reason})" if cancel_reason else ""),
        )
        return quote

    # --- Writes: Re-quote / Versioning (Phase 2C) -----------------------------
    def requote(self, *, quotation_id: int, scope: str, actor) -> Quote:
        """Create a new version (re-quote) from an existing quote."""
        quote = self.get_quotation(quotation_id=quotation_id, scope=scope, actor=actor)

        # Re-quote is only valid for sent, approved/accepted, or rejected quotes
        if quote.status not in (STATUS_SENT, STATUS_ACCEPTED, STATUS_REJECTED):
            raise QuotationConflict(f"Không thể re-quote từ trạng thái '{quote.status}'.")

        # Mark current version as superseded
        current_version = self.quotations.db.get(QuoteVersion, quote.current_version_id)
        if current_version:
            current_version.status = VERSION_STATUS_SUPERSEDED

        # Create new version
        new_version = QuoteVersion(
            quote_id=quote.id,
            version_number=current_version.version_number + 1 if current_version else 2,
            status=VERSION_STATUS_DRAFT,
            total_cost_snapshot=current_version.total_cost_snapshot if current_version else 0.0,
            subtotal_amount=current_version.subtotal_amount if current_version else 0.0,
            discount_amount=current_version.discount_amount if current_version else 0.0,
            vat_percent=current_version.vat_percent if current_version else 0.0,
            vat_amount=current_version.vat_amount if current_version else 0.0,
            final_amount=current_version.final_amount if current_version else 0.0,
            estimate_snapshot_json=current_version.estimate_snapshot_json if current_version else None,
            internal_cost_snapshot_json=current_version.internal_cost_snapshot_json if current_version else None,
            created_by=actor.id,
        )
        self.quotations.db.add(new_version)
        self.quotations.db.flush()

        # Duplicate items to new version
        if current_version:
            for item in current_version.items:
                new_item = QuoteItem(
                    quote_version_id=new_version.id,
                    estimate_option_id=item.estimate_option_id,
                    line_no=item.line_no,
                    product_type=item.product_type,
                    product_name=item.product_name,
                    product_spec_text=item.product_spec_text,
                    product_spec_snapshot_json=item.product_spec_snapshot_json,
                    quantity=item.quantity,
                    unit=item.unit,
                    total_cost_snapshot=item.total_cost_snapshot,
                    margin_percent=item.margin_percent,
                    selling_price=item.selling_price,
                    unit_price=item.unit_price,
                    discount_amount=item.discount_amount,
                    vat_percent=item.vat_percent,
                    vat_amount=item.vat_amount,
                    final_amount=item.final_amount,
                    note=item.note,
                )
                self.quotations.db.add(new_item)

        quote.current_version_id = new_version.id
        quote.status = STATUS_DRAFT
        self.quotations.update(quote)

        self.audit.create(
            actor_user_id=actor.id,
            action="change_order",
            target=f"quote:{quote.id}",
            detail=f"{quote.quote_number}: v{current_version.version_number if current_version else 1} -> v{new_version.version_number} (re-quote)",
        )
        return quote
