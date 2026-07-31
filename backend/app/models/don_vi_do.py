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
    # 1 <tu> = he_so <den>. Dòng SỐ thì > 0 (service chặn 0/âm — chia cho 0 khi đi chiều ngược);
    # dòng CÔNG THỨC lưu 0 vì hệ số chỉ có lúc chạy. Để 0 chứ không để 1: đường nào lỡ đọc nhầm cột
    # này sẽ ra 0 (hỏng thấy ngay) chứ không ra số y như thật mà sai.
    he_so: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    # QUY ĐỔI ĐỘNG — hệ số là công thức, tính lúc dùng: "1 tờ = dinh_luong * dai * rong" kg. Có
    # những cặp không có đáp án chung (tờ 65×86 Ford 70 nặng 0,039 kg, tờ 79×109 Couché 300 nặng
    # 0,258 kg) nhưng TÍNH ĐƯỢC từ khổ + định lượng, nên vẫn thuộc danh mục — chỉ là hệ số biết
    # tính. Biến do NƠI GỌI bơm vào (`quy_doi_service.ngu_canh`): chỉ nơi gọi mới biết bước này
    # đang đếm tờ nguyên hay tờ in.
    cong_thuc: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ghi_chu: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
