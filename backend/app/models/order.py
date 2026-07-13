"""Đơn hàng bán (Order + OrderLine) ORM models — spec-10-don-hang-ban (bước ④ CHỐT ĐƠN).

An **order** (đơn hàng bán) is created AFTER a khách chấp nhận a **báo giá đã duyệt**
(``Quotation.status == approved`` còn hạn). At chốt đơn it **snapshots** the priced
quotation copy-on-write so a later price/norm change never rewrites the đơn:

P0 invariants honoured here (§34 L877-879, §43 #5 L1209-1210):
  - **Nguồn = Báo giá đã duyệt, KHÔNG Tính giá**: the order pins ``quotation_id`` **+**
    ``quotation_version`` **+** ``quotation_effective_from`` (C1 — báo giá versioned, chỉ FK
    là hụt). Read via **SEAM-04** (``quotation_ref``); Báo giá IS built (feat-043..045) so the
    read is live, but the deposit half of SEAM-04 (Payment) is still TREO (feat-048).
  - **Snapshot copy-on-write on the ORDER-LINE**: ``unit_price_snapshot`` (Int) **and**
    ``norm_snapshot`` (JSON) are stored ON ``order_lines`` — there is NO live FK to the
    price/norm tables. Đổi giá gốc sau đó KHÔNG đổi số trên đơn.
  - **Ẩn field vật lý khỏi Sale (§29 P0 L730, §43 #1)**: khổ giấy / số màu / số kẽm /
    imposition / PrintForm are NEVER stored or exposed here — that layer sống ở Sản xuất.

Cardinality (§34/§43 #6): ``Order 1─n Job`` (thực tế n-n Order-line ↔ Job/PrintForm qua bảng
nối, ghép bài) — so there is **no hard FK to Job** here (Sản xuất chưa build). ``parent_order_id``
is a self-FK used **ONLY** for an **đơn bổ sung** (sub-job trỏ đơn gốc); ``change_order`` (đổi)
giữ lịch sử qua Quotation-version, KHÔNG dùng ``parent_order_id`` (Resolved decision #5).

``row_version`` (optimistic locking) is deliberately NOT modelled on Order (doc chỉ mandate
cho Job/Quotation, §34 L898 — Out-of-scope). VAT chân lý ở ``InvoiceLine`` (⑬); the order carries
only ``vat_pct_estimate`` to ước tổng. Portable across SQLite and Postgres.

Cross-module reads are SEAMS (owned by this consumer per DIP; upstream implements later):
  - ``quotation_id`` → **SEAM-04** (Báo giá + Payment) — quotation_ref live, deposit TREO.
  - ``proof.customer_approved`` (cổng ⑤→⑥ chỉ-báo) → **SEAM-05** (Chế bản) — F6, TREO.
  - ``has_customer_paper`` lô giấy chi tiết → **SEAM-06** (Kho) — F4, TREO.
  - tiến độ SX → **SEAM-01** (Sản xuất) · trạng thái giao → **SEAM-02** (Giao hàng) — F7, TREO.
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
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from ..db import Base

# --- order_type (§41 L1135) ----------------------------------------------------
ORDER_TYPE_NOI_BO = "noi_bo"      # nội bộ
ORDER_TYPE_THEO_YC = "theo_yc"    # theo yêu cầu
ORDER_TYPES = (ORDER_TYPE_NOI_BO, ORDER_TYPE_THEO_YC)

# --- order_kind (§32 L807-813) -------------------------------------------------
ORDER_KIND_MOI = "moi"            # đơn mới
ORDER_KIND_BO_SUNG = "bo_sung"    # đơn bổ sung (sub-job, giữ kẽm cũ → rẻ), giá bán riêng
ORDER_KINDS = (ORDER_KIND_MOI, ORDER_KIND_BO_SUNG)

# --- Lifecycle (state machine §9/§32 L825-829) ---------------------------------
# Stored as plain strings; the transition table + guards live in order_state.py.
STATUS_DRAFT = "draft"              # đang lập (chưa chốt) — dòng đơn còn sửa được
STATUS_ORDERED = "ordered"         # đã chốt (gate ③→④ đạt) — snapshot khóa, dòng đơn read-only
STATUS_ON_HOLD = "on_hold"         # tạm giữ
STATUS_CHANGE_ORDER = "change_order"  # đổi đơn (re-quote giữ lịch sử qua Quotation-version)
STATUS_CANCELLED = "cancelled"     # đã hủy (+cancel_reason, cancelled_at_state)

ORDER_STATUSES = (
    STATUS_DRAFT,
    STATUS_ORDERED,
    STATUS_ON_HOLD,
    STATUS_CHANGE_ORDER,
    STATUS_CANCELLED,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # System-generated order number (DH001, DH002…). Unique. NOT `PB###` (PB = mã phòng ban).
    # Pattern chưa xác nhận với SVN — DH### is the working default (documented as unconfirmed).
    order_no: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)

    # SEAM-04: the approved quotation this order references. customer_id is pulled FROM the
    # quotation (§ form: khách chỉ-đọc). FK→customers.id (CRM same-app), nullable so a draft
    # can exist while wiring, but create requires an approved quotation → customer.
    customer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="SET NULL"), index=True, nullable=True
    )
    # --- C1 pin: quotation reference (id + version + effective_from) — SEAM-04 --
    # Plain Integer (NO FK to a live price row): báo giá versioned nên a bare FK là hụt; we
    # ghim the exact version + effective window at chốt (copy-on-write source pointer).
    quotation_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    quotation_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quotation_effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)

    # order_type ∈ {noi_bo, theo_yc} (§41). order_kind ∈ {moi, bo_sung} (§32).
    order_type: Mapped[str] = mapped_column(String(16), nullable=False, default=ORDER_TYPE_THEO_YC)
    order_kind: Mapped[str] = mapped_column(String(16), nullable=False, default=ORDER_KIND_MOI)
    # Đơn bổ sung → BẮT BUỘC trỏ đơn gốc (self-FK); NULL cho đơn mới (§32 L807-813).
    # KHÔNG dùng cho change_order (đổi) — đổi giữ lịch sử qua Quotation-version (decision #5).
    parent_order_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("orders.id", ondelete="SET NULL"), index=True, nullable=True
    )

    # NV kinh doanh phụ trách (hoa hồng) + RBAC data-scope owner (own/department/all, §41).
    sale_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), index=True, nullable=True
    )

    # Lifecycle status (see ORDER_STATUSES). Gate ③→④ để sang `ordered` (§32 L827-828).
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=STATUS_DRAFT)

    # F4 cờ ứng giấy khách. Chi tiết lô giấy (ownership=customer, cost=0) sống ở Kho — read-only
    # link qua SEAM-06 (TREO). KHÔNG nhập tồn ở màn này.
    has_customer_paper: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # VAT DỰ KIẾN để ước tổng — nguồn chân lý VAT là InvoiceLine ở ⑬, KHÔNG chốt ở đây.
    vat_pct_estimate: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # F8 Hủy (state cancelled): reason + the status khi hủy (để biết hoàn/không hoàn vật tư-cọc
    # theo bảng mốc §32 L817-825).
    cancel_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cancelled_at_state: Mapped[str | None] = mapped_column(String(16), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    lines: Mapped[list["OrderLine"]] = relationship(
        "OrderLine",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderLine.id",
    )


class OrderLine(Base):
    __tablename__ = "order_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("orders.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # Mô tả SP thương mại (đối ngoại) — NEVER số màu/kẽm/khổ/imposition/PrintForm (§29 P0).
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    qty: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # --- P0 snapshot copy-on-write (§34 L877-878, §43 #5) -----------------------
    # Frozen unit price (Int, VND) + norm snapshot (JSON) captured từ báo giá at create/chốt.
    # NO live FK to a price/norm table — đổi giá gốc sau KHÔNG đổi số trên đơn.
    unit_price_snapshot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    norm_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # A2 (đơn đặc thù): giá vốn TỔNG của dòng (Int, VND), snapshot copy-on-write từ báo giá
    # (`QuoteItem.total_cost_snapshot`) at create — CÙNG GRAIN với line_total (tổng cả SL). Dùng
    # để soi biên lợi nhuận (tổng đơn = Σ cost_snapshot). NULL cho đơn cũ (trước A2) → bỏ qua soi
    # biên (chỉ trigger giá-trị-cao còn hiệu lực). Snapshot theo DÒNG để biên KHÔNG trôi khi
    # đổi dòng đơn (phản biện nghiệp vụ: 1 số tổng đóng băng sẽ sai khi thêm/bớt dòng).
    # BigInteger (không Integer) — tiền, đơn in giá trị lớn có thể vượt Int 2³¹ trên Postgres.
    cost_snapshot: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # VAT DỰ KIẾN cho dòng (ước tổng) — chân lý ở InvoiceLine (⑬).
    vat_pct_estimate: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Thành tiền = qty * unit_price_snapshot (derived + stored; null khi chưa có giá).
    line_total: Mapped[int | None] = mapped_column(Integer, nullable=True)

    order: Mapped["Order"] = relationship("Order", back_populates="lines")


# --- A2: "đơn đặc thù" → Giám đốc duyệt (order_approvals) ----------------------
# Hệ tự soi đơn khi chuẩn bị chốt: giá trị cao / biên lợi nhuận thấp / bán dưới giá vốn. Trip điều
# kiện → CHẶN chốt tới khi GĐ duyệt (audit). Vượt-hạn-mức-công-nợ HOÃN sang Pha D (chưa có hóa đơn
# → nợ = −cọc là số giả). Một hàng = một QUYẾT ĐỊNH (duyệt/từ chối) của GĐ, GHIM số tại thời điểm
# quyết định (order_total gồm VAT · subtotal trước VAT · giá vốn · ngưỡng đang hiệu lực) để re-check
# "bao phủ" lúc chốt (đơn xấu đi so mức GĐ ký → phải trình lại) + làm căn cứ audit.
APPROVAL_DECISION_APPROVED = "approved"
APPROVAL_DECISION_REJECTED = "rejected"
APPROVAL_DECISIONS = (APPROVAL_DECISION_APPROVED, APPROVAL_DECISION_REJECTED)

# Khóa các điều kiện đặc thù (trigger). "no_credit_check" = vượt-hạn-mức HOÃN Pha D (không dùng nay).
EXC_HIGH_VALUE = "high_value"      # tổng gồm VAT ≥ ngưỡng
EXC_LOW_MARGIN = "low_margin"      # 0 ≤ biên < ngưỡng
EXC_BELOW_COST = "below_cost"      # bán dưới giá vốn (biên < 0)


class OrderApproval(Base):
    __tablename__ = "order_approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("orders.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # 'approved' | 'rejected' (xem APPROVAL_DECISIONS).
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    # Các trigger đang bật lúc quyết định (['high_value','low_margin','below_cost']) — audit/hiển thị.
    triggers_json: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # GHIM số tại thời điểm quyết định (tiền = BigInteger). subtotal = trước VAT (base biên);
    # order_total = gồm VAT (đối chiếu ngưỡng giá-trị-cao); cost = tổng giá vốn snapshot.
    order_total: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    order_subtotal: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    order_cost: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    margin_pct_snapshot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Ngưỡng đang hiệu lực lúc GĐ ký (phản biện: đổi hằng số sau này thì lịch sử duyệt vẫn có căn cứ).
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
