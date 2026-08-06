"""Đơn hàng bán — OrderService (nghiệp vụ khâu ④ CHỐT ĐƠN), redesign-don-hang-ban.md P1.

Tầng nghiệp vụ: tạo đơn TỪ BÁO GIÁ khách đã đồng ý + snapshot dòng copy-on-write + list/get/
update (chỉ khi nháp). Chốt/cọc/hủy = P2–P5. Đọc báo giá qua SEAM-04 (QuotationRepository).

ĐÃ GỠ: đường tạo đơn NHẬP TAY và toàn bộ luồng DUYỆT đơn đặc thù. `needs_approval` chỉ từng được
bật bởi đúng đường nhập tay, nên bỏ nhập tay là luồng duyệt hết nguồn dữ liệu. Cột DB
(`source_type`, `order_nature`, `invoice_entity_*`, `needs_approval`, `approval_state`) và bảng
`order_approvals` GIỮ NGUYÊN — dự án không có Alembic, và đơn `nhap_tay` cũ vẫn phải đọc được.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models.order import (
    ATTACH_KIND_CONSENT,
    APPROVAL_STATE_NONE,
    COST_BASIS_QUOTE,
    FAULT_KHACH,
    FAULT_XUONG,
    ORDER_KIND_BO_SUNG,
    SOURCE_BAO_GIA,
    STATUS_CANCELLED,
    STATUS_DRAFT,
    STATUS_ORDERED,
    Order,
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
    OrderDepositReceiptOut,
    OrderDetailOut,
    OrderEnumsOut,
    OrderLineOut,
    OrderListOut,
    OrderRow,
    OrderStatsOut,
)
from ..storage import get_storage, key_from_url, make_key, url_from_key
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
# Đơn mới chỉ có MỘT nguồn, nhưng nhãn giữ cả `nhap_tay` để đơn cũ trong DB còn đọc ra chữ đúng.
_SOURCE_LABELS = {SOURCE_BAO_GIA: "Từ báo giá", "nhap_tay": "Nhập giá tay"}


def _i(x) -> int:
    """Numeric/Decimal → int (làm tròn)."""
    return int(round(float(x))) if x is not None else 0


# --- Đính kèm: bytes đi qua kho file dùng chung, đọc lại qua /api/files --------
_MAX_ATTACH_BYTES = 10 * 1024 * 1024
_MAX_ATTACH_PER = 20


def _save_attachment(subdir: str, owner_id: int, file_name, content_type, data: bytes) -> tuple[str, str, int]:
    ct = (content_type or "").lower()
    if not (ct.startswith("image/") or ct == "application/pdf"):
        raise OrderValidationError("Chỉ nhận ảnh (image/*) hoặc PDF")
    if not data:
        raise OrderValidationError("Tệp rỗng")
    if len(data) > _MAX_ATTACH_BYTES:
        raise OrderValidationError("Tệp vượt quá 10 MB")
    key, safe = make_key(subdir, owner_id, file_name)
    get_storage().save(key, data, content_type)
    return url_from_key(key), safe, len(data)


def _unlink_attachment(url: str) -> None:
    key = key_from_url(url)
    if key:
        get_storage().delete(key)


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
        """Map quotation_id → mã báo giá (quote_number) để hiển thị 'Nguồn'.

        MỘT câu cho cả trang. Trước đây lặp `get_by_id` từng báo giá → N+1.
        """
        qids = {i for i in ids if i}
        if not qids:
            return {}
        rows = self.db.query(Quote.id, Quote.quote_number).filter(Quote.id.in_(qids)).all()
        return {qid: code for qid, code in rows}

    def _money(self, order: Order, *, agg: dict | None = None,
               received: int | None = None) -> dict:
        """Các số tiền suy diễn của 1 đơn (dùng chung cho row + detail).

        `agg`/`received` là số ĐÃ TÍNH SẴN theo lô cho cả trang danh sách (repo.money_sums +
        accounting_repo.received_deposit_sums). Truyền vào thì hàm này KHÔNG chạm DB — đó là
        cách gỡ N+1 ở màn danh sách. Bỏ trống (đường detail 1 đơn) thì tự truy vấn như cũ.
        """
        if agg is None:
            total = self.repo.line_total_sum(order.id)
            total_with_vat = self.repo.total_with_vat(order.id)
            order_cost = self.repo.order_cost_sum(order.id)
        else:
            # Đơn không có dòng nào thì vắng mặt trong map → mặc định ĐÚNG như bản lẻ.
            total = agg.get("total")
            total_with_vat = agg.get("total_with_vat", 0)
            order_cost = agg.get("order_cost")
        # V5: cọc đọc từ phiếu thu THẬT (Kế toán) — Σ PaymentReceipt(order, source=đơn, received).
        if received is None:
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
        # (a) báo giá còn duyệt & còn hạn (chỉ nguồn báo giá)
        if order.source_type == SOURCE_BAO_GIA:
            quote = self.quotations.get_by_id(order.quotation_id) if order.quotation_id else None
            if quote is None or quote.status not in (STATUS_ACCEPTED, "converted_to_order"):
                blockers.append("Báo giá chưa được khách đồng ý")
            elif quote.valid_until and quote.valid_until < date.today():
                blockers.append("Báo giá đã hết hạn — cần báo giá lại")
        # (b) CỌC KHÔNG còn là cổng chốt — Chốt = chốt THÔNG TIN; thu tiền cọc là bước SAU chốt
        # (kế toán thu → Sales "Chuyển xuống SX"). Chỉ cần đủ THÔNG TIN dưới đây để chốt.
        # (c) đủ PO + ngày giao
        if not order.customer_po_no:
            blockers.append("Thiếu số PO khách")
        if not order.delivery_committed_date:
            blockers.append("Thiếu ngày giao cam kết")
        # còn dòng chưa định giá → tổng/cọc bị thiếu, chặn chốt
        if self.repo.unpriced_line_count(order.id) > 0:
            blockers.append("Còn dòng chưa định giá")
        # (d) chứng cứ khách đồng ý: đơn giờ LUÔN từ báo giá accepted — chính báo giá là chứng cứ,
        #     nên cổng "thiếu đính kèm" (chỉ áp cho đơn nhập tay) đã bỏ cùng đường nhập tay.
        # (e/f) cổng "đơn đặc thù chưa được duyệt" đã bỏ cùng luồng duyệt.
        return (len(blockers) == 0), blockers

    def _row(self, order: Order, customer_name: str | None, sale_name: str | None,
             quotation_code: str | None = None, *, agg: dict | None = None,
             received: int | None = None) -> OrderRow:
        m = self._money(order, agg=agg, received=received)
        return OrderRow(
            id=order.id,
            order_no=order.order_no,
            customer_id=order.customer_id,
            customer_name=customer_name,
            quotation_id=order.quotation_id,
            quotation_code=quotation_code,
            source_type=order.source_type,
            order_kind=order.order_kind,
            status=order.status,
            cost_basis=order.cost_basis,
            total=m["total"],
            total_with_vat=m["total_with_vat"],
            deposit_pct=order.deposit_pct,
            deposit_required=m["deposit_required"],
            deposit_received=m["deposit_received"],
            deposit_ok=m["deposit_ok"],
            delivery_committed_date=order.delivery_committed_date,
            is_rush=order.is_rush,
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
            delivery_contact_name=order.delivery_contact_name,
            delivery_contact_phone=order.delivery_contact_phone,
            delivery_note=order.delivery_note,
            production_note=order.production_note,
            vat_pct_estimate=order.vat_pct_estimate,
            lines=[OrderLineOut.model_validate(ln) for ln in order.lines],
            order_cost=m["order_cost"],
            margin_pct=m["margin_pct"],
            cancel_reason=order.cancel_reason,
            cancel_fault=order.cancel_fault,
            deposits=deposits,
            consent_attachments=consent_atts,
            can_confirm=can_confirm,
            confirm_blockers=blockers,
            quote_expired=quote_expired,
            san_xuat_released_at=order.san_xuat_released_at,
        )

    # --- reads --------------------------------------------------------------
    def list(
        self, *, actor, scope: str, q: str | None, status: str | None,
        order_kind: str | None, sort: str, page: int, size: int,
    ) -> OrderListOut:
        rows, total, names, _totals = self.repo.list(
            scope=scope, actor=actor, q=q, status=status, order_kind=order_kind,
            sort=sort, page=page, size=size,
        )
        sale_names = self._user_names([r.sale_user_id for r in rows])
        q_codes = self._quote_codes([r.quotation_id for r in rows])
        # Gỡ N+1: 4 tổng tiền của MỌI đơn trên trang lấy bằng 2 câu gộp, thay vì 4 câu mỗi đơn.
        order_ids = [r.id for r in rows]
        sums = self.repo.money_sums(order_ids)
        received = self.accounting_repo.received_deposit_sums(order_ids)
        items = [
            self._row(o, names.get(o.id), sale_names.get(o.sale_user_id),
                      q_codes.get(o.quotation_id),
                      agg=sums.get(o.id, {}), received=received.get(o.id, 0))
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
            statuses=[EnumOption(value=v, label=lb) for v, lb in _STATUS_LABELS.items()],
        )

    # --- writes -------------------------------------------------------------
    def create(self, *, actor, scope: str, payload) -> OrderDetailOut:
        """Đơn CHỈ sinh từ báo giá khách đã đồng ý — không còn nhánh nào khác."""
        if payload.order_kind == ORDER_KIND_BO_SUNG and not payload.parent_order_id:
            raise OrderValidationError("Đơn bổ sung phải trỏ đơn gốc (giữ kẽm)")
        if payload.deposit_pct is not None and not 0 <= payload.deposit_pct <= 100:
            raise OrderValidationError("% cọc phải trong khoảng 0–100")

        order = self._create_from_quotation(actor=actor, payload=payload)

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

        # Khách chốt MỘT PHẦN: chỉ kéo dòng khách ƯNG (accepted=True). Fallback: 0 dòng True → kéo TẤT
        # CẢ — an toàn cho báo giá cũ chốt trước khi có cột `accepted` (service accept bắt buộc ≥1 dòng
        # True nên báo giá mới luôn có ít nhất 1).
        accepted_items = [it for it in version.items if getattr(it, "accepted", False)]
        source_items = accepted_items if accepted_items else list(version.items)

        lines = []
        for it in sorted(source_items, key=lambda x: x.line_no):
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
                phieu_thanh_phan_id=it.phieu_thanh_phan_id,   # pin truy vết ấn phẩm (soft) từ dòng báo giá
                nhom=getattr(it, "nhom", None),   # nhãn gộp dòng khi in xác nhận đơn (khớp báo giá)
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
            sale_user_id=(quote.salesperson_id or actor.id),
            status=STATUS_DRAFT,
            vat_pct_estimate=_i(version.vat_percent),
            # % cọc nhập trên đơn ưu tiên; chưa nhập thì ghim từ báo giá.
            # % cọc đặt TẠI ĐƠN (báo giá không còn giữ deposit_pct — tích hợp accounting-wip):
            # nhập trên đơn thì lấy, chưa nhập để None → Kế toán đặt lúc ghi cọc.
            deposit_pct=payload.deposit_pct,
            cost_basis=COST_BASIS_QUOTE,
            needs_approval=False,
            approval_state=APPROVAL_STATE_NONE,
            delivery_address=(payload.delivery_address or quote.delivery_address),
            customer_po_no=payload.customer_po_no,
            delivery_committed_date=payload.delivery_committed_date,
            delivery_contact_name=payload.delivery_contact_name,
            delivery_contact_phone=payload.delivery_contact_phone,
            delivery_note=payload.delivery_note,
            production_note=payload.production_note,
            is_rush=payload.is_rush,
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
            "delivery_contact_name", "delivery_contact_phone", "delivery_note",
            "production_note", "is_rush",
        ):
            val = getattr(payload, f)
            if val is not None:
                fields[f] = val
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

    def update_production_hint(self, *, order_id: int, actor, scope: str, payload) -> OrderDetailOut:
        """Sale đổi 'hint sản xuất' (gấp / lưu ý SX) SAU khi đơn đã CHỐT — đường HẸP duy nhất được sửa
        khi `status=ORDERED` (`update()` khóa DRAFT). Chỉ 2 field; realtime tới bàn kế hoạch do router
        phát. KHÔNG nới `update()` cũ (giữ cổng nháp cho phần còn lại của đơn)."""
        order = self.repo.get_with_lines(order_id)
        if order is None or not self.repo.can_access(order=order, scope=scope, actor=actor):
            raise OrderNotFound("Không tìm thấy đơn hàng")
        if order.status != STATUS_ORDERED:
            raise OrderConflict("Chỉ sửa lưu ý sản xuất khi đơn đã chốt")
        fields: dict = {}
        if payload.is_rush is not None:
            fields["is_rush"] = payload.is_rush
        if payload.production_note is not None:
            fields["production_note"] = payload.production_note
        if fields:
            self.repo.update(order, **fields)
        self.audit.create(
            actor_user_id=actor.id, action="update_production_hint",
            target=f"order:{order.id}", detail=f"Cập nhật lưu ý SX đơn {order.order_no}",
        )
        return self._detail(self.repo.get_with_lines(order_id))

    def release_production(self, *, order_id: int, actor, scope: str) -> OrderDetailOut:
        """Sale "Chuyển xuống sản xuất" — đơn đã CHỐT (cọc đủ theo cổng chốt) → set mốc release →
        đơn vào HÀNG CHỜ kế hoạch. NGƯỜI QUYẾT (không auto khi chốt). Idempotent: đã release → giữ
        mốc đầu, bấm lại an toàn."""
        order = self.repo.get_by_id(order_id)
        if order is None or not self.repo.can_access(order=order, scope=scope, actor=actor):
            raise OrderNotFound("Không tìm thấy đơn hàng")
        if order.status != STATUS_ORDERED:
            raise OrderConflict("Chỉ chuyển sản xuất đơn đã chốt")
        if not self._money(order)["deposit_ok"]:
            raise OrderConflict("Chưa đủ cọc — kế toán thu đủ cọc rồi mới chuyển sản xuất")
        if order.san_xuat_released_at is None:
            order.san_xuat_released_at = datetime.now(timezone.utc)
            self.db.commit()
            self.audit.create(
                actor_user_id=actor.id, action="release_production",
                target=f"order:{order.id}", detail=f"Chuyển đơn {order.order_no} xuống sản xuất",
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

    def notify_summary(self, *, actor, scope: str,
                       can_record_deposit: bool, can_manage_status: bool) -> dict:
        """Số nuôi badge/toast real-time — 'việc chờ TÔI xử lý' theo vai (đơn còn NHÁP trong phạm vi):
        Kế toán = đơn chờ ghi cọc; Sale = đơn đủ điều kiện chờ chốt. Tự giảm khi người dùng thao tác
        (không cần cờ 'seen'). Đếm trên tập nháp nhỏ nên rẻ.

        `approval_pending` đã bỏ cùng luồng duyệt. Vẫn TRẢ khoá đó với giá trị 0 để client cũ
        (tab đang mở, bản FE chưa nạp lại) không vỡ khi đọc thiếu khoá."""
        deposit_pending = ready_to_confirm = 0
        for o in self.repo.drafts_in_scope(scope=scope, actor=actor):
            m = self._money(o)
            if can_record_deposit and (o.deposit_pct or 0) > 0 and not m["deposit_ok"]:
                deposit_pending += 1
            if can_manage_status and m["deposit_ok"]:
                ready_to_confirm += 1
        return {
            "action_count": deposit_pending + ready_to_confirm,
            "approval_pending": 0,
            "deposit_pending": deposit_pending,
            "ready_to_confirm": ready_to_confirm,
        }

    # --- Cọc (V5) — Kế toán LẬP PHIẾU THU THẬT từ đơn (bước 2, SAU chốt) ------
    def add_deposit_receipt(self, *, order_id: int, actor, scope: str, payload) -> OrderDetailOut:
        """Kế toán tạo PaymentReceipt(source='don_hang_ban', received) gắn đơn. THU CỌC = BƯỚC 2 SAU
        chốt (chốt = chốt thông tin; kế toán nhận SSE khi đơn chốt → thu cọc). Cho ghi khi đơn đã CHỐT;
        chặn hủy. Quyền gate ở router = record_deposit."""
        order = self.repo.get_by_id(order_id)
        if order is None or not self.repo.can_access(order=order, scope=scope, actor=actor):
            raise OrderNotFound("Không tìm thấy đơn hàng")
        if order.status == STATUS_CANCELLED:
            raise OrderConflict("Đơn đã hủy — không ghi cọc")
        customer_name = None
        if order.customer_id:
            from ..models.customer import Customer

            c = self.db.get(Customer, order.customer_id)
            customer_name = c.name if c else None
        try:
            # Cầu nối kế toán canonical (accounting-wip): lập phiếu thu 01-TT cọc đơn (Nợ 111/112·Có 131).
            self.accounting.create_order_receipt(
                order_id=order.id, order_no=order.order_no, customer_name=customer_name, actor=actor,
                receipt_method=payload.receipt_method, amount=payload.amount,
                receipt_date=(payload.receipt_date or date.today()), note=payload.note,
                company_bank_account_id=payload.company_bank_account_id,
            )
        except AccountingValidationError as exc:
            raise OrderValidationError(str(exc)) from exc
        self.audit.create(
            actor_user_id=actor.id, action="record_deposit", target=f"order:{order.id}",
            detail=f"Thu cọc {int(payload.amount):,}đ ({payload.receipt_method}) — đơn {order.order_no}",
        )
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
        url, safe, size = _save_attachment("don-hang", order.id, file_name, content_type, data)
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
        _unlink_attachment(att.file_url)
        self.db.delete(att)
        self.db.commit()
        self.audit.create(actor_user_id=actor.id, action="delete_consent",
            target=f"order:{order.id}", detail=f"Xóa chứng cứ #{attachment_id}")
        return self._detail(self.repo.get_with_lines(order_id))

    # V5: minh chứng đã thu cọc KHÔNG còn đính ở đơn — dùng PaymentReceiptAttachment (màn Phiếu thu
    # Kế toán, endpoint /api/accounting/payment-receipts/{id}/attachments).
