"""Thực hiện sản xuất — SẢN LƯỢNG · LOT ĐẦU VÀO · BÀN GIAO · XÁC NHẬN VẬT TƯ (Giai đoạn 3, §10–§11).

Năm bảng GHI đứng SAU khung phiên-chạy (Giai đoạn 2) và neo lên snapshot công việc
(`san_xuat_cong_viec`). Chúng KHÔNG chép lại công việc — chỉ ghi kết quả thực tế:

  san_xuat_batch           — một BATCH sản lượng (§11.1): khoảng thời gian + tổng/tốt/hỏng + đơn vị
                             + nhóm lỗi khi có hỏng. Người tham gia SUY LÚC ĐỌC từ khoảng tham gia
                             giao với cửa sổ batch (§12.1) — KHÔNG lưu thành viên.
  san_xuat_batch_lot_vao   — LOT đầu vào đã dùng cho một batch (§10.3): lot đầu ra công đoạn trước
                             hoặc lot BTP kho + số lượng → truy vết nguyên liệu/BTP → batch đầu ra.
  san_xuat_ban_giao        — BÀN GIAO sản lượng tốt sang công đoạn sau (§11.2): MỘT số lượng thống
                             nhất mỗi lần giao. Cùng tổ → tạo thẳng `confirmed`; khác tổ/LSX →
                             `proposed` rồi bên nhận `confirmed`.
  san_xuat_ban_giao_dieu_chinh — ĐIỀU CHỈNH bàn giao (§11.3): KHÔNG xoá cứng, đẻ dòng điều chỉnh giữ
                             lịch sử trước/sau. Giảm dưới lượng công đoạn sau đã dùng → cờ không nhất quán.
  san_xuat_vat_tu_nhan     — TỔ XÁC NHẬN đã nhận vật tư của MỘT phiếu xuất đã ghi sổ (§10.1). Xác nhận
                             phiếu NGUYÊN TRẠNG (không đẻ con số "tổ nhận" đối nghịch "kho giao"). Chỉ
                             phần đã xác nhận mới coi là khả dụng.

NEO snapshot: batch/bàn giao trỏ `san_xuat_cong_viec.id` (bản đóng băng, ổn định). Số dẫn xuất
(sản lượng còn lại, đầu vào khả dụng, % hoàn thành) TÍNH LÚC ĐỌC ở service — không cache cột.

Bảng MỚI → `create_all` tự dựng, KHÔNG migration. Boolean dùng `false()`/`true()` (bẫy Postgres DB
trắng). Mọi bảng mang `version` chống bấm trùng (trừ bảng LỊCH SỬ chỉ-thêm: lot đầu vào, điều chỉnh).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, Numeric, String,
    false as sa_false,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# --- Trạng thái bàn giao (§18: proposed → confirmed → adjusted) ------------------------------
BG_DE_XUAT = "proposed"      # bên giao đã đề xuất, chờ bên nhận xác nhận (khác tổ/LSX)
BG_XAC_NHAN = "confirmed"    # hai bên đã thống nhất — số này là đầu vào công đoạn sau + cơ sở lương
BG_DIEU_CHINH = "adjusted"   # đã có ít nhất một điều chỉnh sau xác nhận
TRANG_THAI_BAN_GIAO = (BG_DE_XUAT, BG_XAC_NHAN, BG_DIEU_CHINH)

# --- Nguồn lot đầu vào (§10.3) ---------------------------------------------------------------
LOT_TU_BATCH = "batch"       # lot đầu ra của công đoạn trước (một batch sản lượng)
LOT_TU_KHO = "kho_lot"       # lot BTP nằm trong kho (soft ref stock_lots — dùng ở pha nhập kho BTP)
NGUON_LOT = (LOT_TU_BATCH, LOT_TU_KHO)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SanXuatBatch(Base):
    """Một BATCH sản lượng của một công việc (§11.1). Nhiều batch một phần trong cùng công đoạn.

    Ràng buộc `tong = tot + hong` do service kiểm (Numeric, không dựa CHECK để còn dung sai làm
    tròn). `hong > 0` bắt buộc `nhom_loi_id` (nhóm lỗi chuẩn hoá), `mo_ta_loi` chỉ bổ sung — không
    thay thế danh mục (§11.1). Người tham gia batch SUY LÚC ĐỌC từ khoảng tham gia giao cửa sổ
    `[bat_dau, ket_thuc]` (§12.1), không lưu ở đây."""

    __tablename__ = "san_xuat_batch"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cong_viec_id: Mapped[int] = mapped_column(
        ForeignKey("san_xuat_cong_viec.id", ondelete="CASCADE"), nullable=False, index=True
    )
    bat_dau: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ket_thuc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    tong: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False)
    tot: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False)
    hong: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False, server_default="0", default=0)
    don_vi: Mapped[str] = mapped_column(String(24), nullable=False)
    # Nhóm lỗi chuẩn hoá khi có hỏng (§11.1). SET NULL để giữ batch cũ khi danh mục lỗi bị xoá mềm.
    nhom_loi_id: Mapped[int | None] = mapped_column(
        ForeignKey("san_xuat_ly_do.id", ondelete="SET NULL"), nullable=True, index=True
    )
    mo_ta_loi: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ghi_chu: Mapped[str | None] = mapped_column(String(500), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class SanXuatBatchLotVao(Base):
    """Một LOT đầu vào đã dùng cho một batch (§10.3). Bảng CHỈ-THÊM (không version): dựng quan hệ
    truy vết nguyên liệu/BTP → batch đầu ra.

    Giai đoạn 3 dùng `nguon_loai='batch'` (lot đầu ra công đoạn trước = một `san_xuat_batch`).
    `nguon_lot_id` là SOFT ref `stock_lots.id` (không FK — module kho có thể migrate riêng), dành
    cho lot BTP nằm trong kho ở pha nhập-kho-BTP sau."""

    __tablename__ = "san_xuat_batch_lot_vao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("san_xuat_batch.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nguon_loai: Mapped[str] = mapped_column(String(16), nullable=False, default=LOT_TU_BATCH)
    # Batch đầu ra của công đoạn TRƯỚC (khi nguon_loai='batch'). SET NULL giữ vết nếu batch nguồn bị gỡ.
    nguon_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("san_xuat_batch.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Soft ref stock_lots.id (khi nguon_loai='kho_lot') — không FK theo precedent soft-ref của kho.
    nguon_lot_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    so_luong: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False)
    don_vi: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class SanXuatBanGiao(Base):
    """BÀN GIAO sản lượng tốt sang công đoạn sau (§11.2). MỘT số lượng thống nhất mỗi lần giao —
    KHÔNG lưu hai con số cạnh tranh.

    Cùng tổ (`cung_to=true`) → tạo thẳng `confirmed` (hai công đoạn liên tiếp cùng tổ tự chuyển).
    Khác tổ/LSX → `proposed`: bên giao sửa `so_luong` được khi còn proposed; bên nhận xác nhận đúng
    con số cuối. `khong_nhat_quan` bật khi một điều chỉnh giảm xuống dưới lượng công đoạn sau đã dùng
    (§11.3) — chặn chốt phân bổ/đóng nhóm."""

    __tablename__ = "san_xuat_ban_giao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nguon_cong_viec_id: Mapped[int] = mapped_column(
        ForeignKey("san_xuat_cong_viec.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Công đoạn sau nhận đầu vào. Nullable: bàn giao ra ngoài (nhập kho BTP) chưa neo công việc sau.
    dich_cong_viec_id: Mapped[int | None] = mapped_column(
        ForeignKey("san_xuat_cong_viec.id", ondelete="SET NULL"), nullable=True, index=True
    )
    cung_to: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_false(), default=False
    )
    so_luong: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False)
    don_vi: Mapped[str] = mapped_column(String(24), nullable=False)
    trang_thai: Mapped[str] = mapped_column(String(16), nullable=False, default=BG_DE_XUAT)
    khong_nhat_quan: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_false(), default=False
    )
    de_xuat_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    de_xuat_luc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    xac_nhan_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    xac_nhan_luc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class SanXuatBanGiaoDieuChinh(Base):
    """Một lần ĐIỀU CHỈNH số lượng bàn giao (§11.3). Bảng CHỈ-THÊM (không version) — giữ lịch sử
    trước/sau, không xoá cứng bàn giao. `khong_nhat_quan=true` nếu `so_luong_sau` thấp hơn lượng
    công đoạn sau đã tiêu thụ tại thời điểm điều chỉnh."""

    __tablename__ = "san_xuat_ban_giao_dieu_chinh"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ban_giao_id: Mapped[int] = mapped_column(
        ForeignKey("san_xuat_ban_giao.id", ondelete="CASCADE"), nullable=False, index=True
    )
    so_luong_truoc: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False)
    so_luong_sau: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False)
    ly_do_id: Mapped[int | None] = mapped_column(
        ForeignKey("san_xuat_ly_do.id", ondelete="SET NULL"), nullable=True, index=True
    )
    mo_ta: Mapped[str | None] = mapped_column(String(500), nullable=True)
    khong_nhat_quan: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_false(), default=False
    )
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class SanXuatVatTuNhan(Base):
    """TỔ XÁC NHẬN đã nhận vật tư của MỘT phiếu xuất đã ghi sổ (§10.1).

    Xác nhận phiếu NGUYÊN TRẠNG — nếu số lệch, kho sửa chứng từ TRƯỚC khi tổ xác nhận (§10.1), nên
    ở đây KHÔNG có con số "tổ nhận" riêng. `voucher_id` UNIQUE: một phiếu xuất chỉ xác nhận một lần.
    Chỉ phiếu đã xác nhận mới coi là tồn khả dụng cho công đoạn (đọc ở service)."""

    __tablename__ = "san_xuat_vat_tu_nhan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    voucher_id: Mapped[int] = mapped_column(
        ForeignKey("stock_vouchers.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    # Tổ nhận (node lá Khối SX) — người xác nhận phải là tổ trưởng tổ này.
    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id"), nullable=False, index=True
    )
    xac_nhan_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    xac_nhan_luc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    ghi_chu: Mapped[str | None] = mapped_column(String(500), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
