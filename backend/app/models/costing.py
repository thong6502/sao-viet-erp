"""Tính giá (Costing / giá thành nội bộ) ORM models — spec-08-tinh-gia.

A **costing** (phương án tính giá) is an INTERNAL cost estimate for a product + quantity:
estimator chọn phương án giấy, nhập số con/khổ, engine bù hao ngược chuỗi ra số tờ / bản
kẽm / công in / gia công → **giá vốn** tách theo cost pool, để **Báo giá đọc lại** (§43
L1217–1219). This screen reads **live versioned** đơn giá/định mức — it does NOT snapshot
(snapshot P0 copy-on-write happens at order-close, §34 L877-878).

Ranh giới cứng (out-of-scope here — spec-08):
  - **bậc SL / lãi / chiết khấu / giá bán** → Báo giá (§11 L333, §41 L1132);
  - **snapshot giá + định mức** → chốt Đơn hàng (§34 L877-878); Báo giá lưu versioned-quote;
  - **PrintForm / ghép bài / share phân bổ** → lớp SX, ẩn khỏi Sale (§40 D2); `share`=1.0
    is an engine background default, NOT a stored estimator field here.

`product_id` is read via **SEAM-11** (ProductRead, module `san_pham`) for cấu phần khổ/
màu/số trang; because san_pham lives in the SAME app it MAY carry a FK→products.id, but the
domain read still goes through the SEAM-11 port (no cross-component coupling on the specs).
`sheet_paper_master_id` is **SEAM-07** (PaperCost, module `dm_giay_vat_tu`/`kho`) — a plain
nullable Integer (no FK) until that catalog exists; the paper price/lô/ownership are looked
up via the raising port stub, never fabricated. Portable across SQLite and Postgres.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base

# --- Enums (domain vocab; validated in the service, stored as plain strings) ----

# Costing lifecycle: draft (đang lập) → ready (đủ input để Báo giá đọc). No snapshot.
STATUS_DRAFT = "draft"
STATUS_READY = "ready"
COSTING_STATUSES = (STATUS_DRAFT, STATUS_READY)

# execution_mode per công đoạn gia công (§14 L389–390, §23 L537): nội bộ khoán / thuê NCC.
EXEC_INTERNAL = "internal"
EXEC_OUTSOURCED = "outsourced"
EXECUTION_MODES = (EXEC_INTERNAL, EXEC_OUTSOURCED)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Costing(Base):
    __tablename__ = "costings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # System-generated sequential code (CG001, CG002…). Unique + read-only; never entered
    # by the user (spec-08 §41; SP###/KH###/PB### pattern).
    code: Mapped[str] = mapped_column(
        String(20), unique=True, index=True, nullable=False
    )
    # SEAM-11: the product this costing is for. FK→products.id (san_pham is same-module);
    # the domain cấu phần read still goes through the ProductRead port. Nullable so a draft
    # may be started before the product is picked (Planner: draft-friendly).
    product_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="SET NULL"), index=True, nullable=True
    )
    # Số lượng cần giao (bắt buộc > 0 — validated in the service). KHÔNG bậc SL (A1).
    qty_final: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # draft | ready (see COSTING_STATUSES). ready = đủ input để Báo giá đọc.
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=STATUS_DRAFT)
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    paper_options: Mapped[list["CostingPaperOption"]] = relationship(
        "CostingPaperOption",
        back_populates="costing",
        cascade="all, delete-orphan",
        order_by="CostingPaperOption.id",
    )
    operations: Mapped[list["CostingOperation"]] = relationship(
        "CostingOperation",
        back_populates="costing",
        cascade="all, delete-orphan",
        order_by="CostingOperation.sequence",
    )


class CostingPaperOption(Base):
    __tablename__ = "costing_paper_options"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    costing_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("costings.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # SEAM-07: FK-nullable to PaperMaster (Danh mục Giấy · dm_giay_vat_tu). Plain nullable
    # Integer (no FK) until that catalog is built — the giá per-ram/kg + lot_type + ownership
    # are looked up via the raising port stub, never a fabricated paper.
    sheet_paper_master_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Khổ tờ in (sheet size, cm). Numeric so mm/cm decimals survive SQLite + Postgres.
    sheet_w: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    sheet_h: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    # Số con trên khổ — NHẬP TAY (>0), with a parallel geometry suggestion (§31a). The
    # value the estimator typed is authoritative; the suggestion is only a warning.
    pieces_per_sheet: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Cờ ràng buộc thớ: khi true, gợi ý loại nhánh xoay khỏi công thức (§31 L782).
    grain_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Phương án giấy được chọn để "dùng" (so sánh nhiều phương án — F7). Default False.
    selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    costing: Mapped["Costing"] = relationship("Costing", back_populates="paper_options")


class CostingOperation(Base):
    __tablename__ = "costing_operations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    costing_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("costings.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Display / process order.
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Tên công đoạn gia công (cán màng, bế, đóng cuốn…). Free text at P0.
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # internal (khoán nội bộ — SEAM-08) | outsourced (NCC — SEAM-12). Đơn giá pull, not
    # entered here; cost pool "Gia công" phân đôi nguồn theo mode.
    execution_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default=EXEC_INTERNAL
    )

    costing: Mapped["Costing"] = relationship("Costing", back_populates="operations")
