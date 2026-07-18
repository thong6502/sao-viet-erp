"""Customer ORM model (Khách hàng / CRM contact) — spec-06-khach-hang.

One row per customer in the sales contact book. "Mở rộng từ nền RBAC" (DOMAIN §23
L528): a customer is owned by a Sale (`sale_user_id → users.id`) so RBAC data-scope
(own/department/all) can narrow the list. `tax_code` (MST) is optional (khách lẻ có
thể không có MST) and only *soft*-checked for duplicates — the domain is explicit that
this is a warning, NOT a hard block (§34 L885, §41 L1133), so it is indexed but NOT
unique. `credit_limit` is a plain VND integer here; the live receivable balance lives
in Công nợ and is read через SEAM-16 — never stored on this row. Portable across
SQLite and Postgres.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# Allowed values for `status`. `lead` = khách tiềm năng (đang chào hàng, chưa phát sinh
# giao dịch — khảo sát #22: lưu cả khách chưa có đơn để sale chăm sóc trên phần mềm).
STATUS_LEAD = "lead"
STATUS_ACTIVE = "active"
STATUS_INACTIVE = "inactive"
CUSTOMER_STATUSES = (STATUS_LEAD, STATUS_ACTIVE, STATUS_INACTIVE)

# Loại khách (redesign spec-06 v2) — quyết định có cần MST hay không.
#   ca_nhan  — cá nhân / khách lẻ: KHÔNG bắt buộc MST (form ẩn ô MST).
#   cong_ty  — doanh nghiệp: hiện MST (tùy chọn, cảnh báo trùng mềm).
KIND_CA_NHAN = "ca_nhan"
KIND_CONG_TY = "cong_ty"
CUSTOMER_KINDS = (KIND_CA_NHAN, KIND_CONG_TY)

# Kiểu mốc điều khoản thanh toán (khảo sát #12 — "mỗi khách một đặc thù, không cố định"):
#   prepay        — trả trước X% khi đặt hàng
#   net_delivery  — X ngày kể từ ngày nhận hàng
#   net_eom       — đối chiếu cuối tháng, X ngày sau đối chiếu
#   custom        — đặc thù khác, mô tả ở payment_term_note
PAYMENT_TERM_TYPES = ("prepay", "net_delivery", "net_eom", "custom")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # System-generated sequential code (KH001, KH002…). Unique + read-only; never entered
    # by the user (spec-06 KH-02, following the PB### pattern of feat-023).
    code: Mapped[str] = mapped_column(
        String(20), unique=True, index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # MST (mã số thuế). Optional; indexed for the duplicate-check but NOT unique — a
    # duplicate MST is a soft warning, not a block (§34 L885, §41 L1133).
    tax_code: Mapped[str | None] = mapped_column(
        String(20), index=True, nullable=True
    )
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Contact person at the customer (suy luận CRM — not in the domain but standard).
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Credit limit in VND (integer đồng), default 0. This is the LIMIT only; the live
    # outstanding balance is read from Công nợ via SEAM-16, never stored here.
    credit_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # Owning Sale (RBAC scope owner). Nullable so a customer can exist unassigned;
    # indexed because every scoped list query filters on it.
    sale_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), index=True, nullable=True
    )
    # DORMANT (redesign spec-06 v2): trạng thái lead/active/inactive đã BỎ khỏi UI + logic
    # (không còn ô chọn / tab lọc). Cột giữ lại default 'active' để dữ liệu cũ không vỡ; đừng
    # dùng cho nghiệp vụ mới.
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=STATUS_ACTIVE, server_default=STATUS_ACTIVE
    )
    # Loại KH (redesign spec-06 v2). Khách cũ mặc định 'cong_ty' (ERP in chủ yếu B2B); cá
    # nhân sửa tay. Cá nhân → form ẩn MST; công ty → hiện MST (tùy chọn).
    customer_kind: Mapped[str] = mapped_column(
        String(12), nullable=False, default=KIND_CONG_TY, server_default=KIND_CONG_TY
    )
    # Số ngày công nợ TỐI ĐA — thời hạn khách phải thanh toán, tính từ NGÀY XUẤT HÓA ĐƠN
    # (net terms; redesign spec-06 v2). Cặp với `credit_limit` thành chính sách "cho nợ":
    # được nợ tối đa X đồng VÀ trong Y ngày. None = chưa đặt hạn ngày. Sửa cần quyền
    # `set_credit_terms`. Đợt này chỉ LƯU + HIỂN THỊ; cảnh báo/chặn khi quá hạn là việc của
    # Công nợ AR (SEAM để sau).
    payment_term_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # --- DORMANT (2026-07-15): kiểu điều khoản (dropdown prepay/net_eom/custom) + % trả trước
    # + ghi chú tự do đã BỎ khỏi UI theo yêu cầu; giờ chỉ giữ SỐ NGÀY ở trên. Cột giữ lại
    # (SQLite không drop gọn); đừng dùng.
    payment_term_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    prepay_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    payment_term_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # DORMANT (redesign spec-06 v2): "chiết khấu mặc định" (trade/buyer) đã BỎ, thay bằng
    # rào chiết khấu/biên min–max bên dưới. Cột giữ lại (SQLite không drop gọn); đừng dùng.
    discount_trade_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    discount_buyer_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    # --- Chính sách CHIẾT KHẤU & BIÊN LỢI NHUẬN (rào chắn báo giá, redesign spec-06 v2).
    # % ∈ [0,100], min ≤ max; None = chưa đặt rào. Sửa cần quyền `set_credit_terms` (đã mở
    # rộng nghĩa = "chính sách tài chính"). Đợt này chỉ LƯU + HIỂN THỊ; việc CHẶN/cảnh báo
    # khi lập báo giá là chỗ nối engine Báo giá (SEAM để lại).
    discount_min_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    discount_max_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    margin_min_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    margin_max_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class CustomerContact(Base):
    """Một người liên hệ của khách hàng (khảo sát #10–#11: khách luôn có nhiều người —
    mua hàng, kho, kế toán, kỹ thuật… — cần ghi chức vụ + nhiệm vụ để các bộ phận tự
    liên hệ). `customers.contact_name` vẫn giữ làm "liên hệ nhanh" trên form."""

    __tablename__ = "customer_contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)   # chức vụ
    duty: Mapped[str | None] = mapped_column(String(255), nullable=True)    # nhiệm vụ
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Liên hệ chính (khảo sát #11) — service giữ bất biến: tối đa MỘT is_primary/khách.
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class CustomerAddress(Base):
    """Một địa điểm giao hàng của khách (khảo sát #9: "khách hàng luôn có nhiều vị trí
    giao hàng"). CHỖ NỐI Tính giá: khi báo giá cần phí giao hàng, Tính giá sẽ đọc danh
    sách này để chọn điểm giao — chưa wire ở đợt này."""

    __tablename__ = "customer_addresses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    label: Mapped[str] = mapped_column(String(120), nullable=False)  # "Nhà máy Bắc Ninh"
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Địa chỉ giao mặc định — service giữ bất biến: tối đa MỘT is_default/khách.
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


# Loại tài liệu đính kèm hồ sơ KH (khảo sát #21: hợp đồng, GPKD, file thiết kế, khác).
DOC_HOP_DONG = "hop_dong"
DOC_GPKD = "gpkd"
DOC_THIET_KE = "thiet_ke"
DOC_KHAC = "khac"
CUSTOMER_DOC_KINDS = (DOC_HOP_DONG, DOC_GPKD, DOC_THIET_KE, DOC_KHAC)


class CustomerTag(Base):
    """Nhãn phân loại do SALES GÁN TAY (khảo sát #7: khách lẻ / doanh nghiệp / đại lý /
    VIP… "rất cần để phân loại chăm sóc"). Nhãn tự do, một khách nhiều nhãn; service
    chặn trùng nhãn (case-insensitive) trong cùng một khách. Chạy SONG SONG với tier
    tự động — nhãn là người nói, tier là dữ liệu nói."""

    __tablename__ = "customer_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    label: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


# Hình thức chăm sóc (khảo sát #27: gọi điện, nhắn tin, email, gặp trực tiếp…).
CARE_GOI_DIEN = "goi_dien"
CARE_NHAN_TIN = "nhan_tin"
CARE_EMAIL = "email"
CARE_GAP = "gap_truc_tiep"
CARE_KHAC = "khac"
CARE_KINDS = (CARE_GOI_DIEN, CARE_NHAN_TIN, CARE_EMAIL, CARE_GAP, CARE_KHAC)


class CustomerCareEvent(Base):
    """Một lần chăm sóc ĐÃ THỰC HIỆN (khảo sát #20: "đã quy định làm việc trên một nền
    tảng số" — ngày nào gọi, trao đổi gì). Hiện trong tab Chăm sóc và gộp vào timeline
    Nhật ký của khách."""

    __tablename__ = "customer_care_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(
        String(24), nullable=False, default=CARE_KHAC, server_default=CARE_KHAC
    )
    note: Mapped[str] = mapped_column(String(1000), nullable=False)
    # Thời điểm chăm sóc thật (cho phép ghi bù buổi gặp hôm qua) — mặc định lúc ghi.
    happened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


# Trạng thái việc chăm sóc (lịch hẹn / follow-up).
TASK_OPEN = "open"
TASK_DONE = "done"
TASK_CANCELLED = "cancelled"
CARE_TASK_STATUSES = (TASK_OPEN, TASK_DONE, TASK_CANCELLED)

# Chu kỳ lặp lịch hẹn (redesign-lich-hen-cham-soc). 'none' = hẹn đơn lẻ (tương thích ngược).
REPEAT_FREQS = ("none", "day", "week", "month")


class CustomerCareTask(Base):
    """Một việc chăm sóc CẦN LÀM (khảo sát #27–#28: "hẹn ngày 15 gọi lại"; hệ thống nhắc
    lần 1/2/3 khi quá hạn). Mức nhắc KHÔNG lưu — tính từ số ngày quá hạn khi đọc (lần 1 =
    đến hạn, lần 2 = quá ≥2 ngày, lần 3 = quá ≥5 ngày) để con số luôn thật, không cần cron."""

    __tablename__ = "customer_care_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    note: Mapped[str] = mapped_column(String(500), nullable=False)  # việc cần làm
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=TASK_OPEN, server_default=TASK_OPEN, index=True
    )
    # Người phụ trách việc — mặc định Sale phụ trách khách (panel "Cần chăm sóc" lọc theo đây).
    assignee_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), index=True, nullable=True
    )
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # --- Lịch hẹn calendar (redesign-lich-hen-cham-soc): luật lặp + chuỗi ngoại lệ ---
    # Hẹn-đầu-chuỗi mang luật (repeat_freq≠'none'); due_date = mốc lần đầu. Lần tương lai KHÔNG
    # lưu — bung ảo khi đọc lịch. Chỉ lần bị đụng (xong/dời/hủy) mới thành 1 dòng ngoại lệ
    # (series_id = id hẹn-đầu-chuỗi, occurrence_date = lần được thay). 'none' = hẹn đơn lẻ như cũ.
    repeat_freq: Mapped[str] = mapped_column(String(8), nullable=False, server_default="none", default="none")
    repeat_interval: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1", default=1)
    repeat_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    series_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    occurrence_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class CustomerNote(Base):
    """Ghi chú TỰ DO của team về một khách (tab "Ghi chú"). Khác hẳn:
      - CustomerCareEvent (Chăm sóc): việc ĐÃ LÀM, có loại + timeline;
      - AuditLog / mốc chứng từ (Nhật ký): sự kiện hệ thống.
    Đây là LƯU Ý dùng chung ("khách khó tính · thích giao sáng · chốt qua Zalo nhanh nhất").
    `pinned` đẩy ghi chú quan trọng lên đầu; `updated_at` chỉ set khi SỬA NỘI DUNG (None =
    chưa sửa → FE hiện "đã sửa" khi != None; ghim/bỏ ghim KHÔNG tính là sửa). Xem cần quyền
    `read`; thêm/sửa/xóa/ghim cần quyền `update` (không cần quyền tài chính). Bảng MỚI nên
    create_all tự tạo — không cần migration cột. KHÔNG ghi audit (giữ tách khỏi Nhật ký)."""

    __tablename__ = "customer_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    body: Mapped[str] = mapped_column(String(4000), nullable=False)
    pinned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    # Chỉ set khi sửa NỘI DUNG (None = chưa sửa). Không dùng onupdate để ghim không bump.
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class CustomerAttachment(Base):
    """File đính kèm hồ sơ khách hàng. Bytes nằm dưới <backend>/static/crm và được serve
    read-only tại /static; chỉ lưu path ở đây (mirror employee_attachments)."""

    __tablename__ = "customer_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    doc_kind: Mapped[str] = mapped_column(
        String(24), nullable=False, default=DOC_KHAC, server_default=DOC_KHAC
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str | None] = mapped_column(String(100), nullable=True)  # MIME
    uploaded_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
