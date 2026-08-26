"""Lịch sử giá trị công thức lượng/sản lượng — mục 3+7 "Bảng định mức".

Vì sao có bảng riêng: `audit_logs` (`nhat_ky_danh_muc.ghi_sua`) đã ghi MỌI thay đổi của mọi danh
mục, nhưng gộp thành một dòng chữ "Công thức tính lượng A → B" trong `detail` — đọc được nhưng
không TRA LẠI được (không lọc theo trường, không lấy đúng giá trị cũ để hiện cạnh ô đang sửa).
Bảng này lưu THÊM, có cấu trúc, CHỈ cho các trường công thức (`cong_thuc_luong`,
`cong_thuc_san_luong`) — không thay `audit_logs`, không đổi hành vi nhật ký hiện có.

`bang`/`row_id` phẳng (không FK riêng từng bảng) — đúng quy ước `AuditLog.target`, dùng chung cho
cả 5 danh mục (giấy · vật tư khác · máy thiết bị · công đoạn · đầu việc khoán).

Bảng mới → `create_all` tự tạo, KHÔNG migration (như `xep_lich_van_de` / `machine_unavailable_periods`).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CongThucLichSu(Base):
    """Một lần đổi giá trị công thức — 1 dòng / 1 trường / 1 lần lưu thực sự đổi."""

    __tablename__ = "cong_thuc_lich_su"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bang: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    row_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    truong: Mapped[str] = mapped_column(String(40), nullable=False)
    gia_tri_cu: Mapped[str | None] = mapped_column(Text, nullable=True)
    gia_tri_moi: Mapped[str | None] = mapped_column(Text, nullable=True)
    sua_boi: Mapped[int | None] = mapped_column(Integer, nullable=True)  # soft → users.id
    sua_luc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
