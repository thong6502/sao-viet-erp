"""Đơn hàng bán — OrderService (nghiệp vụ khâu ④ CHỐT ĐƠN), redesign-don-hang-ban.md P1.

Tầng nghiệp vụ: tạo đơn (từ báo giá đã duyệt / nhập tay) + snapshot dòng copy-on-write + list/get/
update (chỉ khi nháp). Chốt/cọc/duyệt/hủy = P2–P5. Đọc báo giá qua SEAM-04 (QuotationRepository).
"""
from __future__ import annotations

import re
import secrets
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

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
)
from ..models.quotation import STATUS_ACCEPTED, Quote
from ..models.user import User
from ..repositories.accounting_repo import AccountingRepository
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.order_repo import OrderRepository
from ..repositories.quotation_repo import QuotationRepository
from ..schemas.order import (
    EnumOption,
    OrderActivityItem,
    OrderActivityOut,
    AttachmentOut,
    OrderApprovalOut,
    OrderDepositReceiptOut,
    OrderDetailOut,
    OrderEnumsOut,
    OrderLineOut,
    OrderListOut,
    OrderRow,
    OrderStatsOut,
)
from .accounting_service import AccountingService, AccountingValidationError


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
        accounting_repo: AccountingRepository,
        accounting: AccountingService,
    ) -> None:
        self.repo = repo
        self.audit = audit
        self.quotations = quotations
        self.db = db
        # V5: cọc = PaymentReceipt (Kế toán). accounting_repo → đọc Σ received + list phiếu; accounting
        # (service) → LẬP phiếu thu cọc. Cùng Session request-scoped nên chung transaction.
        self.accounting_repo = accounting_repo
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
        # V5: cọc đọc từ phiếu thu THẬT (Kế toán) — Σ PaymentReceipt(order, source=đơn, received).
        received = self.accounting_repo.received_deposit_sum(order.id)
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
        names = self._user_names([order.sale_user_id])
        m = self._money(order)
        # V5: danh sách phiếu thu cọc (PaymentReceipt nguồn đơn) — thay bản ghi OrderDeposit cũ.
        deposits = [
            OrderDepositReceiptOut(
                id=r.id, code=r.code, doc_no=r.doc_no, amount=int(r.amount),
                receipt_method=r.receipt_method, status=r.status,
                receipt_date=r.receipt_date, created_at=r.created_at,
            )
            for r in self.accounting_repo.list_order_receipts(order.id)
        ]
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
        quote_expired = False
        if order.quotation_id:
            qq = self.quotations.get_by_id(order.quotation_id)
            q_code = qq.quote_number if qq else None
            # Việc 4: cờ có cấu trúc để FE bật nút "Gia hạn báo giá" — khớp ĐÚNG blocker hết-hạn ở
            # cổng chốt (đơn nháp nguồn báo giá + báo giá accepted đã quá hạn), khỏi dò chuỗi.
            quote_expired = bool(
                order.status == STATUS_DRAFT
                and order.source_type == SOURCE_BAO_GIA
                and qq is not None
                and qq.status in (STATUS_ACCEPTED, "converted_to_order")
                and qq.valid_until and qq.valid_until < date.today()
            )
        return OrderDetailOut(
            **self._row(order, cust_name, names.get(order.sale_user_id), q_code).model_dump(),
            quotation_version=order.quotation_version,
            quotation_effective_from=order.quotation_effective_from,
            parent_order_id=order.parent_order_id,
            customer_po_no=order.customer_po_no,
            delivery_address=order.delivery_address,
            invoice_entity_name=order.invoice_entity_name,
            invoice_entity_tax_code=order.invoice_entity_tax_code,
            vat_pct_estimate=order.vat_pct_estimate,
            lines=[OrderLineOut.model_validate(ln) for ln in order.lines],
            order_cost=m["order_cost"],
            margin_pct=m["margin_pct"],
            cancel_reason=order.cancel_reason,
            cancel_fault=order.cancel_fault,
            deposits=deposits,
            approvals=approvals,
            consent_attachments=consent_atts,
            can_confirm=can_confirm,
            confirm_blockers=blockers,
            quote_expired=quote_expired,
        )

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
        from ..models.order import STATUS_DRAFT, STATUS_ORDERED

        counts = self.repo.stats(scope=scope, actor=actor)
        # KPI tiền: dùng CÙNG công thức _money (required = round(pct·twv/100), received từ phiếu thu)
        # nên số KPI = tổng đúng số hiện trên từng dòng.
        rows = self.repo.value_rows(scope=scope, actor=actor, statuses=(STATUS_DRAFT, STATUS_ORDERED))
        received = self.accounting_repo.received_deposit_sums(list(rows.keys()))
        awaiting = shortfall = ordered_value = 0
        for oid, r in rows.items():
            twv = r["total_with_vat"]
            pct = r["deposit_pct"]
            required = int(round(float(pct) * twv / 100)) if pct else 0
            if r["status"] == STATUS_ORDERED:
                ordered_value += twv
            elif r["status"] == STATUS_DRAFT and required > 0 and received.get(oid, 0) < required:
                awaiting += 1
                shortfall += required - received.get(oid, 0)
        return OrderStatsOut(
            **counts,
            awaiting_deposit=awaiting,
            deposit_shortfall=shortfall,
            ordered_value=ordered_value,
        )

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
        if payload.deposit_pct is not None and not 0 <= payload.deposit_pct <= 100:
            raise OrderValidationError("% cọc phải trong khoảng 0–100")

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
                unit_price_snapshot=unit,
                line_total=net_line,
                vat_pct_estimate=_i(it.vat_percent),
                cost_snapshot=(_i(it.total_cost_snapshot) if it.total_cost_snapshot else None),
                phieu_thanh_phan_id=it.phieu_thanh_phan_id,   # pin truy vết ấn phẩm (soft) từ dòng báo giá
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
            sale_user_id=(quote.salesperson_id or actor.id),
            status=STATUS_DRAFT,
            vat_pct_estimate=_i(version.vat_percent),
            # % cọc nhập trên đơn ưu tiên; chưa nhập thì ghim từ báo giá.
            deposit_pct=(payload.deposit_pct if payload.deposit_pct is not None else quote.deposit_pct),
            cost_basis=COST_BASIS_QUOTE,
            needs_approval=False,
            approval_state=APPROVAL_STATE_NONE,
            delivery_address=(payload.delivery_address or quote.delivery_address),
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
            sale_user_id=actor.id,
            status=STATUS_DRAFT,
            vat_pct_estimate=payload.vat_pct_estimate,
            deposit_pct=payload.deposit_pct,   # sale nhập trên đơn (nhập tay không có báo giá để ghim)
            cost_basis=COST_BASIS_NONE,
            needs_approval=True,   # nhập tay LUÔN cần duyệt (trình duyệt ở P3)
            approval_state=APPROVAL_STATE_NONE,
            delivery_address=payload.delivery_address,
            customer_po_no=payload.customer_po_no,
            delivery_committed_date=payload.delivery_committed_date,
            invoice_entity_name=payload.invoice_entity_name,
            invoice_entity_tax_code=payload.invoice_entity_tax_code,
        )
        return order

    def update(self, *, order_id: int, actor, scope: str, payload) -> OrderDetailOut:
        order = self.repo.get_with_lines(order_id)
        if order is None or not self.repo.can_access(order=order, scope=scope, actor=actor):
            raise OrderNotFound("Không tìm thấy đơn hàng")
        if order.status != STATUS_DRAFT:
            raise OrderConflict("Đơn đã chốt/hủy — không sửa được")

        fields: dict = {}
        for f in (
            "customer_po_no", "delivery_committed_date", "delivery_address",
            "invoice_entity_name", "invoice_entity_tax_code",
        ):
            val = getattr(payload, f)
            if val is not None:
                fields[f] = val
        if payload.order_nature is not None:
            if payload.order_nature not in ORDER_NATURES:
                raise OrderValidationError("Bản chất đơn không hợp lệ")
            fields["order_nature"] = payload.order_nature
        if payload.deposit_pct is not None:
            if not 0 <= payload.deposit_pct <= 100:
                raise OrderValidationError("% cọc phải trong khoảng 0–100")
            fields["deposit_pct"] = payload.deposit_pct
        if fields:
            self.repo.update(order, **fields)
        self.audit.create(
            actor_user_id=actor.id, action="update_order",
            target=f"order:{order.id}", detail=f"Cập nhật đơn {order.order_no}",
        )
        return self._detail(self.repo.get_with_lines(order_id))

    def extend_source_quote(self, *, order_id: int, actor, scope: str) -> OrderDetailOut:
        """Việc 4 — Gia hạn báo giá NGUỒN ngay từ đơn (gỡ blocker 'báo giá hết hạn' ở cổng chốt).
        Gộp vào luồng đơn, KHÔNG nhảy màn: đặt lại valid_until = hôm nay + 30 ngày (đúng quy ước
        bản mới ở quotation_service:1146). Quyền = `update` (router đã chặn — Sale + TP/GĐ), scope
        kẹp qua can_access. Chỉ áp cho đơn NHÁP nguồn báo giá + báo giá accepted đã hết hạn; ghi vết
        vào audit để hiện trên timeline báo giá."""
        order = self.repo.get_by_id(order_id)
        if order is None or not self.repo.can_access(order=order, scope=scope, actor=actor):
            raise OrderNotFound("Không tìm thấy đơn hàng")
        if order.status != STATUS_DRAFT:
            raise OrderConflict("Đơn đã chốt/hủy — không cần gia hạn báo giá")
        if order.source_type != SOURCE_BAO_GIA or not order.quotation_id:
            raise OrderValidationError("Đơn nhập giá tay không gắn báo giá để gia hạn")
        quote = self.quotations.get_by_id(order.quotation_id)
        if quote is None or quote.status not in (STATUS_ACCEPTED, "converted_to_order"):
            raise OrderValidationError("Báo giá nguồn không ở trạng thái gia hạn được")
        if not (quote.valid_until and quote.valid_until < date.today()):
            raise OrderValidationError("Báo giá còn hạn — không cần gia hạn")
        new_until = date.today() + timedelta(days=30)
        quote.valid_until = new_until
        self.quotations.update(quote)
        self.audit.create(
            actor_user_id=actor.id, action="extend_quote_validity",
            target=f"quote:{quote.id}",
            detail=f"Gia hạn báo giá {quote.quote_number} tới {new_until.isoformat()} "
                   f"(từ đơn {order.order_no})",
        )
        return self._detail(self.repo.get_with_lines(order_id))

    def notify_summary(self, *, actor, scope: str, can_approve: bool,
                       can_record_deposit: bool, can_manage_status: bool) -> dict:
        """Số nuôi badge/toast real-time — 'việc chờ TÔI xử lý' theo vai (đơn còn NHÁP trong phạm vi):
        TP/GĐ = đơn chờ duyệt; Kế toán = đơn chờ ghi cọc; Sale = đơn đủ điều kiện chờ chốt. Tự giảm
        khi người dùng thao tác (không cần cờ 'seen'). Đếm trên tập nháp nhỏ nên rẻ."""
        approval_pending = deposit_pending = ready_to_confirm = 0
        for o in self.repo.drafts_in_scope(scope=scope, actor=actor):
            m = self._money(o)
            if can_approve and o.approval_state == APPROVAL_STATE_PENDING:
                approval_pending += 1
            if can_record_deposit and (o.deposit_pct or 0) > 0 and not m["deposit_ok"]:
                deposit_pending += 1
            if can_manage_status and m["deposit_ok"] and (
                not o.needs_approval or o.approval_state == APPROVAL_STATE_APPROVED
            ):
                ready_to_confirm += 1
        return {
            "action_count": approval_pending + deposit_pending + ready_to_confirm,
            "approval_pending": approval_pending,
            "deposit_pending": deposit_pending,
            "ready_to_confirm": ready_to_confirm,
        }

    # --- Cọc (V5) — Kế toán LẬP PHIẾU THU THẬT từ đơn, chỉ khi đơn còn NHÁP -
    def add_deposit_receipt(self, *, order_id: int, actor, scope: str, payload) -> OrderDetailOut:
        """Kế toán bấm trên drawer đơn → tạo PaymentReceipt(source='don_hang_ban', received) gắn đơn.
        Chỉ ghi khi đơn còn NHÁP (cọc là cổng TRƯỚC chốt). Quyền gate ở router = record_deposit."""
        order = self.repo.get_by_id(order_id)
        if order is None or not self.repo.can_access(order=order, scope=scope, actor=actor):
            raise OrderNotFound("Không tìm thấy đơn hàng")
        if order.status != STATUS_DRAFT:
            raise OrderConflict("Đơn đã chốt/hủy — không ghi cọc")
        customer_name = None
        if order.customer_id:
            from ..models.customer import Customer

            c = self.db.get(Customer, order.customer_id)
            customer_name = c.name if c else None
        try:
            self.accounting.create_order_deposit_receipt(
                order=order, customer_name=customer_name, actor=actor,
                receipt_method=payload.receipt_method, amount=payload.amount,
                receipt_date=payload.receipt_date, note=payload.note,
                company_bank_account_id=payload.company_bank_account_id,
            )
        except AccountingValidationError as exc:
            raise OrderValidationError(str(exc)) from exc
        self.audit.create(
            actor_user_id=actor.id, action="record_deposit", target=f"order:{order.id}",
            detail=f"Thu cọc {int(payload.amount):,}đ ({payload.receipt_method}) — đơn {order.order_no}",
        )
        return self._detail(self.repo.get_with_lines(order_id))

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

    # V5: minh chứng đã thu cọc KHÔNG còn đính ở đơn — dùng PaymentReceiptAttachment (màn Phiếu thu
    # Kế toán, endpoint /api/accounting/payment-receipts/{id}/attachments).
