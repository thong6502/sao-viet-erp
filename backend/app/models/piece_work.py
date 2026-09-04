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

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

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
    """Đơn giá khoán: 1 công việc của 1 tổ với đơn vị + đơn giá.

    Từ 17/08/2026 đây là DANH MỤC "Công việc khoán" trong Cấu hình danh mục (`loai =
    "cong_viec_khoan"`, quyền `dm_cong_viec_khoan`) — cùng nền với 10 màn kia, nên có mã tự sinh,
    nhật ký từng dòng và luật xoá chung. Nó vẫn là bảng giá mà Lương khoán tra, chỉ khác chỗ KHAI:
    trước nằm trong một tab của màn Lương, nay đứng cùng chỗ với Công đoạn · Đơn vị · Bù hao, vì
    bên dùng nó nhiều nhất là SẢN XUẤT (bước lệnh chọn đầu việc khoán), không phải kế toán lương.
    """

    __tablename__ = "piece_rates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Tổ khoán (vd 'to_boi', 'to_can_phu', 'to_cat', 'may_in_5mau'). Trục gom + tra.
    group_name: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    # Tổ (departments.id) sở hữu đơn giá — khai đơn giá NGAY trong Cấu hình lương của tổ.
    # Nullable: đơn giá cũ/chưa gắn tổ vẫn hợp lệ; group_name giữ làm nhãn hiển thị.
    department_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
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
    # Vì sao gắn vào ĐẦU VIỆC chứ không vào đơn vị: "Bắt tay + vào keo" khoán đ/`cuốn` mà bước đếm
    # bằng `tay` — cầu `tay → cuốn` không có trong bảng cặp nên đầu việc này CHƯA BAO GIỜ ra tiền.
    # Khai `sl_ra` ở đây là xong, mà không kéo theo mọi việc khác cũng đo bằng `cuốn`.
    #
    # ⚠️ GHÌM vào bước lệnh: `khoan_snapshot()` chép chuỗi này vào `khoan_json` cạnh `don_gia`/
    # `don_vi`. Lệnh đã phát đọc ảnh chụp — xưởng sửa cách đo về sau KHÔNG được xê dịch tiền công
    # của lệnh đang chạy. Muốn bước cũ ăn công thức mới thì chọn lại đầu việc.
    cong_thuc_luong: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Còn dùng hay đã ngừng. Xoá một đơn giá đang được định mức đầu việc trỏ tới là làm mồ côi dữ
    # liệu, nên luồng xoá chung chỉ tắt cờ này khi còn nơi dùng (xem `danh_muc_tham_chieu`).
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class PieceLeaderBonusBracket(Base):
    """Bậc THƯỞNG/PHẠT tổ trưởng theo KHOẢNG SẢN LƯỢNG × TỶ LỆ HÀNG LỖI (chủ 04/09/2026).

    Chủ: *"nó phải sét 2 điều kiện 1 là khoảng sản lượng, 2 là tỷ lệ lỗi"*.

    Mỗi TỔ một bộ bậc riêng (`department_id`) — khác `late_penalty_brackets`/`pit_tax_brackets`
    vốn là bảng toàn công ty. Một dòng = một ô của lưới (khoảng sản lượng × trần tỷ lệ lỗi):

        sl_tu   sl_den   up_to_defect_pct   rate_pct
            0    5 000                  5      +5,00
            0    5 000               NULL      −5,00
        5 000   10 000                  3      +7,00
        5 000   10 000                 20      −8,00
        5 000   10 000               NULL     −15,00
       10 000     NULL                  3     +10,00
       10 000     NULL               NULL     −15,00

    Cách tra (xem `PieceWorkService.leader_bonus_pct`): lọc các dòng có `sl_tu < SL <= sl_den`
    (`sl_den = NULL` là ∞) rồi trong nhóm đó lấy dòng ĐẦU TIÊN có `tỷ lệ lỗi <= up_to_defect_pct`
    (`NULL` = ∞, phải nằm cuối nhóm). Ranh giới `<` ... `<=` lấy ĐÚNG quy ước bậc số lượng của
    `services/bu_hao_engine.py` — hai bảng bậc cùng hình dạng mà tra ngược nhau là bẫy chết người.

    Tiền = **sản lượng × rate_pct% × đơn giá khoán của đầu việc**, cộng/trừ vào lương của MỘT
    người: tổ trưởng (`departments.head_user_id`). Không chia cho cả tổ.

    ĐÃ NỐI VÀO LUỒNG (04/09/2026): `services/san_xuat/thuong_to_truong.py` tra bảng này lúc ĐÓNG
    NHÓM thành phẩm rồi ghi một dòng `san_xuat_thuong_to_truong`, từ đó chảy vào cột
    `payroll_lines.thuong_to_truong`. Sản lượng lấy từ phân bổ ĐÃ CHỐT của tổ trong nhóm, tỷ lệ lỗi
    lấy từ phiếu KCS (`accepted`/`recorded`). Tổ KHÔNG khai bậc ⇒ không có dòng nào, không lỗi.
    """

    __tablename__ = "piece_leader_bonus_brackets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Tổ sở hữu bộ bậc. Soft-ref `departments.id` (không FK cứng, giống `piece_rates`).
    department_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)                # thứ tự bậc 1..N
    # --- Điều kiện 1: KHOẢNG SẢN LƯỢNG của tổ trong lệnh (mg `0262`) --------------------------
    # Khoảng nửa mở `sl_tu < SL <= sl_den`, cùng tên cột và cùng quy ước với bậc bù hao.
    sl_tu: Mapped[float] = mapped_column(
        Numeric(14, 2), nullable=False, default=0, server_default="0"
    )
    # Trần sản lượng. NULL = ∞ (khoảng cao nhất).
    sl_den: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    # --- Điều kiện 2: TRẦN % HÀNG LỖI trong khoảng sản lượng đó -------------------------------
    # NULL = "trở lên" — đúng MỘT dòng mỗi khoảng sản lượng và phải ở cuối khoảng.
    up_to_defect_pct: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    # % nhân với (sản lượng × đơn giá khoán). DƯƠNG = thưởng · ÂM = phạt. Gõ nhầm dấu là đảo ngược.
    rate_pct: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


# ⚠️ `PieceLeaderBonusSetting` (bảng `piece_leader_bonus_settings`, cột `min_output_qty`) GỠ ngày
# 04/09/2026 cùng mg `0262`. Nó là cửa chặn "sản lượng cả kỳ dưới X thì không xét" — sinh ra vì
# bảng bậc chỉ có MỘT chiều là tỷ lệ lỗi. Nay chính bảng bậc mang khoảng sản lượng, nên khoảng
# thấp nhất khai `rate_pct = 0` đã gánh đúng việc đó, ngay trong bảng người dùng đang nhìn.
