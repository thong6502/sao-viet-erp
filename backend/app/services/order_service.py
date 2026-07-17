"""Đơn hàng bán — OrderService (nghiệp vụ khâu ④ CHỐT ĐƠN), redesign-don-hang-ban.md P1.

Tầng nghiệp vụ: tạo đơn (từ báo giá đã duyệt / nhập tay) + snapshot dòng copy-on-write + list/get/
update (chỉ khi nháp). Chốt/cọc/duyệt/hủy = P2–P5. Đọc báo giá qua SEAM-04 (QuotationRepository).
"""
from __future__ import annotations

import re
import secrets
from datetime import date, datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from .accounting_service import AccountingService

from ..models.order import (
    ATTACH_KIND_CONSENT,
    APPROVAL_DECISION_APPROVED,
    APPROVAL_DECISION_REJECTED,
    APPROVAL_STATE_APPROVED,
    APPROVAL_STATE_NONE,
    APPROVAL_STATE_PENDING,
    APPROVAL_STATE_REJECTED,
    COST_BASIS_NONE,
    COST_BASIS_QUOTE,
    DEPOSIT_KIND_CK,
    DEPOSIT_KINDS,
    EXC_NO_COST,
    FAULT_KHACH,
    FAULT_XUONG,
    ORDER_KIND_BO_SUNG,
    ORDER_NATURES,
    SOURCE_BAO_GIA,
    SOURCE_NHAP_TAY,
    SOURCE_TYPES,
    STATUS_CANCELLED,
    STATUS_DRAFT,
    STATUS_ORDERED,
    Order,
    OrderApproval,
    OrderAttachment,
    OrderDeposit,
    OrderDepositAttachment,
)
from ..models.quotation import STATUS_ACCEPTED, Quote
from ..models.user import User
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.order_repo import OrderRepository
from ..repositories.quotation_repo import QuotationRepository
from ..schemas.order import (
    EnumOption,
    OrderActivityItem,
    OrderActivityOut,
    AttachmentOut,
    OrderApprovalOut,
    OrderDepositOut,
    OrderDetailOut,
    OrderEnumsOut,
    OrderLineOut,
    OrderListOut,
    OrderReceiptOut,
    OrderRow,
    OrderStatsOut,
)


class OrderError(Exception):
    """Base — router maps to HTTP."""


class OrderNotFound(OrderError):
    pass


class OrderForbidden(OrderError):
    pass


class OrderValidationError(OrderError):
    pass


class OrderConflict(OrderError):
    pass


_STATUS_LABELS = {
    STATUS_DRAFT: "Nháp",
    STATUS_ORDERED: "Đã chốt",
    STATUS_CANCELLED: "Hủy",
}
_SOURCE_LABELS = {SOURCE_BAO_GIA: "Từ báo giá", SOURCE_NHAP_TAY: "Nhập giá tay"}
_NATURE_LABELS = {"hang_hoa": "Hàng hóa", "gia_cong": "Gia công"}


def _i(x) -> int:
    """Numeric/Decimal → int (làm tròn)."""
    return int(round(float(x))) if x is not None else 0


# --- Đính kèm: lưu bytes dưới <backend>/static, phục vụ qua /static -----------
_STATIC_DIR = Path(__file__).resolve().parents[2] / "static"
_MAX_ATTACH_BYTES = 10 * 1024 * 1024
_MAX_ATTACH_PER = 20


def _safe_name(file_name: str | None) -> str:
    name = Path((file_name or "file").replace("\\", "/")).name
    return re.sub(r'[<>:"|?*\x00-\x1f]', "_", name)[:180].strip(" .") or "file"


def _save_static(subdir: str, owner_id: int, file_name, content_type, data: bytes) -> tuple[str, str, int]:
    ct = (content_type or "").lower()
    if not (ct.startswith("image/") or ct == "application/pdf"):
        raise OrderValidationError("Chỉ nhận ảnh (image/*) hoặc PDF")
    if not data:
        raise OrderValidationError("Tệp rỗng")
    if len(data) > _MAX_ATTACH_BYTES:
        raise OrderValidationError("Tệp vượt quá 10 MB")
    safe = _safe_name(file_name)
    token = secrets.token_hex(4)
    dest = _STATIC_DIR / subdir / str(owner_id)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / f"{token}_{safe}").write_bytes(data)
    return f"/static/{subdir}/{owner_id}/{token}_{safe}", safe, len(data)


def _unlink_static(url: str) -> None:
    try:
        (_STATIC_DIR.parent / url.lstrip("/")).unlink(missing_ok=True)
    except OSError:
        pass


class OrderService:
    def __init__(
        self,
        repo: OrderRepository,
        audit: AuditLogRepository,
        quotations: QuotationRepository,
        db: Session,
        accounting: "AccountingService | None" = None,
    ) -> None:
        self.repo = repo
        self.audit = audit
        self.quotations = quotations
        self.db = db
        # SEAM: sinh/đọc phiếu thu 01-TT cho cọc (dùng chung quyển sổ PT với kế toán mua).
        self.accounting = accounting

    # --- helpers ------------------------------------------------------------
    def _user_names(self, ids: list[int]) -> dict[int, str]:
        ids = [i for i in {i for i in ids} if i]
        if not ids:
            return {}
        rows = self.db.query(User.id, User.name).filter(User.id.in_(ids)).all()
        return {uid: name for uid, name in rows}

    def _quote_codes(self, ids: list[int | None]) -> dict[int, str]:
        """Map quotation_id → mã báo giá (quote_number) để hiển thị 'Nguồn'."""
        out: dict[int, str] = {}
        for qid in {i for i in ids if i}:
            q = self.quotations.get_by_id(qid)
            if q is not None:
                out[qid] = q.quote_number
        return out

    def _money(self, order: Order) -> dict:
        """Các số tiền suy diễn của 1 đơn (dùng chung cho row + detail)."""
        total = self.repo.line_total_sum(order.id)
        total_with_vat = self.repo.total_with_vat(order.id)
        order_cost = self.repo.order_cost_sum(order.id)
        # Cọc = Σ phiếu thu 01-TT ĐÃ THU của đơn (quyển sổ PT chung). Fallback order_deposits cũ
        # nếu accounting chưa inject (một số test service dựng OrderService trần).
        if self.accounting is not None:
            received = self.accounting.received_sum_for_order(order.id)
        else:
            received = self.repo.deposit_received_sum(order.id)
        pct = order.deposit_pct
        required = int(round(float(pct) * total_with_vat / 100)) if pct else 0
        # biên: chỉ khi có giá vốn (cost_basis=quote) + có total
        margin = None
        if order.cost_basis == COST_BASIS_QUOTE and order_cost is not None and total:
            margin = round((total - order_cost) * 100 / total)
        return dict(
            total=total,
            total_with_vat=total_with_vat,
            order_cost=order_cost,
            deposit_received=received,
            deposit_required=required,
            deposit_ok=(required == 0) or (received >= required),
            margin_pct=margin,
        )

    def _confirm_gate(self, order: Order) -> tuple[bool, list[str]]:
        """Cổng chốt (§8): trả (đủ điều kiện?, danh sách còn thiếu). Đọc-được cho FE + chặn confirm."""
        blockers: list[str] = []
        if order.status != STATUS_DRAFT:
            return False, ["Đơn không ở trạng thái nháp"]
        m = self._money(order)
        # (a) báo giá còn duyệt & còn hạn (chỉ nguồn báo giá)
        if order.source_type == SOURCE_BAO_GIA:
            quote = self.quotations.get_by_id(order.quotation_id) if order.quotation_id else None
            if quote is None or quote.status not in (STATUS_ACCEPTED, "converted_to_order"):
                blockers.append("Báo giá chưa được khách đồng ý")
            elif quote.valid_until and quote.valid_until < date.today():
                blockers.append("Báo giá đã hết hạn — cần báo giá lại")
        # (b) cọc đủ
        if not m["deposit_ok"]:
            blockers.append(f"Cọc chưa đủ (đã thu {m['deposit_received']:,}/{m['deposit_required']:,})")
        # (c) đủ PO + ngày giao
        if not order.customer_po_no:
            blockers.append("Thiếu số PO khách")
        if not order.delivery_committed_date:
            blockers.append("Thiếu ngày giao cam kết")
        # còn dòng chưa định giá → tổng/cọc bị thiếu, chặn chốt
        if self.repo.unpriced_line_count(order.id) > 0:
            blockers.append("Còn dòng chưa định giá")
        # (d) chứng cứ khách đồng ý — đơn NHẬP TAY cần đính kèm (đơn báo giá dựa vào báo giá accepted)
        if order.source_type == SOURCE_NHAP_TAY and not any(
            a.kind == ATTACH_KIND_CONSENT for a in order.attachments
        ):
            blockers.append("Thiếu chứng cứ khách đồng ý (đính kèm)")
        # (e/f) đặc thù đã duyệt
        if order.needs_approval and order.approval_state != APPROVAL_STATE_APPROVED:
            blockers.append("Đơn đặc thù chưa được duyệt")
        return (len(blockers) == 0), blockers

    def _row(self, order: Order, customer_name: str | None, sale_name: str | None,
             quotation_code: str | None = None) -> OrderRow:
        m = self._money(order)
        return OrderRow(
            id=order.id,
            order_no=order.order_no,
            customer_id=order.customer_id,
            customer_name=customer_name,
            quotation_id=order.quotation_id,
            quotation_code=quotation_code,
            source_type=order.source_type,
            order_kind=order.order_kind,
            order_nature=order.order_nature,
            status=order.status,
            is_rush=order.is_rush,
            approval_state=order.approval_state,
            needs_approval=order.needs_approval,
            cost_basis=order.cost_basis,
            total=m["total"],
            total_with_vat=m["total_with_vat"],
            deposit_pct=order.deposit_pct,
            deposit_required=m["deposit_required"],
            deposit_received=m["deposit_received"],
            deposit_ok=m["deposit_ok"],
            delivery_committed_date=order.delivery_committed_date,
            sale_user_id=order.sale_user_id,
            sale_name=sale_name,
            created_at=order.created_at,
            ordered_at=order.ordered_at,
        )

    def _detail(self, order: Order) -> OrderDetailOut:
        cust_name = None
        if order.customer_id:
            from ..models.customer import Customer

            c = self.db.get(Customer, order.customer_id)
            cust_name = c.name if c else None
        dep_recorders = [d.recorded_by for d in order.deposits if d.recorded_by]
        names = self._user_names([order.sale_user_id, order.cancel_by, *dep_recorders])
        m = self._money(order)
        deposits = []
        for d in order.deposits:
            deposits.append(OrderDepositOut(
                id=d.id, deposit_kind=d.deposit_kind, amount_expected=d.amount_expected,
                amount_received=d.amount_received, reconciled=d.reconciled,
                reconciled_by=d.reconciled_by, reconciled_at=d.reconciled_at, note=d.note,
                received_at=d.received_at, recorded_by=d.recorded_by,
                recorded_by_name=names.get(d.recorded_by), created_at=d.created_at,
                attachments=[
                    AttachmentOut(id=x.id, url=x.file_path, file_name=x.original_name,
                                  content_type=x.content_type, uploaded_at=x.uploaded_at)
                    for x in d.attachments
                ],
            ))
        aps = (
            self.db.query(OrderApproval)
            .filter(OrderApproval.order_id == order.id)
            .order_by(OrderApproval.decided_at.desc())
            .all()
        )
        ap_names = self._user_names([a.decided_by for a in aps if a.decided_by])
        approvals = []
        for a in aps:
            ao = OrderApprovalOut.model_validate(a)
            ao.decided_by_name = ap_names.get(a.decided_by)
            approvals.append(ao)
        consent_atts = [
            AttachmentOut(id=a.id, url=a.file_url, file_name=a.file_name,
                          content_type=a.content_type, uploaded_at=a.uploaded_at)
            for a in order.attachments if a.kind == ATTACH_KIND_CONSENT
        ]
        can_confirm, blockers = self._confirm_gate(order)
        q_code = None
        if order.quotation_id:
            qq = self.quotations.get_by_id(order.quotation_id)
            q_code = qq.quote_number if qq else None
        parent_no = None
        if order.parent_order_id:
            parent = self.repo.get_by_id(order.parent_order_id)
            parent_no = parent.order_no if parent else None
        # Phiếu thu 01-TT của đơn (production, accounting inject). Test service không inject → [].
        receipts = self._order_receipts_out(order.id)
        return OrderDetailOut(
            **self._row(order, cust_name, names.get(order.sale_user_id), q_code).model_dump(),
            quotation_version=order.quotation_version,
            quotation_effective_from=order.quotation_effective_from,
            parent_order_id=order.parent_order_id,
            parent_order_no=parent_no,
            customer_po_no=order.customer_po_no,
            delivery_address=order.delivery_address,
            delivery_contact_name=order.delivery_contact_name,
            delivery_contact_phone=order.delivery_contact_phone,
            delivery_note=order.delivery_note,
            production_note=order.production_note,
            invoice_entity_name=order.invoice_entity_name,
            invoice_entity_tax_code=order.invoice_entity_tax_code,
            vat_pct_estimate=order.vat_pct_estimate,
            lines=[OrderLineOut.model_validate(ln) for ln in order.lines],
            order_cost=m["order_cost"],
            margin_pct=m["margin_pct"],
            cancel_reason=order.cancel_reason,
            cancel_fault=order.cancel_fault,
            cancel_by_name=names.get(order.cancel_by),
            cancel_at=order.cancel_at,
            deposits=deposits,
            receipts=receipts,
            approvals=approvals,
            consent_attachments=consent_atts,
            can_confirm=can_confirm,
            confirm_blockers=blockers,
        )

    def _order_receipts_out(self, order_id: int) -> list["OrderReceiptOut"]:
        """Map phiếu thu 01-TT của đơn → OrderReceiptOut cho FE (rỗng nếu chưa inject accounting)."""
        if self.accounting is None:
            return []
        out: list[OrderReceiptOut] = []
        for r in self.accounting.repo.list_receipts_for_order(order_id):
            out.append(OrderReceiptOut(
                id=r.id, code=r.code, doc_no=r.doc_no, receipt_method=r.receipt_method,
                amount=int(r.amount_vnd), status=r.status, receipt_date=r.receipt_date,
                content=r.content, bank_reference=r.bank_reference,
                payer_name=r.payer_name, debit_account=r.debit_account, credit_account=r.credit_account,
                created_by_name=self._user_names([r.created_by_user_id]).get(r.created_by_user_id),
                attachments=[
                    AttachmentOut(id=a.id, url=a.file_url, file_name=a.file_name,
                                  content_type=a.file_type, uploaded_at=a.uploaded_at)
                    for a in r.attachments
                ],
            ))
        return out

    # --- reads --------------------------------------------------------------
    def list(
        self, *, actor, scope: str, q: str | None, status: str | None,
        order_kind: str | None, sort: str, page: int, size: int,
        approval_state: str | None = None,
    ) -> OrderListOut:
        rows, total, names, _totals = self.repo.list(
            scope=scope, actor=actor, q=q, status=status, order_kind=order_kind,
            approval_state=approval_state, sort=sort, page=page, size=size,
        )
        sale_names = self._user_names([r.sale_user_id for r in rows])
        q_codes = self._quote_codes([r.quotation_id for r in rows])
        items = [
            self._row(o, names.get(o.id), sale_names.get(o.sale_user_id),
                      q_codes.get(o.quotation_id))
            for o in rows
        ]
        return OrderListOut(items=items, total=total, page=page, size=size)

    def stats(self, *, actor, scope: str) -> OrderStatsOut:
        return OrderStatsOut(**self.repo.stats(scope=scope, actor=actor))

    def get(self, *, order_id: int, actor, scope: str) -> OrderDetailOut:
        order = self.repo.get_with_lines(order_id)
        if order is None:
            raise OrderNotFound("Không tìm thấy đơn hàng")
        if not self.repo.can_access(order=order, scope=scope, actor=actor):
            raise OrderNotFound("Không tìm thấy đơn hàng")  # ngoài vùng = 404
        return self._detail(order)

    def activity(self, *, order_id: int, actor, scope: str) -> OrderActivityOut:
        order = self.repo.get_by_id(order_id)
        if order is None or not self.repo.can_access(order=order, scope=scope, actor=actor):
            raise OrderNotFound("Không tìm thấy đơn hàng")
        logs = self.audit.list_by_target(f"order:{order_id}", limit=200)
        names = self._user_names([lg.actor_user_id for lg in logs])
        items = [
            OrderActivityItem(
                at=lg.created_at, actor_id=lg.actor_user_id,
                actor_name=names.get(lg.actor_user_id), action=lg.action, detail=lg.detail,
            )
            for lg in logs
        ]
        return OrderActivityOut(items=items)

    def enums(self) -> OrderEnumsOut:
        return OrderEnumsOut(
            source_types=[EnumOption(value=v, label=_SOURCE_LABELS[v]) for v in SOURCE_TYPES],
            order_natures=[EnumOption(value=v, label=_NATURE_LABELS[v]) for v in ORDER_NATURES],
            statuses=[EnumOption(value=v, label=lb) for v, lb in _STATUS_LABELS.items()],
        )

    # --- writes -------------------------------------------------------------
    def create(self, *, actor, scope: str, payload) -> OrderDetailOut:
        if payload.source_type not in SOURCE_TYPES:
            raise OrderValidationError("Nguồn đơn không hợp lệ")
        if payload.order_kind == ORDER_KIND_BO_SUNG and not payload.parent_order_id:
            raise OrderValidationError("Đơn bổ sung phải trỏ đơn gốc (giữ kẽm)")
        if payload.order_nature not in ORDER_NATURES:
            raise OrderValidationError("Bản chất đơn không hợp lệ")

        if payload.source_type == SOURCE_BAO_GIA:
            order = self._create_from_quotation(actor=actor, payload=payload)
        else:
            order = self._create_manual(actor=actor, payload=payload)

        self.audit.create(
            actor_user_id=actor.id,
            action="create_order",
            target=f"order:{order.id}",
            detail=f"Tạo đơn {order.order_no} ({_SOURCE_LABELS.get(order.source_type, order.source_type)})",
        )
        return self._detail(order)

    def _create_from_quotation(self, *, actor, payload) -> Order:
        if not payload.quotation_id:
            raise OrderValidationError("Thiếu báo giá nguồn")
        quote: Quote | None = self.quotations.get_by_id(payload.quotation_id)
        if quote is None:
            raise OrderValidationError("Không tìm thấy báo giá")
        if quote.status != STATUS_ACCEPTED:
            raise OrderValidationError("Báo giá chưa được khách đồng ý (accepted)")
        if self.repo.active_order_for_quotation(quote.id) is not None:
            raise OrderConflict("Báo giá này đã có đơn (1 báo giá → 1 đơn)")
        version = next((v for v in quote.versions if v.id == quote.current_version_id), None)
        if version is None:
            raise OrderValidationError("Báo giá chưa có phiên bản hiệu lực")

        lines = []
        for it in sorted(version.items, key=lambda x: x.line_no):
            # line_total = NET trước VAT (SAU chiết khấu) = final_amount − vat_amount — khớp đúng số
            # trên báo giá đã ghim. KHÔNG dùng qty×unit_price: `unit_price` của báo giá là giá GỘP
            # (trước CK, = selling_price/qty) → nhân trực tiếp sẽ thổi phồng đúng bằng discount.
            net_line = int(round(float(it.final_amount) - float(it.vat_amount)))
            unit = int(round(net_line / it.quantity)) if it.quantity else net_line
            lines.append(dict(
                description=it.product_name or "",
                qty=it.quantity,
                don_vi_tinh=(getattr(it, "unit", None) or "cái"),   # ĐVT kéo từ dòng báo giá
                unit_price_snapshot=unit,
                line_total=net_line,
                vat_pct_estimate=_i(it.vat_percent),
                cost_snapshot=(_i(it.total_cost_snapshot) if it.total_cost_snapshot else None),
            ))

        order = self.repo.create(
            lines=lines,
            source_type=SOURCE_BAO_GIA,
            customer_id=quote.customer_id,
            quotation_id=quote.id,
            quotation_version=version.version_number,
            quotation_effective_from=(version.created_at.date() if version.created_at else None),
            order_kind=payload.order_kind,
            parent_order_id=payload.parent_order_id,
            order_nature=payload.order_nature,
            is_rush=payload.is_rush,
            sale_user_id=(quote.salesperson_id or actor.id),
            status=STATUS_DRAFT,
            vat_pct_estimate=_i(version.vat_percent),
            deposit_pct=None,   # thỏa thuận lúc chốt đơn — Kế toán đặt trên đơn, báo giá không giữ
            cost_basis=COST_BASIS_QUOTE,
            needs_approval=False,
            approval_state=APPROVAL_STATE_NONE,
            delivery_address=(payload.delivery_address or quote.delivery_address),
            delivery_contact_name=payload.delivery_contact_name,
            delivery_contact_phone=payload.delivery_contact_phone,
            delivery_note=payload.delivery_note,
            production_note=payload.production_note,
            customer_po_no=payload.customer_po_no,
            delivery_committed_date=payload.delivery_committed_date,
            invoice_entity_name=payload.invoice_entity_name,
            invoice_entity_tax_code=payload.invoice_entity_tax_code,
        )
        return order

    def _create_manual(self, *, actor, payload) -> Order:
        if not payload.customer_id:
            raise OrderValidationError("Đơn nhập tay phải chọn khách hàng")
        if not payload.lines:
            raise OrderValidationError("Đơn nhập tay phải có ít nhất 1 dòng")
        lines = []
        for ln in payload.lines:
            unit = ln.unit_price
            lines.append(dict(
                description=ln.description,
                qty=ln.qty,
                don_vi_tinh=(getattr(ln, "don_vi_tinh", None) or "cái"),
                unit_price_snapshot=unit,
                line_total=(ln.qty * unit if unit is not None else None),
                vat_pct_estimate=ln.vat_pct,
                cost_snapshot=None,  # nhập tay: không giá vốn
            ))
        order = self.repo.create(
            lines=lines,
            source_type=SOURCE_NHAP_TAY,
            customer_id=payload.customer_id,
            quotation_id=None,
            quotation_version=None,
            quotation_effective_from=None,
            order_kind=payload.order_kind,
            parent_order_id=payload.parent_order_id,
            order_nature=payload.order_nature,
            is_rush=payload.is_rush,
            sale_user_id=actor.id,
            status=STATUS_DRAFT,
            vat_pct_estimate=payload.vat_pct_estimate,
            deposit_pct=None,
            cost_basis=COST_BASIS_NONE,
            needs_approval=True,   # nhập tay LUÔN cần duyệt (trình duyệt ở P3)
            approval_state=APPROVAL_STATE_NONE,
            delivery_address=payload.delivery_address,
            delivery_contact_name=payload.delivery_contact_name,
            delivery_contact_phone=payload.delivery_contact_phone,
            delivery_note=payload.delivery_note,
            production_note=payload.production_note,
            customer_po_no=payload.customer_po_no,
            delivery_committed_date=payload.delivery_committed_date,
            invoice_entity_name=payload.invoice_entity_name,
            invoice_entity_tax_code=payload.invoice_entity_tax_code,
        )
        return order

    # Nhóm HẬU CẦN — giao nhận, không đụng giá/giá vốn/kẽm → sửa được CẢ SAU KHI CHỐT (có log).
    _LOGISTICS_FIELDS = (
        "customer_po_no", "delivery_committed_date", "delivery_address",
        "delivery_contact_name", "delivery_contact_phone", "delivery_note", "production_note",
    )

    def update(self, *, order_id: int, actor, scope: str, payload, can_set_deposit_pct: bool = False) -> OrderDetailOut:
        order = self.repo.get_with_lines(order_id)
        if order is None or not self.repo.can_access(order=order, scope=scope, actor=actor):
            raise OrderNotFound("Không tìm thấy đơn hàng")
        if order.status == STATUS_CANCELLED:
            raise OrderConflict("Đơn đã hủy — không sửa được")
        after_confirm = order.status == STATUS_ORDERED

        fields: dict = {}
        for f in self._LOGISTICS_FIELDS:
            val = getattr(payload, f)
            if val is not None:
                fields[f] = val
        if payload.is_rush is not None:
            fields["is_rush"] = bool(payload.is_rush)
        # Nhóm THƯƠNG MẠI (bản chất / pháp nhân xuất HĐ / % cọc) — CHỈ sửa khi còn NHÁP.
        commercial = {
            "order_nature": payload.order_nature,
            "invoice_entity_name": payload.invoice_entity_name,
            "invoice_entity_tax_code": payload.invoice_entity_tax_code,
            "deposit_pct": payload.deposit_pct,
        }
        touching_commercial = any(v is not None for v in commercial.values())
        if after_confirm and touching_commercial:
            raise OrderConflict("Đơn đã chốt — chỉ sửa được thông tin giao hàng (ngày giao, địa chỉ, người nhận, lưu ý, gấp).")
        if not after_confirm:
            if payload.order_nature is not None:
                if payload.order_nature not in ORDER_NATURES:
                    raise OrderValidationError("Bản chất đơn không hợp lệ")
                fields["order_nature"] = payload.order_nature
            for f in ("invoice_entity_name", "invoice_entity_tax_code"):
                val = getattr(payload, f)
                if val is not None:
                    fields[f] = val
            # % cọc: khóa khỏi Sale — chỉ Kế toán (`record_deposit`) đặt được.
            if payload.deposit_pct is not None:
                if not can_set_deposit_pct:
                    raise OrderForbidden("Chỉ Kế toán được đặt % cọc của đơn.")
                pct = float(payload.deposit_pct)
                if not 0 <= pct <= 100:
                    raise OrderValidationError("% cọc phải trong khoảng 0–100")
                fields["deposit_pct"] = pct
        if fields:
            self.repo.update(order, **fields)
        self.audit.create(
            actor_user_id=actor.id, action="update_order",
            target=f"order:{order.id}",
            detail=f"{'Sửa sau chốt' if after_confirm else 'Cập nhật'} đơn {order.order_no}: {', '.join(sorted(fields)) or '—'}",
        )
        return self._detail(self.repo.get_with_lines(order_id))

    # --- Cọc (P2) — Kế toán ghi phiếu thu, chỉ khi đơn còn NHÁP -------------
    def _load_draft_for_deposit(self, order_id: int, actor, scope: str) -> Order:
        order = self.repo.get_by_id(order_id)
        if order is None or not self.repo.can_access(order=order, scope=scope, actor=actor):
            raise OrderNotFound("Không tìm thấy đơn hàng")
        if order.status != STATUS_DRAFT:
            raise OrderConflict("Đơn đã chốt/hủy — không ghi/sửa cọc")
        return order

    def _apply_deposit_fields(self, dep: OrderDeposit, payload, actor) -> None:
        if payload.deposit_kind not in DEPOSIT_KINDS:
            raise OrderValidationError("Hình thức cọc không hợp lệ")
        dep.deposit_kind = payload.deposit_kind
        dep.amount_expected = payload.amount_expected
        dep.amount_received = payload.amount_received
        dep.note = payload.note
        dep.received_at = payload.received_at
        # đối chiếu sao kê CHỈ có nghĩa với CK
        rec = bool(payload.reconciled) and payload.deposit_kind == DEPOSIT_KIND_CK
        dep.reconciled = rec
        dep.reconciled_by = actor.id if rec else None
        dep.reconciled_at = datetime.now(timezone.utc) if rec else None

    def add_deposit(self, *, order_id: int, actor, scope: str, payload) -> OrderDetailOut:
        order = self._load_draft_for_deposit(order_id, actor, scope)
        dep = OrderDeposit(order_id=order.id, recorded_by=actor.id)
        self._apply_deposit_fields(dep, payload, actor)
        self.db.add(dep)
        self.db.commit()
        self.audit.create(
            actor_user_id=actor.id, action="record_deposit", target=f"order:{order.id}",
            detail=f"Ghi cọc {payload.amount_received:,}đ ({payload.deposit_kind}) — đơn {order.order_no}",
        )
        return self._detail(self.repo.get_with_lines(order_id))

    def update_deposit(self, *, order_id: int, deposit_id: int, actor, scope: str, payload) -> OrderDetailOut:
        order = self._load_draft_for_deposit(order_id, actor, scope)
        dep = self.db.get(OrderDeposit, deposit_id)
        if dep is None or dep.order_id != order.id:
            raise OrderNotFound("Không tìm thấy phiếu thu")
        self._apply_deposit_fields(dep, payload, actor)
        self.db.commit()
        self.audit.create(
            actor_user_id=actor.id, action="update_deposit", target=f"order:{order.id}",
            detail=f"Sửa phiếu thu #{deposit_id} — đơn {order.order_no}",
        )
        return self._detail(self.repo.get_with_lines(order_id))

    def delete_deposit(self, *, order_id: int, deposit_id: int, actor, scope: str) -> OrderDetailOut:
        order = self._load_draft_for_deposit(order_id, actor, scope)
        dep = self.db.get(OrderDeposit, deposit_id)
        if dep is None or dep.order_id != order.id:
            raise OrderNotFound("Không tìm thấy phiếu thu")
        self.db.delete(dep)
        self.db.commit()
        self.audit.create(
            actor_user_id=actor.id, action="delete_deposit", target=f"order:{order.id}",
            detail=f"Xóa phiếu thu #{deposit_id} — đơn {order.order_no}",
        )
        return self._detail(self.repo.get_with_lines(order_id))

    # --- Cọc = Phiếu thu 01-TT (production) — dùng chung quyển sổ PT kế toán ---
    # Đường mới thay order_deposits: nút "Tạo phiếu thu" trên đơn → sinh PT thật (01-TT), đơn đọc
    # ngược Σ phiếu thu đã thu. order_deposits ở trên GIỮ cho tương thích + test service không inject
    # accounting; production luôn có accounting → đi đường này.
    def _require_accounting(self):
        if self.accounting is None:
            raise OrderValidationError("Chức năng phiếu thu chưa sẵn sàng.")
        return self.accounting

    def create_deposit_receipt(self, *, order_id: int, actor, scope: str, payload) -> OrderDetailOut:
        acc = self._require_accounting()
        order = self._load_draft_for_deposit(order_id, actor, scope)
        cust_name = None
        if order.customer_id:
            from ..models.customer import Customer

            c = self.db.get(Customer, order.customer_id)
            cust_name = c.name if c else None
        acc.create_order_receipt(
            order_id=order.id, order_no=order.order_no, customer_name=cust_name, actor=actor,
            receipt_method=payload.receipt_method, amount=payload.amount,
            receipt_date=payload.receipt_date, content=payload.content,
            bank_reference=payload.bank_reference, company_bank_account_id=payload.company_bank_account_id,
            note=payload.note, mark_received=payload.mark_received,
        )
        return self._detail(self.repo.get_with_lines(order_id))

    def cancel_deposit_receipt(self, *, order_id: int, receipt_id: int, actor, scope: str, reason: str) -> OrderDetailOut:
        acc = self._require_accounting()
        order = self._load_draft_for_deposit(order_id, actor, scope)
        self._assert_receipt_of_order(acc, order.id, receipt_id)
        acc.cancel_order_receipt(receipt_id, actor=actor, reason=reason)
        return self._detail(self.repo.get_with_lines(order_id))

    def add_receipt_attachment(self, *, order_id, receipt_id, actor, scope, file_name, content_type, data) -> OrderDetailOut:
        acc = self._require_accounting()
        order = self._load_draft_for_deposit(order_id, actor, scope)
        self._assert_receipt_of_order(acc, order.id, receipt_id)
        acc.add_receipt_attachment(receipt_id, actor=actor, file_name=file_name, content_type=content_type, data=data)
        return self._detail(self.repo.get_with_lines(order_id))

    def delete_receipt_attachment(self, *, order_id, receipt_id, attachment_id, actor, scope) -> OrderDetailOut:
        acc = self._require_accounting()
        order = self._load_draft_for_deposit(order_id, actor, scope)
        self._assert_receipt_of_order(acc, order.id, receipt_id)
        acc.delete_receipt_attachment(receipt_id, attachment_id, actor=actor)
        return self._detail(self.repo.get_with_lines(order_id))

    @staticmethod
    def _assert_receipt_of_order(acc, order_id: int, receipt_id: int) -> None:
        row = acc.repo.get_receipt(receipt_id)
        if row is None or row.order_id != order_id:
            raise OrderNotFound("Không tìm thấy phiếu thu của đơn này")

    # --- Duyệt đơn đặc thù (P3) — luật trình-duyệt --------------------------
    def _load_approvable(self, order_id: int, actor, scope: str) -> Order:
        order = self.repo.get_by_id(order_id)
        if order is None or not self.repo.can_access(order=order, scope=scope, actor=actor):
            raise OrderNotFound("Không tìm thấy đơn hàng")
        if order.status != STATUS_DRAFT:
            raise OrderConflict("Đơn đã chốt/hủy")
        if not order.needs_approval:
            raise OrderValidationError("Đơn này không cần duyệt")
        return order

    def submit_for_approval(self, *, order_id: int, actor, scope: str) -> OrderDetailOut:
        order = self._load_approvable(order_id, actor, scope)
        if order.approval_state == APPROVAL_STATE_APPROVED:
            raise OrderConflict("Đơn đã được duyệt")
        order.approval_state = APPROVAL_STATE_PENDING
        self.db.commit()
        self.audit.create(actor_user_id=actor.id, action="submit_order_approval",
            target=f"order:{order.id}", detail=f"Trình duyệt đơn {order.order_no}")
        return self._detail(self.repo.get_with_lines(order_id))

    def _record_decision(self, order: Order, actor, decision: str, note: str | None) -> None:
        m = self._money(order)
        triggers = [EXC_NO_COST] if order.cost_basis == COST_BASIS_NONE else None
        self.db.add(OrderApproval(
            order_id=order.id, decision=decision, note=note, decided_by=actor.id,
            triggers_json=triggers, order_total=m["total_with_vat"],
            order_subtotal=(m["total"] or 0), order_cost=m["order_cost"],
            margin_pct_snapshot=m["margin_pct"],
        ))

    def approve(self, *, order_id: int, actor, scope: str, note: str | None) -> OrderDetailOut:
        order = self._load_approvable(order_id, actor, scope)
        if not note or not note.strip():
            raise OrderValidationError("Duyệt phải nêu ghi chú / lý do")
        self._record_decision(order, actor, APPROVAL_DECISION_APPROVED, note)
        order.approval_state = APPROVAL_STATE_APPROVED
        self.db.commit()
        self.audit.create(actor_user_id=actor.id, action="approve_order",
            target=f"order:{order.id}",
            detail=f"Duyệt đơn {order.order_no}" + (f" — {note}" if note else ""))
        return self._detail(self.repo.get_with_lines(order_id))

    def reject(self, *, order_id: int, actor, scope: str, note: str | None) -> OrderDetailOut:
        order = self._load_approvable(order_id, actor, scope)
        if not note or not note.strip():
            raise OrderValidationError("Từ chối phải nêu lý do")
        self._record_decision(order, actor, APPROVAL_DECISION_REJECTED, note)
        order.approval_state = APPROVAL_STATE_REJECTED
        self.db.commit()
        self.audit.create(actor_user_id=actor.id, action="reject_order",
            target=f"order:{order.id}", detail=f"Từ chối đơn {order.order_no} — {note}")
        return self._detail(self.repo.get_with_lines(order_id))

    # --- Chốt đơn (P4) — transaction compare-and-set + khóa báo giá ---------
    def confirm(self, *, order_id: int, actor, scope: str) -> OrderDetailOut:
        order = self.repo.get_by_id(order_id)
        if order is None or not self.repo.can_access(order=order, scope=scope, actor=actor):
            raise OrderNotFound("Không tìm thấy đơn hàng")
        ok, blockers = self._confirm_gate(order)
        if not ok:
            raise OrderValidationError("Chưa đủ điều kiện chốt: " + "; ".join(blockers))
        now = datetime.now(timezone.utc)
        # compare-and-set: chỉ chốt nếu vẫn đang draft (chống chốt trùng / hủy song song)
        updated = (
            self.db.query(Order)
            .filter(Order.id == order.id, Order.status == STATUS_DRAFT)
            .update(
                {"status": STATUS_ORDERED, "ordered_at": now, "ordered_by": actor.id},
                synchronize_session=False,
            )
        )
        if updated != 1:
            self.db.rollback()
            raise OrderConflict("Đơn vừa được người khác chốt hoặc hủy")
        # khóa báo giá gốc (1 báo giá → 1 đơn) — cùng transaction với chốt
        if order.source_type == SOURCE_BAO_GIA and order.quotation_id:
            quote = self.quotations.get_by_id(order.quotation_id)
            if quote is not None and quote.status != "converted_to_order":
                quote.status = "converted_to_order"
        self.db.commit()
        self.audit.create(actor_user_id=actor.id, action="confirm_order",
            target=f"order:{order.id}", detail=f"Chốt đơn {order.order_no}")
        # push Sản xuất (SEAM-01) — Sản xuất chưa build → ghi vết idempotent theo order_id
        self.audit.create(actor_user_id=actor.id, action="push_production",
            target=f"order:{order.id}", detail=f"Đẩy đơn {order.order_no} xuống Sản xuất (seam)")
        return self._detail(self.repo.get_with_lines(order_id))

    # --- Hủy đơn (P5) — nháp (tự do) vs đã chốt (TP/GĐ + lỗi + seam) --------
    def cancel(self, *, order_id: int, actor, scope: str, reason: str, fault: str | None,
               can_cancel_ordered: bool) -> OrderDetailOut:
        order = self.repo.get_by_id(order_id)
        if order is None or not self.repo.can_access(order=order, scope=scope, actor=actor):
            raise OrderNotFound("Không tìm thấy đơn hàng")
        if order.status == STATUS_CANCELLED:
            raise OrderConflict("Đơn đã hủy")
        if not reason or not reason.strip():
            raise OrderValidationError("Hủy đơn phải nêu lý do")
        if order.status == STATUS_ORDERED:
            # Hủy sau chốt: chỉ TP/GĐ (approve_exception); bắt lỗi tại ai. Cọc KHÔNG xóa (giữ
            # nguyên order_deposits → "còn cọc chưa quyết toán" suy từ data); báo giá KHÔNG mở lại
            # (giữ converted_to_order). Hoàn/giữ cọc bao nhiêu = đàm phán NGOÀI hệ thống.
            if not can_cancel_ordered:
                raise OrderForbidden("Hủy đơn đã chốt cần quyền duyệt (TP KD / Giám đốc)")
            if fault not in (FAULT_KHACH, FAULT_XUONG):
                raise OrderValidationError("Hủy đơn đã chốt phải nêu lỗi tại ai (khách / xưởng)")
            order.cancel_fault = fault
        order.status = STATUS_CANCELLED
        order.cancel_reason = reason
        order.cancel_by = actor.id
        order.cancel_at = datetime.now(timezone.utc)
        self.db.commit()
        self.audit.create(actor_user_id=actor.id, action="cancel_order", target=f"order:{order.id}",
            detail=f"Hủy đơn {order.order_no}" + (f" (lỗi {fault})" if fault else "") + f" — {reason}")
        return self._detail(self.repo.get_with_lines(order_id))

    # --- Đính kèm — chứng cứ khách đồng ý + minh chứng cọc (chỉ khi nháp) ----
    def _load_editable_draft(self, order_id: int, actor, scope: str) -> Order:
        order = self.repo.get_by_id(order_id)
        if order is None or not self.repo.can_access(order=order, scope=scope, actor=actor):
            raise OrderNotFound("Không tìm thấy đơn hàng")
        if order.status != STATUS_DRAFT:
            raise OrderConflict("Đơn đã chốt/hủy — không sửa đính kèm")
        return order

    def add_consent_attachment(self, *, order_id, actor, scope, file_name, content_type, data) -> OrderDetailOut:
        order = self._load_editable_draft(order_id, actor, scope)
        if sum(1 for a in order.attachments if a.kind == ATTACH_KIND_CONSENT) >= _MAX_ATTACH_PER:
            raise OrderValidationError(f"Tối đa {_MAX_ATTACH_PER} đính kèm")
        url, safe, size = _save_static("don-hang", order.id, file_name, content_type, data)
        self.db.add(OrderAttachment(order_id=order.id, kind=ATTACH_KIND_CONSENT, file_url=url,
            file_name=safe, content_type=content_type, size_bytes=size, uploaded_by=actor.id))
        self.db.commit()
        self.audit.create(actor_user_id=actor.id, action="upload_consent",
            target=f"order:{order.id}", detail=f"Chứng cứ đồng ý + {safe}")
        return self._detail(self.repo.get_with_lines(order_id))

    def delete_consent_attachment(self, *, order_id, attachment_id, actor, scope) -> OrderDetailOut:
        order = self._load_editable_draft(order_id, actor, scope)
        att = self.db.get(OrderAttachment, attachment_id)
        if att is None or att.order_id != order.id:
            raise OrderNotFound("Không tìm thấy đính kèm")
        _unlink_static(att.file_url)
        self.db.delete(att)
        self.db.commit()
        self.audit.create(actor_user_id=actor.id, action="delete_consent",
            target=f"order:{order.id}", detail=f"Xóa chứng cứ #{attachment_id}")
        return self._detail(self.repo.get_with_lines(order_id))

    def add_deposit_attachment(self, *, order_id, deposit_id, actor, scope, file_name, content_type, data) -> OrderDetailOut:
        order = self._load_editable_draft(order_id, actor, scope)
        dep = self.db.get(OrderDeposit, deposit_id)
        if dep is None or dep.order_id != order.id:
            raise OrderNotFound("Không tìm thấy phiếu thu")
        if len(dep.attachments) >= _MAX_ATTACH_PER:
            raise OrderValidationError(f"Tối đa {_MAX_ATTACH_PER} minh chứng")
        url, safe, size = _save_static("don-hang-coc", dep.id, file_name, content_type, data)
        self.db.add(OrderDepositAttachment(deposit_id=dep.id, file_path=url, original_name=safe,
            content_type=content_type, size_bytes=size, uploaded_by=actor.id))
        self.db.commit()
        self.audit.create(actor_user_id=actor.id, action="upload_deposit_proof",
            target=f"order:{order.id}", detail=f"Minh chứng cọc + {safe}")
        return self._detail(self.repo.get_with_lines(order_id))

    def delete_deposit_attachment(self, *, order_id, deposit_id, attachment_id, actor, scope) -> OrderDetailOut:
        order = self._load_editable_draft(order_id, actor, scope)
        att = self.db.get(OrderDepositAttachment, attachment_id)
        if att is None or att.deposit_id != deposit_id:
            raise OrderNotFound("Không tìm thấy minh chứng")
        _unlink_static(att.file_path)
        self.db.delete(att)
        self.db.commit()
        self.audit.create(actor_user_id=actor.id, action="delete_deposit_proof",
            target=f"order:{order.id}", detail=f"Xóa minh chứng #{attachment_id}")
        return self._detail(self.repo.get_with_lines(order_id))
