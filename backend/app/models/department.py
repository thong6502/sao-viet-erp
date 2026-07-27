"""Department ORM model (phòng ban).

One row per organizational department (Kinh doanh, Hành chính nhân sự, …). A
department groups its own Roles; a user belongs to exactly one department.
Portable across SQLite and Postgres.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, false as sa_false
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# Cơ chế lương của phòng (Pha 1 — bộ nguyên tắc lương). Cách một phòng ra mức lương cho
# mọi người trong phòng:
#   cung                 = lương cứng, ấn định tay từng người (khối quản lý/hành chính).
#   bac_tho              = theo bậc thợ (thợ 1/2/3, phụ 1/2) — vd tổ In.
#   tham_nien            = theo thâm niên (<1 / 1–5 / 5–10 / >10 năm) — vd Cắt, Bồi, Cán.
#   tham_nien_gioi_tinh  = theo thâm niên × nam/nữ — vd Dán, Thành phẩm.
SALARY_MECHANISMS = ("cung", "bac_tho", "tham_nien", "tham_nien_gioi_tinh")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    # System-generated unique code (spec-05): "PB" + zero-padded sequence (PB001, PB002, …).
    # Read-only — users never type it; assigned by the repository on create.
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    # Optional free-text description (spec-05).
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Parent department for the org tree (spec-05): self-FK, null = root unit. Children are
    # cascade-deleted with their parent's branch (handled in the service, not the DB).
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("departments.id"), index=True, nullable=True
    )
    # Organizational tier this unit sits at (spec-06 / PBI-4009): FK→unit_levels.id, null =
    # untagged. Drives the head's title label (Trưởng khối / Trưởng phòng / Tổ trưởng).
    level_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("unit_levels.id"), index=True, nullable=True
    )
    # Logical reference to users.id (the trưởng phòng). Kept as a plain column to avoid a
    # users<->departments FK cycle under create_all; the DB-level FK can land with Alembic.
    head_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # --- Bộ nguyên tắc lương của phòng (Pha 1) ---------------------------------------
    # Cơ chế ra mức lương (xem SALARY_MECHANISMS). Mặc định 'cung' = ấn định tay.
    salary_mechanism: Mapped[str] = mapped_column(
        String(24), nullable=False, default="cung", server_default="cung"
    )
    # % lương thử việc của phòng (công ty dùng 0.80; Đ26 BLLĐ tối thiểu 0.85).
    probation_ratio: Mapped[float] = mapped_column(
        Numeric(5, 4), nullable=False, default=0.80, server_default="0.80"
    )
    # Phòng sản xuất có lương khoán theo sản lượng (nối engine khoán ở pha sau).
    has_piece_work: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Đánh dấu phòng ban thuộc khối SẢN XUẤT (nền phân tổ cho Kế hoạch SX). Tick ở 1 nút cha ⇒ cả
    # cây con (theo parent_id) coi như sản xuất; phân hệ Sản xuất liệt kê đúng subtree này. "Effective
    # sản xuất" = cột này true HOẶC có tổ tiên true (tính ở service, KHÔNG cascade lưu).
    la_san_xuat: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_false(), default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
