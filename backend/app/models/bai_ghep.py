"""Bài ghép (print gang) — gom các công đoạn chạy CHUNG của NHIỀU LSX trên 1 tờ, 1 lần lên máy.

Đối tượng KẾ HOẠCH: chỉ quản phần CHẠY CHUNG. Chung KHÔNG chỉ có mỗi bước in — cùng một tờ
ghép thì bộ kẽm là một (CTP chung), cán màng cán cả tờ, bế chung nếu cùng dao; điểm TOẢ nằm sau
bước gộp cuối cùng, không phải cứ sau in. NGƯỜI khai bước nào chung (xem `bai_ghep_cong_doan`),
máy không tự đoán. Mỗi LSX vẫn giữ nguyên mã/số lượng/hạn/routing-riêng/chi phí; qua điểm toả
thì tách ra chạy tiếp riêng. Không gộp lệnh, không nuốt LSX (khớp mô hình gang chuẩn ngành:
Phoenix Layout→Product, printIQ parent/sub "revert to standard job").

NEO THÀNH VIÊN VÀO `lsx_id` (FK THẬT), KHÔNG vào công đoạn: sửa routing LSX = replace-all →
`lsx_cong_doan.id` tái sinh, neo công đoạn sẽ mất dấu. Mỗi LSX vào TỐI ĐA 1 bài ghép (ca 1 LSX
nhiều công đoạn in → pha sau). "LSX đã ghép chưa" suy qua `NOT EXISTS(bai_ghep_thanh_vien)`, không
cột cache.

Số dẫn xuất (số tờ tốt / sản lượng dự kiến / dư / tổng tờ / hạn in muộn nhất / % tờ dùng) TÍNH
LÚC ĐỌC ở service — KHÔNG lưu cột (tránh 2 nguồn sự thật, bám precedent `lsx_service`).

RBAC MODULE = "san_xuat" (tái dùng, không đẻ quyền mới). Bảng mới → `create_all` tự tạo, KHÔNG
migration. Boolean (nếu phát sinh) dùng `false()`/`true()` của SQLAlchemy — bẫy Postgres.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    DateTime, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base

# --- Trạng thái (song song LSX). `da_lap_ke_hoach` (≈ Firm Planned) ĐÃ dùng: set qua service xếp lịch,
# khóa sửa thành viên/giấy — gỡ kế hoạch để mở lại. `da_phat_hanh` (≈ Released) ĐÃ dùng: gate xung đột
# 0-Chặn → thả xuống xưởng (cả thành viên). Các mốc sau (`dang_in`, `da_in_xong`, `da_xa_to`,
# `hoan_thanh`) thuộc pha thực thi, CHƯA dùng.
TT_NHAP = "nhap"            # vừa tạo / đang cấu hình giấy·khổ·thành viên
TT_SAN_SANG = "san_sang"   # qua checklist tối thiểu → sẵn sàng xếp lịch
TT_DA_LAP_KE_HOACH = "da_lap_ke_hoach"  # đã sinh dòng xếp lịch → khóa sửa thành viên/giấy
TT_DA_PHAT_HANH = "da_phat_hanh"        # đã phát hành xuống xưởng (Released)
TRANG_THAI_BAI_GHEP = (TT_NHAP, TT_SAN_SANG, TT_DA_LAP_KE_HOACH, TT_DA_PHAT_HANH)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BaiGhep(Base):
    """Header một bài ghép — giấy + khổ tờ in chạy chung + máy + hao hụt. Thành viên ở `thanh_viens`."""

    __tablename__ = "bai_ghep"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ma: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)  # GB26-0001

    trang_thai: Mapped[str] = mapped_column(String(20), nullable=False, default=TT_NHAP)

    # --- Giấy + khổ tờ in CHẠY CHUNG (một tờ ghép chỉ một loại giấy) ---
    giay_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)  # → giay_nguyen.id
    kho_in_dai: Mapped[int | None] = mapped_column(Integer, nullable=True)   # mm
    kho_in_rong: Mapped[int | None] = mapped_column(Integer, nullable=True)  # mm
    may_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)   # → may_thiet_bi.id

    # --- Hao hụt tờ (người khai) — cộng vào số tờ tốt để ra tổng tờ cấp ---
    hao_hut_setup: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # bù canh máy
    hao_hut_chay: Mapped[int] = mapped_column(Integer, nullable=False, default=0)   # bù khi chạy

    ghi_chu: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)  # → users.id
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    # Để SQLAlchemy tự xoá thành viên khi xoá bài (đúng trên cả SQLite lẫn Postgres); `ondelete`
    # dưới FK là lớp chặn cuối ở DB. KHÔNG `passive_deletes` (SQLite dev mặc định tắt PRAGMA FK).
    thanh_viens: Mapped[list["BaiGhepThanhVien"]] = relationship(
        "BaiGhepThanhVien",
        back_populates="bai_ghep",
        order_by="BaiGhepThanhVien.id",
        cascade="all, delete-orphan",
    )


class BaiGhepThanhVien(Base):
    """1 LSX tham gia bài ghép (gang member). Neo `lsx_id` (FK THẬT), số con/tờ trong bài do người khai."""

    __tablename__ = "bai_ghep_thanh_vien"
    # Chống thêm TRÙNG một LSX vào cùng một bài (guard "1 LSX ≤ 1 bài" nằm ở service, cross-table).
    __table_args__ = (UniqueConstraint("bai_ghep_id", "lsx_id", name="uq_bai_ghep_lsx"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # FK THẬT + CASCADE: xoá bài → xoá thành viên.
    bai_ghep_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bai_ghep.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # FK THẬT + RESTRICT: chặn xoá LSX đang ghép ở tầng DB (Postgres). Nguồn/cấu trúc = FK thật
    # theo convention repo (khác FK danh mục mềm).
    lsx_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lsx.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    # Số con của LSX này trên tờ ghép (ups). INPUT người sửa (bố cục ghép khác in riêng); mặc định
    # = `lsx.so_con`. Số tờ tốt = max_i(ceil(lsx.so_luong_dat / so_con_tren_to)).
    so_con_tren_to: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # DEPRECATED — thay bằng `bai_ghep_cong_doan` + `bai_ghep_cong_doan_map`. Cột này giả định
    # "bước in là điểm gộp DUY NHẤT", sai với thực tế (còn CTP/cán/bế chung) và không diễn tả nổi
    # nhiều bước gộp. Giữ cột để không vỡ dữ liệu đang có; ngừng ĐỌC ở code mới. Gỡ ở đợt dọn
    # riêng (cần `db_migrations.py` + `DB_SCHEMA.md`), không gỡ giữa lúc refactor.
    buoc_in_step_key: Mapped[str | None] = mapped_column(String(40), nullable=True)

    bai_ghep: Mapped["BaiGhep"] = relationship("BaiGhep", back_populates="thanh_viens")
