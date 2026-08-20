"""Danh mục LÝ DO & LỖI sản xuất — dùng chung cho hỏng batch, lỗi KCS, và các lý do vận hành (§15).

Một danh mục CHUẨN HOÁ, gộp vào màn Cấu hình danh mục hiện có (KHÔNG đẻ màn mới). Cột `nhom` phân
loại dùng-vào-việc-gì (lỗi hỏng vs lý do tạm dừng vs điều chỉnh bàn giao…): batch hỏng chỉ chọn
`nhom='loi'`, ô "lý do tạm dừng" chỉ chọn `nhom='tam_dung'`, v.v. Frontend KHÔNG hard-code danh
sách lý do — mọi ô chọn đổ từ đây, lọc theo `nhom` (§15 cuối).

RBAC tái dùng module "san_xuat" (không đẻ quyền mới — xem `catalog_registry`). Bảng MỚI →
`create_all` tự dựng, KHÔNG migration. Boolean dùng `true()` của SQLAlchemy (bẫy Postgres DB trắng).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, true as sa_true
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# --- Nhóm lý do/lỗi chuẩn hoá (§15) ----------------------------------------------------------
# Một danh mục lỗi CHUNG cho hỏng-sản-xuất + lỗi-KCS: cùng `nhom='loi'`.
NHOM_LOI = "loi"                       # sản lượng hỏng tại công đoạn + lỗi KCS phát hiện
# Các lý do vận hành:
NHOM_TAM_DUNG = "tam_dung"             # lý do tạm dừng phiên chạy
NHOM_BAT_DAU_TRE = "bat_dau_tre"       # lý do bắt đầu trễ so với dự kiến
NHOM_LECH_NHAN_SU = "lech_nhan_su"     # số người thực tế khác dự kiến (§7.1)
NHOM_THIEU_VAT_TU = "thieu_vat_tu"     # chạy khi vật tư chưa đủ (§10.2)
NHOM_DIEU_CHINH_BAN_GIAO = "dieu_chinh_ban_giao"  # điều chỉnh bàn giao (§11.3)
NHOM_MO_LAI_PHAN_BO = "mo_lai_phan_bo"  # mở lại phân bổ đã chốt (§12.3)
NHOM_DONG_THIEU = "dong_thieu"         # đóng thiếu nhóm thành phẩm (§13.3)
NHOM_LY_DO = (
    NHOM_LOI, NHOM_TAM_DUNG, NHOM_BAT_DAU_TRE, NHOM_LECH_NHAN_SU, NHOM_THIEU_VAT_TU,
    NHOM_DIEU_CHINH_BAN_GIAO, NHOM_MO_LAI_PHAN_BO, NHOM_DONG_THIEU,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SanXuatLyDo(Base):
    """1 dòng = 1 lý do/lỗi chuẩn hoá (vd nhóm `loi`: "Nhăn giấy"; nhóm `tam_dung`: "Chờ mực")."""

    __tablename__ = "san_xuat_ly_do"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ma: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    # Dùng-vào-việc-gì; ô chọn ở FE lọc theo cột này (xem NHOM_LY_DO). Service kiểm giá trị hợp lệ.
    nhom: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    ten: Mapped[str] = mapped_column(String(150), nullable=False)
    mo_ta: Mapped[str | None] = mapped_column(String(500), nullable=True)
    thu_tu: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)

    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_true(), default=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
