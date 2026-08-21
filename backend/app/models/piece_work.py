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


class PieceLeaderBonusSetting(Base):
    """NGƯỠNG tối thiểu để xét thưởng/phạt tổ trưởng — mỗi tổ một dòng (chủ 30/07/2026).

    Chủ: *"ở đó mới có Tỷ lệ lỗi tới nhưng không biết nằm trong phạm vi sản lượng là bao nhiêu"*.

    **Vì sao cần:** bảng bậc chỉ có MỘT chiều là tỷ lệ lỗi, nên tổ làm rất ít và tổ làm rất nhiều
    được đối xử như nhau. Tệ hơn: làm càng ít thì tỷ lệ lỗi càng vô nghĩa — hỏng 2 tờ trên 20 tờ đã
    là 10%, đủ rơi xuống bậc phạt nặng nhất dù thực tế chẳng làm được gì.

    Luật:
        sản lượng của tổ  <  ngưỡng  ⇒  KHÔNG thưởng, KHÔNG phạt, bất kể tỷ lệ lỗi
        sản lượng của tổ  ≥  ngưỡng  ⇒  áp bảng bậc như thường (">=", KHÔNG phải ">")
        ngưỡng = 0                   ⇒  KHÔNG gác
        chưa biết sản lượng (None)   ⇒  COI NHƯ dưới ngưỡng (fail-closed)

    Vế cuối là chủ ý: chưa xác nhận được tổ có đạt ngưỡng hay không thì không được phát thưởng.

    Ngưỡng là **một con số trần, KHÔNG kèm đơn vị** (chủ chốt 30/07/2026: *"Đơn vị bỏ đi"*).
    ⚠️ Hệ quả cho người nối nguồn sản lượng sau này: cộng **toàn bộ** sản lượng của tổ trong kỳ rồi
    so, không lọc theo đơn vị. Tổ nào làm nhiều loại việc khác đơn vị (vd vừa "m²" vừa "tờ") thì con
    số cộng lại không có ý nghĩa vật lý — đó là đánh đổi đã biết, không phải sơ suất.

    ⚠️ Cùng số phận với bảng bậc: **CHƯA RA TIỀN** cho tới khi dựng lại nguồn sản lượng — chưa có
    nguồn nào báo sản lượng nên mọi tổ đều rơi vào nhánh fail-closed. Khai ở đây là chuẩn bị trước.

    Bảng riêng chứ không thêm cột vào `piece_leader_bonus_brackets`: ngưỡng là MỘT luật cho cả bộ
    bậc, nhét vào từng bậc thì mỗi dòng mang một bản sao và sớm muộn lệch nhau.
    """

    __tablename__ = "piece_leader_bonus_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Soft-ref `departments.id` (không FK cứng, giống `piece_rates` và bảng bậc). UNIQUE: mỗi tổ
    # đúng một ngưỡng — hai dòng cho cùng một tổ thì không ai biết dòng nào đang có hiệu lực.
    department_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    # Sản lượng tối thiểu trong kỳ. `0` = không gác. Không kèm đơn vị — xem docstring.
    min_output_qty: Mapped[float] = mapped_column(
        Numeric(14, 2), nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
