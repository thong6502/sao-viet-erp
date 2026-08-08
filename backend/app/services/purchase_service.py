"""Business service for Thu mua MVP."""
from __future__ import annotations

import secrets
import string
import unicodedata
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from ..models.role import SCOPE_ALL, SCOPE_DEPARTMENT, SCOPE_OWN
from ..models.purchase import (
    DEPARTMENT_PURCHASE_SOURCE_TYPES,
    DPR_CANCELLED,
    DPR_DONE,
    DPR_IN_PURCHASE,
    DPR_OPEN,
    DPR_PENDING_APPROVAL,
    DepartmentPurchaseRequest,
    PR_APPROVED,
    PR_CANCELLED,
    PR_DRAFT,
    PR_PENDING,
    PR_PURCHASED,
    PR_RECEIVED,
    PR_REJECTED,
    SUPPLIER_ACTIVE,
    SUPPLIER_INACTIVE,
    SUPPLIER_STATUSES,
    PurchaseRequest,
    SOURCE_CONG_NGHE,
    SOURCE_GIA_CONG_NGOAI,
    SOURCE_KHAC,
    SOURCE_KHO,
    SOURCE_KINH_DOANH,
    SOURCE_SAN_XUAT,
    Supplier,
)
from ..models.accounting import (
    PAYMENT_RECEIPT_RECEIVED,
    PAYMENT_VOUCHER_PAID,
    PAYMENT_VOUCHER_WAITING,
)
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.purchase_repo import (
    DepartmentPurchaseRequestLineInput,
    DepartmentPurchaseRequestRepository,
    PurchaseRequestLineInput,
    PurchaseRequestRepository,
    SupplierItemInput,
    SupplierRepository,
)
from ..repositories.rbac_repo import DepartmentRepository
from ..repositories.user_repo import UserRepository
from .rbac_service import AuthorizationService


# Những module được cấp quyền ĐỌC danh sách YCMH. Router dựng cổng quyền từ đúng danh sách này
# (`DEPARTMENT_REQUEST_READERS`), nên hai nơi không thể lệch nhau.
#
# Dùng cả cho việc co danh sách về phòng ban: ai có scope `all` ở BẤT KỲ module nào trong đây thì
# thấy YCMH toàn công ty. Chỉ hỏi mỗi `thu_mua` là sai — kế toán (SEAM-25) truy vết YCMH nguồn từ
# PMH/Phiếu chi mà KHÔNG hề có quyền `thu_mua`, `scope_for` trả None nên bị co về phòng Kế toán và
# nhìn thấy RỖNG. Người chỉ có scope phòng ban thì vẫn bị co như cũ.
DEPARTMENT_REQUEST_READER_MODULES = (
    "thu_mua",
    "bao_gia",
    "kho",
    "san_xuat",
    "dm_giay_vat_tu",
    "ke_toan",
)


# Những module được cấp quyền ĐỌC phiếu mua hàng. Ai có scope `all` ở BẤT KỲ module nào trong đây
# thì thấy phiếu của toàn công ty.
#
# ⚠️ Phải có `ke_toan`: màn Đơn mua hàng của kế toán (`/api/accounting/inbox`) gọi CHUNG
# `list_requests`, mà kế toán KHÔNG có quyền `thu_mua` ⇒ `scope_for` trả None ⇒ bị co về "của
# mình" ⇒ thấy RỖNG. Đúng cái bẫy đã sập với YCMH — đừng lặp lại.
PURCHASE_REQUEST_READER_MODULES = ("thu_mua", "ke_toan")


# Thang bậc tiến độ của một phiếu mua, dùng để SUY trạng thái yêu cầu mua hàng (xem
# `_tinh_lai_trang_thai_ycmh`).
#
# BỊ TỪ CHỐI / ĐÃ HUỶ = bậc 0: phần hàng đó chưa ai mua được, nên yêu cầu phải quay về "Chờ mua"
# để thu mua lập phiếu khác — `create` chỉ nhận yêu cầu đang "Chờ mua" nên để bậc cao hơn là chặn
# mất đường lập lại. Bỏ qua hẳn cũng sai: có ngày báo "Xong" trong khi một nửa đơn bị từ chối.
#
# NHÁP = bậc 1 (Chờ duyệt), KHÔNG phải 0. Trông lệch nhưng đúng với hệ: `_replace_sources`
# (purchase_repo.py) đẩy yêu cầu sang "Chờ duyệt" ngay khi thu mua TẠO phiếu, kể cả phiếu còn nháp
# — đó là cách hệ GIỮ CHỖ yêu cầu để người thứ hai không lập phiếu chồng lên. Để bậc 0 thì suy ra
# một đằng, repo ghi một nẻo, và chỗ giữ chỗ vỡ.
#
# ⚠️ Việc repo tự đặt trạng thái nghiệp vụ là SAI TẦNG. Gỡ được thì phải tách "giữ chỗ" ra khỏi
# "trạng thái" — ngoài phạm vi đợt này, ghi lại đây để đợt sau còn biết đường.
_BAC_PHIEU = {
    PR_REJECTED: 0,
    PR_CANCELLED: 0,
    PR_DRAFT: 1,
    PR_PENDING: 1,
    PR_APPROVED: 2,
    PR_PURCHASED: 2,
    PR_RECEIVED: 3,
}

_BAC_SANG_TRANG_THAI = {
    0: DPR_OPEN,
    1: DPR_PENDING_APPROVAL,
    2: DPR_IN_PURCHASE,
    3: DPR_DONE,
}


class PurchaseError(Exception):
    pass


class PurchaseValidationError(PurchaseError):
    pass


class PurchaseNotFound(PurchaseError):
    pass


class PurchaseConflict(PurchaseError):
    pass


class PurchaseForbidden(PurchaseError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _business_today() -> date:
    return datetime.now(ZoneInfo("Asia/Bangkok")).date()


def _money_round(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _purchase_line_amounts(
    *,
    quantity: float,
    unit_price: int,
    discount_percent: float,
    vat_percent: float,
) -> tuple[int, int, int, int]:
    gross = _money_round(Decimal(str(quantity)) * Decimal(unit_price))
    discount = _money_round(Decimal(gross) * Decimal(str(discount_percent)) / Decimal(100))
    taxable = max(0, gross - discount)
    vat = _money_round(Decimal(taxable) * Decimal(str(vat_percent)) / Decimal(100))
    return gross, discount, vat, taxable + vat


def qty_thuc_nhan(line) -> float:
    """Số THỰC NHẬN của một dòng phiếu mua.

    `received_quantity` NULL = chưa ai khai ⇒ coi như nhận đủ số đã đặt. Nhờ quy ước này mọi phiếu
    lập trước 05/08/2026 giữ nguyên số tiền sau khi nâng cấp."""
    return float(line.quantity if line.received_quantity is None else line.received_quantity)


def purchase_money(row) -> dict:
    """MỘT nguồn số cho mọi con tiền của một phiếu mua hàng.

    Cả `_to_request_out` (màn Mua hàng / Đơn mua hàng) lẫn màn **Công nợ phải trả** đều gọi hàm
    này. Để hai bên tự cộng lấy là để hai bên lệch nhau — mà lệch TIỀN thì không ai phát hiện cho
    tới lúc ngồi đối chiếu với NCC.

    Hai tổng đi song song, đừng lẫn:
    - `total` — giá trị **đơn đặt**, theo `quantity`. Vẫn là con số in trên đơn.
    - `received_total` — giá trị hàng **thực nhận**, theo `received_quantity`.

    `tran` (trần) là số dùng để chốt còn nợ bao nhiêu và được lập phiếu chi tối đa bao nhiêu:
    hàng đã về ⇒ theo **thực nhận** (NCC giao 80% thì không cho lập phiếu 100%); hàng chưa về ⇒
    vẫn theo giá trị đơn, để còn đặt cọc / ứng trước được."""
    total = 0
    received_total = 0
    for line in row.lines:
        unit_price = int(line.expected_unit_price)
        discount_percent = float(line.discount_percent or 0)
        vat_percent = float(line.vat_percent or 0)
        _, _, _, line_total = _purchase_line_amounts(
            quantity=float(line.quantity),
            unit_price=unit_price,
            discount_percent=discount_percent,
            vat_percent=vat_percent,
        )
        _, _, _, line_received = _purchase_line_amounts(
            quantity=qty_thuc_nhan(line),
            unit_price=unit_price,
            discount_percent=discount_percent,
            vat_percent=vat_percent,
        )
        total += line_total
        received_total += line_received
    pending_amount = sum(
        int(voucher.amount_vnd)
        for voucher in row.payment_vouchers
        if voucher.status == PAYMENT_VOUCHER_WAITING
    )
    paid_amount = sum(
        int(voucher.amount_vnd)
        for voucher in row.payment_vouchers
        if voucher.status == PAYMENT_VOUCHER_PAID
    )
    # Tiền ĐÃ THU về (phiếu thu received) làm giảm số đã chi thực;
    # paid_amount giữ số thô để UI hiện tách bạch "đã chi X, đã thu Y".
    receipt_received_amount = sum(
        int(receipt.amount_vnd)
        for voucher in row.payment_vouchers
        for receipt in voucher.receipts
        if receipt.status == PAYMENT_RECEIPT_RECEIVED
    )
    net_paid = paid_amount - receipt_received_amount
    tran = received_total if row.status == PR_RECEIVED else total
    outstanding_amount = max(0, tran - net_paid)
    available_amount = max(0, tran - net_paid - pending_amount)
    if tran > 0 and net_paid >= tran:
        payment_status = "paid"
    elif net_paid > 0 or pending_amount > 0:
        payment_status = "partial"
    else:
        payment_status = "unpaid"
    return {
        "total": total,
        "received_total": received_total,
        "tran": tran,
        "pending_amount": pending_amount,
        "paid_amount": paid_amount,
        "receipt_received_amount": receipt_received_amount,
        "net_paid": net_paid,
        "outstanding_amount": outstanding_amount,
        "available_amount": available_amount,
        "payment_status": payment_status,
    }


class PurchaseService:
    def __init__(
        self,
        suppliers: SupplierRepository,
        department_requests: DepartmentPurchaseRequestRepository,
        requests: PurchaseRequestRepository,
        users: UserRepository,
        departments: DepartmentRepository,
        audit: AuditLogRepository,
        authz: AuthorizationService,
        hang=None,
    ) -> None:
        self.suppliers = suppliers
        self.department_requests = department_requests
        self.requests = requests
        self.users = users
        self.departments = departments
        self.audit = audit
        self.authz = authz
        # `VatLieuKhoService` — tra danh mục gốc + quy đổi đơn vị, để bảng giá NCC gắn được về
        # mặt hàng và so được giá. None → bỏ qua phần gắn (giữ tương thích với test cũ).
        self.hang = hang

    # --- suppliers ---------------------------------------------------------

    def so_gia_ncc(self, hang_loai: str, hang_id: int) -> dict:
        """Các NCC bán MỘT mặt hàng, giá quy về ĐƠN VỊ GỐC để so ngang.

        Vì sao phải quy đổi mới so được: NCC A báo 1.020.000 đ/ram, NCC B báo 24.500 đ/kg — hai
        con số này không so trực tiếp được. Đưa cả hai về đ/<đơn vị gốc> thì mới biết ai rẻ.

        Dòng không quy đổi được KHÔNG bị loại (người dùng vẫn cần thấy NCC đó có bán) nhưng xếp
        CUỐI kèm lý do — xếp hạng một dòng chưa biết giá thật là mời chọn nhầm.
        """
        from .vat_lieu_kho_service import VatLieuKhoError

        info = self.hang.don_vi_cua_mat_hang(hang_loai, hang_id)
        rows: list[dict] = []
        for sup, it in self.suppliers.items_for_hang(hang_loai, hang_id):
            r = {
                "supplier_id": sup.id, "supplier_name": sup.name,
                "supplier_item_id": it.id, "unit": it.unit,
                "unit_price": int(it.unit_price or 0),
                "vat_percent": float(it.vat_percent or 0),
                "gia_quy_doi": None, "gia_quy_doi_vat": None,
                "dien_giai": None, "ly_do": None,
            }
            try:
                # 1 đơn vị NCC bán bằng `he_so_ve_goc` đơn vị gốc → giá/đơn-vị-gốc = giá ÷ hệ số.
                qd = self.hang.quy_ve_goc(hang_loai, hang_id, it.unit, 1)
                hs = qd["he_so_ve_goc"]
                if hs > 0:
                    gia = int(round(int(it.unit_price or 0) / hs))
                    r["gia_quy_doi"] = gia
                    r["gia_quy_doi_vat"] = int(round(gia * (1 + float(it.vat_percent or 0) / 100)))
                    r["dien_giai"] = qd["dien_giai"]
            except VatLieuKhoError as e:
                r["ly_do"] = str(e)
            rows.append(r)
        # `float("inf")` cho dòng chưa quy đổi được → luôn nằm cuối, không lẫn vào xếp hạng.
        rows.sort(key=lambda x: (x["gia_quy_doi"] if x["gia_quy_doi"] is not None else float("inf")))
        return {
            "hang_loai": hang_loai, "hang_id": hang_id,
            "hang_ma": info.get("ma"), "hang_ten": info.get("ten"),
            "don_vi_goc": info.get("don_vi_goc"), "don_vi_goc_ten": info.get("don_vi_goc_ten"),
            "items": rows,
        }

    def list_suppliers(
        self,
        *,
        q: str | None = None,
        status: str | None = None,
        supplier_group: str | None = None,
        sort: str = "name",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Supplier], int]:
        return self.suppliers.list(
            q=q, status=status, supplier_group=supplier_group, sort=sort, page=page, size=size
        )

    def get_supplier(self, supplier_id: int) -> Supplier:
        supplier = self.suppliers.get_by_id(supplier_id)
        if supplier is None:
            raise PurchaseNotFound("Không tìm thấy nhà cung cấp.")
        return supplier

    def _clean_supplier_values(self, **values) -> dict:
        name = (values.get("name") or "").strip()
        if not name:
            raise PurchaseValidationError("Tên nhà cung cấp không được trống.")
        tax_code = (values.get("tax_code") or "").strip()
        phone = (values.get("phone") or "").strip()
        email = (values.get("email") or "").strip()
        address = (values.get("address") or "").strip()
        contact_name = (values.get("contact_name") or "").strip()
        supplier_group = (values.get("supplier_group") or "").strip()
        required = [
            (tax_code, "Mã số thuế"),
            (phone, "Số điện thoại"),
            (email, "Email"),
            (address, "Địa chỉ"),
            (contact_name, "Người liên hệ"),
            (supplier_group, "Nhóm nhà cung cấp"),
        ]
        missing = [label for value, label in required if not value]
        if missing:
            raise PurchaseValidationError(
                "Nhà cung cấp thiếu thông tin bắt buộc: " + ", ".join(missing) + "."
            )
        status = values.get("status") or SUPPLIER_ACTIVE
        if status not in SUPPLIER_STATUSES:
            raise PurchaseValidationError("Trạng thái nhà cung cấp không hợp lệ.")
        items = self._clean_supplier_items(values.get("items") or [])
        return {
            "name": name,
            "tax_code": tax_code,
            "phone": phone,
            "email": email,
            "address": address,
            "contact_name": contact_name,
            "supplier_group": supplier_group,
            "payment_terms": (values.get("payment_terms") or "").strip() or None,
            "status": status,
            "note": (values.get("note") or "").strip() or None,
            "items": items,
        }

    def _clean_supplier_items(self, raw_items) -> list[SupplierItemInput]:
        items: list[SupplierItemInput] = []
        for raw in raw_items or []:
            get = raw.get if isinstance(raw, dict) else lambda key, default=None: getattr(raw, key, default)
            item_name = (get("item_name") or "").strip()
            unit = (get("unit") or "").strip()
            raw_price = get("unit_price", 0) or 0
            raw_vat = get("vat_percent", 0) or 0
            note = (get("note") or "").strip() or None
            if not item_name and not unit and not raw_price and not raw_vat and not note:
                continue
            if not item_name:
                raise PurchaseValidationError("Ten mat hang nha cung cap khong duoc trong.")
            if not unit:
                raise PurchaseValidationError("Don vi tinh mat hang nha cung cap khong duoc trong.")
            unit_price = int(raw_price)
            if unit_price <= 0:
                raise PurchaseValidationError("Don gia mat hang nha cung cap phai lon hon 0.")
            vat_percent = float(raw_vat)
            if vat_percent < 0 or vat_percent > 100:
                raise PurchaseValidationError("VAT mat hang nha cung cap phai tu 0 den 100.")
            hang_loai = (get("hang_loai") or "").strip() or None
            hang_id = get("hang_id") or None
            if (hang_loai is None) != (hang_id is None):
                raise PurchaseValidationError(
                    "Mat hang goc phai co ca loai lan ma — chon lai o o Vat tu."
                )
            if hang_loai is not None:
                # Đơn vị NCC bán phải nằm trong tập đổi được của mặt hàng, nếu không thì cột "giá
                # quy về đơn vị gốc" vĩnh viễn trống và dòng này không bao giờ so giá được.
                self._kiem_don_vi_ncc(hang_loai, int(hang_id), unit)
            items.append(
                SupplierItemInput(
                    hang_loai=hang_loai,
                    hang_id=int(hang_id) if hang_id else None,
                    item_name=item_name,
                    unit=unit,
                    unit_price=unit_price,
                    vat_percent=vat_percent,
                    note=note,
                )
            )
        return items

    def _kiem_don_vi_ncc(self, hang_loai: str, hang_id: int, unit: str) -> None:
        from .vat_lieu_kho_service import VatLieuKhoError

        if self.hang is None:
            return
        try:
            self.hang.quy_ve_goc(hang_loai, hang_id, unit, 1)
        except VatLieuKhoError as e:
            raise PurchaseValidationError(str(e)) from None

    def create_supplier(self, *, actor, **values) -> Supplier:
        cleaned = self._clean_supplier_values(**values)
        existing = self.suppliers.find_by_name(cleaned["name"])
        if existing is not None:
            raise PurchaseConflict("Nhà cung cấp đã tồn tại.")
        supplier = self.suppliers.create(**cleaned)
        self.audit.create(
            actor_user_id=actor.id,
            action="create_supplier",
            target=f"supplier:{supplier.id}",
            detail=supplier.name,
        )
        return supplier

    def update_supplier(self, supplier_id: int, *, actor, **values) -> Supplier:
        supplier = self.get_supplier(supplier_id)
        cleaned = self._clean_supplier_values(**values)
        existing = self.suppliers.find_by_name(cleaned["name"])
        if existing is not None and existing.id != supplier.id:
            raise PurchaseConflict("Nhà cung cấp đã tồn tại.")
        supplier = self.suppliers.update(supplier, **cleaned)
        self.audit.create(
            actor_user_id=actor.id,
            action="update_supplier",
            target=f"supplier:{supplier.id}",
            detail=supplier.name,
        )
        return supplier

    def toggle_supplier_active(self, supplier_id: int, *, actor) -> Supplier:
        supplier = self.get_supplier(supplier_id)
        next_status = SUPPLIER_INACTIVE if supplier.status == SUPPLIER_ACTIVE else SUPPLIER_ACTIVE
        supplier = self.suppliers.update(supplier, status=next_status)
        self.audit.create(
            actor_user_id=actor.id,
            action="toggle_supplier",
            target=f"supplier:{supplier.id}",
            detail=f"{supplier.name} -> {supplier.status}",
        )
        return supplier

    def list_supplier_item_catalog(self) -> list[dict]:
        return self.suppliers.list_item_catalog()

    # --- department purchase requests -------------------------------------

    def list_department_requests(
        self,
        *,
        actor,
        q: str | None = None,
        status: str | None = None,
        source_type: str | None = None,
        sort: str = "-created_at",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict], int]:
        filter_by_department = not self._sees_all_department_requests(actor)
        rows, total = self.department_requests.list(
            q=q,
            status=status,
            source_type=source_type,
            requesting_department_id=actor.department_id,
            filter_by_department=filter_by_department,
            sort=sort,
            page=page,
            size=size,
        )
        return [self._to_department_request_out(row) for row in rows], total

    def _sees_all_department_requests(self, actor) -> bool:
        """Có nhìn được YCMH của TOÀN công ty không.

        HAI vai khác hẳn nhau, đừng gộp:

        · **Người XỬ LÝ** — ai có module `thu_mua` — thấy YCMH của MỌI phòng ban. Đó là HỘP VIỆC
          của họ: công việc của thu mua chính là biến đơn của phòng khác thành phiếu mua. Không
          phụ thuộc scope: nhân viên thu mua scope `own` (chỉ thấy PHIẾU MUA của mình) vẫn phải
          thấy đủ yêu cầu gửi đến, nếu không thì ngồi nhìn màn hình trống.
        · **Người ĐỀ NGHỊ** (bao_gia · kho · san_xuat · dm_giay_vat_tu) — chỉ thấy yêu cầu của
          phòng mình, trừ khi được cấp scope `all`.

        ⚠️ Ngày 04/08/2026 tôi hạ scope `thu_mua` của nhân viên mua hàng xuống `own` để họ chỉ
        thấy PHIẾU MUA của mình — và làm mù luôn hộp việc này, vì lúc đó cả hai danh sách cùng đọc
        một ô scope. Hai thứ khác nhau thì phải hỏi hai câu khác nhau.
        """
        if self.authz.scope_for(actor, "thu_mua") is not None:
            return True
        return any(
            self.authz.scope_for(actor, module) == SCOPE_ALL
            for module in DEPARTMENT_REQUEST_READER_MODULES
        )

    def _can_view_department_request(self, row: DepartmentPurchaseRequest, actor) -> bool:
        if self._sees_all_department_requests(actor):
            return True
        return row.requesting_department_id == actor.department_id

    def _department_request(self, request_id: int) -> DepartmentPurchaseRequest:
        row = self.department_requests.get_by_id(request_id)
        if row is None:
            raise PurchaseNotFound("Khong tim thay phieu yeu cau mua tu phong ban.")
        return row

    def get_department_request(self, request_id: int, *, actor) -> dict:
        row = self._department_request(request_id)
        if not self._can_view_department_request(row, actor):
            raise PurchaseNotFound("Khong tim thay phieu yeu cau mua tu phong ban.")
        return self._to_department_request_out(row)

    def _clean_department_request_header(
        self,
        *,
        source_type: str | None,
        purpose: str | None,
        needed_date: date | None,
    ) -> tuple[str, str, date]:
        cleaned_source_type = (source_type or "").strip()
        if cleaned_source_type not in DEPARTMENT_PURCHASE_SOURCE_TYPES:
            raise PurchaseValidationError("Nguon yeu cau mua khong hop le.")
        cleaned_purpose = (purpose or "").strip()
        if not cleaned_purpose:
            raise PurchaseValidationError("Muc dich yeu cau mua khong duoc trong.")
        if needed_date is None:
            raise PurchaseValidationError("Ngay can hang la thong tin bat buoc.")
        if needed_date < _business_today():
            raise PurchaseValidationError("Ngay can hang khong duoc nho hon hom nay.")
        return cleaned_source_type, cleaned_purpose, needed_date

    def _source_type_for_actor(self, actor) -> str:
        if actor.department_id is None:
            return SOURCE_KHAC
        department = self.departments.get_by_id(actor.department_id)
        if department is None:
            return SOURCE_KHAC
        normalized = unicodedata.normalize("NFD", department.name or "")
        name = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn").lower()
        if "kho" in name:
            return SOURCE_KHO
        if "san xuat" in name:
            return SOURCE_SAN_XUAT
        if "cong nghe" in name:
            return SOURCE_CONG_NGHE
        if "gia cong" in name:
            return SOURCE_GIA_CONG_NGOAI
        if "kinh doanh" in name or "sale" in name:
            return SOURCE_KINH_DOANH
        return SOURCE_KHAC

    def _clean_department_lines(self, raw_lines) -> list[DepartmentPurchaseRequestLineInput]:
        if not raw_lines:
            raise PurchaseValidationError("Yeu cau mua phai co it nhat mot dong vat tu.")
        lines: list[DepartmentPurchaseRequestLineInput] = []
        for line in raw_lines:
            get = line.get if isinstance(line, dict) else lambda key, default=None: getattr(line, key, default)
            item_name = (get("item_name") or "").strip()
            if not item_name:
                raise PurchaseValidationError("Ten vat tu khong duoc trong.")
            if not self.suppliers.has_active_item(item_name):
                raise PurchaseValidationError("Vat tu chua co trong danh muc mat hang nha cung cap.")
            unit = (get("unit") or "").strip()
            if not unit:
                raise PurchaseValidationError("Don vi tinh khong duoc trong.")
            quantity = float(get("quantity"))
            if quantity <= 0:
                raise PurchaseValidationError("So luong phai lon hon 0.")
            lines.append(
                DepartmentPurchaseRequestLineInput(
                    item_name=item_name,
                    unit=unit,
                    quantity=quantity,
                    expected_unit_price=0,
                    note=(get("note") or "").strip() or None,
                )
            )
        return lines

    def _new_department_request_code(self) -> str:
        today = datetime.now().strftime("%y%m%d")
        alphabet = string.ascii_uppercase + string.digits
        for _ in range(20):
            rand = "".join(secrets.choice(alphabet) for _ in range(4))
            code = f"YCMH-{today}-{rand}"
            if self.department_requests.get_by_code(code) is None:
                return code
        raise PurchaseConflict("Khong sinh duoc ma yeu cau mua duy nhat, vui long thu lai.")

    def create_department_request(
        self,
        *,
        source_type: str | None,
        related_document_type: str | None,
        related_document_code: str | None,
        purpose: str | None,
        needed_date: date | None,
        note: str | None,
        lines,
        actor,
    ) -> dict:
        if not self.can_create_department_request(actor):
            raise PurchaseForbidden("Ban khong co quyen tao yeu cau mua hang cho bo phan.")
        source_type = self._source_type_for_actor(actor)
        source_type, cleaned_purpose, needed_date = self._clean_department_request_header(
            source_type=source_type, purpose=purpose, needed_date=needed_date
        )
        row = self.department_requests.create(
            code=self._new_department_request_code(),
            source_type=source_type,
            requesting_department_id=actor.department_id,
            requested_by_user_id=actor.id,
            related_document_type=(related_document_type or "").strip() or None,
            related_document_code=(related_document_code or "").strip() or None,
            purpose=cleaned_purpose,
            needed_date=needed_date,
            note=(note or "").strip() or None,
            lines=self._clean_department_lines(lines),
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="create_department_purchase_request",
            target=f"department_purchase_request:{row.id}",
            detail=row.code,
        )
        return self._to_department_request_out(row)

    def can_create_department_request(self, actor) -> bool:
        if self.authz.can(actor, "thu_mua", "request"):
            return True
        if actor.department_id is None:
            return False
        department = self.departments.get_by_id(actor.department_id)
        return department is not None and department.head_user_id == actor.id

    def update_department_request(
        self,
        request_id: int,
        *,
        source_type: str | None,
        related_document_type: str | None,
        related_document_code: str | None,
        purpose: str | None,
        needed_date: date | None,
        note: str | None,
        lines,
        actor,
    ) -> dict:
        row = self._department_request(request_id)
        if row.status != DPR_OPEN:
            raise PurchaseConflict("Chi yeu cau chua tao phieu mua moi duoc sua.")
        if row.requested_by_user_id != actor.id:
            raise PurchaseForbidden("Chi nguoi tao yeu cau moi duoc sua.")
        source_type, cleaned_purpose, needed_date = self._clean_department_request_header(
            source_type=row.source_type, purpose=purpose, needed_date=needed_date
        )
        saved = self.department_requests.update(
            row,
            purpose=cleaned_purpose,
            needed_date=needed_date,
            note=(note or "").strip() or None,
            lines=self._clean_department_lines(lines),
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="update_department_purchase_request",
            target=f"department_purchase_request:{row.id}",
            detail=row.code,
        )
        return self._to_department_request_out(saved)

    def cancel_department_request(self, request_id: int, *, reason: str | None, actor) -> dict:
        row = self._department_request(request_id)
        if row.status != DPR_OPEN:
            raise PurchaseConflict("Chi yeu cau dang cho mua moi duoc huy.")
        can_cancel_any = self.authz.can(actor, "thu_mua", "cancel")
        if row.requested_by_user_id != actor.id and not can_cancel_any:
            raise PurchaseForbidden("Chi nguoi tao yeu cau hoac admin moi duoc huy.")
        row.status = DPR_CANCELLED
        row.note = (reason or "").strip() or row.note
        saved = self.department_requests.save(row)
        self.audit.create(
            actor_user_id=actor.id,
            action="cancel_department_purchase_request",
            target=f"department_purchase_request:{row.id}",
            detail=row.code,
        )
        return self._to_department_request_out(saved)

    # --- purchase requests -------------------------------------------------

    def list_requests(
        self,
        *,
        q: str | None = None,
        status: str | None = None,
        supplier_id: int | None = None,
        sort: str = "-created_at",
        page: int = 1,
        size: int = 20,
        actor=None,
        exclude_statuses: list[str] | None = None,
    ) -> tuple[list[dict], int]:
        # PHẠM VI NHÌN (chủ 04/08/2026: "nhân viên chỉ thấy đơn của tôi thôi, trưởng bộ phận hoặc
        # giám đốc mới thấy cả"). Trước đây hàm này KHÔNG nhận `actor` — ai có `thu_mua:read` là
        # thấy phiếu của cả công ty, bất kể vai được khai scope gì.
        creator_ids: list[int] | None = None
        if actor is not None:
            scope = self._purchase_scope(actor)
            if scope == SCOPE_DEPARTMENT:
                creator_ids = self._nguoi_cung_phong(actor)
            elif scope != SCOPE_ALL:
                creator_ids = [actor.id]
        rows, total = self.requests.list(
            q=q, status=status, supplier_id=supplier_id, sort=sort, page=page, size=size,
            creator_ids=creator_ids, exclude_statuses=exclude_statuses,
        )
        return [self._to_request_out(r) for r in rows], total

    def _purchase_scope(self, actor) -> str | None:
        """Phạm vi phiếu mua actor được nhìn: `all` | `department` | `own`.

        `all` nếu có scope `all` ở BẤT KỲ module nào trong `PURCHASE_REQUEST_READER_MODULES` —
        không thì lấy scope rộng nhất trong số các module actor có. Người không có module nào →
        `own` (chỉ phiếu của chính mình), đó là mức chặt nhất chứ không phải "thấy hết"."""
        rong_dan = {SCOPE_OWN: 0, SCOPE_DEPARTMENT: 1, SCOPE_ALL: 2}
        best = SCOPE_OWN
        for module in PURCHASE_REQUEST_READER_MODULES:
            sc = self.authz.scope_for(actor, module)
            if sc and rong_dan.get(sc, 0) > rong_dan[best]:
                best = sc
        return best

    def _nguoi_cung_phong(self, actor) -> list[int]:
        """id của những người CÙNG PHÒNG BAN với actor — dùng cho scope `department`.

        `purchase_requests` không có cột phòng ban, chỉ có `created_by_user_id`, nên phải quy về
        "người tạo thuộc phòng ban của tôi"."""
        if getattr(actor, "department_id", None) is None:
            return [actor.id]
        return [u.id for u in self.users.list_by_department(actor.department_id)] or [actor.id]

    def _co_duoc_xem(self, row: PurchaseRequest, actor) -> bool:
        scope = self._purchase_scope(actor)
        if scope == SCOPE_ALL:
            return True
        if scope == SCOPE_DEPARTMENT:
            return row.created_by_user_id in set(self._nguoi_cung_phong(actor))
        return row.created_by_user_id == actor.id

    def get_request(self, request_id: int, *, actor=None) -> dict:
        row = self._request(request_id)
        # Lọc ở DANH SÁCH mà để CHI TIẾT mở là vô nghĩa — biết id là đọc được hết. Báo 404 chứ
        # không 403: không xác nhận cho người ngoài biết phiếu đó có tồn tại hay không.
        if actor is not None and not self._co_duoc_xem(row, actor):
            raise PurchaseNotFound("Không tìm thấy phiếu yêu cầu mua hàng.")
        return self._to_request_out(row)

    def _request(self, request_id: int) -> PurchaseRequest:
        """Tra phiếu theo id, KHÔNG kiểm phạm vi.

        ⚠️ Chỉ dùng cho đường đọc đã tự kiểm (`get_request`) hoặc chỗ gọi nội bộ. Mọi hàm GHI phải
        đi qua `_request_ghi` — xem lý do ở đó."""
        row = self.requests.get_by_id(request_id)
        if row is None:
            raise PurchaseNotFound("Không tìm thấy phiếu yêu cầu mua hàng.")
        return row

    def _request_ghi(self, request_id: int, actor) -> PurchaseRequest:
        """Cửa DUY NHẤT cho mọi hàm ghi lên phiếu mua. **Ghi không được rộng hơn đọc.**

        Trước 05/08/2026 chỉ đường ĐỌC kiểm phạm vi; toàn bộ đường GHI tra thẳng `_request` nên
        cổng quyền ở router chỉ hỏi *"có quyền `thu_mua:update` không"*, KHÔNG hỏi phiếu đó của ai.
        Nhân viên không nhìn thấy phiếu đồng nghiệp trong danh sách (nhận 404) nhưng gọi thẳng theo
        id thì **sửa, xoá, gửi duyệt, đánh dấu đã nhận hàng** đều được — mà "đã nhận hàng" thì ĐẺ RA
        CÔNG NỢ trên bàn kế toán. Id là số chạy, đoán được.

        Trớ trêu là `cancel` đã có chốt sở hữu riêng từ 04/08, còn `delete` thì không: huỷ phiếu
        người khác bị chặn mà XOÁ HẲN lại được.

        Báo 404 chứ không 403 — giống hệt đường đọc, để không xác nhận cho người ngoài biết phiếu đó
        có tồn tại. Trả 403 là tự khai ra "có phiếu này nhưng anh không được đụng"."""
        row = self._request(request_id)
        if not self._co_duoc_xem(row, actor):
            raise PurchaseNotFound("Không tìm thấy phiếu yêu cầu mua hàng.")
        return row

    def _require_supplier_active(self, supplier_id: int | None) -> None:
        if supplier_id is None:
            raise PurchaseValidationError("Nhà cung cấp là thông tin bắt buộc.")
        supplier = self.suppliers.get_by_id(supplier_id)
        if supplier is None:
            raise PurchaseValidationError("Nhà cung cấp không tồn tại.")
        if supplier.status != SUPPLIER_ACTIVE:
            raise PurchaseValidationError("Nhà cung cấp đang ngừng hợp tác.")

    def _clean_request_header(
        self,
        *,
        supplier_id: int | None,
        purpose: str | None,
        needed_date: date | None,
    ) -> tuple[int, str, date]:
        if supplier_id is None:
            raise PurchaseValidationError("Nhà cung cấp là thông tin bắt buộc.")
        cleaned_purpose = (purpose or "").strip()
        if not cleaned_purpose:
            raise PurchaseValidationError("Mục đích mua hàng không được trống.")
        if needed_date is None:
            raise PurchaseValidationError("Ngày cần hàng là thông tin bắt buộc.")
        if needed_date < _business_today():
            raise PurchaseValidationError("Ngay can hang khong duoc nho hon hom nay.")
        return supplier_id, cleaned_purpose, needed_date

    def _clean_expected_receipt_date(
        self,
        *,
        needed_date: date,
        expected_receipt_date: date | None,
    ) -> date | None:
        if expected_receipt_date is None:
            return None
        if expected_receipt_date < _business_today():
            raise PurchaseValidationError("Ngay du kien nhan hang khong duoc nho hon hom nay.")
        # KHÔNG chặn "nhận sớm hơn ngày cần" (chủ 03/08/2026). Nhận hàng TRƯỚC ngày cần chính là
        # trường hợp MONG MUỐN — bắt `nhận ≥ cần` là cấm đúng cái tốt, ép mọi kế hoạch phải về sát
        # hạn hoặc trễ. Ràng buộc duy nhất còn lại: không nhận vào ngày đã qua.
        return expected_receipt_date

    @staticmethod
    def _chot_noi_dong(cleaned_lines, source_requests) -> None:
        """Dòng phiếu chỉ được trỏ về dòng của CHÍNH yêu cầu nguồn nó gắn.

        Không chốt thì phiếu trỏ được sang dòng của yêu cầu khác, và chi tiết YCMH hiện nhầm tiến
        độ của người khác — im lặng, không báo lỗi.

        Chạy RIÊNG sau khi đã gỡ yêu cầu nguồn, không nhét vào `_clean_lines`: nhét vào thì phải
        gỡ nguồn trước khi làm sạch dòng, và thứ tự báo lỗi đảo ngược — người dùng gõ thiếu đơn vị
        tính lại nhận câu "yêu cầu không còn ở trạng thái chờ mua"."""
        hop_le = {line.id for src in source_requests for line in getattr(src, "lines", [])}
        for line in cleaned_lines:
            src_line_id = getattr(line, "department_request_line_id", None)
            if src_line_id is not None and src_line_id not in hop_le:
                raise PurchaseValidationError(
                    f'Dòng "{line.item_name}" trỏ tới một dòng không thuộc yêu cầu nguồn của phiếu này.'
                )

    def _clean_lines(
        self, raw_lines, *, supplier_id: int | None = None
    ) -> list[PurchaseRequestLineInput]:
        """Làm sạch dòng hàng của PHIẾU MUA.

        `supplier_id` bắt buộc trên đường thật (create/update): mỗi dòng phải nằm trong danh mục
        mặt hàng ĐANG BẬT của CHÍNH NCC đó. Trước 04/08/2026 chỗ này không kiểm gì — chọn NCC A
        rồi ghi mặt hàng chỉ NCC B bán thì phiếu vẫn tạo được, im lặng, tới lúc gửi đơn mới vỡ.
        Để `None` là bỏ qua kiểm — chỉ dành cho chỗ gọi không có NCC (nếu sau này có).

        Cái nối dòng ↔ dòng (`department_request_line_id`) chỉ được ĐỌC ở đây, chốt tính hợp lệ
        nằm ở `_chot_noi_dong` — chạy sau khi đã gỡ yêu cầu nguồn, để không đảo thứ tự báo lỗi.
        """
        if not raw_lines:
            raise PurchaseValidationError("Phiếu phải có ít nhất một dòng hàng.")
        lines: list[PurchaseRequestLineInput] = []
        for line in raw_lines:
            get = line.get if isinstance(line, dict) else lambda key, default=None: getattr(line, key, default)
            item_name = (get("item_name") or "").strip()
            if not item_name:
                raise PurchaseValidationError("Tên hàng không được trống.")
            if supplier_id is not None and not self.suppliers.supplier_sells(supplier_id, item_name):
                raise PurchaseValidationError(
                    f'Nha cung cap nay khong ban "{item_name}". '
                    "Chon nha cung cap khac cho dong nay, hoac khai mat hang do cho ho truoc."
                )
            unit = (get("unit") or "").strip()
            if not unit:
                raise PurchaseValidationError("Đơn vị tính không được trống.")
            quantity = float(get("quantity"))
            expected_unit_price = int(get("expected_unit_price"))
            discount_percent = float(get("discount_percent") or 0)
            vat_percent = float(get("vat_percent") or 0)
            if quantity <= 0:
                raise PurchaseValidationError("Số lượng phải lớn hơn 0.")
            if expected_unit_price <= 0:
                raise PurchaseValidationError("Đơn giá dự kiến phải lớn hơn 0.")
            if discount_percent < 0 or discount_percent > 100:
                raise PurchaseValidationError("Giảm giá (%) phải trong khoảng 0 đến 100.")
            if vat_percent < 0 or vat_percent > 100:
                raise PurchaseValidationError("Thuế GTGT (%) phải trong khoảng 0 đến 100.")
            raw_src = get("department_request_line_id")
            src_line_id = int(raw_src) if raw_src not in (None, "") else None
            lines.append(
                PurchaseRequestLineInput(
                    item_name=item_name,
                    unit=unit,
                    quantity=quantity,
                    expected_unit_price=expected_unit_price,
                    discount_percent=discount_percent,
                    vat_percent=vat_percent,
                    note=(get("note") or "").strip() or None,
                    department_request_line_id=src_line_id,
                )
            )
        return lines

    def _new_purchase_code(self) -> str:
        today = datetime.now().strftime("%y%m%d")
        alphabet = string.ascii_uppercase + string.digits
        for _ in range(20):
            rand = "".join(secrets.choice(alphabet) for _ in range(4))
            code = f"PMH-{today}-{rand}"
            if self.requests.get_by_code(code) is None:
                return code
        raise PurchaseConflict("Không sinh được mã phiếu duy nhất, vui lòng thử lại.")

    def _resolve_source_requests(
        self,
        source_request_ids,
        *,
        allow_in_purchase: bool = True,
        allowed_reserved_ids: set[int] | None = None,
    ) -> list[DepartmentPurchaseRequest]:
        allowed_reserved_ids = allowed_reserved_ids or set()
        ids: list[int] = []
        seen: set[int] = set()
        for raw_id in source_request_ids or []:
            source_id = int(raw_id)
            if source_id not in seen:
                ids.append(source_id)
                seen.add(source_id)
        if not ids:
            raise PurchaseValidationError("Phieu mua phai gan it nhat mot yeu cau mua tu phong ban.")
        if len(ids) != 1:
            raise PurchaseValidationError("Moi phieu mua hang chi duoc gan 1 yeu cau mua tu phong ban.")
        rows = self.department_requests.get_many(ids)
        by_id = {row.id: row for row in rows}
        missing = [str(source_id) for source_id in ids if source_id not in by_id]
        if missing:
            raise PurchaseValidationError("Yeu cau mua khong ton tai: " + ", ".join(missing) + ".")
        blocked = [
            row.code
            for row in rows
            if row.status in (DPR_DONE, DPR_CANCELLED)
            or (
                row.status in (DPR_PENDING_APPROVAL, DPR_IN_PURCHASE)
                and row.id not in allowed_reserved_ids
                and not allow_in_purchase
            )
        ]
        if blocked:
            raise PurchaseValidationError(
                "Yeu cau mua khong con o trang thai cho mua: " + ", ".join(blocked) + "."
            )
        return [by_id[source_id] for source_id in ids]

    def create_request(
        self,
        *,
        supplier_id: int | None,
        purpose: str | None,
        needed_date: date | None,
        expected_receipt_date: date | None = None,
        note: str | None,
        lines,
        source_request_ids,
        actor,
    ) -> dict:
        supplier_id, cleaned_purpose, needed_date = self._clean_request_header(
            supplier_id=supplier_id, purpose=purpose, needed_date=needed_date
        )
        expected_receipt_date = self._clean_expected_receipt_date(
            needed_date=needed_date, expected_receipt_date=expected_receipt_date
        )
        self._require_supplier_active(supplier_id)
        cleaned_lines = self._clean_lines(lines, supplier_id=supplier_id)
        source_requests = self._resolve_source_requests(source_request_ids, allow_in_purchase=False)
        self._chot_noi_dong(cleaned_lines, source_requests)
        row = self.requests.create(
            code=self._new_purchase_code(),
            supplier_id=supplier_id,
            purpose=cleaned_purpose,
            needed_date=needed_date,
            expected_receipt_date=expected_receipt_date,
            created_by_user_id=actor.id,
            note=(note or "").strip() or None,
            lines=cleaned_lines,
            source_requests=source_requests,
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="create_purchase_request",
            target=f"purchase_request:{row.id}",
            detail=row.code,
        )
        return self._to_request_out(row)

    def create_requests_batch(
        self,
        *,
        purpose,
        needed_date,
        expected_receipt_date: date | None = None,
        note: str | None,
        lines,
        source_request_ids,
        actor,
    ) -> list[dict]:
        """Tạo N phiếu mua từ một danh sách dòng ĐÃ GÁN nhà cung cấp — nhóm theo NCC.

        Một phiếu mua là thoả thuận với MỘT nhà cung cấp, nên yêu cầu chứa hàng của nhiều nơi thì
        buộc phải tách. Gộp vào một lời gọi vì hai lý do:

        1. Giao diện KHÔNG gọi API tạo phiếu nhiều lần được: tạo phiếu đầu là yêu cầu nguồn bị
           giữ chỗ ngay (`_replace_sources` đẩy sang `pending_approval`), lần thứ hai cho NCC khác
           sẽ bị `_resolve_source_requests` chặn. Ở đây khai luôn tập yêu cầu đó là "đã biết,
           cho phép" nên cả mẻ dùng chung được.
        2. Hỏng thì hỏng CẢ MẺ (`create_many` một commit), không để lại phiếu mồ côi giữ chỗ.

        Thứ tự phiếu ra theo thứ tự NCC XUẤT HIỆN LẦN ĐẦU trong danh sách dòng — người dùng nhìn
        bảng từ trên xuống thì phiếu cũng ra theo thứ tự đó, không nhảy lung tung.
        """
        raw = list(lines or [])
        if not raw:
            raise PurchaseValidationError("Phai co it nhat mot dong hang.")

        # Nhóm theo NCC, giữ thứ tự xuất hiện.
        nhom: dict[int, list] = {}
        for line in raw:
            get = line.get if isinstance(line, dict) else lambda k, d=None: getattr(line, k, d)
            sid = get("supplier_id")
            if not sid:
                raise PurchaseValidationError(
                    f'Dong "{(get("item_name") or "").strip()}" chua chon nha cung cap.'
                )
            nhom.setdefault(int(sid), []).append(line)

        # Yêu cầu nguồn: giải MỘT lần cho cả mẻ. `allowed_reserved_ids` để chính các yêu cầu này
        # không tự chặn nhau khi phiếu thứ hai trở đi gắn lại cùng tập.
        source_requests = self._resolve_source_requests(source_request_ids, allow_in_purchase=False)
        source_ids = {row.id for row in source_requests}

        # Kiểm TẤT CẢ trước khi dựng bất cứ thứ gì — vỡ ở nhóm thứ ba thì hai nhóm đầu cũng
        # không được tạo.
        items: list[dict] = []
        for supplier_id, group in nhom.items():
            sid, cleaned_purpose, cleaned_needed = self._clean_request_header(
                supplier_id=supplier_id, purpose=purpose, needed_date=needed_date
            )
            cleaned_receipt = self._clean_expected_receipt_date(
                needed_date=cleaned_needed, expected_receipt_date=expected_receipt_date
            )
            self._require_supplier_active(sid)
            cleaned_group = self._clean_lines(group, supplier_id=sid)
            self._chot_noi_dong(cleaned_group, source_requests)
            items.append(dict(
                code=self._new_purchase_code(),
                supplier_id=sid,
                purpose=cleaned_purpose,
                needed_date=cleaned_needed,
                expected_receipt_date=cleaned_receipt,
                created_by_user_id=actor.id,
                note=(note or "").strip() or None,
                lines=cleaned_group,
                source_requests=self._resolve_source_requests(
                    source_ids, allow_in_purchase=False, allowed_reserved_ids=source_ids
                ),
            ))

        rows = self.requests.create_many(items)
        for row in rows:
            self.audit.create(
                actor_user_id=actor.id,
                action="create_purchase_request",
                target=f"purchase_request:{row.id}",
                detail=row.code,
            )
        return [self._to_request_out(row) for row in rows]

    def update_request(
        self,
        request_id: int,
        *,
        actor,
        supplier_id,
        source_request_ids,
        purpose,
        needed_date,
        expected_receipt_date=None,
        note,
        lines,
    ) -> dict:
        row = self._request_ghi(request_id, actor)
        if row.status not in (PR_DRAFT, PR_REJECTED):
            raise PurchaseConflict("Chỉ phiếu nháp hoặc bị từ chối mới được sửa.")
        supplier_id, cleaned_purpose, needed_date = self._clean_request_header(
            supplier_id=supplier_id, purpose=purpose, needed_date=needed_date
        )
        expected_receipt_date = self._clean_expected_receipt_date(
            needed_date=needed_date, expected_receipt_date=expected_receipt_date
        )
        self._require_supplier_active(supplier_id)
        cleaned_lines = self._clean_lines(lines, supplier_id=supplier_id)
        nguon = self._resolve_source_requests(
            source_request_ids,
            allow_in_purchase=False,
            allowed_reserved_ids={link.department_request_id for link in row.sources},
        )
        self._chot_noi_dong(cleaned_lines, nguon)
        row = self.requests.update_header_and_lines(
            row,
            supplier_id=supplier_id,
            purpose=cleaned_purpose,
            needed_date=needed_date,
            expected_receipt_date=expected_receipt_date,
            note=(note or "").strip() or None,
            lines=cleaned_lines,
            source_requests=nguon,
        )
        self.audit.create(
            actor_user_id=actor.id,
            action="update_purchase_request",
            target=f"purchase_request:{row.id}",
            detail=row.code,
        )
        return self._to_request_out(row)

    def delete_request(self, request_id: int, *, actor) -> None:
        row = self._request_ghi(request_id, actor)
        if row.status != PR_DRAFT:
            raise PurchaseConflict("Chỉ phiếu nháp mới được xóa.")
        code = row.code
        # Suy LẠI bỏ qua chính phiếu sắp xoá — sau `delete` thì quan hệ đã rời, không đọc được nữa.
        for link in row.sources:
            self._tinh_lai_trang_thai_ycmh(link.department_request, bo_qua_phieu_id=row.id)
        self.requests.delete(row)
        self.audit.create(
            actor_user_id=actor.id,
            action="delete_purchase_request",
            target=f"purchase_request:{request_id}",
            detail=code,
        )

    def submit(self, request_id: int, *, actor) -> dict:
        row = self._request_ghi(request_id, actor)
        if row.status not in (PR_DRAFT, PR_REJECTED):
            raise PurchaseConflict("Chỉ phiếu nháp hoặc bị từ chối mới được gửi duyệt.")
        row.status = PR_PENDING
        row.submitted_at = _now()
        row.approved_by_user_id = None
        row.approved_at = None
        for link in row.sources:
            self._tinh_lai_trang_thai_ycmh(link.department_request)
        saved = self.requests.save(row)
        self.audit.create(actor_user_id=actor.id, action="submit_purchase_request", target=f"purchase_request:{row.id}", detail=row.code)
        return self._to_request_out(saved)

    def approve(self, request_id: int, *, actor) -> dict:
        row = self._request_ghi(request_id, actor)
        if row.status != PR_PENDING:
            raise PurchaseConflict("Chỉ phiếu đang chờ duyệt mới được duyệt.")
        # TÁCH VAI (chủ 04/08/2026: "thu mua làm gì có quyền duyệt"): ai đề xuất chi tiền thì
        # không được là người đồng ý chi. Chốt ở ĐÂY chứ không chỉ ở phân quyền, vì phân quyền là
        # cấu hình — bật lại lúc nào cũng được ở màn Phân quyền mà không ai hay.
        #
        # KHÔNG miễn cho giám đốc (chủ chốt). Hệ quả: giám đốc tự lập phiếu thì phải người khác
        # duyệt. Muốn nới thì thêm một ô miễn trừ, đừng gỡ chốt.
        if row.created_by_user_id is not None and row.created_by_user_id == actor.id:
            raise PurchaseForbidden(
                "Nguoi lap phieu khong duoc tu duyet phieu cua chinh minh."
            )
        row.status = PR_APPROVED
        row.approved_by_user_id = actor.id
        row.approved_at = _now()
        for link in row.sources:
            self._tinh_lai_trang_thai_ycmh(link.department_request)
        saved = self.requests.save(row)
        self.audit.create(actor_user_id=actor.id, action="approve_purchase_request", target=f"purchase_request:{row.id}", detail=row.code)
        return self._to_request_out(saved)

    def reject(self, request_id: int, *, reason: str | None, actor) -> dict:
        row = self._request_ghi(request_id, actor)
        if row.status != PR_PENDING:
            raise PurchaseConflict("Chỉ phiếu đang chờ duyệt mới được từ chối.")
        row.status = PR_REJECTED
        row.approved_by_user_id = actor.id
        row.approved_at = _now()
        row.note = (reason or "").strip() or row.note
        for link in row.sources:
            self._tinh_lai_trang_thai_ycmh(link.department_request)
        saved = self.requests.save(row)
        self.audit.create(actor_user_id=actor.id, action="reject_purchase_request", target=f"purchase_request:{row.id}", detail=row.code)
        return self._to_request_out(saved)

    def mark_purchased(self, request_id: int, *, actor) -> dict:
        row = self._request_ghi(request_id, actor)
        if row.status != PR_APPROVED:
            raise PurchaseConflict("Chỉ phiếu đã duyệt mới được đánh dấu đã mua.")
        row.status = PR_PURCHASED
        saved = self.requests.save(row)
        self.audit.create(actor_user_id=actor.id, action="mark_purchase_request_purchased", target=f"purchase_request:{row.id}", detail=row.code)
        return self._to_request_out(saved)

    def _tinh_lai_trang_thai_ycmh(self, source, *, bo_qua_phieu_id: int | None = None) -> None:
        """SUY trạng thái yêu cầu mua hàng từ tập phiếu con. Gọi ở MỌI mốc đụng tới phiếu.

        Trước 05/08/2026 chỉ mốc *nhận hàng* biết suy; sáu chỗ còn lại set thẳng nên "ai bấm sau
        thì ghi đè". Hệ quả thấy được trên màn:
        - Duyệt MỘT phiếu là yêu cầu thành "Đang mua", dù phiếu kia còn nằm chờ giám đốc ⇒ bộ phận
          tưởng cả yêu cầu đã được duyệt.
        - Từ chối một phiếu kéo yêu cầu về "Chờ mua" dù phiếu kia đã duyệt và đang đi mua.
        - Phiếu bị TỪ CHỐI không được loại khỏi phép "mọi phiếu đã về hàng" (chỉ loại phiếu HUỶ)
          nên yêu cầu treo ở "Đang mua" **vĩnh viễn**, kể cả khi hàng đã về đủ qua phiếu lập lại.

        Luật: xếp bậc, lấy bậc **THẤP NHẤT**. Báo bi quan thì cùng lắm bộ phận đi hỏi; báo lạc
        quan thì họ ngồi chờ hàng không bao giờ tới.

        Phiếu **bị từ chối / đã huỷ** tính là bậc 0 (Chờ mua), KHÔNG phải bỏ qua: phần hàng đó chưa
        ai mua được, nên yêu cầu phải quay lại hàng chờ để thu mua lập phiếu khác — hoặc bộ phận
        huỷ hẳn yêu cầu. Bỏ qua thì có ngày báo "Xong" trong khi một nửa đơn bị từ chối. Và vì
        `create` chỉ nhận yêu cầu đang "Chờ mua", để bậc 0 mới còn đường lập lại.

        Suy theo **DÒNG** khi phiếu có nối `department_request_line_id` — chính xác hơn hẳn: phiếu
        cũ bị huỷ và phiếu mới đã về hàng cùng phủ một dòng thì dòng đó tính là đã xong. Dữ liệu cũ
        không có nối thì lùi về suy theo PHIẾU.

        Yêu cầu đã HUỶ thì không đụng — huỷ là quyết định của người, không phải trạng thái suy ra.
        """
        if source is None or source.status == DPR_CANCELLED:
            return
        phieu = [
            link.purchase_request
            for link in getattr(source, "purchase_links", [])
            if link.purchase_request is not None
            and (bo_qua_phieu_id is None or link.purchase_request.id != bo_qua_phieu_id)
        ]
        if not phieu:
            source.status = DPR_OPEN
            return

        bac_theo_dong: dict[int, int] = {}
        for p in phieu:
            for line in p.lines:
                src_line_id = getattr(line, "department_request_line_id", None)
                if src_line_id is None:
                    continue
                # Một dòng có thể đi qua NHIỀU phiếu (bị từ chối rồi lập lại) ⇒ lấy tiến độ CAO
                # NHẤT của dòng đó, không phải của phiếu cuối cùng.
                bac_theo_dong[src_line_id] = max(
                    bac_theo_dong.get(src_line_id, 0), _BAC_PHIEU.get(p.status, 0)
                )
        if bac_theo_dong:
            # Dòng nào chưa có phiếu nào phủ thì vẫn là "Chờ mua" — chính là chỗ hay bị bỏ sót.
            bac = min(
                bac_theo_dong.get(line.id, 0) for line in getattr(source, "lines", [])
            ) if getattr(source, "lines", None) else min(bac_theo_dong.values())
        else:
            bac = min(_BAC_PHIEU.get(p.status, 0) for p in phieu)
        source.status = _BAC_SANG_TRANG_THAI[bac]

    # `_moi_phieu_da_ve_hang` đã GỠ 05/08/2026: `_tinh_lai_trang_thai_ycmh` nuốt trọn việc của nó
    # và làm đúng thêm hai ca mà nó bỏ sót — phiếu BỊ TỪ CHỐI (nó chỉ loại phiếu huỷ nên yêu cầu
    # treo vĩnh viễn) và suy theo DÒNG khi có nối dòng ↔ dòng.

    def _ap_so_thuc_nhan(self, row: PurchaseRequest, khai: list[dict] | None) -> None:
        """Ghi số thực nhận vào các dòng của phiếu.

        `khai` là None hoặc rỗng ⇒ KHÔNG đụng gì, các dòng giữ `received_quantity` cũ (thường là
        NULL = nhận đủ). Nhờ vậy đường gọi cũ `mark_received(id, actor=...)` chạy y như trước.

        Không cho khai NHIỀU hơn số đặt: giá trị thực nhận là trần lập phiếu chi, khai vống lên là
        chi vượt giá trị đơn giám đốc đã duyệt mà không qua duyệt lại. NCC giao dư thật thì sửa đơn,
        không phải sửa ở đây."""
        if not khai:
            return
        theo_id = {line.id: line for line in row.lines}
        for item in khai:
            line_id = item.get("line_id")
            line = theo_id.get(line_id)
            if line is None:
                raise PurchaseValidationError(f"Dòng {line_id} không thuộc phiếu này.")
            raw = item.get("received_quantity")
            if raw is None:
                line.received_quantity = None
                continue
            qty = float(raw)
            if qty < 0:
                raise PurchaseValidationError("Số thực nhận không được âm.")
            if qty > float(line.quantity):
                raise PurchaseValidationError(
                    f"'{line.item_name}': nhận {qty:g} nhiều hơn số đặt {float(line.quantity):g}. "
                    "Nhận dư thì sửa đơn rồi duyệt lại, không khai vống ở đây."
                )
            line.received_quantity = qty

    def mark_received(self, request_id: int, *, received_lines: list[dict] | None = None, actor) -> dict:
        row = self._request_ghi(request_id, actor)
        if row.status != PR_PURCHASED:
            raise PurchaseConflict("Chỉ phiếu đã mua mới được đánh dấu đã nhận hàng.")
        self._ap_so_thuc_nhan(row, received_lines)
        row.status = PR_RECEIVED
        # Một yêu cầu có thể tách thành NHIỀU phiếu (mỗi NCC một phiếu) ⇒ chỉ "Xong" khi MỌI phần
        # của nó đã về. Phiếu giấy về trước mà báo Xong thì bộ phận tưởng đủ hàng trong khi băng
        # keo còn chưa ai mua.
        for link in row.sources:
            self._tinh_lai_trang_thai_ycmh(link.department_request)
        saved = self.requests.save(row)
        self.audit.create(actor_user_id=actor.id, action="mark_purchase_request_received", target=f"purchase_request:{row.id}", detail=row.code)
        return self._to_request_out(saved)

    def update_received_quantities(self, request_id: int, *, received_lines: list[dict], actor) -> dict:
        """Sửa lại số thực nhận SAU khi phiếu đã ở 'Đã nhận hàng'.

        Dùng cho ca NCC giao làm nhiều đợt: đợt 1 khai 60, đợt 2 về thì sửa lên 100. (Lịch sử từng
        đợt về ngày nào thì hàm này KHÔNG lưu — chờ phiếu nhập kho.)

        Đòi `thu_mua:approve` chứ không phải `update`: sửa số này là **đổi số nợ đã ghi trên màn kế
        toán**, ngang với việc lùi trạng thái. Vào nhật ký để còn truy được ai sửa.

        Chốt an toàn: hạ số thực nhận xuống DƯỚI số đã chi/đang chờ chi là chặn — nếu không thì
        phiếu chi treo lơ lửng vượt cả giá trị hàng, `available_amount` âm bị kẹp về 0 và số liệu
        im lặng sai."""
        if not self.authz.can(actor, "thu_mua", "approve"):
            raise PurchaseForbidden("Chỉ người có quyền duyệt mới được sửa số thực nhận.")
        row = self._request_ghi(request_id, actor)
        if row.status != PR_RECEIVED:
            raise PurchaseConflict("Chỉ phiếu đã nhận hàng mới sửa được số thực nhận.")
        self._ap_so_thuc_nhan(row, received_lines)
        money = purchase_money(row)
        da_cam_ket = money["net_paid"] + money["pending_amount"]
        if money["received_total"] < da_cam_ket:
            raise PurchaseConflict(
                f"Giá trị thực nhận ({money['received_total']:,}đ) thấp hơn số đã chi và đang chờ chi "
                f"({da_cam_ket:,}đ). Huỷ bớt phiếu chi trước rồi sửa lại."
            )
        saved = self.requests.save(row)
        self.audit.create(
            actor_user_id=actor.id,
            action="update_purchase_request_received_quantities",
            target=f"purchase_request:{row.id}",
            detail=f"{row.code} — thực nhận {money['received_total']:,}đ / đặt {money['total']:,}đ",
        )
        return self._to_request_out(saved)

    def undo_received(self, request_id: int, *, reason: str | None, actor) -> dict:
        """Lùi 'Đã nhận hàng' về 'Đã mua'.

        Trước 05/08/2026 KHÔNG có đường nào ra khỏi `received`: `mark_received` chỉ gán vào, còn
        `cancel()` chặn thẳng phiếu đã nhận. Bấm nhầm là kẹt vĩnh viễn — trước đây không ai thấy,
        nhưng từ khi có màn Công nợ phải trả thì mỗi lần bấm nhầm là đẻ một món nợ ảo nằm chình ình
        trên bàn kế toán.

        Ba việc, thiếu việc nào cũng hỏng:

        1. **Tiền đã ra thì không lùi.** Có phiếu chi ĐÃ CHI nghĩa là tiền rời két rồi; quay lại
           khai 'chưa nhận hàng' là nói dối sổ quỹ. Phiếu mới `chờ chi` thì lùi thoải mái — nợ chưa
           thành tiền, kế toán huỷ phiếu là xong.
        2. Lật phiếu về `purchased`.
        3. **Tính LẠI trạng thái YCMH nguồn** qua `_tinh_lai_trang_thai_ycmh`. Quên vế này thì
           YCMH đứng nguyên 'Xong' trong khi phiếu đã lùi — bộ phận đề nghị nhìn vào tưởng đủ hàng.
           Suy lại chứ KHÔNG kéo mù: một YCMH tách ra nhiều phiếu theo NCC, lùi một phiếu chưa chắc
           đã hết 'Xong'.

        Quyền: `thu_mua:approve` (trưởng bộ phận / giám đốc). Nút này XOÁ một món nợ khỏi màn kế
        toán nên không phải việc nhân viên tự quyết — cùng lằn ranh đã áp cho `cancel`."""
        if not self.authz.can(actor, "thu_mua", "approve"):
            raise PurchaseForbidden("Chỉ người có quyền duyệt mới được lùi trạng thái đã nhận hàng.")
        ly_do = (reason or "").strip()
        if not ly_do:
            raise PurchaseValidationError("Phải ghi lý do lùi trạng thái đã nhận hàng.")
        row = self._request_ghi(request_id, actor)
        if row.status != PR_RECEIVED:
            raise PurchaseConflict("Chỉ phiếu đã nhận hàng mới lùi được.")
        if any(v.status == PAYMENT_VOUCHER_PAID for v in row.payment_vouchers):
            raise PurchaseConflict(
                "Đơn đã có phiếu chi ĐÃ CHI — xử lý phần tiền trước khi lùi trạng thái."
            )
        row.status = PR_PURCHASED
        for link in row.sources:
            self._tinh_lai_trang_thai_ycmh(link.department_request)
        saved = self.requests.save(row)
        self.audit.create(
            actor_user_id=actor.id,
            action="undo_purchase_request_received",
            target=f"purchase_request:{row.id}",
            detail=f"{row.code} — {ly_do}",
        )
        return self._to_request_out(saved)

    def cancel(self, request_id: int, *, reason: str | None, actor) -> dict:
        row = self._request_ghi(request_id, actor)
        if row.status in (PR_RECEIVED, PR_CANCELLED):
            raise PurchaseConflict("Phiếu đã nhận hàng hoặc đã hủy thì không thể hủy tiếp.")
        # Huỷ phiếu ĐÃ GỬI DUYỆT là quyết định của người duyệt, không phải của thu mua (chủ chốt
        # 04/08/2026). Người chỉ có `cancel` thì chỉ được dọn phiếu NHÁP DO CHÍNH MÌNH lập — giữ
        # được việc tự dọn nháp mà không cho giết phiếu đang nằm trên bàn giám đốc.
        #
        # Phân biệt theo NĂNG LỰC (`approve`) chứ không theo tên vai: tên vai đổi lúc nào cũng
        # được, mà đổi xong thì luật viết theo tên vai câm lặng thất hiệu.
        if not self.authz.can(actor, "thu_mua", "approve"):
            if row.status != PR_DRAFT or row.created_by_user_id != actor.id:
                raise PurchaseForbidden(
                    "Chi huy duoc phieu nhap do chinh minh lap. "
                    "Phieu da gui duyet thi nguoi duyet quyet."
                )
        if any(
            voucher.status in (PAYMENT_VOUCHER_WAITING, PAYMENT_VOUCHER_PAID)
            for voucher in row.payment_vouchers
        ):
            raise PurchaseConflict("Phiếu đã có chứng từ thanh toán nên không thể hủy.")
        row.status = PR_CANCELLED
        row.note = (reason or "").strip() or row.note
        for link in row.sources:
            self._tinh_lai_trang_thai_ycmh(link.department_request)
        saved = self.requests.save(row)
        self.audit.create(actor_user_id=actor.id, action="cancel_purchase_request", target=f"purchase_request:{row.id}", detail=row.code)
        return self._to_request_out(saved)

    # --- output helpers ----------------------------------------------------

    def _user_name(self, user_id: int | None) -> str | None:
        if user_id is None:
            return None
        u = self.users.get_by_id(user_id)
        return u.name if u is not None else None

    def _to_request_out(self, row: PurchaseRequest) -> dict:
        # Mọi con TIỀN lấy từ `purchase_money` — dùng chung với màn Công nợ phải trả, không cộng lại
        # ở đây. Vòng lặp dưới chỉ dựng phần HIỂN THỊ của từng dòng.
        money = purchase_money(row)
        total = money["total"]
        lines = []
        for line in row.lines:
            qty = float(line.quantity)
            unit_price = int(line.expected_unit_price)
            discount_percent = float(line.discount_percent or 0)
            vat_percent = float(line.vat_percent or 0)
            _, discount_amount, vat_amount, line_total = _purchase_line_amounts(
                quantity=qty,
                unit_price=unit_price,
                discount_percent=discount_percent,
                vat_percent=vat_percent,
            )
            lines.append(
                {
                    "id": line.id,
                    "item_name": line.item_name,
                    "unit": line.unit,
                    "quantity": qty,
                    "received_quantity": (
                        None if line.received_quantity is None else float(line.received_quantity)
                    ),
                    "expected_unit_price": unit_price,
                    "discount_percent": discount_percent,
                    "discount_amount": discount_amount,
                    "vat_percent": vat_percent,
                    "vat_amount": vat_amount,
                    "line_total": line_total,
                    "note": line.note,
                }
            )
        sources = []
        for link in row.sources:
            source = link.department_request
            sources.append(
                {
                    "id": link.id,
                    "department_request_id": link.department_request_id,
                    "code": source.code if source is not None else link.source_code_snapshot,
                    "status": source.status if source is not None else None,
                    "source_type": source.source_type if source is not None else None,
                    "purpose": source.purpose if source is not None else None,
                    "needed_date": source.needed_date if source is not None else None,
                    "requesting_department_name": (
                        source.requesting_department.name
                        if source is not None and source.requesting_department is not None
                        else None
                    ),
                    "requested_by_name": (
                        source.requested_by.name
                        if source is not None and source.requested_by is not None
                        else None
                    ),
                }
            )
        pending_amount = money["pending_amount"]
        paid_amount = money["paid_amount"]
        receipt_received_amount = money["receipt_received_amount"]
        outstanding_amount = money["outstanding_amount"]
        available_amount = money["available_amount"]
        payment_status = money["payment_status"]
        return {
            "id": row.id,
            "code": row.code,
            "status": row.status,
            "supplier_id": row.supplier_id,
            "supplier_name": row.supplier.name if row.supplier else None,
            "purpose": row.purpose,
            "needed_date": row.needed_date,
            "expected_receipt_date": row.expected_receipt_date,
            "created_by_user_id": row.created_by_user_id,
            "created_by_name": self._user_name(row.created_by_user_id),
            "submitted_at": row.submitted_at,
            "approved_by_user_id": row.approved_by_user_id,
            "approved_by_name": self._user_name(row.approved_by_user_id),
            "approved_at": row.approved_at,
            "note": row.note,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "total_estimate": total,
            # Giá trị hàng THỰC NHẬN. Bằng `total_estimate` chừng nào chưa ai khai thiếu.
            "received_total": money["received_total"],
            "pending_amount": pending_amount,
            "paid_amount": paid_amount,
            "receipt_received_amount": receipt_received_amount,
            "outstanding_amount": outstanding_amount,
            "available_amount": available_amount,
            "payment_status": payment_status,
            "payment_voucher_count": len(row.payment_vouchers),
            "sources": sources,
            "lines": lines,
        }

    def _tinh_trang_tung_dong(self, row: DepartmentPurchaseRequest) -> dict[int, dict]:
        """Với mỗi DÒNG của yêu cầu: nó đã vào phiếu nào, của NCC nào, tới đâu rồi.

        Trước 05/08/2026 chi tiết yêu cầu KHÔNG hề nhắc tới phiếu mua nào — bộ phận vào xem cũng
        không biết yêu cầu của mình đã thành phiếu nào, ai bán, tới đâu.

        Một dòng có thể đi qua NHIỀU phiếu (bị từ chối rồi thu mua lập lại) ⇒ lấy phiếu có tiến độ
        CAO NHẤT, không phải phiếu mới nhất: phiếu lập lại đã về hàng thì dòng đó xong, dù phiếu cũ
        vẫn nằm đó ở trạng thái bị từ chối.

        Chỉ đọc qua `department_request_line_id`. KHÔNG ghép bù bằng tên hàng cho dữ liệu cũ — thà
        để trống và nói "chưa rõ" còn hơn đoán sai mà trông như thật."""
        theo_dong: dict[int, dict] = {}
        for link in getattr(row, "purchase_links", []):
            phieu = link.purchase_request
            if phieu is None:
                continue
            for pl in phieu.lines:
                src_line_id = getattr(pl, "department_request_line_id", None)
                if src_line_id is None:
                    continue
                bac = _BAC_PHIEU.get(phieu.status, 0)
                cu = theo_dong.get(src_line_id)
                if cu is not None and cu["_bac"] >= bac:
                    continue
                theo_dong[src_line_id] = {
                    "_bac": bac,
                    "purchase_request_id": phieu.id,
                    "purchase_code": phieu.code,
                    "purchase_status": phieu.status,
                    "supplier_name": phieu.supplier.name if phieu.supplier else None,
                    "ordered_quantity": float(pl.quantity),
                    "ordered_unit": pl.unit,
                    "received_quantity": (
                        float(pl.received_quantity) if pl.received_quantity is not None else None
                    ),
                }
        for muc in theo_dong.values():
            muc.pop("_bac", None)
        return theo_dong

    def _to_department_request_out(self, row: DepartmentPurchaseRequest) -> dict:
        total = 0
        lines = []
        tinh_trang = self._tinh_trang_tung_dong(row)
        for line in row.lines:
            qty = float(line.quantity)
            unit_price = int(line.expected_unit_price)
            line_total = int(round(qty * unit_price))
            total += line_total
            lines.append(
                {
                    "id": line.id,
                    "item_name": line.item_name,
                    "unit": line.unit,
                    "quantity": qty,
                    "expected_unit_price": unit_price,
                    "line_total": line_total,
                    "note": line.note,
                    # None = chưa vào phiếu nào, HOẶC phiếu lập trước 05/08/2026 (chưa có nối
                    # dòng ↔ dòng). Giao diện phải nói rõ hai ca đó, đừng hiện như nhau.
                    "fulfilment": tinh_trang.get(line.id),
                }
            )
        return {
            "id": row.id,
            "code": row.code,
            "status": row.status,
            "source_type": row.source_type,
            "requesting_department_id": row.requesting_department_id,
            "requesting_department_name": (
                row.requesting_department.name if row.requesting_department is not None else None
            ),
            "requested_by_user_id": row.requested_by_user_id,
            "requested_by_name": row.requested_by.name if row.requested_by is not None else None,
            "related_document_type": row.related_document_type,
            "related_document_code": row.related_document_code,
            "purpose": row.purpose,
            "needed_date": row.needed_date,
            "note": row.note,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "total_estimate": total,
            "lines": lines,
            # Các phiếu mua sinh ra từ yêu cầu này. Vẫn cần dù đã có `fulfilment` theo dòng: yêu
            # cầu lập trước 05/08/2026 không có nối dòng ↔ dòng nên `fulfilment` rỗng, còn đây thì
            # luôn có — ít nhất bộ phận biết yêu cầu của mình đã thành phiếu nào, ai bán.
            "purchase_requests": sorted(
                (
                    {
                        "id": link.purchase_request.id,
                        "code": link.purchase_request.code,
                        "status": link.purchase_request.status,
                        "supplier_name": (
                            link.purchase_request.supplier.name
                            if link.purchase_request.supplier
                            else None
                        ),
                    }
                    for link in getattr(row, "purchase_links", [])
                    if link.purchase_request is not None
                ),
                key=lambda p: p["code"],
            ),
        }
