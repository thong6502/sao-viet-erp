"""Yêu cầu HỦY đơn nghỉ phép / phiếu tăng ca ĐÃ DUYỆT (chủ chốt 23/09/2026).

Đơn đã duyệt là một cam kết trong kế hoạch của tổ (đã xếp người thay ca, đã lên kế hoạch chạy
đơn) ⇒ người lao động KHÔNG tự hủy thẳng được nữa, chỉ được XIN hủy. Ai có quyền duyệt phiếu thì
duyệt yêu cầu hủy; không có hạn chót, người duyệt tự cân nhắc; nghỉ phép và tăng ca y hệt nhau.
Thiết kế: `docs/prd-xin-huy-don-da-duyet.md`.

MỘT bảng cho cả hai loại đơn (`loai`). Đơn gốc GIỮ trạng thái `approved` cho tới khi được đồng ý
hủy — nên bảng công, quỹ phép, cổng chấm tăng ca không phải biết gì về bảng này. Mỗi lần xin hủy
là một dòng ⇒ còn nguyên lịch sử (xin → giữ nguyên → xin lại → đồng ý).

Người duyệt / HCNS HỦY TRỰC TIẾP đơn đã duyệt cũng ghi một dòng ở đây (`truc_tiep`), để lý do hủy
có chỗ lưu và người lao động đọc được. Bảng MỚI ⇒ `create_all` tạo, không migration.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, false as sa_false
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

LOAI_NGHI_PHEP = "nghi_phep"   # leave_requests
LOAI_TANG_CA = "tang_ca"       # overtime_requests
LOAI_DON = (LOAI_NGHI_PHEP, LOAI_TANG_CA)

TT_CHO = "cho"                 # đang chờ người duyệt quyết — đơn gốc VẪN hiệu lực
TT_DONG_Y = "dong_y"           # đã hủy (cả đơn, hoặc phần ngày còn lại của đơn nghỉ đang dở)
TT_GIU_NGUYEN = "giu_nguyen"   # người duyệt giữ đơn — vẫn đi làm / vẫn nghỉ như đã duyệt
TT_RUT_LAI = "rut_lai"         # người lao động rút lại trước khi có ai quyết
TRANG_THAI = (TT_CHO, TT_DONG_Y, TT_GIU_NGUYEN, TT_RUT_LAI)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class YeuCauHuy(Base):
    __tablename__ = "yeu_cau_huy"
    __table_args__ = (
        Index("ix_yeu_cau_huy_don", "loai", "request_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    loai: Mapped[str] = mapped_column(String(12), nullable=False)
    # Id trong `leave_requests` hoặc `overtime_requests` tuỳ `loai` — hai bảng nên không đặt FK.
    request_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # Chép từ đơn gốc: lọc theo phạm vi tổ của người duyệt mà không phải JOIN hai bảng đơn.
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    ly_do: Mapped[str] = mapped_column(String(500), nullable=False)
    trang_thai: Mapped[str] = mapped_column(String(12), nullable=False, default=TT_CHO,
                                            server_default=TT_CHO, index=True)
    # true = người duyệt / HCNS hủy thẳng (không qua bước xin) — dòng sinh ra đã ở `dong_y`.
    truc_tiep: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False,
                                            server_default=sa_false())
    # ĐƠN NGHỈ ĐANG DỞ (chủ chốt "tính nghỉ 1 ngày"): hủy từ ngày này trở đi, giữ các ngày trước
    # đó. Bằng ngày bắt đầu (hoặc null) = hủy cả đơn. Phiếu tăng ca luôn null.
    huy_tu_ngay: Mapped[date | None] = mapped_column(Date, nullable=True)
    # `end_date` gốc của đơn nghỉ, ghi lúc đồng ý rút ngắn — để còn biết đơn từng dài bao nhiêu.
    den_ngay_cu: Mapped[date | None] = mapped_column(Date, nullable=True)
    ly_do_quyet: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow,
                                                 nullable=False)
    decided_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
