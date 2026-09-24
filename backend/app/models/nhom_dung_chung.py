"""Nhóm DÙNG CHUNG dữ liệu — khối Kinh doanh.

Hai người cùng một nhóm thì, ở BỐN màn `tinh_gia_thanh` · `bao_gia` · `don_hang_ban` ·
`khach_hang`, phạm vi "Của tôi" được hiểu rộng ra: của tôi + của người cùng nhóm. Nhóm chỉ
MỞ RỘNG DỮ LIỆU, KHÔNG nâng quyền — mọi ô quyền vẫn tính theo vai của người đang thao tác.

Vì sao không dùng phạm vi "Cả phòng": phòng Kinh doanh có cả chục người, còn nhu cầu là ĐÚNG
hai người làm chung một mớ việc. Vì sao không thêm người vào từng phiếu: phiếu tính giá → báo
giá → đơn hàng là ba chặng, thêm tay ở cả ba là bắt làm đi làm lại.

CỐ Ý không gắn nhóm vào phòng ban: hai người khác phòng vẫn gộp chung được. Cũng CỐ Ý không
cho chọn màn lúc tạo nhóm — bốn màn là CỨNG. Áp cho mọi màn thì A thấy luôn phiếu lương và hồ
sơ của B, vì mấy màn đó cũng dùng "Của tôi" để nói "chỉ mình tôi". Khối khác cần thì đẻ loại
nhóm riêng, không nong cái này ra.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class NhomDungChung(Base):
    __tablename__ = "nhom_dung_chung"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ten: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class NhomDungChungThanhVien(Base):
    """Một người trong một nhóm. Một người ở được NHIỀU nhóm (tập dùng chung = hợp các nhóm)."""

    __tablename__ = "nhom_dung_chung_thanh_vien"
    __table_args__ = (
        UniqueConstraint("nhom_id", "user_id", name="uq_nhom_dung_chung_thanh_vien"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nhom_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("nhom_dung_chung.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    added_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
