"""Kỹ thuật máy — phiếu SỬA CHỮA (máy hỏng) + phiếu BẢO TRÌ định kỳ + ảnh minh chứng dùng chung.

Một vai thao tác duy nhất: **thợ sửa chữa**. Không bước duyệt, không tách người-sửa / người-nghiệm-thu
(chủ chốt 12/08/2026) ⇒ toàn bộ module gác bằng MỘT quyền `ky_thuat_may`.

Ba điều đáng nhớ trước khi sửa file này:

* **Chu kỳ bảo trì KHÔNG nằm ở đây.** Nguồn là `may_thiet_bi.fields_theo_loai["lich_bao_tri"]` —
  danh sách GÓI `{id, viec, so, don_vi, ngay_bat_dau, hang_muc[]}` do người khai máy dựng. Phiếu chỉ
  neo `goi_id` và SNAPSHOT lại tên/chu kỳ/việc con. Đừng đẻ bảng chu kỳ thứ hai: hai nơi khai chu kỳ
  là sớm muộn hai nơi lệch nhau mà không ai báo.
* **"Quá hạn" và "Đã dời" KHÔNG phải trạng thái lưu** — tính lúc đọc (`ngay_ke_hoach` đã qua mà chưa
  xong; `ngay_ke_hoach_goc` khác `ngay_ke_hoach`). Lưu thành cột là lại sinh ra thứ phải nhớ đi cập
  nhật, đúng bệnh của `may_thiet_bi.trang_thai` đã bị gỡ 11/08.
* **Đóng phiếu cần ảnh** — ràng buộc ở service (`ky_thuat_may_service`), không có cờ quyền nào bỏ
  qua được. Bảng ảnh dùng chung cho cả hai loại phiếu qua cặp (`loai_phieu`, `phieu_id`).

Bảng MỚI ⇒ `create_all` tự dựng, KHÔNG viết `db_migrations.py`. Nhưng phải ghi vào
`docs/DB_SCHEMA.md` cùng lúc — file đó có guard test.

🔴 **Vì sao tiền tố `ky_thuat_*` chứ không phải `bao_tri_phieu`:** module Bảo trì cũ bị gỡ
12/08/2026 nhưng ba bảng `bao_tri_phieu` · `bao_tri_hen` · `bao_tri_anh` VẪN NẰM LẠI trong Postgres
dev/prod (dự án không có Alembic nên không ai drop). `create_all` thấy bảng đã tồn tại là bỏ qua,
không ALTER ⇒ model mới sẽ trỏ vào bảng cũ thiếu cột: test chạy SQLite trắng thì xanh, DB thật thì
vỡ lúc lưu. Đặt tên khác là cách rẻ nhất để né, khỏi phải drop bảng người khác.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Date,
    DateTime,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# --- Phiếu sửa chữa: MỘT phiếu chạy từ lúc báo hỏng tới lúc sửa xong ---------------
# Cố ý không tách "phiếu báo hỏng" và "phiếu sửa chữa": cùng một cái máy, cùng một lần hỏng, tách
# hai chứng từ là bắt thợ nhập hai lần rồi tự đi nối lại.
TT_SC_CHO_SUA = "cho_sua"
TT_SC_DANG_SUA = "dang_sua"
TT_SC_CHO_VAT_TU = "cho_vat_tu"   # đã bắt tay vào nhưng thiếu đồ (lát này chỉ ghi chữ, chưa nối kho)
TT_SC_DA_SUA_XONG = "da_sua_xong"
TRANG_THAI_SUA_CHUA = (TT_SC_CHO_SUA, TT_SC_DANG_SUA, TT_SC_CHO_VAT_TU, TT_SC_DA_SUA_XONG)
TT_SC_DANG_MO = (TT_SC_CHO_SUA, TT_SC_DANG_SUA, TT_SC_CHO_VAT_TU)

MUC_DO_NHE = "nhe"
MUC_DO_TRUNG_BINH = "trung_binh"
MUC_DO_NGHIEM_TRONG = "nghiem_trong"
MUC_DO = (MUC_DO_NHE, MUC_DO_TRUNG_BINH, MUC_DO_NGHIEM_TRONG)

# --- Phiếu bảo trì ---------------------------------------------------------------
# 🔴 Bảo trì chỉ có HAI nấc (chủ chốt 12/08/2026): chờ làm → xong. Nấc "đang thực hiện" ĐÃ BỎ —
# nó bắt thợ bấm hai lần cho một việc, mà lần bấm đầu chẳng nói thêm được gì: bảo trì định kỳ làm
# xong trong một lượt, không phải việc kéo dài nhiều ngày cần theo dõi tiến độ.
# Ai bấm "Xác nhận đã bảo trì xong" thì CHÍNH người đó là người làm — không có bước nhận việc riêng.
TT_BT_CHO_THUC_HIEN = "cho_thuc_hien"
TT_BT_HOAN_THANH = "hoan_thanh"
TRANG_THAI_BAO_TRI = (TT_BT_CHO_THUC_HIEN, TT_BT_HOAN_THANH)
TT_BT_DANG_MO = (TT_BT_CHO_THUC_HIEN,)

LOAI_BT_DINH_KY = "dinh_ky"    # sinh từ gói trong `lich_bao_tri` của máy
LOAI_BT_DOT_XUAT = "dot_xuat"  # thợ tự lập, không thuộc gói nào ⇒ `goi_id` để trống
LOAI_BAO_TRI = (LOAI_BT_DINH_KY, LOAI_BT_DOT_XUAT)

# --- Ảnh minh chứng --------------------------------------------------------------
LOAI_PHIEU_SUA_CHUA = "sua_chua"
LOAI_PHIEU_BAO_TRI = "bao_tri"
LOAI_PHIEU = (LOAI_PHIEU_SUA_CHUA, LOAI_PHIEU_BAO_TRI)

GIAI_DOAN_TRUOC = "truoc"  # ảnh hiện trạng — KHUYẾN KHÍCH, không bắt buộc
GIAI_DOAN_SAU = "sau"      # ảnh chứng thực — BẮT BUỘC ≥1 tấm mới đóng được phiếu
GIAI_DOAN = (GIAI_DOAN_TRUOC, GIAI_DOAN_SAU)

MA_PREFIX_SUA_CHUA = "SC-"
MA_PREFIX_BAO_TRI = "PBT-"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SuaChuaMay(Base):
    """1 lần máy hỏng: ghi nhận → sửa → đóng phiếu kèm ảnh."""

    __tablename__ = "ky_thuat_sua_chua"
    __table_args__ = (
        # Màn lọc theo máy + theo trạng thái (tab), và cột danh sách sắp theo thời điểm báo.
        Index("ix_ky_thuat_sua_chua_trang_thai", "may_id", "trang_thai"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ma: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)  # SC-0001
    # FK MỀM theo convention repo (soft → `may_thiet_bi.id`): xoá máy không làm bay lịch sử hỏng hóc.
    may_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)

    bo_phan_hong: Mapped[str] = mapped_column(String(150), nullable=False)
    mo_ta: Mapped[str | None] = mapped_column(Text, nullable=True)          # triệu chứng thợ thấy
    muc_do: Mapped[str] = mapped_column(
        String(16), nullable=False, default=MUC_DO_TRUNG_BINH, server_default=MUC_DO_TRUNG_BINH
    )

    # Người BÁO hỏng — thường KHÁC người đang gõ (thợ đứng máy báo miệng, tổ kỹ thuật nhập hộ).
    # Vì thế là ô chọn nhân viên, không lấy mặc định từ user đăng nhập. Tên snapshot để 3 tháng sau
    # nhân viên nghỉ việc vẫn tra được ai báo.
    nguoi_bao_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)  # soft → employees.id
    nguoi_bao_ten: Mapped[str | None] = mapped_column(String(150), nullable=True)
    thoi_diem: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    nguyen_nhan_phuong_an: Mapped[str | None] = mapped_column(Text, nullable=True)  # ghi lúc sửa
    trang_thai: Mapped[str] = mapped_column(
        String(16), nullable=False, default=TT_SC_CHO_SUA, server_default=TT_SC_CHO_SUA
    )
    # Chỉ điền khi đóng phiếu. `hoan_thanh_at` là DẤU VẾT (giờ đóng), không dùng để tính chu kỳ.
    hoan_thanh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hoan_thanh_boi: Mapped[int | None] = mapped_column(Integer, nullable=True)  # soft → users.id
    ghi_chu: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class BaoTriMay(Base):
    """1 lần bảo trì của 1 gói trên 1 máy (hoặc 1 lần đột xuất không thuộc gói nào)."""

    __tablename__ = "ky_thuat_bao_tri"
    __table_args__ = (
        # Câu hỏi nóng nhất của service: "gói này còn phiếu nào đang mở không / hoàn thành lần chót
        # ngày nào" → luôn lọc theo (máy, gói).
        Index("ix_ky_thuat_bao_tri_may_goi", "may_id", "goi_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ma: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)  # PBT-0001
    may_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)  # soft → may_thiet_bi.id

    # NEO vào gói trong `may_thiet_bi.fields_theo_loai["lich_bao_tri"][].id` (dạng `hm-...`).
    # Null = phiếu đột xuất. Neo bằng id chứ không bằng tên: đổi tên gói vẫn giữ nguyên lịch sử.
    goi_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # SNAPSHOT lúc sinh phiếu — gói bị đổi tên/đổi chu kỳ/xoá về sau không làm sai phiếu đã in ra.
    goi_ten: Mapped[str | None] = mapped_column(String(150), nullable=True)
    chu_ky_so: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    chu_ky_don_vi: Mapped[str | None] = mapped_column(String(8), nullable=True)  # ngay|tuan|thang|nam

    loai: Mapped[str] = mapped_column(
        String(12), nullable=False, default=LOAI_BT_DINH_KY, server_default=LOAI_BT_DINH_KY
    )
    # Ngày (không giờ): chu kỳ khai theo ngày/tuần/tháng/năm nên mốc cũng ở mức NGÀY — bớt hẳn bẫy
    # naive/aware từng làm vỡ Xếp lịch.
    ngay_ke_hoach: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    # Giữ ngày dự kiến BAN ĐẦU để biết phiếu đã bị dời; "Đã dời" là dẫn xuất từ chỗ này.
    ngay_ke_hoach_goc: Mapped[date | None] = mapped_column(Date, nullable=True)
    ly_do_doi: Mapped[str | None] = mapped_column(String(300), nullable=True)

    # Checklist: [{id, ten, xong}] — snapshot `goi.hang_muc` + cột tick. Người khai sửa việc con
    # trên máy thì phiếu ĐÃ SINH vẫn giữ nguyên nội dung lúc giao việc.
    hang_muc: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # NGƯỜI LÀM — KHÔNG gõ tay, KHÔNG có bước nhận việc: ai bấm "Xác nhận đã bảo trì xong" thì hệ
    # ghi chính người đó (chủ chốt 12/08/2026). Tên là SNAPSHOT để người nghỉ việc rồi vẫn tra được.
    # Thuê hãng ngoài thì ghi vào `ghi_chu`, không đẻ ô riêng.
    nguoi_thuc_hien_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)  # soft → users.id
    nguoi_thuc_hien: Mapped[str | None] = mapped_column(String(150), nullable=True)

    trang_thai: Mapped[str] = mapped_column(
        String(16), nullable=False, default=TT_BT_CHO_THUC_HIEN, server_default=TT_BT_CHO_THUC_HIEN
    )
    # MỐC NGHIỆP VỤ để tính kỳ sau (`han_ke_tiep`) — ngày thợ làm xong, không phải giờ bấm nút.
    ngay_hoan_thanh: Mapped[date | None] = mapped_column(Date, nullable=True)
    hoan_thanh_boi: Mapped[int | None] = mapped_column(Integer, nullable=True)  # soft → users.id
    ghi_chu: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class KyThuatMayAnh(Base):
    """Ảnh minh chứng, dùng chung hai loại phiếu qua cặp (`loai_phieu`, `phieu_id`).

    Một bảng chứ không hai: hai bảng ảnh giống hệt nhau nghĩa là mọi chỗ đọc/xoá/đếm ảnh đều phải
    viết hai lần, và sớm muộn một trong hai bị quên (vd xoá phiếu mà ảnh nằm lại).
    """

    __tablename__ = "ky_thuat_may_anh"
    __table_args__ = (
        Index("ix_ktm_anh_phieu", "loai_phieu", "phieu_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    loai_phieu: Mapped[str] = mapped_column(String(12), nullable=False)  # sua_chua | bao_tri
    phieu_id: Mapped[int] = mapped_column(Integer, nullable=False)
    giai_doan: Mapped[str] = mapped_column(
        String(8), nullable=False, default=GIAI_DOAN_SAU, server_default=GIAI_DOAN_SAU
    )

    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    uploaded_by: Mapped[int | None] = mapped_column(Integer, nullable=True)  # soft → users.id
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
