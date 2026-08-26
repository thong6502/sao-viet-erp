"""Danh mục Giấy & Vật tư (Cấu hình danh mục).

- `ChungLoaiGiay`  — phân loại giấy (Couche/Ford/Bristol/Ivory/Duplex/Kraft…).
- `GiayNguyen`     — tờ giấy nguyên (khổ mua); ăn theo 1 Chủng loại giấy (`chung_loai_giay_id`).
- `GiayGiaVersion` — lịch sử giá của 1 Giấy. DI TÍCH: UI đã tắt (`hasVersions: false`) từ khi
                     đơn giá chuyển sang nhập per-phiếu; endpoint còn nhưng màn không gọi.
- `VatTuInAn`      — vật tư in ấn danh mục PHẲNG (mực/kẽm/hoá chất/màng/keo… chung 1 bảng, phân
                     biệt bằng TÊN): Mã · Tên · ĐVT · công thức · ghi chú. Không phân loại con, không tồn.

Danh mục CRUD thuần — chỉ khai CÔNG THỨC; đơn giá nhập ở phiếu tính giá (per-phiếu), engine
KHÔNG đọc `don_gia` tại danh mục.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean, Date, DateTime, Integer, JSON, Numeric, String, Text,
    false as sa_false,
    true as sa_true,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# `THO` còn dùng cho `GiayNguyen.tho` (thớ của TỪNG loại giấy) — ĐỪNG gỡ theo.
THO = ("canh_dai", "canh_ngan")

# MẶT HÀNG GỐC nằm ở HAI bảng với hai dãy id riêng, nên mọi nơi trỏ tới nó (kho, NCC) phải mang
# CẶP `(hang_loai, hang_id)` chứ không mang mỗi id. Khoá cặp thay vì hai cột `giay_id`/`vat_tu_id`
# rời: tồn kho phải GỘP NHÓM theo mặt hàng (`GROUP BY hang_loai, hang_id`), mà hai cột nullable thì
# mọi truy vấn gộp đều phải COALESCE và unique constraint phải tách làm hai.
HANG_GIAY = "giay"
HANG_VAT_TU = "vat_tu"
HANG_LOAI = (HANG_GIAY, HANG_VAT_TU)
# GỠ 2026-08-08: `DON_VI_GIA_GIAY` / `DON_VI_GIA_VAT_TU` — hai danh sách đơn vị CỨNG. Đơn vị giờ
# lấy từ danh mục `don_vi_do` (nguồn duy nhất, dùng chung cho Kho · NCC · khoán · tính giá); thêm
# đơn vị là việc khai ở màn Đơn vị & quy đổi, không phải sửa code.


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ChungLoaiGiay(Base):
    """Chủng loại giấy — phân loại (Couche/Ford/Bristol/Ivory/Duplex/Kraft…). Giấy ăn theo đây."""

    __tablename__ = "chung_loai_giay"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ma: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    ten: Mapped[str] = mapped_column(String(150), nullable=False)
    mo_ta: Mapped[str | None] = mapped_column(String(500), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_true(), default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class GiayNguyen(Base):
    """Tờ giấy nguyên (khổ lớn để mua) — ăn theo 1 Chủng loại giấy."""

    __tablename__ = "giay_nguyen"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ma: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    ten: Mapped[str] = mapped_column(String(150), nullable=False)
    chung_loai_giay_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)  # → chung_loai_giay.id
    kho_dai: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)   # mm; 0 = cuộn/khổ mở
    kho_rong: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)  # mm; 0 = cuộn/khổ mở
    gsm: Mapped[int] = mapped_column(Integer, nullable=False)       # định lượng
    caliper_micron: Mapped[int | None] = mapped_column(Integer, nullable=True)  # độ dày (spine/creep; ≠ gsm)
    tho: Mapped[str | None] = mapped_column(String(12), nullable=True)          # canh_dai|canh_ngan
    # ĐƠN VỊ GỐC của mặt hàng — mã trong `don_vi_do`, KHÔNG còn là enum cứng ở frontend. Tồn kho
    # cộng dồn theo đơn vị này; nhập bằng đơn vị nào cũng được rồi quy về đây (xem `quy_doi_service.
    # don_vi_dung_duoc`). NULL = chưa chọn: không mặc định "kg" nữa vì đoán sai một lần là sai
    # vĩnh viễn — màn danh mục hiện "Chưa chọn đơn vị" để người khai tự chọn.
    don_vi_gia: Mapped[str | None] = mapped_column(String(24), nullable=True)
    don_gia: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0", default=0)
    gia_thi_truong: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)   # giá tham khảo thị trường
    kho_tinh_gia: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_true(), default=True)  # khổ này dùng để tính giá?
    cong_thuc_gia: Mapped[str | None] = mapped_column(Text, nullable=True)
    # CÔNG THỨC LƯỢNG (mg 0195) — "một lệnh cần bao nhiêu <đơn vị này>". Cùng luật với
    # `VatTuInAn.cong_thuc_luong`: ra LƯỢNG cho kế hoạch vật tư, khác `cong_thuc_gia` ngay trên
    # (ra TIỀN cho phiếu tính giá).
    #
    # Có ô này thì giấy khai ĐVT `kg` THẬT rồi tự tính ra kg — không phải đi vòng qua cạnh quy đổi
    # động `tờ → kg` nữa. Cạnh đó là thứ duy nhất còn giữ "công thức mà lại có đích", thứ chủ chốt
    # 13/08/2026 là vô lý; khai ở đây xong thì xoá nó bằng tay trên UI được.
    cong_thuc_luong: Mapped[str | None] = mapped_column(Text, nullable=True)
    ghi_chu: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # NVL THAY THẾ (mg 0239) — mảng id GIẤY khác dùng thay được món này. MỘT CHIỀU: khai A→B
    # không tự suy B→A, cần cả hai chiều thì người khai tự thêm cả hai. NULL = chưa khai.
    thay_the_ids: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)
    # Ảnh minh hoạ vật tư (1 ảnh). Lưu đường `/api/files/materials/…` (đọc qua router có đăng nhập);
    # trang QR công khai serve lại chính key này qua `/api/public/vat-lieu-anh` bằng token QR. NULL = chưa có ảnh.
    anh_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1", default=1)  # phiên bản giá hiện hành (mirror từ giay_gia_version)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_true(), default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class GiayGiaVersion(Base):
    """Phiên bản giá giấy — ẢNH CHỤP toàn bản ghi Giấy tại 1 mốc hiệu lực (lịch sử giá).

    Mỗi lần "Thêm phiên bản" đẻ 1 row; `is_current` = mốc đang áp dụng; `giay_nguyen` mirror
    các trường của version is_current. `giay_id` soft int → `giay_nguyen` (no DB FK).
    """

    __tablename__ = "giay_gia_version"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    giay_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)  # → giay_nguyen.id
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1", default=1)
    ngay_hieu_luc: Mapped[date | None] = mapped_column(Date, nullable=True)     # áp dụng từ ngày
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_true(), default=True)
    # -- ảnh chụp toàn bản ghi tại mốc này --
    kho_dai: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)
    kho_rong: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)
    gsm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    caliper_micron: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tho: Mapped[str | None] = mapped_column(String(12), nullable=True)
    don_vi_gia: Mapped[str] = mapped_column(String(8), nullable=False, server_default="kg", default="kg")
    don_gia: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0", default=0)
    gia_thi_truong: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    ghi_chu: Mapped[str | None] = mapped_column(String(500), nullable=True)     # lý do đổi (vd NCC tăng giá)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class VatTuInAn(Base):
    """Vật tư in ấn — danh mục PHẲNG (mực/kẽm/hoá chất/màng/keo… chung 1 bảng, phân biệt bằng TÊN).

    Đơn giản theo bảng xưởng: Mã · Tên · ĐVT · Giá · Ghi chú. Không phân loại, không tồn.
    """

    __tablename__ = "vat_tu_in_an"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ma: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    ten: Mapped[str] = mapped_column(String(150), nullable=False)
    # ĐƠN VỊ GỐC — mã trong `don_vi_do`. NULL = chưa chọn (xem ghi chú ở `GiayNguyen.don_vi_gia`).
    don_vi_gia: Mapped[str | None] = mapped_column(String(24), nullable=True)
    # BỎ quy cách đóng gói (`don_vi_dong_goi` / `he_so_dong_goi`, mg 0170 → gỡ 10/08/2026): khai
    # quy đổi hai nơi (ở đây và ở danh mục Đơn vị & quy đổi) là bắt người dùng nhớ luật vô ích.
    # Cần "thùng keo 20 kg" thì khai thẳng một đơn vị như vậy trong danh mục Đơn vị & quy đổi.
    # Hai cột cũ để nguyên trong DB (không drop, dự án không có Alembic) nhưng không còn ai đọc.
    don_gia: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0", default=0)
    cong_thuc_gia: Mapped[str | None] = mapped_column(Text, nullable=True)
    # CÔNG THỨC LƯỢNG (mg 0194) — "một lệnh cần bao nhiêu <đơn vị này>", biến lấy từ quy cách lệnh.
    # KHÁC `cong_thuc_gia` ngay trên: ô kia ra TIỀN cho phiếu tính giá, ô này ra LƯỢNG cho BOM ở
    # bước lệnh. Hai câu hỏi khác nhau nên hai ô, đừng gộp.
    #
    # Vì sao đặt ở VẬT TƯ chứ không ở đơn vị (chủ chốt 13/08/2026): `kg` dùng chung cho keo · mực ·
    # giấy, mà mỗi thứ tiêu hao theo một cách khác hẳn. Gắn công thức lên `kg` là mọi vật tư đo bằng
    # kg đều bị tính theo cùng một công thức; muốn tránh thì phải đẻ `kg_keo`, `kg_muc`, `kg_giay`…
    # rồi kho và mua hàng lãnh đủ mấy cái tên đó trong khi họ vẫn cân bằng kg thật.
    cong_thuc_luong: Mapped[str | None] = mapped_column(Text, nullable=True)
    ghi_chu: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # NVL THAY THẾ (mg 0239) — mảng id VẬT TƯ KHÁC khác dùng thay được món này. MỘT CHIỀU, xem
    # ghi chú đầy đủ ở `GiayNguyen.thay_the_ids`. NULL = chưa khai.
    thay_the_ids: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)

    # THÀNH PHẨM của một đơn hàng (mg 0203 · docs/prd-thanh-pham.md).
    #
    # Sản phẩm in là hàng ĐẶT RIÊNG — "Hộp thuốc 10 vỉ, in 2 màu, cán bóng" không có sẵn ở danh
    # mục nào. Nhưng kho chỉ xuất được thứ CÓ trong danh mục (luật 08/08/2026 bỏ ô tên tự do),
    # nên lúc CHỐT ĐƠN hệ tự khai mỗi dòng đơn thành một dòng ở đây.
    #
    # ⚠️ NGƯNG DÙNG LÀM KHOÁ từ 21/08/2026 (mg 0228). Giữ cột để tra lịch sử "đơn đầu tiên của
    # khách nào", KHÔNG được dùng lại làm công tắc màn hay phạm vi gộp trùng.
    #
    # Trước đó nó gánh HAI việc: chủ của thành phẩm + công tắc chia hai màn danh mục. Chủ dự án
    # bỏ: "thành phẩm này là một cái tên hàng, nêu chưa khai để tái sử dụng, tránh phình lên" —
    # tức nó KHÔNG thuộc về ai, giống bán cùng một cái quạt cho nhiều khách. Hệ quả:
    #   · công tắc màn chuyển sang cột `la_thanh_pham` ngay dưới;
    #   · phạm vi gộp trùng chuyển thành TÊN đã chuẩn hoá, không kèm khách.
    customer_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)

    # CÔNG TẮC chia hai màn dùng chung bảng này: `true` ⇒ màn "Thành phẩm", `false` ⇒ "Vật tư
    # khác" (xem `_VatTuRepo` / `_ThanhPhamRepo`). Cột cờ RIÊNG chứ không suy từ cột khác nữa —
    # suy từ `customer_id` đã hỏng đúng lúc thành phẩm thôi thuộc về khách. Thêm ở mg 0228.
    la_thanh_pham: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa_false()
    )

    # Đơn ĐẦU TIÊN đặt món này — giữ để tra nguồn gốc, KHÔNG phải khoá định danh (mg 0203 từng
    # dùng làm khoá và sai: đặt lại là đẻ dòng thứ hai). Không cập nhật ở những lần đặt sau.
    #
    # Soft-ref, KHÔNG FK cứng: danh mục sống lâu hơn đơn — huỷ đơn KHÔNG xoá thành phẩm vì có thể
    # đã nhập kho, xoá là làm mồ côi lô tồn. Cùng khuôn `stock_requests.purchase_delivery_id`.
    order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    order_line_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    # Ảnh minh hoạ vật tư (1 ảnh) — xem ghi chú `GiayNguyen.anh_url`.
    anh_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_true(), default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
