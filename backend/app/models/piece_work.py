"""Đơn giá khoán ORM (module `luong`, nhịp 2).

Một bảng duy nhất:
  - `piece_rates` — đơn giá khoán theo tổ/bộ phận + đơn vị (m²/bài in/tấn/cuốn/lượt/hộp).
                    Số hóa các bảng "CÔNG KHOÁN" thật; là bảng giá tra khi ghi Phiếu sản lượng.

Lương khoán KHÔNG còn tầng "sổ khoán" (quỹ tổ + chia hệ số). Tiền khoán mỗi NV = Phiếu sản
lượng theo NGƯỜI (SL × đơn giá − trừ lỗi) cộng thẳng vào cột `khoan` của payroll_lines khi tính
lương (xem PieceWorkService.khoan_map). Portable SQLite/Postgres.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# --- Đơn vị tính đơn giá khoán ----------------------------------------------
#
# ⚠️ ĐÂY CHỈ LÀ GỢI Ý MỒI, KHÔNG PHẢI WHITELIST (chủ 29/07/2026: *"chỉ select được mấy cái thôi,
# nhiều cái khác thì sao, bất tiện lắm"*). Nhà máy in còn hàng chục đơn vị khác (mét tới, ram,
# thùng carton…) — người dùng gõ thẳng, đơn vị nào đã dùng sẽ tự vào danh sách gợi ý lần sau
# (`PieceWorkRepository.distinct_units`).
#
# Lưu CHỮ HIỂN THỊ, không phải mã. Bản cũ lưu mã (`m2`) rồi dịch sang nhãn (`m²`) lúc hiện —
# cho gõ tự do mà giữ cách đó thì bấm gợi ý "m²" lưu ra chuỗi khác với mã "m2" của dòng cũ:
# hai dòng cùng nghĩa, khác giá trị. Migration 0125 đã đổi 8 mã cũ sang nhãn.
DEFAULT_PIECE_UNITS = (
    "m²",        # bồi, cán/phủ
    "bài in",    # máy in, theo số màu
    "tấn",       # cắt giấy cuộn
    "cuốn",      # cắt/bắt thành phẩm
    "lượt",      # cắt demi
    "hộp",       # gỡ hàng
    "tờ",
    "kg",
    "bộ",
    "chiếc",
    "khác",
)
UNIT_KHAC = "khác"   # giá trị mặc định khi bỏ trống

_MONEY = Numeric(14, 2)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PieceRate(Base):
    """Đơn giá khoán: 1 công việc của 1 tổ với đơn vị + đơn giá."""

    __tablename__ = "piece_rates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Tổ khoán (vd 'to_boi', 'to_can_phu', 'to_cat', 'may_in_5mau'). Trục gom + tra.
    group_name: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    # Tổ (departments.id) sở hữu đơn giá — khai đơn giá NGAY trong Cấu hình lương của tổ.
    # Nullable: đơn giá cũ/chưa gắn tổ vẫn hợp lệ; group_name giữ làm nhãn hiển thị.
    department_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    code: Mapped[str | None] = mapped_column(String(20), nullable=True)  # mã (A–F cho máy in)
    name: Mapped[str] = mapped_column(String(255), nullable=False)       # tên công việc
    # Công đoạn gắn đơn giá (mã cong_doan.ma) — tra đơn giá theo (tổ + công đoạn) khi ghi phiếu.
    cong_doan: Mapped[str | None] = mapped_column(String(30), index=True, nullable=True)
    # CHỮ hiển thị, không phải mã — xem ghi chú ở `DEFAULT_PIECE_UNITS`. 24 ký tự vì 12 vừa khít
    # "thùng carton" là hỏng. Đổi kiểu cột ⇒ migration 0125.
    unit: Mapped[str] = mapped_column(String(24), nullable=False, default=UNIT_KHAC, server_default=UNIT_KHAC)
    unit_price: Mapped[float] = mapped_column(_MONEY, nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class PieceLeaderBonusBracket(Base):
    """Bậc THƯỞNG/PHẠT tổ trưởng theo TỶ LỆ HÀNG LỖI của tổ (chủ 29/07/2026).

    Chủ: *"thằng tổ trưởng — thêm cơ chế thưởng phạt theo bậc lũy tiến ăn theo phần trăm của tổng
    sản lượng lương khoán của tổ. Hàng lỗi khoảng 5% thì thưởng 2% trên tổng, lỗi trên 10% thì bị
    trừ 10% trên tổng. **% này là tiền đó nha**."*

    Mỗi TỔ một bộ mốc riêng (`department_id`) — khác `LatePenaltyBracket`/`PitTaxBracket` vốn là
    bảng toàn công ty. Cách tra thì y hệt: bậc ĐẦU TIÊN có `tỷ lệ lỗi ≤ up_to_defect_pct` thắng;
    `up_to_defect_pct = NULL` là bậc cao nhất (∞), phải nằm cuối.

    Ví dụ đúng số chủ nêu:
        seq 1 · ≤ 5%   · +2,00  ⇒ thưởng 2% tổng khoán của tổ
        seq 2 · ≤ 10%  ·  0,00  ⇒ không thưởng không phạt
        seq 3 · (∞)    · −10,00 ⇒ phạt 10% tổng khoán của tổ

    ⚠️ ENGINE CHƯA ÁP BẢNG NÀY. Tiền thưởng/phạt tính trên TỔNG TIỀN KHOÁN của tổ, mà tổng khoán
    hiện **luôn = 0**: `PieceWorkService.khoan_map` đọc từ `self.outputs`, nhưng
    `ProductionOutputRepository` KHÔNG TỒN TẠI trong code và `deps.py` truyền `outputs=None`.
    Khai mốc ở đây là chuẩn bị sẵn; nối vào lương cùng lúc dựng lại nguồn sản lượng. Màn khai có
    banner nói thẳng điều này — đừng gỡ.
    """

    __tablename__ = "piece_leader_bonus_brackets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Tổ sở hữu bộ mốc. Soft-ref `departments.id` (không FK cứng, giống `piece_rates`).
    department_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)                # thứ tự bậc 1..N
    # Trần % HÀNG LỖI của bậc. NULL = bậc cao nhất (∞) — đúng MỘT bậc và phải ở cuối.
    up_to_defect_pct: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    # % trên TỔNG TIỀN KHOÁN của tổ. DƯƠNG = thưởng · ÂM = phạt. Gõ nhầm dấu là đảo ngược ý nghĩa.
    rate_pct: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
