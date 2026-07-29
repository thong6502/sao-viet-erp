"""Lô kho + ngưỡng tồn — docs/spec-kho-de-nghi.md §6–§7.

**Mỗi lần nhập = MỘT lô riêng, id riêng, giá riêng.** Không gộp lô kể cả trùng mã hàng,
trùng giá — gộp là mất tính đích danh, mà BRD §3.19 chốt phương pháp giá xuất là ĐÍCH
DANH theo lô nhập.

Hệ quả quan trọng: **tồn của một mã hàng = tổng `sl_con_lai` của các lô.** Không có cột
"tồn" nào lưu rời, nên tồn không bao giờ lệch với lịch sử nhập/xuất.

Bảng MỚI → `create_all` tự dựng, không cần migration.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    true as sa_true,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# Trạng thái lô (rút gọn từ BRD §3.15). Chỉ `available` mới tính vào TỒN KHẢ DỤNG —
# hàng chờ KCS / hàng lỗi vẫn nằm trong kho (tồn thực tế) nhưng không được xuất.
LOT_AVAILABLE = "available"
LOT_HOLD = "hold"            # giữ chỗ cho đơn/LSX
LOT_QC_WAIT = "qc_wait"      # chờ KCS
LOT_DEFECT = "defect"        # hàng lỗi
LOT_EMPTY = "empty"          # đã xuất hết
LOT_STATUSES = (LOT_AVAILABLE, LOT_HOLD, LOT_QC_WAIT, LOT_DEFECT, LOT_EMPTY)
# Chỉ những trạng thái này được cộng vào tồn khả dụng / được chọn khi xuất.
LOT_ISSUABLE = (LOT_AVAILABLE,)

# Trạng thái tồn so với ngưỡng (spec §7). Dùng chung cho 3 chỗ: cảnh báo đẩy, đèn tín
# hiệu ở màn đề nghị, dashboard kho — định nghĩa MỘT lần ở đây.
STOCK_OVER = "du_ton"        # 🔵 > ngưỡng tối đa
STOCK_OK = "du"              # 🟢 đủ
STOCK_CRITICAL = "can_mua"   # 🟠 ≤ ngưỡng tồn
STOCK_OUT = "het"            # 🔴 = 0
# Bỏ mức "cận tồn/sắp hết" (2026-07-29) — chỉ còn 4 mức.
STOCK_LEVELS = (STOCK_OVER, STOCK_OK, STOCK_CRITICAL, STOCK_OUT)
# Hai mức này kích hoạt đẩy nhắc realtime cho người có quyền đề nghị (spec §8).
STOCK_ALERT_LEVELS = (STOCK_CRITICAL, STOCK_OUT)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StockLot(Base):
    """1 dòng = 1 lô nhập kho, mang GIÁ riêng của lần nhập đó.

    Ví dụ: SP A nhập đợt 1 giá 100k → lô 1; đợt 2 giá 200k → lô 2. Xuất 15 cái =
    10 từ lô 1 + 5 từ lô 2 → giá vốn 10×100k + 5×200k.
    """

    __tablename__ = "stock_lots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Mã lô người dùng đọc được: LOT-<mã hàng>-<yymmdd>-<seq>.
    ma_lo: Mapped[str] = mapped_column(String(60), unique=True, index=True, nullable=False)
    material_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("materials.id"), index=True, nullable=False
    )
    # Phiếu nhập sinh ra lô. Nullable vì tồn đầu kỳ (giai đoạn sau) không có phiếu.
    voucher_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("stock_vouchers.id"), index=True, nullable=True
    )
    kho_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("kho_hang.id"), index=True, nullable=False
    )
    vi_tri: Mapped[str | None] = mapped_column(String(100), nullable=True)

    ngay_nhap: Mapped[date] = mapped_column(Date, nullable=False)
    ncc: Mapped[str | None] = mapped_column(String(150), nullable=True)
    # Giá vốn của RIÊNG lô này (VND/đvt). Chỉ vai có `can_view_cost` được xem — router
    # ẩn trường này, kể cả trên bản in (spec §9.1).
    don_gia_nhap: Mapped[int] = mapped_column(
        BigInteger, CheckConstraint("don_gia_nhap >= 0"),
        nullable=False, server_default="0", default=0,
    )
    sl_ban_dau: Mapped[float] = mapped_column(
        Numeric(14, 2), CheckConstraint("sl_ban_dau > 0"), nullable=False
    )
    sl_con_lai: Mapped[float] = mapped_column(
        Numeric(14, 2), CheckConstraint("sl_con_lai >= 0"), nullable=False
    )
    # Hạn sử dụng / date in bao bì — nền cho gợi ý FEFO khi xuất.
    hsd: Mapped[date | None] = mapped_column(Date, nullable=True)
    trang_thai: Mapped[str] = mapped_column(
        String(16), index=True, nullable=False,
        server_default=LOT_AVAILABLE, default=LOT_AVAILABLE,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    __table_args__ = (
        CheckConstraint("sl_con_lai <= sl_ban_dau", name="chk_stock_lots_con_lai"),
    )


class StockThreshold(Base):
    """Ngưỡng tồn theo cặp (mã hàng × kho) — spec §7.

    So sánh chạy trên TỒN KHẢ DỤNG (chỉ lô `available`), không phải tồn thực tế: hàng
    chờ KCS / hàng lỗi nằm trong kho nhưng không dùng được nên không được tính (BRD §1.5).
    """

    __tablename__ = "stock_thresholds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    material_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("materials.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kho_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("kho_hang.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Dưới mức này = 🟠 phải mua ngay.
    nguong_ton: Mapped[float] = mapped_column(
        Numeric(14, 2), CheckConstraint("nguong_ton >= 0"), nullable=False
    )
    # ĐÃ BỎ mức "cận tồn/sắp hết" (2026-07-29) — cột giữ lại (luôn NULL) để tránh migration phá DB;
    # `stock_level` không còn dùng. FE không khai nữa; endpoint vẫn nhận optional cho tương thích.
    nguong_can_ton: Mapped[float | None] = mapped_column(
        Numeric(14, 2), CheckConstraint("nguong_can_ton >= 0"), nullable=True
    )
    # Trần 🔵 — cảnh báo mua dư, hàng dễ quá date.
    nguong_toi_da: Mapped[float | None] = mapped_column(
        Numeric(14, 2), CheckConstraint("nguong_toi_da >= 0"), nullable=True
    )
    canh_bao: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_true(), default=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("material_id", "kho_id", name="uq_stock_thresholds_material_kho"),
    )
