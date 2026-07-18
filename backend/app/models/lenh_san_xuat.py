"""Kế hoạch & Lệnh sản xuất (P0 data layer) — spec `docs/spec-ke-hoach-san-xuat.md`.

7 bảng (máy CHỈ GHI NHẬN — không MRP/validate; `routing_step` sửa tay ở kế hoạch, trạng thái qua QR):
  - `LenhSanXuat` (`lenh_sx`)   — Lệnh SX = 1 ấn phẩm/cấu phần = 1 routing (traveler qua các tổ).
  - `PrintForm`   (`print_form`) — Tờ in = 1 lượt chạy máy vật lý (1 bộ kẽm · 1 lần canh) = NƠI ghép.
  - `GangPlacement`(`gang_placement`) — danh sách xếp bài: tờ in ↔ lệnh + SỐ CON (nguồn sự thật ghép).
  - `SanLuong`    (`san_luong`)  — log sản lượng theo công đoạn (số đạt / số hỏng).
  - `BanGiao`     (`ban_giao`)   — log bàn giao giữa công đoạn/tổ (giao → xác nhận nhận).
  - `QcDefect`    (`qc_defect`)  — phiếu lỗi QC (QC nêu → tổ trưởng xác nhận). Disposition = P1.
  - `RoutingStep` (`routing_step`) — routing RIÊNG mỗi lệnh (§13.2): copy công đoạn từ job spec PTG
    khi bung; kế hoạch sửa được khi bước còn chờ; trạng thái (chờ/đang/xong) set qua QR (Chunk C).

Quy ước theo repo (order.py / phieu_tinh_gia.py / cong_doan.py):
  - `Mapped` / `mapped_column`, helper `_utcnow`, timestamp `DateTime(timezone=True)`.
  - FK MỀM (soft-ref) = plain `Integer` (KHÔNG ForeignKey) khớp convention danh mục của repo
    (`phieu_thanh_phan_id`, `may_id`, `giay_id`, `cong_doan_id`, tổ = `departments.id`).
  - FK THẬT chỉ cho quan hệ sở hữu trong cùng module + tới `orders` (`order_id`) để cascade xoá.
  - ĐỌC quy cách / routing / vật tư từ PTG (`PhieuThanhPhan`/`PhieuThanhPham`) — KHÔNG chép lại.

BẪY DB (CLAUDE.md): KHÔNG Alembic. Bảng MỚI → `create_all` tự tạo (không đụng `db_migrations.py`).
Không có cột Boolean ở đây (trạng thái = chuỗi enum; "đã nhận"/"đã duyệt" suy từ cột `*_at` nullable)
→ tránh bẫy server_default bool. Cập nhật `docs/DB_SCHEMA.md` cùng lúc (guard test).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --- Lệnh SX: trạng thái (suy ra theo routing — record-only, KHÔNG bấm tay) --------
LENH_NHAP = "nhap"            # nháp (tự đề khi chốt đơn)
LENH_DANG_CHAY = "dang_chay"  # đang chạy (đã phát, đang qua các tổ)
LENH_XONG = "xong"            # xong (đủ SL thành phẩm nhập kho)
LENH_HUY = "huy"              # hủy
LENH_TRANG_THAI = (LENH_NHAP, LENH_DANG_CHAY, LENH_XONG, LENH_HUY)

# --- Tờ in: trạng thái phát (cổng phát = đã gán máy + MỌI lệnh duyệt mẫu, §8) ------
PF_CHO_GHEP = "cho_ghep"          # chờ ghép
PF_DU_DIEU_KIEN = "du_dieu_kien"  # đủ điều kiện (đã gán máy + duyệt mẫu AND)
PF_DA_PHAT = "da_phat"            # đã phát xuống xưởng
PF_IN_XONG = "in_xong"            # in xong
PF_TRANG_THAI = (PF_CHO_GHEP, PF_DU_DIEU_KIEN, PF_DA_PHAT, PF_IN_XONG)

# --- QC: trạng thái xác nhận (QC nêu → tổ trưởng xác nhận, §8) ---------------------
QC_CHO = "cho"                          # QC nêu, CHỜ tổ trưởng xác nhận (chưa thành lỗi chính thức)
QC_XAC_NHAN = "to_truong_xac_nhan"      # tổ trưởng đã xác nhận → lỗi ghi nhận chính thức
QC_TRANG_THAI = (QC_CHO, QC_XAC_NHAN)

# --- Routing step: trạng thái bước (chờ → đang → xong) — set qua QR ở màn thực thi (Chunk C) ------
RS_CHO = "cho"      # chờ tới lượt (còn sửa được ở kế hoạch)
RS_DANG = "dang"    # đang chạy (đã khóa sửa)
RS_XONG = "xong"    # xong (đã khóa sửa)
RS_TRANG_THAI = (RS_CHO, RS_DANG, RS_XONG)


class LenhSanXuat(Base):
    """Lệnh SX = 1 ấn phẩm/cấu phần in = 1 routing (ruột · bìa · name card · tem…).

    Thuộc 1 đơn; đọc quy cách/routing/vật tư từ PTG qua `phieu_thanh_phan_id` (KHÔNG nhập lại).
    Móc n–n với tờ in qua `gang_placement`.
    """

    __tablename__ = "lenh_sx"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Đơn sở hữu lệnh (FK thật — cascade xoá theo đơn).
    order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("orders.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Ấn phẩm nguồn (soft → phieu_thanh_phan.id): đọc giấy/khổ/màu/số con + routing (PhieuThanhPham).
    phieu_thanh_phan_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    # Máy gán cho lệnh (soft → may_thiet_bi.id); máy chạy THỰC gán ở tờ in.
    may_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    trang_thai: Mapped[str] = mapped_column(String(16), nullable=False, default=LENH_NHAP)

    # --- Cụm duyệt mẫu (§5): con dấu người + giờ + snapshot đóng băng {tổ·chức vụ·tên} ---
    mau_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mau_approved_by: Mapped[int | None] = mapped_column(Integer, nullable=True)  # → users.id (soft)
    # Đóng băng danh tính người duyệt tại thời điểm duyệt: {"to":..., "chuc_vu":..., "ten":...}.
    mau_approved_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class PrintForm(Base):
    """Tờ in = 1 lượt chạy máy vật lý (1 bộ kẽm · 1 lần canh máy) — NƠI ghép bài.

    Móc n–n với lệnh qua `gang_placement` (+ số con). Giấy/khổ/số màu là ẢNH CHỤP để người
    kế hoạch dễ nhìn (đọc gợi ý từ PTG) — máy KHÔNG lọc/chặn/cảnh báo.
    """

    __tablename__ = "print_form"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # --- Giấy (soft → giay_nguyen.id) + nhãn hiển thị ---
    giay_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    giay_label: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # --- Khổ tờ in (mm) ---
    kho_in_dai: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    kho_in_rong: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    so_mau: Mapped[int] = mapped_column(Integer, nullable=False, default=0)   # số màu (bộ kẽm cả tờ)
    may_id: Mapped[int | None] = mapped_column(Integer, nullable=True)        # → may_thiet_bi.id (soft)
    so_to_chay: Mapped[int] = mapped_column(Integer, nullable=False, default=0)   # số tờ chạy
    so_kem: Mapped[int] = mapped_column(Integer, nullable=False, default=0)       # số kẽm

    trang_thai: Mapped[str] = mapped_column(String(16), nullable=False, default=PF_CHO_GHEP)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class GangPlacement(Base):
    """Danh sách xếp bài (placement) = "cái bóng kế toán" của ghép — 1 dòng: tờ · lệnh · số con.

    Số con NHẬP TAY (dàn bài là việc chế bản ngoài ERP). Nguồn sự thật của ghép (§3).
    """

    __tablename__ = "gang_placement"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    print_form_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("print_form.id", ondelete="CASCADE"), index=True, nullable=False
    )
    lenh_sx_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lenh_sx.id", ondelete="CASCADE"), index=True, nullable=False
    )
    so_con: Mapped[int] = mapped_column(Integer, nullable=False, default=0)   # con/tờ của lệnh này

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class SanLuong(Base):
    """Log sản lượng (tổ chạy) — tổ trưởng ghi số đạt + số hỏng cho 1 công đoạn của 1 lệnh (§8).

    Log thuần — KHÔNG state-machine. Khoán (số đạt × đơn giá) = P2, đọc lại số từ đây.
    """

    __tablename__ = "san_luong"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lenh_sx_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lenh_sx.id", ondelete="CASCADE"), index=True, nullable=False
    )
    cong_doan_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # → cong_doan.id (soft)
    to_id: Mapped[int | None] = mapped_column(Integer, nullable=True)         # tổ thực hiện → departments.id (soft)
    so_dat: Mapped[int] = mapped_column(Integer, nullable=False, default=0)   # số đạt
    so_hong: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # số hỏng
    nguoi_ghi: Mapped[int | None] = mapped_column(Integer, nullable=True)     # tổ trưởng ghi → users.id (soft)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )   # thời điểm ghi


class BanGiao(Base):
    """Log bàn giao (§8) — tổ trưởng GIAO số đạt sang công đoạn/tổ kế → tổ kế XÁC NHẬN NHẬN.

    Record-only: ghi giao + nhận (lệch số để sau truy). `nhan_at` NULL = chưa xác nhận nhận.
    """

    __tablename__ = "ban_giao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lenh_sx_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lenh_sx.id", ondelete="CASCADE"), index=True, nullable=False
    )
    cong_doan_tu_id: Mapped[int | None] = mapped_column(Integer, nullable=True)   # công đoạn TỪ → cong_doan.id (soft)
    cong_doan_toi_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # công đoạn TỚI → cong_doan.id (soft)
    so_giao: Mapped[int] = mapped_column(Integer, nullable=False, default=0)      # số giao
    to_giao_id: Mapped[int | None] = mapped_column(Integer, nullable=True)        # tổ giao → departments.id (soft)
    to_nhan_id: Mapped[int | None] = mapped_column(Integer, nullable=True)        # tổ nhận → departments.id (soft)

    giao_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )   # thời điểm giao (= lúc tạo bản ghi)
    nhan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # xác nhận nhận (nullable)


class QcDefect(Base):
    """Phiếu lỗi QC (§8) — QC nêu (ảnh + tổ bị quy + công đoạn + mô tả) → tổ trưởng XÁC NHẬN.

    Record-only 2 bước (`created_at` = QC nêu, `xac_nhan_at` = tổ trưởng xác nhận). Chưa xác nhận =
    chưa thành lỗi chính thức. KHÔNG tự quy lỗi / trừ khoán / quyết in bù — disposition để P1.
    """

    __tablename__ = "qc_defect"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lenh_sx_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lenh_sx.id", ondelete="CASCADE"), index=True, nullable=False
    )
    cong_doan_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # → cong_doan.id (soft)
    to_bi_quy_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # tổ bị quy → departments.id (soft)
    anh_url: Mapped[str | None] = mapped_column(String(500), nullable=True)   # ảnh minh chứng (url/path)
    mo_ta: Mapped[str | None] = mapped_column(Text, nullable=True)            # mô tả lỗi

    trang_thai: Mapped[str] = mapped_column(String(24), nullable=False, default=QC_CHO)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )   # QC nêu
    xac_nhan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # tổ trưởng xác nhận


class RoutingStep(Base):
    """1 bước routing của lệnh SX (spec §13.2) — copy công đoạn từ job spec PTG (`PhieuThanhPham`)
    khi bung lệnh; kế hoạch SỬA được (thêm/bớt/đổi thứ tự/đổi tổ) khi bước còn CHỜ. Tổ phụ trách
    (`to_id`) = ảnh chụp `cong_doan.department_id` lúc copy (đổi được). Trạng thái set qua quét QR
    ở màn tổ (Chunk C). Routing RIÊNG trên lệnh → sửa KHÔNG đụng phiếu tính giá.
    """

    __tablename__ = "routing_step"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lenh_sx_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lenh_sx.id", ondelete="CASCADE"), index=True, nullable=False
    )
    thu_tu: Mapped[int] = mapped_column(Integer, nullable=False, default=0)    # thứ tự bước trong routing
    cong_doan_id: Mapped[int | None] = mapped_column(Integer, nullable=True)   # → cong_doan.id (soft)
    to_id: Mapped[int | None] = mapped_column(Integer, nullable=True)          # tổ phụ trách → departments.id (soft; snapshot cong_doan.department_id)
    ten: Mapped[str] = mapped_column(String(255), nullable=False, default="")  # tên công đoạn (ảnh chụp để hiển thị)

    trang_thai: Mapped[str] = mapped_column(String(16), nullable=False, default=RS_CHO)
    bat_dau_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)     # bắt đầu (quét QR)
    hoan_thanh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # hoàn thành (quét QR)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
