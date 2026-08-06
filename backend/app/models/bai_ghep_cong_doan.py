"""Công đoạn CHUNG của bài ghép — lớp GHI ĐÈ lên bước tương ứng của từng LSX thành viên.

Ghép bài không chỉ chung mỗi bước in: cùng một tờ ghép thì bộ kẽm là một (CTP chung), cán màng
cán cả tờ (cán chung), và bế cũng chung nếu các lệnh cùng dao. Trước đây service tự dò bước in
rồi đúc thành một node duy nhất — vừa đoán thay người, vừa chỉ gộp được đúng một bước, vừa làm
mỗi lệnh tự cộng một bộ hao canh máy cho CÙNG một lần lên máy.

Nay NGƯỜI khai: chọn các bước cùng công đoạn ở nhiều lệnh rồi gộp. Mỗi lần gộp sinh MỘT dòng ở
đây (`bai_ghep_cong_doan`) + các dòng ánh xạ (`bai_ghep_cong_doan_map`) trỏ về bước gốc của từng
lệnh. Dòng này mang kế hoạch THẬT của lượt chạy chung: một tổ, một máy, một lần hao, một thời
lượng.

GHI ĐÈ, KHÔNG PHÁ GỐC. Bước của LSX vẫn còn nguyên trong `lsx_cong_doan` với số của nó; tách gộp
ra là số cũ quay lại, không phải khôi phục từ đâu cả. Engine chỉ việc "chỗ nào bị đè thì lấy số
của bài".

CHỈ CHỨA KẾ HOẠCH. Sáu cột thực-tế-giao-nhận của `lsx_cong_doan` (`giao_luc`, `sl_giao_thuc`,
`nhan_luc`…) CỐ Ý không mirror sang đây — ghi nhận hàng đi/về là việc của pha thực thi.

PHỤ THUỘC KHÔNG LƯU Ở ĐÂY. Cạnh của bài là DẪN XUẤT: lấy cạnh sẵn có giữa các bước của lệnh rồi
thay mỗi bước đã gộp bằng dòng chung của nó. Khai ở hai nơi là hai nguồn sự thật.

Bảng MỚI → `create_all` tự tạo, KHÔNG migration (bám precedent `bai_ghep`).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text,
    UniqueConstraint, true as sa_true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base
from .lsx import LB_MAY


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BaiGhepCongDoan(Base):
    """1 công đoạn chạy CHUNG của bài — cùng hình dạng kế hoạch với `LsxCongDoan`."""

    __tablename__ = "bai_ghep_cong_doan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    step_key: Mapped[str] = mapped_column(
        String(36), unique=True, index=True, nullable=False, default=lambda: str(uuid4())
    )
    bai_ghep_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bai_ghep.id", ondelete="CASCADE"), index=True, nullable=False
    )
    thu_tu: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # --- Nhận diện (khớp bước gốc — điều kiện gộp là CÙNG công đoạn) ---
    cong_doan_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    ten: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    nhom: Mapped[str | None] = mapped_column(String(12), nullable=True)
    loai_buoc: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default=LB_MAY, default=LB_MAY
    )
    bat_buoc: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_true(), default=True
    )

    # --- Phân công: MỘT lượt chạy thì một tổ, một máy, một kíp ---
    department_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    may_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    so_nhan_cong: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1", default=1)
    so_nhan_cong_tieu_chuan: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1", default=1
    )
    so_nhan_cong_toi_da: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Mirror `lsx_cong_doan.so_nhan_cong_toi_thieu` — bước chung của bài cũng là một bước có kế hoạch.
    so_nhan_cong_toi_thieu: Mapped[int | None] = mapped_column(Integer, nullable=True)
    khoan_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # --- Số lượng & hao hụt: tính ở ĐƠN VỊ TỜ GHÉP, hao đếm ĐÚNG MỘT LẦN cho cả lượt ---
    so_luong_vao: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    so_luong_ra: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    don_vi_vao: Mapped[str | None] = mapped_column(String(12), nullable=True)
    don_vi_ra: Mapped[str | None] = mapped_column(String(12), nullable=True)
    he_so_quy_doi: Mapped[float] = mapped_column(
        Numeric(12, 4), nullable=False, server_default="1", default=1
    )
    # Cặp hao kiểu BC: `hao_hut` = số tờ cố định (canh máy), `hao_hut_pct` = % theo độ dài lượt.
    # Tách đôi vì hai thứ áp khác nhau, và vì `bai_ghep` đã có sẵn hai ô setup/chạy tương ứng.
    hao_hut: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    hao_hut_pct: Mapped[float] = mapped_column(
        Numeric(6, 2), nullable=False, server_default="0", default=0
    )
    so_luot_chay: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1", default=1)

    # --- Thời gian (phút) — một lượt chạy, một khoảng chiếm máy ---
    setup_phut: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default="0", default=0)
    nang_suat: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    # String(32) — cùng lý do với `lsx_cong_doan.don_vi_nang_suat` (mã đơn vị người khai chọn).
    don_vi_nang_suat: Mapped[str | None] = mapped_column(String(32), nullable=True)
    chay_phut: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    # DORMANT 2026-08-04 — mirror `LsxCongDoan.ve_sinh_phut`, cùng lý do: bỏ khỏi hệ, giữ cột.
    ve_sinh_phut: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default="0", default=0)
    # "Thời gian khác" (migration 0153) — mirror `LsxCongDoan.phat_sinh_phut`.
    phat_sinh_phut: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default="0", default=0)
    cho_phut: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default="0", default=0)
    di_chuyen_phut: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default="0", default=0)

    # --- Gia công ngoài (DỰ KIẾN). Bước chung thuê ngoài thì cả bài đi một phiếu, một NCC. ---
    nha_cung_cap: Mapped[str | None] = mapped_column(String(150), nullable=True)
    sl_gui: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    ngay_gui_dk: Mapped[date | None] = mapped_column(Date, nullable=True)
    van_chuyen_ngay: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    gia_cong_ngay: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    ngay_nhan_dk: Mapped[date | None] = mapped_column(Date, nullable=True)
    hao_hut_cho_phep: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    don_gia_gia_cong: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    yeu_cau_ky_thuat: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Ghi chú của BÀI. Ghi chú kỹ thuật của từng lệnh KHÔNG bị đè — service gom lại kèm mã lệnh,
    # vì thợ chạy chung một lượt phải đọc được yêu cầu của mọi khách trên tờ đó.
    ghi_chu: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    thanh_phans: Mapped[list["BaiGhepCongDoanMap"]] = relationship(
        "BaiGhepCongDoanMap", back_populates="buoc_chung", cascade="all, delete-orphan"
    )
    vat_tus: Mapped[list["BaiGhepCongDoanVatTu"]] = relationship(
        "BaiGhepCongDoanVatTu", back_populates="buoc_chung",
        order_by="BaiGhepCongDoanVatTu.thu_tu", cascade="all, delete-orphan",
    )


class BaiGhepCongDoanMap(Base):
    """Dòng chung này ĐÈ lên bước nào của lệnh nào.

    Neo bằng `lsx_step_key` chứ không bằng `lsx_cong_doan.id`: sửa routing của lệnh là
    replace-all → `id` tái sinh, neo theo id sẽ mất dấu (đúng bài học đã neo thành viên vào
    `lsx_id` thay vì vào công đoạn).
    """

    __tablename__ = "bai_ghep_cong_doan_map"
    __table_args__ = (
        # Một bước của lệnh chỉ được đè bởi ĐÚNG MỘT dòng chung.
        UniqueConstraint("lsx_step_key", name="uq_bgcd_map_lsx_step"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bai_ghep_cong_doan_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bai_ghep_cong_doan.id", ondelete="CASCADE"), index=True, nullable=False
    )
    lsx_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    lsx_step_key: Mapped[str] = mapped_column(String(36), index=True, nullable=False)

    buoc_chung: Mapped["BaiGhepCongDoan"] = relationship(
        "BaiGhepCongDoan", back_populates="thanh_phans"
    )


class BaiGhepCongDoanVatTu(Base):
    """Vật tư của bước chung — mực, kẽm, màng… dùng cho cả lượt, không của riêng lệnh nào."""

    __tablename__ = "bai_ghep_cong_doan_vat_tu"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bai_ghep_cong_doan_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bai_ghep_cong_doan.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Mirror ĐÚNG `LsxCongDoanVatTu` (kể cả kiểu snapshot) để drawer dùng lại không phải rẽ nhánh.
    vat_tu_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    vat_tu_ma_snapshot: Mapped[str] = mapped_column(String(30), nullable=False)
    vat_tu_ten_snapshot: Mapped[str] = mapped_column(String(150), nullable=False)
    don_vi_snapshot: Mapped[str] = mapped_column(String(16), nullable=False)
    so_luong: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    thu_tu: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    buoc_chung: Mapped["BaiGhepCongDoan"] = relationship(
        "BaiGhepCongDoan", back_populates="vat_tus"
    )
