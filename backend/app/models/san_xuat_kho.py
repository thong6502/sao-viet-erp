"""Thực hiện sản xuất — KHO SẢN XUẤT: registry hàng · lot BTP/thành phẩm · yêu cầu nhập kho (Giai đoạn 5, §14).

Ba bảng GHI khép kín khâu kho của lớp thực thi, đứng SAU KCS (§13) và neo lên snapshot công việc /
nhóm thành phẩm / batch KCS. Chúng KHÔNG thay nghiệp vụ chứng từ kho hiện có (§22) — chỉ ghi nhận
hàng do sản xuất đẻ ra và đường nó vào kho:

  san_xuat_kho_hang   — REGISTRY hàng sản xuất (§14.2): danh tính hàng TRONG MỘT ĐƠN, hai subtype
                        `btp` / `thanh_pham`. Thành phẩm = nhóm sản phẩm của đơn ("DH019 + Kỷ yếu");
                        BTP mịn hơn (LSX + công đoạn nguồn + quy cách). Đây KHÔNG phải SKU chung tái
                        dùng — hàng chỉ giao/tái dùng trong đúng đơn của nó (§14.1, §14.2).
  san_xuat_kho_lot    — một LÔ hàng sản xuất đã ghi nhận (§14.1, §14.2). Với thành phẩm: mỗi lần kho
                        xác nhận một phần yêu cầu nhập kho đẻ một lot (neo `nhap_kho_yc_id` + batch
                        KCS). Với BTP dư: mỗi lần phân loại đẻ một lot mang `phan_loai`
                        (`nhap_btp` / `mau_luu` / `phe`); riêng `nhap_btp` chờ kho xác nhận nhận.
  san_xuat_nhap_kho_yc — YÊU CẦU nhập kho thành phẩm (§14.1): KCS tạo nhiều yêu cầu một phần từ các
                        batch ĐẠT; kho xác nhận từng phần (`so_luong_xac_nhan` cộng dồn); phần đã ghi
                        nhận BỊ KHÓA, phần chưa nhận KCS còn phân loại lại. Neo `kcs_batch_id` (§19).

NEO snapshot: mọi bảng trỏ `order_id` / `nhom_id` / `lsx_id` / `cong_doan_ref_id` (SET NULL giữ vết).
Số dẫn xuất (còn được yêu cầu, tồn khả dụng) TÍNH LÚC ĐỌC ở service — không cache cột.

Ba bảng dựng bằng `create_all`; cột THÊM SAU vẫn phải có migration (`kho_id` = mg 0255 — `create_all`
không ALTER). Boolean dùng `false()`/`true()` (bẫy Postgres DB trắng). Bảng nghiệp vụ (registry,
yêu cầu) mang `version` chống bấm trùng; bảng LỊCH SỬ chỉ-thêm
(lot) không có `version`. RBAC: yêu cầu nhập kho gate tổ trưởng KCS (module `san_xuat`); kho xác nhận
gate quyền `kho` (nhân viên kho) tại router.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, Numeric, String,
    false as sa_false,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# --- Subtype hàng sản xuất (§14.2) -----------------------------------------------------------
HANG_BTP = "btp"                 # bán thành phẩm
HANG_THANH_PHAM = "thanh_pham"   # thành phẩm theo đơn hàng
LOAI_HANG = (HANG_BTP, HANG_THANH_PHAM)

# --- Phân loại BTP dư trước khi đóng nhóm (§14.2) --------------------------------------------
PL_NHAP_BTP = "nhap_btp"   # nhập kho BTP (chờ kho xác nhận nhận)
PL_MAU_LUU = "mau_luu"     # mẫu lưu (giữ làm mẫu, không vào tồn khả dụng)
PL_PHE = "phe"             # phế/hỏng (bỏ)
PHAN_LOAI_BTP_DU = (PL_NHAP_BTP, PL_MAU_LUU, PL_PHE)

# --- Trạng thái yêu cầu nhập kho thành phẩm (§14.1, §18) -------------------------------------
YC_CHO_KHO = "cho_kho"           # KCS đã tạo, chờ kho xác nhận nhận
YC_MOT_PHAN = "nhap_mot_phan"    # kho đã xác nhận một phần
YC_DA_NHAP = "da_nhap"           # kho đã xác nhận đủ số yêu cầu
YC_HUY = "huy"                   # KCS huỷ phần chưa nhận (phân loại lại)
TRANG_THAI_YC = (YC_CHO_KHO, YC_MOT_PHAN, YC_DA_NHAP, YC_HUY)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SanXuatKhoHang(Base):
    """REGISTRY hàng sản xuất — danh tính hàng TRONG MỘT ĐƠN (§14.2). Service get-or-create theo
    khóa (đơn, nhóm, loại, LSX, công đoạn nguồn, quy cách) nên KHÔNG đẻ trùng danh tính. `ma` là
    mã sinh ổn định. BTP của một đơn CHỈ tái dùng trong đơn đó — ràng buộc ở tầng chọn lot đầu vào,
    registry chỉ giữ danh tính + subtype."""

    __tablename__ = "san_xuat_kho_hang"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ma: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    loai_hang: Mapped[str] = mapped_column(String(16), nullable=False, default=HANG_THANH_PHAM)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nhom_id: Mapped[int | None] = mapped_column(
        ForeignKey("san_xuat_nhom.id", ondelete="SET NULL"), nullable=True, index=True
    )
    lsx_id: Mapped[int | None] = mapped_column(
        ForeignKey("lsx.id", ondelete="SET NULL"), nullable=True, index=True
    )
    cong_doan_ref_id: Mapped[int | None] = mapped_column(
        ForeignKey("san_xuat_cong_viec.id", ondelete="SET NULL"), nullable=True, index=True
    )
    ten: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    quy_cach: Mapped[str | None] = mapped_column(String(255), nullable=True)
    don_vi: Mapped[str] = mapped_column(String(24), nullable=False, default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class SanXuatKhoLot(Base):
    """Một LÔ hàng sản xuất đã ghi nhận (§14.1, §14.2). Bảng CHỈ-THÊM (không `version`) — mỗi lần kho
    xác nhận một phần / mỗi lần phân loại BTP dư đẻ MỘT lot mới, giữ lịch sử đủ.

    Thành phẩm: `loai_hang=thanh_pham`, neo `nhap_kho_yc_id` + `kcs_batch_id`, `kho_xac_nhan=true`
    (do kho tạo lúc xác nhận). BTP dư: `loai_hang=btp` + `phan_loai`; `nhap_btp` chờ kho xác nhận
    (`kho_xac_nhan=false` → true khi kho nhận), còn `mau_luu`/`phe` là chung cục ngay (không qua kho).
    `nguon_batch_id` = lot nguồn (batch sản lượng) của BTP để truy vết."""

    __tablename__ = "san_xuat_kho_lot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hang_id: Mapped[int] = mapped_column(
        ForeignKey("san_xuat_kho_hang.id", ondelete="CASCADE"), nullable=False, index=True
    )
    loai_hang: Mapped[str] = mapped_column(String(16), nullable=False, default=HANG_THANH_PHAM)
    # Snapshot danh tính (§14.2). SET NULL giữ lot khi nguồn bị xoá mềm.
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    nhom_id: Mapped[int | None] = mapped_column(
        ForeignKey("san_xuat_nhom.id", ondelete="SET NULL"), nullable=True, index=True
    )
    lsx_id: Mapped[int | None] = mapped_column(
        ForeignKey("lsx.id", ondelete="SET NULL"), nullable=True, index=True
    )
    cong_doan_ref_id: Mapped[int | None] = mapped_column(
        ForeignKey("san_xuat_cong_viec.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Thành phẩm: batch KCS = lot logic + yêu cầu nhập kho sinh ra lot này.
    kcs_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("san_xuat_kcs_batch.id", ondelete="SET NULL"), nullable=True, index=True
    )
    nhap_kho_yc_id: Mapped[int | None] = mapped_column(
        ForeignKey("san_xuat_nhap_kho_yc.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # BTP: lot nguồn (batch sản lượng công đoạn nguồn) để truy vết.
    nguon_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("san_xuat_batch.id", ondelete="SET NULL"), nullable=True, index=True
    )
    quy_cach: Mapped[str | None] = mapped_column(String(255), nullable=True)
    so_luong: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False)
    don_vi: Mapped[str] = mapped_column(String(24), nullable=False)
    # Chỉ có với BTP dư; thành phẩm để None.
    phan_loai: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    # KHO ĐÍCH (31/08/2026) — kho ĐÃ THỰC SỰ NHẬN lot này. Bảng CHỈ-THÊM nên nhập nhiều lần vào
    # nhiều kho thì mỗi lot mang kho của nó. HIỆN chỉ đường THÀNH PHẨM (`kho_xac_nhan_nhap`) ghi cột
    # này. Nullable vì ba lý do, đừng đọc nhầm còn một:
    #   · lot BTP `mau_luu`/`phe` không vào kho nào;
    #   · lot BTP `nhap_btp` VẪN để trống — `kho_xac_nhan_btp` đặt `kho_xac_nhan=True` mà không đụng
    #     `kho_id` (thiếu sót đã biết, tách thành việc nối tiếp, KHÔNG vá ở đây);
    #   · lot CŨ (trước migration 0255) không biết đã vào kho nào — đoán mò còn tệ hơn để trống.
    kho_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    kho_xac_nhan: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_false(), default=False
    )
    xac_nhan_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    xac_nhan_luc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ghi_chu: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class SanXuatNhapKhoYc(Base):
    """YÊU CẦU nhập kho thành phẩm (§14.1). Bảng nghiệp vụ (đổi trạng thái + số xác nhận cộng dồn) →
    mang `version`.

    KCS tạo nhiều yêu cầu MỘT PHẦN từ một batch ĐẠT; tổng số yêu cầu của một batch KHÔNG vượt
    `batch.so_luong_dat` (service kiểm). Kho xác nhận từng phần: `so_luong_xac_nhan` cộng dồn, phần
    đó BỊ KHÓA (đẻ lot thành phẩm). Phần chưa xác nhận KCS huỷ để phân loại lại. Trạng thái suy theo
    số: chờ kho → một phần → đủ; huỷ là chung cục cho phần còn lại."""

    __tablename__ = "san_xuat_nhap_kho_yc"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kcs_batch_id: Mapped[int] = mapped_column(
        ForeignKey("san_xuat_kcs_batch.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hang_id: Mapped[int | None] = mapped_column(
        ForeignKey("san_xuat_kho_hang.id", ondelete="SET NULL"), nullable=True, index=True
    )
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    nhom_id: Mapped[int | None] = mapped_column(
        ForeignKey("san_xuat_nhom.id", ondelete="SET NULL"), nullable=True, index=True
    )
    so_luong_yeu_cau: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False)
    so_luong_xac_nhan: Mapped[float] = mapped_column(
        Numeric(18, 3), nullable=False, server_default="0", default=0
    )
    don_vi: Mapped[str] = mapped_column(String(24), nullable=False)
    quy_cach: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # KHO ĐÍCH ĐỀ NGHỊ (31/08/2026) — KCS gợi ý nên nhập vào kho nào; kho vẫn tự chọn lúc xác nhận
    # (kho thật nằm trên LOT). Để trống là bình thường: KCS không buộc phải biết chỗ cất.
    kho_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    trang_thai: Mapped[str] = mapped_column(String(16), nullable=False, default=YC_CHO_KHO)
    ghi_chu: Mapped[str | None] = mapped_column(String(500), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    xac_nhan_last_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    xac_nhan_last_luc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
