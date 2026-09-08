"""Sổ tài sản cố định & công cụ dụng cụ (kế toán).

MỘT bảng `tai_san` cho cả TSCĐ lẫn CCDC — phân biệt bằng `loai`. Không có danh mục nhóm tài
sản: số tháng khấu hao kế toán gõ thẳng vào phiếu (chốt 07/09/2026 — danh mục nhóm chỉ tiết
kiệm một ô mỗi lần ghi tăng, đổi lại đẻ thêm một màn để sai).

KHÔNG có ô tài khoản kế toán, và cũng KHÔNG còn ô định khoản riêng: `ghi_chu_hach_toan` đã gỡ
(mg 0278) vì hai ô ghi chú cạnh nhau chỉ làm người nhập phân vân gõ vào đâu. Cần nhớ định khoản
thì gõ vào `ghi_chu` như mọi thứ cần nhớ khác — module không đọc nội dung ô đó.

KHÔNG có kỳ chốt (chủ chốt 08/09/2026: "nó chỉ theo dõi khấu hao thôi"). Hao mòn lũy kế không
nằm ở cột nào — engine (`services/tai_san/khau_hao.py`) TÍNH từ bảng mốc `tai_san_moc` tới hết
tháng trước. Mỗi lần cơ sở trích đổi (ghi tăng, nạp đầu kỳ, nâng cấp, CCDC giảm bớt cái) là thêm
một mốc, mốc cũ giữ nguyên ⇒ tháng trước mốc mới vẫn tính theo cơ sở cũ. Bộ ba
`co_so_trich` / `so_thang_con` / `moc_tu_ngay` trên `tai_san` chỉ là GƯƠNG của mốc hiện tại để
bảng và form đọc thẳng. Ba bảng kỳ cũ (`tai_san_khau_hao`, `tai_san_ky`, `tai_san_ky_log`) và cột
`hao_mon_luy_ke` gỡ ở mg 0281.

Tiền để `BigInteger`: nguyên giá máy in tràn int32 trên Postgres (đã vỡ thật một lần).

Bảng MỚI → `create_all` tự dựng (kể cả `tai_san_moc`); mg 0277 cấp QUYỀN cho vai đã có, mg 0278
gỡ ô định khoản, mg 0281 gỡ kỳ chốt + dựng mốc cho tài sản đã có sẵn trên DB.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base

# `loai` — tách TSCĐ với CCDC. Chỉ khác nhau ở nhãn + gợi ý số tháng, luật tính GIỐNG HỆT.
LOAI_TSCD = "tscd"
LOAI_CCDC = "ccdc"

# `tai_san_bien_dong.loai` — hai chứng từ, một bảng. `ghi_giam` chỉ còn ở dòng CŨ: chủ bỏ nghiệp
# vụ ghi giảm 08/09/2026 ("cái ghi giảm bỏ đi") — món bán / hỏng / không dùng nữa thì XOÁ khỏi sổ.
BD_DIEU_CHUYEN = "dieu_chuyen"
BD_NANG_CAP = "nang_cap"
BD_GHI_GIAM = "ghi_giam"

TT_DANG_DUNG = "dang_dung"
#: Chỉ dòng CŨ (đã ghi giảm trước 08/09/2026): engine vẫn ngừng trích từ `ngay_giam`, bảng vẫn
#: hiện "Đã ghi giảm" + còn lại 0; không mã nào đặt trạng thái này nữa.
TT_DA_GIAM = "da_giam"

# `nguon_vao` — tài sản mua mới trong kỳ vs số dư mang sang lúc bắt đầu dùng phần mềm.
NGUON_GHI_TANG = "ghi_tang"
NGUON_DAU_KY = "dau_ky"

# `tai_san_moc.nguon` — việc gì đẻ ra mốc cơ sở đó. `giam_lo` chỉ còn ở dòng cũ (ghi giảm đã bỏ).
MOC_GHI_TANG = "ghi_tang"
MOC_DAU_KY = "dau_ky"
MOC_NANG_CAP = "nang_cap"
MOC_GIAM_LO = "giam_lo"
MOC_SUA = "sua"


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

    # --- Gương của mốc cơ sở HIỆN TẠI (bảng thật là `tai_san_moc`, xem docstring module) ----
    #: Số tiền CÒN PHẢI TRÍCH tính từ `moc_tu_ngay`.
    co_so_trich: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    #: Số tháng còn phải trích kể từ `moc_tu_ngay`.
    so_thang_con: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Ngày bắt đầu áp bộ cơ sở hiện tại (ghi tăng ⇒ ngày sử dụng; nâng cấp ⇒ đầu kỳ sau).
    moc_tu_ngay: Mapped[date] = mapped_column(Date, nullable=False)

    # --- Nạp số dư đầu kỳ (tài sản đã dùng trước khi lên phần mềm) -----------------------
    nguon_vao: Mapped[str] = mapped_column(
        String(8), nullable=False, default=NGUON_GHI_TANG, server_default=NGUON_GHI_TANG
    )
    hao_mon_dau_ky: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    thang_da_trich_dau_ky: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # --- Ai giữ ---------------------------------------------------------------------------
    bo_phan_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("departments.id", ondelete="SET NULL"), index=True, nullable=True
    )
    #: Người quản lý = MỘT NHÂN VIÊN của bộ phận đang giữ (chủ chốt 08/09/2026: không gõ tay).
    #: Đổi bộ phận (sửa / điều chuyển) mà không chọn người mới thì về NULL — người cũ thuộc bộ
    #: phận cũ. mg 0282.
    nguoi_quan_ly_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    #: Tên chụp lại lúc chọn nhân viên (bảng đọc thẳng, khỏi join); dòng cũ trước 08/09 còn chữ
    #: tự gõ thì vẫn hiện nguyên.
    nguoi_quan_ly: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: Không còn ô nhập trên form từ 08/09/2026 (chủ bỏ) — cột giữ để không phải migrate.
    vi_tri: Mapped[str | None] = mapped_column(String(255), nullable=True)
    so_hoa_don: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: Như `vi_tri`: form không hỏi nữa, cột nằm lại.
    nha_cung_cap: Mapped[str | None] = mapped_column(String(255), nullable=True)

    #: Chữ TỰ DO — kế toán ghi gì tuỳ ý, kể cả định khoản. Hệ KHÔNG đọc nội dung.
    ghi_chu: Mapped[str | None] = mapped_column(Text, nullable=True)

    trang_thai: Mapped[str] = mapped_column(
        String(12), nullable=False, index=True, default=TT_DANG_DUNG, server_default=TT_DANG_DUNG
    )
    #: Chỉ dòng CŨ đã ghi giảm trước 08/09/2026 — từ ngày này engine ngừng trích. Không còn mã
    #: nào ghi vào cột này.
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
    moc: Mapped[list["TaiSanMoc"]] = relationship(
        back_populates="tai_san", cascade="all, delete-orphan",
        order_by="TaiSanMoc.tu_ngay, TaiSanMoc.id",
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


class TaiSanMoc(Base):
    """Một đoạn cơ sở trích của tài sản — hiệu lực từ `tu_ngay` tới trước mốc kế tiếp.

    Đây là ĐẦU VÀO của engine khấu hao. Ghi tăng / nạp đầu kỳ đẻ mốc đầu; nâng cấp và CCDC giảm
    một phần lô đẻ mốc mới (mốc cũ giữ, nên tháng trước đó vẫn tính theo cơ sở cũ — trước 08/09
    bộ ba bị ghi đè tại chỗ, tháng nâng cấp trích 0 và tháng trước nó về 0 khi tính lại). Sửa ô số
    khi CHƯA có chứng từ thì dựng lại mốc duy nhất. Không ai sửa tay từng mốc: mốc là hệ quả
    của chứng từ.
    """

    __tablename__ = "tai_san_moc"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tai_san_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tai_san.id", ondelete="CASCADE"), index=True, nullable=False
    )
    #: Từ ngày này áp cơ sở dưới. Không rơi vào ngày 1 thì tháng đó prorate theo ngày.
    tu_ngay: Mapped[date] = mapped_column(Date, nullable=False)
    #: Nguyên giá lúc mốc bắt đầu (sau nâng cấp / sau rút bớt phần lô đã bỏ).
    nguyen_gia: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    #: Số tiền còn phải trích kể từ `tu_ngay` = `nguyen_gia − luy_ke_dau`.
    co_so_trich: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    so_thang_con: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Hao mòn lũy kế ngay TRƯỚC mốc (đã điều chỉnh). Mốc đầu của tài sản mua mới = 0.
    luy_ke_dau: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    #: `ghi_tang` | `dau_ky` | `nang_cap` | `giam_lo` | `sua`.
    nguon: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    tai_san: Mapped["TaiSan"] = relationship(back_populates="moc")


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
