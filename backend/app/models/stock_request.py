"""Phiếu ĐỀ NGHỊ nhập/xuất kho — bước đứng TRƯỚC phiếu kho (BRD sơ đồ luồng).

Ai cần hàng lập đề nghị (SL đề nghị) → quản lý DUYỆT → thủ kho căn cứ đề nghị đã duyệt
để LẬP PHIẾU nhập/xuất thật (StockVoucher, ref_type='stock_request'). Nhánh này SONG SONG
với việc lập phiếu trực tiếp — không bắt buộc. Bảng mới → create_all tự dựng.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StockRequest(Base):
    """Header đề nghị kho. request_type: 'nhap' | 'xuat'."""

    __tablename__ = "stock_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    request_type: Mapped[str] = mapped_column(String(8), nullable=False, index=True)  # nhap/xuat
    # Loại phiếu cụ thể mong muốn (NK-GK / XK-SX / …) — giữ đủ case như phiếu kho. Null = chưa chọn.
    voucher_type_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("wh_voucher_types.id"), nullable=True
    )
    warehouse_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("warehouses.id"), index=True, nullable=False
    )
    # Đối tượng gợi ý (NCC cho nhập / bộ phận-tổ nhận cho xuất) — text tự do như phiếu kho P1.
    partner_ref: Mapped[str | None] = mapped_column(String(150), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # draft(Nháp) / pending(Chờ duyệt) / approved(Đã duyệt) / rejected(Từ chối) /
    # fulfilled(Đã lập phiếu) / cancelled(Đã hủy)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", index=True)
    requested_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    approved_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # Phiếu kho đã lập từ đề nghị này (khi status='fulfilled'). Truy vết 2 chiều với StockVoucher.
    voucher_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("stock_vouchers.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    lines: Mapped[list["StockRequestLine"]] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )


class StockRequestLine(Base):
    """Dòng đề nghị — vật tư + SL đề nghị (SL thực nhận điền ở bước lập phiếu)."""

    __tablename__ = "stock_request_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stock_requests.id", ondelete="CASCADE"), index=True, nullable=False
    )
    material_id: Mapped[int] = mapped_column(Integer, ForeignKey("materials.id"), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False)
    uom: Mapped[str | None] = mapped_column(String(16), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    request: Mapped["StockRequest"] = relationship(back_populates="lines")
    # Chỉ đọc — để đề nghị tự trả kèm mã/tên vật tư, không phụ thuộc danh mục phía client.
    material = relationship("Material", lazy="selectin", viewonly=True)

    @property
    def material_code(self) -> str | None:
        return self.material.code if self.material else None

    @property
    def material_name(self) -> str | None:
        return self.material.name if self.material else None
