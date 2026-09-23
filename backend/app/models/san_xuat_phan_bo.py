"""Thực hiện sản xuất — HỖ TRỢ CHÉO (Giai đoạn 4, §9).

MỘT bảng duy nhất: `san_xuat_ho_tro` — thoả thuận "người tổ nào sang giúp tổ nào, ngày nào, cho
công đoạn nào", xác nhận HAI tổ trưởng. Trạng thái: pending_both → confirmed → cancelled.

⚠️ TẦNG CHIA SẢN LƯỢNG GỠ HẲN 18/09/2026 (mg `0322`). Bốn bảng `san_xuat_phan_bo`,
`san_xuat_phan_bo_dong`, `san_xuat_phan_bo_bu_tru`, `san_xuat_phan_bo_loai_tru` XOÁ, cùng engine
`services/san_xuat/phan_bo.py` (chia theo phút + largest-remainder) và cột
`san_xuat_ho_tro.ty_le_phan_tram`.

Vì sao: chủ dự án bác hẳn việc máy tự chia — *"không có cái nào là chia cho từng người đâu. Ví dụ
mẻ đó 3 người, ghi sản lượng 3.000 và thay kẽm số lượng 2, thì ghi nhận thế thôi, đừng có chia bất
cứ gì"*. Cách chia sẽ có ở màn KẾ TOÁN, đọc thẳng mẻ. Tỷ lệ phần trăm của phiếu hỗ trợ đi theo vì
nó chỉ sinh ra để chia; còn VẾT ai sang giúp ai thì giữ, đó là việc giữa hai tổ trưởng.

An toàn vì prod đang DB trắng và cột khoán của bảng lương đã bằng 0 cho mọi người từ 11/09/2026 —
chưa đồng nào chảy qua tầng chia.

Mẻ nhiều tổ nay KHÔNG chia: mẻ có CHỦ duy nhất (tổ của bước), và hiện đủ con số ở tab Sản lượng của
mọi tổ có người trong mẻ — tổ khách thấy ở mục riêng, không cộng vào tổng của mình.

Boolean dùng `false()`/`true()` (bẫy Postgres DB trắng).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# --- Trạng thái thỏa thuận hỗ trợ (§9.1, §18) ------------------------------------------------
HT_CHO_HAI_BEN = "pending_both"   # chờ đủ xác nhận của hai tổ trưởng (gốc + thực hiện)
HT_XAC_NHAN = "confirmed"         # cả hai tổ trưởng đã xác nhận → phiếu thành vết chính thức
HT_HUY = "cancelled"              # đã huỷ (vd lịch chưa chạy bị phát hành cập nhật §9.2)
TRANG_THAI_HO_TRO = (HT_CHO_HAI_BEN, HT_XAC_NHAN, HT_HUY)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SanXuatHoTro(Base):
    """Một THỎA THUẬN hỗ trợ chéo giữa hai tổ cho một công đoạn (§9.1).

    Xác nhận HAI tổ trưởng: `xac_nhan_goc_*` (tổ gốc của người hỗ trợ) và `xac_nhan_thuc_hien_*`
    (tổ đang thực hiện công đoạn). Đủ cả hai → `trang_thai=confirmed`. Phần hỗ trợ thuộc
    `ngay_lam_viec` (§9.2: không chuyển sang ngày hoàn thành công đoạn)."""

    __tablename__ = "san_xuat_ho_tro"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cong_viec_id: Mapped[int] = mapped_column(
        ForeignKey("san_xuat_cong_viec.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Tổ gốc = nơi ghi nhận phần hỗ trợ (§9.2). Tổ thực hiện = snapshot tổ của công đoạn.
    to_goc_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    to_thuc_hien_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    ngay_lam_viec: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # ⚠️ `ty_le_phan_tram` GỠ 18/09/2026 (mg `0322`) — tỷ lệ chỉ sinh ra để CHIA sản lượng, mà tầng
    # chia đã gỡ hẳn. Phiếu hỗ trợ nay thuần là VẾT "ai sang giúp ai, ngày nào".
    trang_thai: Mapped[str] = mapped_column(String(16), nullable=False, default=HT_CHO_HAI_BEN)
    mo_ta: Mapped[str | None] = mapped_column(String(500), nullable=True)
    de_xuat_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    xac_nhan_goc_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    xac_nhan_goc_luc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    xac_nhan_thuc_hien_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    xac_nhan_thuc_hien_luc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    huy_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    huy_luc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ly_do_huy: Mapped[str | None] = mapped_column(String(500), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
