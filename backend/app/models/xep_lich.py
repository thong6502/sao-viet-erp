"""Xếp lịch công đoạn — biến routing (đã "sẵn sàng") thành công việc CÓ MÁY + GIỜ cụ thể.

Mỗi dòng = 1 công đoạn cần xếp lịch. Hai NGUỒN:
- `lsx`     : 1 công đoạn của 1 lệnh sản xuất (neo `lsx_cong_doan_id`).
- `in_ghep` : 1 công đoạn CHẠY CHUNG của 1 bài ghép (neo `bai_ghep_id` + `bai_ghep_cong_doan_id`) —
  xuất hiện MỘT lần dưới mã bài ghép, KHÔNG lặp trên từng LSX thành viên. Bài gộp được nhiều công
  đoạn (CTP · in · cán · bế) nên có thể có NHIỀU dòng loại này cho một bài. Kết thúc của bước chung
  MUỘN NHẤT là tiền đề cho các bước riêng sau điểm toả của từng LSX.

BẢNG CHỈ LƯU QUYẾT ĐỊNH CỦA NGƯỜI (gán máy/tổ/NCC · ca · giờ bắt đầu/kết thúc · trạng thái · khóa). Mọi
số DẪN XUẤT (thời lượng, sớm-nhất/muộn-nhất, độ dư, nhãn nguy cơ, cờ xung đột) TÍNH LÚC ĐỌC ở service —
KHÔNG lưu cột (bám precedent `lsx_service.thoi_luong_buoc` / `bai_ghep_service.tinh_so_to`).

NEO CHÍNH `lsx_cong_doan_id` (PK bản ghi operation, KHÁC `cong_doan.id` danh mục): an toàn vì routing bị
KHÓA khi lệnh đã `da_lap_ke_hoach` (chặn `replace_routing` — nơi duy nhất id công đoạn tái sinh). Vòng
đời không mồ côi: "gỡ kế hoạch" xóa dòng lịch TRƯỚC khi mở lại routing.

RBAC MODULE = "san_xuat" (tái dùng). Bảng mới → `create_all` tự tạo, KHÔNG migration. Boolean dùng
`false()` của SQLAlchemy (bẫy Postgres, KHÔNG "0"/"1"). FK cấu trúc (`lsx_id`, `bai_ghep_id`) là FK THẬT
+ `ondelete=CASCADE` (lớp chặn cuối ở DB); FK danh mục (máy · tổ · ca) MỀM theo convention repo.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, String,
    false as sa_false,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# --- Nguồn dòng lịch ---
NGUON_LSX = "lsx"          # công đoạn của 1 lệnh sản xuất
NGUON_IN_GHEP = "in_ghep"  # công đoạn in chạy chung của 1 bài ghép
NGUON = (NGUON_LSX, NGUON_IN_GHEP)

# --- Trạng thái xếp lịch của DÒNG (khác trạng thái lệnh). Lát 1: chờ ↔ đã xếp; "đã khóa"/"có xung đột"
# là biểu diễn DẪN XUẤT ở UI (từ `is_locked` + cờ xung đột tính lúc đọc), không phải giá trị lưu riêng.
TT_CHO_XEP = "cho_xep"  # chưa đủ máy/giờ để lên Gantt
TT_DA_XEP = "da_xep"    # đã có máy (hoặc tổ/NCC) + giờ bắt đầu
TRANG_THAI_XEP_LICH = (TT_CHO_XEP, TT_DA_XEP)

# --- Mã lý do bị chặn (`blocked_reason`) — người đọc hiểu vì sao chưa xếp được. Tập MỞ, service điền.
LY_DO_THIEU_MAY = "thieu_may"                # bước nội bộ chưa gán máy/tổ
LY_DO_THIEU_THOI_LUONG = "thieu_thoi_luong"  # chưa khai năng suất → không tính được thời lượng
LY_DO_CHO_TIEN_DE = "cho_tien_de"            # bước trước chưa xếp/chưa xong


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class XepLichCongDoan(Base):
    """1 dòng kế hoạch xếp lịch cho 1 công đoạn (operation) hoặc 1 lần in chung của bài ghép."""

    __tablename__ = "xep_lich_cong_doan"
    # Query xung đột máy: gom theo máy rồi so khoảng [start_at, finish_at) → index (máy, giờ bắt đầu).
    __table_args__ = (
        Index("ix_xep_lich_may_thoigian", "may_id", "start_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # --- Nhận diện nguồn ---
    nguon: Mapped[str] = mapped_column(String(12), nullable=False, default=NGUON_LSX)
    # FK THẬT + CASCADE (lớp chặn cuối DB). Nullable vì dòng `in_ghep` không thuộc 1 LSX cụ thể.
    lsx_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("lsx.id", ondelete="CASCADE"), index=True, nullable=True
    )
    # NEO CHÍNH → `lsx_cong_doan.id` (soft — id ổn định nhờ khóa routing khi đã lập KH). Null khi `in_ghep`.
    lsx_cong_doan_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    bai_ghep_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("bai_ghep.id", ondelete="CASCADE"), index=True, nullable=True
    )
    # NEO bước chạy chung NÀO của bài (soft → `bai_ghep_cong_doan.id`). Bài gộp cả CTP/cán/bế chứ
    # không riêng bước in, nên MỖI bước chung là MỘT dòng lịch. Trước đây bài chỉ đẻ đúng một dòng
    # "in ghép" trong khi routing lệnh đã loại hết bước bị đè → gộp CTP/cán là hai bước đó biến mất
    # khỏi board: không đặt chỗ máy, không tính thời lượng, không ai báo.
    bai_ghep_cong_doan_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    # Snapshot `lsx_cong_doan.thu_tu` — sắp thứ tự chuỗi + suy bước trước-sau không cần join.
    source_thu_tu: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Snapshot loại bước routing (may/to/thue_ngoai); dòng in ghép cũng dùng `may`.
    loai_buoc: Mapped[str] = mapped_column(String(12), nullable=False, default="may")

    # --- Tài nguyên được gán (record-only: máy đề xuất, người quyết) ---
    may_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)         # → may_thiet_bi.id
    department_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)  # → departments.id (tổ)
    nha_cung_cap: Mapped[str | None] = mapped_column(String(150), nullable=True)  # thuê ngoài — text tự do
    work_shift_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)  # → work_shifts.id

    # --- Lịch (theo GIỜ — persist để Gantt đọc + query xung đột) ---
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Trạng thái ---
    trang_thai: Mapped[str] = mapped_column(String(16), nullable=False, default=TT_CHO_XEP)
    is_locked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_false(), default=False
    )
    blocked_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ghi_chu: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)  # → users.id
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
