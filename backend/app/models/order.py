"""Đơn hàng bán (Order + OrderLine + OrderApproval + OrderAttachment) ORM models —
redesign-don-hang-ban.md (khâu ④ CHỐT ĐƠN). V5: cọc KHÔNG còn ở đây — Kế toán lập
PaymentReceipt(source='don_hang_ban', order_id) (models/accounting.py).

An **order** (đơn hàng bán) is created từ một **báo giá đã duyệt** (`accepted`, còn hạn). At chốt
đơn it **snapshots** the priced line copy-on-write so a later price/norm change never rewrites
the đơn.

P1 redesign (2026-07-15) — quyết định đã khóa (xem docs/redesign-don-hang-ban.md):
  - **1 nguồn:** `bao_gia` (ghim quotation_id+version+effective_from, giá+giá vốn bất biến).
    Đơn bổ sung (`order_kind=bo_sung`, `parent_order_id`) giữ kẽm → giá riêng.
  - **% cọc = ghim từ BÁO GIÁ** (`deposit_pct`), khóa trên đơn. Số ngày công nợ KHÔNG giữ ở đơn.
  - **Trạng thái active:** draft → ordered → cancelled. (`on_hold`/`change_order` dormant.)
  - **Hủy:** `cancel_*` (lý do + lỗi tại ai) — cọc KHÔNG xóa; "còn cọc chưa quyết toán" SUY RA từ
    data (đơn hủy + Σ cọc đã nhận > 0). Duyệt bản in + tiến độ SX là luồng NGOÀI hệ thống (bỏ field).

GỠ 2026-08-04 — đường tạo đơn NHẬP TAY + toàn bộ luồng DUYỆT đơn đặc thù. Các hằng/cột dưới đây
thành **DORMANT**: giữ nguyên để 12 đơn `nhap_tay` cũ còn đọc được và vì dự án KHÔNG có Alembic
(`create_all` không ALTER được) — không phải vì còn ai dùng. Cùng kiểu với `has_customer_paper`.
DORMANT: `SOURCE_NHAP_TAY` · `order_nature` · `invoice_entity_*` · `needs_approval` ·
`approval_state` · bảng `order_approvals`.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Numeric,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from ..db import Base

# --- source_type (P1 redesign): nguồn tạo đơn ---------------------------------
SOURCE_BAO_GIA = "bao_gia"        # NGUỒN DUY NHẤT hiện nay
SOURCE_NHAP_TAY = "nhap_tay"      # DORMANT — đường tạo đã gỡ, hằng còn để ĐỌC đơn cũ
SOURCE_TYPES = (SOURCE_BAO_GIA, SOURCE_NHAP_TAY)

# --- order_nature: DORMANT (gỡ cùng vùng "Bản chất đơn" trên UI) ---------------
NATURE_HANG_HOA = "hang_hoa"      # xưởng lo hết → HĐ toàn bộ giá trị
NATURE_GIA_CONG = "gia_cong"      # khách ứng giấy → HĐ chỉ tiền công
ORDER_NATURES = (NATURE_HANG_HOA, NATURE_GIA_CONG)

# --- order_type (§41, dormant) -------------------------------------------------
ORDER_TYPE_NOI_BO = "noi_bo"
ORDER_TYPE_THEO_YC = "theo_yc"
ORDER_TYPES = (ORDER_TYPE_NOI_BO, ORDER_TYPE_THEO_YC)

# --- order_kind ----------------------------------------------------------------
ORDER_KIND_MOI = "moi"            # đơn mới
ORDER_KIND_BO_SUNG = "bo_sung"    # đơn bổ sung (giữ kẽm → giá riêng), bắt buộc parent_order_id
ORDER_KINDS = (ORDER_KIND_MOI, ORDER_KIND_BO_SUNG)

# --- Lifecycle (state machine) — active: draft/ordered/cancelled ---------------
STATUS_DRAFT = "draft"              # đang lập (chưa chốt) — dòng đơn còn sửa
STATUS_ORDERED = "ordered"         # đã chốt (gate đạt) — khóa cứng, xuống SX
STATUS_CANCELLED = "cancelled"     # đã hủy (+cancel_*)
STATUS_ON_HOLD = "on_hold"         # DORMANT (redesign bỏ) — giữ hằng số cho tương thích
STATUS_CHANGE_ORDER = "change_order"  # DORMANT (redesign bỏ)

ORDER_STATUSES = (
    STATUS_DRAFT,
    STATUS_ORDERED,
    STATUS_CANCELLED,
)

# --- approval_state: DORMANT (luồng duyệt đơn đã gỡ) ---------------------------
# Chỉ còn APPROVAL_STATE_NONE được GHI (mọi đơn mới); 3 giá trị kia không sinh ra nữa.
APPROVAL_STATE_NONE = "none"        # đơn không cần duyệt
APPROVAL_STATE_PENDING = "pending"  # đã "Trình duyệt", chờ người có quyền
APPROVAL_STATE_APPROVED = "approved"
APPROVAL_STATE_REJECTED = "rejected"
APPROVAL_STATES = (
    APPROVAL_STATE_NONE,
    APPROVAL_STATE_PENDING,
    APPROVAL_STATE_APPROVED,
    APPROVAL_STATE_REJECTED,
)

# --- cost_basis: nguồn/độ tin của giá vốn để báo cáo biên trung thực -----------
COST_BASIS_QUOTE = "quote"          # từ báo giá (có giá vốn)
COST_BASIS_NONE = "none"            # nhập tay không giá vốn → biên "không xác định"

# --- cancel_fault --------------------------------------------------------------
FAULT_KHACH = "khach"
FAULT_XUONG = "xuong"
CANCEL_FAULTS = (FAULT_KHACH, FAULT_XUONG)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # System-generated order number (DH001, DH002…). Unique.
    order_no: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)

    customer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="SET NULL"), index=True, nullable=True
    )
    # --- C1 pin: quotation reference (id + version + effective_from) — SEAM-04 --
    quotation_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    quotation_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quotation_effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Nguồn + bản chất
    source_type: Mapped[str] = mapped_column(String(16), nullable=False, default=SOURCE_BAO_GIA)
    order_nature: Mapped[str] = mapped_column(String(16), nullable=False, default=NATURE_HANG_HOA)
    order_type: Mapped[str] = mapped_column(String(16), nullable=False, default=ORDER_TYPE_THEO_YC)
    order_kind: Mapped[str] = mapped_column(String(16), nullable=False, default=ORDER_KIND_MOI)
    # Đơn bổ sung → BẮT BUỘC trỏ đơn gốc (self-FK); NULL cho đơn mới.
    parent_order_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("orders.id", ondelete="SET NULL"), index=True, nullable=True
    )

    # NV kinh doanh phụ trách + RBAC data-scope owner.
    sale_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), index=True, nullable=True
    )

    status: Mapped[str] = mapped_column(String(16), nullable=False, default=STATUS_DRAFT)

    # DORMANT (thay bằng order_nature) — giữ cột để không mất dữ liệu cũ.
    has_customer_paper: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    vat_pct_estimate: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # % HOA HỒNG của đơn này (mg 0227 · docs/redesign-luong-kinh-doanh.md §4.6). PHÂN SỐ:
    # 0.05 = 5%, cùng quy ước `employee_salaries.commission_pct`.
    #
    # CHỤP ẢNH lúc CHỐT đơn từ mức của chính người sales (`employee_salaries.commission_pct`,
    # versioned). Chụp chứ không đọc-sống: đổi % cho người ta từ tháng sau KHÔNG được làm đổi
    # hoa hồng của đơn đã chốt tháng trước — tiền đã hứa thì không sửa ngược.
    #
    # 0 = đơn này không có hoa hồng (mặc định của mọi đơn).
    commission_pct: Mapped[float] = mapped_column(
        Numeric(6, 4), nullable=False, default=0, server_default="0"
    )

    # --- P1: thông tin đặt hàng (Sale nhập khi nháp) ----------------------------
    customer_po_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    delivery_committed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delivery_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Graft đơn V4 (khớp DB_SCHEMA.md §orders): người nhận + SĐT snapshot (Sale xổ từ danh bạ
    # khách CustomerContact, KHÔNG auto-fill is_primary) · lưu ý giao → tài xế · lưu ý SX → tổ in.
    delivery_contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    delivery_contact_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    delivery_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    production_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Hàng gấp — cờ ưu tiên cho sản xuất (graft đơn V4).
    is_rush: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Pháp nhân xuất HĐ (khi khách xin xuất tên khác; mặc định = khách).
    invoice_entity_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    invoice_entity_tax_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # % cọc GHIM TỪ BÁO GIÁ (khóa trên đơn) — base cổng chốt.
    deposit_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Nguồn/độ tin giá vốn: quote (có) / none (nhập tay → biên không xác định).
    cost_basis: Mapped[str] = mapped_column(String(16), nullable=False, default=COST_BASIS_QUOTE)

    # --- Duyệt tại đơn (P3) — nguồn không-qua-báo-giá ---------------------------
    needs_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approval_state: Mapped[str] = mapped_column(String(16), nullable=False, default=APPROVAL_STATE_NONE)

    # --- Chốt (P4) --------------------------------------------------------------
    ordered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ordered_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )

    # --- Chuyển xuống sản xuất (handoff Đơn→Kế hoạch) ---------------------------
    # Sale bấm "Chuyển xuống sản xuất" (sau chốt, đủ cọc) → set mốc → đơn vào HÀNG CHỜ kế hoạch.
    # Người QUYẾT (không auto khi chốt); NULL = chưa chuyển.
    san_xuat_released_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- Hủy (P5) ---------------------------------------------------------------
    cancel_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cancelled_at_state: Mapped[str | None] = mapped_column(String(16), nullable=True)  # dormant
    cancel_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    cancel_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_fault: Mapped[str | None] = mapped_column(String(16), nullable=True)  # khach/xuong

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    lines: Mapped[list["OrderLine"]] = relationship(
        "OrderLine",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderLine.id",
    )
    # V5: cọc KHÔNG còn là bảng tự chứa. Kế toán lập PaymentReceipt(source='don_hang_ban',
    # order_id) — cổng đủ cọc đọc Σ PaymentReceipt(order, received). Không relationship ngược
    # ở đây (đọc 1 chiều qua accounting_repo để tránh order phụ thuộc cứng vào kế toán).
    attachments: Mapped[list["OrderAttachment"]] = relationship(
        "OrderAttachment",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderAttachment.id",
    )


class OrderLine(Base):
    __tablename__ = "order_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("orders.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # Mô tả SP thương mại (đối ngoại) — NEVER số màu/kẽm/khổ/imposition/PrintForm.
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    qty: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # ĐVT dòng — kéo từ dòng báo giá (QuoteItem.unit) / gõ tay (graft đơn V4).
    don_vi_tinh: Mapped[str] = mapped_column(String(30), nullable=False, default="cái")

    # Pin TRUY VẾT ấn phẩm (soft, KHÔNG FK cứng) → PhieuThanhPhan.id của PTG mà dòng báo giá nguồn
    # trỏ tới (song sinh QuoteItem.phieu_thanh_phan_id) — nối lại mạch ấn phẩm↔báo giá↔đơn ở khúc
    # chốt bán. KHÔNG đọc-sống để định giá (cost_snapshot mới là chân lý tiền) → không phá
    # copy-on-write. NULL cho đơn nhập tay (không có ấn phẩm định giá).
    phieu_thanh_phan_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Nhãn NHÓM GỘP KHI IN (copy từ `quote_items.nhom`): bản in xác nhận đơn gom các dòng cùng
    # nhãn thành 1 dòng, khớp bản báo giá khách đã nhận. KHÔNG đụng sản xuất — `lsx_service` vẫn
    # sinh 1 lệnh cho MỖI dòng đơn, nên ruột/bìa vẫn ra 2 lệnh riêng.
    nhom: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # --- P0 snapshot copy-on-write ----------------------------------------------
    unit_price_snapshot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    norm_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Giá vốn TỔNG của dòng (cùng grain với line_total). NULL cho đơn nhập tay (không giá vốn).
    cost_snapshot: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    vat_pct_estimate: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    line_total: Mapped[int | None] = mapped_column(Integer, nullable=True)

    order: Mapped["Order"] = relationship("Order", back_populates="lines")


# --- A2/P3: "đơn đặc thù" → duyệt tại đơn (order_approvals) --------------------
APPROVAL_DECISION_APPROVED = "approved"
APPROVAL_DECISION_REJECTED = "rejected"
APPROVAL_DECISIONS = (APPROVAL_DECISION_APPROVED, APPROVAL_DECISION_REJECTED)

EXC_HIGH_VALUE = "high_value"
EXC_LOW_MARGIN = "low_margin"
EXC_BELOW_COST = "below_cost"
EXC_NO_COST = "no_cost"            # nhập tay không giá vốn (luôn cần duyệt)
EXC_DISCOUNT_OUT = "discount_out"
EXC_MARKUP_OUT = "markup_out"    # markup (lợi nhuận/GIÁ VỐN) ngoài rào của khách — cổng BÁO GIÁ


class OrderApproval(Base):
    __tablename__ = "order_approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("orders.id", ondelete="CASCADE"), index=True, nullable=False
    )
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    triggers_json: Mapped[list | None] = mapped_column(JSON, nullable=True)

    order_total: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    order_subtotal: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    order_cost: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
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


# --- Đính kèm CẤP ĐƠN (chứng cứ khách đồng ý — cổng chốt §8d) ------------------
ATTACH_KIND_CONSENT = "consent"     # chứng cứ khách đồng ý (ảnh PO/Zalo…)
ATTACH_KINDS = (ATTACH_KIND_CONSENT,)


class OrderAttachment(Base):
    __tablename__ = "order_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("orders.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default=ATTACH_KIND_CONSENT)
    # URL phục vụ qua /api/files (bytes trong kho file `don-hang/<order_id>/`, cần quyền đọc đơn).
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uploaded_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    order: Mapped["Order"] = relationship("Order", back_populates="attachments")
