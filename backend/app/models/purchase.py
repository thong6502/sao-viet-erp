"""Purchasing models — module `thu_mua`.

MVP scope: suppliers + purchase request header/lines. A user creates one purchase
request on the UI; the backend stores it as a header row plus many line rows in a
single transaction.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


SUPPLIER_ACTIVE = "active"
SUPPLIER_INACTIVE = "inactive"
SUPPLIER_STATUSES = (SUPPLIER_ACTIVE, SUPPLIER_INACTIVE)

PR_DRAFT = "draft"
PR_PENDING = "pending_approval"
PR_APPROVED = "approved"
PR_REJECTED = "rejected"
PR_PURCHASED = "purchased"
# Có ≥1 đợt giao nhưng tổng thực nhận chưa đủ số đặt. SUY từ `purchase_deliveries`, không ai gõ.
PR_PARTIALLY_RECEIVED = "partially_received"
PR_RECEIVED = "received"
PR_CANCELLED = "cancelled"
PURCHASE_REQUEST_STATUSES = (
    PR_DRAFT,
    PR_PENDING,
    PR_APPROVED,
    PR_REJECTED,
    PR_PURCHASED,
    PR_PARTIALLY_RECEIVED,
    PR_RECEIVED,
    PR_CANCELLED,
)

# Loại file đính kèm của mua hàng. `hop_dong` treo ở PMH (delivery_id NULL); `hoa_don` và
# `bien_ban_giao` treo ở một đợt giao cụ thể.
PURCHASE_ATTACHMENT_HOP_DONG = "hop_dong"
PURCHASE_ATTACHMENT_HOA_DON = "hoa_don"
PURCHASE_ATTACHMENT_BIEN_BAN = "bien_ban_giao"
PURCHASE_ATTACHMENT_KHAC = "khac"
PURCHASE_ATTACHMENT_KINDS = (
    PURCHASE_ATTACHMENT_HOP_DONG,
    PURCHASE_ATTACHMENT_HOA_DON,
    PURCHASE_ATTACHMENT_BIEN_BAN,
    PURCHASE_ATTACHMENT_KHAC,
)

DPR_OPEN = "open"
DPR_PENDING_APPROVAL = "pending_approval"
DPR_IN_PURCHASE = "in_purchase"
DPR_DONE = "done"
DPR_CANCELLED = "cancelled"
DEPARTMENT_PURCHASE_REQUEST_STATUSES = (
    DPR_OPEN,
    DPR_PENDING_APPROVAL,
    DPR_IN_PURCHASE,
    DPR_DONE,
    DPR_CANCELLED,
)

SOURCE_KINH_DOANH = "kinh_doanh"
SOURCE_KHO = "kho"
SOURCE_SAN_XUAT = "san_xuat"
SOURCE_CONG_NGHE = "cong_nghe"
SOURCE_GIA_CONG_NGOAI = "gia_cong_ngoai"
SOURCE_KHAC = "khac"
DEPARTMENT_PURCHASE_SOURCE_TYPES = (
    SOURCE_KINH_DOANH,
    SOURCE_KHO,
    SOURCE_SAN_XUAT,
    SOURCE_CONG_NGHE,
    SOURCE_GIA_CONG_NGOAI,
    SOURCE_KHAC,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    tax_code: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    supplier_group: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    payment_terms: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # HẠN MỨC công nợ — trần số tiền được nợ NCC này. 0 = không đặt hạn mức.
    # Chỉ CẢNH BÁO MỀM (chủ chốt 06/08/2026): hiện pill đỏ ở màn Công nợ và nhắc khi duyệt PMH,
    # KHÔNG chặn ở đâu cả.
    credit_limit: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    # ĐỊNH MỨC công nợ — số NGÀY NCC cho nợ kể từ ngày hóa đơn; chưa có hóa đơn mới lùi về ngày
    # giao. 0 = trả ngay. NULL = CHƯA ĐẶT HẠN ⇒ đợt giao không bao giờ
    # vào cột "Quá hạn", nên màn Công nợ phải đẩy nó lên ĐẦU kèm badge thay vì để chìm.
    credit_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=SUPPLIER_ACTIVE)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    bank_accounts: Mapped[list["SupplierBankAccount"]] = relationship(
        "SupplierBankAccount",
        back_populates="supplier",
        cascade="all, delete-orphan",
        order_by="SupplierBankAccount.id",
    )
    items: Mapped[list["SupplierItem"]] = relationship(
        "SupplierItem",
        back_populates="supplier",
        cascade="all, delete-orphan",
        order_by="SupplierItem.id",
    )


class SupplierItem(Base):
    __tablename__ = "supplier_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    supplier_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("suppliers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # MẶT HÀNG GỐC mà dòng này bán (mg 0172). NULLABLE có chủ ý: NCC còn bán thứ ngoài danh mục
    # vật tư (dịch vụ, gia công thuê ngoài) — bắt buộc gắn thì không khai nổi mấy dòng đó. Dòng
    # nào CÓ gắn mới vào được bảng so giá.
    #
    # Trước đây ghép NCC với kho bằng CHUỖI `item_name`: thu mua gõ "Couche 150" còn danh mục ghi
    # "Couché 150 79×109" là trượt, mà trượt thì im lặng — không báo lỗi, chỉ là mãi không so được giá.
    hang_loai: Mapped[str | None] = mapped_column(String(8), nullable=True)
    hang_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # Đơn vị NCC BÁN theo — phải nằm trong tập đổi được của mặt hàng (nếu đã gắn), để quy giá về
    # đơn vị gốc mà so ngang giữa các NCC.
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    unit_price: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    vat_percent: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    # BỎ `lead_time_days` (mg 0176 → gỡ 10/08/2026): số ngày NCC giao phải KHAI TAY lúc dựng danh
    # mục, mà lúc đó chưa ai biết ông ấy giao mấy ngày — số đoán lại đi bật đèn "đặt muộn" của kế
    # hoạch vật tư. Cần lại thì SUY từ lịch sử mua (ngày đặt → ngày nhận thật). Cột để nguyên
    # trong DB (không có Alembic, không drop) nhưng không còn code nào đọc/ghi.
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    supplier: Mapped[Supplier] = relationship("Supplier", back_populates="items")


class PurchaseRequest(Base):
    __tablename__ = "purchase_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=PR_DRAFT, index=True)
    supplier_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("suppliers.id", ondelete="SET NULL"), index=True, nullable=True
    )
    # DORMANT từ 07/08/2026 — gộp vào `content`. Giữ cột vì dự án không có Alembic; thôi đọc, thôi ghi.
    purpose: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Ô GỘP "Nội dung / mục đích" — thay cho cặp `purpose` + `note` (chủ chốt 07/08/2026).
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Lý do TỪ CHỐI · HUỶ · ĐÓNG ĐƠN · MỞ LẠI. Tách hẳn khỏi `content`: trước đây `cancel()` chạy
    # `row.note = reason` ⇒ GHI ĐÈ mất ghi chú của người lập. Và nối vào cuối nội dung thì không
    # lọc được "những đơn bị từ chối vì lý do gì".
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    needed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_receipt_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Số hợp đồng mua. Bản thân hợp đồng là ẢNH đính kèm (`purchase_attachments.kind='hop_dong'`) —
    # cố ý KHÔNG dựng danh mục hợp đồng (chủ chốt 06/08/2026, Đ3).
    contract_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Cọc DỰ KIẾN theo hợp đồng — chỉ để nhắc kế toán, TUYỆT ĐỐI không vào công thức công nợ.
    # Tiền cọc THẬT luôn là một Phiếu chi `payment_stage='advance'` đã chi (Đ2). Để số này vào công
    # thức là trừ cọc HAI LẦN khi kế toán lập cả phiếu chi cọc.
    deposit_expected: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    supplier: Mapped[Supplier | None] = relationship("Supplier")
    lines: Mapped[list["PurchaseRequestLine"]] = relationship(
        "PurchaseRequestLine",
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="PurchaseRequestLine.id",
    )
    sources: Mapped[list["PurchaseRequestSource"]] = relationship(
        "PurchaseRequestSource",
        back_populates="purchase_request",
        cascade="all, delete-orphan",
        order_by="PurchaseRequestSource.id",
    )
    payment_vouchers: Mapped[list["PaymentVoucher"]] = relationship(
        "PaymentVoucher",
        back_populates="purchase_request",
        order_by="PaymentVoucher.id",
    )
    deliveries: Mapped[list["PurchaseDelivery"]] = relationship(
        "PurchaseDelivery",
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="PurchaseDelivery.seq_no",
    )
    attachments: Mapped[list["PurchaseAttachment"]] = relationship(
        "PurchaseAttachment",
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="PurchaseAttachment.id",
    )


class PurchaseRequestLine(Base):
    __tablename__ = "purchase_request_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    purchase_request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("purchase_requests.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Dòng của YCMH đã đẻ ra dòng này. Nối DÒNG ↔ DÒNG, khác `purchase_request_sources` (nối
    # PHIẾU ↔ YÊU CẦU). Không có nó thì chỉ biết "phiếu này đến từ yêu cầu kia", không biết dòng
    # giấy trong phiếu là dòng nào của yêu cầu ⇒ không hiện được trạng thái TỪNG SẢN PHẨM.
    #
    # KHÔNG ghép bù bằng tên hàng: thu mua sửa được tên khi lập phiếu (hệ còn chủ động gợi ý sửa
    # cho khớp danh mục NCC), và một yêu cầu có thể có hai dòng trùng tên. Ghép trượt thì im lặng
    # hiện SAI trạng thái, không báo lỗi.
    #
    # NULL = phiếu lập trước 05/08/2026, hoặc dòng thu mua tự thêm ngoài yêu cầu.
    department_request_line_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("department_purchase_request_lines.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # MẶT HÀNG GỐC của dòng (mg 0174) — kế thừa từ dòng YCMH qua `department_request_line_id`.
    # NULL = dòng mua thứ ngoài danh mục vật tư (dịch vụ, gia công) hoặc phiếu lập trước 08/08/2026.
    # Bảng cân đối CHỈ cộng "hàng đang về" cho dòng CÓ gắn — không đoán ngược từ `item_name`.
    hang_loai: Mapped[str | None] = mapped_column(String(8), nullable=True)
    hang_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False, default="cái")
    quantity: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    # Số THỰC NHẬN, khai lúc bấm "Đã nhận hàng". NULL = chưa ai khai ⇒ coi như nhận đủ `quantity`,
    # nhờ vậy mọi phiếu lập trước 05/08/2026 giữ nguyên số tiền, không đơn nào tự đổi giá trị.
    # Công nợ phải trả cộng theo cột này, không theo `quantity` — NCC giao thiếu mà vẫn ghi nợ đủ
    # là kế toán chi thừa.
    received_quantity: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    expected_unit_price: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    discount_percent: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    vat_percent: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    request: Mapped[PurchaseRequest] = relationship("PurchaseRequest", back_populates="lines")


DOC_YCMH = "ycmh"
DOC_PMH = "pmh"
STATUS_DOC_TYPES = (DOC_YCMH, DOC_PMH)

# Ai làm đổi trạng thái. `may` = hệ tự suy, KHÔNG ai bấm — xem `PurchaseStatusHistory`.
CHANGE_BY_NGUOI = "nguoi"
CHANGE_BY_MAY = "may"
CHANGE_SOURCES = (CHANGE_BY_NGUOI, CHANGE_BY_MAY)


class PurchaseStatusHistory(Base):
    """LỊCH SỬ TRẠNG THÁI của yêu cầu mua hàng và phiếu mua hàng (chủ chốt 07/08/2026).

    Vì sao KHÔNG dùng `audit_logs`: cột `detail` bên đó là chữ tự do (`"PMH-x — lý do y"`). Suy
    ngược ra *"trạng thái TRƯỚC ĐÓ là gì"* từ chữ tự do là đoán, mà đoán trượt thì màn hiện sai và
    không có gì báo lỗi.

    Vì sao có cột `source`: trạng thái YCMH là số **SUY RA** từ các phiếu con
    (`_tinh_lai_trang_thai_ycmh`) — duyệt một PMH thì YCMH tự nhảy, không ai bấm gì. Không phân
    biệt người/máy thì lịch sử hiện một dòng đổi trạng thái không tên ai, người đọc tưởng mất dữ
    liệu.

    ⚠️ CHỈ ghi khi trạng thái THỰC SỰ đổi, và CHỈ ghi đổi trạng thái. Sửa nội dung/dòng hàng vẫn
    thuộc `audit_logs`. Bảng này mà thành nơi ghi mọi thứ là nó phình vô ích.
    """

    __tablename__ = "purchase_status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # SOFT REF: `doc_id` trỏ sang `department_purchase_requests` HOẶC `purchase_requests` tuỳ
    # `doc_type` — hai bảng khác nhau nên không khai khoá ngoại được.
    doc_type: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    doc_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # NULL = dòng ĐẦU TIÊN (lúc chứng từ ra đời).
    from_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    to_status: Mapped[str] = mapped_column(String(24), nullable=False)
    # NULL = MÁY tự suy, không ai bấm.
    changed_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source: Mapped[str] = mapped_column(String(8), nullable=False, default=CHANGE_BY_NGUOI)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )


class PurchaseDelivery(Base):
    """ĐỢT GIAO — một lần NCC giao hàng cho một phiếu mua.

    Vì sao phải có bảng này (chủ chốt 06/08/2026): trước đó số thực nhận là MỘT con số cộng dồn trên
    `purchase_request_lines.received_quantity`, không ngày, không lịch sử, không hoá đơn. Hệ quả là
    công nợ chỉ biết hai trạng thái "chưa nhận gì" và "nhận cả đơn":
      - giao 1/3 đợt ⇒ đơn còn `purchased` ⇒ màn Công nợ hiện 0đ trong khi đã nợ thật (GIẤU NỢ);
      - bấm "Đã nhận hàng" sớm ⇒ ghi nợ đủ 100% khi hàng mới về 1/3 (THỪA NỢ).

    Có đợt giao thì **nợ phát sinh theo từng đợt** — hàng về tới đâu nợ tới đó.

    HOÁ ĐƠN: nhiều đợt mang CÙNG `invoice_number` = cùng MỘT hoá đơn (thực tế NCC hay giao 3 đợt
    rồi mới xuất một hoá đơn chung). Cố ý chưa tách bảng `purchase_invoices` — khi nào cần hoá đơn
    mang SỐ TIỀN riêng lệch với tổng các đợt (VAT làm tròn, chiết khấu cuối kỳ) thì mới tách.
    """

    __tablename__ = "purchase_deliveries"
    __table_args__ = (
        UniqueConstraint("purchase_request_id", "seq_no", name="uq_purchase_delivery_seq"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    purchase_request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("purchase_requests.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Đợt 1, 2, 3… trong phạm vi MỘT phiếu mua. Cố ý KHÔNG cấp mã chứng từ toàn hệ: đợt giao không
    # phải chứng từ ký được, nó là sự kiện của phiếu mua.
    seq_no: Mapped[int] = mapped_column(Integer, nullable=False)
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Hạn trả riêng của đợt/dữ liệu cũ. Khi có ngày hóa đơn + số ngày cho nợ, service ưu tiên suy
    # `invoice_date + suppliers.credit_days`; chưa có ngày hóa đơn mới dùng hạn này hoặc ngày giao.
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    invoice_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # SỐ TIỀN của đợt, theo HOÁ ĐƠN — người khai gõ tay (chủ chốt 06/08/2026, sửa Đ4).
    #
    # Ban đầu thiết kế để máy tự tính từ đơn giá trên phiếu, cố ý không có cột này. Chủ bác bỏ:
    # thực tế NCC xuất hoá đơn với số tiền KHÔNG suy được từ đơn giá đặt (giao 500 cái nhưng hoá
    # đơn ghi 5tr — gộp cước, bù chênh, làm tròn theo hợp đồng...). Tự tính khi đó là ra một con số
    # không khớp chứng từ, mà chứng từ mới là thứ đi đối chiếu với NCC.
    #
    # NULL = chưa khai ⇒ LÙI VỀ số máy tính từ đơn giá (`gia_tri_dot_giao`). Nhờ vậy đợt ghi trước
    # thay đổi này giữ nguyên giá trị, và người dùng vẫn được máy gợi ý sẵn khi mở form.
    amount: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 🔌 Chỗ neo cho Phiếu nhập kho. Đợt giao và phiếu nhập kho là CÙNG một sự kiện vật lý (hàng về
    # tới cửa) — khi build Kho ↔ Mua hàng thì nối vào đây, đừng đẻ khái niệm thứ ba. Soft ref (không
    # FK) vì module Kho có thể chưa có bảng lúc migration chạy. Đợt này luôn NULL.
    stock_voucher_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    request: Mapped[PurchaseRequest] = relationship("PurchaseRequest", back_populates="deliveries")
    lines: Mapped[list["PurchaseDeliveryLine"]] = relationship(
        "PurchaseDeliveryLine",
        back_populates="delivery",
        cascade="all, delete-orphan",
        order_by="PurchaseDeliveryLine.id",
    )
    attachments: Mapped[list["PurchaseAttachment"]] = relationship(
        "PurchaseAttachment",
        back_populates="delivery",
        cascade="all, delete-orphan",
        order_by="PurchaseAttachment.id",
    )


class PurchaseDeliveryLine(Base):
    """Dòng của một đợt giao — mặt hàng nào, đợt này nhận bao nhiêu.

    CỐ Ý KHÔNG CÓ CỘT TIỀN. Tiền của đợt = `quantity` × đơn giá/CK/VAT đã chốt ở
    `purchase_request_lines`. Mở ô tiền ở đây là đẻ nguồn sự thật thứ hai: tổng các đợt sẽ lệch với
    giá trị đơn mà không ai phát hiện cho tới lúc đối chiếu với NCC. NCC tính khác đơn giá đặt thì
    sửa đơn giá trên PMH rồi duyệt lại.
    """

    __tablename__ = "purchase_delivery_lines"
    __table_args__ = (
        UniqueConstraint("delivery_id", "purchase_request_line_id", name="uq_purchase_delivery_line"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    delivery_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("purchase_deliveries.id", ondelete="CASCADE"), index=True, nullable=False
    )
    purchase_request_line_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("purchase_request_lines.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    quantity: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    delivery: Mapped[PurchaseDelivery] = relationship("PurchaseDelivery", back_populates="lines")
    request_line: Mapped["PurchaseRequestLine"] = relationship("PurchaseRequestLine")


class PurchaseAttachment(Base):
    """Ảnh/file của mua hàng — hợp đồng (treo ở PMH) hoặc hoá đơn/biên bản (treo ở đợt giao).

    Bytes nằm trong kho file `mua-hang/<purchase_request_id>/` (app/storage.py), đọc lại qua
    /api/files; DB chỉ giữ metadata + path.

    ⚠️ Tiền tố `mua-hang` PHẢI có trong `_PREFIX_PERMISSION` (`routers/files.py`). Bảng đó fail-MỞ:
    tiền tố không khai thì chỉ cần đăng nhập là đọc được — tức hợp đồng NCC lộ cho toàn công ty.
    """

    __tablename__ = "purchase_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    purchase_request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("purchase_requests.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # NULL = file của cả phiếu mua (hợp đồng). Có giá trị = file của riêng một đợt giao.
    delivery_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("purchase_deliveries.id", ondelete="CASCADE"), index=True, nullable=True
    )
    kind: Mapped[str] = mapped_column(
        String(24), nullable=False, default=PURCHASE_ATTACHMENT_KHAC
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    uploaded_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    request: Mapped[PurchaseRequest] = relationship("PurchaseRequest", back_populates="attachments")
    delivery: Mapped[PurchaseDelivery | None] = relationship(
        "PurchaseDelivery", back_populates="attachments"
    )


class DepartmentPurchaseRequest(Base):
    __tablename__ = "department_purchase_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=DPR_OPEN, index=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    requesting_department_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("departments.id", ondelete="SET NULL"), index=True, nullable=True
    )
    requested_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    related_document_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    related_document_code: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    # DORMANT từ 07/08/2026 — gộp vào `content`. Giữ cột, thôi đọc thôi ghi.
    purpose: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    needed_date: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    requesting_department = relationship("Department")
    requested_by = relationship("User")
    lines: Mapped[list["DepartmentPurchaseRequestLine"]] = relationship(
        "DepartmentPurchaseRequestLine",
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="DepartmentPurchaseRequestLine.id",
    )
    purchase_links: Mapped[list["PurchaseRequestSource"]] = relationship(
        "PurchaseRequestSource",
        back_populates="department_request",
        order_by="PurchaseRequestSource.id",
    )


class DepartmentPurchaseRequestLine(Base):
    __tablename__ = "department_purchase_request_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    department_request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("department_purchase_requests.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # MẶT HÀNG GỐC của dòng (mg 0174) — nút "Đề nghị mua" ở bảng cân đối vật tư ghi thẳng vào đây,
    # nên phiếu mua sinh ra sau đó kế thừa được mà không phải đoán tên. NULL = khai tay ngoài danh mục.
    hang_loai: Mapped[str | None] = mapped_column(String(8), nullable=True)
    hang_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    expected_unit_price: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    request: Mapped[DepartmentPurchaseRequest] = relationship(
        "DepartmentPurchaseRequest", back_populates="lines"
    )


class PurchaseRequestSource(Base):
    __tablename__ = "purchase_request_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    purchase_request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("purchase_requests.id", ondelete="CASCADE"), index=True, nullable=False
    )
    department_request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("department_purchase_requests.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    source_code_snapshot: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    purchase_request: Mapped[PurchaseRequest] = relationship(
        "PurchaseRequest", back_populates="sources"
    )
    department_request: Mapped[DepartmentPurchaseRequest] = relationship(
        "DepartmentPurchaseRequest", back_populates="purchase_links"
    )
