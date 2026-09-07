"""Sổ tài sản cố định & công cụ dụng cụ (kế toán).

MỘT bảng `tai_san` cho cả TSCĐ lẫn CCDC — phân biệt bằng `loai`. Không có danh mục nhóm tài
sản: số tháng khấu hao kế toán gõ thẳng vào phiếu (chốt 07/09/2026 — danh mục nhóm chỉ tiết
kiệm một ô mỗi lần ghi tăng, đổi lại đẻ thêm một màn để sai).

KHÔNG có ô tài khoản kế toán, và cũng KHÔNG còn ô định khoản riêng: `ghi_chu_hach_toan` đã gỡ
(mg 0278) vì hai ô ghi chú cạnh nhau chỉ làm người nhập phân vân gõ vào đâu. Cần nhớ định khoản
thì gõ vào `ghi_chu` như mọi thứ cần nhớ khác — module không đọc nội dung ô đó.

Ba trường `co_so_trich` / `so_thang_con` / `moc_tu_ngay` là ĐẦU VÀO DUY NHẤT của engine khấu
hao — nạp đầu kỳ, ghi tăng, nâng cấp và CCDC giảm một phần lô đều quy về bộ ba này, nên engine
không cần biết tài sản đến từ đường nào.

Tiền để `BigInteger`: nguyên giá máy in tràn int32 trên Postgres (đã vỡ thật một lần).

Bảng MỚI → `create_all` tự dựng; mg 0277 cấp QUYỀN cho vai đã có, mg 0278 gỡ ô định khoản.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base

# `loai` — tách TSCĐ với CCDC. Chỉ khác nhau ở nhãn + gợi ý số tháng, luật tính GIỐNG HỆT.
LOAI_TSCD = "tscd"
LOAI_CCDC = "ccdc"

# `tai_san_bien_dong.loai` — ba chứng từ, một bảng.
BD_DIEU_CHUYEN = "dieu_chuyen"
BD_NANG_CAP = "nang_cap"
BD_GHI_GIAM = "ghi_giam"

TT_DANG_DUNG = "dang_dung"
TT_DA_GIAM = "da_giam"

# `nguon_vao` — tài sản mua mới trong kỳ vs số dư mang sang lúc bắt đầu dùng phần mềm.
NGUON_GHI_TANG = "ghi_tang"
NGUON_DAU_KY = "dau_ky"

KY_MO = "mo"
KY_DA_CHOT = "da_chot"

KK_DANG_KIEM = "dang_kiem"
KK_DA_KET = "da_ket"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TaiSan(Base):
    """Một tài sản cố định, hoặc một LÔ công cụ dụng cụ cùng loại mua cùng lượt."""

    __tablename__ = "tai_san"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    #: Mã hệ sinh: `TS-0001` cho TSCĐ, `CC-0001` cho CCDC.
    ma: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    ten: Mapped[str] = mapped_column(String(255), nullable=False)
    loai: Mapped[str] = mapped_column(
        String(8), nullable=False, index=True, default=LOAI_TSCD, server_default=LOAI_TSCD
    )
    #: CCDC nhập theo lô: 12 tấm cao su = 1 dòng, số lượng 12. TSCĐ luôn để 1.
    so_luong: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    don_gia: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    #: Tổng các dòng chi phí cấu thành (giá mua + vận chuyển + lắp đặt chạy thử…).
    nguyen_gia: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    #: Số tháng khấu hao/phân bổ kế toán chọn. Gợi ý: máy in 7–15 năm, CCDC tối đa 3 năm.
    so_thang: Mapped[int] = mapped_column(Integer, nullable=False)
    ngay_su_dung: Mapped[date] = mapped_column(Date, nullable=False)

    # --- Bộ ba đầu vào của engine khấu hao (xem docstring module) ------------------------
    #: Số tiền CÒN PHẢI TRÍCH tính từ `moc_tu_ngay`.
    co_so_trich: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    #: Số tháng còn phải trích kể từ `moc_tu_ngay`.
    so_thang_con: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Ngày bắt đầu áp bộ cơ sở hiện tại (ghi tăng ⇒ ngày sử dụng; nâng cấp ⇒ đầu kỳ sau).
    moc_tu_ngay: Mapped[date] = mapped_column(Date, nullable=False)
    #: Hao mòn đã trích tới nay — CHỈ cộng vào lúc CHỐT kỳ, không cộng lúc tính thử.
    hao_mon_luy_ke: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    # --- Nạp số dư đầu kỳ (tài sản đã dùng trước khi lên phần mềm) -----------------------
    nguon_vao: Mapped[str] = mapped_column(
        String(8), nullable=False, default=NGUON_GHI_TANG, server_default=NGUON_GHI_TANG
    )
    hao_mon_dau_ky: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    thang_da_trich_dau_ky: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # --- Ai giữ, ở đâu ------------------------------------------------------------------
    bo_phan_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("departments.id", ondelete="SET NULL"), index=True, nullable=True
    )
    nguoi_quan_ly: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vi_tri: Mapped[str | None] = mapped_column(String(255), nullable=True)
    so_hoa_don: Mapped[str | None] = mapped_column(String(64), nullable=True)
    nha_cung_cap: Mapped[str | None] = mapped_column(String(255), nullable=True)

    #: Chữ TỰ DO — kế toán ghi gì tuỳ ý, kể cả định khoản. Hệ KHÔNG đọc nội dung.
    ghi_chu: Mapped[str | None] = mapped_column(Text, nullable=True)

    trang_thai: Mapped[str] = mapped_column(
        String(12), nullable=False, index=True, default=TT_DANG_DUNG, server_default=TT_DANG_DUNG
    )
    #: Ngày ghi giảm — từ ngày này engine ngừng trích (tháng chứa nó tính theo số ngày dùng).
    ngay_giam: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    chi_phi: Mapped[list["TaiSanChiPhi"]] = relationship(
        back_populates="tai_san", cascade="all, delete-orphan", order_by="TaiSanChiPhi.id"
    )
    bien_dong: Mapped[list["TaiSanBienDong"]] = relationship(
        back_populates="tai_san", order_by="TaiSanBienDong.ngay, TaiSanBienDong.id"
    )


class TaiSanChiPhi(Base):
    """Một dòng cấu thành nguyên giá. Giữ lại để giải thích 3,3 tỷ đến từ đâu."""

    __tablename__ = "tai_san_chi_phi"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tai_san_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tai_san.id", ondelete="CASCADE"), index=True, nullable=False
    )
    dien_giai: Mapped[str] = mapped_column(String(255), nullable=False)
    so_tien: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    tai_san: Mapped["TaiSan"] = relationship(back_populates="chi_phi")


class TaiSanBienDong(Base):
    """Một chứng từ biến động: điều chuyển | nâng cấp | ghi giảm.

    MỘT bảng chứ không ba: ba nghiệp vụ dùng chung phần lớn cột (tài sản, ngày, lý do) và luôn
    được đọc chung ở tab lịch sử của tài sản. Cột riêng để NULL.
    """

    __tablename__ = "tai_san_bien_dong"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tai_san_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tai_san.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    loai: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    ngay: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    #: nâng cấp ⇒ chi phí nâng cấp; ghi giảm ⇒ giá bán/thu hồi; điều chuyển ⇒ NULL.
    so_tien: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    bo_phan_moi_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    #: Chỉ nâng cấp: số tháng còn dùng kể từ kỳ áp dụng.
    so_thang_con_lai: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Chỉ ghi giảm CCDC theo lô: bỏ mấy cái trong lô.
    so_luong_giam: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ly_do: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nguoi_tao_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    tai_san: Mapped["TaiSan"] = relationship(back_populates="bien_dong")


class TaiSanKhauHao(Base):
    """Số trích của MỘT tài sản trong MỘT kỳ. Kỳ chưa chốt thì tính lại là ghi đè."""

    __tablename__ = "tai_san_khau_hao"
    __table_args__ = (
        UniqueConstraint("tai_san_id", "ky_nam", "ky_thang", name="uq_tai_san_khau_hao_ky"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tai_san_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tai_san.id", ondelete="CASCADE"), index=True, nullable=False
    )
    ky_nam: Mapped[int] = mapped_column(Integer, nullable=False)
    ky_thang: Mapped[int] = mapped_column(Integer, nullable=False)
    muc_trich: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    luy_ke: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    con_lai: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    #: Bộ phận chịu chi phí kỳ này — CHỤP lại lúc tính, vì tài sản có thể điều chuyển sau đó.
    bo_phan_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )


class TaiSanKy(Base):
    """Trạng thái một kỳ khấu hao. Chốt rồi thì mọi số của kỳ đó đóng băng."""

    __tablename__ = "tai_san_ky"
    __table_args__ = (UniqueConstraint("ky_nam", "ky_thang", name="uq_tai_san_ky"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ky_nam: Mapped[int] = mapped_column(Integer, nullable=False)
    ky_thang: Mapped[int] = mapped_column(Integer, nullable=False)
    trang_thai: Mapped[str] = mapped_column(
        String(8), nullable=False, default=KY_MO, server_default=KY_MO
    )
    ngay_chot: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    nguoi_chot_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class TaiSanKiemKe(Base):
    """Một đợt kiểm kê tài sản — bung danh sách phải có, đối chiếu tay, ra thiếu/thừa."""

    __tablename__ = "tai_san_kiem_ke"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ma: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    ngay: Mapped[date] = mapped_column(Date, nullable=False)
    #: NULL = kiểm toàn công ty.
    bo_phan_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    trang_thai: Mapped[str] = mapped_column(
        String(12), nullable=False, default=KK_DANG_KIEM, server_default=KK_DANG_KIEM
    )
    ghi_chu: Mapped[str | None] = mapped_column(Text, nullable=True)
    nguoi_tao_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    dong: Mapped[list["TaiSanKiemKeDong"]] = relationship(
        back_populates="dot", cascade="all, delete-orphan", order_by="TaiSanKiemKeDong.id"
    )


class TaiSanKiemKeDong(Base):
    """Một dòng đối chiếu. `tai_san_id` NULL = món PHÁT HIỆN ngoài sổ (thừa)."""

    __tablename__ = "tai_san_kiem_ke_dong"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tai_san_kiem_ke.id", ondelete="CASCADE"), index=True, nullable=False
    )
    tai_san_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("tai_san.id", ondelete="SET NULL"), nullable=True
    )
    #: 'co' | 'khong_thay' | NULL (chưa đối chiếu).
    ket_qua: Mapped[str | None] = mapped_column(String(12), nullable=True)
    #: Tên món thừa do người kiểm gõ vào (dòng không gắn tài sản nào trong sổ).
    ten_phat_hien: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tinh_trang: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ghi_chu: Mapped[str | None] = mapped_column(Text, nullable=True)

    dot: Mapped["TaiSanKiemKe"] = relationship(back_populates="dong")
