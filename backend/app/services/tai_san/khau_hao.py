"""Engine khấu hao / phân bổ — HÀM THUẦN, không chạm DB.

Đầu vào là DANH SÁCH MỐC cơ sở (`Moc`) của một tài sản, xếp theo ngày. Mỗi mốc nói: từ ngày này
số tiền còn phải trích là bao nhiêu, chia cho mấy tháng, nguyên giá lúc đó, và lũy kế ngay trước
mốc (sau điều chỉnh nếu có). Ghi tăng / nạp đầu kỳ tạo mốc đầu; nâng cấp và CCDC giảm một phần lô
tạo mốc MỚI — mốc cũ vẫn giữ, nên tháng trước mốc mới tính theo cơ sở cũ. (Trước 08/09/2026 bộ ba
bị ghi đè tại chỗ ⇒ tháng nâng cấp trích 0, tháng trước đó về 0 khi tính lại.)

KHÔNG còn kỳ chốt (chủ chốt 08/09/2026: "nó chỉ theo dõi khấu hao thôi"): hao mòn lũy kế tại một
tháng = cộng dồn lịch tới hết tháng đó. Cùng một sổ hỏi lúc nào cũng ra đúng một số.

Luật một tháng:  mức tròn tháng = co_so_trich // so_thang_con  (của mốc đang hiệu lực).
Prorate theo NGÀY chỉ ở tháng chứa `tu_ngay` của mốc (khi không rơi vào ngày 1) và tháng ghi
giảm. Luôn cap bởi `nguyen_gia − lũy kế` nên kỳ cuối tự trích nốt phần lẻ do làm tròn — không cần
luật riêng cho kỳ cuối. Làm tròn XUỐNG đồng ở từng kỳ (`//`), phần dư dồn hết vào kỳ cuối: cách
ngược lại (làm tròn đều rồi bù kỳ cuối bằng số ÂM) cho ra dòng "trích -37đ" trên bảng in.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Moc:
    """Một đoạn cơ sở trích, hiệu lực từ `tu_ngay` tới trước mốc kế tiếp."""

    tu_ngay: date
    nguyen_gia: int
    co_so_trich: int
    so_thang_con: int
    #: Lũy kế ngay TRƯỚC khi mốc bắt đầu (đã điều chỉnh, vd CCDC bỏ bớt cái thì rút theo tỷ lệ).
    luy_ke_dau: int = 0


@dataclass(frozen=True)
class DongThang:
    """Một dòng của lịch khấu hao: trích của tháng, lũy kế và còn lại SAU tháng đó."""

    nam: int
    thang: int
    muc_trich: int
    luy_ke: int
    con_lai: int


#: Tên cũ — bảng "dự kiến" và bảng thật nay là MỘT lịch, chỉ khác tháng đang đứng.
DongDuKien = DongThang


def _so_ngay(nam: int, thang: int) -> int:
    return calendar.monthrange(nam, thang)[1]


def _sang_thang(nam: int, thang: int) -> tuple[int, int]:
    return (nam + 1, 1) if thang == 12 else (nam, thang + 1)


def thang_truoc(nam: int, thang: int) -> tuple[int, int]:
    return (nam - 1, 12) if thang == 1 else (nam, thang - 1)


def muc_trich_thang(co_so_trich: int, so_thang_con: int) -> int:
    """Mức trích tròn một tháng, làm tròn XUỐNG đồng."""
    if so_thang_con <= 0:
        raise ValueError("so_thang_con phải > 0")
    return int(co_so_trich) // int(so_thang_con)


def _muc_ky(moc: Moc, luy_ke: int, nam: int, thang: int, ngay_giam: date | None) -> int:
    """Số tiền trích của ĐÚNG một tháng theo mốc `moc`. 0 nếu tháng nằm ngoài đời tài sản."""
    con_lai = int(moc.nguyen_gia) - int(luy_ke)
    if con_lai <= 0 or moc.so_thang_con <= 0:
        return 0

    ngay_trong_thang = _so_ngay(nam, thang)
    dau_ky = date(nam, thang, 1)
    cuoi_ky = date(nam, thang, ngay_trong_thang)
    if moc.tu_ngay > cuoi_ky:
        return 0
    if ngay_giam is not None and ngay_giam < dau_ky:
        return 0

    tu = max(moc.tu_ngay, dau_ky)
    den = min(ngay_giam, cuoi_ky) if ngay_giam is not None else cuoi_ky
    if den < tu:
        return 0

    muc = muc_trich_thang(moc.co_so_trich, moc.so_thang_con)
    so_ngay_dung = (den - tu).days + 1
    if so_ngay_dung < ngay_trong_thang:
        muc = muc * so_ngay_dung // ngay_trong_thang
    return min(muc, con_lai)


def _sap(mocs) -> list[Moc]:
    return sorted(mocs, key=lambda m: (m.tu_ngay,))


def lich_khau_hao(
    mocs,
    *,
    ngay_giam: date | None = None,
    den: tuple[int, int] | None = None,
    so_ky_toi_da: int = 600,
) -> list[DongThang]:
    """Lịch trích từng tháng, từ tháng của mốc đầu tới khi hết giá trị (hoặc tới `den` = (năm,
    tháng) nếu cho). Tháng nào trích 0 thì không có dòng.

    Mốc hiệu lực của một tháng = mốc CUỐI có `tu_ngay` ≤ cuối tháng. Sang mốc mới thì lũy kế nhảy
    về `luy_ke_dau` của mốc đó (mốc nâng cấp mang đúng lũy kế đã trích, mốc giảm lô mang lũy kế đã
    rút bớt phần của mấy cái bỏ).

    `so_ky_toi_da` là chốt chặn vòng lặp: mức trích có thể bằng 0 (nguyên giá quá nhỏ so với số
    tháng) và khi đó lũy kế không bao giờ đuổi kịp nguyên giá.
    """
    mocs = _sap(mocs)
    if not mocs:
        return []
    ra: list[DongThang] = []
    nam, thang = mocs[0].tu_ngay.year, mocs[0].tu_ngay.month
    i_moc = -1
    luy_ke = int(mocs[0].luy_ke_dau)
    for _ in range(so_ky_toi_da):
        if den is not None and (nam, thang) > tuple(den):
            break
        if ngay_giam is not None and ngay_giam < date(nam, thang, 1):
            break
        cuoi_ky = date(nam, thang, _so_ngay(nam, thang))
        j = i_moc
        while j + 1 < len(mocs) and mocs[j + 1].tu_ngay <= cuoi_ky:
            j += 1
        if j != i_moc:
            i_moc = j
            luy_ke = int(mocs[j].luy_ke_dau)
        moc = mocs[i_moc]
        muc = _muc_ky(moc, luy_ke, nam, thang, ngay_giam)
        if muc > 0:
            luy_ke += muc
            ra.append(DongThang(nam, thang, muc, luy_ke, int(moc.nguyen_gia) - luy_ke))
        if luy_ke >= int(moc.nguyen_gia) and i_moc == len(mocs) - 1:
            break
        nam, thang = _sang_thang(nam, thang)
    return ra


def luy_ke_den(mocs, nam: int, thang: int, *, ngay_giam: date | None = None) -> int:
    """Hao mòn lũy kế tính đến HẾT tháng (năm, tháng)."""
    mocs = _sap(mocs)
    if not mocs:
        return 0
    cuoi_ky = date(nam, thang, _so_ngay(nam, thang))
    hieu_luc = [m for m in mocs if m.tu_ngay <= cuoi_ky]
    if not hieu_luc:
        return int(mocs[0].luy_ke_dau)          # chưa tới mốc đầu
    moc = hieu_luc[-1]
    lich = lich_khau_hao(mocs, ngay_giam=ngay_giam, den=(nam, thang))
    trong_moc = [d for d in lich if (d.nam, d.thang) >= (moc.tu_ngay.year, moc.tu_ngay.month)]
    return int(trong_moc[-1].luy_ke) if trong_moc else int(moc.luy_ke_dau)


def muc_thang(
    mocs, nam: int, thang: int, *, ngay_giam: date | None = None
) -> tuple[int, int]:
    """(số trích của tháng, lũy kế SAU tháng đó)."""
    for d in lich_khau_hao(mocs, ngay_giam=ngay_giam, den=(nam, thang)):
        if (d.nam, d.thang) == (nam, thang):
            return d.muc_trich, d.luy_ke
    return 0, luy_ke_den(mocs, nam, thang, ngay_giam=ngay_giam)


# --- Tiện ích cho tài sản chỉ có MỘT mốc (giữ chữ ký cũ cho test/đọc code) ------------------


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
    """Số tiền trích của ĐÚNG một kỳ (nam, thang) với một mốc duy nhất. 0 nếu ngoài đời tài sản."""
    moc = Moc(tu_ngay=moc_tu_ngay, nguyen_gia=int(nguyen_gia), co_so_trich=int(co_so_trich),
              so_thang_con=int(so_thang_con), luy_ke_dau=int(luy_ke))
    return _muc_ky(moc, int(luy_ke), nam, thang, ngay_giam)


def lich_du_kien(
    *,
    co_so_trich: int,
    so_thang_con: int,
    moc_tu_ngay: date,
    nguyen_gia: int,
    luy_ke: int,
    so_ky_toi_da: int = 400,
) -> list[DongThang]:
    """Lịch khấu hao của một mốc duy nhất từ mốc tới khi hết giá trị."""
    moc = Moc(tu_ngay=moc_tu_ngay, nguyen_gia=int(nguyen_gia), co_so_trich=int(co_so_trich),
              so_thang_con=int(so_thang_con), luy_ke_dau=int(luy_ke))
    return lich_khau_hao([moc], so_ky_toi_da=so_ky_toi_da)
