"""Danh mục KHUÔN & KHUNG — kho dụng cụ dùng chung của xưởng (master data nhẹ).

Mỗi con dao làm riêng cho hình của 1 ấn phẩm; đơn lặp lại thì lôi dao cũ ra dùng. Khai để TÌM LẠI:
mã / tên ấn phẩm / khách / loại / số kệ / ngày làm / tình trạng / ghi chú.

Từ 16/08/2026 (mg 0205) danh mục này ĐƯỢC NỐI: bước của lệnh sản xuất trỏ vào đây qua
`lsx_cong_doan.khuon_be_id`. Người cấu hình lệnh chọn "dùng dao có sẵn" (lọc theo khách + loại) hoặc
"làm dao mới" — nhánh sau tạo thẳng một dòng ở đây với `tinh_trang='dang_dat_lam'`. Đó là lý do hai
cột `khach_hang_id` + `loai` phải có: không lọc được thì ô chọn bày cả kho, người ta tìm không ra
rồi đặt làm con dao đã có.

Tên bảng vẫn là `khuon_be` (và quyền vẫn là module `khuon_be`) dù nay chứa cả khuôn ép nhũ — đổi
tên bảng/quyền là mọi vai mất sạch quyền màn này. Chỉ nhan đề trên màn đổi thành "Khuôn".
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, true as sa_true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base

# Tình trạng khuôn — record-only (con người phán, máy chỉ ghi nhận).
# `dang_dat_lam` (mg 0177): khuôn CHƯA có trong tay, đang đặt thợ làm. Đi kèm `ngay_ve_du_kien` —
# ngày đó hiện ngay tại bước dùng khuôn ở lệnh sản xuất, để người xếp việc biết chưa chạy được.
TINH_TRANG = ("dang_dung", "dang_dat_lam", "hong", "thanh_ly")

# Loại dụng cụ (mg 0205; thêm `khung_lua` 04/09/2026 — khung lụa cũng lưu kho dùng lại như khuôn
# bế, nên nó thuộc về đây chứ không phải vật tư tiêu hao). DÙNG CHUNG bộ mã với
# `cong_doan.TOOLING_TYPE` — ô chọn khuôn ở bước lệnh lọc bằng cách so thẳng
# `cong_doan.tooling_type == khuon_be.loai`, hai bộ mã lệch nhau là lọc ra rỗng. Đó đúng là lỗi
# khung lụa mắc suốt từ trước: công đoạn khai được loại đó mà kho không nhận, nên bước lụa mở ô
# chọn ra RỖNG và bấm "làm dao mới" thì service ném 400.
LOAI_KHUON = ("khuon_be", "khuon_ep", "khung_lua")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class KhuonBe(Base):
    """1 dòng = 1 khuôn bế đã khai báo (vd khuôn hộp bánh của khách A)."""

    __tablename__ = "khuon_be"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ma: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)  # KB-####
    ten: Mapped[str] = mapped_column(String(200), nullable=False)            # tên khuôn / ấn phẩm áp dụng
    khach_hang_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("customers.id"), index=True, nullable=True
    )
    # Bế hay ép nhũ. Thiếu nó thì bước "Ép nhũ" mở ô chọn ra thấy cả dao bế — chọn nhầm, tới máy
    # mới biết. Nullable: 6 dòng có sẵn từ trước chưa ai phân loại, ép NOT NULL là phải đoán hộ.
    loai: Mapped[str | None] = mapped_column(String(16), index=True, nullable=True)
    so_ke: Mapped[str | None] = mapped_column(String(120), nullable=True)    # số kệ / vị trí lưu ← lõi
    tinh_trang: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="dang_dung", default="dang_dung"
    )  # dang_dung|dang_dat_lam|hong|thanh_ly
    # NGÀY CÓ KHUÔN (dự kiến) — ngày dao nằm trong tay xưởng, BẤT KỂ đường nào: thuê ngoài thì là
    # ngày về, xưởng tự làm thì là ngày làm xong. Chỉ có nghĩa với `tinh_trang='dang_dat_lam'`.
    #
    # Tên cột giữ nguyên `ngay_ve_du_kien` (mg 0177) dù nhãn trên màn là "Ngày có khuôn": đổi tên
    # cột là một migration + rà mọi nơi đọc, đổi lấy một chuỗi người dùng không bao giờ nhìn thấy.
    # ⚠️ ĐỪNG đọc chữ "về" ở đây thành "chỉ dành cho hàng thuê ngoài" — xưởng tự làm dùng chung ô.
    ngay_ve_du_kien: Mapped[date | None] = mapped_column(Date, nullable=True)
    ghi_chu: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # `lazy="joined"` chứ KHÔNG tra tên khách trong property: màn danh mục trả 20 dòng/trang, tra
    # từng dòng là 20 query thừa mỗi lần mở màn (N+1). Quan hệ many-to-one nên JOIN không nhân dòng.
    khach_hang = relationship("Customer", lazy="joined")

    @property
    def khach_hang_ten(self) -> str | None:
        """Tên khách để bày ra màn — `KhuonBeRow` đọc được nhờ `from_attributes=True`."""
        return self.khach_hang.name if self.khach_hang is not None else None

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_true(), default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
