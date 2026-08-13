"""Thiết bị / Máy (Machine) — master data, spec `docs/spec-may-thiet-bi.md`.

1 bảng master `may_thiet_bi`, phân biệt bằng `loai_may` (chữ TỰ DO, khớp danh mục `nhom_may`).
Máy là **spec năng lực**: khổ giấy/kẽm, vùng in, chừa lề, tốc độ, thời gian chuẩn bị — những số
Tính giá · Lệnh SX · Xếp lịch · Bình bài thật sự đọc.

🔴 **DỌN LỚN 11/08/2026 — bỏ ~50 cột không có ô nhập.** Chủ chốt: *"không nhập liệu được thì là
rác"*. Đã gỡ khỏi model (cột nằm lại orphan trong Postgres — dự án không có Alembic, không drop,
nhưng KHÔNG còn code nào đọc/ghi):
  · **BHR** (`von_dau_tu` `nam_khau_hao` `gio_lam_nam` `availability_pct` `luong_gio` `markup_pct`…)
    — cả khối giá vốn giờ máy + `compute_bhr` + endpoint `/bhr`, `/bhr-preview`. Có spec §4 và test
    xanh, NHƯNG chưa bao giờ có ô nhập trên form Máy và không engine giá nào gọi ⇒ luôn null.
  · **Tài sản** `ma_tai_san` `ma_TK_cost_center` `nha_cung_cap` `ngay_dua_vao_su_dung`
    `het_han_bao_hanh` `phuong_phap_khau_hao`.
  · **Nhận diện thừa** `dia_diem` `phong_ban_id` `ghi_chu_2` `nhom_cost_center` `finishing_subtype`.
  · **Năng lực không nối** `min_stock_gsm` `max_stock_gsm` `vat_lieu_ho_tro_class` `so_ca`
    `chi_so_dem_luot` `so_may_song_song`.
  · **Offset chưa nối engine** `so_units` `units_truoc` `units_sau` `khoa_class` `co_tro_mat`
    `cho_phep_tu_tro` `cho_phep_tro_dau_duoi` `bu_hao_canh_may_per_mau` `bu_hao_chay_pct`
    `ho_tro_cip3` (hàm `routing_engine.so_to_in_gross` nhận bù hao qua THAM SỐ, không đọc máy).
  · **Bảo trì thô** `ngay_bao_tri_gan_nhat` `chu_ky_bao_tri` `chu_ky_bao_tri_don_vi`
    `ngay_bao_tri_ke_tiep` — thay bằng khối **Lịch bảo trì định kỳ** (`fields_theo_loai.lich_bao_tri`:
    đầu việc + chu kỳ ngày/tuần/tháng/năm, nhiều hạng mục/máy).
  · **Dormant** `ca_lam_ids` `thoi_gian_rua_muc`.
  · **`trang_thai` + property `active`** — bỏ ô "Tình trạng" khỏi form ⇒ mọi máy luôn `active`,
    cờ đó chưa bao giờ phân loại được gì. Máy dừng vì bảo trì/hỏng thì khoá theo KHOẢNG THỜI GIAN
    ở `machine_unavailable_periods` (Xếp lịch đọc cái đó), không phải một cờ mức-máy.
Thêm cột lại chỉ khi có ô nhập đi kèm — đừng dựng cột trước rồi hẹn form sau.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    true as sa_true,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# --- Enums (khớp spec + engine) ---
LOAI_MAY = (
    "press_offset_sheet", "press_offset_web", "press_digital", "press_flexo_label",
    "press_gravure", "wide_format", "prepress_ctp", "finishing", "thue_ngoai", "other",
)
# `TRANG_THAI` (active/maintenance/retired) ĐÃ GỠ 11/08/2026 cùng cột `trang_thai`: không có ô
# nhập nào trên form Máy ⇒ mọi máy luôn "active", cái cờ chưa bao giờ phân loại được gì. Máy dừng
# vì bảo trì/hỏng thì khoá theo KHOẢNG THỜI GIAN ở `machine_unavailable_periods` — đó mới là thứ
# Xếp lịch thật sự đọc.
# Danh sách CỐ ĐỊNH, khớp ô chọn ở `DonViTocDoField` (FE). Chủ chốt 04/08/2026.
# CẢNH BÁO: chỉ `to_gio · cai_gio · kem_gio` là Lệnh SX khớp được để ra thời lượng
# (`_DV_VAO_SANG_NS` trong `lsx_service.py`); phần còn lại chỉ để GHI NHẬN năng lực máy.
# Hằng số này hiện KHÔNG được validate ở đâu — máy vẫn lưu được giá trị ngoài danh sách.
DON_VI_TOC_DO = (
    "ban_proof_gio", "mau_gio", "kem_gio", "to_gio", "tan_gio",
    "me_gio", "m2_gio", "nhip_gio", "hop_gio",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MayThietBi(Base):
    __tablename__ = "may_thiet_bi"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ---- Nhận diện ----
    ma: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    ten: Mapped[str] = mapped_column(String(150), nullable=False)
    loai_may: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    hang_san_xuat: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    so_seri: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ghi_chu: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ---- Năng lực / tốc độ ----
    # `toc_do` = tốc độ TRUNG BÌNH (nhãn màn hình đổi 03/08/2026). Tên cột GIỮ NGUYÊN: Tính giá,
    # Lệnh SX, Xếp lịch và Chọn-máy-hợp-khổ đều đang đọc `toc_do`, đổi tên là gãy cả bốn.
    toc_do: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    # Dải năng lực máy — CHỈ ĐỂ KHAI (chủ 03/08/2026: "khai ra vậy thôi, sau họ dùng họ tự biết
    # lấy ra"). KHÔNG nối vào công thức nào: mọi tính thời gian vẫn chạy bằng `toc_do` trung bình.
    # Muốn cho lịch chạy bằng KHOẢNG [sớm–muộn] thì phải viết lại lõi xếp lịch (`_cong_gio_lam`
    # cộng MỘT con số phút), không phải chỉ đọc thêm hai cột này.
    toc_do_min: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    toc_do_max: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    # Mã dạng `<đơn vị đếm>_gio`, SUY RA từ danh mục `don_vi_do` (chủ tự thêm/xoá đơn vị ở màn
    # "Đơn vị & quy đổi"). `don_vi_do.ma` rộng 24 ⇒ mã ở đây có thể tới 28 ký tự: 16 là TRÀN.
    # SQLite bỏ qua độ dài nên test vẫn xanh, Postgres thật thì lỗi lúc lưu — nới lên 32 (mg 0153).
    don_vi_toc_do: Mapped[str | None] = mapped_column(String(32), nullable=True)
    makeready_time_default: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)  # phút
    # 🔴 `cho_ky_thuat_gio` ĐÃ GỠ 13/08/2026 — xem chú thích cùng tên ở `models/cong_doan.py`.
    # Cột để nằm im trong Postgres, không đọc ở đâu nữa.
    # Kíp chuẩn cần để vận hành máy — hoạch định nhân lực, KHÔNG nhân tốc độ máy.
    so_nhan_cong: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, server_default="1", default=1)

    # ---- Khổ · vùng in · chừa lề (★ = engine bình bài đọc) ----
    kho_max_dai: Mapped[int | None] = mapped_column(Integer, nullable=True)   # ★ bình bài
    kho_max_rong: Mapped[int | None] = mapped_column(Integer, nullable=True)  # ★
    kho_min_dai: Mapped[int | None] = mapped_column(Integer, nullable=True)   # ★
    kho_min_rong: Mapped[int | None] = mapped_column(Integer, nullable=True)  # ★
    kho_kem_dai: Mapped[int | None] = mapped_column(Integer, nullable=True)   # khổ bản kẽm (mm)
    kho_kem_rong: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vung_in_dai: Mapped[int | None] = mapped_column(Integer, nullable=True)   # vùng in lớn nhất (mm)
    vung_in_rong: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gripper_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)    # mép nhíp trên BẢN KẼM (~44mm)
    # Nhíp GIẤY — cạnh máy kẹp tờ giấy, KHÁC `gripper_mm` (nhíp kẽm) cả về nghĩa lẫn độ lớn (~8-12mm).
    # ★ bình bài: trừ vào chiều DÀI tờ in (1 cạnh nạp), KHÔNG trừ chiều rộng.
    nhip_giay_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    le_hong_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)          # ★ trừ MỖI BÊN chiều rộng
    duoi_thang_mau_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)   # ★ trừ chiều dài (đuôi tờ)

    # ---- Túi JSON: field đặc thù theo loai_may + khối con của form ----
    # Khoá đang dùng: `chuan_bi_khoan` (các khoản chuẩn bị → cộng ra makeready_time_default) và
    # `lich_bao_tri` — Lịch bảo trì định kỳ, mỗi phần tử là một GÓI:
    #   {id, viec, so, don_vi ∈ ngay|tuan|thang|nam, ngay_bat_dau, hang_muc: [{id, ten}]}
    # `id` (dạng `hm-...`) là NEO của phiếu bảo trì (`bao_tri_phieu.goi_id`) — đổi tên gói không mất
    # mốc. `ngay_bat_dau` (ISO date) là mốc cho kỳ ĐẦU; từ kỳ 2 hạn tính từ ngày hoàn thành phiếu
    # gần nhất, xem `services/ky_thuat_may_service.py::han_ke_tiep`.
    fields_theo_loai: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


# Tên nhóm máy MẶC ĐỊNH — nguồn DUY NHẤT cho cả migration backfill lẫn seed.
# `schema_migrations` sống qua `drop_all` nên test không chạy lại migration; chỉ seed dựng được
# DB test. Chép danh sách ra hai chỗ là sớm muộn hai chỗ lệch nhau.
NHOM_MAY_MAC_DINH = ("Máy in", "In ngoài", "Cán màng / UV", "Bồi", "Bế")


class NhomMay(Base):
    """Danh mục NHÓM MÁY — danh sách tên được phép chọn ở ô "Nhóm máy" của màn Thiết bị.

    ⚠️ **KHÔNG phải khoá ngoại.** `may_thiet_bi.loai_may` vẫn lưu CHỮ, và bảng này chỉ quản danh
    sách tên được bày ra. Lý do: chuỗi đó đang được đọc ở Lệnh SX (`LsxBuocDrawer`,
    `LsxDetailView`, `LsxRoutingTable`), Phiếu tính giá, và ở chính màn Máy (`isMayIn()` quyết định
    ẩn/hiện ~8 ô, facet tab lọc theo nó). Đổi sang id là kéo theo cả 5 chỗ đó + migration dữ liệu,
    trong khi việc cần làm chỉ là "cho thêm và cho xoá tên trong danh sách".

    Hệ quả phải nhớ: xoá một nhóm KHÔNG tự sửa máy đang mang tên đó ⇒ service phải CHẶN xoá khi
    còn máy dùng (kèm số máy), nếu không là để lại máy thuộc nhóm không còn tồn tại."""

    __tablename__ = "nhom_may"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ten: Mapped[str] = mapped_column(String(60), unique=True, index=True, nullable=False)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_true(), default=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
