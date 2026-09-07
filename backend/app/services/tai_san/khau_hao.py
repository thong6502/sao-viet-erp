"""Engine khấu hao / phân bổ — HÀM THUẦN, không chạm DB.

Bốn đường vào sổ (nạp đầu kỳ · ghi tăng · nâng cấp · CCDC giảm một phần lô) đều quy về bộ ba
`co_so_trich` / `so_thang_con` / `moc_tu_ngay`, nên engine chỉ có một luật:

    mức tròn tháng = co_so_trich // so_thang_con

Prorate theo NGÀY chỉ ở hai chỗ: tháng chứa `moc_tu_ngay` (khi mốc không rơi vào ngày 1) và
tháng ghi giảm. Luôn cap bởi `nguyen_gia - luy_ke` nên kỳ cuối tự trích nốt phần lẻ do làm
tròn — không cần luật riêng cho kỳ cuối.

Làm tròn XUỐNG đồng ở từng kỳ (`//`), phần dư dồn hết vào kỳ cuối. Cách ngược lại (làm tròn
đều rồi bù ở kỳ cuối bằng số ÂM) cho ra dòng "trích -37đ" trên bảng in — kế toán không giải
thích được với cơ quan thuế.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class DongDuKien:
    """Một dòng của bảng khấu hao DỰ KIẾN (chưa ghi sổ, chỉ để nhìn trước)."""

    nam: int
    thang: int
    muc_trich: int
    luy_ke: int
    con_lai: int


def _so_ngay(nam: int, thang: int) -> int:
    return calendar.monthrange(nam, thang)[1]


def _sang_thang(nam: int, thang: int) -> tuple[int, int]:
    return (nam + 1, 1) if thang == 12 else (nam, thang + 1)


def muc_trich_thang(co_so_trich: int, so_thang_con: int) -> int:
    """Mức trích tròn một tháng, làm tròn XUỐNG đồng."""
    if so_thang_con <= 0:
        raise ValueError("so_thang_con phải > 0")
    return int(co_so_trich) // int(so_thang_con)


def trich_mot_ky(
    *,
    co_so_trich: int,
    so_thang_con: int,
    moc_tu_ngay: date,
    nguyen_gia: int,
    luy_ke: int,
    nam: int,
    thang: int,
    ngay_giam: date | None = None,
) -> int:
    """Số tiền trích của ĐÚNG một kỳ (nam, thang). 0 nếu kỳ nằm ngoài đời tài sản."""
    con_lai = int(nguyen_gia) - int(luy_ke)
    if con_lai <= 0 or so_thang_con <= 0:
        return 0

    ngay_trong_thang = _so_ngay(nam, thang)
    dau_ky = date(nam, thang, 1)
    cuoi_ky = date(nam, thang, ngay_trong_thang)

    # Chưa tới mốc, hoặc đã ghi giảm từ kỳ trước ⇒ kỳ này không có gì để trích.
    if moc_tu_ngay > cuoi_ky:
        return 0
    if ngay_giam is not None and ngay_giam < dau_ky:
        return 0

    tu = max(moc_tu_ngay, dau_ky)
    den = min(ngay_giam, cuoi_ky) if ngay_giam is not None else cuoi_ky
    if den < tu:
        return 0

    muc = muc_trich_thang(co_so_trich, so_thang_con)
    so_ngay_dung = (den - tu).days + 1
    if so_ngay_dung < ngay_trong_thang:
        muc = muc * so_ngay_dung // ngay_trong_thang
    return min(muc, con_lai)


def lich_du_kien(
    *,
    co_so_trich: int,
    so_thang_con: int,
    moc_tu_ngay: date,
    nguyen_gia: int,
    luy_ke: int,
    so_ky_toi_da: int = 400,
) -> list[DongDuKien]:
    """Bảng khấu hao dự kiến từ mốc tới khi hết giá trị — hiện ngay sau khi ghi tăng.

    `so_ky_toi_da` là chốt chặn vòng lặp: mức trích có thể bằng 0 (nguyên giá quá nhỏ so với số
    tháng) và khi đó lũy kế không bao giờ đuổi kịp nguyên giá.
    """
    ra: list[DongDuKien] = []
    nam, thang = moc_tu_ngay.year, moc_tu_ngay.month
    dang_luy_ke = int(luy_ke)
    for _ in range(so_ky_toi_da):
        if dang_luy_ke >= nguyen_gia:
            break
        muc = trich_mot_ky(
            co_so_trich=co_so_trich,
            so_thang_con=so_thang_con,
            moc_tu_ngay=moc_tu_ngay,
            nguyen_gia=nguyen_gia,
            luy_ke=dang_luy_ke,
            nam=nam,
            thang=thang,
        )
        if muc > 0:
            dang_luy_ke += muc
            ra.append(DongDuKien(nam, thang, muc, dang_luy_ke, int(nguyen_gia) - dang_luy_ke))
        nam, thang = _sang_thang(nam, thang)
    return ra
