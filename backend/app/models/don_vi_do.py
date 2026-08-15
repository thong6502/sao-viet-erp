"""Danh mục ĐƠN VỊ ĐO + quy đổi — module dùng chung (khoán · kho · mua hàng · tính giá).

Vì sao có bảng này: cùng một số lượng, mỗi phân hệ gọi bằng một đơn vị khác. Bảng khoán của xưởng
ghi **đ/m²** (cán/phủ) hoặc **đ/tấn** (cắt), lệnh sản xuất đếm **tờ**, kho giấy cân **kg**, mua hàng
đặt theo **ram**. Trước đây mỗi chỗ tự giữ hệ số riêng (`lsx_cong_doan.he_so_quy_doi`,
`material.don_vi_phu`, `stock_request_lines.he_so_quy_doi`) — nhiều nguồn thì sớm muộn lệch nhau,
mà lệch ở đây là lệch TIỀN.

MÔ HÌNH: bảng đơn vị chỉ là DANH SÁCH TÊN; mọi phép đổi nằm ở bảng CẶP `DonViQuyDoi` — "1 tấn =
1.000 kg", đúng cách người ta nói. Hai đơn vị đổi được cho nhau khi và chỉ khi có đường cặp nối
chúng (`services/quy_doi_service.py` dò BFS qua trung gian). Không có "đơn vị chuẩn", không có
"hệ số về đơn vị gốc" — chủ mở form ra không hiểu mình đang điền gì (2026-07-30).

Cặp nào không có đáp án chung nhưng TÍNH ĐƯỢC (1 tờ mấy kg — tuỳ khổ + định lượng) thì khai bằng
CÔNG THỨC (`DonViQuyDoi.cong_thuc`), số ra lúc chạy. Máy không bao giờ tự nhân hai đơn vị chưa ai
nối — thiếu đường hay thiếu biến đều trả "không đổi được", không đoán.

KHÔNG khai ở đây thứ phụ thuộc từng mặt hàng ("1 thùng keo = 3 kg" khác "1 thùng mực = ? kg") —
chỗ đó là `material.don_vi_phu` + `he_so_quy_doi`, đã có. Đừng làm hai nơi.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint,
    false as sa_false,
    true as sa_true,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# Họ quy đổi GỢI Ý — không phải whitelist (form MỞ, giống `may_thiet_bi.loai_may`): xưởng có họ lạ
# (cuộn, kiện…) thì gõ thêm. Service chuẩn hoá `strip().lower()` khi lưu để hai lần gõ cùng nghĩa
# không thành hai họ khác nhau — mà hai họ khác nhau là "không đổi được cho nhau".
HO_GOI_Y = (
    "dien_tich",    # cm² · m²
    "khoi_luong",   # g · kg · tấn
    "do_dai",       # mm · mét
    "to",           # tờ · ram (500 tờ)
    "thanh_pham",   # cái · con · cuốn · bộ · hộp — đều là "một thành phẩm được đếm"
    "kem",          # bản kẽm
    "bai",          # bài in (khớp mã đơn vị `bai` của bước lệnh)
    "luot",         # lượt chạy (cắt demi…)
    "thung",        # thùng · bao
    "khac",
)

# Nhãn người đọc — PHẢI phủ hết `HO_GOI_Y`, thiếu key nào là màn khai hiện mã trần
# ("nhóm thanh_pham") và người dùng không biết đang chọn cái gì.
HO_NHAN = {
    "dien_tich": "Diện tích",
    "khoi_luong": "Khối lượng",
    "do_dai": "Độ dài",
    "to": "Tờ",
    "thanh_pham": "Thành phẩm",
    "kem": "Kẽm",
    "bai": "Bài in",
    "luot": "Lượt",
    "thung": "Thùng / bao",
    "khac": "Khác",
}

# --- DÒNG GIẤY: những TRẠM mà tờ giấy đi qua trong xưởng ----------------------------------------
# Cùng MỘT đống giấy nhưng mỗi chặng đếm một kiểu: mua về đếm TỜ NGUYÊN, xả xong đếm TỜ IN, bế ra
# đếm CON (hoặc gấp thành TAY), đóng xong đếm CÁI. Đây là thứ DUY NHẤT engine cần biết về đơn vị
# để chạy chuỗi bù hao ngược; mọi đơn vị khác (kg · m² · thùng · kẽm · lượt) đứng NGOÀI dòng và
# không cần cờ — NULL là trạng thái bình thường của gần hết danh mục.
#
# Vì sao là CỜ TRÊN DANH MỤC chứ không phải danh sách mã cứng trong code (trước 2026-08-11 nằm ở
# `cong_doan.DON_VI_DONG_GIAY`): công đoạn khai đơn vị nào là việc của xưởng, đơn vị mới thêm ở màn
# Đơn vị phải dùng được ngay. Code chỉ hỏi "đơn vị này đứng ở TRẠM nào", không hỏi "tên nó là gì".
TRAM_TO_NGUYEN = "to_nguyen"
TRAM_TO = "to"
TRAM_CON = "con"
TRAM_TAY = "tay"
TRAM_CAI = "cai"
TRAM_DONG_GIAY = (TRAM_TO_NGUYEN, TRAM_TO, TRAM_CON, TRAM_TAY, TRAM_CAI)
TRAM_NHAN = {
    TRAM_TO_NGUYEN: "Tờ nguyên (giấy mua về)",
    TRAM_TO: "Tờ in",
    TRAM_CON: "Con (mảnh bế ra)",
    TRAM_TAY: "Tay sách",
    TRAM_CAI: "Thành phẩm",
}
# CẦU giữa hai trạm — dòng giấy chảy MỘT CHIỀU và chỉ qua những nhịp CÓ HỆ SỐ:
#     tờ nguyên ──(số mảnh xả)──▶ tờ in ──┬─(con/tờ)─▶ con ─(1/số con)─▶ thành phẩm
#                                         ├─(1)──────▶ tay ─(số tay)──▶ thành phẩm   (khâu sách)
#                                         └─(con hoặc 1/số tay)───────▶ thành phẩm   (lối đi tắt)
#
# Đây là chỗ DUY NHẤT còn liệt kê tay, và nó ĐÚNG chỗ: mỗi nhịp cần một hệ số lấy từ quy cách lệnh
# (bình bài · số mảnh xả · số tay), hệ số đó là CÔNG THỨC nằm ở `lsx_service._he_so_cau`. Thêm đơn
# vị mới vào danh mục thì KHÔNG phải sửa đây; chỉ khi xưởng đẻ ra một nhịp dòng giấy mới thì mới
# phải khai cả hệ số của nó — và lúc đó buộc phải sửa code, đúng ra là thế.
#
# `to_nguyen → cai` KHÔNG có trong danh sách: nhảy cóc qua khâu in thì chẳng ai biết một tờ nguyên
# ra mấy thành phẩm, để lọt là engine lấy hệ số 1 rồi cấp thiếu giấy trong im lặng.
CAU_TRAM = frozenset({
    (TRAM_TO_NGUYEN, TRAM_TO),
    (TRAM_TO, TRAM_CON), (TRAM_CON, TRAM_CAI),
    (TRAM_TO, TRAM_TAY), (TRAM_TAY, TRAM_CAI),
    (TRAM_TO, TRAM_CAI),
})


def tram_chay_xuoi(tram_vao: str | None, tram_ra: str | None) -> bool:
    """Cặp trạm có chảy ĐÚNG CHIỀU dòng giấy không. Cùng trạm = bước không đổi cách đếm (in, KCS).

    Thay `cong_doan.CAP_DON_VI_HOP_LE`: bản cũ liệt kê tay theo MÃ ĐƠN VỊ nên thêm đơn vị là phải
    sửa code. Bản này liệt kê theo TRẠM — đơn vị nào gắn cờ trạm nào thì tự khớp.
    """
    if tram_vao is None or tram_ra is None:
        return False
    return tram_vao == tram_ra or (tram_vao, tram_ra) in CAU_TRAM


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DonViDo(Base):
    """1 đơn vị đo. Quy đổi KHÔNG nằm ở đây — xem `DonViQuyDoi` (bảng cặp)."""

    __tablename__ = "don_vi_do"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Mã dùng trong công thức / API (m2, kg, tan, to, ram, con…). CHỮ HIỂN THỊ nằm ở `ten`.
    ma: Mapped[str] = mapped_column(String(24), unique=True, index=True, nullable=False)
    ten: Mapped[str] = mapped_column(String(60), nullable=False)          # "m²" · "tấn" · "tờ"
    # LOẠI ĐO (diện tích · khối lượng · tờ · thành phẩm…). KHÔNG còn là điều kiện để quy đổi —
    # quy đổi bây giờ đi theo cặp đã khai. `ho` chỉ để: gom nhóm khi hiển thị, và cho các CẦU theo
    # quy cách biết đích thuộc loại nào (tờ → m² là cầu sang loại diện tích).
    ho: Mapped[str] = mapped_column(String(24), index=True, nullable=False, default="khac")
    # ⚠️ CỘT CŨ — mô hình "hệ số về đơn vị gốc" đã bỏ (chủ 2026-07-30: khó hiểu, người nghĩ theo
    # CẶP "1 tấn = 1.000 kg"). Giữ cột để không mất dữ liệu lịch sử; KHÔNG đọc ở bất kỳ đâu nữa —
    # nguồn chân lý là `don_vi_quy_doi`. Đọc lại cột này là đẻ ra nguồn thứ hai.
    he_so_goc: Mapped[float] = mapped_column(
        Numeric(18, 6), nullable=False, server_default="1", default=1
    )
    # Mốc quy đổi hiện tại bắt đầu áp. Sửa số quy đổi là đổi tiền của mọi phiếu tính về sau → phải
    # nói rõ từ ngày nào; mọi lần sửa còn ghi AuditLog. KHÔNG dựng bảng lịch sử ở lát này.
    hieu_luc_tu: Mapped[date | None] = mapped_column(Date, nullable=True)
    ghi_chu: Mapped[str | None] = mapped_column(String(500), nullable=True)

    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_true(), default=True
    )
    # ⚠️ CỘT CHẾT 15/08/2026 — KHÔNG nơi nào đọc nữa, giữ để dữ liệu cũ không mất.
    #
    # Ý định ban đầu: lọc ô "Đơn vị tốc độ" của màn Máy cho khỏi bày cả danh mục. Cái hỏng là
    # **không bao giờ có ô nào để bật cờ này** — chỉ migration 0154 bật sẵn cho 8 mã và seed set
    # theo đúng 8 mã ấy. Nên nó không phải "cờ người dùng khai", nó là một danh sách cứng nằm dưới
    # DB: đơn vị xưởng tự khai thì cờ = false vĩnh viễn và không dùng làm tốc độ được.
    #
    # Chủ chốt 15/08: ô chọn bày MỌI đơn vị đang `active`. Danh sách dài hơn vài dòng, đổi lại khai
    # đơn vị nào cũng dùng được ngay — đúng lẽ của module Đơn vị & quy đổi.
    #
    # Xoá cột phải viết migration nên để lượt sau; đừng đọc lại nó, và đừng dựng bộ lọc mới ở đây.
    dung_lam_toc_do: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_false(), default=False
    )
    # Đơn vị này đứng ở TRẠM nào trên dòng giấy — xem khối `TRAM_DONG_GIAY` đầu file. NULL = ngoài
    # dòng giấy (kg · thùng · kẽm · lượt…), là trạng thái của gần hết danh mục.
    #
    # String chứ không Boolean: engine cần biết trạm NÀO để kiểm chiều chảy (tờ nguyên → tờ in →
    # con/tay → cái); Boolean chỉ nói được "có nằm trên dòng hay không" nên không chặn nổi `cai → to`.
    tram_dong_giay: Mapped[str | None] = mapped_column(String(12), nullable=True)
    # CÁCH ĐO — công thức ĐỊNH NGHĨA chính đơn vị này (mg 0192, nền BOM). Đọc là:
    #
    #     "một <đơn vị này> đo bằng <công thức>", biến lấy từ quy cách của việc đang làm.
    #     vd  m² tờ in  :=  dai_in * rong_in * to_sau_in
    #
    # KHÁC HẲN `don_vi_quy_doi.cong_thuc`: dòng bên kia nối HAI đơn vị ("1 tờ = … kg"), còn cột này
    # là đơn vị TỰ ĐỊNH NGHĨA, không đổi sang cái gì. Nhờ vậy mỗi đơn vị có đúng MỘT cách đo —
    # không có gì để chọn nhầm lúc bung vật tư ở bước lệnh.
    #
    # Cũng KHÁC công thức ở Giấy · Vật tư khác · Công đoạn: ba ô đó ra TIỀN, ô này ra LƯỢNG.
    cong_thuc: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class DonViQuyDoi(Base):
    """1 CẶP quy đổi: "1 <tu> = <he_so> <den>" — đúng cách người ta nói ("1 tấn = 1.000 kg").

    Nguồn chân lý của mọi phép đổi. Cạnh đi HAI CHIỀU: khai `tấn → kg = 1.000` thì máy đổi ngược
    `kg → tấn` bằng 1/1.000, khỏi khai hai dòng.

    Cặp chưa khai trực tiếp thì máy DÒ ĐƯỜNG qua trung gian (hỏi tấn→g mà chỉ có tấn→kg và kg→g
    thì nhân dọc đường). Đổi lại, hai cặp có thể mâu thuẫn nhau (1 tấn = 1.000 kg nhưng 1 tấn =
    999.000 g) — service CHẶN không cho lưu cặp làm lệch đường đã có (chủ chốt 2026-07-30), nếu
    không thì tiền lệch mà không ai biết.
    """

    __tablename__ = "don_vi_quy_doi"
    __table_args__ = (
        UniqueConstraint("tu_id", "den_id", name="uq_don_vi_quy_doi_cap"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # FK THẬT + CASCADE: xoá đơn vị thì cặp của nó không được ở lại làm đường đi ma.
    tu_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("don_vi_do.id", ondelete="CASCADE"), index=True, nullable=False
    )
    den_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("don_vi_do.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # 1 <tu> = he_so <den>, LUÔN là số cố định > 0 (service chặn 0/âm — chia cho 0 khi đi ngược).
    # 🔴 Cột `cong_thuc` (quy đổi ĐỘNG "1 tờ = dinh_luong*dai*rong kg") ĐÃ GỠ 14/08/2026, mg 0198.
    # Lý do: cùng một đơn vị đích có thể tính ra bằng nhiều đường ⇒ BOM không biết chọn đường nào.
    # Nay CÁCH ĐO khai ở CHÍNH đơn vị (`don_vi_do.cong_thuc`, mg 0192) và trả thẳng LƯỢNG của cả
    # lệnh, còn giấy/vật tư có công thức riêng đè lên (`giay_nguyen.cong_thuc_luong` mg 0195,
    # `vat_tu_in_an.cong_thuc_luong` mg 0194). Cặp trong bảng này chỉ còn hệ số chết.
    he_so: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    ghi_chu: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
