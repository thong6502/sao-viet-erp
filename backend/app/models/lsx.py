"""Lệnh sản xuất (LSX) — 1 DÒNG ĐƠN = 1 LỆNH, các lệnh NGANG HÀNG (không cha-con).

Mô hình 3 tầng chuẩn print MIS: Job (đơn hàng bán) → Part (`lsx`) → Operation (`lsx_cong_doan`).
Mỗi "chi tiết sản phẩm" đã tính giá (`PhieuThanhPhan`) mà khách CHỐT (thành `OrderLine`) sinh đúng
1 lệnh; lệnh nào cũng chạy độc lập dù cùng một đơn. Ghép bài (nhiều lệnh in chung 1 tờ) là tầng
KHÁC, dựng ở pha sau — KHÔNG gộp lệnh.

Quy cách + routing CHỤP SNAPSHOT lúc tạo (`quy_cach_json` + các dòng `lsx_cong_doan`): sau đó ai sửa
phiếu tính giá cũng không làm xê dịch lệnh đã phát ra, và kế hoạch sửa routing tại lệnh cũng không
ngược lên phiếu tính giá. Số lượng lấy từ ĐƠN HÀNG (`order_lines.qty` — bản cam kết bán), KHÔNG lấy
số lúc tính giá.

RBAC MODULE = "san_xuat". FK cha-con (`lsx_id`) + nguồn (`order_id`, `order_line_id`) là FK THẬT;
FK danh mục (máy, khuôn, công đoạn, tổ, user) là MỀM (plain int) theo convention soft-ref của repo.
Gotcha Postgres: Boolean default = `false()`/`true()` của SQLAlchemy, KHÔNG server_default "0"/"1".
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text,
    false as sa_false, true as sa_true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base

# --- Loại lệnh (§13 spec) — lát 1 chỉ sinh `san_xuat_moi`; các loại sau nối ở pha bổ sung/bù/làm lại.
LOAI_MOI = "san_xuat_moi"
LOAI_BO_SUNG = "bo_sung"
LOAI_BU = "bu"
LOAI_LAM_LAI = "lam_lai"
LOAI_MAU = "mau"
LOAI_NOI_BO = "noi_bo"
LOAI_LSX = (LOAI_MOI, LOAI_BO_SUNG, LOAI_BU, LOAI_LAM_LAI, LOAI_MAU, LOAI_NOI_BO)

# --- Trạng thái — lát 1 dừng ở `san_sang`. Các mốc sau (`da_lap_ke_hoach`, `da_phat_hanh`,
# `dang_san_xuat`, `hoan_thanh`, `da_dong`) thuộc pha xếp lịch / thực thi, CHƯA dùng.
TT_NHAP = "nhap"                 # vừa tạo, dữ liệu đủ
TT_CHO_BO_SUNG = "cho_bo_sung"   # thiếu file/khuôn/quy cách/routing
TT_SAN_SANG = "san_sang"         # kế hoạch xác nhận đủ → chờ xếp lịch
TRANG_THAI_LSX = (TT_NHAP, TT_CHO_BO_SUNG, TT_SAN_SANG)
TRANG_THAI_SUA_DUOC = (TT_NHAP, TT_CHO_BO_SUNG, TT_SAN_SANG)  # chưa phát hành → sửa/xoá được

# --- Đơn vị đếm của 1 công đoạn (print MIS: mỗi operation có đơn vị riêng, đổi ở ranh giới xén).
DV_TO = "to"      # tờ in
DV_CAI = "cai"    # con / thành phẩm
DV_KEM = "kem"    # bộ kẽm (chế bản)
DV_BAI = "bai"    # bài bình (chế bản: 1 bài → n bản kẽm)
DON_VI_CONG_DOAN = (DV_TO, DV_CAI, DV_KEM, DV_BAI)

# --- Loại bước (execution type). Quyết định bước CHIẾM cái gì khi lên Gantt — đây là lý do routing
# tồn tại. Đối chiếu Dynamics 365 BC (nền của print MIS PrintVis): "wait/move time don't consume
# capacity on the work center calendar" → `cho` chỉ đẩy thời gian, không chiếm tài nguyên nào.
LB_MAY = "may"                 # chiếm MÁY (in, cán, bế, xén)
LB_TO = "to"                   # chiếm TỔ lao động (dán tay, đóng gói)
LB_THUE_NGOAI = "thue_ngoai"   # nhà gia công làm — không chiếm máy/tổ nội bộ
LB_CHO = "cho"                 # chờ kỹ thuật (khô mực, khô keo) — không chiếm gì
LB_KCS = "kcs"                 # kiểm tra — chiếm tổ
LB_XA_TO = "xa_to"             # chia/tách bán thành phẩm — chiếm máy xén
LB_BAI_GHEP = "bai_ghep"       # chạy chung ở bài ghép — khai sẵn, PHA SAU mới sinh
LOAI_BUOC = (LB_MAY, LB_TO, LB_THUE_NGOAI, LB_CHO, LB_KCS, LB_XA_TO, LB_BAI_GHEP)
# Bước chiếm tổ (nhiều người làm song song được → `so_nhan_cong` chia thời gian chạy).
LOAI_BUOC_THEO_TO = (LB_TO, LB_KCS)

# --- Đơn vị năng suất (output/giờ). Khớp `may_thiet_bi.don_vi_toc_do` ở phần dùng được.
NS_TO_GIO = "to_gio"
NS_CAI_GIO = "cai_gio"
NS_KEM_GIO = "kem_gio"
NS_BAI_GIO = "bai_gio"
DON_VI_NANG_SUAT = (NS_TO_GIO, NS_CAI_GIO, NS_KEM_GIO, NS_BAI_GIO)

# --- Điều kiện bắt đầu (§4.5) — tập cờ CỐ ĐỊNH, lưu trong `dieu_kien_json`. "Công đoạn trước xong"
# là mặc định của mô hình tuyến tính nên không có cờ riêng.
DIEU_KIEN = (
    "co_vat_tu",         # vật tư (giấy/mực) đã sẵn
    "file_duyet",        # file khách đã duyệt
    "kem_xong",          # kẽm đã xuất
    "khuon_san_sang",    # khuôn bế/ép đã có
    "mau_mau_ky",        # mẫu màu đã ký
    "nhan_tu_gia_cong",  # đã nhận bán thành phẩm từ nhà gia công
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Lsx(Base):
    __tablename__ = "lsx"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ma: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)  # LSX26-0001

    # --- Nhận diện ---
    loai: Mapped[str] = mapped_column(String(20), nullable=False, default=LOAI_MOI)
    # Lệnh bổ sung/bù/làm lại trỏ về lệnh gốc (pha sau; soft-ref để khỏi vướng cascade).
    lsx_goc_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    ten: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    # --- Nguồn (Job → Part) ---
    order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("orders.id"), index=True, nullable=False
    )
    order_line_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("order_lines.id"), index=True, nullable=False
    )
    # Phiên bản báo giá đã chốt (truy vết thương mại) + "chi tiết tính giá" nguồn. CẢ HAI là soft-ref
    # và chỉ để TRUY VẾT: `phieu_thanh_phan_id` KHÔNG đọc-sống để tính lại (id đổi mỗi lần lưu PTG vì
    # phiếu ghi kiểu replace-all) — mọi số của lệnh nằm ở snapshot dưới đây.
    quote_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    phieu_thanh_phan_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- Số lượng (MIS: Ordered → Planned; Produced thuộc pha thực thi) ---
    so_luong_dat: Mapped[int] = mapped_column(Integer, nullable=False, default=0)      # = order_lines.qty
    don_vi_tinh: Mapped[str] = mapped_column(String(30), nullable=False, default="cái")
    bu_hao_to: Mapped[int] = mapped_column(Integer, nullable=False, default=0)         # tờ bù (auto+tay)
    so_to_ke_hoach: Mapped[int] = mapped_column(Integer, nullable=False, default=0)    # tờ vào máy
    so_to_nguyen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)      # tờ giấy nguyên
    so_con: Mapped[int] = mapped_column(Integer, nullable=False, default=1)            # con/tờ

    # --- Thời gian (2 mốc: hạn khách từ đơn + hạn nội bộ do kế hoạch đặt) ---
    ban_giao_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    han_giao_khach: Mapped[date | None] = mapped_column(Date, nullable=True)
    han_hoan_thanh_sx: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_rush: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_false(), default=False
    )

    # --- Kỹ thuật ---
    # Snapshot quy cách lúc tạo: khổ ①②③ · giấy + định lượng · số màu A/B · cách in · chừa · số kẽm ·
    # số lượt · ghi chú kỹ thuật. READ-ONLY ở lát 1 (đổi giấy/màu/khổ = yêu cầu thay đổi kỹ thuật).
    quy_cach_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Ảnh chụp routing NGAY LÚC TẠO lệnh (list dict rút gọn: ten · nhom · loai_buoc · thue ngoài).
    # Chỉ để §14 phát hiện "routing đã đổi so với bài tính giá" — KHÔNG dùng để tính lại bất cứ gì.
    routing_goc_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    khuon_be_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)  # → khuon_be.id
    may_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)       # → may_thiet_bi.id

    # --- Quản lý ---
    trang_thai: Mapped[str] = mapped_column(String(20), nullable=False, default=TT_NHAP)
    nguoi_phu_trach_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)  # → users.id
    ghi_chu: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    # KHÔNG dùng `passive_deletes=True`: nó giao việc xoá con cho DB, mà SQLite (dev) mặc định
    # TẮT `PRAGMA foreign_keys` → xoá lệnh xong công đoạn còn mồ côi, rồi lệnh mới TÁI DÙNG id
    # sẽ nhận nhầm routing của lệnh đã xoá. Để SQLAlchemy tự xoá con thì đúng trên cả SQLite lẫn
    # Postgres. `ondelete="CASCADE"` dưới FK vẫn giữ làm lớp chặn cuối ở DB.
    cong_doans: Mapped[list["LsxCongDoan"]] = relationship(
        "LsxCongDoan",
        back_populates="lsx",
        order_by="LsxCongDoan.thu_tu",
        cascade="all, delete-orphan",
    )


class LsxCongDoan(Base):
    """1 bước routing của lệnh (Operation) — copy từ `phieu_thanh_pham` lúc tạo, kế hoạch SỬA được.

    Mỗi bước tự mang SỐ LƯỢNG VÀO/RA + ĐƠN VỊ VÀO/RA riêng vì đơn vị đổi qua ranh giới xén: chế bản
    đếm bộ kẽm, in/cán/bế đếm TỜ vào, dán/đóng gói đếm CON. Máy điền mặc định theo nhóm công đoạn +
    danh mục (`cong_doan.setup_time`, `may_thiet_bi.toc_do`…), người kế hoạch quyết con số cuối —
    kế thừa là MẶC ĐỊNH, không phải read-only.

    Mô hình thời gian bám Dynamics 365 BC (nền của print MIS PrintVis): setup tính 1 lần/lệnh, chạy
    scale theo SL, `cho_phut`/`di_chuyen_phut` đẩy lịch nhưng KHÔNG ăn capacity của máy.
    """

    __tablename__ = "lsx_cong_doan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lsx_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lsx.id", ondelete="CASCADE"), index=True, nullable=False
    )
    thu_tu: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    cong_doan_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)  # → cong_doan.id
    ten: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    nhom: Mapped[str | None] = mapped_column(String(12), nullable=True)  # prepress|print|finishing
    # Tổ nhận việc — snapshot `cong_doan.department_id` lúc copy (đổi danh mục sau không lay lệnh đã tạo).
    department_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    may_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)  # → may_thiet_bi.id

    # --- Nhận diện bước ---
    loai_buoc: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default=LB_MAY, default=LB_MAY
    )
    bat_buoc: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_true(), default=True
    )

    # --- Số lượng & hao hụt ---
    # Đơn vị VÀO ≠ RA là chuyện thường ở ranh giới xén/bế: 5.170 tờ vào → 20.680 con ra (hệ số 4).
    so_luong_vao: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    so_luong_ra: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    don_vi_vao: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default=DV_TO, default=DV_TO
    )
    don_vi_ra: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default=DV_TO, default=DV_TO
    )
    he_so_quy_doi: Mapped[float] = mapped_column(
        Numeric(12, 4), nullable=False, server_default="1", default=1
    )
    # Cặp hao hụt kiểu BC: `hao_hut_pct` = Scrap Factor % (theo SL), `hao_hut` = Fixed Scrap Qty
    # (số tuyệt đối, canh máy). Tính ngược: SL_vào = SL_ra × (1 + pct) + hao_hut.
    hao_hut: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    hao_hut_pct: Mapped[float] = mapped_column(
        Numeric(6, 2), nullable=False, server_default="0", default=0
    )
    so_luot_chay: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1", default=1
    )

    # --- Năng suất & thời gian (phút) — nguồn dữ liệu cho Gantt ---
    # `chiếm máy` = setup + chạy + vệ sinh (ăn capacity). `chờ`/`di chuyển` CHỈ đẩy thời gian, không
    # ăn capacity — đúng BC: "wait time and move time don't consume capacity on the work center".
    setup_phut: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default="0", default=0)
    nang_suat: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    don_vi_nang_suat: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # Người kế hoạch gõ đè thời gian chạy → thắng công thức năng suất. NULL = để máy tính.
    chay_phut: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    ve_sinh_phut: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default="0", default=0)
    cho_phut: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default="0", default=0)
    di_chuyen_phut: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default="0", default=0)
    # Số người/máy chạy ĐỒNG THỜI (BC: Concurrent Capacities) — 5 người dán thì thời gian chạy ÷ 5.
    # Chỉ có nghĩa với bước chiếm tổ; bước chiếm máy để 1.
    so_nhan_cong: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1", default=1
    )

    # --- Phương thức thực hiện ---
    # DS máy thay thế — CHỈ ĐỂ THAM KHẢO, không tự xếp lịch (BC: "for information only").
    may_thay_the_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Cờ điều kiện bắt đầu, tập `DIEU_KIEN`.
    dieu_kien_json: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # --- Gia công ngoài (§8) — chỉ dùng khi `loai_buoc = thue_ngoai`. NCC khai TAY (text tự do):
    # cơ sở gia công nhỏ lẻ thường chưa có trong danh mục `suppliers`, chốt không bắt khai trước.
    nha_cung_cap: Mapped[str | None] = mapped_column(String(150), nullable=True)
    sl_gui: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    ngay_gui_dk: Mapped[date | None] = mapped_column(Date, nullable=True)
    van_chuyen_ngay: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)  # 1 chiều
    gia_cong_ngay: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    ngay_nhan_dk: Mapped[date | None] = mapped_column(Date, nullable=True)
    hao_hut_cho_phep: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    don_gia_gia_cong: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    yeu_cau_ky_thuat: Mapped[str | None] = mapped_column(Text, nullable=True)
    nguoi_giao_nhan_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)  # → users.id

    ghi_chu: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    lsx: Mapped["Lsx"] = relationship("Lsx", back_populates="cong_doans")
