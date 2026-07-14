"""Báo giá (Quotation / Quote) ORM models — Header-Version-Item (H-V-I) structure.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    JSON,
    Date,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..db import Base

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

# Status constants for Quote (7 trạng thái nghiệp vụ, xem docs/redesign-bao-gia.md §3).
STATUS_DRAFT = "draft"                       # Nháp
STATUS_PENDING_APPROVAL = "pending_approval" # Chờ duyệt — CHỈ báo giá đặc thù, đã "Trình duyệt"
STATUS_APPROVED = "approved"                 # Đã duyệt — GĐ Kinh doanh duyệt xong, CHỜ sale gửi khách
STATUS_SENT = "sent"                         # Đã gửi khách (sale tự gửi; tách khỏi "duyệt" theo chủ đầu tư)
STATUS_ACCEPTED = "accepted"                 # Khách hàng đồng ý
STATUS_REJECTED = "rejected"                 # Khách hàng từ chối (SAU khi gửi — khác GĐ từ chối duyệt)
STATUS_EXPIRED = "expired"                   # Hết hiệu lực
STATUS_CONVERTED_TO_ORDER = "converted_to_order"  # (ẩn) Đã lên đơn — khóa 1 báo giá = 1 đơn
STATUS_CANCELLED = "cancelled"               # Hủy báo giá

QUOTE_STATUSES = (
    STATUS_DRAFT,
    STATUS_PENDING_APPROVAL,
    STATUS_APPROVED,
    STATUS_SENT,
    STATUS_ACCEPTED,
    STATUS_REJECTED,
    STATUS_EXPIRED,
    STATUS_CONVERTED_TO_ORDER,
    STATUS_CANCELLED,
)

# Status constants for QuoteVersion
VERSION_STATUS_DRAFT = "draft"
VERSION_STATUS_LOCKED = "locked"
VERSION_STATUS_SENT = "sent"
VERSION_STATUS_ACCEPTED = "accepted"
VERSION_STATUS_REJECTED = "rejected"
VERSION_STATUS_SUPERSEDED = "superseded"
VERSION_STATUS_CANCELLED = "cancelled"


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Sequential code like BG26-0001
    quote_number: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    
    customer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="SET NULL"), index=True, nullable=True
    )
    customer_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    estimate_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("estimates.id", ondelete="SET NULL"), index=True, nullable=True
    )
    # BG-1: nguồn báo giá MỚI = 1 Phiếu tính giá (PTG). Soft link (plain int — PTG dùng FK mềm theo
    # convention repo). 1 PTG → 1 BG đang hiệu lực: GUARD ở service (KHÔNG unique cứng — báo giá
    # cancelled/rejected/expired nhả chỗ, cho báo giá lại / repeat order). estimate_id = hệ CŨ (gỡ ở BG-4).
    phieu_tinh_gia_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)

    salesperson_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=STATUS_DRAFT)
    
    # Reference to the current active/accepted or draft version id
    current_version_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    payment_terms: Mapped[str | None] = mapped_column(String(255), nullable=True)
    delivery_terms: Mapped[str | None] = mapped_column(String(255), nullable=True)
    delivery_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Người liên hệ SNAPSHOT trên báo giá (redesign-bao-gia §4/§5) — auto-fill từ CRM
    # `CustomerContact.is_primary` khi chọn khách, sửa được; đóng băng để bản in không đổi.
    contact_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone_snapshot: Mapped[str | None] = mapped_column(String(30), nullable=True)
    contact_title_snapshot: Mapped[str | None] = mapped_column(String(120), nullable=True)
    customer_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    internal_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
    # Real-time "gửi duyệt": mốc người SOẠN (salesperson) đã xem quyết định duyệt/từ chối gần nhất
    # của báo giá này. NULL = có quyết định MỚI chưa xem → nuôi badge/toast phía Sale. Timestamp,
    # KHÔNG Boolean (né gotcha server_default Postgres). Reset về NULL mỗi lần GĐ ra quyết định.
    decision_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    versions: Mapped[list[QuoteVersion]] = relationship(
        "QuoteVersion", back_populates="quote", cascade="all, delete-orphan", order_by="QuoteVersion.version_number"
    )
    attachments: Mapped[list[QuoteAttachment]] = relationship(
        "QuoteAttachment", back_populates="quote", cascade="all, delete-orphan"
    )
    activity_logs: Mapped[list[QuoteActivityLog]] = relationship(
        "QuoteActivityLog", back_populates="quote", cascade="all, delete-orphan"
    )


class QuoteVersion(Base):
    __tablename__ = "quote_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    quote_id: Mapped[int] = mapped_column(Integer, ForeignKey("quotes.id", ondelete="CASCADE"), index=True, nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=VERSION_STATUS_DRAFT)
    change_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    # Snapshots
    estimate_snapshot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    internal_cost_snapshot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    customer_output_snapshot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    pricing_snapshot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    
    total_cost_snapshot: Mapped[float | None] = mapped_column(Numeric(15, 2), nullable=True)
    subtotal_amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    discount_amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    vat_percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    vat_amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    final_amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    
    pdf_file_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    quote: Mapped[Quote] = relationship("Quote", back_populates="versions")
    items: Mapped[list[QuoteItem]] = relationship(
        "QuoteItem", back_populates="quote_version", cascade="all, delete-orphan", order_by="QuoteItem.line_no"
    )


class QuoteItem(Base):
    __tablename__ = "quote_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    quote_version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("quote_versions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # 1 báo giá pick từ NHIỀU phiếu tính giá → mỗi dòng giữ tham chiếu phiếu gốc của riêng nó
    # (Quote.estimate_id ở header chỉ còn là "phiếu đầu tiên" cho tương thích cũ).
    estimate_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("estimates.id", ondelete="SET NULL"), index=True, nullable=True
    )
    estimate_option_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # BG-1: dòng báo giá nguồn từ 1 "sản phẩm" (PhieuThanhPhan) của PTG. Soft ref (gỡ estimate_* ở BG-4).
    phieu_thanh_phan_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    # Mã PO của khách cho dòng này (cột "MÃ PO" trên mẫu báo giá thật) — tùy chọn, nhập tay.
    po_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    
    product_type: Mapped[str] = mapped_column(String(50), nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_spec_text: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    product_spec_snapshot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False, default="cái")
    
    total_cost_snapshot: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    margin_percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    selling_price: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    unit_price: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    discount_amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    vat_percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    vat_amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    final_amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    quote_version: Mapped[QuoteVersion] = relationship("QuoteVersion", back_populates="items")


class QuoteAttachment(Base):
    __tablename__ = "quote_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    quote_id: Mapped[int] = mapped_column(Integer, ForeignKey("quotes.id", ondelete="CASCADE"), index=True, nullable=False)
    quote_version_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("quote_versions.id", ondelete="CASCADE"), index=True, nullable=True
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    
    uploaded_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    quote: Mapped[Quote] = relationship("Quote", back_populates="attachments")


class QuoteActivityLog(Base):
    __tablename__ = "quote_activity_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    quote_id: Mapped[int] = mapped_column(Integer, ForeignKey("quotes.id", ondelete="CASCADE"), index=True, nullable=False)
    quote_version_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("quote_versions.id", ondelete="CASCADE"), index=True, nullable=True
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    old_value_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_value_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    
    actor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    quote: Mapped[Quote] = relationship("Quote", back_populates="activity_logs")


class QuoteApproval(Base):
    """BG-2: GĐ duyệt "báo giá ĐẶC THÙ" (biên thấp / dưới vốn / giá trị cao) — chặn "gửi khách" tới khi
    duyệt. Song sinh với `order_approvals` (cùng máy `exception_gate`), khóa theo `quote_id`. Ghim SỐ +
    NGƯỠNG lúc quyết định để re-check "bao phủ" (báo giá đổi xấu đi → phải trình lại) + audit. Bản GẦN
    NHẤT quyết định cổng. Tiền = BigInteger. Bảng MỚI (create_all tự tạo, không cần migration)."""

    __tablename__ = "quote_approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    quote_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("quotes.id", ondelete="CASCADE"), index=True, nullable=False
    )
    decision: Mapped[str] = mapped_column(String(16), nullable=False)   # approved | rejected
    triggers_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # GHIM số lúc quyết định. total = gồm VAT (mốc quy mô); subtotal = trước VAT (base biên).
    total: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    subtotal: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cost: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    margin_pct_snapshot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_margin_pct: Mapped[int | None] = mapped_column(Integer, nullable=True)
    high_value_threshold: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    decided_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
