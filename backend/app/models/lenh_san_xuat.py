"""Kế hoạch & Lệnh sản xuất (P0 data layer) — spec `docs/spec-ke-hoach-san-xuat.md`.

6 bảng (máy CHỈ GHI NHẬN — không MRP/validate; `routing_step` sửa tay ở kế hoạch):
  - `LenhSanXuat` (`lenh_sx`)   — Lệnh SX = 1..n ấn phẩm (pick gom) = 1 routing chung (traveler qua tổ).
  - `LenhItem`    (`lenh_item`) — bài con trong lệnh: lệnh ↔ ấn phẩm ↔ dòng đơn (nguồn sự thật ấn phẩm).
  - `PrintForm`   (`print_form`) — Tờ in = 1 lượt chạy máy vật lý (1 bộ kẽm · 1 lần canh) = NƠI ghép.
  - `GangPlacement`(`gang_placement`) — danh sách xếp bài: tờ in ↔ lệnh + SỐ CON (nguồn sự thật ghép).
  - `RoutingStep` (`routing_step`) — routing RIÊNG mỗi lệnh (§13.2): copy công đoạn từ job spec PTG
    khi bung; kế hoạch sửa được (thêm/bớt/đổi thứ tự/đổi tổ).
  - `RoutingStepAssignment` (`routing_step_assignment`) — gán thợ vào 1 bước routing (Lát 1): tổ
    trưởng gán; thợ được gán mới hứng việc + xem lệnh của mình. n–n bước↔thợ.

Module theo dõi thực thi xưởng (sản lượng · bàn giao · QC · nhập kho) đã GỠ — chỉ còn phần kế hoạch.

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

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
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
    # Máy gán cho lệnh (soft → may_thiet_bi.id). ①② dùng làm gợi ý copy từ PTP; ④ (lịch chạy) điều độ
    # kéo lệnh vào HÀNG máy in trong bảng Máy×Ngày = set field này (máy chỉ ghi nhận, không auto).
    may_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Khuôn bế (③): soft → khuon_be.id — điều độ gán khuôn cho lệnh có công đoạn bế (cảnh báo mềm, không chặn phát).
    khuon_be_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    trang_thai: Mapped[str] = mapped_column(String(16), nullable=False, default=LENH_NHAP)

    # --- Hạn giao (①): thuộc tính LỆNH. `han_giao_khach` snapshot `Order.delivery_committed_date`
    # lúc bung (kế thừa đơn); `han_giao_noi_bo` = buffer nội bộ (planner nhập, sớm hơn). Sửa khi
    # NHÁP; đóng băng lúc phát (service chặn theo trạng thái — chưa có ô quyền đổi-hạn sau phát). ---
    han_giao_khach: Mapped[date | None] = mapped_column(Date, nullable=True)
    han_giao_noi_bo: Mapped[date | None] = mapped_column(Date, nullable=True)

    # --- Lịch chạy (④ — bảng Máy×Ngày, người xếp tay): `ngay_chay` = ngày dự kiến (cột lưới);
    # `thu_tu_chay` = thứ tự trong ô (máy×ngày). `thoi_luong_phut` = thời lượng dự kiến — NỀN cho
    # Gantt-đầy-đủ-theo-giờ pha sau (để trống giờ), lưu sẵn để khỏi đổi schema. Máy = `may_id` ở trên. ---
    ngay_chay: Mapped[date | None] = mapped_column(Date, nullable=True)
    thu_tu_chay: Mapped[int | None] = mapped_column(Integer, nullable=True)
    thoi_luong_phut: Mapped[int | None] = mapped_column(Integer, nullable=True)

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


class RoutingStep(Base):
    """1 bước routing của lệnh SX (spec §13.2) — copy công đoạn từ job spec PTG (`PhieuThanhPham`)
    khi bung lệnh; kế hoạch SỬA được (thêm/bớt/đổi thứ tự/đổi tổ). Tổ phụ trách (`to_id`) = ảnh
    chụp `cong_doan.department_id` lúc copy (đổi được). Routing RIÊNG trên lệnh → sửa KHÔNG đụng
    phiếu tính giá.
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
    # Ghi chú kỹ thuật + quy cách BƯỚC — ảnh chụp từ `PhieuThanhPham` lúc copy (②: tổ hết trơ).
    ghi_chu: Mapped[str | None] = mapped_column(String(500), nullable=True)    # chép PhieuThanhPham.ghi_chu
    quy_cach: Mapped[str | None] = mapped_column(String(255), nullable=True)   # tóm tắt "N mặt · M vị trí · thuê ngoài"
    # Máy finishing + ca do TỔ tự xếp cho bước NÀY (Lát 1 · 1.12): điều độ đã gán máy-in/khuôn ở cấp
    # lệnh; máy bế/cán + ca là nội bộ tổ. Record-only (máy CHỈ GHI NHẬN — KHÔNG validate loại máy/chặn).
    may_id: Mapped[int | None] = mapped_column(Integer, nullable=True)          # → may_thiet_bi.id (soft)
    ca: Mapped[str | None] = mapped_column(String(16), nullable=True)           # "Ca 1" / "Ca 2" / "Ca 3"

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class LenhItem(Base):
    """Bài con trong 1 lệnh SX — 1 dòng: lệnh · ấn phẩm · dòng đơn (§ pick nhiều ấn phẩm/lệnh).

    Cho phép 1 LỆNH ôm NHIỀU ấn phẩm (người kế hoạch tự PICK gom — máy CHỈ GHI NHẬN, không phán
    "đủ giống"): mỗi ấn phẩm = 1 "bài con" giữ chi tiết RIÊNG (đọc quy cách từ PTP), dùng CHUNG
    routing của lệnh. NGUỒN SỰ THẬT ấn phẩm của lệnh (cột `lenh_sx.phieu_thanh_phan_id` GIỮ =
    ấn phẩm đại diện / bài con đầu, để tương thích chỗ đọc cũ). SL đích đọc SỐNG qua `order_line_id`
    → `OrderLine.qty` (KHÔNG chép). Lệnh cũ chưa có bản ghi → service fallback về đại diện.
    """

    __tablename__ = "lenh_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lenh_sx_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lenh_sx.id", ondelete="CASCADE"), index=True, nullable=False
    )
    phieu_thanh_phan_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)  # → phieu_thanh_phan.id (soft)
    order_line_id: Mapped[int | None] = mapped_column(Integer, nullable=True)   # → order_lines.id (soft; đọc SL đích sống)
    thu_tu: Mapped[int] = mapped_column(Integer, nullable=False, default=0)     # thứ tự bài con trong lệnh

    # OVERRIDE quy cách in tại LỆNH (§ kế thừa-nhưng-sửa-được): {field: value} người kế hoạch đổi so
    # với báo giá (null/absent = kế thừa). KHÔNG đụng bảng tính giá. Chỉ sửa khi lệnh còn NHÁP; khóa
    # sau phát. Ghép bài (tờ in) lấy giá trị HIỆU LỰC (báo giá + override) làm mặc định.
    quy_cach_override: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class RoutingStepAssignment(Base):
    """Gán thợ vào 1 bước routing (Lát 1 — hộp việc 2 tầng). Tổ trưởng (quyền `can_assign_work`)
    gán; thợ được gán mới HỨNG thông báo + xem lệnh của mình (thợ chỉ-xem). n–n: 1 bước nhiều thợ,
    1 thợ nhiều bước. FK thật tới `routing_step` (cascade xoá theo bước); `user_id`/`assigned_by`
    soft-ref tới `users.id` (khớp convention danh mục — users là module khác). Máy CHỈ GHI NHẬN.
    """

    __tablename__ = "routing_step_assignment"
    __table_args__ = (
        UniqueConstraint("routing_step_id", "user_id", name="uq_rsa_step_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    routing_step_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("routing_step.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)   # → users.id (soft; thợ được gán)
    assigned_by: Mapped[int | None] = mapped_column(Integer, nullable=True)     # → users.id (soft; tổ trưởng gán)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class SanLuong(Base):
    """Sản lượng THỰC THI của 1 bước routing (Lát 2) — ghi đạt/hỏng theo BƯỚC (không theo thợ; offset
    đếm máy/kíp). Event-log: cộng dồn nhiều đợt (lệnh chạy nhiều ca) → tổng = Σ. Máy CHỈ GHI NHẬN;
    trạng thái/tiến độ bước SUY từ các bản ghi này (KHÔNG cột lifecycle riêng trên routing_step).
    `don_vi` = "to"/"con" (Tổ In/Cán đếm tờ; Tổ Bế trở đi đếm con) — ghi nhãn, KHÔNG engine quy đổi.
    """

    __tablename__ = "san_luong"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lenh_sx_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lenh_sx.id", ondelete="CASCADE"), index=True, nullable=False
    )
    routing_step_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("routing_step.id", ondelete="CASCADE"), index=True, nullable=False
    )
    to_id: Mapped[int | None] = mapped_column(Integer, nullable=True)   # tổ ghi (soft → departments.id, snapshot)
    so_dat: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    so_hong: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    don_vi: Mapped[str] = mapped_column(String(16), nullable=False, default="to")   # "to" | "con"
    ghi_chu: Mapped[str | None] = mapped_column(String(500), nullable=True)
    nguoi_ghi: Mapped[int | None] = mapped_column(Integer, nullable=True)   # → users.id (soft)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class BanGiao(Base):
    """Bàn giao 2 CON DẤU giữa 2 bước routing (Lát 2). Tổ giao khai `so_giao` (giao_at); tổ nhận XÁC
    NHẬN `so_nhan` (nhan_at) — LỆCH được (thất thoát/đếm lại), KHÔNG chặn. Trạng thái nhận SUY từ
    `nhan_at` (null = chưa nhận). Giao cho bước KẾ trong routing (`toi_step_id`; null = bước cuối →
    chờ nhập kho L4). Máy CHỈ GHI NHẬN — "nhận" KHÔNG gate chặn tổ nhận chạy. Lệch = `so_giao − so_nhan`.
    """

    __tablename__ = "ban_giao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lenh_sx_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lenh_sx.id", ondelete="CASCADE"), index=True, nullable=False
    )
    tu_step_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)  # bước giao (soft → routing_step.id)
    toi_step_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True) # bước nhận (soft; null = bước cuối)
    to_giao: Mapped[int | None] = mapped_column(Integer, nullable=True)      # tổ giao (soft → departments.id)
    to_nhan: Mapped[int | None] = mapped_column(Integer, nullable=True)      # tổ nhận (soft)
    so_giao: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    don_vi: Mapped[str] = mapped_column(String(16), nullable=False, default="to")
    nguoi_giao: Mapped[int | None] = mapped_column(Integer, nullable=True)   # → users.id (soft)
    giao_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    so_nhan: Mapped[int | None] = mapped_column(Integer, nullable=True)      # null = chưa xác nhận nhận
    ly_do_lech: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nguoi_nhan: Mapped[int | None] = mapped_column(Integer, nullable=True)   # → users.id (soft)
    nhan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
