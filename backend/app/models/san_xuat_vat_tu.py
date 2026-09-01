"""Đề nghị cấp vật tư của TỔ tại một công đoạn (docs/spec-de-nghi-cap-vat-tu-cong-doan.md §2).

Vì sao là bảng RIÊNG chứ không nhét vào `stock_requests`: hai bảng này giữ BẢN ĐỐI CHIẾU của sản
xuất — kế hoạch bao nhiêu, tổ xin bao nhiêu, lệch vì lý do gì — kể cả những dòng tổ xin 0. Yêu cầu
kho chỉ là ẢNH CHIẾU của phần DƯƠNG: kho không cần biết "kế hoạch có mà tổ không lấy", và cũng
không được phép thấy lý do lệch (spec §7). Nhét chung một bảng là bắt kho gánh ngữ nghĩa của sản
xuất, rồi mọi màn kho phải học cách bỏ qua dòng 0.

Bảng MỚI → `create_all` tự dựng; migration `0249` chỉ cần cho cột thêm vào bảng CŨ.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base

# Lần đầu = ảnh của kế hoạch. Bổ sung = phát sinh sau khi kho đã lập phiếu cho lần trước.
DN_LAN_DAU = "lan_dau"
DN_BO_SUNG = "bo_sung"
DE_NGHI_LOAI = (DN_LAN_DAU, DN_BO_SUNG)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SanXuatVatTuDeNghi(Base):
    """Một LẦN tổ đề nghị cấp vật tư cho một công đoạn."""

    __tablename__ = "san_xuat_vat_tu_de_nghi"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cong_viec_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("san_xuat_cong_viec.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    lan_so: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    loai: Mapped[str] = mapped_column(String(12), nullable=False, default=DN_LAN_DAU)
    # GIỜ cần thật. `stock_requests.ngay_can` chỉ có DATE, mà ca chiều cần hàng lúc 13h30 khác hẳn
    # ca sáng cần lúc 6h — kho soạn theo giờ chứ không theo ngày.
    can_luc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Yêu cầu kho ảnh chiếu. NULL khi MỌI dòng bằng 0 — tổ xác nhận không cần cấp gì, không có
    # việc gì cho kho làm, nên không đẻ chứng từ rỗng.
    stock_request_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("stock_requests.id", ondelete="SET NULL"), nullable=True
    )
    created_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    updated_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    dongs: Mapped[list["SanXuatVatTuDeNghiDong"]] = relationship(
        "SanXuatVatTuDeNghiDong", back_populates="de_nghi",
        cascade="all, delete-orphan", order_by="SanXuatVatTuDeNghiDong.id",
    )

    __table_args__ = (
        UniqueConstraint("cong_viec_id", "lan_so", name="uq_sx_vt_de_nghi_cv_lan"),
        # Một yêu cầu kho chỉ thuộc đúng một lần đề nghị — nếu không thì "sửa lần 2" có thể
        # ghi đè yêu cầu của lần 1 mà không ai phát hiện.
        UniqueConstraint("stock_request_id", name="uq_sx_vt_de_nghi_stock_request"),
    )


class SanXuatVatTuDeNghiDong(Base):
    """Một mặt hàng trong một lần đề nghị.

    Lần ĐẦU lưu MỌI vật tư kế hoạch, kể cả dòng tổ xin 0 — để về sau đọc được "kế hoạch có, tổ
    không lấy", câu đó không suy ngược được từ yêu cầu kho (yêu cầu kho chỉ chứa dòng dương).
    Vật tư ngoài kế hoạch: `sl_ke_hoach = 0`.

    Bốn con số vì phải so được HAI thang: `sl_*` theo đơn vị người ta nhìn (tờ, ram, thùng) để bản
    in đúng chữ, `sl_*_goc` theo đơn vị gốc để MÁY so lệch. So bằng đơn vị người khai là so 100 tờ
    với 12 kg.
    """

    __tablename__ = "san_xuat_vat_tu_de_nghi_dong"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    de_nghi_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("san_xuat_vat_tu_de_nghi.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    hang_loai: Mapped[str] = mapped_column(String(8), nullable=False)
    hang_id: Mapped[int] = mapped_column(Integer, nullable=False)
    dvt: Mapped[str] = mapped_column(String(24), nullable=False)
    dvt_goc: Mapped[str] = mapped_column(String(24), nullable=False)
    sl_ke_hoach: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False, default=0.0)
    sl_ke_hoach_goc: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False, default=0.0)
    sl_yeu_cau: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False, default=0.0)
    sl_yeu_cau_goc: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False, default=0.0)
    ly_do_chenh_lech: Mapped[str | None] = mapped_column(String(500), nullable=True)

    de_nghi: Mapped[SanXuatVatTuDeNghi] = relationship(
        "SanXuatVatTuDeNghi", back_populates="dongs"
    )

    __table_args__ = (
        UniqueConstraint("de_nghi_id", "hang_loai", "hang_id", name="uq_sx_vt_dn_dong_hang"),
    )
