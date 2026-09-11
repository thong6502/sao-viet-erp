"""Xếp lịch 3 — mốc BẮT ĐẦU của một LỆNH SẢN XUẤT.

Một dòng = một lệnh. Bảng này lưu ĐÚNG MỘT quyết định của người: `bat_dau_at`. Ngày kết thúc của
lệnh, mốc từng công đoạn và các đoạn máy chạy trong ca đều TÍNH LÚC ĐỌC ở `services/xep_lich_3` —
bám precedent `lsx_service.thoi_luong_buoc` / `bai_ghep_service.tinh_so_to`.

KHÔNG lưu `ket_thuc_at`: nó phụ thuộc ca làm việc, ngày nghỉ, tốc độ máy và số lượng — bốn thứ đổi
được sau lưng. Lưu ra là có một con số trông-như-thật nhưng đã lệch cấu hình, mà không ai đi kiểm.

KHÁC `xep_lich_cong_doan` (module 2): bảng kia một dòng một CÔNG ĐOẠN và có gán máy/tổ/ca. Bảng
này không gán gì — máy đã nằm sẵn trên `lsx_cong_doan.may_id` từ lúc tạo lệnh, nên bàn xếp lịch
cấp lệnh không cần ai gán lại.

RBAC MODULE = "xep_lich_3". `lsx_id` là FK THẬT + `ondelete=CASCADE` (lớp chặn cuối ở DB) và
UNIQUE: màn ở cấp LỆNH nên hai mốc cho một lệnh là mâu thuẫn chứ không phải dữ liệu. Bảng mới →
`create_all` tự tạo trên DB trắng; DB live nhận qua migration `0291`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class XepLichLenh(Base):
    """Mốc bắt đầu do người điều độ đặt cho MỘT lệnh sản xuất."""

    __tablename__ = "xep_lich_lenh"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lsx_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lsx.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    # Thứ DUY NHẤT người quyết. Wall-clock naive ("giờ nhà máy") — ghi bằng `_aware`, đọc `_naive`.
    bat_dau_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)  # soft → users.id
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    # Chốt chống ghi đè khi hai người cùng kéo một thanh (`expected_updated_at` ở API → 409).
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
