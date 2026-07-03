"""Báo giá (Quotation / Quote) ORM models — Header-Version-Item (H-V-I) structure.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from sqlalchemy import (
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

# Status constants for Quote
STATUS_DRAFT = "draft"
STATUS_SENT = "sent"
STATUS_ACCEPTED = "accepted"
STATUS_REJECTED = "rejected"
STATUS_EXPIRED = "expired"
STATUS_CONVERTED_TO_ORDER = "converted_to_order"
STATUS_CANCELLED = "cancelled"

QUOTE_STATUSES = (
    STATUS_DRAFT,
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
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    
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
