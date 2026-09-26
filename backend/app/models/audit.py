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
    # Hai index thêm 25/09/2026 (mg `0336`) cho màn Nhật ký sau khi lọc chuyển về MÁY CHỦ: lọc
    # theo hành động và theo người thao tác, cả hai luôn kèm sắp xếp theo thời gian.
    __table_args__ = (
        Index("ix_audit_logs_target_created_at", "target", "created_at"),
        Index("ix_audit_logs_action_created_at", "action", "created_at"),
        Index("ix_audit_logs_actor_created_at", "actor_user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    #: Tên người thao tác CHỤP TẠI LÚC GHI. Trước 25/09/2026 màn Nhật ký tra tên từ `users` lúc
    #: ĐỌC, nên đổi tên một người là mọi dòng cũ của họ đổi theo — nhật ký nói sai về quá khứ.
    #: Đọc thì ưu tiên cột này; rỗng (dòng cũ) mới tra ngược sang `users`.
    actor_name_luc_do: Mapped[str] = mapped_column(String(120), nullable=False, default="",
                                                   server_default="")
    #: Ai, TỪ ĐÂU. Điền tự động từ request đang chạy (`app/audit_context.py`) nên mọi đường ghi
    #: audit đều có, không phải sửa hơn 200 chỗ gọi. Rỗng = việc của máy (seeder, tác vụ nền).
    ip: Mapped[str] = mapped_column(String(45), nullable=False, default="", server_default="")
    user_agent: Mapped[str] = mapped_column(String(255), nullable=False, default="",
                                            server_default="")
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True, nullable=False
    )
