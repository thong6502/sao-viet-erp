"""Phiếu xin ĐI MUỘN / VỀ SỚM / NGHỈ NỬA BUỔI (module `di_muon`).

Một bảng:
  - `late_early_requests` — phiếu xin VẮNG MẶT một khoảng giờ trong MỘT ngày công: NV tự gửi rồi
                            tổ trưởng duyệt, HOẶC tổ trưởng khai hộ (duyệt luôn).

Vì sao KHÔNG dùng chung `leave_requests` (chốt với chủ 27/07/2026): đây không phải đơn nghỉ phép mà
là **phiếu chấm công ngoại lệ** — cùng hình dạng với phiếu tăng ca (1 ngày, từ giờ → đến giờ, 1
phiếu/ngày, TỔ TRƯỞNG duyệt). Gộp vào đơn nghỉ thì phải nhớ lọc nó ra ở 7 chỗ đọc đơn nghỉ (badge,
chuông, lịch nghỉ, 2 danh sách, chặn chốt công, quota); sót một chỗ là hai loại phiếu lẫn vào nhau —
đúng lỗi chủ đã gặp.

HAI NHÁNH TIỀN, phân biệt bằng `leave_type_id`:
  - NULL          → không trừ quỹ phép; phần vắng KHÔNG được trả công (đi muộn / về sớm thường).
  - khác NULL     → tiêu `leave_cong` ngày phép (làm tròn 0,5) và phần vắng VẪN được trả theo
                    LƯƠNG VỊ TRÍ (đúng luật "ngày nghỉ phép chỉ trả lương cơ bản").
Cả hai nhánh đều được MIỄN PHẠT đi muộn/về sớm đúng số phút đã xin.

Portable across SQLite/Postgres.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_CANCELLED = "cancelled"
LATE_EARLY_STATUSES = (STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED, STATUS_CANCELLED)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LateEarlyRequest(Base):
    """Phiếu xin vắng mặt theo GIỜ của 1 NV cho 1 NGÀY CÔNG."""

    __tablename__ = "late_early_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # NGÀY CÔNG của ca gốc (ngày VÀO ca) — khớp đúng cách Bảng công tháng gom ca qua đêm.
    work_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    # Khoảng VẮNG MẶT tính bằng PHÚT TỪ 00:00 CỦA `work_date`, cùng trục tuyến tính mà
    # `compute_day_cong` dùng. Engine chỉ dùng ĐỘ DÀI `to_minute - from_minute`.
    from_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    to_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    # Trừ vào quỹ phép năm hay không — do người tạo phiếu tự chọn.
    # NULL = không trừ (mất công phần vắng). Khác NULL = loại nghỉ bị trừ (soft-ref `leave_types.id`,
    # KHÔNG FK cứng để loại nghỉ bị xoá không kéo đổ phiếu đã duyệt).
    leave_type_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    # Số ngày phép bị trừ, ĐÃ LÀM TRÒN 0,5 (vắng ≤ nửa ca → 0,5; vượt nửa ca → 1,0). 0 khi không trừ.
    leave_cong: Mapped[float] = mapped_column(
        Numeric(4, 2), nullable=False, default=0, server_default="0"
    )
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=STATUS_PENDING, server_default=STATUS_PENDING, index=True
    )
    decided_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    # Chuông Topbar: thời điểm NGƯỜI NỘP đã xem kết quả. NULL = chưa xem. Timestamp, KHÔNG Boolean
    # (né gotcha server_default vỡ Postgres).
    seen_by_employee_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
