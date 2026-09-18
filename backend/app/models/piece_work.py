"""Đơn giá khoán ORM (module `luong`, nhịp 2).

Một bảng duy nhất:
  - `piece_rates` — đơn giá khoán theo công việc + đơn vị (m²/bài in/tấn/cuốn/lượt/hộp); các tổ
                    làm việc đó ở bảng nối `cong_viec_khoan_to`.
                    Số hóa các bảng "CÔNG KHOÁN" thật; là bảng giá tra khi ghi Phiếu sản lượng.

Lương khoán KHÔNG còn tầng "sổ khoán" (quỹ tổ + chia hệ số). Tiền khoán mỗi NV = Phiếu sản
lượng theo NGƯỜI (SL × đơn giá − trừ lỗi) cộng thẳng vào cột `khoan` của payroll_lines khi tính
lương (xem PieceWorkService.khoan_map). Portable SQLite/Postgres.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base

# --- Đơn vị tính đơn giá khoán ----------------------------------------------
#
# Đơn vị CHỌN TỪ DANH MỤC `Đơn vị & quy đổi` (chủ 31/07/2026 — xem
# `GET /api/payroll/khoan/units`). Trước đó là ô gõ tự do có gợi ý mồi; gõ tự do thì đơn vị lệch
# một chữ so với danh mục là lệnh sản xuất vĩnh viễn không quy đổi ra tiền được. Thiếu đơn vị ⇒
# thêm ở danh mục, KHÔNG sửa code.
#
UNIT_KHAC = "khác"   # giá trị mặc định khi bỏ trống

_MONEY = Numeric(14, 2)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PieceRate(Base):
    """Đơn giá khoán: 1 công việc (của một hay NHIỀU tổ) với đơn vị + đơn giá.

    Từ 17/08/2026 đây là DANH MỤC "Công việc khoán" trong Cấu hình danh mục (`loai =
    "cong_viec_khoan"`, quyền `dm_cong_viec_khoan`) — cùng nền với 10 màn kia, nên có mã tự sinh,
    nhật ký từng dòng và luật xoá chung. Nó vẫn là bảng giá mà Lương khoán tra, chỉ khác chỗ KHAI:
    trước nằm trong một tab của màn Lương, nay đứng cùng chỗ với Công đoạn · Đơn vị · Bù hao, vì
    bên dùng nó nhiều nhất là SẢN XUẤT (bước lệnh chọn đầu việc khoán), không phải kế toán lương.
    """

    __tablename__ = "piece_rates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # ⚠️ `group_name` (nhãn tổ) + `department_id` (MỘT tổ) GỠ 17/09/2026, mg `0311`: một công việc
    # khoán nay làm được ở NHIỀU tổ — danh sách nằm ở bảng nối `cong_viec_khoan_to` (`to_lam`).
    # ⚠️ `ma` · `ten` · `active` — ĐỔI TÊN từ `code` · `name` · `is_active` ngày 17/08/2026 (mg
    # `0210`) để bảng vào được nền danh mục dùng chung (`CatalogRepo` · `CatalogService` ·
    # `make_catalog_router` đều đọc đúng ba tên này). Đây là ĐỔI TÊN CỘT THẬT, không phải bí danh:
    # bốn màn danh mục khác đã đặt cùng ba tên đó, giữ hai bộ tên cho cùng một ý là nguồn gốc của
    # những lỗi "sửa một bên, bên kia im lặng chạy tên cũ".
    ma: Mapped[str | None] = mapped_column(String(20), nullable=True)  # mã (KH-####; A–F đời cũ)
    ten: Mapped[str] = mapped_column(String(255), nullable=False)      # tên công việc khoán
    # ⚠️ CỘT CHẾT — trước đây tra đơn giá theo (tổ + công đoạn). Bảng này giờ là KHAI BÁO thuần:
    # đơn giá chỉ treo vào TỔ, việc nào của tổ dùng đơn giá nào là do bên sản xuất chọn ở bước
    # lệnh. Giữ cột để không mất dữ liệu cũ; KHÔNG đọc ở bất kỳ đâu nữa.
    cong_doan: Mapped[str | None] = mapped_column(String(30), index=True, nullable=True)
    # CHỮ hiển thị, không phải mã — xem ghi chú ở `DEFAULT_PIECE_UNITS`. 24 ký tự vì 12 vừa khít
    # "thùng carton" là hỏng. Đổi kiểu cột ⇒ migration 0125.
    unit: Mapped[str] = mapped_column(String(24), nullable=False, default=UNIT_KHAC, server_default=UNIT_KHAC)
    unit_price: Mapped[float] = mapped_column(_MONEY, nullable=False)
    # CÔNG THỨC LƯỢNG của ĐẦU VIỆC NÀY (mg `0213`) — "việc này khoán theo lượng nào", tính ra số
    # đơn vị của `unit` rồi mới nhân `unit_price`.
    #
    # CÁCH ĐO LƯỢNG KHOÁN — tab "Công thức khoán" của màn Công việc khoán (18/09/2026, mg `0317`).
    # Ra LƯỢNG theo `unit`; màn Khoán theo kỳ của kế toán nhân với `unit_price`. TẦNG SẢN XUẤT
    # TUYỆT ĐỐI KHÔNG CHẠY CÔNG THỨC NÀY — bàn tổ chỉ ghi nhận số lượng, không phép nhân nào.
    #
    # Đây là QUAY NGƯỢC mg `0274` (hồi đó dời ô này xuống bảng đầu việc của công đoạn), ghi rõ
    # để lượt sau không tưởng là quên. Lý do hồi đó — "cùng đầu việc làm ở hai công đoạn thì đếm
    # khác nhau" — tan khi mỗi công việc khoán đã mang MÃ RIÊNG của xưởng, đã mã hoá sẵn khổ / số
    # màu / số lớp. Một mã việc = một cách đếm. Đo trên DB dev 18/09/2026: mỗi công việc khoán chỉ
    # khai ở ĐÚNG MỘT công đoạn, 0 xung đột công thức ⇒ dồn về đây là 1-1, không mất gì.
    cong_thuc_khoan: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Còn dùng hay đã ngừng. Xoá một đơn giá đang được định mức đầu việc trỏ tới là làm mồ côi dữ
    # liệu, nên luồng xoá chung chỉ tắt cờ này khi còn nơi dùng (xem `danh_muc_tham_chieu`).
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    # VIỆC PHÁT SINH của công việc khoán này (14/09/2026) — xem `ViecPhatSinh`. `delete-orphan`:
    # bỏ một dòng khỏi danh sách là xoá hàng thật, xoá công việc khoán là xoá luôn các việc con
    # (không trông vào `ON DELETE CASCADE`, SQLite test không bật khoá ngoại).
    viec_phat_sinh: Mapped[list["ViecPhatSinh"]] = relationship(
        "ViecPhatSinh", back_populates="cong_viec_khoan", order_by="ViecPhatSinh.thu_tu",
        cascade="all, delete-orphan",
    )
    # CÁC TỔ làm việc này (17/09/2026) — cùng một việc ("Bế nổi") có thể do tổ Bế lẫn tổ Thành phẩm
    # làm, cùng đơn giá. `delete-orphan`: bỏ một tổ khỏi danh sách là xoá dòng nối.
    to_lam: Mapped[list["CongViecKhoanTo"]] = relationship(
        "CongViecKhoanTo", back_populates="cong_viec_khoan",
        order_by="CongViecKhoanTo.department_id", cascade="all, delete-orphan",
    )

    @property
    def department_ids(self) -> list[int]:
        """Id các tổ làm việc này — thứ mọi chỗ khớp "đầu việc của tổ X" đọc (`X in department_ids`)."""
        return [t.department_id for t in self.to_lam]

    @department_ids.setter
    def department_ids(self, ids: list[int]) -> None:
        """Thay TRỌN danh sách tổ. Giữ nguyên dòng nối của tổ còn trong danh sách (không
        xoá-rồi-chèn): cùng khoá chính `(piece_rate_id, department_id)`, xoá rồi chèn lại trong một
        lần flush là vấp thứ tự INSERT/DELETE của unit-of-work."""
        cu = {t.department_id: t for t in self.to_lam}
        self.to_lam = [cu.get(int(i)) or CongViecKhoanTo(department_id=int(i))
                       for i in dict.fromkeys(ids)]


class CongViecKhoanTo(Base):
    """Một TỔ làm được một công việc khoán — bảng nối `piece_rates` ↔ `departments`.

    `department_id` là soft-ref như mọi cột tổ khác (không FK cứng sang `departments`): tổ bị xoá thì
    dòng nối ở lại, form hiện "(không còn là tổ)" để người khai tự gỡ — xoá ngầm là mất dấu việc
    đó từng thuộc tổ nào.
    """

    __tablename__ = "cong_viec_khoan_to"

    piece_rate_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("piece_rates.id", ondelete="CASCADE"), primary_key=True
    )
    department_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    cong_viec_khoan: Mapped["PieceRate"] = relationship("PieceRate", back_populates="to_lam")


class ViecPhatSinh(Base):
    """Việc PHÁT SINH của một công việc khoán — vd "In 4 màu" có "Thay kẽm · 100 đ/bản".

    Thứ bậc chủ xưởng chốt: tổ → công đoạn → công việc khoán → việc phát sinh. Nên dòng này chỉ
    khai BA thứ (tên việc · đơn giá · đơn vị tính); tổ và công đoạn đọc ở công việc khoán cha.

    Đợt đầu CHỈ khai báo + hiển thị trong danh mục; sản xuất chưa đọc bảng này. Id của từng dòng
    được GIỮ qua các lần lưu (repo sửa tại chỗ theo id, không xoá-rồi-chèn lại) — lúc sản xuất ghi
    "thay kẽm · 7" thì trỏ vào id, đổi tên việc không làm mồ côi các lần ghi cũ.
    """

    __tablename__ = "cong_viec_khoan_phat_sinh"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    piece_rate_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("piece_rates.id", ondelete="CASCADE"), index=True, nullable=False
    )
    ten: Mapped[str] = mapped_column(String(255), nullable=False)
    don_gia: Mapped[float] = mapped_column(_MONEY, nullable=False)
    # MÃ danh mục `don_vi_do` (`kem`, `luot`) như `piece_rates.unit`. Khác cha ở chỗ service CHẶN
    # mã ngoài danh mục: bảng mới, không có dòng đời cũ nào cần đỡ.
    don_vi: Mapped[str] = mapped_column(String(24), nullable=False)
    thu_tu: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    cong_viec_khoan: Mapped["PieceRate"] = relationship("PieceRate", back_populates="viec_phat_sinh")


# ⚠️ `PieceLeaderBonusBracket` (bảng `piece_leader_bonus_brackets`) GỠ 13/09/2026 cùng mg `0300`:
# bỏ hẳn thưởng/phạt tổ trưởng theo khoảng sản lượng × tỷ lệ lỗi KCS (bảng bậc, API, màn khai và
# cột lương `payroll_lines.thuong_to_truong`).
