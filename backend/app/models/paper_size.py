"""Paper Size model — standard paper sizes master data (khổ giấy tiêu chuẩn).

Catalog of standard buy sizes (khổ giấy mua), print-sheet sizes (khổ tờ in) and cut
sizes (khổ cắt) used across estimating/costing. Serves three jobs (spec):
  1. chọn khổ tờ in trên màn Tính giá,
  2. tính số con hình học trên tờ,
  3. quy đổi tiền giấy theo tờ / ram / kg / m².

Full spec A–E:
  A. Thông tin chung  — code, name, size_group, loại khổ (3 boolean), note, is_active
  B. Kích thước       — width_cm, height_cm, area_m2 (DERIVED), allow_rotation
  C. Áp dụng cho máy  — compatible_machine_ids (JSON), default_machine_id
  D. Quan hệ khổ cắt  — parent_size_id, cut_count, cut_waste_rate
  E. Audit / versioning — version, effective_from/to, used_count, created_by/updated_by.
     Unique = (code, version): sửa KÍCH THƯỚC một khổ ĐÃ dùng (used_count>0) tạo BẢN
     VERSION MỚI thay vì sửa tại chỗ — resolve theo code + ngày hiệu lực + version cao nhất
     (mirror `imposition_types`).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    UniqueConstraint,
    false as sa_false,
    true as sa_true,
)
from sqlalchemy.orm import Mapped, mapped_column
from ..db import Base

# --- Loại khổ (summary code, DERIVED from the 3 booleans; kept for back-compat & filter) ---
SIZE_TYPE_BUY = "mua"      # chỉ khổ giấy mua
SIZE_TYPE_PRINT = "in"     # chỉ khổ tờ in
SIZE_TYPE_BOTH = "ca_hai"  # vừa mua vừa tờ in
SIZE_TYPE_CUT = "cat"      # khổ cắt
SIZE_TYPE_OTHER = "khac"
SIZE_TYPES = (SIZE_TYPE_BUY, SIZE_TYPE_PRINT, SIZE_TYPE_BOTH, SIZE_TYPE_CUT, SIZE_TYPE_OTHER)

# Nhóm khổ (spec A). Khổ công nghiệp / khổ A / khổ cắt / tùy chỉnh.
SIZE_GROUPS = ("cong_nghiep", "kho_a", "kho_cat", "custom")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def summarize_size_type(is_purchase: bool, is_print: bool, is_cut: bool) -> str:
    """Derive the summary `size_type` code from the 3 loại-khổ booleans."""
    if is_cut:
        return SIZE_TYPE_CUT
    if is_purchase and is_print:
        return SIZE_TYPE_BOTH
    if is_purchase:
        return SIZE_TYPE_BUY
    if is_print:
        return SIZE_TYPE_PRINT
    return SIZE_TYPE_OTHER


class PaperSize(Base):
    __tablename__ = "paper_sizes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Mã khổ — cho gõ tay (A3, K79x109); fallback auto KG### khi bỏ trống. KHÔNG còn unique
    # một mình: unique là (code, version) để nuôi version-chain (spec E).
    code: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # ---- A. Thông tin chung ----
    # Nhóm khổ — cong_nghiep / kho_a / kho_cat / custom.
    size_group: Mapped[str] = mapped_column(
        String(20), index=True, nullable=False, server_default="custom", default="custom"
    )
    # Loại khổ = 3 boolean độc lập (1 khổ có thể vừa mua vừa tờ in).
    is_purchase_size: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_false(), default=False
    )
    is_print_sheet_size: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_true(), default=True
    )
    is_cut_size: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_false(), default=False
    )
    # Mã tóm tắt loại khổ (mua/in/ca_hai/cat) — derived, giữ để lọc & back-compat.
    size_type: Mapped[str] = mapped_column(
        String(16), index=True, nullable=False, server_default="in"
    )
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ---- B. Kích thước ----
    width_cm: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    height_cm: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    # area_m2 là DERIVED (property bên dưới) — không lưu cột, khỏi validate lệch.
    # Cho phép xoay chiều khi tính số con hình học.
    allow_rotation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_true(), default=True
    )

    # ---- C. Áp dụng cho máy ----
    # list machine id chạy được khổ này. NULL hoặc [] = mọi máy.
    compatible_machine_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Là khổ mặc định cho máy nào (gợi ý ở Tính giá). NULL = không.
    default_machine_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ---- D. Quan hệ khổ cắt ----
    # Khổ cha (nếu đây là khổ cắt ra từ khổ lớn). Plain Integer (mirror sheet_paper_master_id).
    parent_size_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    cut_count: Mapped[int | None] = mapped_column(Integer, nullable=True)  # số tờ con tạo ra
    cut_waste_rate: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)  # % hao cắt

    # ---- E. Audit / versioning ----
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1", default=1)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Đã dùng trong bao nhiêu phiếu/snapshot (khóa sửa kích thước tại chỗ khi > 0)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_true(), default=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("code", "version", name="uq_paper_size_code_version"),
    )

    @property
    def area_m2(self) -> float:
        """Diện tích m² — tính động từ rộng × cao (cm). Không lưu cột."""
        try:
            return round(float(self.width_cm) * float(self.height_cm) / 10000.0, 4)
        except (TypeError, ValueError):
            return 0.0
