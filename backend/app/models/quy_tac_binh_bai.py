"""Quy tắc bình bài (Imposition Rule) — master data, spec `docs/spec-quy-tac-binh-bai.md` §3.

3 bảng:
  - quy_tac_binh_bai         : HEADER (danh tính), KHÔNG chứa cấu hình bình bài.
  - quy_tac_binh_bai_version : VERSION (toàn bộ cấu hình + version-chain is_current).
  - folding_scheme           : bảng phụ (sơ đồ gấp tay sách) cho mode signature.

Cấu hình sống ở VERSION; sửa cấu hình = đẻ version mới (không sửa đè) → báo giá cũ ghim
đúng version_no vẫn tái lập số cũ (§4/§12).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false as sa_false,
    true as sa_true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base

# Enum values (khớp engine imposition_engine)
LAYOUT_MODES = ("step_repeat", "signature", "nesting", "repeat_around")
TRANG_THAI = ("active", "inactive")
GRAIN_CONSTRAINTS = ("none", "canh_dai", "song_song_gay", "theo_song")
WORK_STYLES = ("sheetwise", "work_turn")
NEST_METHODS = ("grid", "true_shape")
SCHEME_CODES = ("F4", "F8", "F16", "F32")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QuyTacBinhBai(Base):
    """HEADER — danh tính quy tắc (§3.1). Không chứa cấu hình bình bài."""

    __tablename__ = "quy_tac_binh_bai"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Mã nghiệp vụ — viết hoa, unique, KHÔNG đổi sau tạo.
    ma: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    ten: Mapped[str] = mapped_column(String(150), nullable=False)
    mo_ta: Mapped[str | None] = mapped_column(Text, nullable=True)
    # active | inactive — inactive = ẩn khi gán; không xoá nếu đang tham chiếu.
    trang_thai: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="active", default="active"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    versions: Mapped[list["QuyTacBinhBaiVersion"]] = relationship(
        back_populates="rule", cascade="all, delete-orphan"
    )


class QuyTacBinhBaiVersion(Base):
    """VERSION — toàn bộ cấu hình bình bài (§3.2). unique(rule_id, version_no)."""

    __tablename__ = "quy_tac_binh_bai_version"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("quy_tac_binh_bai.id", ondelete="CASCADE"), index=True, nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    # Đúng 1 dòng is_current=true mỗi rule (enforce ở service).
    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_true(), default=True
    )
    ghi_chu_version: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # --- Công tắc chính ---
    layout_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="step_repeat", default="step_repeat"
    )

    # --- Hình học chung (mọi mode) ---
    side_margin_mm: Mapped[float] = mapped_column(Numeric(7, 2), nullable=False, server_default="5", default=5)
    tail_colorbar_mm: Mapped[float] = mapped_column(Numeric(7, 2), nullable=False, server_default="8", default=8)
    gutter_mm: Mapped[float] = mapped_column(Numeric(7, 2), nullable=False, server_default="4", default=4)
    allow_rotate: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_true(), default=True)
    grain_constraint: Mapped[str] = mapped_column(String(20), nullable=False, server_default="none", default="none")
    bleed_default_mm: Mapped[float] = mapped_column(Numeric(7, 2), nullable=False, server_default="3", default=3)

    # --- A. step_repeat ---
    allow_gang: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_false(), default=False)
    min_gutter_mm: Mapped[float] = mapped_column(Numeric(7, 2), nullable=False, server_default="4", default=4)

    # --- B. signature --- (pages_per_sig/lanes NULL = auto)
    pages_per_sig: Mapped[int | None] = mapped_column(Integer, nullable=True)
    work_style: Mapped[str] = mapped_column(String(16), nullable=False, server_default="sheetwise", default="sheetwise")

    # --- C. nesting ---
    nest_method: Mapped[str] = mapped_column(String(16), nullable=False, server_default="grid", default="grid")
    matrix_allowance_mm: Mapped[float] = mapped_column(Numeric(7, 2), nullable=False, server_default="5", default=5)

    # --- D. repeat_around ---
    lanes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gap_around_mm: Mapped[float] = mapped_column(Numeric(7, 2), nullable=False, server_default="3", default=3)

    # --- Guardrails ---
    min_pages: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_pages: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_spine_mm: Mapped[float | None] = mapped_column(Numeric(7, 2), nullable=True)
    warn_on_grain_violation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_true(), default=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    rule: Mapped["QuyTacBinhBai"] = relationship(back_populates="versions")

    __table_args__ = (
        UniqueConstraint("rule_id", "version_no", name="uq_qtbb_rule_version"),
    )


class FoldingScheme(Base):
    """Sơ đồ gấp tay sách (§3.3) — cấp dữ liệu cho preview signature."""

    __tablename__ = "folding_scheme"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scheme_code: Mapped[str] = mapped_column(String(8), nullable=False)  # F4|F8|F16|F32
    folds: Mapped[int] = mapped_column(Integer, nullable=False)
    # {page_no: [row,col] hoặc index ô} mỗi mặt; {page_no: 0|180} góc xoay.
    page_position_map: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    rotation_map: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    work_style: Mapped[str] = mapped_column(String(16), nullable=False, server_default="sheetwise", default="sheetwise")

    __table_args__ = (
        UniqueConstraint("scheme_code", "work_style", name="uq_folding_scheme_code_style"),
    )
