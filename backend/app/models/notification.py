"""Thông báo trong hệ thống (trung tâm thông báo — chuông ở Topbar).

Mỗi bản ghi = 1 thông báo GỬI TỚI MỘT người (`user_id`). Lưu để hiện danh sách ở chuông + đếm
"chưa đọc" (`read_at IS NULL`). Có `link_loai` + `link_id` để bấm 1 thông báo là mở đúng phiếu/yêu
cầu liên quan. Cố tình GENERIC (không cột riêng cho kho) để sau nối thêm module khác.

Bảng MỚI → create_all tự dựng; không cần migration ADD COLUMN.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Notification(Base):
    """1 thông báo gửi tới 1 người nhận. `read_at` NULL = chưa đọc (nuôi số ở chuông)."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Người NHẬN thông báo.
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), index=True, nullable=False
    )
    # Phân loại nghiệp vụ (vd 'kho_moi', 'kho_hoan_tat', 'kho_huy') — FE có thể chọn icon/màu.
    loai: Mapped[str] = mapped_column(String(40), nullable=False)
    tieu_de: Mapped[str] = mapped_column(String(200), nullable=False)
    noi_dung: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Đích điều hướng khi bấm: loại đối tượng ('kho_inbox' = Hộp yêu cầu/thủ kho, 'kho_mine' = màn
    # Yêu cầu/người tạo) + id (request_id). NULL = thông báo thuần, không nhảy đâu.
    link_loai: Mapped[str | None] = mapped_column(String(40), nullable=True)
    link_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Thời điểm người nhận ĐỌC (bấm vào). NULL = chưa đọc ⇒ tính vào badge chuông.
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True, nullable=False
    )
