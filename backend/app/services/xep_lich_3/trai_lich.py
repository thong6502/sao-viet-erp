"""Xếp lịch 3 — trải thời lượng các bước lên giờ làm việc. HÀM THUẦN, không DB, không ORM.

Tách khỏi `service.py` có chủ đích: đây là phép tính DUY NHẤT mà cả bốn chỗ tiêu thụ lịch đều đi
qua (giữ chỗ vật tư · kế hoạch NVL · bàn tổ · máy đang chạy), nên nó phải kiểm được bằng số mà
không cần dựng đơn → lệnh → routing.

Dùng khung THEO CA (`LichXuong` với `lien_tuc=False`) — khác module 2 vốn cho máy chạy trọn ngày.
Đây chính là chỗ "cộng thêm thời gian nghỉ giữa ca và ngoài ca" mà mục tiêu module đòi: thanh trên
bàn Gantt dài bằng thời gian LỊCH, còn tổng các đoạn bên trong mới là giờ máy chạy thật.

Mốc vào/ra là WALL-CLOCK naive (giờ nhà máy); bên trong `LichXuong` tính tz-aware, nên vào phải
`_aware`, ra phải `_naive`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ..xep_lich_service import _aware, _cong_gio_lam, _naive, _vao_gio_lam


@dataclass(frozen=True)
class BuocVao:
    """Một bước routing đã quy về SỐ — service lo dịch từ `LsxCongDoan` sang đây."""

    lsx_cong_doan_id: int
    thu_tu: int
    chay_phut: float
    # Bước thuê ngoài: số NGÀY LỊCH chiếm chỗ. `None` = chưa khai đủ để biết (vẫn không chặn).
    thue_ngoai_ngay: int | None = None
    la_thue_ngoai: bool = False


@dataclass(frozen=True)
class DoanChay:
    """Một đoạn máy CHẠY liền mạch trong ca — lớp đậm của thanh hai lớp trên Gantt."""

    tu: datetime
    den: datetime
    buoc_index: int


@dataclass(frozen=True)
class MocBuoc:
    lsx_cong_doan_id: int
    thu_tu: int
    bat_dau: datetime
    ket_thuc: datetime
    chay_phut: float


@dataclass(frozen=True)
class KetQuaTrai:
    bat_dau: datetime
    ket_thuc: datetime
    da_doi: bool
    chay_phut: float
    doan: list[DoanChay] = field(default_factory=list)
    buoc: list[MocBuoc] = field(default_factory=list)
    ghi_chu: list[str] = field(default_factory=list)


def trai_lich(moc: datetime, buoc: list[BuocVao], lich) -> KetQuaTrai:
    """Trải `buoc` (sắp theo `thu_tu`) từ `moc`; trả mốc lệnh + mốc từng bước + các đoạn chạy.

    Chuỗi bám `thu_tu`, KHÔNG bám `phu_thuoc` và cũng không bám thứ tự người gọi truyền vào.

    Mốc rơi vào nghỉ giữa ca / ngoài ca / ngày nghỉ thì TRƯỢT tới đầu khoảng chạy được gần nhất và
    bật `da_doi` — đây là làm tròn cho phép cộng có nghĩa, KHÔNG phải cửa chặn: module này không
    chặn gì hết, chỉ báo cho người biết mốc đã dời đi đâu.
    """
    dau = _vao_gio_lam(_aware(moc), lich)
    da_doi = _naive(dau) != moc
    con: datetime = dau
    doan: list[DoanChay] = []
    moc_buoc: list[MocBuoc] = []
    ghi_chu: list[str] = []
    tong_chay = 0.0

    for i, b in enumerate(sorted(buoc, key=lambda x: (x.thu_tu, x.lsx_cong_doan_id))):
        b_dau = con
        if b.la_thue_ngoai:
            if b.thue_ngoai_ngay is None:
                ghi_chu.append(
                    "Bước gia công ngoài chưa khai ngày gửi/nhận — lệnh có thể kết thúc muộn hơn."
                )
            else:
                # NGÀY LỊCH: nhà cung cấp chạy theo lịch của họ, không theo ca của xưởng mình.
                con = con + timedelta(days=b.thue_ngoai_ngay)
        elif b.chay_phut > 0:
            doan.extend(_cat_doan(b_dau, b.chay_phut, i, lich))
            con = _cong_gio_lam(con, b.chay_phut, lich)
            tong_chay += b.chay_phut
        moc_buoc.append(MocBuoc(
            lsx_cong_doan_id=b.lsx_cong_doan_id, thu_tu=b.thu_tu,
            bat_dau=_naive(b_dau), ket_thuc=_naive(con), chay_phut=b.chay_phut,
        ))

    return KetQuaTrai(
        bat_dau=_naive(dau), ket_thuc=_naive(con), da_doi=da_doi,
        chay_phut=tong_chay, doan=doan, buoc=moc_buoc, ghi_chu=ghi_chu,
    )


def _cat_doan(tu: datetime, chay_phut: float, buoc_index: int, lich) -> list[DoanChay]:
    """Cắt `chay_phut` từ `tu` thành các đoạn CHẠY LIỀN MẠCH, bỏ nghỉ giữa ca / ngoài ca / ngày nghỉ.

    Đi theo chính các khoảng làm-việc mà `lich.next_interval` cấp — cùng nguồn `_cong_gio_lam` đi,
    nên đoạn cuối không bao giờ lệch mốc kết thúc của bước. Tổng các đoạn LUÔN bằng `chay_phut`.
    `next_interval` tự chặn vòng bằng `_MAX_NGAY`, không có đường lặp vô hạn.
    """
    ra: list[DoanChay] = []
    con = float(chay_phut)
    cur = tu
    for _ in range(5000):
        if con <= 1e-9:
            break
        iv = lich.next_interval(cur)
        if iv is None:          # hết khung trong tầm `_MAX_NGAY` — trả những gì đã cắt được
            break
        seg_start, seg_end = iv
        if cur < seg_start:
            cur = seg_start
        an = min((seg_end - cur).total_seconds() / 60.0, con)
        if an <= 0:             # con trỏ đúng mép phải khoảng: nhảy sang khoảng kế
            cur = seg_end
            continue
        ra.append(DoanChay(
            tu=_naive(cur), den=_naive(cur + timedelta(minutes=an)), buoc_index=buoc_index,
        ))
        con -= an
        cur = cur + timedelta(minutes=an)
    return ra
