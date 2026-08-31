"""Thực hiện sản xuất — nền NHÓM THÀNH PHẨM & GÓI PHÁT HÀNH (Giai đoạn 1).

Lớp thực thi đứng SAU khâu phát hành của Xếp lịch 2 (xem `docs/spec-thuc-hien-san-xuat.md`).
KHÔNG thay màn lập lịch, KHÔNG dựng hệ sản xuất tách rời. 6 bảng ở đây khắc hoạ đúng nhóm
"Nhóm và phát hành" trong §19:

  san_xuat_nhom          — nhóm thành phẩm (tự sinh từ OrderLine.nhom; §3.1)
  san_xuat_nhom_lsx      — dòng thành viên: nhóm ↔ LSX (neo `lsx_id` THẬT)
  san_xuat_goi_phat_hanh — gói phát hành = một thành phần liên thông (§4.1)
  san_xuat_phien_ban     — phiên bản phát hành/cập nhật của gói (§4.3, giữ lịch sử đủ)
  san_xuat_cong_viec     — SNAPSHOT một công đoạn + neo trạng thái thực thi (§4.2, §18)
  san_xuat_phu_thuoc     — SNAPSHOT cạnh phụ thuộc chéo giữa LSX cùng nhóm = bước ghép (§3.2)

NEO: thành viên/công việc neo `lsx_id` + `bai_ghep_id` (FK THẬT, ổn định). CÔNG ĐOẠN neo bằng
`step_key` + id LỎNG (không FK) — vì replace_routing tái sinh `lsx_cong_doan.id`; nhưng phát hành
đã khoá routing (`da_phat_hanh`) nên snapshot đóng băng, không bị tái sinh sau đó (bám precedent
`bai_ghep.py`).

SNAPSHOT là bản ĐÓNG BĂNG: sau phát hành, đổi cơ cấu/định mức/tổ ở danh mục KHÔNG đụng công việc
đang chạy (§2.2 cuối, §4.3). Số dẫn xuất (sản lượng thực, % hoàn thành…) TÍNH LÚC ĐỌC ở service
theo precedent `lsx_service`/`bai_ghep` — không cache cột.

Bảng MỚI → `create_all` tự dựng, KHÔNG migration (migration chỉ cho ALTER cột bảng cũ). Boolean
dùng `false()`/`true()` của SQLAlchemy — bẫy Postgres create_all trên DB trắng. RBAC tái dùng
module "san_xuat" (không đẻ quyền mới ở lát này).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    DateTime, ForeignKey, Integer, JSON, Numeric, String, UniqueConstraint,
    false as sa_false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base

# --- Trạng thái nhóm thành phẩm (§18) --------------------------------------------------------
NHOM_DANG_SX = "in_production"          # đang sản xuất
NHOM_CHO_DIEU_KIEN = "waiting_conditions"  # chờ điều kiện (thiếu vật tư / chờ nhánh)
NHOM_DONG_DU = "closed_full"           # đóng đủ
NHOM_DONG_THIEU = "closed_short"       # đóng thiếu (short-close)
TRANG_THAI_NHOM = (NHOM_DANG_SX, NHOM_CHO_DIEU_KIEN, NHOM_DONG_DU, NHOM_DONG_THIEU)

# --- Trạng thái gói phát hành ----------------------------------------------------------------
GOI_DANG_PHAT_HANH = "dang_phat_hanh"  # đang hiệu lực
GOI_DA_THU_HOI = "da_thu_hoi"          # đã thu hồi (chỉ khi CHƯA có việc nào bắt đầu — §4.3)
TRANG_THAI_GOI = (GOI_DANG_PHAT_HANH, GOI_DA_THU_HOI)

# --- Loại phiên bản --------------------------------------------------------------------------
PB_PHAT_HANH = "phat_hanh"   # phát hành lần đầu
PB_CAP_NHAT = "cap_nhat"     # phát hành cập nhật
LOAI_PHIEN_BAN = (PB_PHAT_HANH, PB_CAP_NHAT)

# --- Trạng thái công việc (work item) — §18: released → running ↔ paused → completed ---------
CV_PHAT_HANH = "released"
CV_DANG_CHAY = "running"
CV_TAM_DUNG = "paused"
CV_HOAN_THANH = "completed"
TRANG_THAI_CONG_VIEC = (CV_PHAT_HANH, CV_DANG_CHAY, CV_TAM_DUNG, CV_HOAN_THANH)

# --- Loại bước (khớp routing LSX) ------------------------------------------------------------
BUOC_MAY = "may"
BUOC_TO = "to"
BUOC_THUE_NGOAI = "thue_ngoai"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SanXuatNhom(Base):
    """Nhóm thành phẩm — tự sinh từ `OrderLine.nhom` (§3.1). KHÔNG bắt người dùng nhập lại tên;
    dòng đơn không có `nhom` thành một nhóm đơn lẻ. Kế hoạch KHÔNG được tự ghép/tách nhóm — sai
    thì sửa từ Sale/đơn hàng trước khi phát hành.

    `khoa` = định danh ỔN ĐỊNH trong một đơn: dùng `nhom` nếu có, ngược lại `line:<order_line_id>`
    (để nhiều dòng không-nhom trong cùng đơn không đụng nhau). `than_chinh_lsx_id` = LSX thân chính
    tiếp tục đi tới KCS cuối sau bước ghép đầu tiên (§3.2)."""

    __tablename__ = "san_xuat_nhom"
    __table_args__ = (UniqueConstraint("order_id", "khoa", name="uq_san_xuat_nhom_order_khoa"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ma: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    khoa: Mapped[str] = mapped_column(String(160), nullable=False)
    nhom_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ten: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    than_chinh_lsx_id: Mapped[int | None] = mapped_column(
        ForeignKey("lsx.id", ondelete="SET NULL"), nullable=True
    )
    trang_thai: Mapped[str] = mapped_column(String(24), nullable=False, default=NHOM_DANG_SX)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    thanh_viens: Mapped[list["SanXuatNhomLsx"]] = relationship(
        back_populates="nhom", cascade="all, delete-orphan"
    )


class SanXuatNhomLsx(Base):
    """Dòng thành viên nhóm — nhóm ↔ LSX. Mỗi LSX thuộc TỐI ĐA 1 nhóm (`lsx_id` unique). Neo
    `order_line_id` để truy vết nguồn nhóm (OrderLine.nhom). `la_than_chinh` đánh dấu LSX thân
    chính (đúng một dòng/nhóm sau bước ghép đầu)."""

    __tablename__ = "san_xuat_nhom_lsx"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nhom_id: Mapped[int] = mapped_column(
        ForeignKey("san_xuat_nhom.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lsx_id: Mapped[int] = mapped_column(
        ForeignKey("lsx.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    order_line_id: Mapped[int | None] = mapped_column(
        ForeignKey("order_lines.id", ondelete="SET NULL"), nullable=True
    )
    la_than_chinh: Mapped[bool] = mapped_column(
        nullable=False, server_default=sa_false(), default=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    nhom: Mapped["SanXuatNhom"] = relationship(back_populates="thanh_viens")


class SanXuatGoiPhatHanh(Base):
    """Gói phát hành = một THÀNH PHẦN LIÊN THÔNG (§4.1): một nhóm + các LSX + phụ thuộc chéo +
    Bài ghép dùng chung + các nhóm khác bị nối qua cùng Bài ghép. Toàn bộ phát hành NGUYÊN TỬ.
    `version_hien_tai` trỏ tới `san_xuat_phien_ban.so` đang hiệu lực; mỗi lần "Phát hành cập nhật"
    tăng số và đẻ một phiên bản mới (giữ lịch sử đủ)."""

    __tablename__ = "san_xuat_goi_phat_hanh"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ma: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    trang_thai: Mapped[str] = mapped_column(
        String(24), nullable=False, default=GOI_DANG_PHAT_HANH
    )
    version_hien_tai: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    phien_bans: Mapped[list["SanXuatPhienBan"]] = relationship(
        back_populates="goi", cascade="all, delete-orphan"
    )


class SanXuatPhienBan(Base):
    """Phiên bản phát hành/cập nhật của một gói (§4.3). `so` tăng 1,2,3…; `loai` phân biệt lần
    phát hành đầu với các lần cập nhật; `ly_do` bắt buộc khi cập nhật. Lịch sử phiên bản giữ đủ
    — KHÔNG xoá phiên bản cũ."""

    __tablename__ = "san_xuat_phien_ban"
    __table_args__ = (UniqueConstraint("goi_id", "so", name="uq_san_xuat_phien_ban_goi_so"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    goi_id: Mapped[int] = mapped_column(
        ForeignKey("san_xuat_goi_phat_hanh.id", ondelete="CASCADE"), nullable=False, index=True
    )
    so: Mapped[int] = mapped_column(Integer, nullable=False)
    loai: Mapped[str] = mapped_column(String(16), nullable=False, default=PB_PHAT_HANH)
    ly_do: Mapped[str | None] = mapped_column(String(500), nullable=True)
    phat_hanh_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    goi: Mapped["SanXuatGoiPhatHanh"] = relationship(back_populates="phien_bans")


class SanXuatCongViec(Base):
    """Công việc (work item) — SNAPSHOT một công đoạn tại lúc phát hành + NEO trạng thái thực thi
    (§4.2, §18). Một dòng cho mỗi công đoạn LSX (hoặc mỗi công đoạn Bài ghép dùng chung) trong
    phiên bản đang hiệu lực của gói. Thanh KẾ HOẠCH giữ nguyên theo phiên bản đã phát hành; lớp
    THỰC TẾ (pha sau) đè lên.

    Đóng băng theo §4.2: tổ (`department_id`) + trạng thái KCS (`la_kcs`, `la_kcs_cuoi`), máy,
    thời gian/ca dự kiến, định mức + đơn vị + `khoan_json`, dữ liệu vật tư. Neo công đoạn nguồn
    bằng `step_key` + id LỎNG (không FK — replace_routing tái sinh id; xem docstring module).

    `phien_ban_so` cho biết snapshot thuộc phiên bản nào — cập nhật lịch đẻ dòng mới ở phiên bản
    mới, KHÔNG sửa đè dòng cũ (giữ lịch sử)."""

    __tablename__ = "san_xuat_cong_viec"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    goi_id: Mapped[int] = mapped_column(
        ForeignKey("san_xuat_goi_phat_hanh.id", ondelete="CASCADE"), nullable=False, index=True
    )
    phien_ban_so: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    nhom_id: Mapped[int | None] = mapped_column(
        ForeignKey("san_xuat_nhom.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Neo THẬT (ổn định): LSX / Bài ghép. Công đoạn neo LỎNG (step_key + id, không FK).
    lsx_id: Mapped[int | None] = mapped_column(
        ForeignKey("lsx.id", ondelete="SET NULL"), nullable=True, index=True
    )
    bai_ghep_id: Mapped[int | None] = mapped_column(
        ForeignKey("bai_ghep.id", ondelete="SET NULL"), nullable=True, index=True
    )
    lsx_cong_doan_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bai_ghep_cong_doan_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    step_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ten_cong_doan: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    nhom_cong_doan: Mapped[str | None] = mapped_column(String(24), nullable=True)
    loai_buoc: Mapped[str] = mapped_column(String(16), nullable=False, default=BUOC_MAY)
    # Snapshot phòng/tổ thực hiện + trạng thái KCS (§2.2, §4.2).
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    la_kcs: Mapped[bool] = mapped_column(
        nullable=False, server_default=sa_false(), default=False
    )
    la_kcs_cuoi: Mapped[bool] = mapped_column(
        nullable=False, server_default=sa_false(), default=False
    )
    # KCS kiêm nhiệm (mg `0250`): SNAPSHOT ĐẦY ĐỦ checklist (danh mục + bổ sung LSX/bài ghép) tại
    # lúc PHÁT HÀNH — không chỉ phần bổ sung như `lsx_cong_doan.kcs_tieu_chi_bo_sung_json`. Task 3
    # mới thực sự GHI nội dung này; ở đây CHỈ khai cột, nullable (chưa phát hành qua luồng mới =
    # NULL, KHÔNG đoán). Hình dạng: list[{tieu_chi_id, ma, ten, huong_dan, bat_buoc, nguon, thu_tu}].
    kcs_tieu_chi_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Khoá MỀM → `may_thiet_bi.id` (danh mục máy ĐANG CHẠY), đúng quy ước của `lsx_cong_doan`
    # / `xep_lich_cong_doan` / `bai_ghep`. Trước mig `0237` đây là FK CỨNG trỏ `machines` —
    # danh mục đời tính giá, id lệch hẳn — nên bước dùng máy ngoài dải đó là phát hành VỠ.
    may_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Thời gian/ca dự kiến (đóng băng từ xep_lich_cong_doan).
    du_kien_bat_dau: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    du_kien_ket_thuc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Định mức, đơn vị, khoán, vật tư (JSON snapshot).
    so_luong_vao: Mapped[float | None] = mapped_column(Numeric(18, 3), nullable=True)
    so_luong_ra: Mapped[float | None] = mapped_column(Numeric(18, 3), nullable=True)
    don_vi_vao: Mapped[str | None] = mapped_column(String(40), nullable=True)
    don_vi_ra: Mapped[str | None] = mapped_column(String(40), nullable=True)
    he_so_quy_doi: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    dinh_muc_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    khoan_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    vat_tu_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    trang_thai: Mapped[str] = mapped_column(String(16), nullable=False, default=CV_PHAT_HANH)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class SanXuatPhuThuoc(Base):
    """Cạnh phụ thuộc chéo giữa hai LSX cùng nhóm — SNAPSHOT bước ghép (§3.2). Chỉ tồn tại giữa
    LSX cùng một nhóm thành phẩm. Đóng băng: công đoạn nguồn/đích (qua công việc), tỷ lệ ghép,
    đơn vị nguồn/đích, quy tắc quy đổi, số lượng yêu cầu. Sản lượng bước ghép bị chặn trên bởi
    đầu vào bắt buộc ÍT NHẤT sau quy đổi (§3.2 cuối) — tính ở service, không cache."""

    __tablename__ = "san_xuat_phu_thuoc"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    goi_id: Mapped[int] = mapped_column(
        ForeignKey("san_xuat_goi_phat_hanh.id", ondelete="CASCADE"), nullable=False, index=True
    )
    phien_ban_so: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    nhom_id: Mapped[int] = mapped_column(
        ForeignKey("san_xuat_nhom.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nguon_cong_viec_id: Mapped[int] = mapped_column(
        ForeignKey("san_xuat_cong_viec.id", ondelete="CASCADE"), nullable=False
    )
    dich_cong_viec_id: Mapped[int] = mapped_column(
        ForeignKey("san_xuat_cong_viec.id", ondelete="CASCADE"), nullable=False
    )
    ty_le_ghep: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    don_vi_nguon: Mapped[str | None] = mapped_column(String(40), nullable=True)
    don_vi_dich: Mapped[str | None] = mapped_column(String(40), nullable=True)
    quy_tac_quy_doi: Mapped[str | None] = mapped_column(String(120), nullable=True)
    so_luong_yeu_cau: Mapped[float | None] = mapped_column(Numeric(18, 3), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
