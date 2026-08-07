"""Phiếu nhập / xuất kho — docs/spec-kho-de-nghi.md §5.

**Mọi phiếu bắt buộc ứng theo một đề nghị đã duyệt** (`request_id` NOT NULL). Luật này
khớp BRD: mỗi nghiệp vụ kho đều có chứng từ đề nghị đứng trước (nhập mua ← đề nghị mua
§2.17, nhập TP ← yêu cầu nhập kho của KCS §2.3 b2, xuất cấp bù ← đề xuất cấp bù §2.6 b2…).
Ba miễn trừ của BRD (tồn đầu kỳ §2.1, điều chỉnh sau kiểm kê §2.16, hủy/thanh lý §2.14)
đều NGOÀI phạm vi giai đoạn 1 nên chưa cần cửa thoát.

Phiếu ở trạng thái `draft` chưa đụng tồn; `posted` mới ghi sổ (tạo lô nếu nhập, trừ
`sl_con_lai` nếu xuất) và cộng `sl_da_ung` về dòng đề nghị.

Bảng MỚI → `create_all` tự dựng, không cần migration.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base

VOUCHER_NHAP = "NHAP"
VOUCHER_XUAT = "XUAT"
VOUCHER_KINDS = (VOUCHER_NHAP, VOUCHER_XUAT)

VOUCHER_DRAFT = "draft"          # chưa ghi sổ — chưa đụng tồn
VOUCHER_POSTED = "posted"        # đã ghi sổ — tồn đã đổi
VOUCHER_CANCELLED = "cancelled"  # hủy khi còn nháp
VOUCHER_STATUSES = (VOUCHER_DRAFT, VOUCHER_POSTED, VOUCHER_CANCELLED)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StockVoucher(Base):
    """Header phiếu nhập/xuất — in ra theo mẫu 01-VT / 02-VT (TT200)."""

    __tablename__ = "stock_vouchers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Số phiếu in trên chứng từ (PNK0001 / PXK0001) — sinh qua document_sequences.
    ma: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    loai: Mapped[str] = mapped_column(String(8), index=True, nullable=False)
    # BẮT BUỘC: không có đề nghị thì không có phiếu (spec §5).
    request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stock_requests.id"), index=True, nullable=False
    )
    kho_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("kho_hang.id"), index=True, nullable=False
    )
    ngay: Mapped[date] = mapped_column(Date, nullable=False)
    nguoi_lap_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), index=True, nullable=False
    )
    # Ô "Họ tên người giao hàng" (01-VT) / "người nhận hàng" (02-VT) trên bản in. Text tự
    # do vì người giao có thể là tài xế NCC — không phải user của hệ thống.
    nguoi_giao_nhan: Mapped[str | None] = mapped_column(String(150), nullable=True)
    ghi_chu: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    trang_thai: Mapped[str] = mapped_column(
        String(16), index=True, nullable=False,
        server_default=VOUCHER_DRAFT, default=VOUCHER_DRAFT,
    )
    ghi_so_luc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Ai GHI SỔ (duyệt/chốt) phiếu — người có quyền `post` (Kế toán kho / QL kho). Null khi chưa
    # ghi sổ. Tách khỏi `nguoi_lap_id` (người lập nháp) theo SoD.
    nguoi_ghi_so_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), index=True, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    lines: Mapped[list[StockVoucherLine]] = relationship(
        "StockVoucherLine",
        back_populates="voucher",
        cascade="all, delete-orphan",
        order_by="StockVoucherLine.id",
    )
    # Hóa đơn/chứng từ gốc scan đính kèm (dòng "Số chứng từ gốc kèm theo" trên mẫu 01-VT/02-VT).
    attachments: Mapped[list[StockVoucherAttachment]] = relationship(
        "StockVoucherAttachment",
        back_populates="voucher",
        cascade="all, delete-orphan",
        order_by="StockVoucherAttachment.id",
    )

    __table_args__ = (
        CheckConstraint("loai IN ('NHAP','XUAT')", name="chk_stock_vouchers_loai"),
    )


class StockVoucherLine(Base):
    """1 dòng phiếu = 1 lần đụng vào MỘT lô.

    Phiếu xuất ăn nhiều lô thì tách thành nhiều dòng phân bổ (10 từ lô 1 + 5 từ lô 2 =
    2 dòng), vì mỗi lô một giá vốn — gộp lại thì không truy được giá đích danh.
    """

    __tablename__ = "stock_voucher_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    voucher_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stock_vouchers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Dòng đề nghị mà dòng phiếu này ứng vào — nền cho chặn "ứng vượt SL duyệt".
    request_line_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stock_request_lines.id"), index=True, nullable=False
    )
    material_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("materials.id"), index=True, nullable=False
    )
    # Phiếu XUẤT: bắt buộc, trỏ vào lô bị trừ. Phiếu NHẬP: null lúc nháp, được gán khi
    # ghi sổ (lúc đó lô mới được sinh ra).
    lot_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("stock_lots.id"), index=True, nullable=True
    )
    so_luong: Mapped[float] = mapped_column(
        Numeric(14, 2), CheckConstraint("so_luong > 0"), nullable=False
    )
    # Chỉ phiếu NHẬP: giá của lô sắp tạo. Phiếu xuất lấy giá từ lô nên để trống.
    don_gia: Mapped[int | None] = mapped_column(
        BigInteger, CheckConstraint("don_gia IS NULL OR don_gia >= 0"), nullable=True
    )
    # Ghi chú riêng cho DÒNG (mặt hàng) trên phiếu — vd tình trạng bao gói, lô hàng lỗi lẻ…
    ghi_chu: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Phiếu NHẬP: VỊ TRÍ cất lô trong kho (kệ/ô) do thủ kho khai lúc lập; ghi sổ chép sang
    # `stock_lots.vi_tri`. Null với phiếu XUẤT (không tạo lô). Thêm qua migration 0115.
    vi_tri: Mapped[str | None] = mapped_column(String(100), nullable=True)

    voucher: Mapped[StockVoucher] = relationship("StockVoucher", back_populates="lines")


class StockVoucherAttachment(Base):
    """Hóa đơn/chứng từ gốc scan đính kèm phiếu nhập/xuất (hóa đơn NCC, biên bản giao nhận…).

    Bytes nằm dưới <backend>/static/kho/<voucher_id>/, phục vụ read-only qua mount /static
    (public — cùng phạm vi ke-toan/avatars/hr); DB chỉ lưu metadata + path (mirror
    payment_voucher_attachments). Cho đính THÊM cả khi phiếu đã `posted` (hóa đơn về sau);
    chỉ chặn `cancelled`.
    """

    __tablename__ = "stock_voucher_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_voucher_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stock_vouchers.id", ondelete="CASCADE"), nullable=False, index=True
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

    voucher: Mapped[StockVoucher] = relationship("StockVoucher", back_populates="attachments")
