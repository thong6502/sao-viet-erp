"""Business rules for Accounting purchase approvals and payment vouchers."""
from __future__ import annotations

import secrets
import string
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from sqlalchemy import BigInteger, cast, func, select
from sqlalchemy.exc import IntegrityError

from ..models.accounting import (
    BANK_FEE_BEARERS,
    BANK_FEE_PAYER,
    PAYMENT_RECEIPT_CANCELLED,
    PAYMENT_RECEIPT_RECEIVED,
    PAYMENT_RECEIPT_WAITING,
    PAYMENT_STAGE_ADVANCE,
    PAYMENT_STAGES,
    PAYMENT_VOUCHER_CANCELLED,
    PAYMENT_VOUCHER_PAID,
    PAYMENT_VOUCHER_STATUSES,
    PAYMENT_VOUCHER_TYPES,
    RECEIPT_SOURCE_ORDER,
    RECEIPT_SOURCE_OTHER,
    RECEIPT_SOURCE_PURCHASE,
    RECEIPT_SOURCE_SALES_INVOICE,
    SALES_INVOICE_CANCELLED,
    SALES_INVOICE_ISSUED,
    VOUCHER_SOURCE_CUSTOMER_REFUND,
    VOUCHER_SOURCE_INTERNAL,
    VOUCHER_SOURCE_OTHER,
    VOUCHER_SOURCE_PURCHASE,
    VOUCHER_SOURCE_SALARY_ADVANCE,
    VOUCHER_BANK_TRANSFER,
    VOUCHER_CASH,
    CompanyBankAccount,
    PaymentReceipt,
    PaymentReceiptAttachment,
    PaymentVoucher,
    PaymentVoucherAttachment,
    SalesInvoice,
    SupplierBankAccount,
)
from ..models.customer import Customer
from ..models.document_sequence import (
    SEQ_DOC_TYPE_PAYMENT_RECEIPT,
    SEQ_DOC_TYPE_PAYMENT_VOUCHER,
)
from ..models.order import Order, OrderLine, STATUS_ORDERED
from ..models.purchase import (
    DPR_CANCELLED,
    DPR_DONE,
    DPR_IN_PURCHASE,
    PR_APPROVED,
    PR_PARTIALLY_RECEIVED,
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
from .purchase_service import (
    _purchase_line_amounts,
    gia_tri_dot_giao,
    han_tra_dot,
    phan_bo_tien_dot,
    purchase_money,
)
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


def _order_line_total_with_vat():
    return cast(OrderLine.line_total, BigInteger) * (100 + OrderLine.vat_pct_estimate)


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

# --- PHÂN TUỔI CÔNG NỢ (aging) ---------------------------------------------
# MỘT nguồn duy nhất cho mốc rổ VÀ nhãn rổ. API trả kèm `label` + `min_days`/`max_days` để giao
# diện in ra và tự lọc — frontend KHÔNG được gõ lại "1–7" hay số 7/15/30/60 ở đâu cả. Gõ hai nơi
# là hai nơi lệch nhau ngay lần đầu chủ đổi mốc, mà lệch ở màn tiền thì không ai phát hiện.
#
# Đây chỉ là phép NHÓM trên `overdue_days` đã tính sẵn — không có phép tính tiền nào ở đây.
# `min_days=None` = không có cận dưới (rổ chưa tới hạn), `max_days=None` = không có cận trên.
AGING_CHUA_TOI_HAN = "chua_toi_han"
AGING_BUCKETS: tuple[dict, ...] = (
    # Rổ này gom cả đợt CHƯA TỚI HẠN lẫn đợt KHÔNG CÓ HẠN (`credit_days` NULL ⇒ `han_tra_dot`
    # trả None ⇒ `overdue_days` = 0). Đó đúng là hành vi `_no_theo_han` vẫn chạy từ 06/08/2026:
    # đợt không hạn nằm ở `no_han_amount`. Rổ tuổi chỉ XÉ phần quá hạn ra, KHÔNG đổi chỗ của
    # đợt không-hạn — nó vẫn phải đeo badge "Chưa đặt hạn" ở danh sách chi tiết để không ai
    # tưởng nó đã được canh.
    {"key": AGING_CHUA_TOI_HAN, "label": "Chưa tới hạn", "min_days": None, "max_days": 0},
    {"key": "d1_7", "label": "Trễ 1–7 ngày", "min_days": 1, "max_days": 7},
    {"key": "d8_15", "label": "Trễ 8–15 ngày", "min_days": 8, "max_days": 15},
    {"key": "d16_30", "label": "Trễ 16–30 ngày", "min_days": 16, "max_days": 30},
    {"key": "d31_60", "label": "Trễ 31–60 ngày", "min_days": 31, "max_days": 60},
    {"key": "d60_plus", "label": "Trễ > 60 ngày", "min_days": 61, "max_days": None},
)
AGING_KEYS: tuple[str, ...] = tuple(b["key"] for b in AGING_BUCKETS)
# 5 rổ TRỄ. Tổng tiền 5 rổ này phải LUÔN bằng `overdue_amount` cũ — hai chỗ nói hai kiểu tiền là
# lỗi nặng nhất của màn này (test_phan_tuoi_cong_no.py canh đúng bất biến đó).
AGING_KEYS_TRE: tuple[str, ...] = tuple(k for k in AGING_KEYS if k != AGING_CHUA_TOI_HAN)


def ro_tuoi(overdue_days: int) -> str:
    """Số ngày quá hạn → KHOÁ rổ tuổi. Mốc lấy từ `AGING_BUCKETS`, đừng gõ lại số ở chỗ khác."""
    for b in AGING_BUCKETS:
        if (b["min_days"] is None or overdue_days >= b["min_days"]) and (
            b["max_days"] is None or overdue_days <= b["max_days"]
        ):
            return str(b["key"])
    return AGING_CHUA_TOI_HAN


def _aging_rong() -> dict[str, dict[str, int]]:
    """Bộ rổ rỗng — đủ 6 khoá. NCC không nợ gì vẫn phải trả về đủ rổ = 0, chứ không phải `{}`:
    thiếu khoá là giao diện đọc ra `undefined` rồi in "NaN đ"."""
    return {k: {"amount": 0, "count": 0} for k in AGING_KEYS}


def _aging_cong(dich: dict[str, dict[str, int]], them: dict[str, dict[str, int]]) -> None:
    for k, v in them.items():
        dich[k]["amount"] += v["amount"]
        dich[k]["count"] += v["count"]


def _aging_ra_danh_sach(ro: dict[str, dict[str, int]]) -> list[dict]:
    """Bộ rổ → danh sách CÓ NHÃN, đúng thứ tự già dần. Giao diện chỉ việc in, không tự đặt tên rổ."""
    return [
        {
            "key": b["key"],
            "label": b["label"],
            "min_days": b["min_days"],
            "max_days": b["max_days"],
            "amount": ro[str(b["key"])]["amount"],
            "count": ro[str(b["key"])]["count"],
        }
        for b in AGING_BUCKETS
    ]


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


def _order_total_with_vat(order: Order) -> int:
    """Giá trị đơn gồm VAT, cùng công thức với màn Đơn hàng bán."""
    total_x100 = sum(
        int(line.line_total or 0) * (100 + int(line.vat_pct_estimate or 0))
        for line in order.lines
    )
    return total_x100 // 100


def receivable_rows(
    repo: AccountingRepository, *, customer_id: int | None = None
) -> list[dict]:
    """Một nguồn sự thật cho Công nợ phải thu và thẻ công nợ CRM.

    Chỉ hóa đơn `issued` sinh nợ. Phiếu thu gắn hóa đơn trừ đích danh; cọc gắn đơn
    được cấn FIFO theo (ngày hóa đơn, id) nhưng không tự biến thành công nợ trước
    khi hóa đơn xuất hiện.
    """
    invoices = repo.list_sales_invoices(
        customer_id=customer_id, status=SALES_INVOICE_ISSUED
    )
    if not invoices:
        return []

    invoice_ids = [row.id for row in invoices]
    direct_sums = repo.received_invoice_receipt_sums(invoice_ids)
    order_ids = sorted({row.order_id for row in invoices})
    deposit_sums = repo.received_deposit_sums(order_ids)
    customers = repo.customers_by_ids(
        {row.customer_id for row in invoices if row.customer_id is not None}
    )

    by_order: dict[int, list[SalesInvoice]] = {}
    for invoice in invoices:
        by_order.setdefault(invoice.order_id, []).append(invoice)

    deposit_offsets: dict[int, int] = {}
    for order_id, order_invoices in by_order.items():
        deposit_pool = int(deposit_sums.get(order_id, 0))
        for invoice in sorted(order_invoices, key=lambda row: (row.invoice_date, row.id)):
            direct = min(int(invoice.amount_vnd), int(direct_sums.get(invoice.id, 0)))
            offset = min(deposit_pool, max(0, int(invoice.amount_vnd) - direct))
            deposit_offsets[invoice.id] = offset
            deposit_pool -= offset

    rows: list[dict] = []
    for invoice in invoices:
        direct = int(direct_sums.get(invoice.id, 0))
        deposit_offset = int(deposit_offsets.get(invoice.id, 0))
        amount = int(invoice.amount_vnd)
        received = min(amount, direct + deposit_offset)
        customer = customers.get(invoice.customer_id) if invoice.customer_id else None
        rows.append(
            {
                "invoice_id": invoice.id,
                "invoice_symbol": invoice.invoice_symbol,
                "invoice_number": invoice.invoice_number,
                "invoice_date": invoice.invoice_date,
                "order_id": invoice.order_id,
                "order_code": invoice.order.order_no,
                "customer_id": invoice.customer_id,
                "customer_name": invoice.customer_name_snapshot,
                "credit_limit": int(customer.credit_limit or 0) if customer else 0,
                "payment_term_days": customer.payment_term_days if customer else None,
                "payment_term_days_snapshot": invoice.payment_term_days_snapshot,
                "due_date": invoice.due_date,
                "amount": amount,
                "direct_received_amount": direct,
                "deposit_offset_amount": deposit_offset,
                "received_amount": received,
                "remaining_amount": max(0, amount - received),
            }
        )
    return rows


class AccountingService:
    def __init__(
        self,
        repo: AccountingRepository,
        purchases: PurchaseRequestRepository,
        suppliers: SupplierRepository,
        users: UserRepository,
        audit: AuditLogRepository,
        sequences: SequenceService,
        payroll=None,
        employees=None,
    ) -> None:
        self.repo = repo
        self.purchases = purchases
        self.suppliers = suppliers
        self.users = users
        self.audit = audit
        self.sequences = sequences
        # PayrollRepository | EmployeeRepository — CHỈ ĐỌC, chỉ để lập phiếu chi từ phiếu tạm ứng
        # lương (18/08/2026): đọc phiếu tạm ứng + tên nhân viên. None (unit test dựng tay) ⇒ nguồn
        # `salary_advance` báo lỗi rõ ràng thay vì vỡ.
        self._payroll = payroll
        self._employees = employees

    # --- bank accounts ----------------------------------------------------

    def list_company_accounts(self, *, active_only: bool = False, usage: str | None = None):
        if usage not in (None, "receive", "pay"):
            raise AccountingValidationError("Mục đích tài khoản không hợp lệ.")
        return self.repo.list_company_accounts(active_only=active_only, usage=usage)

    def create_company_account(self, *, actor, **values):
        cleaned = self._clean_bank_account(values, include_usage=True)
        cleaned.pop("is_default", None)
        row = CompanyBankAccount(**cleaned, is_default=False)
        try:
            saved = self.repo.save_company_account(row, make_default=False)
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
        cleaned = self._clean_bank_account(values, include_usage=True)
        cleaned.pop("is_default", None)
        for key, value in cleaned.items():
            setattr(row, key, value)
        row.is_default = False
        try:
            saved = self.repo.save_company_account(row, make_default=False)
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
        cleaned.pop("is_default", None)
        row = SupplierBankAccount(
            supplier_id=supplier_id, **cleaned, is_default=False
        )
        try:
            saved = self.repo.save_supplier_account(row, make_default=False)
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
        cleaned.pop("is_default", None)
        row.supplier_id = supplier_id
        for key, value in cleaned.items():
            setattr(row, key, value)
        row.is_default = False
        try:
            saved = self.repo.save_supplier_account(row, make_default=False)
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

    def _no_cua_phieu(self, row) -> dict:
        """Bóc một phiếu mua thành các con số công nợ.

        Tiền lấy từ `purchase_money` — DÙNG CHUNG với màn Mua hàng, không cộng lại ở đây. Hai chỗ
        tự cộng lấy là hai chỗ lệch, mà lệch tiền thì tới lúc đối chiếu với NCC mới lòi ra.

        Từ 06/08/2026 chỉ còn MỘT con số nợ: `outstanding_amount = hàng đã giao − đã chi ròng`.
        Rổ "chờ chi" biến mất cùng trạng thái `waiting_payment` — lập phiếu chi nghĩa là tiền đã ra,
        nên không còn khoảng giữa "đã ghi sổ" và "đã trả" để mà theo dõi riêng."""
        money = purchase_money(row)
        return {"money": money, "con_no": money["outstanding_amount"]}

    @staticmethod
    def _ngay_chi(v) -> date:
        """Ngày tiền THỰC SỰ rời két. `paid_at` là mốc bấm 'Đã chi'; phiếu cũ chưa có thì lùi về
        ngày chứng từ."""
        return v.paid_at.date() if v.paid_at is not None else v.voucher_date

    def _no_tung_dot(self, row) -> tuple[list[dict], int, int]:
        """Bóc một phiếu thành **(các đợt giao, cọc chung, cọc chưa dùng hết)** cho MÀN CÔNG NỢ.

        Phép phân bổ nằm ở `purchase_service.phan_bo_tien_dot` — DÙNG CHUNG với màn Mua hàng (trần
        lập phiếu chi bám đúng con số này). Hai chỗ tự phân lấy là hai chỗ lệch, mà lệch ở đây thì
        một đợt có thể biến mất khỏi công nợ ở màn này trong khi màn kia vẫn cho lập phiếu.

        Hàm này chỉ khoác thêm phần HIỂN THỊ: hạn trả, số hoá đơn, ngày giao.

        Phiếu chưa có đợt giao nào (dữ liệu cũ) trả `([], 0, 0)`: nợ của nó không quy được về đợt
        nào, màn hình phải hiện ở mức PHIẾU."""
        phan_bo, coc, coc_du = phan_bo_tien_dot(row)
        out = [
            {
                "delivery_id": m["delivery"].id,
                "seq_no": m["delivery"].seq_no,
                "delivery_date": m["delivery"].delivery_date,
                "due_date": han_tra_dot(m["delivery"], row.supplier),
                "invoice_number": m["delivery"].invoice_number,
                "invoice_date": m["delivery"].invoice_date,
                "amount": m["amount"],
                "paid": m["paid"],
                "coc_bu": m["coc_bu"],
                "con_no": m["con_no"],
            }
            for m in phan_bo
        ]
        return out, coc, coc_du

    def _no_theo_han(self, row, con_no: int, hom_nay: date) -> tuple[int, int]:
        """Tách phần còn nợ thành (QUÁ HẠN, CHƯA TỚI HẠN).

        Hạn trả nay thuộc về ĐỢT GIAO, không thuộc phiếu chi nữa — phiếu chi là tiền đã ra, nó
        không có hạn. Đợt của NCC chưa khai `credit_days` thì `han_tra_dot` trả None ⇒ rơi vào
        "chưa tới hạn", và màn hình phải lôi nó lên đầu kèm badge 'Chưa đặt hạn'. Im lặng ở đây là
        một món nợ không ai canh — đúng bệnh giấu nợ đã vá một lần ở phiếu chi thiếu hạn.

        `_no_tung_dot` đã chiếu cọc xuống từng đợt rồi (`con_no` là số SAU khi bù), nên ở đây chỉ
        việc cộng — cọc đã trả thì phần đó không thể còn bị tính là trễ."""
        if con_no <= 0:
            return 0, 0
        dots, _coc, _du = self._no_tung_dot(row)
        if not dots:
            return 0, con_no
        qua_han = sum(
            d["con_no"]
            for d in dots
            if d["con_no"] > 0 and d["due_date"] is not None and d["due_date"] < hom_nay
        )
        return qua_han, max(0, con_no - qua_han)

    def _no_theo_ro_tuoi(self, row, con_no: int, hom_nay: date) -> dict[str, dict[str, int]]:
        """Xé phần còn nợ của MỘT phiếu thành các RỔ TUỔI (tiền + số đợt).

        Chỉ NHÓM, không tính lại đồng nào: cùng danh sách đợt, cùng phép so hạn, cùng phép trừ
        `con_no − quá hạn` với `_no_theo_han`. Nhờ vậy tổng 5 rổ trễ LUÔN đúng bằng
        `overdue_amount`, và rổ "chưa tới hạn" đúng bằng `no_han_amount` — hai màn không bao giờ
        nói hai kiểu tiền. Tự cộng lấy ở đây là mở đúng cái cửa đó.

        Đợt KHÔNG có hạn (`han_tra_dot` trả None) không vào rổ trễ nào; nó ở lại "chưa tới hạn"
        y như `_no_theo_han` vẫn xếp — giữ nguyên hành vi cũ, chỉ thêm rổ."""
        ro = _aging_rong()
        if con_no <= 0:
            return ro
        dots, _coc, _du = self._no_tung_dot(row)
        if not dots:
            # Phiếu CŨ không theo dõi theo đợt: nợ chỉ quy được về mức PHIẾU, không có hạn ⇒ cả
            # cục nằm ở "chưa tới hạn" (đúng nhánh `return 0, con_no` của `_no_theo_han`), đếm là
            # MỘT khoản.
            ro[AGING_CHUA_TOI_HAN]["amount"] += con_no
            ro[AGING_CHUA_TOI_HAN]["count"] += 1
            return ro
        qua_han = 0
        for d in dots:
            if d["con_no"] <= 0:
                continue
            if d["due_date"] is not None and d["due_date"] < hom_nay:
                khoa = ro_tuoi((hom_nay - d["due_date"]).days)
                ro[khoa]["amount"] += d["con_no"]
                ro[khoa]["count"] += 1
                qua_han += d["con_no"]
            else:
                ro[AGING_CHUA_TOI_HAN]["count"] += 1
        ro[AGING_CHUA_TOI_HAN]["amount"] += max(0, con_no - qua_han)
        return ro

    def payables_summary(
        self,
        *,
        q: str | None = None,
        filter_: str = "all",
        aging_bucket: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> dict:
        """Công nợ phải trả gom theo nhà cung cấp.

        Dựng dòng khi **còn nợ > 0 HOẶC đã trả trong kỳ > 0**. Chỉ lấy "còn nợ > 0" là NCC vừa trả
        hết biến mất khỏi bảng ngay — mà đó đúng là lúc cần thấy nhất: câu hỏi *"làm sao biết mình
        đã trả hết"* chỉ trả lời được bằng cách NHÌN THẤY danh sách đã trả, không phải bằng việc
        không thấy gì (im lặng còn có nghĩa là màn hỏng).

        `q` = tìm theo tên NCC. Khi có `q` thì lôi ra **mọi** NCC khớp tên, kể cả nợ 0đ và không hề
        giao dịch trong kỳ — dùng để tra một NCC đã im lặng lâu. Lọc ở SERVER chứ không lọc trên
        danh sách đã dựng, vì NCC đó vốn không có dòng nào để mà lọc.

        `aging_bucket` = một khoá trong `AGING_KEYS`: chỉ giữ NCC còn tiền trong RỔ TUỔI đó. Đi
        cùng đường với `filter_` (lọc trên danh sách đã dựng, sau khi thẻ tổng đã chốt), nên bấm
        một rổ KHÔNG làm mấy con số tổng ở đầu màn nhảy theo."""
        hom_nay = _business_today()
        moc_ky = hom_nay - timedelta(days=31 * PAYABLES_PERIOD_MONTHS)
        tim = (q or "").strip().lower()
        theo_ncc: dict[int | None, dict] = {}

        def _muc(row) -> dict:
            han_muc = int(getattr(row.supplier, "credit_limit", 0) or 0) if row.supplier else 0
            return theo_ncc.setdefault(
                row.supplier_id,
                {
                    "supplier_id": row.supplier_id,
                    "supplier_name": row.supplier.name if row.supplier else "(không rõ NCC)",
                    "order_count": 0,
                    "overdue_amount": 0,
                    "no_han_amount": 0,
                    # Rổ tuổi của RIÊNG NCC này. NCC không nợ gì vẫn có đủ 6 rổ = 0.
                    "aging": _aging_rong(),
                    "paid_in_period": 0,
                    "total_due": 0,
                    "credit_limit": han_muc,
                    "credit_days": getattr(row.supplier, "credit_days", None) if row.supplier else None,
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
            muc["total_due"] += no["con_no"]
            qua_han, chua_han = self._no_theo_han(row, no["con_no"], hom_nay)
            muc["overdue_amount"] += qua_han
            muc["no_han_amount"] += chua_han
            # Rổ tuổi = xé chính hai con số trên ra theo `overdue_days`, không cộng lại từ đầu.
            _aging_cong(muc["aging"], self._no_theo_ro_tuoi(row, no["con_no"], hom_nay))

        items = sorted(
            theo_ncc.values(),
            key=lambda m: (m["total_due"], m["paid_in_period"]),
            reverse=True,
        )
        for m in items:
            # Cảnh báo MỀM (Đ6): chỉ gắn cờ, không chặn gì ở đâu.
            m["vuot_han_muc"] = m["credit_limit"] > 0 and m["total_due"] > m["credit_limit"]
            m["vuot_bao_nhieu"] = (
                max(0, m["total_due"] - m["credit_limit"]) if m["credit_limit"] > 0 else 0
            )
        # Thẻ tổng quan luôn tính trên TOÀN BỘ NCC đang có hoạt động/nợ, không đổi theo ô tìm kiếm,
        # bộ lọc hay trang hiện tại. Dòng nợ 0 chỉ được lôi ra khi người dùng chủ động tìm tên.
        tong_hop = [m for m in items if m["total_due"] > 0 or m["paid_in_period"] > 0]
        if tim:
            items = [m for m in items if tim in (m["supplier_name"] or "").lower()]
        if filter_ == "overdue":
            items = [m for m in items if m["overdue_amount"] > 0]
        elif filter_ == "chua_han":
            items = [m for m in items if m["no_han_amount"] > 0]
        elif filter_ == "vuot_han_muc":
            items = [m for m in items if m["vuot_han_muc"]]
        # Lọc theo RỔ TUỔI đi sau, cùng kiểu với `filter_`: khoá lạ thì BỎ QUA (không lọc), y như
        # `filter_` lạ — cửa lọc không phải chỗ ném 422 vào mặt người đang xem công nợ.
        if aging_bucket in AGING_KEYS:
            items = [m for m in items if m["aging"][aging_bucket]["amount"] > 0]

        # Dải rổ tuổi ở ĐẦU MÀN tính trên `tong_hop` — cùng gốc với thẻ "Tổng phải trả"/"Quá hạn",
        # nên bấm lọc hay lật trang KHÔNG làm nó nhảy. Dải mà nhảy theo trang thì nó đang đo cái
        # trang, không đo món nợ.
        tong_ro = _aging_rong()
        for m in tong_hop:
            _aging_cong(tong_ro, m["aging"])

        page = max(1, page)
        size = max(1, min(size, 200))
        total = len(items)
        pages = max(1, (total + size - 1) // size)
        page = min(page, pages)
        bat_dau = (page - 1) * size
        return {
            "items": items[bat_dau:bat_dau + size],
            "total": total,
            "page": page,
            "size": size,
            "pages": pages,
            "total_due": sum(m["total_due"] for m in tong_hop),
            # GIỮ NGUYÊN: nhiều chỗ đang ăn con số này. Rổ tuổi chỉ XÉ nó ra chứ không thay nó.
            "overdue_amount": sum(m["overdue_amount"] for m in tong_hop),
            "aging": _aging_ra_danh_sach(tong_ro),
            "paid_in_period": sum(m["paid_in_period"] for m in tong_hop),
            "vuot_han_muc_count": sum(1 for m in tong_hop if m["vuot_han_muc"]),
            "period_months": PAYABLES_PERIOD_MONTHS,
            "as_of": hom_nay,
        }

    def payables_detail(self, supplier_id: int, *, all_history: bool = False) -> dict:
        """Chi tiết công nợ một NCC — chưa vào sổ · 🟡 chờ chi · ✅ đã chi trong kỳ.


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
        con_no: list[dict] = []
        coc_chung: list[dict] = []
        da_chi: list[dict] = []
        qua_han_tong = 0
        for row in self.purchases.list_for_payables(supplier_id=supplier_id):
            no = self._no_cua_phieu(row)
            money = no["money"]
            # Quá hạn tính SAU khi trừ cọc — cọc đã trả rồi thì phần đó không còn trễ. Dùng chung
            # hàm với màn tổng hợp để hai màn không bao giờ ra hai con số.
            qua_han_tong += self._no_theo_han(row, no["con_no"], hom_nay)[0]
            dots, coc, coc_du = self._no_tung_dot(row)
            if coc > 0:
                # CỌC là cọc của CẢ ĐƠN, không thuộc đợt nào — hiện thành dòng riêng chứ không nhét
                # vào cột "đã trả" của một đợt. Nhét vào là bảng nói dối: người đối chiếu với NCC
                # theo từng đợt sẽ không khớp được với sao kê.
                #
                # `da_dung` để màn hình nói được "cọc 100.000, đã bù hết vào đợt 1" — nếu không,
                # người đọc thấy một dòng trừ 100.000 mà không biết nó trừ vào đâu.
                coc_chung.append(
                    {
                        "purchase_request_id": row.id,
                        "code": row.code,
                        "status": row.status,
                        "amount": coc,
                        "da_dung": max(0, coc - coc_du),
                        "con_du": max(0, coc_du),
                    }
                )
            if dots:
                for d in dots:
                    if d["con_no"] <= 0:
                        continue
                    # Tính MỘT lần rồi tái dùng cho cả `overdue_days` lẫn `aging_bucket` — hai
                    # trường phải luôn khớp nhau, tách ra tính hai lần là mở cửa cho chúng lệch.
                    so_ngay_tre = (
                        (hom_nay - d["due_date"]).days
                        if d["due_date"] is not None and d["due_date"] < hom_nay
                        else 0
                    )
                    con_no.append(
                        {
                            "purchase_request_id": row.id,
                            "code": row.code,
                            "status": row.status,
                            "delivery_id": d["delivery_id"],
                            "seq_no": d["seq_no"],
                            "delivery_date": d["delivery_date"],
                            "due_date": d["due_date"],
                            "chua_dat_han": d["due_date"] is None,
                            "overdue_days": so_ngay_tre,
                            "aging_bucket": ro_tuoi(so_ngay_tre) if so_ngay_tre > 0 else None,
                            "invoice_number": d["invoice_number"],
                            "invoice_date": d["invoice_date"],
                            "amount": d["amount"],
                            "paid": d["paid"],
                            "coc_bu": d["coc_bu"],
                            "con_no": d["con_no"],
                        }
                    )
            elif no["con_no"] > 0:
                # Phiếu CŨ không theo dõi theo đợt: nợ chỉ quy được về mức PHIẾU. Không có hạn trả
                # nên không bao giờ vào cột Quá hạn — vẫn phải hiện, và `chua_dat_han` kéo nó lên đầu.
                con_no.append(
                    {
                        "purchase_request_id": row.id,
                        "code": row.code,
                        "status": row.status,
                        "delivery_id": None,
                        "seq_no": None,
                        "delivery_date": None,
                        "due_date": None,
                        "chua_dat_han": True,
                        "overdue_days": 0,
                        "aging_bucket": None,
                        "invoice_number": None,
                        "amount": money["gia_tri_da_giao"],
                        "paid": money["net_paid"],
                        "con_no": no["con_no"],
                    }
                )
            # Số ĐỢT của từng phiếu chi. Chỉ có `delivery_id` thì màn hình đành ghi "trả theo đợt"
            # chung chung — cầm sao kê NCC đối chiếu không biết dòng nào là đợt mấy (chủ 07/08/2026).
            seq_theo_dot = {d.id: d.seq_no for d in (getattr(row, "deliveries", []) or [])}
            for v in row.payment_vouchers:
                if v.status != PAYMENT_VOUCHER_PAID:
                    continue
                ngay = self._ngay_chi(v)
                if ngay < moc_ky:
                    continue
                did = getattr(v, "delivery_id", None)
                da_chi.append(
                    {
                        "voucher_id": v.id,
                        "code": v.code,
                        "doc_no": v.doc_no,
                        "voucher_type": v.voucher_type,
                        "payment_stage": v.payment_stage,
                        "delivery_id": did,
                        "delivery_seq_no": seq_theo_dot.get(did),
                        "purchase_request_id": row.id,
                        "purchase_code": row.code,
                        "amount": int(v.amount_vnd),
                        "invoice_number": v.invoice_number,
                        "invoice_date": v.invoice_date,
                        "has_attachment": bool(v.attachments),
                        "paid_date": ngay,
                        # `_user_name` đi qua `Session.get` ⇒ cùng một kế toán lập 20 phiếu vẫn chỉ
                        # một lượt vào DB (lần sau lấy ở identity map), không thành N+1.
                        "created_by_user_id": v.created_by_user_id,
                        "created_by_name": self._user_name(v.created_by_user_id),
                    }
                )
        # Sắp theo hạn trả; đợt THIẾU hạn đẩy lên ĐẦU chứ không dìm xuống cuối — chúng không bao giờ
        # vào được cột Quá hạn nên phải đập vào mắt để còn đi khai số ngày cho nợ của NCC.
        con_no.sort(key=lambda x: (x["due_date"] is not None, x["due_date"] or hom_nay))
        da_chi.sort(key=lambda x: x["paid_date"], reverse=True)
        han_muc = int(getattr(supplier, "credit_limit", 0) or 0) if supplier is not None else 0
        # `con_no` của từng đợt ĐÃ trừ cọc trong `_no_tung_dot` ⇒ cộng thẳng, KHÔNG trừ lần nữa.
        # Cọc lớn hơn nợ (ứng trước nhiều, hàng về ít) chỉ làm mọi đợt về 0, không thành số âm —
        # phần dôi ra là khoản phải THU, việc khác, không thuộc màn này.
        tong_no = sum(x["con_no"] for x in con_no)
        tong_coc = sum(x["amount"] for x in coc_chung)
        # Rổ tuổi của drawer đếm trên ĐÚNG danh sách đang hiện bên dưới nó (`con_no`), nên pill và
        # bảng không bao giờ chửi nhau. Đợt chưa có hạn có `overdue_days` = 0 ⇒ rơi vào "chưa tới
        # hạn" và vẫn giữ badge "Chưa đặt hạn" ở cột Hạn trả — nó không bị rổ tuổi nuốt mất.
        ro_chi_tiet = _aging_rong()
        for x in con_no:
            khoa = ro_tuoi(x["overdue_days"])
            ro_chi_tiet[khoa]["amount"] += x["con_no"]
            ro_chi_tiet[khoa]["count"] += 1
        return {
            "supplier_id": supplier_id,
            "supplier_name": supplier.name if supplier is not None else "(không rõ NCC)",
            "credit_limit": han_muc,
            "credit_days": getattr(supplier, "credit_days", None) if supplier is not None else None,
            "vuot_han_muc": han_muc > 0 and tong_no > han_muc,
            "vuot_bao_nhieu": max(0, tong_no - han_muc) if han_muc > 0 else 0,
            "items": con_no,
            # Cọc/ứng trước của CẢ ĐƠN — dòng riêng, không thuộc đợt nào (chủ chốt 06/08/2026).
            "coc_chung": coc_chung,
            "coc_chung_amount": tong_coc,
            "paid": da_chi,
            "period_months": PAYABLES_PERIOD_MONTHS,
            "all_history": all_history,
            "total_due": tong_no,
            "overdue_amount": qua_han_tong,
            "aging": _aging_ra_danh_sach(ro_chi_tiet),
            "paid_in_period": sum(x["amount"] for x in da_chi),
            "as_of": hom_nay,
        }

    # --- vouchers ---------------------------------------------------------

    def list_vouchers(self, **filters):
        rows, total, totals = self.repo.list_vouchers(**filters)
        return [self._voucher_out(row) for row in rows], total, totals

    def get_voucher(self, voucher_id: int):
        return self._voucher_out(self._voucher(voucher_id))

    def create_voucher(self, *, actor, purchase_request_id: int | None = None,
                       salary_advance_id: int | None = None, **values):
        source_type = (values.get("source_type") or VOUCHER_SOURCE_PURCHASE).strip()
        if source_type == VOUCHER_SOURCE_SALARY_ADVANCE or salary_advance_id is not None:
            purchase = None
            advance = self._advance_cho_phieu_chi(salary_advance_id)
            prepared = self._prepare_standalone_voucher(values, advance=advance)
        elif source_type == VOUCHER_SOURCE_PURCHASE or purchase_request_id is not None:
            if purchase_request_id is None:
                raise AccountingValidationError("Phiếu chi từ Đơn mua hàng phải chọn Đơn mua hàng nguồn.")
            purchase = self._purchase(purchase_request_id)
            prepared = self._prepare_voucher(
                purchase, values, allow_pending_purchase=False, exclude_voucher_id=None
            )
        else:
            purchase = None
            prepared = self._prepare_standalone_voucher(values)
        doc_no = self._next_voucher_doc_no()
        voucher = self._new_voucher(purchase, prepared, actor.id, doc_no=doc_no)
        saved = self.repo.save_voucher(voucher)
        self.audit.create(
            actor_user_id=actor.id,
            action="create_payment_voucher",
            target=f"payment_voucher:{saved.id}",
            detail=f"{saved.code} <- {purchase.code if purchase else prepared['source_type']}",
        )
        return self._voucher_out(saved)

    # ĐÃ GỠ 04/08/2026: `approve_and_create_voucher()` — gộp duyệt PMH + lập phiếu chi vào một
    # thao tác. Tách vai: người đồng ý chi không được là người viết phiếu chi. Duyệt nay ở
    # `purchase_service.approve()` (có chốt chống tự duyệt), lập phiếu chi ở `create_voucher()`.

    # ĐÃ GỠ 07/08/2026: `update_voucher()` — sửa một phiếu chi đã lập.
    #
    # Chủ chốt: *"đã lập phiếu chứng từ rồi sao lại cho sửa nữa vậy, chỉ cho nó đính kèm tài liệu
    # lên thôi"*. Đúng nguyên tắc chứng từ: phiếu chi phát hành ra là TIỀN ĐÃ RỜI KÉT (Đ1), sửa nó
    # là làm cho tờ giấy đang nằm ở chỗ NCC khác với bản trong máy. Sai thì HUỶ (có lý do, giữ số
    # chứng từ) rồi lập phiếu mới — dấu vết còn đủ hai bản.
    #
    # Còn sửa được: ĐÍNH KÈM tài liệu (`add_voucher_attachment` / `delete_voucher_attachment`) —
    # hoá đơn, UNC ngân hàng thường về sau khi chi.

    # ĐÃ GỠ 06/08/2026: `mark_paid()` — nút "Xác nhận đã chi". Không còn nghĩa gì khi lập phiếu chi
    # ĐÃ LÀ hành vi chi tiền (Đ1). Giữ lại một nút hai bước chỉ tạo ra khoảng giữa mà bên nghiệp vụ
    # nói thẳng là không tồn tại: *"tạo phiếu chi là đã chi tiền rồi còn công nợ cái gì"*.

    def cancel_voucher(self, voucher_id: int, *, actor, reason: str):
        """Huỷ một phiếu chi — nay nghĩa là GHI NHẬN NHẦM, vì tiền đã ra lúc lập phiếu.

        Chặn khi đã có phiếu thu gắn vào: phiếu thu là tiền tiêu không hết nộp về, huỷ phiếu chi gốc
        sẽ để phiếu thu treo không có gốc và cộng ngược thành nợ ảo. Luật này vốn có từ trước, chỉ
        chuyển chỗ kiểm — trước đây `cancel` chỉ cho phiếu `waiting` nên phiếu có phiếu thu (buộc
        phải `paid`) tự nhiên không bao giờ huỷ được."""
        voucher = self._voucher(voucher_id)
        if voucher.status == PAYMENT_VOUCHER_CANCELLED:
            raise AccountingConflict("Chứng từ đã hủy rồi.")
        if voucher.receipts:
            raise AccountingConflict(
                "Chứng từ đã có phiếu thu gắn vào nên không hủy được — hủy phiếu thu trước."
            )
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

    # --- receivables -------------------------------------------------------

    def _receivable_rows(self, *, customer_id: int | None = None) -> list[dict]:
        return receivable_rows(self.repo, customer_id=customer_id)

    def _sales_invoice_out(self, invoice: SalesInvoice, money_row: dict | None = None) -> dict:
        active = invoice.status == SALES_INVOICE_ISSUED
        direct = money_row["direct_received_amount"] if money_row else 0
        deposit = money_row["deposit_offset_amount"] if money_row else 0
        received = money_row["received_amount"] if money_row else 0
        remaining = money_row["remaining_amount"] if money_row else 0
        return {
            "id": invoice.id,
            "order_id": invoice.order_id,
            "order_code": invoice.order.order_no,
            "customer_id": invoice.customer_id,
            "customer_name": invoice.customer_name_snapshot,
            "invoice_symbol": invoice.invoice_symbol,
            "invoice_number": invoice.invoice_number,
            "invoice_date": invoice.invoice_date,
            "amount_vnd": int(invoice.amount_vnd),
            "payment_term_days_snapshot": invoice.payment_term_days_snapshot,
            "due_date": invoice.due_date,
            "status": invoice.status,
            "direct_received_amount": direct if active else 0,
            "deposit_offset_amount": deposit if active else 0,
            "received_amount": received if active else 0,
            "remaining_amount": remaining if active else 0,
            "created_by_user_id": invoice.created_by_user_id,
            "created_by_name": self._user_name(invoice.created_by_user_id),
            "created_at": invoice.created_at,
            "cancelled_by_user_id": invoice.cancelled_by_user_id,
            "cancelled_by_name": self._user_name(invoice.cancelled_by_user_id),
            "cancelled_at": invoice.cancelled_at,
            "cancel_reason": invoice.cancel_reason,
        }

    def list_order_sales_invoices(self, order_id: int) -> dict:
        order = self.repo.get_sales_order(order_id)
        if order is None:
            raise AccountingNotFound("Không tìm thấy đơn hàng bán.")
        invoices = self.repo.list_sales_invoices(order_id=order_id)
        money = {
            row["invoice_id"]: row
            for row in self._receivable_rows(customer_id=order.customer_id)
            if row["order_id"] == order_id
        }
        order_total = _order_total_with_vat(order)
        invoiced = sum(
            int(row.amount_vnd)
            for row in invoices
            if row.status == SALES_INVOICE_ISSUED
        )
        return {
            "order_id": order.id,
            "order_code": order.order_no,
            "order_total": order_total,
            "invoiced_amount": invoiced,
            "uninvoiced_amount": max(0, order_total - invoiced),
            "deposit_received": self.repo.received_deposit_sum(order.id),
            "items": [self._sales_invoice_out(row, money.get(row.id)) for row in invoices],
        }

    def create_sales_invoice(self, *, actor, **values) -> dict:
        order_id = int(values.get("order_id") or 0)
        order = self.repo.get_sales_order(order_id)
        if order is None:
            raise AccountingNotFound("Không tìm thấy đơn hàng bán.")
        if order.status != STATUS_ORDERED:
            raise AccountingConflict("Chỉ đơn hàng đã chốt mới được ghi nhận hóa đơn.")
        if order.customer_id is None:
            raise AccountingValidationError("Đơn hàng chưa có khách hàng để ghi nhận công nợ.")
        customer = self.repo.get_customer(order.customer_id)
        if customer is None:
            raise AccountingValidationError("Khách hàng của đơn không còn tồn tại.")
        invoice_date = values.get("invoice_date")
        if invoice_date is None:
            raise AccountingValidationError("Ngày hóa đơn không được để trống.")
        if invoice_date > _business_today():
            raise AccountingValidationError("Ngày hóa đơn không được ở tương lai.")
        if order.ordered_at is not None and invoice_date < order.ordered_at.date():
            raise AccountingValidationError("Ngày hóa đơn không được trước ngày chốt đơn.")
        invoice_number = _text(
            values.get("invoice_number"), label="Số hóa đơn", required=True, max_length=64
        )
        invoice_symbol = _text(
            values.get("invoice_symbol"), label="Ký hiệu hóa đơn", required=True, max_length=64
        )
        order_total = _order_total_with_vat(order)
        already_invoiced = self.repo.issued_invoice_amount_for_order(order.id)
        available = max(0, order_total - already_invoiced)
        amount = int(values.get("amount_vnd") or available)
        if amount <= 0:
            raise AccountingValidationError("Đơn hàng không còn giá trị để ghi hóa đơn.")
        if amount > available:
            raise AccountingValidationError(
                f"Số tiền hóa đơn vượt phần chưa xuất hóa đơn ({available:,} đ)."
            )
        term_days = customer.payment_term_days
        due_date = (
            invoice_date + timedelta(days=int(term_days))
            if term_days is not None
            else None
        )
        invoice = SalesInvoice(
            order_id=order.id,
            customer_id=customer.id,
            invoice_symbol=invoice_symbol,
            invoice_number=invoice_number,
            invoice_date=invoice_date,
            amount_vnd=amount,
            payment_term_days_snapshot=term_days,
            due_date=due_date,
            customer_name_snapshot=customer.name,
            status=SALES_INVOICE_ISSUED,
            created_by_user_id=actor.id,
        )
        try:
            saved = self.repo.save_sales_invoice(invoice)
        except IntegrityError as exc:
            raise AccountingConflict("Số và ký hiệu hóa đơn đã tồn tại.") from exc
        self.audit.create(
            actor_user_id=actor.id,
            action="create_sales_invoice",
            target=f"sales_invoice:{saved.id}",
            detail=f"{saved.invoice_number} <- {order.order_no}: {amount:,}đ",
        )
        money = next(
            (row for row in self._receivable_rows(customer_id=customer.id) if row["invoice_id"] == saved.id),
            None,
        )
        return self._sales_invoice_out(saved, money)

    def cancel_sales_invoice(self, invoice_id: int, *, actor, reason: str) -> dict:
        invoice = self.repo.get_sales_invoice(invoice_id)
        if invoice is None:
            raise AccountingNotFound("Không tìm thấy hóa đơn bán.")
        if invoice.status == SALES_INVOICE_CANCELLED:
            raise AccountingConflict("Hóa đơn đã hủy rồi.")
        if self.repo.sales_invoice_has_active_receipts(invoice.id):
            raise AccountingConflict(
                "Hóa đơn đã có phiếu thu gắn vào; hãy hủy phiếu thu trước."
            )
        cleaned = _text(reason, label="Lý do hủy", required=True, max_length=2000)
        invoice.status = SALES_INVOICE_CANCELLED
        invoice.cancel_reason = cleaned
        invoice.cancelled_by_user_id = actor.id
        invoice.cancelled_at = _now()
        saved = self.repo.save_sales_invoice(invoice)
        self.audit.create(
            actor_user_id=actor.id,
            action="cancel_sales_invoice",
            target=f"sales_invoice:{saved.id}",
            detail=f"{saved.invoice_number}: {cleaned}",
        )
        return self._sales_invoice_out(saved)

    def _receipts_for_receivable_rows(
        self, rows: list[dict], *, since: date | None = None
    ) -> list[dict]:
        invoice_ids = sorted({row["invoice_id"] for row in rows})
        order_ids = sorted({row["order_id"] for row in rows})
        receipts = self.repo.list_receipts_for_receivables(
            invoice_ids=invoice_ids, order_ids=order_ids, since=since
        )
        return [
            {
                "receipt_id": row.id,
                "code": row.code,
                "doc_no": row.doc_no,
                "order_id": (
                    row.order_id
                    if row.order_id is not None
                    else (row.sales_invoice.order_id if row.sales_invoice else None)
                ),
                "order_code": row.order_no_snapshot,
                "source_type": row.source_type,
                "sales_invoice_id": row.sales_invoice_id,
                "sales_invoice_number": (
                    row.sales_invoice.invoice_number if row.sales_invoice else None
                ),
                "applied_to": (
                    "deposit_offset"
                    if row.source_type == RECEIPT_SOURCE_ORDER
                    else "sales_invoice"
                ),
                "receipt_method": row.receipt_method,
                "amount": int(row.amount_vnd),
                "receipt_date": row.receipt_date,
                "payer_name": row.payer_name,
                "bank_reference": row.bank_reference,
                "created_by_name": self._user_name(row.created_by_user_id),
            }
            for row in receipts
        ]

    def receivables_summary(
        self,
        *,
        q: str | None = None,
        filter_: str = "all",
        page: int = 1,
        size: int = 20,
    ) -> dict:
        hom_nay = _business_today()
        moc_ky = hom_nay - timedelta(days=31 * PAYABLES_PERIOD_MONTHS)
        tim = (q or "").strip().lower()
        rows = self._receivable_rows()
        receipts = self._receipts_for_receivable_rows(rows, since=moc_ky)
        order_to_customer = {r["order_id"]: r["customer_id"] for r in rows}
        invoice_to_customer = {r["invoice_id"]: r["customer_id"] for r in rows}
        thu_theo_khach: dict[int | None, int] = {}
        for receipt in receipts:
            cid = (
                invoice_to_customer.get(receipt["sales_invoice_id"])
                if receipt["sales_invoice_id"] is not None
                else order_to_customer.get(receipt["order_id"])
            )
            thu_theo_khach[cid] = thu_theo_khach.get(cid, 0) + receipt["amount"]

        theo_khach: dict[int | None, dict] = {}
        for row in rows:
            cid = row["customer_id"]
            bucket = theo_khach.setdefault(
                cid,
                {
                    "customer_id": cid,
                    "customer_name": row["customer_name"],
                    "invoice_count": 0,
                    "invoiced_amount": 0,
                    "received_amount": 0,
                    "total_due": 0,
                    "overdue_amount": 0,
                    "no_han_amount": 0,
                    "credit_limit": row["credit_limit"],
                    "payment_term_days": row["payment_term_days"],
                    "received_in_period": 0,
                },
            )
            bucket["invoiced_amount"] += row["amount"]
            bucket["received_amount"] += row["received_amount"]
            con_no = row["remaining_amount"]
            if con_no <= 0:
                continue
            bucket["invoice_count"] += 1
            bucket["total_due"] += con_no
            if row["due_date"] is not None and row["due_date"] < hom_nay:
                bucket["overdue_amount"] += con_no
            else:
                bucket["no_han_amount"] += con_no

        for cid, amount in thu_theo_khach.items():
            if cid in theo_khach:
                theo_khach[cid]["received_in_period"] += amount

        items = []
        for item in theo_khach.values():
            khop_tim = bool(tim) and tim in (item["customer_name"] or "").lower()
            if item["total_due"] <= 0 and item["received_in_period"] <= 0 and not khop_tim:
                continue
            item["vuot_han_muc"] = item["credit_limit"] > 0 and item["total_due"] > item["credit_limit"]
            item["vuot_bao_nhieu"] = (
                max(0, item["total_due"] - item["credit_limit"]) if item["credit_limit"] > 0 else 0
            )
            items.append(item)
        items.sort(key=lambda x: (x["total_due"], x["received_in_period"]), reverse=True)
        tong_hop = [i for i in items if i["total_due"] > 0 or i["received_in_period"] > 0]
        if tim:
            items = [i for i in items if tim in (i["customer_name"] or "").lower()]
        if filter_ == "overdue":
            items = [i for i in items if i["overdue_amount"] > 0]
        elif filter_ == "chua_han":
            items = [i for i in items if i["no_han_amount"] > 0]
        elif filter_ == "vuot_han_muc":
            items = [i for i in items if i["vuot_han_muc"]]

        page = max(1, page)
        size = max(1, min(size, 200))
        total = len(items)
        pages = max(1, (total + size - 1) // size)
        page = min(page, pages)
        bat_dau = (page - 1) * size
        return {
            "items": items[bat_dau:bat_dau + size],
            "total": total,
            "page": page,
            "size": size,
            "pages": pages,
            "total_due": sum(i["total_due"] for i in tong_hop),
            "overdue_amount": sum(i["overdue_amount"] for i in tong_hop),
            "received_in_period": sum(i["received_in_period"] for i in tong_hop),
            "vuot_han_muc_count": sum(1 for i in tong_hop if i["vuot_han_muc"]),
            "period_months": PAYABLES_PERIOD_MONTHS,
            "as_of": hom_nay,
        }

    def receivables_detail(self, customer_id: int, *, all_history: bool = False) -> dict:
        hom_nay = _business_today()
        moc_ky = date.min if all_history else hom_nay - timedelta(days=31 * PAYABLES_PERIOD_MONTHS)
        customer = self.repo.get_customer(customer_id)
        if customer is None:
            raise AccountingNotFound("Không tìm thấy khách hàng.")
        rows = self._receivable_rows(customer_id=customer_id)
        items = []
        for row in rows:
            con_no = row["remaining_amount"]
            if con_no <= 0:
                continue
            items.append(
                {
                    "invoice_id": row["invoice_id"],
                    "invoice_symbol": row["invoice_symbol"],
                    "invoice_number": row["invoice_number"],
                    "invoice_date": row["invoice_date"],
                    "order_id": row["order_id"],
                    "order_code": row["order_code"],
                    "customer_id": row["customer_id"],
                    "customer_name": row["customer_name"],
                    "due_date": row["due_date"],
                    "chua_dat_han": row["due_date"] is None,
                    "overdue_days": (
                        (hom_nay - row["due_date"]).days
                        if row["due_date"] is not None and row["due_date"] < hom_nay
                        else 0
                    ),
                    "amount": row["amount"],
                    "direct_received_amount": row["direct_received_amount"],
                    "deposit_offset_amount": row["deposit_offset_amount"],
                    "received_amount": row["received_amount"],
                    "remaining_amount": con_no,
                }
            )
        items.sort(key=lambda x: (x["due_date"] is not None, x["due_date"] or hom_nay))
        paid = self._receipts_for_receivable_rows(rows, since=moc_ky)
        total_due = sum(i["remaining_amount"] for i in items)
        overdue_amount = sum(i["remaining_amount"] for i in items if i["overdue_days"] > 0)
        credit_limit = int(customer.credit_limit or 0)
        return {
            "customer_id": customer.id,
            "customer_name": customer.name,
            "credit_limit": credit_limit,
            "payment_term_days": customer.payment_term_days,
            "vuot_han_muc": credit_limit > 0 and total_due > credit_limit,
            "vuot_bao_nhieu": max(0, total_due - credit_limit) if credit_limit > 0 else 0,
            "items": items,
            "paid": paid,
            "period_months": PAYABLES_PERIOD_MONTHS,
            "all_history": all_history,
            "total_due": total_due,
            "overdue_amount": overdue_amount,
            "received_in_period": sum(p["amount"] for p in paid),
            "as_of": hom_nay,
        }

    # --- payment receipts ---------------------------------------------------

    def list_receipts(
        self,
        *,
        q: str | None = None,
        status: str | None = None,
        payment_voucher_id: int | None = None,
        source_type: str | None = None,
        sort: str = "-created_at",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict], int]:
        # Màn Phiếu thu kế toán là một sổ chung: thu hoàn phiếu chi, thu cọc đơn bán, và thu khác.
        # Truyền source_type khi cần lọc riêng từng nguồn; None = xem toàn bộ sổ.
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

    def create_other_receipt(self, *, actor, **values):
        prepared = self._prepare_other_receipt(values)
        doc_no = self.sequences.generate_flat_code(SEQ_DOC_TYPE_PAYMENT_RECEIPT)
        account = prepared.pop("company_account")
        receipt = PaymentReceipt(
            code=self._new_receipt_code(),
            doc_no=doc_no,
            source_type=RECEIPT_SOURCE_OTHER,
            status=PAYMENT_RECEIPT_RECEIVED,
            created_by_user_id=actor.id,
            received_by_user_id=actor.id,
            received_at=_now(),
        )
        for key, value in prepared.items():
            setattr(receipt, key, value)
        receipt.company_bank_account_id = account.id if account else None
        receipt.company_account_holder_snapshot = account.account_holder if account else None
        receipt.company_account_number_snapshot = account.account_number if account else None
        receipt.company_bank_name_snapshot = account.bank_name if account else None
        receipt.company_bank_branch_snapshot = account.bank_branch if account else None
        saved = self.repo.save_receipt(receipt)
        self.audit.create(
            actor_user_id=actor.id,
            action="create_other_payment_receipt",
            target=f"payment_receipt:{saved.id}",
            detail=saved.code,
        )
        return self._receipt_out(saved)

    def create_receipt(self, payment_voucher_id: int, *, actor, **values):
        voucher = self._voucher(payment_voucher_id)
        if voucher.status != PAYMENT_VOUCHER_PAID:
            raise AccountingConflict("Chỉ Phiếu chi/UNC đã chi mới được lập phiếu thu.")
        prepared = self._prepare_receipt(voucher, values, exclude_receipt_id=None)
        # Cấp số trước khi chạm ORM object (xem _next_voucher_doc_no).
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
            if not company_account.use_for_receipts:
                raise AccountingValidationError("Tài khoản này chưa được bật dùng để thu.")
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
            # Nợ/Có ĐỂ TRỐNG (chủ 21/08/2026: "cái nợ và có ấy thì họ điền gì kệ họ"). Hai cột
            # này không nuôi tính toán nào, chỉ IN ra phiếu — `printTT200` in sẵn dòng chấm khi
            # trống để kế toán tự ghi. Đúng ý ban đầu, xem mg 2288: "định khoản Nợ/Có NHẬP TAY".
            debit_account=None,
            credit_account=None,
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

    def create_sales_invoice_receipt(
        self, invoice_id: int, *, actor, **values
    ) -> dict:
        """Lập Phiếu thu đã thu tiền, gắn đích danh một hóa đơn bán còn nợ."""
        invoice = self.repo.get_sales_invoice(invoice_id)
        if invoice is None:
            raise AccountingNotFound("Không tìm thấy hóa đơn bán.")
        if invoice.status != SALES_INVOICE_ISSUED:
            raise AccountingConflict("Chỉ hóa đơn còn hiệu lực mới được lập phiếu thu.")
        prepared = self._prepare_other_receipt(values)
        receipt_date = prepared.get("receipt_date")
        if receipt_date is not None and receipt_date < invoice.invoice_date:
            raise AccountingValidationError("Ngày thu không được trước ngày hóa đơn.")
        money_row = next(
            (
                row
                for row in self._receivable_rows(customer_id=invoice.customer_id)
                if row["invoice_id"] == invoice.id
            ),
            None,
        )
        remaining = money_row["remaining_amount"] if money_row else 0
        if int(prepared["amount_vnd"]) > remaining:
            raise AccountingValidationError(
                f"Số tiền thu vượt quá phần hóa đơn còn phải thu ({remaining:,} đ)."
            )
        account = prepared.pop("company_account")
        doc_no = self.sequences.generate_flat_code(SEQ_DOC_TYPE_PAYMENT_RECEIPT)
        receipt = PaymentReceipt(
            code=self._new_receipt_code(),
            doc_no=doc_no,
            source_type=RECEIPT_SOURCE_SALES_INVOICE,
            sales_invoice_id=invoice.id,
            # Cố ý không gắn order_id: tiền này là THU HÓA ĐƠN, không được làm cổng cọc nhích lên.
            order_id=None,
            order_no_snapshot=invoice.order.order_no,
            customer_name_snapshot=invoice.customer_name_snapshot,
            status=PAYMENT_RECEIPT_RECEIVED,
            created_by_user_id=actor.id,
            received_by_user_id=actor.id,
            received_at=_now(),
        )
        for key, value in prepared.items():
            setattr(receipt, key, value)
        receipt.company_bank_account_id = account.id if account else None
        receipt.company_account_holder_snapshot = account.account_holder if account else None
        receipt.company_account_number_snapshot = account.account_number if account else None
        receipt.company_bank_name_snapshot = account.bank_name if account else None
        receipt.company_bank_branch_snapshot = account.bank_branch if account else None
        saved = self.repo.save_receipt(receipt)
        self.audit.create(
            actor_user_id=actor.id,
            action="create_sales_invoice_receipt",
            target=f"payment_receipt:{saved.id}",
            detail=f"{saved.code} <- HĐ {invoice.invoice_number}",
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
        if receipt.source_type == RECEIPT_SOURCE_OTHER:
            raise AccountingConflict("Phiếu thu khác đã ghi nhận tiền, không sửa trực tiếp.")
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
        if receipt.status == PAYMENT_RECEIPT_CANCELLED:
            raise AccountingConflict("Phiếu thu đã hủy.")
        if receipt.source_type in (RECEIPT_SOURCE_OTHER, RECEIPT_SOURCE_SALES_INVOICE):
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

    def _prepare_other_receipt(self, values: dict) -> dict:
        receipt_method = (values.get("receipt_method") or "").strip()
        if receipt_method not in PAYMENT_VOUCHER_TYPES:
            raise AccountingValidationError("Hình thức thu không hợp lệ.")
        payer_name = _text(
            values.get("payer_name"), label="Người nộp tiền", required=True, max_length=255
        )
        amount = int(values.get("amount") or 0)
        if amount <= 0:
            raise AccountingValidationError("Số tiền thu phải lớn hơn 0.")
        content = _text(values.get("content"), label="Nội dung thu", required=True, max_length=500)
        company_account = None
        bank_reference = _text(values.get("bank_reference"), label="Mã giao dịch", max_length=64)
        if receipt_method == VOUCHER_BANK_TRANSFER:
            account_id = values.get("company_bank_account_id")
            company_account = (
                self.repo.get_company_account(int(account_id)) if account_id else None
            )
            if company_account is None or not company_account.is_active:
                raise AccountingValidationError(
                    "Vui lòng chọn tài khoản công ty đang hoạt động."
                )
            if not company_account.use_for_receipts:
                raise AccountingValidationError("Tài khoản này chưa được bật dùng để thu.")
            if company_account.currency != "VND":
                raise AccountingValidationError("Phiếu thu khác hiện chỉ nhận VND.")
            if not bank_reference:
                raise AccountingValidationError(
                    "Thu qua ngân hàng phải có mã giao dịch hoặc số báo có."
                )
        return {
            "payer_name": payer_name,
            "payer_address": _text(
                values.get("payer_address"), label="Địa chỉ người nộp", max_length=500
            ),
            "receipt_method": receipt_method,
            "receipt_date": values.get("receipt_date"),
            "debit_account": _text(values.get("debit_account"), label="Tài khoản Nợ", max_length=64)
            or ("1121" if receipt_method == VOUCHER_BANK_TRANSFER else "1111"),
            "credit_account": _text(values.get("credit_account"), label="Tài khoản Có", max_length=64),
            "amount": amount,
            "amount_vnd": amount,
            "currency": "VND",
            "exchange_rate": 1,
            "content": content,
            "bank_reference": bank_reference,
            "note": _text(values.get("note"), label="Ghi chú", max_length=2000),
            "company_account": company_account,
        }

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
            if not company_account.use_for_receipts:
                raise AccountingValidationError("Tài khoản này chưa được bật dùng để thu.")
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
            "order_id": (
                row.order_id
                if row.order_id is not None
                else (row.sales_invoice.order_id if row.sales_invoice else None)
            ),
            "order_code": row.order_no_snapshot,
            "customer_name": row.customer_name_snapshot,
            "sales_invoice_id": row.sales_invoice_id,
            "sales_invoice_number": (
                row.sales_invoice.invoice_number if row.sales_invoice else None
            ),
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

    def _clean_bank_account(self, values: dict, *, include_usage: bool = False) -> dict:
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
        if include_usage:
            cleaned["use_for_receipts"] = bool(values.get("use_for_receipts", True))
            cleaned["use_for_payments"] = bool(values.get("use_for_payments", True))
        if len(cleaned["currency"]) != 3:
            raise AccountingValidationError("Loại tiền phải gồm 3 ký tự, ví dụ VND.")
        if cleaned["is_default"] and not cleaned["is_active"]:
            raise AccountingValidationError("Tài khoản mặc định phải đang hoạt động.")
        if include_usage and not cleaned["use_for_receipts"] and not cleaned["use_for_payments"]:
            raise AccountingValidationError("Tài khoản công ty phải dùng để thu, để chi hoặc cả hai.")
        return cleaned

    def _prepare_voucher(
        self,
        purchase: PurchaseRequest,
        values: dict,
        *,
        allow_pending_purchase: bool,
        exclude_voucher_id: int | None,
    ) -> dict:
        # `PR_PARTIALLY_RECEIVED` BẮT BUỘC có mặt: đơn giao dở dang chính là ca sinh ra công nợ
        # thường xuyên nhất. Thiếu nó thì hàng về đợt 1, nợ hiện lên màn kế toán, mà bấm trả tiền
        # lại bị chặn "chưa đủ điều kiện" — nợ treo vĩnh viễn không có đường thanh toán.
        allowed_statuses = (PR_APPROVED, PR_PURCHASED, PR_PARTIALLY_RECEIVED, PR_RECEIVED)
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
        # ĐỢT GIAO mà phiếu này trả cho. Cọc thì không có đợt nào để gắn (hàng chưa về); thanh toán
        # thì bắt buộc chỉ rõ đợt — không có nó thì công nợ biết TỔNG đã trả nhưng không biết đợt
        # nào đã xong, và cột Quá hạn (tính theo hạn trả của từng đợt) không quy được về đâu.
        delivery_id = values.get("delivery_id")
        if stage == PAYMENT_STAGE_ADVANCE:
            if delivery_id is not None:
                raise AccountingValidationError(
                    "Phiếu đặt cọc không gắn với đợt giao nào — cọc là tiền chi trước khi hàng về."
                )
            # CỌC phải được KHAI TRƯỚC trên phiếu mua (chủ chốt 09/08/2026). Không khai mà vẫn chi
            # được thì con số "Cọc dự kiến" chỉ là trang trí, và không có gì để đối chiếu với thoả
            # thuận đã ký.
            if int(getattr(purchase, "deposit_expected", 0) or 0) <= 0:
                raise AccountingValidationError(
                    "Phiếu mua này chưa khai Cọc dự kiến. Khai số cọc đã thoả thuận ở phần Hợp đồng "
                    "trên phiếu mua trước, rồi mới lập phiếu đặt cọc."
                )
        else:
            # THANH TOÁN bắt buộc gắn ĐỢT GIAO (chủ chốt 09/08/2026).
            #
            # Trước đó đơn chưa có đợt vẫn chi được với `delivery_id = None` — mở đường cho tiền ra
            # khỏi két mà không có mốc "hàng đã về đợt nào". Khi đó công nợ biết tổng đã trả nhưng
            # không biết đợt nào xong, và cột Quá hạn (tính theo hạn của TỪNG đợt) không quy được
            # về đâu.
            #
            # ⚠️ Hệ quả đã lường: đơn CŨ chưa có đợt sẽ KHÔNG trả tiền được cho tới khi ghi đợt
            # giao. Đơn đã ở trạng thái "Đã nhận" thì phải bấm "Mở lại đơn" mới ghi đợt được — chủ
            # đã chấp nhận ngày 09/08/2026 (dữ liệu đang là dữ liệu test).
            if not purchase.deliveries:
                raise AccountingValidationError(
                    "Phiếu mua này chưa có đợt giao nào. Ghi đợt giao trước — hoặc lập phiếu ĐẶT CỌC "
                    "nếu hàng chưa về."
                )
            if delivery_id is None:
                raise AccountingValidationError(
                    "Phiếu thanh toán phải chọn đợt giao. Chưa có đợt nào thì đây là tiền đặt cọc."
                )
            if not any(d.id == delivery_id for d in purchase.deliveries):
                raise AccountingValidationError("Đợt giao không thuộc phiếu mua này.")

        tran = self._tran_lap_phieu(purchase, stage, delivery_id)
        # Sửa một phiếu ĐÃ CHI: số tiền cũ của chính nó đang nằm trong `net_paid` nên đã bị trừ khỏi
        # trần — cộng lại, nếu không thì mở phiếu ra sửa mỗi dòng nội dung cũng bị báo "vượt trần".
        #
        # Chỉ cộng lại khi phiếu cũ đóng góp vào ĐÚNG cái trần đang tính: đổi phiếu từ đợt 1 sang
        # đợt 2 thì số cũ nằm ở trần của đợt 1, cộng nó vào trần đợt 2 là nới sai.
        if exclude_voucher_id is not None:
            cu = next(
                (
                    v
                    for v in purchase.payment_vouchers
                    if v.id == exclude_voucher_id and v.status == PAYMENT_VOUCHER_PAID
                ),
                None,
            )
            if cu is not None:
                cu_la_coc = cu.payment_stage == PAYMENT_STAGE_ADVANCE
                dang_la_coc = stage == PAYMENT_STAGE_ADVANCE
                cung_dich = (
                    cu_la_coc
                    if dang_la_coc
                    else (not cu_la_coc and getattr(cu, "delivery_id", None) == delivery_id)
                )
                if cung_dich:
                    tran += int(cu.amount_vnd)
        if amount_vnd > tran:
            if stage == PAYMENT_STAGE_ADVANCE:
                nhan = "đặt cọc cho đơn này"
            elif delivery_id is not None:
                seq = next(
                    (d.seq_no for d in purchase.deliveries if d.id == delivery_id), None
                )
                nhan = f"thanh toán cho đợt {seq}" if seq else "thanh toán cho đợt này"
            else:
                nhan = "thanh toán"
            raise AccountingValidationError(
                f"Số tiền quy đổi vượt quá số còn được phép {nhan} ({tran:,} đ). "
                "Trả cho nhiều đợt thì lập nhiều phiếu, mỗi phiếu một đợt."
            )
        content = _text(values.get("content"), label="Nội dung chi", required=True, max_length=500)

        company_account = None
        cash_recipient_name = _text(
            values.get("cash_recipient_name"), label="Người nhận tiền", max_length=255
        )
        beneficiary_holder = _text(
            values.get("beneficiary_account_holder"),
            label="Tên chủ tài khoản thụ hưởng",
            max_length=255,
        )
        beneficiary_number = _text(
            values.get("beneficiary_account_number"),
            label="Số tài khoản thụ hưởng",
            max_length=64,
        )
        beneficiary_bank_name = _text(
            values.get("beneficiary_bank_name"),
            label="Ngân hàng thụ hưởng",
            max_length=255,
        )
        beneficiary_bank_branch = _text(
            values.get("beneficiary_bank_branch"),
            label="Chi nhánh thụ hưởng",
            max_length=255,
        )
        bank_fee_bearer = _text(
            values.get("bank_fee_bearer"), label="Bên chịu phí", max_length=16
        )
        if voucher_type == VOUCHER_CASH:
            if not cash_recipient_name:
                raise AccountingValidationError("Phiếu chi phải có người nhận tiền.")
        else:
            company_id = values.get("company_bank_account_id")
            company_account = self.repo.get_company_account(int(company_id)) if company_id else None
            if company_account is None or not company_account.is_active:
                raise AccountingValidationError("Vui lòng chọn tài khoản công ty đang hoạt động.")
            if not company_account.use_for_payments:
                raise AccountingValidationError("Tài khoản này chưa được bật dùng để chi.")
            if company_account.currency != currency:
                raise AccountingValidationError("Loại tiền của chứng từ phải khớp tài khoản trích nợ.")
            if not beneficiary_holder or not beneficiary_number or not beneficiary_bank_name:
                raise AccountingValidationError(
                    "UNC phải có tên chủ tài khoản, số tài khoản và ngân hàng thụ hưởng."
                )
            bank_fee_bearer = bank_fee_bearer or BANK_FEE_PAYER
            if bank_fee_bearer not in BANK_FEE_BEARERS:
                raise AccountingValidationError("Bên chịu phí ngân hàng không hợp lệ.")

        # HẠN TRẢ thôi bắt buộc từ 06/08/2026: phiếu chi giờ là tiền ĐÃ RA nên nó không có hạn trả.
        # Hạn trả chuyển lên ĐỢT GIAO (`purchase_deliveries.due_date`, mặc định ngày giao +
        # `suppliers.credit_days`) — đó mới là chỗ món nợ phát sinh và cần bị canh.
        # Cột `planned_payment_date` giữ lại cho dữ liệu cũ, không đọc ở đâu nữa.
        han_tra = values.get("planned_payment_date")
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
        if han_tra is not None and ngay_ct is not None and han_tra < ngay_ct:
            raise AccountingValidationError("Hạn trả tiền không được trước ngày chứng từ.")
        return {
            "source_type": VOUCHER_SOURCE_PURCHASE,
            "voucher_type": voucher_type,
            "payment_stage": stage,
            "delivery_id": delivery_id,
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
            # Tài khoản NCC không còn quản lý theo danh mục. UNC chụp thông tin thụ hưởng mà
            # kế toán nhập trên chính chứng từ, để chứng từ cũ không đổi khi NCC đổi tài khoản.
            "supplier_account": None,
            "cash_recipient_name": cash_recipient_name,
            "cash_recipient_address": _text(values.get("cash_recipient_address"), label="Địa chỉ người nhận", max_length=500),
            "cash_recipient_identity": _text(values.get("cash_recipient_identity"), label="Giấy tờ người nhận", max_length=64),
            "beneficiary_account_holder_snapshot": beneficiary_holder,
            "beneficiary_account_number_snapshot": beneficiary_number,
            "beneficiary_bank_name_snapshot": beneficiary_bank_name,
            "beneficiary_bank_branch_snapshot": beneficiary_bank_branch,
            "bank_fee_bearer": bank_fee_bearer,
            "debit_account": _text(values.get("debit_account"), label="Tài khoản Nợ", max_length=64),
            "credit_account": _text(values.get("credit_account"), label="Tài khoản Có", max_length=64),
            "note": _text(values.get("note"), label="Ghi chú", max_length=2000),
        }

    def _prepare_standalone_voucher(self, values: dict, *, advance=None) -> dict:
        source_type = (values.get("source_type") or "").strip()
        if advance is not None:
            source_type = VOUCHER_SOURCE_SALARY_ADVANCE
            # Số tiền và người nhận LẤY TỪ PHIẾU TẠM ỨNG, không nhận từ payload — nếu không thì
            # kế toán gõ số khác số đã duyệt và phiếu chi không còn khớp phiếu duyệt.
            values = dict(values)
            values["amount"] = int(round(float(advance.amount)))
            values["cash_recipient_name"] = self._ten_nhan_vien(advance.employee_id)
        elif source_type not in (
            VOUCHER_SOURCE_INTERNAL,
            VOUCHER_SOURCE_CUSTOMER_REFUND,
            VOUCHER_SOURCE_OTHER,
        ):
            raise AccountingValidationError("Nguồn chi độc lập không hợp lệ.")
        voucher_type = (values.get("voucher_type") or "").strip()
        if voucher_type not in PAYMENT_VOUCHER_TYPES:
            raise AccountingValidationError("Loại chứng từ không hợp lệ.")
        amount = int(values.get("amount") or 0)
        if amount <= 0:
            raise AccountingValidationError("Số tiền chi phải lớn hơn 0.")
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
        voucher_date = values.get("voucher_date")
        if voucher_date is None:
            raise AccountingValidationError("Phiếu chi phải có ngày chứng từ.")
        today = _business_today()
        if voucher_date > today:
            raise AccountingValidationError("Ngày chứng từ không được ở tương lai.")
        invoice_date = values.get("invoice_date")
        if invoice_date is not None and invoice_date > today:
            raise AccountingValidationError("Ngày hóa đơn không được ở tương lai.")

        recipient_name = _text(
            values.get("cash_recipient_name"), label="Người nhận tiền", required=True, max_length=255
        )
        recipient_address = _text(
            values.get("cash_recipient_address"), label="Địa chỉ người nhận", max_length=500
        )
        company_account = None
        bank_fee_bearer = _text(values.get("bank_fee_bearer"), label="Bên chịu phí", max_length=16)
        beneficiary_holder = _text(
            values.get("beneficiary_account_holder"), label="Tên người thụ hưởng", max_length=255
        )
        beneficiary_number = _text(
            values.get("beneficiary_account_number"), label="Số tài khoản thụ hưởng", max_length=64
        )
        beneficiary_bank_name = _text(
            values.get("beneficiary_bank_name"), label="Ngân hàng thụ hưởng", max_length=255
        )
        beneficiary_bank_branch = _text(
            values.get("beneficiary_bank_branch"), label="Chi nhánh thụ hưởng", max_length=255
        )
        if voucher_type == VOUCHER_BANK_TRANSFER:
            company_id = values.get("company_bank_account_id")
            company_account = self.repo.get_company_account(int(company_id)) if company_id else None
            if company_account is None or not company_account.is_active:
                raise AccountingValidationError("Vui lòng chọn tài khoản công ty đang hoạt động.")
            if not company_account.use_for_payments:
                raise AccountingValidationError("Tài khoản này chưa được bật dùng để chi.")
            if company_account.currency != currency:
                raise AccountingValidationError("Loại tiền của chứng từ phải khớp tài khoản trích nợ.")
            if not beneficiary_holder or not beneficiary_number or not beneficiary_bank_name:
                raise AccountingValidationError("UNC độc lập phải có tên, số tài khoản và ngân hàng thụ hưởng.")
            bank_fee_bearer = bank_fee_bearer or BANK_FEE_PAYER
            if bank_fee_bearer not in BANK_FEE_BEARERS:
                raise AccountingValidationError("Bên chịu phí ngân hàng không hợp lệ.")

        source_labels = {
            VOUCHER_SOURCE_INTERNAL: "Chi phí nội bộ",
            VOUCHER_SOURCE_CUSTOMER_REFUND: "Hoàn tiền khách hàng",
            VOUCHER_SOURCE_OTHER: "Khác",
        }
        # Phiếu tạm ứng: mã nguồn in trên chứng từ là MÃ PHIẾU TẠM ỨNG (TU26-0001), để lần ngược
        # từ sổ quỹ về đúng phiếu đã duyệt.
        return {
            "salary_advance_id": advance.id if advance is not None else None,
            "source_type": source_type,
            "voucher_type": voucher_type,
            "payment_stage": "other",
            "delivery_id": None,
            "voucher_date": voucher_date,
            "planned_payment_date": None,
            "amount": amount,
            "amount_vnd": amount_vnd,
            "currency": currency,
            "exchange_rate": exchange_rate,
            "content": _text(values.get("content"), label="Nội dung chi", required=True, max_length=500),
            "invoice_number": _text(values.get("invoice_number"), label="Số hóa đơn", max_length=64),
            "invoice_date": invoice_date,
            "contract_number": _text(values.get("contract_number"), label="Số hợp đồng", max_length=64),
            "company_account": company_account,
            "supplier_account": None,
            "cash_recipient_name": recipient_name,
            "cash_recipient_address": recipient_address,
            "cash_recipient_identity": _text(
                values.get("cash_recipient_identity"), label="Giấy tờ người nhận", max_length=64
            ),
            "bank_fee_bearer": bank_fee_bearer,
            "debit_account": _text(values.get("debit_account"), label="Tài khoản Nợ", max_length=64),
            "credit_account": _text(values.get("credit_account"), label="Tài khoản Có", max_length=64),
            "note": _text(values.get("note"), label="Ghi chú", max_length=2000),
            "source_code_snapshot": (advance.code or f"TU#{advance.id}") if advance is not None
                                    else source_labels[source_type],
            "supplier_name_snapshot": recipient_name,
            "supplier_tax_code_snapshot": None,
            "supplier_address_snapshot": recipient_address,
            "beneficiary_account_holder_snapshot": beneficiary_holder,
            "beneficiary_account_number_snapshot": beneficiary_number,
            "beneficiary_bank_name_snapshot": beneficiary_bank_name,
            "beneficiary_bank_branch_snapshot": beneficiary_bank_branch,
        }

    def _next_voucher_doc_no(self) -> str:
        """Số IN trên mẫu 02-TT (PC00445) — chung bộ đếm cho tiền mặt lẫn UNC.

        Bộ đếm nay đi CHUNG giao dịch (không còn tự commit — xem
        DocumentSequenceRepository.increment_and_get), nên phiếu hỏng thì số cấp dở trả lại.
        Vẫn giữ nếp gọi SAU khi validate xong: số nhảy vô ích cũng là số mất.
        """
        return self.sequences.generate_flat_code(SEQ_DOC_TYPE_PAYMENT_VOUCHER)

    def _new_voucher(
        self, purchase: PurchaseRequest | None, prepared: dict, actor_id: int, *, doc_no: str | None = None
    ) -> PaymentVoucher:
        # LẬP PHIẾU CHI = TIỀN ĐÃ RA (chủ chốt 06/08/2026, Đ1). Không còn khoảng "chờ chi" giữa
        # việc viết phiếu và việc tiền rời két, nên phiếu sinh ra đã là `paid` và mang luôn người
        # chi + mốc chi. `paid_at` lấy NGÀY CHỨNG TỪ chứ không lấy giờ bấm: hoá đơn về muộn thì phiếu
        # mang ngày 28/7 phải rơi vào kỳ kế toán tháng 7, không phải kỳ của hôm nhập liệu.
        voucher = PaymentVoucher(
            code=self._new_voucher_code(prepared["voucher_type"]),
            doc_no=doc_no,
            purchase_request_id=purchase.id if purchase else None,
            supplier_id=purchase.supplier_id if purchase else None,
            status=PAYMENT_VOUCHER_PAID,
            created_by_user_id=actor_id,
            paid_by_user_id=actor_id,
            paid_at=datetime.combine(
                prepared["voucher_date"], time(0, 0), tzinfo=timezone.utc
            ),
        )
        self._apply_voucher(voucher, purchase, prepared)
        return voucher

    def _apply_voucher(self, voucher: PaymentVoucher, purchase: PurchaseRequest | None, prepared: dict) -> None:
        company = prepared.pop("company_account")
        beneficiary = prepared.pop("supplier_account")
        for key, value in prepared.items():
            setattr(voucher, key, value)
        voucher.company_bank_account_id = company.id if company else None
        voucher.supplier_bank_account_id = beneficiary.id if beneficiary else None
        if purchase is not None:
            voucher.source_code_snapshot = purchase.code
            voucher.supplier_id = purchase.supplier_id
            voucher.supplier_name_snapshot = purchase.supplier.name
            voucher.supplier_tax_code_snapshot = purchase.supplier.tax_code
            voucher.supplier_address_snapshot = purchase.supplier.address
        voucher.company_account_holder_snapshot = company.account_holder if company else None
        voucher.company_account_number_snapshot = company.account_number if company else None
        voucher.company_bank_name_snapshot = company.bank_name if company else None
        voucher.company_bank_branch_snapshot = company.bank_branch if company else None
        if beneficiary is not None:
            voucher.beneficiary_account_holder_snapshot = beneficiary.account_holder
            voucher.beneficiary_account_number_snapshot = beneficiary.account_number
            voucher.beneficiary_bank_name_snapshot = beneficiary.bank_name
            voucher.beneficiary_bank_branch_snapshot = beneficiary.bank_branch

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

    def _advance_cho_phieu_chi(self, salary_advance_id: int | None):
        """Phiếu tạm ứng hợp lệ để lập phiếu chi. Bốn chốt, theo đúng chốt của chủ 18/08/2026."""
        if salary_advance_id is None:
            raise AccountingValidationError("Phiếu chi từ tạm ứng phải chọn phiếu tạm ứng nguồn.")
        if self._payroll is None:
            raise AccountingValidationError("Chưa nối được phân hệ Lương để đọc phiếu tạm ứng.")
        a = self._payroll.get_advance(int(salary_advance_id))
        if a is None:
            raise AccountingNotFound("Không tìm thấy phiếu tạm ứng.")
        # CHỐT 1 — CHỈ phiếu ĐÃ DUYỆT. Phiếu chờ duyệt / từ chối / đã huỷ đều không được chi.
        if a.status != "approved":
            raise AccountingValidationError(
                "Chỉ lập phiếu chi cho phiếu tạm ứng ĐÃ DUYỆT."
            )
        # CHỐT 2 — một phiếu tạm ứng chỉ một phiếu chi (DB cũng có UNIQUE chặn song song).
        if self.repo.get_voucher_by_salary_advance(a.id) is not None:
            raise AccountingConflict(
                f"Phiếu tạm ứng {a.code or a.id} đã có phiếu chi rồi."
            )
        return a

    def _ten_nhan_vien(self, employee_id: int) -> str:
        if self._employees is None:
            raise AccountingValidationError("Chưa nối được phân hệ Nhân sự để lấy tên người nhận.")
        emp = self._employees.get_by_id(employee_id)
        if emp is None:
            raise AccountingNotFound("Không tìm thấy nhân viên của phiếu tạm ứng.")
        return emp.full_name

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

    def _tran_lap_phieu(
        self, purchase: PurchaseRequest, stage: str, delivery_id: int | None
    ) -> int:
        """Số tối đa được phép lập phiếu chi, KHÁC NHAU theo loại phiếu (Đ1/§5.4).

        - **ĐẶT CỌC / ứng trước** — trần = **CỌC DỰ KIẾN đã khai** trừ cọc đã chi (chủ chốt
          09/08/2026). Lập được NHIỀU phiếu cọc, miễn tổng không vượt số đã khai. Chưa khai ⇒ chặn
          ngay từ vòng kiểm phía trên, không tới được đây.
        - **THANH TOÁN gắn đợt** — trần đúng bằng phần **CÒN NỢ CỦA CHÍNH ĐỢT ĐÓ**.
        - THANH TOÁN nay BẮT BUỘC gắn đợt, nên nhánh "không gắn đợt" chỉ còn là lưới an toàn.

        ⚠️ TRẦN THEO ĐỢT LÀ CHỐT QUAN TRỌNG, đừng nới về mức đơn (lỗi 07/08/2026):
        trước đó trần lấy `outstanding_amount` của CẢ ĐƠN, nên kế toán chọn "Đợt 2" rồi gõ 75tr cho
        một đợt trị giá 35tr vẫn qua. 40tr thừa chảy vào rổ cọc chung rồi lặng lẽ trả hộ **Đợt 1**
        — món nợ 50tr của đợt 1 biến mất khỏi màn Công nợ mà không ai bấm gì. Đúng bệnh GIẤU NỢ mà
        cả phân hệ này sinh ra để chữa, chỉ khác đường vào.

        Trả cho nhiều đợt bằng một lần chuyển khoản thì lập nhiều phiếu — mỗi phiếu nói rõ nó tất
        toán đợt nào. Đó cũng là thứ đem đi đối chiếu với sao kê NCC được."""
        money = purchase_money(purchase)
        if stage == PAYMENT_STAGE_ADVANCE:
            return money["tran_dat_coc"]
        if delivery_id is None:
            return money["outstanding_amount"]
        dots, _coc, _du = self._no_tung_dot(purchase)
        return next((d["con_no"] for d in dots if d["delivery_id"] == delivery_id), 0)

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
            "source_type": row.source_type or VOUCHER_SOURCE_PURCHASE,
            "salary_advance_id": row.salary_advance_id,
            "receipt_received_amount": receipt_received_amount,
            "receipt_pending_amount": receipt_pending_amount,
            "attachment_count": len(row.attachments),
            # Đợt giao mà phiếu này trả cho. NULL = phiếu đặt cọc (hoặc phiếu cũ trước 06/08/2026,
            # khi chưa có khái niệm đợt giao) — màn hình hiện "cả đơn" cho hai ca đó.
            "delivery_id": getattr(row, "delivery_id", None),
            "delivery_seq_no": next(
                (
                    d.seq_no
                    for d in (purchase.deliveries if purchase else [])
                    if d.id == getattr(row, "delivery_id", None)
                ),
                None,
            ),
            "purchase_request_id": row.purchase_request_id,
            "purchase_request_code": purchase.code if purchase else row.source_code_snapshot,
            "purchase_request_total": purchase_total,
            "purchase_paid_amount": purchase_paid_amount,
            # Người phụ trách mua (lập PMH) — mặc định "Người nộp tiền" của phiếu thu.
            "purchase_created_by_user_id": (
                purchase.created_by_user_id if purchase else None
            ),
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
