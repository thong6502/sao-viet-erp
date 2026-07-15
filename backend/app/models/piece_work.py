"""Lương khoán ORM models (module `luong`, nhịp 2).

Bốn bảng:
  - `piece_rates`         — đơn giá khoán theo tổ + đơn vị (m²/bài in/tấn/cuốn/lượt/hộp).
                            Số hóa các bảng "CÔNG KHOÁN" thật.
  - `piece_batches`       — "sổ khoán" 1 tổ / 1 kỳ (year, month, group). Cấu hình tổ:
                            % tổ trưởng, bù lỗ (min đảm bảo), thưởng vượt năng suất.
  - `piece_batch_entries` — dòng sản lượng nhập tay (đơn giá × khối lượng = tiền).
  - `piece_batch_shares`  — chia quỹ về từng thành viên theo hệ số (weight).

Tiền khoán mỗi NV/kỳ → cộng vào cột `khoan` của payroll_lines (engine đọc qua
PieceWorkService.khoan_map). Portable SQLite/Postgres.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# --- Đơn vị tính đơn giá khoán ----------------------------------------------
UNIT_M2 = "m2"          # mét vuông (bồi, cán/phủ)
UNIT_BAI_IN = "bai_in"  # bài in (máy in, theo số màu)
UNIT_TAN = "tan"        # tấn (cắt giấy cuộn)
UNIT_CUON = "cuon"      # cuốn (cắt/bắt thành phẩm)
UNIT_LUOT = "luot"      # lượt (cắt demi)
UNIT_HOP = "hop"        # hộp (gỡ hàng)
UNIT_TO = "to"          # tờ
UNIT_KHAC = "khac"      # khác
PIECE_UNITS = (UNIT_M2, UNIT_BAI_IN, UNIT_TAN, UNIT_CUON, UNIT_LUOT, UNIT_HOP, UNIT_TO, UNIT_KHAC)

# Trạng thái sổ khoán (nhịp Pha 5): draft = đang soạn (sửa được); locked = đã chốt (chỉ sổ đã
# chốt mới chảy vào bảng lương; cấm sửa sản lượng/hệ số/cấu hình cho tới khi mở lại).
BATCH_DRAFT = "draft"
BATCH_LOCKED = "locked"
PIECE_BATCH_STATUSES = (BATCH_DRAFT, BATCH_LOCKED)

_MONEY = Numeric(14, 2)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PieceRate(Base):
    """Đơn giá khoán: 1 công việc của 1 tổ với đơn vị + đơn giá."""

    __tablename__ = "piece_rates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Tổ khoán (vd 'to_boi', 'to_can_phu', 'to_cat', 'may_in_5mau'). Trục gom + tra.
    group_name: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    code: Mapped[str | None] = mapped_column(String(20), nullable=True)  # mã (A–F cho máy in)
    name: Mapped[str] = mapped_column(String(255), nullable=False)       # tên công việc
    # Công đoạn gắn đơn giá (mã cong_doan.ma) — Pha 5b: tra đơn giá theo (tổ + công đoạn) khi ghi phiếu.
    cong_doan: Mapped[str | None] = mapped_column(String(30), index=True, nullable=True)
    unit: Mapped[str] = mapped_column(String(12), nullable=False, default=UNIT_KHAC, server_default=UNIT_KHAC)
    unit_price: Mapped[float] = mapped_column(_MONEY, nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class PieceBatch(Base):
    """Sổ khoán của 1 tổ trong 1 kỳ. UNIQUE(year, month, group_name)."""

    __tablename__ = "piece_batches"
    __table_args__ = (UniqueConstraint("year", "month", "group_name", name="uq_piece_batch_ymg"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    year: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    month: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    group_name: Mapped[str] = mapped_column(String(40), nullable=False)
    # Tổ trưởng (nhận % trước). Logical link, không FK cứng.
    leader_employee_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    leader_pct: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0.05, server_default="0.05")
    # Bù lỗ = mức tối thiểu đảm bảo (quỹ < bù lỗ thì lấy bù lỗ). 0 = không áp.
    min_guarantee: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    # Thưởng vượt năng suất: quỹ vượt `over_target` thì phần vượt × `over_bonus_pct`.
    over_target: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    over_bonus_pct: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0, server_default="0")
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Chốt sổ: draft/locked. Đồng bộ với kỳ lương — chỉ sổ locked mới vào bảng lương.
    status: Mapped[str] = mapped_column(String(8), nullable=False, default=BATCH_DRAFT, server_default=BATCH_DRAFT)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class PieceBatchEntry(Base):
    """Một dòng sản lượng trong sổ khoán: khối lượng × đơn giá = tiền."""

    __tablename__ = "piece_batch_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("piece_batches.id", ondelete="CASCADE"), index=True, nullable=False
    )
    piece_rate_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("piece_rates.id", ondelete="SET NULL"), nullable=True
    )
    work_name: Mapped[str] = mapped_column(String(255), nullable=False)   # snapshot tên
    unit: Mapped[str] = mapped_column(String(12), nullable=False, default=UNIT_KHAC, server_default=UNIT_KHAC)
    unit_price: Mapped[float] = mapped_column(_MONEY, nullable=False)     # snapshot đơn giá
    quantity: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    amount: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Nguồn dòng (Pha 5b): manual = gõ tay; phieu = materialize từ Phiếu sản lượng lúc chốt sổ.
    source: Mapped[str] = mapped_column(String(8), nullable=False, default="manual", server_default="manual")
    production_output_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)  # soft link → production_outputs.id


class PieceBatchShare(Base):
    """Chia quỹ khoán về 1 thành viên theo hệ số (weight); `amount` là tiền tính được."""

    __tablename__ = "piece_batch_shares"
    __table_args__ = (UniqueConstraint("batch_id", "employee_id", name="uq_piece_share_be"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("piece_batches.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    weight: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=1, server_default="1")
    amount: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0, server_default="0")
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
