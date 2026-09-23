"""AuditLog ORM model.

One row per privilege-changing action (gán phòng, gán vai trò, sửa khuôn quyền,
khóa tài khoản) so the Activity Log screen can show who did what, when.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    # Tab "Nhật ký" của mọi màn danh mục/phiếu hỏi `target = 'loai:id' ORDER BY created_at DESC`
    # (`AuditLogRepository.list_by_target`). Không có index này thì mỗi lần mở drawer là quét cả
    # bảng — mà đây là bảng phình nhanh nhất hệ (mọi lần lưu đều ghi một dòng). Mg `0301`.
    __table_args__ = (
        Index("ix_audit_logs_target_created_at", "target", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True, nullable=False
    )
