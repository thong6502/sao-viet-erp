"""Imposition Type model — imposition/bình bài types master data (kiểu bình bài).

Catalog of imposition schemes (1 mặt, tự trở, trở nhíp, A-B, perfecting, tùy chỉnh)
whose coefficients the pricing engine reads to compute finished-piece count, plate
sets, machine passes and ink passes.

Full spec A–E (feat — Kiểu bình bài):
  A. Thông tin chung  — code (mã ngữ nghĩa), name, group_kind, note, is_active, version
  B. Hệ số tính chính — finished_factor, pass_count, plate_set_factor, ink_pass_factor,
                        sides, allow_rotate, shared_plate_set
  C. Điều kiện áp dụng — technology, applies_to_sides, applicable_product_types /
                        _machine_ids / _paper_size_ids, allow_multi_signature, priority
  D. Diễn giải công thức — HARD-CODE trong pricing_engine (spec cho phép ở MVP, không cột)
  E. Audit / versioning — version, effective_from/to, used_count, created_by/updated_by,
                        created_at/updated_at. Unique = (code, version): sửa 1 kiểu ĐÃ dùng
                        trong báo giá snapshot (used_count>0) tạo BẢN VERSION MỚI thay vì
                        sửa tại chỗ — engine resolve theo code + ngày hiệu lực + version cao nhất.
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
    Text,
    UniqueConstraint,
    false as sa_false,
    true as sa_true,
)
from sqlalchemy.orm import Mapped, mapped_column
from ..db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Nhóm kiểu bình bài (Nhóm kiểu — spec A). one_side/two_side/multi_page/custom.
GROUP_KINDS = ("one_side", "two_side", "multi_page", "custom")
# Áp dụng cho số mặt (spec C) — bộ lọc gợi ý ở màn Tính giá. any = không giới hạn.
APPLIES_TO_SIDES = ("any", "1", "2", "multi")


class ImpositionType(Base):
    __tablename__ = "imposition_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Mã kiểu bình — ngữ nghĩa, do người dùng nhập (ONE_SIDE, TU_TRO, TRO_NHIP, AB…).
    # KHÔNG còn unique một mình: unique là (code, version) để nuôi version-chain (spec E).
    code: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # A. Nhóm kiểu — one_side/two_side/multi_page/custom.
    group_kind: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="custom", default="custom"
    )
    # số mặt in (1 hoặc 2)
    sides: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1", default=1)

    # ---- B. Hệ số tính chính ----
    # Hệ số thành phẩm (quy đổi số con hình học → số con thành phẩm; tự trở = 0.5)
    finished_factor: Mapped[float] = mapped_column(
        Numeric(6, 3), nullable=False, server_default="1.0", default=1.0
    )
    # Số lượt qua máy (nuôi giờ máy — config, KHÔNG suy từ số mặt)
    pass_count: Mapped[float] = mapped_column(
        Numeric(6, 3), nullable=False, server_default="1", default=1
    )
    # Hệ số bộ kẽm (nuôi tiền kẽm; 1 mặt=1, tự trở=1, trở nhíp=2)
    plate_set_factor: Mapped[float] = mapped_column(
        Numeric(6, 3), nullable=False, server_default="1.0", default=1.0
    )
    # Hệ số lượt in màu (nuôi tiền mực; mặc định = số mặt)
    ink_pass_factor: Mapped[float] = mapped_column(
        Numeric(6, 3), nullable=False, server_default="1.0", default=1.0
    )
    # Cho phép xoay bài khi bình
    allow_rotate: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_true(), default=True
    )
    # Có dùng chung bộ kẽm (diễn giải nghiệp vụ; suy được từ plate_set_factor)
    shared_plate_set: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_false(), default=False
    )
    # Mô tả ngắn / diễn giải (textarea)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ---- C. Điều kiện áp dụng (lọc gợi ý ở màn Tính giá) ----
    technology: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="offset", default="offset"
    )
    applies_to_sides: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="any", default="any"
    )
    # list các product_type / machine_id / paper_size_id áp dụng. NULL hoặc [] = tất cả.
    applicable_product_types: Mapped[list | None] = mapped_column(JSON, nullable=True)
    applicable_machine_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    applicable_paper_size_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    allow_multi_signature: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_true(), default=True
    )
    # Thứ tự ưu tiên khi auto-suggest (nhỏ = ưu tiên cao)
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="100", default=100
    )

    # ---- E. Audit / versioning ----
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1", default=1
    )
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Đã dùng trong bao nhiêu báo giá snapshot (khóa sửa-tại-chỗ khi > 0)
    used_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )
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
        UniqueConstraint("code", "version", name="uq_imposition_code_version"),
    )
