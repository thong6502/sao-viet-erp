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
from uuid import uuid4

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint,
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

# --- Trạng thái (bám lifecycle print MIS / Dynamics BC). `da_lap_ke_hoach` (≈ Firm Planned) ĐÃ dùng:
# set qua service xếp lịch (KHÔNG qua `set_trang_thai` chung) + KHÓA routing — gỡ kế hoạch để mở lại.
# `da_phat_hanh` (≈ Released) ĐÃ dùng: gate xung đột 0-Chặn ở bàn xếp lịch → thả xuống xưởng (routing
# vẫn khóa; thu hồi phát hành để về `da_lap_ke_hoach`). Các mốc sau (`dang_san_xuat`, `hoan_thanh`,
# `da_dong`) thuộc pha thực thi, CHƯA dùng.
TT_NHAP = "nhap"                 # vừa tạo, dữ liệu đủ
TT_CHO_BO_SUNG = "cho_bo_sung"   # thiếu file/khuôn/quy cách/routing
TT_SAN_SANG = "san_sang"         # kế hoạch xác nhận đủ → chờ xếp lịch
TT_DA_LAP_KE_HOACH = "da_lap_ke_hoach"  # đã sinh dòng xếp lịch → routing bị khóa
TT_DA_PHAT_HANH = "da_phat_hanh"        # đã phát hành xuống xưởng (Released) — routing vẫn khóa
TRANG_THAI_LSX = (TT_NHAP, TT_CHO_BO_SUNG, TT_SAN_SANG, TT_DA_LAP_KE_HOACH, TT_DA_PHAT_HANH)
TRANG_THAI_SUA_DUOC = (TT_NHAP, TT_CHO_BO_SUNG, TT_SAN_SANG)  # chưa lập KH → sửa/xoá routing được

# --- Đơn vị đếm của 1 công đoạn (print MIS: mỗi operation có đơn vị riêng, đổi ở ranh giới xén).
DV_TO_NGUYEN = "to_nguyen"  # tờ giấy NGUYÊN (khổ mua về, chưa xả) — khác tờ in!
DV_TO = "to"      # tờ in (sau khi xả từ tờ nguyên)
DV_CAI = "cai"    # con / tờ thành phẩm
DV_CON = "con"    # mảnh cắt ra từ MỘT tờ in — KHÁC `cai`: sách gấp tay thì nhiều tờ mới ra 1 cuốn
DV_KEM = "kem"    # bộ kẽm (chế bản) — nhãn màn hình là "Bản"
DV_BAI = "bai"    # bài bình (chế bản: 1 bài → n bản kẽm)
# Thêm 2026-08-05 theo yêu cầu chủ: mức TAY của khâu sách, nằm trên dòng giấy.
#   tờ in ──(gấp)──▶ TAY sách ──(bắt tay + vào keo)──▶ cuốn
# `cai` (thành phẩm) là ĐÍCH CUỐI của dòng giấy — chủ chốt 2026-08-05, không có mức nào sau nó.
# CHƯA có cầu quy đổi (chủ chốt "quy đổi bàn sau"): `_he_so_cau` không có key nên
# `he_so.get(..., 1.0)` rơi về hệ số 1 — chuỗi ngược vẫn chạy, chỉ là chưa nhân/chia gì.
# Khi chốt công thức thì thêm vào `CAU_QUY_DOI` + `_he_so_cau`, ĐỪNG khai hệ số ở chỗ khác.
DV_TAY = "tay"    # tay sách (1 tờ in gấp lại = 1 tay, mang n trang)
# Đơn vị KHÔNG nằm trên dòng giấy — chỉ để ghi nhận, không có cầu quy đổi (xem `CAU_QUY_DOI`).
DV_NGOAI_DONG_GIAY = ("mau", "tan", "me", "m2", "nhip", "hop")
DON_VI_CONG_DOAN = (
    DV_TO_NGUYEN, DV_TO, DV_CON, DV_TAY, DV_CAI, DV_KEM, DV_BAI, *DV_NGOAI_DONG_GIAY,
)

# Dòng giấy đi qua BA đơn vị với HAI điểm quy đổi. Hệ số KHÔNG lưu ở đâu cả — phiếu tính giá đã
# có sẵn (`so_manh_xa` từ khổ giấy, `con` từ bình bài); lưu lại là đẻ nguồn sự thật thứ hai.
#     tờ nguyên ──(xả: ÷ số mảnh xả)──▶ tờ in ──(bế/xén: × con/tờ)──▶ tờ thành phẩm
#     tờ nguyên ──(÷ số mảnh xả)──▶ tờ in ──(× con/tờ)──▶ con ──(÷ số tay)──▶ thành phẩm
# Cầu `to → cai` GIỮ NGUYÊN (đi tắt, bỏ qua `con`) vì phần lớn routing khai thẳng như vậy; hai
# cầu qua `con` là đường dài cho bước nào thật sự đếm mảnh. Hệ số cả bốn suy ở `_he_so_cau`.
CAU_QUY_DOI = (
    (DV_TO_NGUYEN, DV_TO), (DV_TO, DV_CAI), (DV_TO, DV_CON), (DV_CON, DV_CAI),
)

# --- Loại bước (execution type). Quyết định bước CHIẾM cái gì khi lên Gantt — đây là lý do routing
# tồn tại. Thời gian chờ/di chuyển nằm trên bước và không chiếm năng lực tài nguyên.
LB_MAY = "may"                 # chiếm MÁY (in, cán, bế, xén)
LB_TO = "to"                   # chiếm TỔ lao động (dán tay, đóng gói)
LB_THUE_NGOAI = "thue_ngoai"   # nhà gia công làm — không chiếm máy/tổ nội bộ
LOAI_BUOC = (LB_MAY, LB_TO, LB_THUE_NGOAI)
# Bước chiếm tổ (nhiều người làm song song được → `so_nhan_cong` chia thời gian chạy).
LOAI_BUOC_THEO_TO = (LB_TO,)

# --- Đơn vị năng suất (output/giờ). Khớp `may_thiet_bi.don_vi_toc_do` ở phần dùng được.
NS_TO_GIO = "to_gio"
NS_CAI_GIO = "cai_gio"
NS_KEM_GIO = "kem_gio"
# KHÔNG có `bai_gio`. Máy CTP nhả ra BẢN KẼM chứ không nhả ra "bài": một bài 4 màu tốn 4 lượt ghi,
# bài 1 màu tốn 1 — khai "20 bài/giờ" là con số không đo được. Thứ đo ổn định là `kem_gio`.
# (Mã cũ sinh ra từ thời `DON_VI_CONG_DOAN` cho công đoạn khai 5 đơn vị; nay `DON_VI_DONG_GIAY`
# chỉ còn `to_nguyen · to · cai` nên không bước nào khớp được `bai` — nó chết hẳn, đã gỡ.)
DON_VI_NANG_SUAT = (NS_TO_GIO, NS_CAI_GIO, NS_KEM_GIO)

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
    step_key: Mapped[str] = mapped_column(
        String(36), unique=True, index=True, nullable=False, default=lambda: str(uuid4())
    )
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
    # Khuôn dùng cho CHÍNH BƯỚC NÀY (soft-ref → khuon_be.id). Chỉ có nghĩa khi công đoạn nguồn bật
    # cờ `requires_tooling` với `tooling_type` là khuôn lưu kho (khuon_be · khuon_ep).
    #
    # Vì sao ở BƯỚC chứ không ở lệnh (11/08/2026): một lệnh hộp giấy có thể vừa Bế (khuôn bế) vừa
    # Ép nhũ (khuôn ép) — ô khuôn ở cấp lệnh chỉ giữ được MỘT cái, cái còn lại không ai biết lấy
    # khuôn nào. Gắn theo bước thì bảng cân đối còn canh được đúng mốc: khuôn bế phải có mặt ngày
    # chạy bước bế, khuôn ép ngày chạy bước ép — hai ngày khác nhau.
    khuon_be_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)

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
    # KẾ THỪA từ `cong_doan.don_vi_vao/ra`, server ghi — client KHÔNG gửi, drawer không có ô chọn.
    # Đơn vị vào/ra là bản chất của công đoạn (bế luôn là tờ in → con), không đổi theo từng đơn.
    # NULL = bước KHÔNG CHẠM GIẤY (chế bản đếm kẽm) → đứng ngoài chuỗi tính ngược.
    # String(12): mã `to_nguyen` dài 9 — VARCHAR(8) cũ CHẬT, Postgres ném lỗi độ dài lúc ghi.
    don_vi_vao: Mapped[str | None] = mapped_column(String(12), nullable=True)
    don_vi_ra: Mapped[str | None] = mapped_column(String(12), nullable=True)
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
    # String(32): đơn vị năng suất của bước TỔ nay là mã người khai chọn ở định mức đầu việc
    # (`ban_proof_gio` dài 13) chứ không chỉ ba mã suy ra `to_gio`/`cai_gio`/`kem_gio`. SQLite bỏ
    # qua độ dài nên test không bắt được — chỉ Postgres thật mới lỗi lúc lưu (migration 0159).
    don_vi_nang_suat: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Người kế hoạch gõ đè thời gian chạy → thắng công thức năng suất. NULL = để máy tính.
    chay_phut: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    # DORMANT 2026-08-04 — vệ sinh/rửa mực bỏ khỏi hệ: bước mới luôn 0, engine thôi cộng.
    ve_sinh_phut: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default="0", default=0)
    # "Thời gian khác" (migration 0153) — ô DUY NHẤT người kế hoạch còn gõ được ở tab Thời gian;
    # cộng THẲNG vào thời gian chiếm máy. Chuẩn bị/tốc độ nay kế thừa từ máy, không sửa tại bước.
    phat_sinh_phut: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default="0", default=0)
    cho_phut: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default="0", default=0)
    di_chuyen_phut: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default="0", default=0)
    # Số người/máy chạy ĐỒNG THỜI (BC: Concurrent Capacities) — 5 người dán thì thời gian chạy ÷ 5.
    # Chỉ có nghĩa với bước chiếm tổ; bước chiếm máy để 1.
    so_nhan_cong: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1", default=1
    )
    # Snapshot định mức tại lúc bung/chọn đầu việc. Với bước Máy đây là kíp tiêu chuẩn và max=NULL;
    # với bước Tổ, `toi_da` chặn phần năng suất tăng thêm nhưng không cấm kế hoạch bố trí dư người.
    so_nhan_cong_tieu_chuan: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1", default=1
    )
    so_nhan_cong_toi_da: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Mốc thứ ba của định mức nhân lực. Cả ba mốc KẾ THỪA từ `cong_doan_dau_viec` nhưng SỬA ĐƯỢC
    # tại bước (kế thừa = mặc định, không read-only). Chỉ `toi_da` vào công thức (trần thời gian);
    # `toi_thieu` hiện là khai báo.
    so_nhan_cong_toi_thieu: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- Phương thức thực hiện ---
    # ĐẦU VIỆC KHOÁN của bước (`piece_rates`) — kế hoạch chọn "hôm nay bước cán này làm CÁN MỜ hay
    # GHÉP MATELIZE", vì cùng một công đoạn mà hai đơn giá khoán khác nhau, máy không đoán được.
    # SNAPSHOT {rate_id, ten, don_vi, don_gia} chứ không đọc-sống: xưởng lên giá khoán về
    # sau KHÔNG được làm xê dịch lệnh đã phát. Tiền khoán là số DẪN XUẤT (tính lúc đọc), không lưu.
    khoan_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
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
    # --- Gia công ngoài: sổ THỰC TẾ (khác 9 cột trên — kia là DỰ KIẾN) -----------------
    # Giao và nhận là HAI sự kiện: khác ngày, khác người, khác số lượng. Ghi qua cửa THỰC THI
    # (`POST .../giao-nhan`), không qua lưu routing — hàng ra cổng lúc lệnh đang chạy, mà lưu
    # routing thì bị chặn ở trạng thái đã lập kế hoạch.
    # Số hỏng/thiếu = `sl_giao_thuc - sl_nhan_thuc`, trạng thái suy từ hai mốc thời gian, tiền
    # gia công thực = `sl_nhan_thuc × don_gia_gia_cong` — DẪN XUẤT, không lưu cột.
    nguoi_giao_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)  # → users.id
    giao_luc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sl_giao_thuc: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    nguoi_nhan_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)  # → users.id
    nhan_luc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sl_nhan_thuc: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)

    ghi_chu: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    lsx: Mapped["Lsx"] = relationship("Lsx", back_populates="cong_doans")
    vat_tus: Mapped[list["LsxCongDoanVatTu"]] = relationship(
        "LsxCongDoanVatTu", back_populates="buoc", order_by="LsxCongDoanVatTu.thu_tu",
        cascade="all, delete-orphan",
    )
    phu_thuoc: Mapped[list["LsxCongDoanPhuThuoc"]] = relationship(
        "LsxCongDoanPhuThuoc", foreign_keys="LsxCongDoanPhuThuoc.buoc_sau_id",
        back_populates="buoc_sau", cascade="all, delete-orphan",
    )


class LsxCongDoanVatTu(Base):
    __tablename__ = "lsx_cong_doan_vat_tu"
    __table_args__ = (UniqueConstraint("lsx_cong_doan_id", "vat_tu_id", name="uq_lsx_buoc_vat_tu"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lsx_cong_doan_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lsx_cong_doan.id", ondelete="CASCADE"), index=True, nullable=False
    )
    vat_tu_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    vat_tu_ma_snapshot: Mapped[str] = mapped_column(String(30), nullable=False)
    vat_tu_ten_snapshot: Mapped[str] = mapped_column(String(150), nullable=False)
    don_vi_snapshot: Mapped[str] = mapped_column(String(16), nullable=False)
    so_luong: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    thu_tu: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    buoc: Mapped["LsxCongDoan"] = relationship("LsxCongDoan", back_populates="vat_tus")


class LsxCongDoanPhuThuoc(Base):
    __tablename__ = "lsx_cong_doan_phu_thuoc"
    __table_args__ = (UniqueConstraint("buoc_truoc_id", "buoc_sau_id", name="uq_lsx_buoc_phu_thuoc"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    buoc_truoc_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lsx_cong_doan.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    buoc_sau_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lsx_cong_doan.id", ondelete="CASCADE"), index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    buoc_sau: Mapped["LsxCongDoan"] = relationship(
        "LsxCongDoan", foreign_keys=[buoc_sau_id], back_populates="phu_thuoc"
    )
