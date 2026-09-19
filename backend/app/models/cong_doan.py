"""Công đoạn (Operation · Routing) — danh mục thao tác + cách tính giá, spec `docs/spec-cong-doan.md` §2.

TẦNG 1 `cong_doan` (danh mục master, ở đây). TẦNG 2 `routing_step` (instance per job) để Phase D
(engine tính giá + jobspec) — chưa dựng vì cần FK jobspec/component. Engine cost/cascade/kẽm =
hàm thuần trong `services/routing_engine.py` (Phase D gọi).

Module MỚI (strangler) — song song `operation.py` cũ. Chưa wired.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint,
    false as sa_false, true as sa_true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base

# prepress=Trước In · print=In · finishing=Gia công sau in · other=Dịch vụ khác.
# "other" = dịch vụ không thuộc dòng chế bản/in/sau-in (vd thuê ngoài đặc thù). Engine key theo
# "print"/"prepress" cụ thể nên "other" rơi vào nhánh finishing-like (mặc định NẰM trên dòng giấy
# như gia công sau in). Phải KHỚP `NHOM_CD` ở frontend/rebuildCatalogConfigs.tsx — mở ở CẢ HAI nơi.
NHOM = ("prepress", "print", "finishing", "other")
CHE_DO_TINH = ("theo_san_luong",)  # "theo_gio" đã gỡ — công đoạn chỉ tính theo công thức/sản lượng
# Đơn vị tính giá công đoạn (bao trùm chế bản + in + sau in). Engine `routing_engine.basis_qty`
# quy đổi mỗi key → số lượng tính tiền từ ctx job.
PRICING_BASIS = (
    "per_sheet",          # Theo số tờ in
    "per_finished_area",  # Theo diện tích thành phẩm (cm²)
    "per_finished_qty",   # Theo số lượng thành phẩm
    "per_book_page",      # Theo số trang sách
    "per_position",       # Theo số vị trí
    "per_bag",            # Theo bao
    "per_carton",         # Theo thùng
    "per_area_sides",     # Theo diện tích (cm²) và số mặt
    "per_sheet_area",     # Theo diện tích tờ in (cm²)
    "per_book_page_q4",   # Theo số trang sách chia 4
    "per_job",            # Trọn gói một lần (cả đơn) — engine ÷ SL ở đơn giá bình quân (khuôn bế…)
    "per_other",          # Khác (nhập tay, giá phẳng)
)
# Dụng cụ DÙNG CHUNG mà bước phải mượn từ kho khuôn. Bật `requires_tooling` nghĩa là: lệnh PHẢI
# gán một dòng khuôn có thật, và hai lệnh mượn cùng một khuôn không được xếp trùng giờ.
#
TOOLING_TYPE = ("khuon_be", "khuon_ep", "khung_lua")
# Cách công đoạn tính bù hao: không / tra bảng (trỏ 1 mã bù hao ở module Bù hao → tra bậc SL) /
# cộng cố định `so_to_bu_hao` tờ (ép kim, UV… — không theo bảng).
KIEU_BU_HAO = ("khong", "tra_bang", "co_dinh")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CongDoan(Base):
    __tablename__ = "cong_doan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ma: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    ten: Mapped[str] = mapped_column(String(150), nullable=False)
    ten_hien_thi: Mapped[str | None] = mapped_column(String(150), nullable=True)  # tên in cho thợ sản xuất
    # Bù hao: cách công đoạn này góp hao. tra_bang → trỏ 1 mã bù hao (`bu_hao_id`) rồi tra bậc theo
    # SL; co_dinh → cộng `so_to_bu_hao` tờ; khong → không góp.
    kieu_bu_hao: Mapped[str] = mapped_column(String(16), nullable=False, server_default="khong", default="khong")
    bu_hao_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)  # → bu_hao.id (soft) khi kieu=tra_bang
    so_to_bu_hao: Mapped[int] = mapped_column(Integer, nullable=False, server_default="50", default=50)  # +tờ hao khi kieu_bu_hao=co_dinh
    # Đơn vị VÀO / RA của công đoạn — KHAI, không đoán theo tên. Từ 06/09/2026 đây là MENU ĐÓNG
    # đúng 5 CHẶNG của dòng giấy (`don_vi_do.TRAM_DONG_GIAY`), KHÔNG còn trỏ vào danh mục đơn vị:
    #   - bước trên dòng giấy khai `to_nguyen → to`, `to → con`, `to → cai`… (chảy một chiều)
    #   - bước KHÔNG chạm giấy (ghi kẽm, đóng thùng) BỎ TRỐNG cả hai — đứng ngoài chuỗi bù hao
    #     của giấy; đơn vị và số của nó do người lập lệnh tự khai ở bước (`tu_khai_don_vi`).
    #
    # NULL vì thế là một CÂU TRẢ LỜI ("ngoài dòng giấy"), không phải "chưa khai". Trước đó bước
    # ngoài dòng khai đơn vị thật (`bai → kem`) và câu hỏi trên-dòng-hay-không đi vòng qua cờ
    # `don_vi_do.tram_dong_giay` — cờ ấy đã gỡ, xem `services/dong_giay.py`.
    #
    # Hệ số quy đổi KHÔNG lưu ở đây: phiếu tính giá đã có `con` (bình bài) và `so_manh_xa` (khổ
    # giấy) — khai lại là đẻ nguồn sự thật thứ hai.
    #
    # String(24) khớp `don_vi_do.ma` — VARCHAR(12) cũ vừa đủ `to_nguyen` (9) nhưng chật ngay khi
    # xưởng khai mã dài hơn, và Postgres ném lỗi độ dài lúc ghi chứ không cắt bớt.
    don_vi_vao: Mapped[str | None] = mapped_column(String(24), nullable=True)
    don_vi_ra: Mapped[str | None] = mapped_column(String(24), nullable=True)
    # ⚠️ `cong_thuc_san_luong` · `don_vi_san_luong` · `he_so_ngoai_dong` GỠ 18/09/2026 (mg `0324`):
    #    công thức sản lượng RA của bước ngoài dòng giấy (vd Ghi kẽm CTP `so_kem` ⇒ 4 bản), đơn vị
    #    của số ấy, và hệ số vào→ra đã ngưng dùng từ 20/08. Số bước ngoài dòng nay do người lập lệnh
    #    tự khai ở bước (`lsx_service.tu_khai_don_vi`); không khai thì bước đứng ở 0.
    nhom: Mapped[str] = mapped_column(String(12), index=True, nullable=False)  # prepress|print|finishing
    # Nhóm MÁY làm được công đoạn này — tên nhóm ở danh mục `nhom_may` ("Máy in"/"Bế"/"Cán màng / UV"…).
    # Chặn gán máy SAI LOẠI ở bước (vd bước Ghi kẽm CTP không cho gán máy Bế). NULL/[] = chưa khai =
    # không ràng buộc. Trục `loai_may` mịn hơn `nhom(3)`: phân biệt được Bế với Cán màng (cùng finishing).
    nhom_may_cho_phep: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Tổ phụ trách: NHIỀU tổ (18/09/2026, mg `0312`) — xem `to_phu_trach` / `department_ids` bên
    # dưới. Cột `department_id` một tổ đã gỡ; bước lệnh CHỌN MỘT trong danh sách này.
    # Lương khoán: công đoạn này có tính khoán không — nguoi (ghi Phiếu sản lượng theo từng người
    # → cột Khoán bảng lương) / khong (không khoán). Không còn 'theo tổ' (đã bỏ tầng sổ khoán).
    khoan_ghi_theo: Mapped[str] = mapped_column(String(8), nullable=False, server_default="khong", default="khong")
    # Pha 5b-2 trừ lỗi: ngưỡng hao CHO PHÉP (không bị trừ dù hỏng). Trừ = phần VƯỢT max(SL×pct, abs)
    # × đơn giá, chỉ khi lỗi DO THỢ, sàn 0. abs = số tuyệt đối (canh máy) chống trừ oan job nhỏ.
    allowed_defect_pct: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False, server_default="0", default=0)
    allowed_defect_abs: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, server_default="0", default=0)

    # Trục tính tiền (khác đơn vị đo)
    che_do_tinh: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="theo_san_luong", default="theo_san_luong"
    )
    pricing_basis: Mapped[str | None] = mapped_column(String(32), nullable=True)  # khi theo_san_luong

    setup_cost: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0", default=0)
    setup_time: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False, server_default="0", default=0)  # phút
    # Cột legacy chỉ giữ để migration/backfill dữ liệu cũ. LSX mới lấy tốc độ từ MÁY
    # (`cong_doan_may.cong_thuc_gio`); bước TỔ thì không có tốc độ nào cả, người lập lệnh gõ SỐ
    # GIỜ KẾ HOẠCH (`lsx_cong_doan.so_gio_ke_hoach`, mg `0319`).
    nang_suat: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    run_rate: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)   # đơn giá theo basis
    rate_tiers: Mapped[list | None] = mapped_column(JSON, nullable=True)            # [{from_qty,rate,kieu,driver}]
    # Bậc đơn giá theo KÍCH THƯỚC thành phẩm (cạnh dài, cm): [{den_cm, don_gia}] — "≤ den_cm → đơn giá".
    # Khi có, engine chọn đơn giá theo cỡ (thay run_rate); vd công dán ≤20cm=100 · 20–40=200 · 40–100=800.
    size_tiers: Mapped[list | None] = mapped_column(JSON, nullable=True)
    first_unit_floor: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)  # sàn bậc đầu (≠ min_charge)
    min_charge: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)         # sàn cả công đoạn

    requires_tooling: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_false(), default=False)
    tooling_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    spoilage_pct: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, server_default="0", default=0)  # KHÔNG áp bước in
    inline_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_false(), default=False)
    cong_thuc_gia: Mapped[str | None] = mapped_column(Text, nullable=True)
    ghi_chu: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_true(), default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    # VẬT TƯ công đoạn này tiêu thụ, mỗi món một công thức định mức riêng (18/09/2026 — tab
    # "Vật tư" của drawer Công đoạn). Trước đây danh sách này neo vào từng ĐẦU VIỆC của tổ
    # (`cong_doan_dau_viec_vat_tu`, gỡ cùng ngày): bước lệnh phải chờ chọn đầu việc mới bung được
    # vật tư, và bước MÁY thì không bung nổi. Neo vào công đoạn thì mọi bước có công đoạn là bung
    # được ngay lúc tạo lệnh.
    vat_tus: Mapped[list["CongDoanVatTu"]] = relationship(
        "CongDoanVatTu", back_populates="cong_doan", order_by="CongDoanVatTu.thu_tu",
        cascade="all, delete-orphan",
    )
    # MÁY chạy được công đoạn này, mỗi dòng mang cách đo GIỜ và cách tính GIÁ của riêng cặp
    # (công đoạn, máy) — xem `CongDoanMay`. Hàng `nhom_may_cho_phep` ở trên nay chỉ còn là BỘ LỌC
    # để chọn máy cho danh sách này.
    may_lam_duoc: Mapped[list["CongDoanMay"]] = relationship(
        "CongDoanMay", back_populates="cong_doan", order_by="CongDoanMay.thu_tu",
        cascade="all, delete-orphan",
    )
    # CÁC TỔ phụ trách công đoạn (18/09/2026) — "Cán màng mờ" do tổ Cán lẫn tổ Thành phẩm làm. Lệnh
    # sản xuất chép MỘT tổ xuống bước (`lsx_cong_doan.department_id`, người kế hoạch chọn trong danh
    # sách này); tổ ĐẦU danh sách là mặc định lúc tạo lệnh / đổi công đoạn. `delete-orphan`: bỏ một
    # tổ khỏi danh sách là xoá dòng nối.
    to_phu_trach: Mapped[list["CongDoanTo"]] = relationship(
        "CongDoanTo", back_populates="cong_doan", order_by="CongDoanTo.thu_tu",
        cascade="all, delete-orphan",
    )

    @property
    def department_ids(self) -> list[int]:
        """Id các tổ phụ trách, ĐÚNG thứ tự người khai chọn — tổ đầu là tổ mặc định của bước."""
        return [t.department_id for t in self.to_phu_trach]

    @department_ids.setter
    def department_ids(self, ids: list[int]) -> None:
        """Thay TRỌN danh sách tổ. Giữ dòng nối của tổ còn lại (chỉ đánh lại `thu_tu`) — cùng khoá
        chính `(cong_doan_id, department_id)`, xoá rồi chèn lại trong một lần flush là vấp thứ tự
        INSERT/DELETE của unit-of-work (xem `PieceRate.department_ids`)."""
        cu = {t.department_id: t for t in self.to_phu_trach}
        moi: list[CongDoanTo] = []
        for i, dept in enumerate(dict.fromkeys(int(x) for x in ids)):
            t = cu.get(dept) or CongDoanTo(department_id=dept)
            t.thu_tu = i
            moi.append(t)
        self.to_phu_trach = moi

    @property
    def to_mac_dinh_id(self) -> int | None:
        """Tổ bước lệnh nhận khi chưa ai chọn — tổ ĐẦU danh sách, trống thì None."""
        ids = self.department_ids
        return ids[0] if ids else None


class CongDoanTo(Base):
    """Một TỔ phụ trách một công đoạn — bảng nối `cong_doan` ↔ `departments`.

    `department_id` soft-ref như mọi cột tổ khác: tổ bị xoá khỏi cây tổ chức thì dòng nối ở lại, form
    hiện "(không còn là tổ)" để người khai tự gỡ. `thu_tu` giữ thứ tự chọn — tổ đầu là mặc định.
    """

    __tablename__ = "cong_doan_to"

    cong_doan_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cong_doan.id", ondelete="CASCADE"), primary_key=True
    )
    department_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    thu_tu: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)

    cong_doan: Mapped["CongDoan"] = relationship("CongDoan", back_populates="to_phu_trach")


class CongDoanVatTu(Base):
    """Vật tư công đoạn tiêu thụ, kèm ĐỊNH MỨC của riêng dòng đó.

    Thay `cong_doan_dau_viec_vat_tu` từ 18/09/2026 (mg `0316`): cùng nội dung, chỉ đổi chỗ neo từ
    ĐẦU VIỆC của tổ lên chính CÔNG ĐOẠN. Đầu việc định mức của tổ gỡ hẳn cùng ngày (mg `0320`) —
    công đoạn là CÔNG NGHỆ, công việc khoán là VIỆC CỦA TỔ, hai thứ không còn bảng giao điểm.

    Vẫn KHÔNG có cột số lượng chết: định mức tuỳ quy cách của từng lệnh (khổ tờ, số màu, số tờ
    chạy), nên cái khai ở đây là CÔNG THỨC (`cong_thuc_luong`), không phải con số. Số suy lúc bung
    ở bước lệnh bằng cách thế quy cách lệnh vào công thức đó. Chưa khai công thức thì KHÔNG bung
    dòng đó, kèm câu lý do — không đoán.

    Vì sao công thức nằm ở ĐÂY chứ không ở món hàng (06/09/2026, lý do còn nguyên giá trị): hai món
    cùng ĐVT `kg` ăn theo hai trục khác hẳn — mực theo SỐ TỜ (`sl_vao / 40000`), dung môi rửa máy
    theo SỐ MÀU (`so_mau * 0.3`: in 5.000 hay 50.000 tờ vẫn 1,2 kg). Và cùng một món ăn khác nhau
    ở hai công đoạn khác khổ.
    """

    __tablename__ = "cong_doan_vat_tu"
    __table_args__ = (
        UniqueConstraint("cong_doan_id", "vat_tu_id", name="uq_cong_doan_vat_tu"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cong_doan_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cong_doan.id", ondelete="CASCADE"), index=True, nullable=False,
    )
    # Soft-ref tới `vat_tu_in_an` — danh mục vật tư có vòng đời riêng, service chặn id không tồn
    # tại hoặc đã ngừng dùng (xem `CongDoanService._soi_vat_tu`).
    vat_tu_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    thu_tu: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)
    cong_thuc_luong: Mapped[str | None] = mapped_column(Text, nullable=True)

    cong_doan: Mapped["CongDoan"] = relationship("CongDoan", back_populates="vat_tus")


class CongDoanMay(Base):
    """Một MÁY chạy được công đoạn này, kèm cách đo giờ và cách tính giá của riêng cặp đó.

    Vì sao là bảng nối chứ không phải cột trên máy hay trên công đoạn (06/09/2026): cả hai con số
    đều là giao của VIỆC × MÁY.
      · `cong_thuc_gio` — treo ở máy (`may_thiet_bi.cong_thuc_luong` cũ) thì mọi công đoạn chạy
        máy đó dùng chung một cách đo, trong khi In khổ 79×109 và In khổ 11×11 đo khác nhau.
      · `cong_thuc_gia` — treo ở công đoạn (`cong_doan.cong_thuc_gia`) thì mọi máy dùng chung một
        đơn giá, trong khi máy 5 màu khổ lớn và máy 2 màu khổ nhỏ có giá khác nhau.

    `may_id` là SOFT-REF (không FK) — cùng lối `piece_rate_id`/`vat_tu_id` ở hai bảng con kia:
    danh mục máy có vòng đời riêng, service chặn id không tồn tại hoặc máy đã thanh lý.

    `cong_thuc_gio` ra LƯỢNG theo đơn vị TỐC ĐỘ của máy, không ra giờ — engine vẫn tự chia tốc độ.
    `cong_thuc_gia` ra TIỀN, và GHI ĐÈ `cong_doan.cong_thuc_gia` khi phiếu tính giá có chọn máy.
    Cả hai để trống = lùi về hành vi cũ (cầu quy đổi cho giờ · công thức của công đoạn cho giá).
    """

    __tablename__ = "cong_doan_may"
    __table_args__ = (
        UniqueConstraint("cong_doan_id", "may_id", name="uq_cd_may"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cong_doan_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cong_doan.id", ondelete="CASCADE"), index=True, nullable=False
    )
    may_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    cong_thuc_gio: Mapped[str | None] = mapped_column(Text, nullable=True)
    cong_thuc_gia: Mapped[str | None] = mapped_column(Text, nullable=True)
    thu_tu: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    cong_doan: Mapped["CongDoan"] = relationship("CongDoan", back_populates="may_lam_duoc")


