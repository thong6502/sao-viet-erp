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

# prepress=Chế bản · print=In · finishing=Gia công sau in · other=Dịch vụ khác.
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
    # Đơn vị VÀO / RA của công đoạn — KHAI, không đoán theo tên. MÃ trong danh mục `don_vi_do`
    # (soft-ref như mọi chỗ khác dùng đơn vị), không còn bó trong 5 mã dòng giấy:
    #   - bước trên dòng giấy khai `to_nguyen → to`, `to → con`, `to → cai`… (chảy một chiều)
    #   - bước KHÔNG chạm giấy khai đơn vị THẬT của nó: ghi kẽm `bai → kem`, trộn keo `cai → me`
    # Cờ `don_vi_do.tram_dong_giay` mới là thứ nói bước có nằm trên dòng giấy hay không.
    #
    # NULL = CHƯA KHAI (dữ liệu cũ, hoặc bước kế hoạch tự thêm) → engine lùi về luật theo `nhom`.
    # Đây là trạng thái tạm, không phải cách khai bước ngoài dòng giấy nữa.
    #
    # Hệ số quy đổi KHÔNG lưu ở đây: phiếu tính giá đã có `con` (bình bài) và `so_manh_xa` (khổ
    # giấy) — khai lại là đẻ nguồn sự thật thứ hai.
    #
    # String(24) khớp `don_vi_do.ma` — VARCHAR(12) cũ vừa đủ `to_nguyen` (9) nhưng chật ngay khi
    # xưởng khai mã dài hơn, và Postgres ném lỗi độ dài lúc ghi chứ không cắt bớt.
    don_vi_vao: Mapped[str | None] = mapped_column(String(24), nullable=True)
    don_vi_ra: Mapped[str | None] = mapped_column(String(24), nullable=True)
    # ⚠️ CỘT NGƯNG DÙNG 20/08/2026 — engine KHÔNG đọc nữa. Hệ số vào→ra của bước ngoài dòng nay lấy
    # TỪ cầu `don_vi_quy_doi` (module Đơn vị & quy đổi) qua `LsxService._he_so_ngoai_dong`: nguồn
    # chân lý duy nhất, thiếu cầu thì BÁO LỖI chứ không mặc định ×1. Ô khai đã gỡ khỏi schema/repo/UI.
    # Giữ cột để không mất dữ liệu; drop bằng migration ở lượt sau. Đọc lại là đẻ nguồn thứ hai gây sai.
    #
    # (Ý cũ) HỆ SỐ vào → ra cho bước NGOÀI dòng giấy (mg 0196). "Một đơn vị vào đẻ ra mấy đơn vị ra."
    #
    # Trên dòng giấy KHÔNG khai ở đây: hệ số ở đó là số con/tờ · số mảnh xả · số tay, đều suy từ
    # quy cách của LỆNH (`_he_so_cau`). Bày ô ra cho bước trên dòng là mời gõ đè lên bình bài —
    # hai nguồn cho một số, sớm muộn lệch.
    #
    # Ngoài dòng thì không có quy cách nào nói "1 bài ra mấy kẽm", nên người phải khai. Chỉ cần
    # khi HAI ĐƠN VỊ KHÁC NHAU: `kẽm → kẽm` thì hệ số luôn 1, hỏi là hỏi thừa.
    #
    # Vì sao vẫn cần dù mỗi đơn vị đã có công thức riêng: nếu CẢ HAI đầu đều đọc công thức thì hai
    # đầu chốt cứng, hao hụt hết chỗ nhét (đúng bệnh `vao = ra = so_kem` của bản cũ). Chỉ vế RA đọc
    # công thức; vế VÀO suy ngược qua hệ số + hao, y hệt dòng giấy.
    he_so_ngoai_dong: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    # CÔNG THỨC SẢN LƯỢNG RA của bước NGOÀI dòng giấy (mg `0214`, 17/08/2026).
    #
    # "Bước này ra bao nhiêu <đơn vị ra>" — vd Ghi kẽm CTP khai `so_kem` ⇒ 4 bản tốt, hỏng 20% ⇒
    # máy suy VÀO = 5. Chỉ vế RA khai; vế VÀO suy ngược qua `he_so_ngoai_dong` + bù hao (xem ghi chú
    # ngay trên).
    #
    # Trước đó số này lấy từ CÔNG THỨC CỦA ĐƠN VỊ RA (`don_vi_do.cong_thuc`, mg `0192`) — sai chủ
    # sở hữu: "một bước ghi kẽm ra mấy bản" là việc của BƯỚC, không phải thuộc tính của đơn vị "bản
    # kẽm"; hai công đoạn cùng đo bằng `kem` có thể ra số khác nhau, mà công thức treo ở đơn vị thì
    # cả hai buộc dùng chung. Cột kia gỡ ở mg `0215` cùng đợt.
    #
    # Bước TRÊN dòng giấy bỏ qua cột này: số của chúng đến từ chuỗi bù hao ngược (tờ → con → tay →
    # cái). Khai vào đây cũng không ai đọc — engine chỉ hỏi nó ở nhánh ngoài dòng.
    cong_thuc_san_luong: Mapped[str | None] = mapped_column(String(200), nullable=True)
    nhom: Mapped[str] = mapped_column(String(12), index=True, nullable=False)  # prepress|print|finishing
    # Nhóm MÁY làm được công đoạn này — tên nhóm ở danh mục `nhom_may` ("Máy in"/"Bế"/"Cán màng / UV"…).
    # Chặn gán máy SAI LOẠI ở bước (vd bước Ghi kẽm CTP không cho gán máy Bế). NULL/[] = chưa khai =
    # không ràng buộc. Trục `loai_may` mịn hơn `nhom(3)`: phân biệt được Bế với Cán màng (cùng finishing).
    nhom_may_cho_phep: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Phòng ban / tổ phụ trách công đoạn (soft-ref → departments.id). Khi phát Lệnh SX, mỗi bước
    # công đoạn đẩy xuống đúng tổ này. Nullable: công đoạn cũ chưa gán vẫn hợp lệ.
    department_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)  # → departments.id (soft)
    # KCS kiêm nhiệm (module KCS kiêm nhiệm, mg `0250`): công đoạn này TỰ THÂN là một bước KIỂM TRA
    # CHẤT LƯỢNG (khác `department_id` — tổ nào làm bước; đây là bước làm GÌ). Khai ở DANH MỤC nên
    # mọi lệnh dựng routing từ công đoạn này về sau đều snapshot cờ xuống `lsx_cong_doan.la_kcs`/
    # `bai_ghep_cong_doan.la_kcs` (logic snapshot/kế thừa là việc của Task 2 — ở đây CHỈ khai cột).
    la_kcs: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_false(), default=False)
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
    # Cột legacy chỉ giữ để migration/backfill dữ liệu cũ. LSX mới lấy tốc độ từ máy hoặc định mức
    # `cong_doan_dau_viec`, không còn đọc năng suất chung của công đoạn.
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

    dau_viec_dinh_muc: Mapped[list["CongDoanDauViec"]] = relationship(
        "CongDoanDauViec", back_populates="cong_doan", order_by="CongDoanDauViec.id",
        cascade="all, delete-orphan",
    )


class CongDoanDauViec(Base):
    """Định mức nhân lực khi đầu việc của tổ được chọn làm bước Tổ tại KHSX."""

    __tablename__ = "cong_doan_dau_viec"
    __table_args__ = (
        UniqueConstraint("cong_doan_id", "piece_rate_id", name="uq_cd_dau_viec_rate"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cong_doan_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cong_doan.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Soft-ref tới piece_rates: bảng giá có vòng đời riêng; service chặn id/tổ không hợp lệ.
    piece_rate_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    nang_suat_nguoi_gio: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    # Dải năng suất — `nang_suat_nguoi_gio` giữ nghĩa TRUNG BÌNH, hai cột này là mức thấp/cao,
    # đúng lối máy (`may_thiet_bi.toc_do` + `toc_do_min`/`toc_do_max`). Nullable: đầu việc chưa
    # khai dải thì ba mức bằng nhau và râu Gantt co về một điểm — KHÔNG bịa min=max=TB.
    nang_suat_nguoi_gio_min: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    nang_suat_nguoi_gio_max: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    # Đơn vị năng suất do người khai CHỌN (mã `<đơn vị>_gio`, cùng bảng với ô "Đơn vị tốc độ" của
    # máy). Đây là NHÃN KHAI BÁO: engine chia thẳng SL vào cho năng suất, KHÔNG quy đổi — bước
    # quy đổi làm sau. Trống = giữ lối cũ (suy theo đơn vị vào của công đoạn).
    don_vi_nang_suat: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Ba mốc nhân lực: tối thiểu ≤ tiêu chuẩn ≤ tối đa. `tieu_chuan` là số điền sẵn vào bước,
    # `toi_da` là trần tính thời gian (thêm người nữa không nhanh hơn). `toi_thieu` là KHAI BÁO —
    # chưa vào công thức, mặc định 1 nghĩa là không ràng buộc.
    so_nguoi_toi_thieu: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    so_nguoi_tieu_chuan: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    so_nguoi_toi_da: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    cong_doan: Mapped["CongDoan"] = relationship("CongDoan", back_populates="dau_viec_dinh_muc")
    # VẬT TƯ đầu việc này tiêu thụ — nền của BOM (12/08/2026). Khai một lần ở danh mục, đến lệnh thì
    # chọn công việc khoán là bung sẵn vào khối "Vật tư cần dùng" của bước.
    vat_tus: Mapped[list["CongDoanDauViecVatTu"]] = relationship(
        "CongDoanDauViecVatTu", back_populates="dau_viec",
        order_by="CongDoanDauViecVatTu.thu_tu", cascade="all, delete-orphan",
    )

    @property
    def vat_tu_ids(self) -> list[int]:
        """Danh sách id vật tư — hình dạng API dùng (`CongDoanDauViecRow` đọc qua from_attributes).
        Giữ ở đây để schema khỏi phải biết bảng nối, và để nơi gọi khỏi tự `.vat_tus` rồi map."""
        return [v.vat_tu_id for v in self.vat_tus]


class CongDoanDauViecVatTu(Base):
    """Vật tư mà MỘT đầu việc của công đoạn tiêu thụ — danh sách thuần, KHÔNG có số lượng.

    Vì sao không có số lượng: định mức tuỳ quy cách của từng lệnh (khổ tờ, số màu, số tờ chạy), nên
    một con số khai ở danh mục là số chết. Số lượng suy lúc bung ở bước lệnh, bằng cách đổi số lượng
    của bước sang đơn vị của vật tư qua QUY ĐỔI ĐỘNG (`quy_doi_service.doi_theo_quy_cach`). Đổi
    không được thì KHÔNG bung dòng đó kèm câu lý do — không đoán.

    Vì sao neo vào `cong_doan_dau_viec` chứ không vào `piece_rates`: đây đúng là dòng người dùng
    nhìn thấy trong bảng "Đầu việc và định mức của tổ" ở drawer Công đoạn, và cho phép cùng một đầu
    việc dùng vật tư khác nhau ở hai công đoạn khác nhau.
    """

    __tablename__ = "cong_doan_dau_viec_vat_tu"
    __table_args__ = (
        UniqueConstraint("cong_doan_dau_viec_id", "vat_tu_id", name="uq_cd_dau_viec_vat_tu"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cong_doan_dau_viec_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cong_doan_dau_viec.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    # Soft-ref tới `vat_tu_in_an` — cùng lối với `piece_rate_id` ở trên: danh mục vật tư có vòng đời
    # riêng, service chặn id không tồn tại hoặc đã ngừng dùng.
    vat_tu_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    thu_tu: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    dau_viec: Mapped["CongDoanDauViec"] = relationship(
        "CongDoanDauViec", back_populates="vat_tus"
    )


