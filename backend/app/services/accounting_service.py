"""Business rules for Accounting purchase approvals and payment vouchers."""
from __future__ import annotations

import secrets
import string
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError

from ..models.accounting import (
    BANK_FEE_BEARERS,
    BANK_FEE_PAYER,
    PAYMENT_RECEIPT_CANCELLED,
    PAYMENT_RECEIPT_RECEIVED,
    PAYMENT_RECEIPT_WAITING,
    PAYMENT_STAGES,
    PAYMENT_VOUCHER_CANCELLED,
    PAYMENT_VOUCHER_PAID,
    PAYMENT_VOUCHER_STATUSES,
    PAYMENT_VOUCHER_TYPES,
    PAYMENT_VOUCHER_WAITING,
    RECEIPT_SOURCE_ORDER,
    RECEIPT_SOURCE_PURCHASE,
    VOUCHER_BANK_TRANSFER,
    VOUCHER_CASH,
    CompanyBankAccount,
    PaymentReceipt,
    PaymentReceiptAttachment,
    PaymentVoucher,
    PaymentVoucherAttachment,
    SupplierBankAccount,
)
from ..models.document_sequence import (
    SEQ_DOC_TYPE_PAYMENT_RECEIPT,
    SEQ_DOC_TYPE_PAYMENT_VOUCHER,
)
from ..models.purchase import (
    DPR_CANCELLED,
    DPR_DONE,
    DPR_IN_PURCHASE,
    PR_APPROVED,
    PR_PENDING,
    PR_PURCHASED,
    PR_RECEIVED,
    PurchaseRequest,
)
from ..repositories.accounting_repo import AccountingRepository
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.purchase_repo import PurchaseRequestRepository, SupplierRepository
from ..repositories.user_repo import UserRepository
from ..storage import get_storage, key_from_url, make_key, url_from_key
from .purchase_service import _purchase_line_amounts, purchase_money
from .sequence_service import SequenceService


class AccountingError(Exception):
    pass


class AccountingValidationError(AccountingError):
    pass


class AccountingNotFound(AccountingError):
    pass


class AccountingConflict(AccountingError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _business_today() -> date:
    """Hôm nay theo giờ xưởng. SEAM — cột 'Quá hạn' của Công nợ phải trả so ngày qua đây.

    Để test chọc được (`monkeypatch.setattr(accounting_service, "_business_today", ...)`). Gọi thẳng
    `date.today()` trong thân hàm là đẻ ra test thối theo thời gian — dự án đã dính một lần rồi."""
    return datetime.now(ZoneInfo("Asia/Bangkok")).date()


# File đính kèm chứng từ: bytes đi qua kho file dùng chung (app/storage.py), đọc lại qua
# /api/files và chỉ người có quyền `ke_toan` mới xem được. Vẫn giới hạn loại + cỡ file.
_ATTACHMENT_SUBDIR = "ke-toan"
_RECEIPT_ATTACHMENT_SUBDIR = "ke-toan-thu"
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_ATTACHMENTS_PER_VOUCHER = 20

# Kỳ của cột "Đã trả" và rổ ✅ trên màn Công nợ phải trả. CỨNG, cố ý không cho chọn trên giao diện:
# ô chọn kỳ là nút toàn màn mà 90% thời gian không dùng tới (việc hằng ngày là "ai đang nợ, ai quá
# hạn" — hai thứ đó không dính gì tới kỳ). Cần tra NCC đã im lặng lâu thì dùng Ô TÌM, nó lôi được
# mọi NCC bất kể kỳ.
#
# Kỳ càng dài càng phải quét nhiều đơn đã tất toán ⇒ đây cũng là chốt chặn màn chậm dần.
PAYABLES_PERIOD_MONTHS = 3


def _delete_stored_file(file_url: str | None) -> None:
    """Gỡ bytes best-effort — xoá row mới là việc chính, file rác không được làm hỏng request."""
    key = key_from_url(file_url)
    if key:
        get_storage().delete(key)


def _text(value, *, label: str, required: bool = False, max_length: int | None = None):
    cleaned = (value or "").strip()
    if required and not cleaned:
        raise AccountingValidationError(f"{label} không được để trống.")
    if max_length is not None and len(cleaned) > max_length:
        raise AccountingValidationError(f"{label} vượt quá {max_length} ký tự.")
    return cleaned or None


class AccountingService:
    def __init__(
        self,
        repo: AccountingRepository,
        purchases: PurchaseRequestRepository,
        suppliers: SupplierRepository,
        users: UserRepository,
        audit: AuditLogRepository,
        sequences: SequenceService,
    ) -> None:
        self.repo = repo
        self.purchases = purchases
        self.suppliers = suppliers
        self.users = users
        self.audit = audit
        self.sequences = sequences

    # --- bank accounts ----------------------------------------------------

    def list_company_accounts(self, *, active_only: bool = False):
        return self.repo.list_company_accounts(active_only=active_only)

    def create_company_account(self, *, actor, **values):
        cleaned = self._clean_bank_account(values)
        make_default = bool(cleaned.pop("is_default")) or self.repo.company_account_count() == 0
        row = CompanyBankAccount(**cleaned, is_default=make_default)
        try:
            saved = self.repo.save_company_account(row, make_default=make_default)
        except IntegrityError as exc:
            raise AccountingConflict("Tài khoản ngân hàng công ty đã tồn tại.") from exc
        self.audit.create(
            actor_user_id=actor.id,
            action="create_company_bank_account",
            target=f"company_bank_account:{saved.id}",
            detail=f"{saved.bank_name} - {saved.account_number}",
        )
        return saved

    def update_company_account(self, account_id: int, *, actor, **values):
        row = self.repo.get_company_account(account_id)
        if row is None:
            raise AccountingNotFound("Không tìm thấy tài khoản ngân hàng công ty.")
        cleaned = self._clean_bank_account(values)
        make_default = bool(cleaned.pop("is_default"))
        for key, value in cleaned.items():
            setattr(row, key, value)
        row.is_default = make_default
        try:
            saved = self.repo.save_company_account(row, make_default=make_default)
        except IntegrityError as exc:
            raise AccountingConflict("Tài khoản ngân hàng công ty đã tồn tại.") from exc
        self.audit.create(
            actor_user_id=actor.id,
            action="update_company_bank_account",
            target=f"company_bank_account:{saved.id}",
            detail=f"{saved.bank_name} - {saved.account_number}",
        )
        return saved

    def toggle_company_account(self, account_id: int, *, actor):
        row = self.repo.get_company_account(account_id)
        if row is None:
            raise AccountingNotFound("Không tìm thấy tài khoản ngân hàng công ty.")
        row.is_active = not row.is_active
        if not row.is_active:
            row.is_default = False
        saved = self.repo.save_company_account(row, make_default=False)
        self.audit.create(
            actor_user_id=actor.id,
            action="toggle_company_bank_account",
            target=f"company_bank_account:{saved.id}",
            detail="active" if saved.is_active else "inactive",
        )
        return saved

    def list_supplier_accounts(self, *, supplier_id: int | None = None, active_only: bool = False):
        return [
            self._supplier_account_out(row)
            for row in self.repo.list_supplier_accounts(
                supplier_id=supplier_id, active_only=active_only
            )
        ]

    def create_supplier_account(self, *, actor, supplier_id: int, **values):
        supplier = self.suppliers.get_by_id(supplier_id)
        if supplier is None:
            raise AccountingNotFound("Không tìm thấy nhà cung cấp.")
        cleaned = self._clean_bank_account(values)
        make_default = bool(cleaned.pop("is_default")) or self.repo.supplier_account_count(supplier_id) == 0
        row = SupplierBankAccount(
            supplier_id=supplier_id, **cleaned, is_default=make_default
        )
        try:
            saved = self.repo.save_supplier_account(row, make_default=make_default)
        except IntegrityError as exc:
            raise AccountingConflict("Tài khoản ngân hàng nhà cung cấp đã tồn tại.") from exc
        self.audit.create(
            actor_user_id=actor.id,
            action="create_supplier_bank_account",
            target=f"supplier_bank_account:{saved.id}",
            detail=f"{supplier.name} - {saved.account_number}",
        )
        return self._supplier_account_out(saved)

    def update_supplier_account(self, account_id: int, *, actor, supplier_id: int, **values):
        row = self.repo.get_supplier_account(account_id)
        if row is None:
            raise AccountingNotFound("Không tìm thấy tài khoản ngân hàng nhà cung cấp.")
        supplier = self.suppliers.get_by_id(supplier_id)
        if supplier is None:
            raise AccountingNotFound("Không tìm thấy nhà cung cấp.")
        cleaned = self._clean_bank_account(values)
        make_default = bool(cleaned.pop("is_default"))
        row.supplier_id = supplier_id
        for key, value in cleaned.items():
            setattr(row, key, value)
        row.is_default = make_default
        try:
            saved = self.repo.save_supplier_account(row, make_default=make_default)
        except IntegrityError as exc:
            raise AccountingConflict("Tài khoản ngân hàng nhà cung cấp đã tồn tại.") from exc
        self.audit.create(
            actor_user_id=actor.id,
            action="update_supplier_bank_account",
            target=f"supplier_bank_account:{saved.id}",
            detail=f"{supplier.name} - {saved.account_number}",
        )
        return self._supplier_account_out(saved)

    def toggle_supplier_account(self, account_id: int, *, actor):
        row = self.repo.get_supplier_account(account_id)
        if row is None:
            raise AccountingNotFound("Không tìm thấy tài khoản ngân hàng nhà cung cấp.")
        row.is_active = not row.is_active
        if not row.is_active:
            row.is_default = False
        saved = self.repo.save_supplier_account(row, make_default=False)
        self.audit.create(
            actor_user_id=actor.id,
            action="toggle_supplier_bank_account",
            target=f"supplier_bank_account:{saved.id}",
            detail="active" if saved.is_active else "inactive",
        )
        return self._supplier_account_out(saved)

    # --- công nợ phải trả -------------------------------------------------
    #
    # KHÔNG có bảng công nợ. Số dư là phép CỘNG TRỪ chạy lúc mở màn, suy từ chứng từ đang có, nên
    # không ai gõ tay sửa được và không bao giờ lệch với phiếu. Muốn một món nợ biến mất chỉ có hai
    # đường: lập phiếu chi rồi chi, hoặc huỷ đơn.
    #
    # Ba rổ, đừng lẫn:
    #   🔴 CHƯA VÀO SỔ — đơn ĐÃ NHẬN HÀNG mà chưa có phiếu chi phủ hết. Nợ có thật nhưng kế toán
    #      chưa lập phiếu. Bỏ rổ này đi là GIẤU NỢ: bảng sạch bong trong khi vẫn đang nợ NCC.
    #   🟡 CHỜ CHI — đã lập phiếu, tiền chưa ra. Nợ đã vào sổ, có hạn trả.
    #   ✅ ĐÃ TRẢ — từng LẦN TRẢ (không phải từng đơn). Cộng lại đúng bằng cột "Đã trả".
    #
    # Rổ ✅ trước 05/08/2026 liệt kê "đơn đã trả xong" — sai đơn vị: cột "Đã trả" là TIỀN, bấm vào
    # mà ra danh sách ĐƠN thì cộng không khớp. Đổi sang từng lần trả cũng hợp việc đối chiếu hơn:
    # NCC gửi sao kê cũng nghĩ theo từng lần nhận tiền, không nghĩ theo đơn.
    #
    # ⚠️ Nhãn trên màn phải là "Đã trả" ở CẢ HAI chỗ (cột ngoài bảng lẫn khối trong drawer). Có lúc
    # ngoài bảng ghi "Đã trả" mà trong drawer ghi "Đã chi trong kỳ" — cùng một con số, hai tên, chủ
    # đọc không hiểu là cái gì. Tên trường trong API (`paid_in_period`, `paid`) giữ nguyên, chỉ nhãn
    # hiển thị mới cần đồng bộ.
    #
    # Đơn đã duyệt mà hàng chưa về KHÔNG nằm ở đây — chưa nợ ai. (Đó là "dự chi", việc khác.)

    def _no_cua_phieu(self, row) -> dict:
        """Bóc một phiếu mua thành các con số công nợ.

        Tiền lấy từ `purchase_money` — DÙNG CHUNG với màn Mua hàng, không cộng lại ở đây. Hai chỗ
        tự cộng lấy là hai chỗ lệch, mà lệch tiền thì tới lúc đối chiếu với NCC mới lòi ra."""
        money = purchase_money(row)
        # `available_amount` = phần trần chưa có phiếu chi nào phủ. Với đơn ĐÃ NHẬN HÀNG, đó đúng
        # bằng số nợ chưa vào sổ. Đơn chưa nhận hàng thì phần này chưa phải nợ.
        chua_vao_so = money["available_amount"] if row.status == PR_RECEIVED else 0
        return {
            "money": money,
            "chua_vao_so": chua_vao_so,
            "cho_chi": money["pending_amount"],
            "con_no": chua_vao_so + money["pending_amount"],
        }

    @staticmethod
    def _ngay_chi(v) -> date:
        """Ngày tiền THỰC SỰ rời két. `paid_at` là mốc bấm 'Đã chi'; phiếu cũ chưa có thì lùi về
        ngày chứng từ."""
        return v.paid_at.date() if v.paid_at is not None else v.voucher_date

    def payables_summary(self, *, q: str | None = None) -> dict:
        """Công nợ phải trả gom theo nhà cung cấp.

        Dựng dòng khi **còn nợ > 0 HOẶC đã trả trong kỳ > 0**. Chỉ lấy "còn nợ > 0" là NCC vừa trả
        hết biến mất khỏi bảng ngay — mà đó đúng là lúc cần thấy nhất: câu hỏi *"làm sao biết mình
        đã trả hết"* chỉ trả lời được bằng cách NHÌN THẤY danh sách đã trả, không phải bằng việc
        không thấy gì (im lặng còn có nghĩa là màn hỏng).

        `q` = tìm theo tên NCC. Khi có `q` thì lôi ra **mọi** NCC khớp tên, kể cả nợ 0đ và không hề
        giao dịch trong kỳ — dùng để tra một NCC đã im lặng lâu. Lọc ở SERVER chứ không lọc trên
        danh sách đã dựng, vì NCC đó vốn không có dòng nào để mà lọc."""
        hom_nay = _business_today()
        moc_ky = hom_nay - timedelta(days=31 * PAYABLES_PERIOD_MONTHS)
        tim = (q or "").strip().lower()
        theo_ncc: dict[int | None, dict] = {}

        def _muc(row) -> dict:
            return theo_ncc.setdefault(
                row.supplier_id,
                {
                    "supplier_id": row.supplier_id,
                    "supplier_name": row.supplier.name if row.supplier else "(không rõ NCC)",
                    "order_count": 0,
                    "unrecorded_amount": 0,
                    "waiting_amount": 0,
                    "overdue_amount": 0,
                    "paid_in_period": 0,
                    "total_due": 0,
                },
            )

        for row in self.purchases.list_for_payables():
            no = self._no_cua_phieu(row)
            da_tra_ky = sum(
                int(v.amount_vnd)
                for v in row.payment_vouchers
                if v.status == PAYMENT_VOUCHER_PAID and self._ngay_chi(v) >= moc_ky
            )
            ten = (row.supplier.name if row.supplier else "").lower()
            khop_tim = bool(tim) and tim in ten
            if no["con_no"] <= 0 and da_tra_ky <= 0 and not khop_tim:
                continue
            muc = _muc(row)
            muc["paid_in_period"] += da_tra_ky
            if no["con_no"] <= 0:
                # Đơn không còn nợ vẫn được góp tiền đã trả, nhưng KHÔNG đếm vào "Đơn còn nợ" —
                # cột đếm mà lẫn đơn đã xong là nó chửi nhau với cột "Tổng còn nợ".
                continue
            muc["order_count"] += 1
            muc["unrecorded_amount"] += no["chua_vao_so"]
            muc["waiting_amount"] += no["cho_chi"]
            muc["total_due"] += no["con_no"]
            for v in row.payment_vouchers:
                if v.status != PAYMENT_VOUCHER_WAITING:
                    continue
                if v.planned_payment_date is not None and v.planned_payment_date < hom_nay:
                    muc["overdue_amount"] += int(v.amount_vnd)

        items = sorted(
            theo_ncc.values(),
            key=lambda m: (m["total_due"], m["paid_in_period"]),
            reverse=True,
        )
        return {
            "items": items,
            "total_due": sum(m["total_due"] for m in items),
            "unrecorded_amount": sum(m["unrecorded_amount"] for m in items),
            "waiting_amount": sum(m["waiting_amount"] for m in items),
            "overdue_amount": sum(m["overdue_amount"] for m in items),
            "paid_in_period": sum(m["paid_in_period"] for m in items),
            "period_months": PAYABLES_PERIOD_MONTHS,
            "as_of": hom_nay,
        }

    def payables_detail(self, supplier_id: int, *, all_history: bool = False) -> dict:
        """Chi tiết công nợ một NCC — 🔴 chưa vào sổ · 🟡 chờ chi · ✅ đã chi trong kỳ.

        ⚠️ Kỳ CHỈ cắt phần ĐÃ TRẢ. Nợ chưa trả (🔴 và 🟡) không hề nhìn ngày — đơn nợ từ hai năm
        trước hôm nay vẫn hiện đủ. Nợ cũ không bao giờ tự biến mất.

        `all_history=True` bỏ mốc kỳ cho riêng rổ ✅ — dùng cho nút "Xem lịch sử cũ hơn". NCC trả
        hết từ 5 tháng trước thì mặc định rổ ✅ rỗng, tra ra "không nợ" nhưng không thấy đã trả
        những gì; nút này để với tới.

        Nới chỉ cho MỘT NCC nên vẫn nhẹ. Đừng bao giờ nới cho cả bảng tổng hợp — lúc đó mỗi lần mở
        màn phải quét mọi đơn từ ngày mở công ty."""
        hom_nay = _business_today()
        moc_ky = (
            date.min if all_history else hom_nay - timedelta(days=31 * PAYABLES_PERIOD_MONTHS)
        )
        supplier = self.suppliers.get_by_id(supplier_id)
        chua_vao_so: list[dict] = []
        cho_chi: list[dict] = []
        da_chi: list[dict] = []
        for row in self.purchases.list_for_payables(supplier_id=supplier_id):
            no = self._no_cua_phieu(row)
            money = no["money"]
            if no["chua_vao_so"] > 0:
                chua_vao_so.append(
                    {
                        "purchase_request_id": row.id,
                        "code": row.code,
                        "status": row.status,
                        "total_estimate": money["total"],
                        "received_total": money["received_total"],
                        "amount": no["chua_vao_so"],
                        "expected_receipt_date": row.expected_receipt_date,
                    }
                )
            for v in row.payment_vouchers:
                chung = {
                    "voucher_id": v.id,
                    "code": v.code,
                    "doc_no": v.doc_no,
                    "voucher_type": v.voucher_type,
                    "purchase_request_id": row.id,
                    "purchase_code": row.code,
                    "amount": int(v.amount_vnd),
                    # Số hoá đơn là thứ PHÂN BIỆT các đợt giao của cùng một đơn. Không có nó thì
                    # ba đợt hiện ba dòng trông y hệt nhau, không biết dòng nào là đợt nào.
                    "invoice_number": v.invoice_number,
                    "invoice_date": v.invoice_date,
                }
                if v.status == PAYMENT_VOUCHER_WAITING:
                    tre = (
                        (hom_nay - v.planned_payment_date).days
                        if v.planned_payment_date is not None and v.planned_payment_date < hom_nay
                        else 0
                    )
                    cho_chi.append(
                        {
                            **chung,
                            "planned_payment_date": v.planned_payment_date,
                            "overdue_days": tre,
                            # Ảnh chụp phiếu giao hàng / hoá đơn NCC. Đợt này chỉ CẢNH BÁO, không
                            # chặn — siết cứng khi chưa biết thực tế kẹt bao nhiêu là dễ tắc việc.
                            "has_attachment": bool(v.attachments),
                        }
                    )
                elif v.status == PAYMENT_VOUCHER_PAID:
                    ngay = self._ngay_chi(v)
                    if ngay >= moc_ky:
                        da_chi.append({**chung, "paid_date": ngay})
        # Sắp theo hạn trả, phiếu THIẾU hạn đẩy lên ĐẦU chứ không dìm xuống cuối: chúng là loại
        # không bao giờ vào được cột Quá hạn, phải đập vào mắt để còn đi đặt hạn.
        cho_chi.sort(key=lambda x: (x["planned_payment_date"] is not None, x["planned_payment_date"] or hom_nay))
        da_chi.sort(key=lambda x: x["paid_date"], reverse=True)
        return {
            "supplier_id": supplier_id,
            "supplier_name": supplier.name if supplier is not None else "(không rõ NCC)",
            "unrecorded": chua_vao_so,
            "waiting": cho_chi,
            "paid": da_chi,
            "period_months": PAYABLES_PERIOD_MONTHS,
            "all_history": all_history,
            "unrecorded_amount": sum(x["amount"] for x in chua_vao_so),
            "waiting_amount": sum(x["amount"] for x in cho_chi),
            "overdue_amount": sum(x["amount"] for x in cho_chi if x["overdue_days"] > 0),
            "paid_in_period": sum(x["amount"] for x in da_chi),
            "as_of": hom_nay,
        }

    # --- vouchers ---------------------------------------------------------

    def list_vouchers(self, **filters):
        rows, total, totals = self.repo.list_vouchers(**filters)
        return [self._voucher_out(row) for row in rows], total, totals

    def get_voucher(self, voucher_id: int):
        return self._voucher_out(self._voucher(voucher_id))

    def create_voucher(self, *, actor, purchase_request_id: int, **values):
        purchase = self._purchase(purchase_request_id)
        prepared = self._prepare_voucher(
            purchase, values, allow_pending_purchase=False, exclude_voucher_id=None
        )
        doc_no = self._next_voucher_doc_no()
        voucher = self._new_voucher(purchase, prepared, actor.id, doc_no=doc_no)
        saved = self.repo.save_voucher(voucher)
        self.audit.create(
            actor_user_id=actor.id,
            action="create_payment_voucher",
            target=f"payment_voucher:{saved.id}",
            detail=f"{saved.code} <- {purchase.code}",
        )
        return self._voucher_out(saved)

    # ĐÃ GỠ 04/08/2026: `approve_and_create_voucher()` — gộp duyệt PMH + lập phiếu chi vào một
    # thao tác. Tách vai: người đồng ý chi không được là người viết phiếu chi. Duyệt nay ở
    # `purchase_service.approve()` (có chốt chống tự duyệt), lập phiếu chi ở `create_voucher()`.

    def update_voucher(self, voucher_id: int, *, actor, purchase_request_id: int, **values):
        voucher = self._voucher(voucher_id)
        if voucher.status != PAYMENT_VOUCHER_WAITING:
            raise AccountingConflict("Chỉ chứng từ đang chờ chi mới được sửa.")
        if purchase_request_id != voucher.purchase_request_id:
            raise AccountingConflict("Không được đổi phiếu mua nguồn của chứng từ.")
        if values.get("voucher_type") != voucher.voucher_type:
            raise AccountingConflict("Không được đổi loại Phiếu chi/UNC sau khi đã lập.")
        purchase = self._purchase(purchase_request_id)
        prepared = self._prepare_voucher(
            purchase, values, allow_pending_purchase=False, exclude_voucher_id=voucher.id
        )
        self._apply_voucher(voucher, purchase, prepared)
        saved = self.repo.save_voucher(voucher)
        self.audit.create(
            actor_user_id=actor.id,
            action="update_payment_voucher",
            target=f"payment_voucher:{saved.id}",
            detail=saved.code,
        )
        return self._voucher_out(saved)

    def mark_paid(self, voucher_id: int, *, actor, bank_reference: str | None):
        voucher = self._voucher(voucher_id)
        if voucher.status != PAYMENT_VOUCHER_WAITING:
            raise AccountingConflict("Chỉ chứng từ đang chờ chi mới được xác nhận đã chi.")
        reference = _text(bank_reference, label="Mã giao dịch", max_length=64)
        if voucher.voucher_type == VOUCHER_BANK_TRANSFER and not reference:
            raise AccountingValidationError("UNC phải có mã giao dịch hoặc số báo nợ.")
        voucher.status = PAYMENT_VOUCHER_PAID
        voucher.bank_reference = reference
        voucher.paid_by_user_id = actor.id
        voucher.paid_at = _now()
        saved = self.repo.save_voucher(voucher)
        self.audit.create(
            actor_user_id=actor.id,
            action="mark_payment_voucher_paid",
            target=f"payment_voucher:{saved.id}",
            detail=saved.code,
        )
        return self._voucher_out(saved)

    def cancel_voucher(self, voucher_id: int, *, actor, reason: str):
        voucher = self._voucher(voucher_id)
        if voucher.status != PAYMENT_VOUCHER_WAITING:
            raise AccountingConflict("Chỉ chứng từ đang chờ chi mới được hủy.")
        cleaned_reason = _text(reason, label="Lý do hủy", required=True, max_length=2000)
        voucher.status = PAYMENT_VOUCHER_CANCELLED
        voucher.cancel_reason = cleaned_reason
        voucher.cancelled_by_user_id = actor.id
        voucher.cancelled_at = _now()
        saved = self.repo.save_voucher(voucher)
        self.audit.create(
            actor_user_id=actor.id,
            action="cancel_payment_voucher",
            target=f"payment_voucher:{saved.id}",
            detail=f"{saved.code}: {cleaned_reason}",
        )
        return self._voucher_out(saved)

    # --- payment receipts ---------------------------------------------------

    def list_receipts(
        self,
        *,
        q: str | None = None,
        status: str | None = None,
        payment_voucher_id: int | None = None,
        source_type: str | None = RECEIPT_SOURCE_PURCHASE,
        sort: str = "-created_at",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict], int]:
        # Màn Phiếu thu kế toán = phiếu thu MUA (purchase_refund). Phiếu thu cọc đơn bán quản ở màn
        # Đơn hàng (chung quyển sổ/dãy số PT nhưng tách VIEW). Truyền source_type=None để xem cả sổ.
        rows, total = self.repo.list_receipts(
            q=q,
            status=status,
            payment_voucher_id=payment_voucher_id,
            source_type=source_type,
            sort=sort,
            page=page,
            size=size,
        )
        return [self._receipt_out(row) for row in rows], total

    def create_receipt(self, payment_voucher_id: int, *, actor, **values):
        voucher = self._voucher(payment_voucher_id)
        if voucher.status != PAYMENT_VOUCHER_PAID:
            raise AccountingConflict("Chỉ Phiếu chi/UNC đã chi mới được lập phiếu thu.")
        prepared = self._prepare_receipt(voucher, values, exclude_receipt_id=None)
        # Cấp số trước khi chạm ORM object — increment_and_get() tự commit (xem
        # _next_voucher_doc_no).
        doc_no = self.sequences.generate_flat_code(SEQ_DOC_TYPE_PAYMENT_RECEIPT)
        receipt = PaymentReceipt(
            code=self._new_receipt_code(),
            doc_no=doc_no,
            payment_voucher_id=voucher.id,
            purchase_request_id=voucher.purchase_request_id,
            status=PAYMENT_RECEIPT_WAITING,
            created_by_user_id=actor.id,
        )
        self._apply_receipt(receipt, voucher, prepared)
        saved = self.repo.save_receipt(receipt)
        self.audit.create(
            actor_user_id=actor.id,
            action="create_payment_receipt",
            target=f"payment_receipt:{saved.id}",
            detail=f"{saved.code} <- {voucher.code}",
        )
        return self._receipt_out(saved)

    def create_order_receipt(
        self,
        *,
        order_id: int,
        order_no: str,
        customer_name: str | None,
        actor,
        receipt_method: str,
        amount: int,
        receipt_date,
        content: str | None = None,
        bank_reference: str | None = None,
        company_bank_account_id: int | None = None,
        note: str | None = None,
        mark_received: bool = True,
    ) -> dict:
        """Sinh phiếu thu 01-TT cho CỌC đơn bán — dùng CHUNG bảng payment_receipts + CHUNG dãy
        số PT với phiếu thu mua hàng (1 quyển sổ quỹ). Người nộp = khách, không cap theo phiếu chi.
        `mark_received=True` (mặc định) → phiếu ở trạng thái đã thu ngay (Kế toán ghi khi tiền đã
        về) → cổng chốt đơn đếm ngay. Định khoản 01-TT: Nợ 111/112 · Có 131 (phải thu khách)."""
        if receipt_method not in PAYMENT_VOUCHER_TYPES:
            raise AccountingValidationError("Hình thức thu không hợp lệ.")
        amount = int(amount or 0)
        if amount <= 0:
            raise AccountingValidationError("Số tiền thu phải lớn hơn 0.")
        company_account = None
        reference = _text(bank_reference, label="Mã giao dịch", max_length=64)
        # TK công ty nhận là TÙY CHỌN với cọc đơn bán (bank_reference đủ vết); nếu có thì kiểm hợp lệ.
        if receipt_method == VOUCHER_BANK_TRANSFER and company_bank_account_id:
            company_account = self.repo.get_company_account(int(company_bank_account_id))
            if company_account is None or not company_account.is_active:
                raise AccountingValidationError("Tài khoản công ty không hợp lệ.")
            if company_account.currency != "VND":
                raise AccountingValidationError("Cọc đơn bán chỉ nhận VND.")
        doc_no = self.sequences.generate_flat_code(SEQ_DOC_TYPE_PAYMENT_RECEIPT)
        receipt = PaymentReceipt(
            code=self._new_receipt_code(),
            doc_no=doc_no,
            source_type=RECEIPT_SOURCE_ORDER,
            order_id=order_id,
            order_no_snapshot=order_no,
            customer_name_snapshot=customer_name,
            payer_name=(customer_name or "Khách hàng"),
            receipt_method=receipt_method,
            receipt_date=receipt_date,
            amount=amount,
            amount_vnd=amount,
            currency="VND",
            exchange_rate=1,
            content=_text(content, label="Nội dung thu", max_length=500) or f"Thu cọc đơn {order_no}",
            debit_account=("1121" if receipt_method == VOUCHER_BANK_TRANSFER else "1111"),
            credit_account="131",
            bank_reference=reference,
            company_bank_account_id=(company_account.id if company_account else None),
            company_account_holder_snapshot=(company_account.account_holder if company_account else None),
            company_account_number_snapshot=(company_account.account_number if company_account else None),
            company_bank_name_snapshot=(company_account.bank_name if company_account else None),
            company_bank_branch_snapshot=(company_account.bank_branch if company_account else None),
            note=_text(note, label="Ghi chú", max_length=2000),
            status=PAYMENT_RECEIPT_WAITING,
            created_by_user_id=actor.id,
        )
        if mark_received:
            receipt.status = PAYMENT_RECEIPT_RECEIVED
            receipt.received_by_user_id = actor.id
            receipt.received_at = _now()
        saved = self.repo.save_receipt(receipt)
        self.audit.create(
            actor_user_id=actor.id,
            action="create_order_receipt",
            target=f"payment_receipt:{saved.id}",
            detail=f"{saved.code} <- đơn {order_no}",
        )
        return self._receipt_out(saved)

    def received_sum_for_order(self, order_id: int) -> int:
        """Σ số tiền các phiếu thu ĐÃ THU (received) của một đơn — cổng chốt đơn đọc số này."""
        return self.repo.receipt_received_sum_for_order(order_id)

    def cancel_order_receipt(self, receipt_id: int, *, actor, reason: str):
        """Hủy phiếu thu CỌC đơn bán — cho hủy cả khi ĐÃ THU (ghi nhầm), khác phiếu thu mua (chỉ
        hủy chờ-thu). Không xóa trắng: giữ vết + số PT trong quyển sổ."""
        receipt = self._receipt(receipt_id)
        if receipt.source_type != RECEIPT_SOURCE_ORDER:
            raise AccountingConflict("Không phải phiếu thu cọc đơn bán.")
        if receipt.status == PAYMENT_RECEIPT_CANCELLED:
            raise AccountingConflict("Phiếu thu đã hủy.")
        cleaned = _text(reason, label="Lý do hủy", required=True, max_length=2000)
        receipt.status = PAYMENT_RECEIPT_CANCELLED
        receipt.cancel_reason = cleaned
        receipt.cancelled_by_user_id = actor.id
        receipt.cancelled_at = _now()
        saved = self.repo.save_receipt(receipt)
        self.audit.create(
            actor_user_id=actor.id, action="cancel_order_receipt",
            target=f"payment_receipt:{saved.id}", detail=f"{saved.code}: {cleaned}",
        )
        return self._receipt_out(saved)

    def update_receipt(self, receipt_id: int, *, actor, **values):
        receipt = self._receipt(receipt_id)
        if receipt.status != PAYMENT_RECEIPT_WAITING:
            raise AccountingConflict("Chỉ phiếu thu đang chờ thu mới được sửa.")
        if receipt.source_type == RECEIPT_SOURCE_ORDER:
            raise AccountingConflict("Phiếu thu cọc đơn bán sửa ở màn Đơn hàng.")
        voucher = receipt.payment_voucher
        prepared = self._prepare_receipt(voucher, values, exclude_receipt_id=receipt.id)
        self._apply_receipt(receipt, voucher, prepared)
        saved = self.repo.save_receipt(receipt)
        self.audit.create(
            actor_user_id=actor.id,
            action="update_payment_receipt",
            target=f"payment_receipt:{saved.id}",
            detail=saved.code,
        )
        return self._receipt_out(saved)

    def mark_receipt_received(self, receipt_id: int, *, actor, bank_reference: str | None):
        receipt = self._receipt(receipt_id)
        if receipt.status != PAYMENT_RECEIPT_WAITING:
            raise AccountingConflict("Chỉ phiếu thu đang chờ thu mới được xác nhận đã thu.")
        reference = _text(bank_reference, label="Mã giao dịch", max_length=64)
        if receipt.receipt_method == VOUCHER_BANK_TRANSFER and not reference:
            raise AccountingValidationError(
                "Thu qua ngân hàng phải có mã giao dịch hoặc số báo có."
            )
        receipt.status = PAYMENT_RECEIPT_RECEIVED
        receipt.bank_reference = reference
        receipt.received_by_user_id = actor.id
        receipt.received_at = _now()
        saved = self.repo.save_receipt(receipt)
        self.audit.create(
            actor_user_id=actor.id,
            action="mark_payment_receipt_received",
            target=f"payment_receipt:{saved.id}",
            detail=saved.code,
        )
        return self._receipt_out(saved)

    def cancel_receipt(self, receipt_id: int, *, actor, reason: str):
        receipt = self._receipt(receipt_id)
        if receipt.status != PAYMENT_RECEIPT_WAITING:
            raise AccountingConflict("Chỉ phiếu thu đang chờ thu mới được hủy.")
        cleaned_reason = _text(reason, label="Lý do hủy", required=True, max_length=2000)
        receipt.status = PAYMENT_RECEIPT_CANCELLED
        receipt.cancel_reason = cleaned_reason
        receipt.cancelled_by_user_id = actor.id
        receipt.cancelled_at = _now()
        saved = self.repo.save_receipt(receipt)
        self.audit.create(
            actor_user_id=actor.id,
            action="cancel_payment_receipt",
            target=f"payment_receipt:{saved.id}",
            detail=f"{saved.code}: {cleaned_reason}",
        )
        return self._receipt_out(saved)

    def _prepare_receipt(
        self, voucher: PaymentVoucher, values: dict, *, exclude_receipt_id: int | None
    ) -> dict:
        receipt_method = (values.get("receipt_method") or "").strip()
        if receipt_method not in PAYMENT_VOUCHER_TYPES:
            raise AccountingValidationError("Hình thức thu không hợp lệ.")
        payer_name = _text(
            values.get("payer_name"), label="Người nộp tiền", required=True, max_length=255
        )

        amount = int(values.get("amount") or 0)
        if amount <= 0:
            raise AccountingValidationError("Số tiền thu phải lớn hơn 0.")
        # Thu bằng đúng loại tiền của phiếu chi gốc — không nhận currency từ payload.
        currency = voucher.currency
        exchange_rate = float(values.get("exchange_rate") or voucher.exchange_rate)
        if exchange_rate <= 0:
            raise AccountingValidationError("Tỷ giá phải lớn hơn 0.")
        if currency == "VND" and exchange_rate != 1:
            raise AccountingValidationError("Tỷ giá của VND phải bằng 1.")
        amount_vnd = int(
            (Decimal(amount) * Decimal(str(exchange_rate))).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )
        reserved = self.repo.receipt_reserved_amount(voucher.id, exclude_id=exclude_receipt_id)
        remaining = int(voucher.amount_vnd) - reserved
        if amount_vnd > remaining:
            raise AccountingValidationError(
                f"Số tiền thu vượt quá phần còn được thu ({remaining:,} đ)."
            )
        content = _text(values.get("content"), label="Nội dung thu", required=True, max_length=500)

        company_account = None
        if receipt_method == VOUCHER_BANK_TRANSFER:
            account_id = values.get("company_bank_account_id")
            company_account = (
                self.repo.get_company_account(int(account_id)) if account_id else None
            )
            if company_account is None or not company_account.is_active:
                raise AccountingValidationError(
                    "Vui lòng chọn tài khoản công ty đang hoạt động."
                )
            if company_account.currency != currency:
                raise AccountingValidationError(
                    "Loại tiền phiếu thu phải khớp tài khoản nhận."
                )

        return {
            "payer_name": payer_name,
            "payer_address": _text(
                values.get("payer_address"), label="Địa chỉ người nộp", max_length=500
            ),
            "receipt_method": receipt_method,
            "receipt_date": values.get("receipt_date"),
            "debit_account": _text(values.get("debit_account"), label="Tài khoản Nợ", max_length=64),
            "credit_account": _text(values.get("credit_account"), label="Tài khoản Có", max_length=64),
            "amount": amount,
            "amount_vnd": amount_vnd,
            "currency": currency,
            "exchange_rate": exchange_rate,
            "content": content,
            "note": _text(values.get("note"), label="Ghi chú", max_length=2000),
            "company_account": company_account,
        }

    def _apply_receipt(
        self, receipt: PaymentReceipt, voucher: PaymentVoucher, prepared: dict
    ) -> None:
        account = prepared.pop("company_account")
        for key, value in prepared.items():
            setattr(receipt, key, value)
        receipt.company_bank_account_id = account.id if account else None
        receipt.voucher_code_snapshot = voucher.code
        receipt.purchase_code_snapshot = voucher.source_code_snapshot
        receipt.supplier_name_snapshot = voucher.supplier_name_snapshot
        receipt.company_account_holder_snapshot = account.account_holder if account else None
        receipt.company_account_number_snapshot = account.account_number if account else None
        receipt.company_bank_name_snapshot = account.bank_name if account else None
        receipt.company_bank_branch_snapshot = account.bank_branch if account else None

    def _new_receipt_code(self) -> str:
        alphabet = string.ascii_uppercase + string.digits
        date_part = _now().strftime("%y%m%d")
        for _ in range(30):
            suffix = "".join(secrets.choice(alphabet) for _ in range(4))
            code = f"PT-{date_part}-{suffix}"
            if self.repo.get_receipt_by_code(code) is None:
                return code
        raise AccountingConflict("Không sinh được mã chứng từ duy nhất, vui lòng thử lại.")

    def _receipt(self, receipt_id: int) -> PaymentReceipt:
        row = self.repo.get_receipt(receipt_id)
        if row is None:
            raise AccountingNotFound("Không tìm thấy phiếu thu.")
        return row

    def _receipt_out(self, row: PaymentReceipt) -> dict:
        return {
            "id": row.id,
            "code": row.code,
            "doc_no": row.doc_no,
            "source_type": row.source_type,
            "order_id": row.order_id,
            "order_no": row.order_no_snapshot,
            "customer_name": row.customer_name_snapshot,
            "payment_voucher_id": row.payment_voucher_id,
            "payment_voucher_code": row.voucher_code_snapshot,
            "purchase_request_id": row.purchase_request_id,
            "purchase_request_code": row.purchase_code_snapshot,
            "supplier_name": row.supplier_name_snapshot,
            "payer_name": row.payer_name,
            "payer_address": row.payer_address,
            "debit_account": row.debit_account,
            "credit_account": row.credit_account,
            "receipt_method": row.receipt_method,
            "status": row.status,
            "receipt_date": row.receipt_date,
            "amount": int(row.amount),
            "amount_vnd": int(row.amount_vnd),
            "currency": row.currency,
            "exchange_rate": float(row.exchange_rate),
            "content": row.content,
            "company_bank_account_id": row.company_bank_account_id,
            "company_account_holder": row.company_account_holder_snapshot,
            "company_account_number": row.company_account_number_snapshot,
            "company_bank_name": row.company_bank_name_snapshot,
            "company_bank_branch": row.company_bank_branch_snapshot,
            "bank_reference": row.bank_reference,
            "created_by_user_id": row.created_by_user_id,
            "created_by_name": self._user_name(row.created_by_user_id),
            "received_by_user_id": row.received_by_user_id,
            "received_by_name": self._user_name(row.received_by_user_id),
            "received_at": row.received_at,
            "cancelled_by_user_id": row.cancelled_by_user_id,
            "cancelled_by_name": self._user_name(row.cancelled_by_user_id),
            "cancelled_at": row.cancelled_at,
            "cancel_reason": row.cancel_reason,
            "note": row.note,
            "attachment_count": len(row.attachments),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    # --- voucher attachments -----------------------------------------------

    def list_voucher_attachments(self, voucher_id: int) -> list[dict]:
        self._voucher(voucher_id)
        return [self._attachment_out(row) for row in self.repo.list_attachments(voucher_id)]

    def add_voucher_attachment(
        self,
        voucher_id: int,
        *,
        actor,
        file_name: str | None,
        content_type: str | None,
        data: bytes,
    ) -> dict:
        voucher = self._voucher(voucher_id)
        if voucher.status == PAYMENT_VOUCHER_CANCELLED:
            raise AccountingConflict("Chứng từ đã hủy — không đính kèm thêm.")
        ct = (content_type or "").lower()
        if not (ct.startswith("image/") or ct == "application/pdf"):
            raise AccountingValidationError("Chỉ nhận ảnh (image/*) hoặc PDF.")
        if not data:
            raise AccountingValidationError("Tệp rỗng.")
        if len(data) > MAX_ATTACHMENT_BYTES:
            raise AccountingValidationError("Tệp vượt quá 10 MB.")
        if len(voucher.attachments) >= MAX_ATTACHMENTS_PER_VOUCHER:
            raise AccountingValidationError(
                f"Mỗi chứng từ tối đa {MAX_ATTACHMENTS_PER_VOUCHER} file đính kèm."
            )
        key, safe_name = make_key(_ATTACHMENT_SUBDIR, voucher.id, file_name)
        get_storage().save(key, data, content_type)
        attachment = PaymentVoucherAttachment(
            payment_voucher_id=voucher.id,
            file_name=safe_name,
            file_url=url_from_key(key),
            file_type=content_type,
            uploaded_by=actor.id,
        )
        saved = self.repo.save_attachment(attachment)
        self.audit.create(
            actor_user_id=actor.id,
            action="upload_payment_voucher_attachment",
            target=f"payment_voucher:{voucher.id}",
            detail=f"{voucher.code} + {safe_name}",
        )
        return self._attachment_out(saved)

    def delete_voucher_attachment(self, voucher_id: int, attachment_id: int, *, actor) -> None:
        voucher = self._voucher(voucher_id)
        attachment = self.repo.get_attachment(attachment_id)
        if attachment is None or attachment.payment_voucher_id != voucher_id:
            raise AccountingNotFound("Không tìm thấy file đính kèm.")
        _delete_stored_file(attachment.file_url)
        file_name = attachment.file_name
        self.repo.delete_attachment(attachment)
        self.audit.create(
            actor_user_id=actor.id,
            action="delete_payment_voucher_attachment",
            target=f"payment_voucher:{voucher.id}",
            detail=f"{voucher.code} - {file_name}",
        )

    @staticmethod
    def _attachment_out(row: PaymentVoucherAttachment) -> dict:
        return {
            "id": row.id,
            "payment_voucher_id": row.payment_voucher_id,
            "file_name": row.file_name,
            "file_url": row.file_url,
            "file_type": row.file_type,
            "uploaded_by": row.uploaded_by,
            "uploaded_at": row.uploaded_at,
        }

    # --- receipt attachments -----------------------------------------------

    def list_receipt_attachments(self, receipt_id: int) -> list[dict]:
        self._receipt(receipt_id)
        return [
            self._receipt_attachment_out(row)
            for row in self.repo.list_receipt_attachments(receipt_id)
        ]

    def add_receipt_attachment(
        self,
        receipt_id: int,
        *,
        actor,
        file_name: str | None,
        content_type: str | None,
        data: bytes,
    ) -> dict:
        receipt = self._receipt(receipt_id)
        if receipt.status == PAYMENT_RECEIPT_CANCELLED:
            raise AccountingConflict("Phiếu thu đã hủy — không đính kèm thêm.")
        ct = (content_type or "").lower()
        if not (ct.startswith("image/") or ct == "application/pdf"):
            raise AccountingValidationError("Chỉ nhận ảnh (image/*) hoặc PDF.")
        if not data:
            raise AccountingValidationError("Tệp rỗng.")
        if len(data) > MAX_ATTACHMENT_BYTES:
            raise AccountingValidationError("Tệp vượt quá 10 MB.")
        if len(receipt.attachments) >= MAX_ATTACHMENTS_PER_VOUCHER:
            raise AccountingValidationError(
                f"Mỗi phiếu thu tối đa {MAX_ATTACHMENTS_PER_VOUCHER} file đính kèm."
            )
        key, safe_name = make_key(_RECEIPT_ATTACHMENT_SUBDIR, receipt.id, file_name)
        get_storage().save(key, data, content_type)
        attachment = PaymentReceiptAttachment(
            payment_receipt_id=receipt.id,
            file_name=safe_name,
            file_url=url_from_key(key),
            file_type=content_type,
            uploaded_by=actor.id,
        )
        saved = self.repo.save_receipt_attachment(attachment)
        self.audit.create(
            actor_user_id=actor.id,
            action="upload_payment_receipt_attachment",
            target=f"payment_receipt:{receipt.id}",
            detail=f"{receipt.code} + {safe_name}",
        )
        return self._receipt_attachment_out(saved)

    def delete_receipt_attachment(self, receipt_id: int, attachment_id: int, *, actor) -> None:
        receipt = self._receipt(receipt_id)
        attachment = self.repo.get_receipt_attachment(attachment_id)
        if attachment is None or attachment.payment_receipt_id != receipt_id:
            raise AccountingNotFound("Không tìm thấy file đính kèm.")
        _delete_stored_file(attachment.file_url)
        file_name = attachment.file_name
        self.repo.delete_receipt_attachment(attachment)
        self.audit.create(
            actor_user_id=actor.id,
            action="delete_payment_receipt_attachment",
            target=f"payment_receipt:{receipt.id}",
            detail=f"{receipt.code} - {file_name}",
        )

    @staticmethod
    def _receipt_attachment_out(row: PaymentReceiptAttachment) -> dict:
        return {
            "id": row.id,
            "payment_receipt_id": row.payment_receipt_id,
            "file_name": row.file_name,
            "file_url": row.file_url,
            "file_type": row.file_type,
            "uploaded_by": row.uploaded_by,
            "uploaded_at": row.uploaded_at,
        }

    # --- validation/output ------------------------------------------------

    def _clean_bank_account(self, values: dict) -> dict:
        cleaned = {
            "account_holder": _text(values.get("account_holder"), label="Chủ tài khoản", required=True, max_length=255),
            "account_number": _text(values.get("account_number"), label="Số tài khoản", required=True, max_length=64),
            "bank_name": _text(values.get("bank_name"), label="Ngân hàng", required=True, max_length=255),
            "bank_branch": _text(values.get("bank_branch"), label="Chi nhánh ngân hàng", required=True, max_length=255),
            "currency": (values.get("currency") or "VND").strip().upper(),
            "is_default": bool(values.get("is_default")),
            "is_active": bool(values.get("is_active", True)),
            "note": _text(values.get("note"), label="Ghi chú", max_length=2000),
        }
        if len(cleaned["currency"]) != 3:
            raise AccountingValidationError("Loại tiền phải gồm 3 ký tự, ví dụ VND.")
        if cleaned["is_default"] and not cleaned["is_active"]:
            raise AccountingValidationError("Tài khoản mặc định phải đang hoạt động.")
        return cleaned

    def _prepare_voucher(
        self,
        purchase: PurchaseRequest,
        values: dict,
        *,
        allow_pending_purchase: bool,
        exclude_voucher_id: int | None,
    ) -> dict:
        allowed_statuses = (PR_APPROVED, PR_PURCHASED, PR_RECEIVED)
        if purchase.status not in allowed_statuses and not (
            allow_pending_purchase and purchase.status == PR_PENDING
        ):
            raise AccountingConflict("Phiếu mua chưa đủ điều kiện lập Phiếu chi/UNC.")
        if purchase.supplier_id is None or purchase.supplier is None:
            raise AccountingValidationError("Phiếu mua chưa có nhà cung cấp.")

        voucher_type = (values.get("voucher_type") or "").strip()
        if voucher_type not in PAYMENT_VOUCHER_TYPES:
            raise AccountingValidationError("Loại chứng từ không hợp lệ.")
        stage = (values.get("payment_stage") or "").strip()
        if stage not in PAYMENT_STAGES:
            raise AccountingValidationError("Đợt thanh toán không hợp lệ.")
        amount = int(values.get("amount") or 0)
        if amount <= 0:
            raise AccountingValidationError("Số tiền thanh toán phải lớn hơn 0.")
        currency = (values.get("currency") or "VND").strip().upper()
        if len(currency) != 3:
            raise AccountingValidationError("Loại tiền phải gồm 3 ký tự, ví dụ VND.")
        exchange_rate = float(values.get("exchange_rate") or 0)
        if exchange_rate <= 0:
            raise AccountingValidationError("Tỷ giá phải lớn hơn 0.")
        if currency == "VND" and exchange_rate != 1:
            raise AccountingValidationError("Tỷ giá của VND phải bằng 1.")
        amount_vnd = int(
            (Decimal(amount) * Decimal(str(exchange_rate))).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )
        tran = self._tran_lap_phieu(purchase)
        reserved = self.repo.reserved_amount(purchase.id, exclude_id=exclude_voucher_id)
        available = max(0, tran - reserved)
        if amount_vnd > available:
            raise AccountingValidationError(
                f"Số tiền quy đổi vượt quá số còn được phép lập ({available:,} đ)."
            )
        content = _text(values.get("content"), label="Nội dung chi", required=True, max_length=500)

        company_account = None
        supplier_account = None
        cash_recipient_name = _text(
            values.get("cash_recipient_name"), label="Người nhận tiền", max_length=255
        )
        bank_fee_bearer = _text(
            values.get("bank_fee_bearer"), label="Bên chịu phí", max_length=16
        )
        if voucher_type == VOUCHER_CASH:
            if not cash_recipient_name:
                raise AccountingValidationError("Phiếu chi phải có người nhận tiền.")
        else:
            company_id = values.get("company_bank_account_id")
            supplier_account_id = values.get("supplier_bank_account_id")
            company_account = self.repo.get_company_account(int(company_id)) if company_id else None
            supplier_account = self.repo.get_supplier_account(int(supplier_account_id)) if supplier_account_id else None
            if company_account is None or not company_account.is_active:
                raise AccountingValidationError("Vui lòng chọn tài khoản công ty đang hoạt động.")
            if supplier_account is None or not supplier_account.is_active:
                raise AccountingValidationError("Vui lòng chọn tài khoản nhà cung cấp đang hoạt động.")
            if supplier_account.supplier_id != purchase.supplier_id:
                raise AccountingValidationError("Tài khoản thụ hưởng không thuộc nhà cung cấp của PMH.")
            if company_account.currency != currency or supplier_account.currency != currency:
                raise AccountingValidationError("Loại tiền của chứng từ phải khớp với hai tài khoản ngân hàng.")
            bank_fee_bearer = bank_fee_bearer or BANK_FEE_PAYER
            if bank_fee_bearer not in BANK_FEE_BEARERS:
                raise AccountingValidationError("Bên chịu phí ngân hàng không hợp lệ.")

        # HẠN TRẢ bắt buộc (chủ 05/08/2026). Trước đó để trống được, mà cột "Quá hạn" ở màn Công nợ
        # so `hạn trả < hôm nay` ⇒ phiếu thiếu hạn KHÔNG BAO GIỜ vào cột đó. Kế toán nhìn bảng thấy
        # "Quá hạn 0đ" rồi yên tâm trong khi có phiếu trễ cả tháng — đúng bệnh giấu nợ, chỉ khác chỗ.
        # Phiếu cũ đã lỡ tạo thiếu hạn thì giữ nguyên, màn Công nợ gắn badge "Chưa đặt hạn" để lôi ra.
        han_tra = values.get("planned_payment_date")
        if han_tra is None:
            raise AccountingValidationError(
                "Phải có hạn trả tiền — không có hạn thì phiếu này không bao giờ bị báo quá hạn."
            )
        ngay_ct = values.get("voucher_date")
        hom_nay = _business_today()
        # CỐ Ý KHÔNG chặn ngày quá khứ. Hoá đơn về muộn là chuyện thường: chi phát sinh 28/7, hoá
        # đơn về 5/8 ⇒ phiếu phải mang ngày 28/7 mới vào đúng kỳ kế toán. Hạn trả quá khứ cũng hợp
        # lệ — nhập phiếu cho khoản ĐÃ trễ thì phải giữ đúng ngày thật để nó hiện đỏ ngay; ép sang
        # tương lai là làm giả nợ.
        #
        # Chỉ chặn ba thứ VÔ LÝ:
        if ngay_ct is not None and ngay_ct > hom_nay:
            raise AccountingValidationError(
                "Ngày chứng từ không được ở tương lai — kiểm lại năm xem có gõ nhầm không."
            )
        ngay_hd = values.get("invoice_date")
        if ngay_hd is not None and ngay_hd > hom_nay:
            raise AccountingValidationError("Ngày hóa đơn không được ở tương lai.")
        if ngay_ct is not None and han_tra < ngay_ct:
            # Hạn trả trước ngày lập chứng từ là vô nghĩa, và nó bơm số rác thẳng vào cột "Quá hạn":
            # phiếu vừa tạo xong đã báo trễ mấy chục ngày.
            raise AccountingValidationError(
                "Hạn trả tiền không được trước ngày chứng từ."
            )
        return {
            "voucher_type": voucher_type,
            "payment_stage": stage,
            "voucher_date": values.get("voucher_date"),
            "planned_payment_date": han_tra,
            "amount": amount,
            "amount_vnd": amount_vnd,
            "currency": currency,
            "exchange_rate": exchange_rate,
            "content": content,
            "invoice_number": _text(values.get("invoice_number"), label="Số hóa đơn", max_length=64),
            "invoice_date": values.get("invoice_date"),
            "contract_number": _text(values.get("contract_number"), label="Số hợp đồng", max_length=64),
            "company_account": company_account,
            "supplier_account": supplier_account,
            "cash_recipient_name": cash_recipient_name,
            "cash_recipient_address": _text(values.get("cash_recipient_address"), label="Địa chỉ người nhận", max_length=500),
            "cash_recipient_identity": _text(values.get("cash_recipient_identity"), label="Giấy tờ người nhận", max_length=64),
            "bank_fee_bearer": bank_fee_bearer,
            "debit_account": _text(values.get("debit_account"), label="Tài khoản Nợ", max_length=64),
            "credit_account": _text(values.get("credit_account"), label="Tài khoản Có", max_length=64),
            "note": _text(values.get("note"), label="Ghi chú", max_length=2000),
        }

    def _next_voucher_doc_no(self) -> str:
        """Số IN trên mẫu 02-TT (PC00445) — chung bộ đếm cho tiền mặt lẫn UNC.

        LƯU Ý: gọi hàm này SAU khi validate xong và TRƯỚC mọi mutation ORM — nó commit.
        """
        return self.sequences.generate_flat_code(SEQ_DOC_TYPE_PAYMENT_VOUCHER)

    def _new_voucher(
        self, purchase: PurchaseRequest, prepared: dict, actor_id: int, *, doc_no: str | None = None
    ) -> PaymentVoucher:
        voucher = PaymentVoucher(
            code=self._new_voucher_code(prepared["voucher_type"]),
            doc_no=doc_no,
            purchase_request_id=purchase.id,
            supplier_id=purchase.supplier_id,
            status=PAYMENT_VOUCHER_WAITING,
            created_by_user_id=actor_id,
        )
        self._apply_voucher(voucher, purchase, prepared)
        return voucher

    def _apply_voucher(self, voucher: PaymentVoucher, purchase: PurchaseRequest, prepared: dict) -> None:
        company = prepared.pop("company_account")
        beneficiary = prepared.pop("supplier_account")
        for key, value in prepared.items():
            setattr(voucher, key, value)
        voucher.company_bank_account_id = company.id if company else None
        voucher.supplier_bank_account_id = beneficiary.id if beneficiary else None
        voucher.source_code_snapshot = purchase.code
        voucher.supplier_id = purchase.supplier_id
        voucher.supplier_name_snapshot = purchase.supplier.name
        voucher.supplier_tax_code_snapshot = purchase.supplier.tax_code
        voucher.supplier_address_snapshot = purchase.supplier.address
        voucher.company_account_holder_snapshot = company.account_holder if company else None
        voucher.company_account_number_snapshot = company.account_number if company else None
        voucher.company_bank_name_snapshot = company.bank_name if company else None
        voucher.company_bank_branch_snapshot = company.bank_branch if company else None
        voucher.beneficiary_account_holder_snapshot = beneficiary.account_holder if beneficiary else None
        voucher.beneficiary_account_number_snapshot = beneficiary.account_number if beneficiary else None
        voucher.beneficiary_bank_name_snapshot = beneficiary.bank_name if beneficiary else None
        voucher.beneficiary_bank_branch_snapshot = beneficiary.bank_branch if beneficiary else None

    def _new_voucher_code(self, voucher_type: str) -> str:
        prefix = "PC" if voucher_type == VOUCHER_CASH else "UNC"
        alphabet = string.ascii_uppercase + string.digits
        date_part = _now().strftime("%y%m%d")
        for _ in range(30):
            suffix = "".join(secrets.choice(alphabet) for _ in range(4))
            code = f"{prefix}-{date_part}-{suffix}"
            if self.repo.get_voucher_by_code(code) is None:
                return code
        raise AccountingConflict("Không sinh được mã chứng từ duy nhất, vui lòng thử lại.")

    def _purchase(self, request_id: int) -> PurchaseRequest:
        row = self.purchases.get_by_id(request_id)
        if row is None:
            raise AccountingNotFound("Không tìm thấy phiếu mua hàng.")
        return row

    def _voucher(self, voucher_id: int) -> PaymentVoucher:
        row = self.repo.get_voucher(voucher_id)
        if row is None:
            raise AccountingNotFound("Không tìm thấy Phiếu chi/UNC.")
        return row

    @staticmethod
    def _purchase_total(purchase: PurchaseRequest) -> int:
        """Giá trị ĐƠN ĐẶT — con số in trên phiếu mua. Chỉ để HIỂN THỊ.

        Trần lập phiếu chi KHÔNG dùng hàm này (xem `_tran_lap_phieu`): hàng về thiếu thì trần phải
        tụt theo, còn số trên đơn thì không đổi."""
        return purchase_money(purchase)["total"]

    @staticmethod
    def _tran_lap_phieu(purchase: PurchaseRequest) -> int:
        """Số tối đa được phép lập phiếu chi cho phiếu mua này.

        Hàng ĐÃ VỀ ⇒ theo giá trị **thực nhận**: NCC giao 800/1000 tờ thì không cho viết phiếu đủ
        1000, nếu không màn Công nợ báo nợ 80% trong khi phiếu chi viết 100% — hai con số chửi nhau
        và kế toán không biết tin số nào. Hàng CHƯA về ⇒ vẫn theo giá trị đơn, để còn đặt cọc /
        ứng trước được."""
        return purchase_money(purchase)["tran"]

    def _supplier_account_out(self, row: SupplierBankAccount) -> dict:
        return {
            "id": row.id,
            "supplier_id": row.supplier_id,
            "supplier_name": row.supplier.name if row.supplier else None,
            "account_holder": row.account_holder,
            "account_number": row.account_number,
            "bank_name": row.bank_name,
            "bank_branch": row.bank_branch,
            "currency": row.currency,
            "is_default": row.is_default,
            "is_active": row.is_active,
            "note": row.note,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    def _user_name(self, user_id: int | None) -> str | None:
        if user_id is None:
            return None
        user = self.users.get_by_id(user_id)
        return user.name if user else None

    def _voucher_out(self, row: PaymentVoucher) -> dict:
        purchase = row.purchase_request
        source_codes = [
            link.department_request.code if link.department_request else link.source_code_snapshot
            for link in purchase.sources
        ] if purchase else []
        purchase_total = self._purchase_total(purchase) if purchase else None
        # Tổng ĐÃ CHI của cả PMH (mọi phiếu chi anh em) — hiện trên dải nhóm.
        purchase_paid_amount = (
            sum(
                int(sibling.amount_vnd)
                for sibling in purchase.payment_vouchers
                if sibling.status == PAYMENT_VOUCHER_PAID
            )
            if purchase
            else None
        )
        receipt_received_amount = sum(
            int(receipt.amount_vnd)
            for receipt in row.receipts
            if receipt.status == PAYMENT_RECEIPT_RECEIVED
        )
        receipt_pending_amount = sum(
            int(receipt.amount_vnd)
            for receipt in row.receipts
            if receipt.status == PAYMENT_RECEIPT_WAITING
        )
        return {
            "id": row.id,
            "code": row.code,
            "doc_no": row.doc_no,
            "debit_account": row.debit_account,
            "credit_account": row.credit_account,
            "receipt_received_amount": receipt_received_amount,
            "receipt_pending_amount": receipt_pending_amount,
            "attachment_count": len(row.attachments),
            "purchase_request_id": row.purchase_request_id,
            "purchase_request_code": purchase.code if purchase else row.source_code_snapshot,
            "purchase_request_total": purchase_total,
            "purchase_paid_amount": purchase_paid_amount,
            # Người phụ trách mua (lập PMH) — mặc định "Người nộp tiền" của phiếu thu.
            "purchase_created_by_name": (
                self._user_name(purchase.created_by_user_id) if purchase else None
            ),
            "source_request_codes": source_codes,
            "supplier_id": row.supplier_id,
            "supplier_name": row.supplier_name_snapshot,
            "supplier_tax_code": row.supplier_tax_code_snapshot,
            "supplier_address": row.supplier_address_snapshot,
            "voucher_type": row.voucher_type,
            "payment_stage": row.payment_stage,
            "status": row.status,
            "voucher_date": row.voucher_date,
            "planned_payment_date": row.planned_payment_date,
            "amount": int(row.amount),
            "amount_vnd": int(row.amount_vnd),
            "currency": row.currency,
            "exchange_rate": float(row.exchange_rate),
            "content": row.content,
            "invoice_number": row.invoice_number,
            "invoice_date": row.invoice_date,
            "contract_number": row.contract_number,
            "company_bank_account_id": row.company_bank_account_id,
            "supplier_bank_account_id": row.supplier_bank_account_id,
            "cash_recipient_name": row.cash_recipient_name,
            "cash_recipient_address": row.cash_recipient_address,
            "cash_recipient_identity": row.cash_recipient_identity,
            "bank_fee_bearer": row.bank_fee_bearer,
            "bank_reference": row.bank_reference,
            "company_account_holder": row.company_account_holder_snapshot,
            "company_account_number": row.company_account_number_snapshot,
            "company_bank_name": row.company_bank_name_snapshot,
            "company_bank_branch": row.company_bank_branch_snapshot,
            "beneficiary_account_holder": row.beneficiary_account_holder_snapshot,
            "beneficiary_account_number": row.beneficiary_account_number_snapshot,
            "beneficiary_bank_name": row.beneficiary_bank_name_snapshot,
            "beneficiary_bank_branch": row.beneficiary_bank_branch_snapshot,
            "created_by_user_id": row.created_by_user_id,
            "created_by_name": self._user_name(row.created_by_user_id),
            "paid_by_user_id": row.paid_by_user_id,
            "paid_by_name": self._user_name(row.paid_by_user_id),
            "paid_at": row.paid_at,
            "cancelled_by_user_id": row.cancelled_by_user_id,
            "cancelled_by_name": self._user_name(row.cancelled_by_user_id),
            "cancelled_at": row.cancelled_at,
            "cancel_reason": row.cancel_reason,
            "note": row.note,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
