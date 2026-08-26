"""Giao hàng — Yêu cầu giao hàng · Lần giao · Đề nghị xuất hàng (docs/prd-giao-hang.md).

SÁU bảng, tất cả đều MỚI ⇒ `create_all` tự dựng, KHÔNG cần migration tạo bảng (migration chỉ để
ALTER bảng cũ). Migration của phân hệ này chỉ làm hai việc: khoá module `giao_hang` + hai cột quyền
mới trên `role_permissions`.

Hai luật xương sống của bản thiết kế — sửa là hỏng cả phân hệ:

* **HAI TẦNG TRẠNG THÁI** (PRD §7). Yêu cầu chỉ LƯU hai trạng thái nó thật sự sở hữu
  (`cho_len_ke_hoach`, `da_huy`); "đang thực hiện" / "đã giao đủ" là HÀM tính từ các lần giao —
  không có cột. Lưu hai chỗ là hai chỗ lệch nhau, mà tầng dưới có 8 trạng thái × 4 kết quả thì
  quên cập nhật ngược một nhánh là yêu cầu treo mãi ở "đang thực hiện".
* **"ĐÃ GIAO BAO NHIÊU" LÀ `SUM`** (PRD quyết định #5). Cộng từ `delivery_trip_lines` của các lần
  `thanh_cong`/`giao_thieu`. KHÔNG có cột `order_lines.delivered_qty` — repo không có Alembic, một
  cột cộng dồn lệch là không có đường phát hiện lẫn đường sửa lại êm.

ĐI QUA KHO NHƯ MỌI THỨ KHÁC: hàng ra khỏi kho phải có phiếu kho, giao khách không ngoại lệ.
Giao hàng KHÔNG dựng chứng từ riêng — nó lập một `stock_requests` loại XUẤT bình thường, kho
lập phiếu · ghi sổ · trừ tồn bằng luồng sẵn có. Nối hai bên bằng soft-ref
`stock_requests.delivery_trip_id` (mg 0201), cùng khuôn `purchase_delivery_id` của Mua hàng.

Bản đầu dựng bảng `delivery_issue_requests` song song với nút *Duyệt* riêng — SAI, và chủ chốt
bắt ba lần mới sửa (19/08/2026). Kho không có bước duyệt (bỏ 06/08/2026), họ LẬP PHIẾU.

Portable SQLite ↔ Postgres: integer PK, string/date/JSON-free, timestamp default ở tầng Python.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base

# --- Trạng thái YÊU CẦU (tầng 1) — chỉ hai giá trị được LƯU -----------------------------------
# "Đang thực hiện" và "Đã giao đủ" KHÔNG có ở đây vì chúng là hàm; xem `delivery_service`.
YC_CHO_LEN_KE_HOACH = "cho_len_ke_hoach"
YC_DA_HUY = "da_huy"
YEU_CAU_STATUSES = (YC_CHO_LEN_KE_HOACH, YC_DA_HUY)

# --- Trạng thái LẦN GIAO (tầng 2) — tám giá trị, một chiều -------------------------------------
LG_DA_LEN_KE_HOACH = "da_len_ke_hoach"
LG_DANG_CHUAN_BI = "dang_chuan_bi"      # KHO ĐÃ DUYỆT đề nghị xuất hàng → đang soạn
LG_DA_LAY_HANG = "da_lay_hang"          # TÀI XẾ tự bấm khi đã cầm được hàng
LG_DANG_GIAO = "dang_giao"
LG_THANH_CONG = "thanh_cong"
LG_GIAO_THIEU = "giao_thieu"
# ⚠️ NGƯNG DÙNG từ 22/08/2026 (PRD một-yêu-cầu-một-chuyến). Giữ hằng số để đọc lại dòng cũ,
# KHÔNG cho ghi mới: "hẹn lại" là trạng thái treo — chuyến chưa xong mà cũng không kết thúc, hàng
# nằm trên xe không biết tới bao giờ. Nay khách hẹn lại = thất bại lần này, TRẢ HÀNG VỀ, lập yêu
# cầu mới cho ngày hẹn. Nhờ vậy lúc nào cũng biết hàng đang ở đâu.
LG_HEN_LAI = "hen_lai"
LG_THAT_BAI = "that_bai"
LG_DANG_TRA_HANG = "dang_tra_hang"
LG_DA_TRA_HANG = "da_tra_hang"
LG_DA_HUY = "da_huy"
LAN_GIAO_STATUSES = (
    LG_DA_LEN_KE_HOACH, LG_DANG_CHUAN_BI, LG_DA_LAY_HANG, LG_DANG_GIAO,
    LG_THANH_CONG, LG_GIAO_THIEU, LG_HEN_LAI, LG_THAT_BAI, LG_DANG_TRA_HANG, LG_DA_TRA_HANG,
    LG_DA_HUY,
)
# Lần giao còn "sống" — yêu cầu đang có một trong các trạng thái này thì KHÔNG lên kế hoạch mới
# được (nghiệm thu #3: một yêu cầu chỉ có MỘT lần giao đang hoạt động).
LAN_GIAO_DANG_CHAY = (
    LG_DA_LEN_KE_HOACH, LG_DANG_CHUAN_BI, LG_DA_LAY_HANG, LG_DANG_GIAO, LG_DANG_TRA_HANG,
)
# Lần giao ĐÃ CỘNG vào "đã giao" của đơn. `giao_thieu` cũng cộng — cộng phần THỰC NHẬN.
LAN_GIAO_CO_HANG_DEN_TAY = (LG_THANH_CONG, LG_GIAO_THIEU)
# Quản lý còn sửa/huỷ được kế hoạch: chỉ khi tài xế CHƯA cầm hàng.
LAN_GIAO_SUA_DUOC = (LG_DA_LEN_KE_HOACH, LG_DANG_CHUAN_BI)

# Hướng xử lý hàng sau một lần giao thất bại (PRD §8).
XU_LY_TRA_VE = "tra_ve"
# ⚠️ NGƯNG DÙNG từ 22/08/2026 — giữ hằng số để đọc dòng cũ, KHÔNG còn là lựa chọn hợp lệ.
# "Chờ giao lại" giữ hàng trên xe trong khi sổ kho ghi đã xuất; đó chính là chỗ che mất lỗi
# "trả hàng về không vào sổ" suốt thời gian qua.
XU_LY_CHO_GIAO_LAI = "cho_giao_lai"
#: Hướng xử lý CHO PHÉP KHAI — chỉ còn trả hàng về kho.
HUONG_XU_LY = (XU_LY_TRA_VE,)

# Ngưỡng cảnh báo số km một chuyến (PRD §8) — KHÔNG chặn, chỉ bắt xác nhận lại. Lỗi hay gặp là gõ
# nhầm 180 thành 1800, chứ không phải gõ số 0.
KM_CANH_BAO = 500


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DeliveryRequest(Base):
    """Yêu cầu giao hàng — MỘT ĐỢT giao của một đơn hàng bán. Một đơn đẻ nhiều yêu cầu."""

    __tablename__ = "delivery_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # YCGH-yymmdd-XXXX — cùng khuôn `YCMH-` bên Thu mua (purchase_service._new_department_request_code).
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)

    order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("orders.id"), index=True, nullable=False
    )
    # Chép từ đơn để lọc/hiện nhanh; đơn không đổi khách sau khi chốt nên không sợ lệch.
    customer_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    # Phòng của người tạo — trục lọc phạm vi `department` (RBAC data-scope).
    department_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("departments.id"), index=True, nullable=True
    )

    ngay_can_giao: Mapped[date] = mapped_column(Date, nullable=False)

    # SNAPSHOT nơi giao (PRD §5) — điền sẵn từ `orders.delivery_*` / sổ địa chỉ khách, sửa được,
    # rồi ĐÔNG LẠI. Sửa địa chỉ đơn tháng sau thì phiếu giao cũ vẫn phải giữ địa chỉ đã giao THẬT.
    # Cùng khuôn `order_lines.unit_price_snapshot`.
    dia_chi: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    nguoi_nhan: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sdt_nguoi_nhan: Mapped[str | None] = mapped_column(String(30), nullable=True)
    ghi_chu: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    trang_thai: Mapped[str] = mapped_column(
        String(20), index=True, nullable=False,
        server_default=YC_CHO_LEN_KE_HOACH, default=YC_CHO_LEN_KE_HOACH,
    )
    ly_do_huy: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    lines: Mapped[list["DeliveryRequestLine"]] = relationship(
        "DeliveryRequestLine", back_populates="request",
        cascade="all, delete-orphan", order_by="DeliveryRequestLine.id",
    )
    trips: Mapped[list["DeliveryTrip"]] = relationship(
        "DeliveryTrip", back_populates="request",
        cascade="all, delete-orphan", order_by="DeliveryTrip.lan_thu",
    )

    __table_args__ = (
        CheckConstraint(
            "trang_thai IN ('cho_len_ke_hoach','da_huy')", name="chk_delivery_requests_trang_thai"
        ),
    )


class DeliveryRequestLine(Base):
    """1 dòng hàng của ĐỢT NÀY. `qty` là số YÊU CẦU giao, không phải số đã giao."""

    __tablename__ = "delivery_request_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("delivery_requests.id", ondelete="CASCADE"), index=True, nullable=False
    )
    order_line_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("order_lines.id"), index=True, nullable=False
    )
    qty: Mapped[int] = mapped_column(
        Integer, CheckConstraint("qty > 0", name="chk_delivery_request_lines_qty"), nullable=False
    )

    # MẶT HÀNG KHO của dòng này — cặp `(hang_loai, hang_id)` trỏ `giay_nguyen`/`vat_tu_in_an`,
    # đúng khoá mà `stock_request_lines` đòi.
    #
    # Vì sao phải có: dòng đơn hàng chỉ mang CHỮ TỰ DO ("Hộp giấy đựng bánh 200g — in offset 4
    # màu"), không trỏ danh mục nào. Không lưu mắt xích này thì mỗi lần gửi yêu cầu xuất kho lại
    # phải gõ tay lại mặt hàng — mời gõ sai, và sai thì kho xuất nhầm hàng.
    #
    # Chọn MỘT LẦN lúc Bán hàng lập yêu cầu giao (họ biết rõ sản phẩm), sau đó mọi bước sau
    # ĐIỀN TỰ ĐỘNG và KHOÁ. Nullable vì dòng gieo trước mg 0202 chưa có.
    hang_loai: Mapped[str | None] = mapped_column(String(8), nullable=True)
    hang_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dvt: Mapped[str | None] = mapped_column(String(24), nullable=True)

    request: Mapped["DeliveryRequest"] = relationship("DeliveryRequest", back_populates="lines")

    __table_args__ = (
        UniqueConstraint("request_id", "order_line_id", name="uq_delivery_request_line"),
    )


class DeliveryTrip(Base):
    """LẦN GIAO — nơi mọi trạng thái, số km và lịch sử thật sự sống (PRD §7 tầng 2).

    Giao lại sau thất bại KHÔNG nhân đôi yêu cầu: chỉ thêm một hàng ở đây với `lan_thu` kế tiếp.
    """

    __tablename__ = "delivery_trips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("delivery_requests.id", ondelete="CASCADE"), index=True, nullable=False
    )
    lan_thu: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Tài xế = `employees` (PRD quyết định #2). KHÔNG dựng bảng `drivers` riêng — trạng thái
    # "đang nghỉ" chỉ đọc được nếu tài xế là nhân viên thật (đơn nghỉ đã duyệt + chấm công).
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employees.id"), index=True, nullable=False
    )
    # Phụ xe — TUỲ CHỌN, tối đa MỘT người (mg 0231). Chủ chốt "1 tài xế 1 phụ xe cho nó dễ", nên
    # cột nullable chứ không đẻ bảng kíp xe: bảng phụ chỉ đáng khi số người thay đổi được.
    # Vai trò do Ô THẢ NGƯỜI VÀO quyết định, không phải thuộc tính của người — hôm nay lái, mai đi
    # phụ là chuyện thường, khai ở hồ sơ là đẻ ra nguồn sự thật thứ hai lệch với thực tế chuyến.
    phu_xe_employee_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id"), index=True, nullable=True
    )

    gio_lay_hang: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    gio_du_kien_giao: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ghi_chu_phan_cong: Mapped[str | None] = mapped_column(String(500), nullable=True)

    trang_thai: Mapped[str] = mapped_column(
        String(20), index=True, nullable=False,
        server_default=LG_DA_LEN_KE_HOACH, default=LG_DA_LEN_KE_HOACH,
    )

    # --- Kết quả (điền khi đóng chuyến) ---
    # `km >= 0`, KHÔNG phải `> 0`: khách không nghe máy khi xe chưa lăn bánh thì 0 km là số THẬT.
    km: Mapped[int | None] = mapped_column(
        Integer, CheckConstraint("km IS NULL OR km >= 0", name="chk_delivery_trips_km"),
        nullable=True,
    )
    thoi_gian_ket_thuc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    nguoi_nhan_thuc_te: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ly_do_that_bai: Mapped[str | None] = mapped_column(String(500), nullable=True)
    huong_xu_ly: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ngay_hen_lai: Mapped[date | None] = mapped_column(Date, nullable=True)
    ghi_chu_ket_qua: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Khoán km: BA SỐ CHỤP LẠI lúc ghi kết quả (mg 0231) ------------------------------------
    # Chụp là bắt buộc. Đọc thẳng đơn giá/tỷ lệ của phòng ban lúc TÍNH LƯƠNG thì tháng sau chủ
    # chỉnh một con số là bảng lương đã chốt của mọi tháng trước đổi theo — đúng bài học
    # `orders.commission_pct` ngày 21/08/2026.
    #
    # NULL = chuyến chạy TRƯỚC khi có tính năng ⇒ engine bỏ qua, không tự đẻ tiền ngược cho quá
    # khứ. Khác hẳn 0: 0 là "đã chụp, và bằng 0" (phòng ban chưa khai đơn giá).
    don_gia_km: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    pct_tai_xe: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    pct_phu_xe: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)

    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    request: Mapped["DeliveryRequest"] = relationship("DeliveryRequest", back_populates="trips")
    lines: Mapped[list["DeliveryTripLine"]] = relationship(
        "DeliveryTripLine", back_populates="trip",
        cascade="all, delete-orphan", order_by="DeliveryTripLine.id",
    )

    __table_args__ = (
        UniqueConstraint("request_id", "lan_thu", name="uq_delivery_trip_lan_thu"),
    )


class DeliveryTripLine(Base):
    """Số THỰC NHẬN từng dòng của một lần giao — nguồn duy nhất của "đã giao bao nhiêu".

    ĐIỀN LUÔN LUÔN khi chuyến có kết quả `thanh_cong` hoặc `giao_thieu`; thành công thì bằng đúng
    số yêu cầu. MỘT LUẬT, KHÔNG RẼ NHÁNH — chỉ điền khi giao thiếu là tạo hai đường tính, mà hai
    đường thì sớm muộn lệch (PRD §13).
    """

    __tablename__ = "delivery_trip_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trip_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("delivery_trips.id", ondelete="CASCADE"), index=True, nullable=False
    )
    order_line_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("order_lines.id"), index=True, nullable=False
    )
    # 0 là hợp lệ: khách nhận dòng A, từ chối dòng B trong cùng chuyến.
    qty_giao: Mapped[int] = mapped_column(
        Integer, CheckConstraint("qty_giao >= 0", name="chk_delivery_trip_lines_qty"),
        nullable=False,
    )

    trip: Mapped["DeliveryTrip"] = relationship("DeliveryTrip", back_populates="lines")

    __table_args__ = (
        UniqueConstraint("trip_id", "order_line_id", name="uq_delivery_trip_line"),
    )


class DeliveryStatusHistory(Base):
    """Lịch sử đổi trạng thái của LẦN GIAO (nghiệm thu #10). Chỉ ghi, không sửa, không xoá."""

    __tablename__ = "delivery_status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trip_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("delivery_trips.id", ondelete="CASCADE"), index=True, nullable=False
    )
    tu_trang_thai: Mapped[str | None] = mapped_column(String(20), nullable=True)
    den_trang_thai: Mapped[str] = mapped_column(String(20), nullable=False)
    nguoi_thao_tac_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    luc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    ghi_chu: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ly_do: Mapped[str | None] = mapped_column(String(500), nullable=True)


class DeliveryTripAttachment(Base):
    """File MINH CHỨNG của một chuyến giao — ảnh hoặc PDF (chủ chốt 22/08/2026).

    Việc thật: hàng đi kèm hoá đơn. Trước lúc đi thì đính hoá đơn để tài xế cầm theo; giao xong
    thì chụp lại tờ khách đã ký. Cả hai đều là file của CHUYẾN đó, nên một bảng là đủ — không
    tách "hoá đơn đi" với "biên nhận về", vì tách ra là bắt người dùng chọn loại trước khi tải,
    mà chọn sai thì phải xoá tải lại.

    Đính vào CHUYẾN chứ không vào yêu cầu: từ 22/08/2026 một yêu cầu chỉ có một chuyến nên hai
    chỗ là một, mà neo vào chuyến thì file đi cùng thứ có người ký nhận và có kết quả.

    Bytes nằm ở kho file dùng chung (`app/storage.py`), đọc lại qua `/api/files`; bảng này chỉ giữ
    metadata + đường dẫn — mirror `payment_receipt_attachments`.
    """

    __tablename__ = "delivery_trip_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trip_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("delivery_trips.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    uploaded_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class DeliveryKmBracket(Base):
    """Bậc đơn giá khoán km, THEO PHÒNG BAN (mg-free — create_all tự dựng bảng mới).

    Tra theo SỐ KM của một chuyến: bậc đầu tiên có `km ≤ up_to_km` → `don_gia`; `up_to_km` NULL =
    bậc cao nhất (từ đó trở lên). Mirror `late_penalty_brackets`.

    ⭐ CÁCH TÍNH: toàn bộ km của chuyến × đơn giá của MỘT bậc mà km rơi vào (chủ chốt 24/08/2026),
    KHÔNG cộng dồn từng đoạn. Chuyến 8 km, bậc 5–10km giá 20.000 ⇒ 8 × 20.000 = 160.000. Đây đúng
    cách bảng lương thật tính (đo 521 chặng: thành tiền = km × đơn giá một bậc).

    Vì sao THEO PHÒNG BAN chứ không toàn công ty như bảng thuế/phạt: đơn giá là thoả thuận của
    khối giao hàng, khai ngay trong màn Phòng ban nơi bật cờ `la_giao_hang` (chủ chốt vị trí này).
    Nhiều tổ giao hàng khác nhau có thể có bảng giá khác nhau.
    """

    __tablename__ = "delivery_km_brackets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    department_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("departments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)                    # thứ tự bậc 1..N
    up_to_km: Mapped[int | None] = mapped_column(Integer, nullable=True)         # trần KM; NULL = ∞
    don_gia: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)     # đồng/km
