"""Loại sản phẩm (Product template) — TẦNG 1 master, spec `docs/spec-san-pham.md` §2.

Template tái dùng (name card, sách, hộp…): GÁN quy tắc bình bài (`imposition_rule_id`) +
routing template mặc định + VAT. KHÔNG giữ cách xếp (→ Bình bài), không giữ khổ máy (→ Máy),
không tự tính tiền (→ Engine). TẦNG 2 `jobspec` (per báo giá) + `component` = Phase D (cùng
engine tính giá).

Module MỚI (strangler) — song song `product_type_catalog.py` cũ. Chưa wired. `imposition_rule_id`
= soft int → `quy_tac_binh_bai.id`; `routing_template` = JSON list `cong_doan.id`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, Integer, JSON, String, Text,
    false as sa_false, true as sa_true,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

STRUCTURAL_TYPE = ("flat", "multipage", "box", "label")
BOX_SUB_TYPE = ("folding_carton", "corrugated", "rigid")
COVER_TYPE = ("tu_bia", "bia_roi")               # tự bìa dùng giấy ruột / bìa rời cần giấy bìa
BINDING = ("ghim", "keo", "khau")
STOCK_CLASS = ("couche", "ford", "ivory", "duplex", "kraft")

# §5.1 ma trận tương thích structural_type ↔ layout_mode (engine kiểm khi gán rule).
STRUCT_LAYOUT_MATRIX = {
    "flat": ("step_repeat", "nesting"),
    "multipage": ("signature",),
    "box": ("nesting", "step_repeat"),
    "label": ("step_repeat",),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LoaiSanPham(Base):
    __tablename__ = "loai_san_pham"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ma: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    ten: Mapped[str] = mapped_column(String(150), nullable=False)
    structural_type: Mapped[str] = mapped_column(String(12), index=True, nullable=False)
    box_sub_type: Mapped[str | None] = mapped_column(String(16), nullable=True)  # khi box

    # Gán bình bài (soft int → quy_tac_binh_bai.id) — §2 bắt buộc.
    imposition_rule_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)

    has_cover: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_false(), default=False)
    cover_type: Mapped[str | None] = mapped_column(String(12), nullable=True)   # khi has_cover
    default_binding: Mapped[str | None] = mapped_column(String(8), nullable=True)
    default_stock_class: Mapped[str | None] = mapped_column(String(12), nullable=True)

    # routing template mặc định — list cong_doan.id (soft).
    routing_template: Mapped[list | None] = mapped_column(JSON, nullable=True)

    ghi_chu: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_true(), default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
