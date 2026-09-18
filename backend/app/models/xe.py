"""Danh mục XE giao hàng và MỨC KHOÁN KM — hai bảng, một nghề.

Chốt 12/09/2026 (xem `docs/prd-khoan-km-giao-hang.md` §11):

    Mức khoán km  ──1──┬──n──  Xe  ──1──n──  Chuyến giao
    (bảng bậc giá)     │        (biển số)     (tra bậc theo mức của xe)

* **Mức** giữ BẢNG BẬC GIÁ và có tên riêng ("Xe 2 tấn", "Xe 5 tấn"). Cần một giá khác thì tạo
  MỨC MỚI, không sửa mức đang có — mức đang có là của những xe khác.
* **Xe** chỉ giữ DANH TÍNH (biển số, tải trọng) và TRỎ vào một mức.

Vì sao không gắn bảng bậc thẳng vào từng xe: đo `SAN LUONG T08.2026.xls` thì xưởng có 4 xe nhưng
chỉ HAI thang giá — xe 2,5T và hai xe 3,5T dùng CHUNG một thang, xe 5 tấn dùng thang bằng thang
thường × 1,1. Gắn thẳng vào xe là bắt khai ba bảng giống hệt nhau, rồi tăng giá quên một bảng là
đẻ lại đúng cái lỗi đang phải sửa: một xe tụt lại ở giá cũ, vẫn ra tiền nên không ai thấy.

Vì sao Xe không khai vào `tai_san`: hiện KHÔNG theo dõi khấu hao xe — `tai_san` không có chiếc
nào. Dựng cả bộ tài sản chỉ để lấy chỗ ghi biển số là đi vòng.

Xe KHÔNG gắn cứng với tài xế: vai tài xế/phụ xe do ô thả người vào quyết định (PRD §3b), khai vào
hồ sơ là đẻ nguồn sự thật thứ hai.
"""
from __future__ import annotations

from datetime import datetime, timezone

from decimal import Decimal

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, Numeric, String, true as sa_true,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MucKhoanKm(Base):
    """Một MỨC khoán km = một bảng bậc giá, dùng chung cho nhiều xe.

    Là cấu hình CHUNG toàn công ty, KHÔNG thuộc phòng ban nào (chủ chốt 14/09/2026). Bảng bậc nằm
    ở `muc_khoan_km_bac` — xem ghi chú ở lớp đó vì sao phải tách khỏi `delivery_km_brackets`.
    """

    __tablename__ = "muc_khoan_km"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    #: Tên mức — KHOÁ NGHIỆP VỤ, và là thứ duy nhất người dùng cần khai. Đặt theo tải trọng cho
    #: dễ nhớ ("Xe 2 tấn"); hệ KHÔNG suy gì từ chữ trong tên, cũng không giữ thêm cột tải trọng
    #: nào cho mức — một cột nữa chỉ để lặp lại thứ cái tên đã nói.
    ten: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    ghi_chu: Mapped[str | None] = mapped_column(String(500), nullable=True)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_true(), default=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class MucKhoanKmBac(Base):
    """Một BẬC trong bảng giá của một mức: km chuyến ≤ `up_to_km` thì ăn `don_gia`.

    ⭐ Bảng RIÊNG, KHÔNG mang `department_id` (14/09/2026). Trước đó bậc của mức nằm chung bảng
    `delivery_km_brackets` với bậc cấp phòng, và bảng đó bắt buộc `department_id` kèm FK xoá dây
    chuyền. Mức thì toàn công ty nhưng từng dòng bậc lại treo vào phòng ban lưu nó — xoá phòng là
    cuốn luôn bảng giá của mọi mức lưu từ màn phòng đó, mức còn tên mà hết giá. Bậc thuộc về MỨC,
    xoá mức thì bậc đi theo; ngoài ra không ai được kéo nó đi.

    Tra bậc: bậc đầu tiên (theo `seq`) có `km ≤ up_to_km` thắng; `up_to_km` NULL = bậc cao nhất
    (∞), chỉ một và ở cuối. Toàn km × đơn giá của MỘT bậc, không cộng dồn từng đoạn (§2.1).
    """

    __tablename__ = "muc_khoan_km_bac"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    muc_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("muc_khoan_km.id", ondelete="CASCADE"), index=True, nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)                    # thứ tự bậc 1..N
    up_to_km: Mapped[int | None] = mapped_column(Integer, nullable=True)         # trần KM; NULL = ∞
    don_gia: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)     # đồng/km


class Xe(Base):
    """Một chiếc xe giao hàng. `ma` = BIỂN SỐ."""

    __tablename__ = "xe"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    #: BIỂN SỐ, khoá nghiệp vụ. Nền danh mục chỉ chuẩn hoá hoa/thường, KHÔNG bóc dấu chấm/gạch —
    #: `51K-774.04` và `51K-77404` là hai mã khác nhau, nên lúc khai phải thống nhất một cách viết.
    ma: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    #: Tên gọi trong xưởng ("Xe a Việt") — người phân chuyến nhớ theo tên này, không nhớ biển số.
    ten: Mapped[str] = mapped_column(String(150), nullable=False)
    tai_trong: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    #: XE NÀY ĂN MỨC NÀO — BẮT BUỘC khi tạo/sửa xe (chủ chốt 14/09/2026, chặn ở `XeService`).
    #: Cột để nullable chỉ vì không ALTER ràng buộc trên bảng đã dựng; luật nằm ở service. Trước
    #: 14/09 xe được để trống và âm thầm ăn đơn giá phẳng 3.600đ/km mà không màn nào hiện số đó.
    muc_khoan_km_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("muc_khoan_km.id"), index=True, nullable=True
    )
    ghi_chu: Mapped[str | None] = mapped_column(String(500), nullable=True)
    #: Tắt = xe đã ngưng: không hiện ở ô chọn chuyến MỚI, nhưng chuyến cũ vẫn giữ tên xe.
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_true(), default=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
