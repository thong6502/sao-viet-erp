"""Vấn đề kế hoạch (xung đột & nguy cơ trễ) — CHỈ lưu PHẦN CON NGƯỜI XỬ LÝ một vấn đề dẫn xuất.

Bản thân "vấn đề" (trùng máy / đè khóa / sai tiền nhiệm / nguy cơ trễ …) là DẪN XUẤT từ trạng thái
lịch hiện tại, TÍNH LÚC ĐỌC ở `XepLichVanDeService.liet_ke()` — KHÔNG lưu (bám mô hình BC Planning
Worksheet: cảnh báo/action-message recompute mỗi lần chạy, không phải thực thể). Bảng này chỉ neo phần
người chạm vào: tiếp nhận / giao / ghi chú / duyệt ngoại lệ — định danh bằng `issue_key` (vân tay ổn
định). Vấn đề tự hết hiệu lực khi lịch hết xung đột (state giữ lại để tra cứu); khớp lại `issue_key`
→ `tai_phat += 1` (mở lại). Lịch sử chuyển trạng thái dùng `AuditLogRepository` — KHÔNG đẻ bảng events.

Bảng mới → `create_all` tự tạo, KHÔNG migration (như `xep_lich_cong_doan`/`machine_unavailable_periods`).
KHÔNG cột Boolean (né bẫy Postgres server_default "0"/"1"). Mọi DateTime tz-aware. FK (user) MỀM theo
convention repo. RBAC MODULE = "san_xuat" (tái dùng).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# --- Vòng đời (BC "Accept Action Message": máy đề xuất, người TIẾP NHẬN rồi mới xử lý). `moi` = chưa
# có ai chạm (KHÔNG có dòng state); dòng chỉ sinh khi có hành động đầu tiên.
TT_MOI = "moi"
TT_TIEP_NHAN = "tiep_nhan"
TT_DANG_XU_LY = "dang_xu_ly"
TT_DA_XU_LY = "da_xu_ly"
TT_NGOAI_LE = "ngoai_le"      # chấp nhận ngoại lệ (nguyên nhân còn đó — khác đã xử lý)
TT_TAM_HOAN = "tam_hoan"
TRANG_THAI_VAN_DE = (TT_MOI, TT_TIEP_NHAN, TT_DANG_XU_LY, TT_DA_XU_LY, TT_NGOAI_LE, TT_TAM_HOAN)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class XepLichVanDe(Base):
    """Phần con người xử lý của 1 vấn đề kế hoạch, neo theo `issue_key` (vân tay dẫn xuất)."""

    __tablename__ = "xep_lich_van_de"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Vân tay vấn đề (vd `trung_may:{may_id}:{a}:{b}`) — 1 vấn đề dẫn xuất ↔ 1 dòng state. Unique.
    issue_key: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)

    trang_thai: Mapped[str] = mapped_column(String(16), nullable=False, default=TT_TIEP_NHAN)
    assigned_to: Mapped[int | None] = mapped_column(Integer, nullable=True)  # soft → users.id
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # --- Ngoại lệ (chấp nhận cho phát hành dù còn cảnh báo) ---
    exception_ly_do: Mapped[str | None] = mapped_column(Text, nullable=True)
    exception_by: Mapped[int | None] = mapped_column(Integer, nullable=True)  # soft → users.id (người duyệt)
    exception_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Số lần vấn đề tái phát (tự hết hiệu lực rồi quay lại) — tăng khi `issue_key` khớp lại.
    tai_phat: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)  # soft → users.id
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
