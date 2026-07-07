"""Yêu cầu cập nhật hồ sơ (module `nhan_su`) — NV tự đề nghị sửa các field định danh/
pháp lý/ngân hàng (không tự sửa thẳng được), HCNS duyệt thì mới áp vào hồ sơ.

Một bảng: `profile_update_requests`. `changes` là JSON {field: giá trị mới}."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

REQ_PENDING = "pending"
REQ_APPROVED = "approved"
REQ_REJECTED = "rejected"
REQUEST_STATUSES = (REQ_PENDING, REQ_APPROVED, REQ_REJECTED)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProfileUpdateRequest(Base):
    __tablename__ = "profile_update_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # {field: new_value} — các field NV đề nghị đổi (whitelist REQUESTABLE_FIELDS ở service).
    changes: Mapped[dict] = mapped_column(JSON, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        String(12), index=True, nullable=False, default=REQ_PENDING, server_default=REQ_PENDING
    )
    decided_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
