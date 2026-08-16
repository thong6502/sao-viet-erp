"""Danh mục Khuôn bế — KHAI BÁO nơi lưu trữ khuôn bế (master data nhẹ).

Mỗi khuôn bế được làm riêng cho hình bế của 1 ấn phẩm; đơn lặp lại thì lôi khuôn cũ
ra dùng. Bản này CHỈ khai báo để tìm lại: mã / tên ấn phẩm / khách hàng / số kệ (vị trí
lưu) / ngày làm khuôn / tình trạng / ghi chú — khai TAY. Liên kết ref (ấn phẩm, khách
hàng) đấu sau. Bảng MỚI → `create_all` tự dựng (không migration; migration chỉ cho ALTER
cột bảng cũ). Gác quyền module riêng `khuon_be`.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Integer, String, true as sa_true
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# Tình trạng khuôn — record-only (con người phán, máy chỉ ghi nhận).
# `dang_dat_lam` (mg 0177): khuôn CHƯA có trong tay, đang đặt thợ làm. Đi kèm `ngay_ve_du_kien` —
# bàn xếp lịch so ngày đó với giờ bắt đầu bước bế để biết khuôn có KỊP không.
TINH_TRANG = ("dang_dung", "dang_dat_lam", "hong", "thanh_ly")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class KhuonBe(Base):
    """1 dòng = 1 khuôn bế đã khai báo (vd khuôn hộp bánh của khách A)."""

    __tablename__ = "khuon_be"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ma: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)  # KB-####
    ten: Mapped[str] = mapped_column(String(200), nullable=False)            # tên khuôn / ấn phẩm áp dụng
    # 🔴 XOÁ 15/08/2026: `khach_hang` — chủ dự án yêu cầu. Cột khai TAY, không nối danh mục Khách
    # hàng, nên nó là bản chép tên dễ lệch (gõ "Cty Kinh Đô" ở đây vs "Công ty CP Kinh Đô" ở CRM).
    # Khuôn nhận diện bằng MÃ + TÊN ấn phẩm; muốn biết của khách nào thì tra qua lệnh dùng khuôn đó.
    so_ke: Mapped[str | None] = mapped_column(String(120), nullable=True)    # số kệ / vị trí lưu ← lõi
    ngay_lam_khuon: Mapped[date | None] = mapped_column(Date, nullable=True)  # ngày làm khuôn mới
    tinh_trang: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="dang_dung", default="dang_dung"
    )  # dang_dung|dang_dat_lam|hong|thanh_ly
    # Ngày khuôn ĐANG ĐẶT LÀM dự kiến về (mg 0177). Chỉ có nghĩa với `tinh_trang='dang_dat_lam'`.
    ngay_ve_du_kien: Mapped[date | None] = mapped_column(Date, nullable=True)
    ghi_chu: Mapped[str | None] = mapped_column(String(500), nullable=True)

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_true(), default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
