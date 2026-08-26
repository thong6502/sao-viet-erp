"""Báo giá (Quotation / Quote) business logic — Header-Version-Item (H-V-I) pattern.
"""
from __future__ import annotations

import math
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from ..models.quotation import (
    DEFAULT_TERMS,
    Quote,
    QuoteVersion,
    QuoteItem,
    STATUS_DRAFT,
    STATUS_PENDING_APPROVAL,
    STATUS_APPROVED,
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
from ..services.exception_gate import (
    DECISIONS as _EXC_DECISIONS,
    DECISION_APPROVED as _EXC_APPROVED,
    approval_status as _exc_approval_status,
    evaluate as _exc_evaluate,
    evaluate_quote as _exc_evaluate_quote,
)
from ..services.sequence_service import SequenceService


_QUY_CACH_IN_NHAN = {
    "mot_mat": "1 mặt",
    "hai_mat": "2 mặt",
    "tu_tro": "trở tự",
    "tro_nhip": "trở nhíp",
}


def _kho_tp(tp) -> str | None:
    """Khổ thành phẩm dạng người đọc — `"205×145mm"`. None khi chưa khai đủ hai chiều.

    Thay cho cột chữ `kho_thanh_pham` đã DROP ở mig 0144: cột đó chỉ chép lại chính hai số này
    bằng cm ("14,5×20,5 cm") nên giữ hai nguồn là mở đường cho chúng lệch nhau.
    """
    dai = int(getattr(tp, "dai_thanh_pham", 0) or 0)
    rong = int(getattr(tp, "rong_thanh_pham", 0) or 0)
    return f"{dai}×{rong}mm" if dai and rong else None


def dien_giai_tu_thanh_phan(db, tp) -> str | None:
    """Bung DIỄN GIẢI quy cách (in ra báo giá) từ 1 'sản phẩm' của bài tính giá.

    Mỗi dòng = 1 gạch đầu dòng trên bản in: khổ · giấy · in · gia công. Là ĐỀ XUẤT — người soạn
    báo giá sửa/bổ sung được (máy không suy ra nổi bồi sóng, đục lỗ, cột thành phẩm…). Thiếu dữ
    liệu thì BỎ dòng đó, KHÔNG bịa (dòng trống trên báo giá gửi khách tệ hơn là không có dòng).
    """
    from ..models.vat_lieu_kho import GiayNguyen

    dong: list[str] = []

    # Khổ thành phẩm: số đo thật. Nhãn chữ `kho_thanh_pham` đã DROP (mig 0144) — nó vốn chỉ chép
    # lại đúng hai số này bằng cm nên bỏ đi không mất gì.
    if _kho_tp(tp):
        dong.append(f"KT: {_kho_tp(tp)}")

    # Giấy: tên + định lượng từ danh mục.
    # GỠ 2026-08-09 (Đợt 4 · K): hậu tố "(khách cấp)". Công ty luôn cấp giấy, nên nhãn đó chỉ còn
    # là câu thừa trên báo giá — và tệ hơn, nó hứa với khách một điều giá không còn phản ánh.
    if getattr(tp, "giay_id", None) is not None:
        giay = db.get(GiayNguyen, tp.giay_id)
        if giay is not None:
            g = giay.ten or ""
            if giay.gsm:
                g = f"{g} {giay.gsm}g".strip()
            if g:
                dong.append(g)

    # In: số màu + quy cách. 2 mặt khác số màu → "4+1 màu"; bằng nhau → "4 màu".
    if getattr(tp, "co_in", False):
        a, b = int(getattr(tp, "so_mau_a", 0) or 0), int(getattr(tp, "so_mau_b", 0) or 0)
        mau = f"{a}+{b}" if b and b != a else (str(a) if a else "")
        if mau:
            nhan = _QUY_CACH_IN_NHAN.get(getattr(tp, "quy_cach_in", None) or "", "")
            dong.append(f"In {mau} màu {nhan}".strip())

    # Gia công sau in: chuỗi công đoạn theo đúng thứ tự người tính giá đã khai.
    gia_cong = [
        (r.ten or "").strip()
        for r in sorted(getattr(tp, "thanh_phams", []) or [], key=lambda r: (r.thu_tu or 0, r.id or 0))
        if (r.ten or "").strip()
    ]
    if gia_cong:
        dong.append(" · ".join(gia_cong))

    return "\n".join(dong) or None


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


class QuotationService:
    def __init__(
        self,
        quotations: QuotationRepository,
        audit: AuditLogRepository,
        customers=None,
        sequence: SequenceService | None = None,
    ) -> None:
        self.quotations = quotations
        self.audit = audit
        self._customers = customers
        self.sequence = sequence

    def _customer_display_name(self, customer_id: int | None) -> str | None:
        if customer_id is None or self._customers is None:
            return None
        c = self._customers.get_by_id(customer_id)
        return c.name if c else None

    def _customer_defaults(self, customer_id: int | None) -> dict:
        """Auto-fill từ CRM (redesign-bao-gia §4): người liên hệ CHÍNH (`CustomerContact.is_primary`)
        + ĐC giao MẶC ĐỊNH (`CustomerAddress.is_default`). Repo list_* đã xếp is_primary/is_default
        lên đầu; fallback phần tử đầu nếu chưa đặt cờ. Rỗng nếu không có khách/repo."""
        out = {"contact_name": None, "contact_phone": None, "contact_title": None, "delivery_address": None}
        if customer_id is None or self._customers is None:
            return out
        contacts = list(getattr(self._customers, "list_contacts", lambda _cid: [])(customer_id))
        primary = next((c for c in contacts if c.is_primary), contacts[0] if contacts else None)
        if primary is not None:
            out.update(contact_name=primary.name, contact_phone=primary.phone, contact_title=primary.title)
        else:
            # Chưa có danh bạ liên hệ riêng → lấy tạm liên hệ ngay trên hồ sơ khách
            # (Customer.contact_name / phone) để ô "Người liên hệ" không trống.
            cust = self._customers.get_by_id(customer_id)
            if cust is not None:
                out.update(
                    contact_name=getattr(cust, "contact_name", None),
                    contact_phone=getattr(cust, "phone", None),
                )
        addrs = list(getattr(self._customers, "list_addresses", lambda _cid: [])(customer_id))
        default_addr = next((a for a in addrs if a.is_default), addrs[0] if addrs else None)
        if default_addr is not None:
            out["delivery_address"] = default_addr.address
        return out

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
            # Markup TRÊN GIÁ VỐN (không phải biên lợi nhuận trên giá bán): gốc 100, markup 20%
            # → bán 120 (chủ chốt 26/08/2026 — khớp cách sale vẫn hiểu "markup").
            m_pct = max(0.0, float(margin_percent))
            selling_price = total_cost * (1.0 + m_pct / 100.0)

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

    def pending_approval_count(self, *, scope: str, actor, can_approve: bool) -> int:
        """Badge 'chờ tôi duyệt': CHỈ người có quyền duyệt đặc thù mới có số; người khác = 0."""
        if not can_approve:
            return 0
        return self.quotations.count_pending_approval(scope=scope, actor=actor)

    def notify_summary(self, *, scope: str, actor, can_approve: bool) -> dict:
        """Số nuôi real-time badge/toast luồng gửi duyệt (SSE snapshot + REST fallback):
        - `pending_approval_count`: số chờ TÔI duyệt (chỉ người duyệt mới có số).
        - `my_decided_unseen`: số báo giá của TÔI (người soạn) vừa được GĐ quyết mà tôi chưa xem."""
        return {
            "pending_approval_count": self.pending_approval_count(
                scope=scope, actor=actor, can_approve=can_approve
            ),
            "my_decided_unseen": self.quotations.count_my_decided_unseen(actor.id),
        }

    def mark_decisions_seen(self, *, actor) -> None:
        """Người soạn xác nhận đã xem các quyết định duyệt/từ chối → đóng badge/toast phía Sale."""
        self.quotations.mark_my_decisions_seen(actor.id)

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

    def activity(self, *, quotation_id: int, scope: str, actor) -> list[dict]:
        """Nhật ký tương tác THẬT của 1 báo giá (feed Hoạt động) — ai làm gì, khi nào. Đọc audit
        log theo target `quote:{id}` (mọi vai trò sale/TP/GĐ đụng cùng phiếu đều để lại dấu vết),
        cũ→mới ĐẢO thành mới→cũ, kèm NGƯỜI thao tác. RBAC: qua get_quotation (đúng phạm vi).

        Người thao tác ghi theo HỒ SƠ ("Ban giám đốc · Giám đốc · Nguyễn Văn Giám") — xem
        `actor_display`; KHÔNG dùng `user_names` (tên tài khoản, chỉ hợp cho cột phụ trách ở list)."""
        from .actor_display import actor_labels

        quote = self.get_quotation(quotation_id=quotation_id, scope=scope, actor=actor)
        rows = self.audit.list_by_target(f"quote:{quote.id}", limit=200)
        names = actor_labels(self.quotations.db, {r.actor_user_id for r in rows if r.actor_user_id})
        return [
            {
                "action": r.action,
                "actor_name": names.get(r.actor_user_id) if r.actor_user_id else None,
                "detail": r.detail,
                "at": r.created_at,
            }
            for r in rows
        ]

    def effective_contact(self, quote: Quote) -> dict:
        """Người liên hệ để HIỂN THỊ ở chi tiết báo giá: ưu tiên SNAPSHOT (đã đóng băng khi
        gửi/khóa); nếu snapshot trống (phiếu cũ / khách chưa có danh bạ) thì lấy tạm liên hệ chính
        hiện tại của khách để ô "Người liên hệ" không trống. Không ghi đè snapshot (chỉ để xem)."""
        if quote.contact_name_snapshot or quote.contact_phone_snapshot:
            return {
                "name": quote.contact_name_snapshot,
                "phone": quote.contact_phone_snapshot,
                "title": quote.contact_title_snapshot,
            }
        d = self._customer_defaults(quote.customer_id)
        return {"name": d["contact_name"], "phone": d["contact_phone"], "title": d["contact_title"]}

    def version_history(self, quote: Quote) -> list[QuoteVersion]:
        return self.quotations.versions_of(quote.quote_number)

    def customer_display(self, quote: Quote):
        if quote.customer_id is None or self._customers is None:
            return None
        return quotation_ports.CustomerRefAdapter(self._customers).get_customer(quote.customer_id)

    def phieu_tinh_gia_ref(self, quote: Quote) -> dict:
        """Tham chiếu Phiếu tính giá NGUỒN (redesign-bao-gia §6, link mở phiếu). {id, ma} — id=None
        cho báo giá cũ chưa neo phiếu nào."""
        if quote.phieu_tinh_gia_id is None:
            return {"id": None, "ma": None}
        from ..models.phieu_tinh_gia import PhieuTinhGia
        ptg = self.quotations.db.get(PhieuTinhGia, quote.phieu_tinh_gia_id)
        return {"id": quote.phieu_tinh_gia_id, "ma": ptg.ma if ptg else None}

    # --- writes ---------------------------------------------------------------
    def create_quotation(
        self,
        *,
        customer_id: int | None,
        phieu_tinh_gia_id: int | None = None,
        margin_percent: float | None = None,
        valid_until: date | None = None,
        terms_text: str | None = None,
        customer_note: str | None = None,
        internal_note: str | None = None,
        actor,
    ) -> Quote:
        """Tạo báo giá TỪ 1 Phiếu tính giá. Từ Đợt 5 đây là nguồn DUY NHẤT — đường Estimate
        (cụm tính giá đời cũ) đã gỡ hẳn, không còn `estimate_id`/`picks`."""
        if phieu_tinh_gia_id is None:
            raise QuotationValidationError(
                "Báo giá phải xuất phát từ một Phiếu tính giá — chọn phiếu trước khi tạo."
            )
        if valid_until and valid_until < date.today():
            raise QuotationValidationError("Hạn hiệu lực không được ở quá khứ.")
        # Mặc định hạn hiệu lực = 30 ngày kể từ hôm nay (ngày tạo phiên bản mới nhất). Để trống chủ ý
        # (không truyền) → auto +30; muốn "đến khi có thông báo" thì xoá ở màn chi tiết sau.
        if valid_until is None:
            valid_until = date.today() + timedelta(days=30)

        # Điều khoản: caller bỏ trống → điền sẵn bộ mặc định để sale sửa ngay trên màn báo giá.
        terms_text = (terms_text or "").strip() or DEFAULT_TERMS

        return self._create_from_ptg(
            phieu_tinh_gia_id=phieu_tinh_gia_id,
            customer_id=customer_id,
            margin_percent=margin_percent,
            valid_until=valid_until,
            terms_text=terms_text,
            customer_note=customer_note,
            internal_note=internal_note,
            actor=actor,
        )

    def _create_from_ptg(
        self, *, phieu_tinh_gia_id: int, customer_id: int | None, margin_percent: float | None,
        valid_until: date | None, terms_text, customer_note, internal_note, actor,
    ) -> Quote:
        """BG-1: tạo báo giá TỪ 1 Phiếu tính giá (PTG) — 1 dòng / mỗi "sản phẩm" (PhieuThanhPhan). Giá
        vốn KHÓA = `gia_von_tp` (snapshot copy-on-write, sửa PTG sau không đổi báo giá). SL = so_luong
        sản phẩm (0 → SL mặc định phiếu). Markup/VAT MẶC ĐỊNH (PhieuThanhPhan không có 2 field này) —
        sales chỉnh sau. GUARD 1 PTG → 1 BG đang hiệu lực (cancelled/rejected/expired nhả chỗ)."""
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from ..models.phieu_tinh_gia import PhieuTinhGia

        db = self.quotations.db
        ptg = db.execute(
            select(PhieuTinhGia)
            .where(PhieuTinhGia.id == phieu_tinh_gia_id)
            .options(selectinload(PhieuTinhGia.thanh_phans))
        ).scalar_one_or_none()
        if ptg is None:
            raise QuotationValidationError("Không tìm thấy phiếu tính giá.")
        if not ptg.thanh_phans:
            raise QuotationValidationError("Phiếu tính giá chưa có sản phẩm nào để báo giá.")

        # 1 PTG → NHIỀU báo giá: mỗi lần bấm "Báo giá" tạo 1 phiếu MỚI (không ghi tiếp phiếu cũ).
        # Sửa/điều chỉnh 1 báo giá đã có → dùng "Tạo phiên bản mới" TRONG phiếu đó (có ghi chú bắt buộc).
        quote_number = self.sequence.generate_code("quotation") if self.sequence else "BG26-0001"
        # Auto-fill người liên hệ chính + ĐC giao mặc định từ CRM (redesign-bao-gia §4); ĐC giao chỉ
        # điền khi caller CHƯA cung cấp.
        defaults = self._customer_defaults(customer_id)
        quote = Quote(
            quote_number=quote_number,
            customer_id=customer_id,
            customer_name_snapshot=self._customer_display_name(customer_id),
            phieu_tinh_gia_id=phieu_tinh_gia_id,
            salesperson_id=actor.id,
            status=STATUS_DRAFT,
            valid_until=valid_until,
            terms_text=terms_text,
            delivery_address=defaults["delivery_address"],
            contact_name_snapshot=defaults["contact_name"],
            contact_phone_snapshot=defaults["contact_phone"],
            contact_title_snapshot=defaults["contact_title"],
            customer_note=customer_note,
            internal_note=internal_note,
            created_by=actor.id,
        )
        self.quotations.create(quote)

        version = QuoteVersion(
            quote_id=quote.id, version_number=1, status=VERSION_STATUS_DRAFT, created_by=actor.id,
        )
        self.quotations.db.add(version)
        self.quotations.db.flush()

        default_margin = float(margin_percent) if margin_percent is not None else 20.0
        self._fill_version_from_ptg(
            version, ptg, margin_by_index=None, default_margin=default_margin, default_vat=10.0,
        )
        quote.current_version_id = version.id
        self.quotations.update(quote)

        self.audit.create(
            actor_user_id=actor.id, action="create_quote", target=f"quote:{quote.id}",
            detail=f"Tạo báo giá {quote.quote_number} v1 từ phiếu tính giá {ptg.ma} "
            f"({len(ptg.thanh_phans)} sản phẩm)",
        )
        return quote

    def _fill_version_from_ptg(
        self, version, ptg, *, margin_by_index: dict[int, float] | None,
        default_margin: float, default_vat: float,
    ) -> None:
        """Dựng dòng báo giá TỪ các 'sản phẩm' (PhieuThanhPhan) của PTG vào 1 version + gộp tổng.
        Giá vốn KHÓA = gia_von_tp; SL = so_luong sản phẩm (0 → SL mặc định phiếu). `margin_by_index`
        GIỮ markup theo VỊ TRÍ dòng (0-based) khi ĐỒNG BỘ LẠI — KHÔNG theo phieu_thanh_phan_id, vì mỗi
        lần sửa PTG `_replace_children` XÓA+TẠO LẠI thanh_phan với id mới (id không ổn định, nhất là
        Postgres không tái dùng id). Dòng chưa có ở bản cũ → dùng default_margin. Duyệt theo thứ tự
        (thu_tu, id) cho ổn định — khớp cách engine sắp xếp."""
        subtotal = discount = vat = final = total_cost = 0.0
        tps = sorted(ptg.thanh_phans, key=lambda t: (t.thu_tu or 0, t.id or 0))
        for pos, tp in enumerate(tps):
            i = pos + 1
            qty = int(tp.so_luong) or int(ptg.so_luong) or 1     # 0 = lấy SL mặc định phiếu
            cost = float(tp.gia_von_tp or 0)
            margin = (margin_by_index or {}).get(pos, default_margin)
            pricing = self.calculate_pricing(
                total_cost=cost, margin_percent=margin, vat_percent=default_vat, quantity=qty,
            )
            self.quotations.db.add(QuoteItem(
                quote_version_id=version.id,
                phieu_thanh_phan_id=tp.id,
                line_no=i,
                product_type=tp.loai_thanh_phan or "san_pham",
                product_name=tp.ten or ptg.ten_san_pham or f"Sản phẩm {i}",
                product_spec_text=_kho_tp(tp),
                # Đông cứng lúc tạo: sửa PTG về sau KHÔNG đổi bản đã gửi khách (đồng bộ → version mới).
                dien_giai=dien_giai_tu_thanh_phan(self.quotations.db, tp),
                # Nhãn nhóm: chỉ để BẢN IN gom dòng (ruột + bìa → 1 dòng "quyển sách"). Dữ liệu
                # vẫn 1 dòng/thành phần để markup riêng + mạch xuống sản xuất không đứt.
                nhom=(getattr(tp, "nhom_bao_gia", None) or None),
                quantity=qty,
                unit=(getattr(tp, "don_vi_tinh", None) or "cái"),   # ĐVT chảy từ sản phẩm PTG
                total_cost_snapshot=cost,
                margin_percent=margin,
                selling_price=pricing["selling_price"],
                unit_price=pricing["unit_price"],
                discount_amount=pricing["discount_amount"],
                vat_percent=default_vat,
                vat_amount=pricing["vat_amount"],
                final_amount=pricing["final_amount"],
            ))
            subtotal += pricing["selling_price"]
            discount += pricing["discount_amount"]
            vat += pricing["vat_amount"]
            final += pricing["final_amount"]
            total_cost += cost
        version.total_cost_snapshot = total_cost
        version.subtotal_amount = subtotal
        version.discount_amount = discount
        version.vat_amount = vat
        version.final_amount = final

    def resync_from_ptg(self, *, phieu_tinh_gia_id: int, scope: str, actor) -> tuple[Quote, str]:
        """PTG đổi số → ĐỒNG BỘ sang báo giá đang hiệu lực (Phương án A). NHÁP → cập nhật TẠI CHỖ
        bản nháp (giữ markup theo dòng + điều khoản/khách đã nhập). ĐÃ CHỐT (chờ duyệt/đã duyệt/
        khách đồng ý) → tạo PHIÊN BẢN MỚI v(n+1) draft giá vốn mới, bản cũ → superseded. Đã lên đơn
        thì CHẶN. Trả `(quote, mode)` với mode ∈ {"draft_synced","new_version"}."""
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from ..models.phieu_tinh_gia import PhieuTinhGia

        db = self.quotations.db
        ptg = db.execute(
            select(PhieuTinhGia)
            .where(PhieuTinhGia.id == phieu_tinh_gia_id)
            .options(selectinload(PhieuTinhGia.thanh_phans))
        ).scalar_one_or_none()
        if ptg is None:
            raise QuotationValidationError("Không tìm thấy phiếu tính giá.")
        if not ptg.thanh_phans:
            raise QuotationValidationError("Phiếu tính giá chưa có sản phẩm nào để báo giá.")

        quote = self.quotations.active_for_phieu(phieu_tinh_gia_id)
        if quote is None:
            raise QuotationConflict("Phiếu tính giá này chưa có báo giá đang hiệu lực.")
        # RBAC scope: chỉ đồng bộ báo giá trong phạm vi của người thao tác.
        self.get_quotation(quotation_id=quote.id, scope=scope, actor=actor)
        if quote.status == STATUS_CONVERTED_TO_ORDER:
            raise QuotationConflict(
                f"Báo giá {quote.quote_number} đã lên đơn hàng — không thể đồng bộ lại từ phiếu tính giá."
            )

        current = db.get(QuoteVersion, quote.current_version_id) if quote.current_version_id else None
        # GIỮ markup người dùng đã đặt theo VỊ TRÍ dòng (bản cũ sắp theo line_no) — KHÔNG theo
        # phieu_thanh_phan_id (id đổi mỗi lần sửa PTG). Dòng mới thêm → default_margin.
        old_items = sorted((current.items if current else []), key=lambda it: it.line_no or 0)
        margin_by_index = {idx: float(it.margin_percent) for idx, it in enumerate(old_items)}

        if quote.status == STATUS_DRAFT:
            # NHÁP: làm mới TẠI CHỖ bản nháp hiện tại (không đẻ version).
            if current is None:
                raise QuotationConflict("Báo giá chưa có phiên bản để đồng bộ.")
            for it in list(current.items):
                db.delete(it)
            db.flush()
            self._fill_version_from_ptg(
                current, ptg, margin_by_index=margin_by_index, default_margin=20.0, default_vat=10.0,
            )
            self.quotations.update(quote)
            self.audit.create(
                actor_user_id=actor.id, action="change_order", target=f"quote:{quote.id}",
                detail=f"{quote.quote_number}: đồng bộ giá vốn từ phiếu tính giá {ptg.ma} (bản nháp v{current.version_number})",
            )
            return quote, "draft_synced"

        # ĐÃ CHỐT: bản cũ superseded, tạo phiên bản mới draft giá vốn mới → quote về nháp.
        if current:
            current.status = VERSION_STATUS_SUPERSEDED
        new_version = QuoteVersion(
            quote_id=quote.id,
            version_number=(current.version_number + 1) if current else 2,
            status=VERSION_STATUS_DRAFT,
            created_by=actor.id,
        )
        db.add(new_version)
        db.flush()
        self._fill_version_from_ptg(
            new_version, ptg, margin_by_index=margin_by_index, default_margin=20.0, default_vat=10.0,
        )
        quote.current_version_id = new_version.id
        quote.status = STATUS_DRAFT
        self.quotations.update(quote)
        self.audit.create(
            actor_user_id=actor.id, action="change_order", target=f"quote:{quote.id}",
            detail=f"{quote.quote_number}: v{current.version_number if current else 1} → v{new_version.version_number} "
            f"đồng bộ giá vốn mới từ phiếu tính giá {ptg.ma}",
        )
        return quote, "new_version"

    # --- BG-2: "báo giá đặc thù" — GĐ duyệt (cùng máy exception_gate với A2) --------

    def exception_eval(self, quote: Quote) -> dict:
        """Soi 'báo giá đặc thù' trên VERSION HIỆN TẠI — cổng **theo TỪNG KHÁCH HÀNG** (redesign):
        - LUÔN áp (chung): Giá trị đơn ≥ 1 tỷ · Bán dưới vốn.
        - Theo rào của KH (bỏ ngưỡng 15% cứng): CHIẾT KHẤU vượt `discount_max_pct` · BIÊN dưới
          `margin_min_pct`. KH chưa đặt rào (None) → bỏ qua cổng đó; KH null (khách lẻ) → chỉ 2 cổng chung.
        Số lấy từ tổng đã lưu của version: subtotal NET (trước VAT, sau CK) · gross (trước CK) · discount ·
        total gồm VAT · cost. (Cổng công nợ HOÃN tới khi build phân hệ Công nợ/AR.)"""
        version = (
            self.quotations.db.get(QuoteVersion, quote.current_version_id)
            if quote.current_version_id else None
        )
        if version is None:
            return _exc_evaluate_quote(subtotal=0, total_gross=0, cost=None)
        subtotal_gross = int(round(float(version.subtotal_amount)))
        discount = int(round(float(version.discount_amount)))
        subtotal_net = subtotal_gross - discount
        total_gross = int(round(float(version.final_amount)))
        cost = int(round(float(version.total_cost_snapshot)))
        # Rào chính sách tài chính của KHÁCH (None nếu chưa đặt / khách lẻ chưa chọn). Ngoài khoảng
        # [min,max] (cả 2 chiều) → đặc thù; rào nào để None thì bỏ chiều đó.
        cust = self._customers.get_by_id(quote.customer_id) if (quote.customer_id and self._customers) else None
        return _exc_evaluate_quote(
            subtotal=subtotal_net, total_gross=total_gross, cost=cost,
            discount_amount=discount, subtotal_gross=subtotal_gross,
            discount_min_pct=(cust.discount_min_pct if cust else None),
            discount_max_pct=(cust.discount_max_pct if cust else None),
            margin_min_pct=(cust.margin_min_pct if cust else None),
            margin_max_pct=(cust.margin_max_pct if cust else None),
        )

    def approval_status(self, quote: Quote, exc: dict | None = None) -> dict:
        """Tình trạng duyệt 'báo giá đặc thù' — DELEGATE về exception_gate.approval_status."""
        if exc is None:
            exc = self.exception_eval(quote)
        row = self.quotations.latest_approval(quote.id)
        latest = None if row is None else {
            "decision": row.decision, "total": row.total, "subtotal": row.subtotal,
            "cost": row.cost, "note": row.note, "decided_at": row.decided_at,
        }
        return _exc_approval_status(exc, latest)

    def quote_gate(self, quote: Quote) -> dict:
        """Khối 'báo giá đặc thù' cho output/UI (nhãn định tính + margin_pct nhạy cảm — router strip).
        Kèm AI đã quyết định gần nhất (tên + thời điểm) để UI hiện 'đã được X duyệt/từ chối'."""
        exc = self.exception_eval(quote)
        appr = self.approval_status(quote, exc)
        row = self.quotations.latest_approval(quote.id)
        decided_by_name = None
        if row is not None and row.decided_by:
            decided_by_name = self.user_names({row.decided_by}).get(row.decided_by)
        return {
            "exception_required": appr["required"],
            "exception_status": appr["status"],       # none|pending|approved|rejected|stale
            "exception_cleared": appr["cleared"],
            "exceptions": exc["triggers"],
            "exception_note": appr["note"],
            "margin_pct": exc["margin_pct"],
            "exception_decision": row.decision if row is not None else None,
            "exception_decided_by_name": decided_by_name,
            "exception_decided_at": row.decided_at if row is not None else None,
        }

    def record_approval(self, *, quotation_id: int, decision: str, note: str | None, scope: str, actor):
        """Giám đốc Kinh doanh DUYỆT / TỪ CHỐI 'báo giá đặc thù' — chỉ khi báo giá đang **Chờ duyệt**
        (`pending_approval`, tức đã 'Trình duyệt'). Ghim số + ngưỡng (audit). Duyệt 'bao phủ' → báo giá
        sang **Đã duyệt** (`sent`, gộp 'đã gửi khách' — Q2). Từ chối → **quay về Nháp** (`draft`) + banner
        lý do (Q4). Chặn nếu báo giá KHÔNG thuộc diện đặc thù."""
        if decision not in _EXC_DECISIONS:
            raise QuotationValidationError("Quyết định không hợp lệ (chỉ 'approved' / 'rejected').")
        quote = self.get_quotation(quotation_id=quotation_id, scope=scope, actor=actor)
        exc = self.exception_eval(quote)
        if not exc["triggers"]:
            raise QuotationValidationError(
                "Báo giá không thuộc diện đặc thù — không cần Giám đốc Kinh doanh duyệt."
            )
        if quote.status != STATUS_PENDING_APPROVAL:
            raise QuotationValidationError(
                "Chỉ duyệt khi báo giá đang 'Chờ duyệt' (Sales phải TRÌNH DUYỆT trước)."
            )
        # Người duyệt PHẢI phản hồi lý do — dù đồng ý hay từ chối (redesign-bao-gia §10, chủ đầu tư chốt).
        if not note or not note.strip():
            raise QuotationValidationError(
                "Phải nêu lý do/ý kiến khi duyệt hoặc từ chối báo giá đặc thù."
            )
        row = self.quotations.create_approval(
            quote_id=quote.id,
            decision=decision,
            triggers_json=[t["key"] for t in exc["triggers"]],
            total=exc["total_gross"],
            subtotal=exc["subtotal"],
            cost=exc["cost"],
            margin_pct_snapshot=exc["margin_pct"],
            min_margin_pct=exc["min_margin_pct"],
            high_value_threshold=exc["high_value_threshold"],
            note=note,
            decided_by=actor.id,
        )
        # Lái trạng thái: GĐ DUYỆT → "Đã duyệt" (approved, khóa; KHÔNG gửi, KHÔNG freeze — sale tự gửi
        # khách sau, freeze lúc gửi). TỪ CHỐI → "Bị từ chối" (rejected, KHÓA) — sale bấm "Tạo phiên
        # bản mới" để sửa rồi trình duyệt lại (versioning CHỈ ở trạng thái từ chối).
        version = self.quotations.db.get(QuoteVersion, quote.current_version_id)
        if decision == _EXC_APPROVED:
            quote.status = STATUS_APPROVED
            if version:
                version.status = VERSION_STATUS_LOCKED
        else:
            quote.status = STATUS_REJECTED
            if version:
                version.status = VERSION_STATUS_REJECTED
        # Real-time: đánh dấu "có quyết định MỚI chưa xem" cho người soạn → badge/toast phía Sale.
        quote.decision_seen_at = None
        self.quotations.update(quote)
        verb = "duyệt" if decision == _EXC_APPROVED else "từ chối"
        # KHÔNG ghim vai vào câu log ("Giám đốc KD …"): người bấm có thể là GĐ Kinh doanh, TP Kinh
        # doanh hay Giám đốc công ty — ai cũng cầm `can_approve_exception`. Vai thật lấy từ HỒ SƠ
        # của người thao tác (`actor_display`), câu log chỉ tả VIỆC.
        self.audit.create(
            actor_user_id=actor.id, action=f"quote_exception_{decision}", target=f"quote:{quote.id}",
            detail=f"{quote.quote_number}: {verb} báo giá đặc thù "
            f"({', '.join(t['key'] for t in exc['triggers'])})",
        )
        return row

    def list_approvals(self, *, quotation_id: int, scope: str, actor) -> list:
        quote = self.get_quotation(quotation_id=quotation_id, scope=scope, actor=actor)
        return self.quotations.list_approvals(quote.id)

    # --- Tài liệu đính kèm (NỘI BỘ: file khách gửi / mẫu thiết kế / ảnh tham khảo) ---
    # Lớp tài liệu tách khỏi dữ liệu giá: cho thêm/xóa ở MỌI trạng thái trừ Hủy (chủ đầu tư chốt).
    # Mọi thao tác để lại vết ai-gì-lúc-nào ở feed Hoạt động (audit theo target quote:{id}).
    def list_attachments(self, *, quotation_id: int, scope: str, actor) -> list:
        quote = self.get_quotation(quotation_id=quotation_id, scope=scope, actor=actor)
        return self.quotations.list_attachments(quote.id)

    def add_attachment(
        self, *, quotation_id: int, scope: str, actor,
        file_name: str, file_url: str, file_type: str | None,
    ):
        quote = self.get_quotation(quotation_id=quotation_id, scope=scope, actor=actor)
        if quote.status == STATUS_CANCELLED:
            raise QuotationLocked("Báo giá đã hủy — không đính kèm tài liệu được.")
        att = self.quotations.add_attachment(
            quote.id, file_name=file_name, file_url=file_url,
            file_type=file_type, uploaded_by=actor.id,
        )
        self.audit.create(
            actor_user_id=actor.id, action="quote_attach_add", target=f"quote:{quote.id}",
            detail=f"{quote.quote_number}: đính kèm tài liệu {file_name}",
        )
        return att

    def delete_attachment(self, *, quotation_id: int, attachment_id: int, scope: str, actor) -> str | None:
        """Xóa 1 đính kèm. Trả `file_url` để router dọn object trong storage (tránh file rác)."""
        quote = self.get_quotation(quotation_id=quotation_id, scope=scope, actor=actor)
        if quote.status == STATUS_CANCELLED:
            raise QuotationLocked("Báo giá đã hủy — không sửa tài liệu đính kèm được.")
        att = self.quotations.get_attachment(attachment_id)
        if att is None or att.quote_id != quote.id:
            raise QuotationNotFound("Không tìm thấy tài liệu đính kèm.")
        file_url = att.file_url
        self.quotations.delete_attachment(att)
        self.audit.create(
            actor_user_id=actor.id, action="quote_attach_delete", target=f"quote:{quote.id}",
            detail=f"{quote.quote_number}: xóa tài liệu {att.file_name}",
        )
        return file_url

    def update_quotation(
        self,
        *,
        quotation_id: int,
        scope: str,
        actor,
        customer_id: int | None,
        valid_until: date | None,
        terms_text: str | None = None,
        customer_note: str | None = None,
        internal_note: str | None = None,
        items_payload: list[dict] | None = None,
    ) -> Quote:
        quote = self.get_quotation(quotation_id=quotation_id, scope=scope, actor=actor)
        if quote.status not in (STATUS_DRAFT,):
            raise QuotationLocked("Chỉ chỉnh sửa được báo giá ở trạng thái nháp.")

        if valid_until and valid_until < date.today():
            raise QuotationValidationError("Hạn hiệu lực không được ở quá khứ.")

        # Update Header — đổi khách → làm mới liên hệ chính + ĐC giao mặc định (redesign-bao-gia §4).
        # ĐC giao không sửa được ở màn báo giá → chỉ làm mới khi ĐỔI KHÁCH, ngoài ra giữ nguyên.
        customer_changed = customer_id != quote.customer_id
        quote.customer_id = customer_id
        quote.customer_name_snapshot = self._customer_display_name(customer_id)
        if customer_changed:
            defaults = self._customer_defaults(customer_id)
            quote.contact_name_snapshot = defaults["contact_name"]
            quote.contact_phone_snapshot = defaults["contact_phone"]
            quote.contact_title_snapshot = defaults["contact_title"]
            quote.delivery_address = defaults["delivery_address"]
        quote.valid_until = valid_until
        quote.terms_text = (terms_text or "").strip() or DEFAULT_TERMS
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
                    db_item.po_code = ip.get("po_code", db_item.po_code)
                    db_item.dien_giai = ip.get("dien_giai", db_item.dien_giai)

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

        # Gộp các lần "Cập nhật báo giá" liên tiếp của cùng người → 1 mục (bump thời điểm), tránh
        # nhật ký Hoạt động phình vô tận khi lưu nháp/sửa nhiều lần.
        self.audit.create_collapsing(
            actor_user_id=actor.id,
            action="update_quote",
            target=f"quote:{quote.id}",
            detail=f"Cập nhật báo giá {quote.quote_number} v{version.version_number}",
        )
        return quote

    # --- Writes: Transition (redesign-bao-gia §3) -----------------------------
    def _apply_send(self, quote: Quote, version) -> None:
        """Thân bước 'Gửi khách' = sang **Đã duyệt** (`sent`): khóa phiên bản + freeze snapshot
        copy-on-write + đặt hạn hiệu lực nếu chưa có. Dùng chung cho draft→sent (báo giá THƯỜNG) và
        duyệt đặc thù (pending_approval → sent, gọi từ `record_approval`)."""
        if version:
            version.status = VERSION_STATUS_SENT
            version.sent_at = datetime.now(timezone.utc)
            # Freeze cost breakdown lúc gửi khách (copy-on-write, P0 §34).
            if version.internal_cost_snapshot_json is None:
                # B5 (redesign-bao-gia §8): đường PhieuTinhGia — freeze phân rã giá vốn theo các DÒNG đã
                # khóa lúc tạo (total_cost_snapshot per PhieuThanhPhan) để bản gửi không đổi khi PTG sửa.
                version.internal_cost_snapshot_json = {
                    "source": "phieu_tinh_gia",
                    "lines": [
                        {
                            "phieu_thanh_phan_id": it.phieu_thanh_phan_id,
                            "product_name": it.product_name,
                            "quantity": it.quantity,
                            "total_cost_snapshot": float(it.total_cost_snapshot or 0),
                        }
                        for it in version.items
                    ],
                }
        quote.status = STATUS_SENT
        if quote.valid_until is None:
            quote.valid_until = date.today()

    def _apply_accept_picks(self, version, accepted_item_ids: list[int] | None) -> None:
        """Ghi quyết định khách chốt MỘT PHẦN lên các dòng của version. None → ưng tất cả (chốt nhanh /
        tương thích cũ). Có danh sách → dòng trong danh sách = ưng, còn lại = không lấy (giữ vết);
        phải ≥1 dòng ưng và id phải thuộc báo giá này."""
        items = list(version.items)
        if accepted_item_ids is None:
            for it in items:
                it.accepted = True
            return
        picked = set(accepted_item_ids)
        valid_ids = {it.id for it in items}
        if picked - valid_ids:
            raise QuotationValidationError("Có dòng được chọn không thuộc báo giá này.")
        if not (picked & valid_ids):
            raise QuotationValidationError("Phải chọn ít nhất 1 sản phẩm khách chốt.")
        for it in items:
            it.accepted = it.id in picked

    def transition(
        self,
        *,
        quotation_id: int,
        to_status: str,
        scope: str,
        actor,
        cancel_reason: str | None = None,
        accepted_item_ids: list[int] | None = None,
    ) -> Quote:
        """Chuyển trạng thái báo giá (redesign-bao-gia §3). Báo giá ĐẶC THÙ KHÔNG được gửi/khách-duyệt
        thẳng — phải TRÌNH DUYỆT (draft→pending_approval) rồi Giám đốc Kinh doanh duyệt (qua /approval).

        `accepted_item_ids` (chỉ khi to_status="accepted"): khách chốt MỘT PHẦN — id các dòng khách ƯNG;
        None = ưng tất cả. Đơn hàng sau đó chỉ kéo dòng accepted=True."""
        quote = self.get_quotation(quotation_id=quotation_id, scope=scope, actor=actor)
        version = self.quotations.db.get(QuoteVersion, quote.current_version_id)

        if to_status == STATUS_PENDING_APPROVAL:
            # Trình duyệt: CHỈ báo giá đặc thù, từ Nháp.
            if quote.status != STATUS_DRAFT:
                raise QuotationConflict(f"Không thể trình duyệt từ trạng thái {quote.status}.")
            if not self.exception_eval(quote)["triggers"]:
                raise QuotationValidationError(
                    "Báo giá không thuộc diện đặc thù — gửi khách thẳng, không cần trình duyệt."
                )
            quote.status = STATUS_PENDING_APPROVAL

        elif to_status == STATUS_SENT:
            # Gửi khách (SALE tự gửi): từ Nháp (báo giá THƯỜNG) HOẶC từ "Đã duyệt" (đặc thù đã được
            # Giám đốc Kinh doanh DUYỆT). Freeze snapshot tại mốc gửi này.
            if quote.status == STATUS_DRAFT:
                if self.quote_gate(quote)["exception_required"]:
                    raise QuotationValidationError(
                        "Báo giá thuộc diện đặc thù — phải TRÌNH DUYỆT để Giám đốc Kinh doanh duyệt "
                        "trước khi gửi khách."
                    )
            elif quote.status != STATUS_APPROVED:
                raise QuotationConflict(f"Không thể chuyển trạng thái {quote.status} -> sent")
            self._apply_send(quote, version)

        elif to_status == STATUS_ACCEPTED:
            # Khách duyệt: từ sent (chuẩn) hoặc draft (chốt trực tiếp — chỉ báo giá thường).
            if quote.status not in (STATUS_SENT, STATUS_DRAFT):
                raise QuotationConflict(f"Không thể duyệt báo giá đang ở trạng thái {quote.status}")
            if quote.status == STATUS_DRAFT and self.quote_gate(quote)["exception_required"]:
                raise QuotationValidationError(
                    "Báo giá thuộc diện đặc thù — phải trình duyệt & gửi khách trước khi khách chốt."
                )
            if quote.valid_until and quote.valid_until < date.today():
                quote.status = STATUS_EXPIRED
                self.quotations.update(quote)
                raise QuotationConflict("Báo giá đã hết hạn hiệu lực, không thể duyệt.")
            quote.status = STATUS_ACCEPTED
            if version:
                version.status = VERSION_STATUS_ACCEPTED
                version.accepted_at = datetime.now(timezone.utc)
                self._apply_accept_picks(version, accepted_item_ids)

        elif to_status == STATUS_REJECTED:
            # Khách từ chối (SAU khi gửi) — khác với Giám đốc KD từ chối duyệt (→ về Nháp).
            if quote.status != STATUS_SENT:
                raise QuotationConflict(f"Không thể từ chối báo giá đang ở trạng thái {quote.status}")
            quote.status = STATUS_REJECTED
            if version:
                version.status = VERSION_STATUS_REJECTED
                version.rejected_at = datetime.now(timezone.utc)

        elif to_status == STATUS_CANCELLED:
            # Hủy (kèm lý do) — từ mọi trạng thái làm việc TRƯỚC khi lên đơn.
            if not cancel_reason or not cancel_reason.strip():
                raise QuotationValidationError("Cần nêu lý do hủy.")
            if quote.status not in (
                STATUS_DRAFT, STATUS_PENDING_APPROVAL, STATUS_APPROVED, STATUS_SENT,
                STATUS_ACCEPTED, STATUS_REJECTED,
            ):
                raise QuotationConflict(f"Không thể hủy báo giá đang ở trạng thái {quote.status}.")
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
    def requote(self, *, quotation_id: int, scope: str, actor, change_reason: str) -> Quote:
        """Create a new version (re-quote) from an existing quote. `change_reason` BẮT BUỘC —
        mỗi phiên bản mới phải ghi rõ LÝ DO/thay đổi (in vào feed Hoạt động + Lịch sử phiên bản)."""
        reason = (change_reason or "").strip()
        if not reason:
            raise QuotationValidationError("Phải ghi chú/lý do cho phiên bản mới trước khi tạo.")
        quote = self.get_quotation(quotation_id=quotation_id, scope=scope, actor=actor)

        # Tạo phiên bản mới CHỈ khi báo giá BỊ TỪ CHỐI (khách từ chối HOẶC GĐ/TP từ chối đặc thù —
        # cả hai đều `rejected`) → sale sửa lại rồi trình duyệt/gửi lại. Trạng thái khác: nháp thì
        # sửa thẳng; đang chạy (chờ duyệt/đã duyệt/đã gửi) hoặc kết thúc (đồng ý/hết hạn/lên đơn/hủy)
        # thì KHÔNG đẻ phiên bản.
        if quote.status != STATUS_REJECTED:
            raise QuotationConflict(
                f"Chỉ tạo phiên bản mới khi báo giá BỊ TỪ CHỐI (hiện: '{quote.status}')."
            )

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
            internal_cost_snapshot_json=current_version.internal_cost_snapshot_json if current_version else None,
            change_reason=reason,
            created_by=actor.id,
        )
        self.quotations.db.add(new_version)
        self.quotations.db.flush()

        # Duplicate items to new version
        if current_version:
            for item in current_version.items:
                new_item = QuoteItem(
                    quote_version_id=new_version.id,
                    phieu_thanh_phan_id=item.phieu_thanh_phan_id,
                    line_no=item.line_no,
                    product_type=item.product_type,
                    product_name=item.product_name,
                    product_spec_text=item.product_spec_text,
                    dien_giai=item.dien_giai,
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
        # Hạn hiệu lực reset = 30 ngày kể từ phiên bản mới nhất (vừa tạo).
        quote.valid_until = date.today() + timedelta(days=30)
        self.quotations.update(quote)

        self.audit.create(
            actor_user_id=actor.id,
            action="change_order",
            target=f"quote:{quote.id}",
            detail=f"{quote.quote_number}: tạo phiên bản v{new_version.version_number} — {reason}",
        )
        return quote
