"""Danh mục ĐƠN VỊ ĐO + quy đổi — module dùng chung (khoán · kho · mua hàng · tính giá).

Vì sao có bảng này: cùng một số lượng, mỗi phân hệ gọi bằng một đơn vị khác. Bảng khoán của xưởng
ghi **đ/m²** (cán/phủ) hoặc **đ/tấn** (cắt), lệnh sản xuất đếm **tờ**, kho giấy cân **kg**, mua hàng
đặt theo **ram**. Trước đây mỗi chỗ tự giữ hệ số riêng (`lsx_cong_doan.he_so_quy_doi`,
`material.don_vi_phu`, `stock_request_lines.he_so_quy_doi`) — nhiều nguồn thì sớm muộn lệch nhau,
mà lệch ở đây là lệch TIỀN.

MÔ HÌNH: mỗi đơn vị thuộc một **họ quy đổi** (`ho`) và khai `he_so_goc` = có bao nhiêu đơn vị GỐC
của họ trong 1 đơn vị này (m² = 10.000 cm² ⇒ gốc là cm², `he_so_goc(m²) = 10000`). Đổi A→B cùng họ
= `× he_so_goc(A) / he_so_goc(B)`. MỘT cột số, không cần bảng cặp N×N.

Khác họ thì **KHÔNG đổi bằng hệ số** — 1 tờ không bằng 1 con, 1 kg không bằng 1 m². Muốn qua họ
khác phải dùng "cầu theo quy cách" (`services/quy_doi_service.py`): tờ→m² cần khổ tờ in, tờ→kg cần
thêm định lượng… Đây là chốt chống lỗi âm thầm: máy không bao giờ tự nhân hai đơn vị khác bản chất.

KHÔNG khai ở đây thứ phụ thuộc từng mặt hàng ("1 thùng keo = 3 kg" khác "1 thùng mực = ? kg") —
chỗ đó là `material.don_vi_phu` + `he_so_quy_doi`, đã có. Đừng làm hai nơi.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, String, true as sa_true
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# Họ quy đổi GỢI Ý — không phải whitelist (form MỞ, giống `may_thiet_bi.loai_may`): xưởng có họ lạ
# (cuộn, kiện…) thì gõ thêm. Service chuẩn hoá `strip().lower()` khi lưu để hai lần gõ cùng nghĩa
# không thành hai họ khác nhau — mà hai họ khác nhau là "không đổi được cho nhau".
HO_GOI_Y = (
    "dien_tich",    # cm² · m²
    "khoi_luong",   # g · kg · tấn
    "do_dai",       # mm · m
    "to",           # tờ · ram (500 tờ)
    "con",          # con / cái / chiếc
    "cuon",         # cuốn · bộ sách
    "kem",          # bản kẽm
    "bai_in",       # bài bình
    "thung",        # thùng · bao
    "khac",
)

HO_NHAN = {
    "dien_tich": "Diện tích",
    "khoi_luong": "Khối lượng",
    "do_dai": "Độ dài",
    "to": "Tờ",
    "con": "Con / cái",
    "cuon": "Cuốn",
    "kem": "Kẽm",
    "bai_in": "Bài in",
    "thung": "Thùng / bao",
    "khac": "Khác",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DonViDo(Base):
    """1 đơn vị đo + hệ số về đơn vị GỐC của họ nó."""

    __tablename__ = "don_vi_do"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Mã dùng trong công thức / API (m2, kg, tan, to, ram, con…). CHỮ HIỂN THỊ nằm ở `ten`.
    ma: Mapped[str] = mapped_column(String(24), unique=True, index=True, nullable=False)
    ten: Mapped[str] = mapped_column(String(60), nullable=False)          # "m²" · "tấn" · "tờ"
    # Họ quy đổi: chỉ đơn vị CÙNG họ mới đổi được cho nhau bằng `he_so_goc`.
    ho: Mapped[str] = mapped_column(String(24), index=True, nullable=False, default="khac")
    # Bao nhiêu đơn vị GỐC của họ trong 1 đơn vị này. Đơn vị gốc = dòng có he_so_goc = 1.
    # m² → 10000 (gốc cm²) · tấn → 1000 (gốc kg) · ram → 500 (gốc tờ).
    he_so_goc: Mapped[float] = mapped_column(
        Numeric(18, 6), nullable=False, server_default="1", default=1
    )
    # Mốc hệ số hiện tại bắt đầu áp. Sửa hệ số là đổi tiền của mọi phiếu tính về sau → phải nói rõ
    # từ ngày nào; mọi lần sửa còn ghi AuditLog. KHÔNG dựng bảng lịch sử ở lát này.
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
