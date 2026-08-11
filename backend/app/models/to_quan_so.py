"""Quân số TỔ theo NGÀY — nền cho quỹ giờ-người ở bàn xếp lịch (mục I).

Vì sao cần bảng này khi đã có `employees` + `leaves`: quân số TỰ TÍNH (nhân sự gắn đúng tổ lá, trừ
đơn phép đã duyệt) đúng cho ngày bình thường, nhưng sai đúng những hôm cần chính xác nhất — mượn
3 người tổ Bế sang phụ tổ Dán, hai người ốm báo miệng buổi sáng. Người tổ trưởng biết con số thật;
chỗ này là nơi họ gõ đè.

**KHÔNG lưu số tự tính vào đây.** Không có dòng gõ đè ⇒ engine tự tính lại mỗi lần đọc. Lưu cả hai
là đẻ ra hai nguồn sự thật, rồi cái ảnh chụp cũ đứng im khi nhân sự đổi tổ.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ToQuanSoNgay(Base):
    """Số người CÓ MẶT của một tổ trong một ngày, do người dùng gõ đè.

    Bảng MỚI → `create_all` tự dựng (migration chỉ để ALTER bảng cũ). Bám precedent
    `cong_doan_cho_ky_thuat`: bảng con nhỏ, khoá cặp, soft-ref sang danh mục.
    """

    __tablename__ = "to_quan_so_ngay"
    __table_args__ = (
        UniqueConstraint("department_id", "ngay", name="uq_to_quan_so_ngay"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Soft-ref `departments.id` — phòng ban có vòng đời riêng (đổi cây, đổi cờ sản xuất); service
    # kiểm id hợp lệ. FK cứng sẽ chặn xoá phòng vì một dòng quân số của ngày nào đó năm ngoái.
    department_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    ngay: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    #: Số người CÓ MẶT. Cho phép 0 (cả tổ nghỉ) — 0 khác với "chưa gõ đè", cái sau là KHÔNG có dòng.
    so_nguoi: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Vì sao lệch số tự tính. Bắt buộc ở service: một con số đè lên dữ liệu nhân sự mà không có lý
    #: do thì tháng sau không ai giải thích nổi vì sao hôm đó lịch tính ra như vậy.
    ly_do: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    nguoi_sua_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
