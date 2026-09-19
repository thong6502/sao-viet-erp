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
    Boolean, Date, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text,
    UniqueConstraint, desc, false as sa_false, true as sa_true,
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
DV_TAY = "tay"    # tay sách (1 tờ in gấp lại = 1 tay, mang n trang)


# --- Loại bước (execution type). Quyết định bước CHIẾM cái gì khi lên Gantt — đây là lý do routing
# tồn tại. Thời gian chờ/di chuyển nằm trên bước và không chiếm năng lực tài nguyên.
LB_MAY = "may"                 # chiếm MÁY (in, cán, bế, xén)
LB_TO = "to"                   # chiếm TỔ lao động (dán tay, đóng gói)
LB_THUE_NGOAI = "thue_ngoai"   # nhà gia công làm — máy của họ khai trong danh mục Máy; nhập
                               # liệu Y HỆT bước máy, chỉ KHÔNG sinh tiền khoán / sản lượng tổ
LOAI_BUOC = (LB_MAY, LB_TO, LB_THUE_NGOAI)
# Bước chiếm tổ — thời lượng là `so_gio_ke_hoach` người lập kế hoạch gõ tay (18/09/2026).
LOAI_BUOC_THEO_TO = (LB_TO,)

# Nhãn TẠM của bước chưa đặt tên và chưa gắn công đoạn. Cột `lsx_cong_doan.ten` NOT NULL nên phải
# có gì đó; chuỗi này là "chưa có tên", KHÔNG phải tên do người đặt. Bước đã gắn `cong_doan_id`
# thì tên đúng là tên danh mục — thấy chuỗi này ở đó là dữ liệu cũ, `replace_routing` tự lấy lại.
TEN_BUOC_TRONG = "Công đoạn"

# --- Đơn vị năng suất: KHÔNG có hằng nào ở đây, và đừng khai lại.
#
# Máy lưu `may_thiet_bi.don_vi_toc_do` dạng `<mã đơn vị>_gio`, mã lấy thẳng từ danh mục Đơn vị &
# quy đổi — xưởng khai `me`/`thung` thì máy khai `me_gio`/`thung_gio`. Cắt hậu tố ở đúng một chỗ:
# `lsx_service.ma_don_vi_toc_do`.
#

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Lsx(Base):
    __tablename__ = "lsx"
    # Hai index sắp xếp của BẢNG LỆNH (rà 18/09/2026). Chúng THAY THẾ `ix_lsx_created_at` và
    # `ix_lsx_trang_thai_created_at` của mg 0217 — xem mg `0315_index_bang_lenh`, chỗ đó xoá hai
    # cái cũ đi. Khác biệt duy nhất là cột `id DESC` ở cuối, và nó không thừa: màn Kế hoạch SX
    # sắp xếp bằng `ORDER BY created_at DESC, id DESC`; index chỉ có `created_at DESC` thì
    # Postgres vẫn phải chèn Incremental Sort để phá hoà trong nhóm cùng giây — lệnh sinh theo lô
    # nên hoà rất nhiều. Đo trên Postgres thật 300.000 dòng: lật tới trang 200 (`OFFSET 9950`)
    # 9,5 ms → 2,4 ms; cắt trang đầu 3,1 ms → 1,6 ms.
    #   · `ix_lsx_sap_xep`      : tab "Tất cả" + mọi lượt không lọc trạng thái.
    #   · `ix_lsx_trang_thai_sx`: tab đã lọc (`trang_thai IN (...)`).
    # Thứ tự cột phải khớp `ORDER BY` (cùng DESC) thì Postgres mới đọc thẳng, khỏi bước sort.
    # Ô tìm kiếm là chuyện khác: `ILIKE '%…%'` không dùng được btree, phần đó do hai index
    # trigram `ix_lsx_ma_trgm` / `ix_lsx_ten_trgm` của mg 0217 lo (chỉ Postgres, cần `pg_trgm`).
    __table_args__ = (
        Index("ix_lsx_sap_xep", desc("created_at"), desc("id")),
        Index("ix_lsx_trang_thai_sx", "trang_thai", desc("created_at"), desc("id")),
    )

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
    # và chỉ để TRUY VẾT: `phieu_thanh_phan_id` KHÔNG đọc-sống để TÍNH LẠI — mọi số của lệnh nằm ở
    # snapshot dưới đây; pin chỉ dùng kéo chi tiết kỹ thuật khi mở drawer ấn phẩm.
    # Id thành phần ỔN ĐỊNH từ 07/09/2026 (router phiếu tính giá ghi ĐÈ TẠI CHỖ thay vì xoá-tạo-lại,
    # migration `0279` đã nối lại các pin chết trước đó), nhưng hàng nguồn VẪN có thể biến mất khi
    # người lập phiếu bỏ hẳn sản phẩm ⇒ mọi chỗ đọc pin phải chịu được None.
    quote_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    phieu_thanh_phan_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- Số lượng (MIS: Ordered → Planned; Produced thuộc pha thực thi) ---
    so_luong_dat: Mapped[int] = mapped_column(Integer, nullable=False, default=0)      # = order_lines.qty
    don_vi_tinh: Mapped[str] = mapped_column(String(30), nullable=False, default="cái")
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
    # CÔNG TẮC giữ chỗ vật tư (17/08/2026). Bật = ĐĂNG KÝ giữ, không phải chụp một lần: giữ được
    # bao nhiêu hay bấy nhiêu, hàng về sau thì tự nhặt thêm cho đủ.
    #
    # Cần cờ RIÊNG, không suy từ "có dòng nào trong `vat_tu_giu_cho` không": trạng thái "đã bật mà
    # chưa giữ được gì" (kho trống, đang chờ mua) không có dòng nào để suy — mà đó chính là trạng
    # thái phải nhớ để hàng về thì tự nhặt.
    giu_cho_bat: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_false(), default=False
    )

    # --- Kỹ thuật ---
    # Snapshot quy cách lúc tạo: khổ ①②③ · giấy + định lượng · số màu A/B · cách in · chừa · số kẽm ·
    # số lượt · ghi chú kỹ thuật. READ-ONLY ở lát 1 (đổi giấy/màu/khổ = yêu cầu thay đổi kỹ thuật).
    quy_cach_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Ảnh chụp routing NGAY LÚC TẠO lệnh (list dict rút gọn: ten · nhom · loai_buoc · thue ngoài).
    # Chỉ để §14 phát hiện "routing đã đổi so với bài tính giá" — KHÔNG dùng để tính lại bất cứ gì.
    routing_goc_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
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
    # Cùng lý do không `passive_deletes` như `cong_doans`. Xoá DÒNG thôi — object trong kho file do
    # router xoá lệnh dọn, vì tầng DB không biết gì về storage.
    dinh_kems: Mapped[list["LsxDinhKem"]] = relationship(
        "LsxDinhKem",
        back_populates="lsx",
        order_by="LsxDinhKem.id",
        cascade="all, delete-orphan",
    )


class LsxCongDoan(Base):
    """1 bước routing của lệnh (Operation) — copy từ `phieu_thanh_pham` lúc tạo, kế hoạch SỬA được.

    Mỗi bước tự mang SỐ LƯỢNG VÀO/RA + ĐƠN VỊ VÀO/RA riêng vì đơn vị đổi qua ranh giới xén: chế bản
    đếm bộ kẽm, in/cán/bế đếm TỜ vào, dán/đóng gói đếm CON. Máy điền mặc định theo nhóm công đoạn +
    danh mục (`cong_doan.setup_time`, `may_thiet_bi.toc_do`…), người kế hoạch quyết con số cuối —
    kế thừa là MẶC ĐỊNH, không phải read-only.

    Mô hình thời gian bám Dynamics 365 BC (nền của print MIS PrintVis): setup tính 1 lần/lệnh, chạy
    scale theo SL. `cho_phut`/`di_chuyen_phut` (đẩy lịch mà không ăn capacity máy) đã GỠ khỏi model
    — cột còn nằm im trong DB, không code nào đọc.
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
    # Con dao dùng cho CHÍNH BƯỚC NÀY (soft-ref → khuon_be.id). Chỉ hỏi ở bước mà công đoạn nguồn
    # bật `requires_tooling`.
    #
    # LỊCH SỬ, đọc trước khi định sửa: cột này từng bị XOÁ HẲN sáng 16/08/2026 (mg `0203`) vì
    # 0/14 bước có gán khuôn. Nguyên nhân KHÔNG phải người dùng lười mà là hình dạng của ô: nó là
    # một select trống, mở ra thấy danh sách rỗng (dao chưa ai khai), KHÔNG có đường tạo dao mới,
    # nên ai cũng đóng lại và bỏ qua. Dựng lại chiều tối cùng ngày (mg `0205`) với hình dạng khác:
    # HAI NHÁNH — "dùng dao có sẵn" (ô chọn đã lọc sẵn theo khách của lệnh + loại dao của bước) và
    # "làm dao mới" (tạo thẳng một dòng trong danh mục Khuôn, tình trạng `dang_dat_lam`).
    #
    # Để trống là hợp lệ, KHÔNG chặn phát hành lệnh — chủ dự án chốt 16/08.
    khuon_be_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    # Ý ĐỊNH CỦA SALE về khuôn, chép từ phiếu tính giá lúc dựng lệnh (chốt 04/09/2026). KHÔNG phải
    # quyết định cuối: quyết định cuối là `khuon_be_id` ở trên, do kế hoạch chốt. Hai thứ tồn tại
    # cạnh nhau để SO ĐƯỢC — lệch nhau nghĩa là tiền đã báo cho khách không khớp việc sẽ làm, và
    # đó là lúc phải có người quyết (báo lại khách hay xưởng tự nuốt), máy chỉ nói ra chỗ lệch.
    khuon_nguon: Mapped[str | None] = mapped_column(String(10), nullable=True)  # co_san|lam_moi
    khuon_phi: Mapped[float] = mapped_column(
        Numeric(18, 2), nullable=False, server_default="0", default=0
    )

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
    # NULL = bước NGOÀI dòng giấy (ghi kẽm, đóng thùng): kế thừa từ công đoạn bỏ trống cả hai ô.
    # Đó là câu trả lời chứ không phải "chưa khai" — xem `services/dong_giay.py`.
    # String(24) khớp `don_vi_do.ma` (VARCHAR(8) rồi (12) đều đã chật một lần).
    don_vi_vao: Mapped[str | None] = mapped_column(String(24), nullable=True)
    don_vi_ra: Mapped[str | None] = mapped_column(String(24), nullable=True)
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
    # ⚠️ `nang_suat` + `don_vi_nang_suat` GỠ 18/09/2026 (mg `0321`): hai cột này CHÉP từ định mức
    # đầu việc của công đoạn, mà đầu việc đã gỡ ⇒ không còn ai nuôi chúng. Bước MÁY vẫn lấy tốc độ
    # đọc SỐNG từ danh mục Máy (không qua cột nào ở đây), bước TỔ nay gõ `so_gio_ke_hoach`.
    # Người kế hoạch gõ đè thời gian chạy → thắng công thức năng suất. NULL = để máy tính.
    chay_phut: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    # DORMANT 2026-08-04 — vệ sinh/rửa mực bỏ khỏi hệ: bước mới luôn 0, engine thôi cộng.
    ve_sinh_phut: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default="0", default=0)
    # "Thời gian khác" (migration 0153) — ô DUY NHẤT người kế hoạch còn gõ được ở tab Thời gian;
    # cộng THẲNG vào thời gian chiếm máy. Chuẩn bị/tốc độ nay kế thừa từ máy, không sửa tại bước.
    phat_sinh_phut: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default="0", default=0)
    di_chuyen_phut: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default="0", default=0)
    # ⚠️ `so_nhan_cong_tieu_chuan` (Kíp chuẩn) GỠ 18/09/2026 (mg `0321`) — chốt *"bỏ luôn logic kíp
    # người mà mấy cái chặn hoặc cảnh báo hoặc phép tính liên quan đến kíp người"*. Hệ thôi biết
    # một việc NÊN mấy người: tổ cử 1 người vào việc thường 5 người cũng không ai cảnh báo, đúng
    # chủ trương máy chỉ ghi nhận. Luật *"phải có ≥ 1 thợ mới bắt đầu được việc"* thì GIỮ — đó là
    # luật về người có mặt, không phải về kíp.
    # SỐ GIỜ KẾ HOẠCH của bước TỔ (18/09/2026, mg `0319`) — người lập kế hoạch gõ tay, đơn vị GIỜ.
    # Mặc định 0 và **không cảnh báo khi để 0**: chốt của chủ dự án *"nếu thiếu thì cứ để 0"*.
    # Đây là thứ THAY cho cả đường tính thời lượng cũ của bước tổ (năng suất khoán ÷ kíp chuẩn),
    # gỡ cùng ngày với đầu việc định mức. Bước MÁY / THUÊ NGOÀI không đọc ô này — chúng vẫn tính
    # từ tốc độ máy. Numeric(8,2) để gõ được 4,5 giờ; không bắt tròn.
    so_gio_ke_hoach: Mapped[float] = mapped_column(
        Numeric(8, 2), nullable=False, server_default="0", default=0
    )

    # --- Phương thức thực hiện ---
    # ⚠️ `khoan_json` (ảnh chụp "Đầu việc thợ làm" của bước) GỠ 18/09/2026 (mg `0321`). Việc khoán
    # nay KHÔNG khai ở bước nữa: thợ chọn ngay lúc GHI MẺ, trong danh sách việc khoán của tổ mình
    # (`san_xuat_batch.piece_rate_id`) — chốt *"ghi mẻ đó nhưng cho công việc chứ không phải công
    # đoạn nữa"*. Ảnh chụp giá dời xuống mẻ, kèm băng "Danh mục đã đổi" của riêng mẻ.
    # `kcs_tieu_chi_bo_sung_json` GỠ ở mg `0283`: checklist KCS nay chỉ còn MỘT nguồn là danh mục
    # `san_xuat_kcs_tieu_chi` gắn theo công đoạn — xem `docs/design-kcs-theo-cong-doan.md`. Đừng
    # bày lại ô gõ thêm dòng riêng cho một lệnh: hai nguồn cho cùng một checklist thì không ai
    # biết bản nào chuẩn, mà dòng gõ tay không mã, không lịch sử, không tái dùng cho lệnh sau.
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
    __table_args__ = (
        UniqueConstraint("lsx_cong_doan_id", "hang_loai", "vat_tu_id", name="uq_lsx_buoc_vat_tu"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lsx_cong_doan_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lsx_cong_doan.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # DANH MỤC nào chứa món này (mg `0280`, 08/09/2026): `"giay"` → `giay_nguyen`, `"vat_tu"` →
    # `vat_tu_in_an`. Trước đó bảng chỉ trỏ được vật tư, còn giấy đi một đường riêng suy từ
    # `quy_cach_json.giay_id` rồi tự treo lên "bước đầu tiên chạm tờ" — hệ đoán cả LOẠI lẫn BƯỚC,
    # nên một lệnh chỉ ôm được đúng một loại giấy và người dùng không sửa được bước tiêu thụ.
    #
    # Cặp `(hang_loai, vat_tu_id)` là khuôn `stock_lots` / `vat_tu_giu_cho` / `stock_requests` /
    # `san_xuat_vat_tu_de_nghi_dong` đã dùng sẵn, nên bảng cân đối và mọi tầng kho hạ nguồn nhận
    # dòng giấy mà không phải rẽ nhánh.
    #
    # Cột id vẫn giữ tên `vat_tu_id` nhưng ĐỌC LÀ `hang_id`: đổi tên là một lượt sửa rộng qua 8 file
    # + 5 file test mà không đổi hành vi nào.
    hang_loai: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default="vat_tu", default="vat_tu", index=True
    )
    vat_tu_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    vat_tu_ma_snapshot: Mapped[str] = mapped_column(String(30), nullable=False)
    vat_tu_ten_snapshot: Mapped[str] = mapped_column(String(150), nullable=False)
    don_vi_snapshot: Mapped[str] = mapped_column(String(16), nullable=False)
    so_luong: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    thu_tu: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # MÁY BUNG hay NGƯỜI KHAI (mg 0191). True = dòng máy tự thêm khi chọn công việc khoán ⇒ lần bung
    # sau được thay bộ mới. False = người tự thêm, hoặc đã sửa số lượng ⇒ máy CHỪA RA, không ghi đè.
    # Không có cờ này thì đổi công việc khoán một cái là mất sạch số người vừa chỉnh.
    tu_dong: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_false(), default=False
    )
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


class LsxDinhKem(Base):
    """Tệp đính kèm của MỘT lệnh: maket, file in, mẫu khách duyệt, ảnh tham khảo…

    Gắn vào cả lệnh, không gắn từng bước, không phân loại. Bytes nằm trong kho file
    (`san-xuat/lsx/<lsx_id>/…`), đọc lại qua `/api/files` có kiểm quyền `san_xuat`. Thêm/xoá ghi
    audit target `lsx:{id}` nên hiện ở tab Nhật ký — bảng này không tự giữ lịch sử.
    """

    __tablename__ = "lsx_dinh_kem"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lsx_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lsx.id", ondelete="CASCADE"), index=True, nullable=False
    )
    ten_tep: Mapped[str] = mapped_column(String(255), nullable=False)       # tên đã làm sạch, để hiện
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)      # /api/files/san-xuat/lsx/…
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    kich_thuoc: Mapped[int] = mapped_column(Integer, nullable=False, default=0)   # byte
    # Soft → users.id. Máy chủ chốt từ tài khoản đang đăng nhập, không nhận từ client.
    nguoi_tai_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tai_luc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    lsx: Mapped["Lsx"] = relationship("Lsx", back_populates="dinh_kems")
