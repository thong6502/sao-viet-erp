"""Xếp lịch — trải thời lượng các bước lên giờ làm việc. HÀM THUẦN, không DB, không ORM.

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
from datetime import date, datetime, time, timedelta

from ..xep_lich_service import (
    GIO_BAT_DAU,
    PHUT_LAM_NGAY,
    _aware,
    _cong_gio_lam,
    _naive,
    _vao_gio_lam,
)


@dataclass(frozen=True)
class BuocVao:
    """Một bước routing đã quy về SỐ — service lo dịch từ `LsxCongDoan` sang đây."""

    lsx_cong_doan_id: int
    thu_tu: int
    chay_phut: float
    # Bước thuê ngoài: số NGÀY LỊCH chiếm chỗ. `None` = chưa khai đủ để biết (vẫn không chặn).
    thue_ngoai_ngay: int | None = None
    la_thue_ngoai: bool = False
    # Vì sao bước này KHÔNG tính được giờ (chưa gán máy · chưa quy đổi được đơn vị…). Có câu này
    # mà `chay_phut == 0` nghĩa là ngày kết thúc đang bị TÍNH THIẾU — thanh phải nói ra.
    canh_bao: str | None = None


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
    # Quãng `bat_dau → ket_thuc` của bước này là NGÀY LỊCH nhà cung cấp giữ, không phải giờ nghỉ.
    la_thue_ngoai: bool = False


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
        elif b.canh_bao:
            # Bước chiếm 0 phút vì THIẾU DỮ KIỆN, không vì nó nhanh: lệnh sẽ xong muộn hơn ngày
            # màn đang bày. Trước 10/09/2026 chỗ này im lặng — bước Dán chưa gán máy lọt qua
            # không một dòng nào, lịch nhảy thẳng từ Bế sang Đóng gói.
            cau = f"Bước {b.thu_tu} chưa tính được giờ nên lệnh có thể xong muộn hơn. {b.canh_bao}"
            if cau not in ghi_chu:
                ghi_chu.append(cau)
        moc_buoc.append(MocBuoc(
            lsx_cong_doan_id=b.lsx_cong_doan_id, thu_tu=b.thu_tu,
            bat_dau=_naive(b_dau), ket_thuc=_naive(con), chay_phut=b.chay_phut,
            la_thue_ngoai=b.la_thue_ngoai,
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


def _hhmm(phut: int, la_mep_phai: bool = False) -> str:
    """Phút trong ngày → "HH:MM". Mép PHẢI đúng nửa đêm ghi "24:00": "06:00–00:00" đọc như ca rỗng."""
    p = int(phut) % 1440
    if la_mep_phai and p == 0 and int(phut) > 0:
        return "24:00"
    return f"{p // 60:02d}:{p % 60:02d}"


def mo_ta_ca(ca_rows) -> list[dict]:
    """Tập ca xưởng → `[{ten, tu, den, nghi_tu, nghi_den}]` cho dòng "Ca 1 06:00–15:00 (nghỉ 12:00–13:00)".

    Khung gộp "06:00–24:00" giấu mất bữa nghỉ nào thuộc ca nào, người đọc phải mở màn Khai ca ra đối
    chiếu. Nghỉ ở đây là số KHAI của ca; khi ca gối nhau thì nghỉ HIỆU LỰC có thể hẹp hơn
    (`doan_nghi_trong_ngay`) — con số đó nằm ở dòng "Nghỉ giữa ca", không phải ở đây.
    """
    ra: list[dict] = []
    for c in ca_rows:
        s, e = int(c.start_minute), int(c.end_minute)
        qua_dem = bool(getattr(c, "is_overnight", False)) or e <= s
        nb, nk = getattr(c, "break_start_minute", None), getattr(c, "break_end_minute", None)
        co_nghi = nb is not None and nk is not None and int(nb) != int(nk)
        ra.append({
            "ten": c.name,
            "tu": _hhmm(s),
            "den": _hhmm(e + (1440 if qua_dem else 0), la_mep_phai=True),
            "nghi_tu": _hhmm(int(nb)) if co_nghi else None,
            "nghi_den": (_hhmm(int(nk) + (1440 if int(nk) <= int(nb) else 0), la_mep_phai=True)
                         if co_nghi else None),
        })
    return ra


def _giao(a: datetime, b: datetime, khoang: list[tuple[datetime, datetime]]):
    """Tách `[a, b)` thành (các mảnh NẰM TRONG `khoang`, các mảnh NẰM NGOÀI). `khoang` đã sort, rời nhau."""
    trong: list[tuple[datetime, datetime]] = []
    ngoai: list[tuple[datetime, datetime]] = []
    cur = a
    for s, e in khoang:
        if e <= cur or s >= b:
            continue
        if s > cur:
            ngoai.append((cur, s))
        trong.append((max(s, cur), min(e, b)))
        cur = min(e, b)
        if cur >= b:
            break
    if cur < b:
        ngoai.append((cur, b))
    return trong, ngoai


def _phut(a: datetime, b: datetime) -> float:
    return (b - a).total_seconds() / 60.0


def _gom_khung(manh: list[tuple[datetime, datetime]]) -> list[dict]:
    """Nối mảnh liền nhau (ngoài ca vắt qua nửa đêm) rồi gom theo khung giờ `HH:MM–HH:MM` + đếm số lần."""
    noi: list[list[datetime]] = []
    for s, e in sorted(manh):
        if noi and s <= noi[-1][1]:
            noi[-1][1] = max(noi[-1][1], e)
        else:
            noi.append([s, e])
    gom: dict[tuple[str, str], dict] = {}
    for s, e in noi:
        k = (_hhmm(s.hour * 60 + s.minute),
             _hhmm(e.hour * 60 + e.minute + (1440 if e.date() > s.date() and e.time() == time() else 0),
                   la_mep_phai=True))
        g = gom.setdefault(k, {"tu": k[0], "den": k[1], "so_lan": 0, "phut": 0.0})
        g["so_lan"] += 1
        g["phut"] += _phut(s, e)
    for g in gom.values():
        g["phut"] = round(g["phut"], 2)
    return sorted(gom.values(), key=lambda g: g["tu"])     # theo giờ trong ngày: 12:00 trước 18:00


def phan_tach_nghi(kq: KetQuaTrai, lich) -> dict:
    """Tách phần KHÔNG CHẠY của thanh (`ket_thuc - bat_dau - chay_phut`) ra từng loại, kèm giờ cụ thể.

    Con số gộp "nghỉ" không trả lời được câu người điều độ hỏi tiếp: nghỉ giữa ca bao lâu, từ mấy
    giờ; ngày nghỉ là những ngày nào. Bốn loại, cộng lại ĐÚNG bằng con số gộp:

      · gia công ngoài — quãng ngày lịch của bước thuê ngoài (không phải nghỉ, nhưng cũng không chạy)
      · ngày nghỉ      — phần rơi vào ngày `is_working_day = False`, theo ngày lịch
      · nghỉ giữa ca   — phần nằm TRONG khung ca (chưa khoét bữa nghỉ) của ngày làm việc
      · ngoài ca       — phần còn lại của ngày làm việc (tối/đêm ngoài giờ ca)

    Khoảng hở = `[bat_dau, ket_thuc]` trừ hợp các đoạn chạy; tổng các đoạn luôn bằng `chay_phut`
    (`_cat_doan`), nên tổng bốn loại khớp `nghi_ngoai_ca_phut` của `_so_lich`. Hàm thuần: chỉ đọc
    `lich.cal.is_working_day` (đã cache theo năm) và khung ca — không thêm truy vấn nào.
    """
    ho: list[tuple[datetime, datetime]] = []
    cur = kq.bat_dau
    for d in sorted(kq.doan, key=lambda x: x.tu):
        if d.tu > cur:
            ho.append((cur, d.tu))
        cur = max(cur, d.den)
    if kq.ket_thuc > cur:
        ho.append((cur, kq.ket_thuc))

    thue = sorted((b.bat_dau, b.ket_thuc) for b in kq.buoc
                  if b.la_thue_ngoai and b.ket_thuc > b.bat_dau)
    gia_cong = 0.0
    giua_ca: list[tuple[datetime, datetime]] = []
    ngoai_ca: list[tuple[datetime, datetime]] = []
    ngay_nghi: dict[date, float] = {}
    for a, b in ho:
        trong_thue, con_lai = _giao(a, b, thue)
        gia_cong += sum(_phut(s, e) for s, e in trong_thue)
        for x, y in con_lai:
            ngay = x.date()
            while True:
                dau = datetime(ngay.year, ngay.month, ngay.day)
                s, e = max(x, dau), min(y, dau + timedelta(days=1))
                if s >= y:
                    break
                if s < e:
                    if not lich.cal.is_working_day(ngay):
                        ngay_nghi[ngay] = ngay_nghi.get(ngay, 0.0) + _phut(s, e)
                    else:
                        khung = [(_naive(p), _naive(q)) for p, q in lich._khung_ngay_tho(ngay)]
                        trong, ngoai = _giao(s, e, khung)
                        giua_ca += trong
                        ngoai_ca += ngoai
                ngay = ngay + timedelta(days=1)

    cas = sorted((s, e + 1440 if qua_dem else e) for s, e, qua_dem in lich.cas) or [
        (GIO_BAT_DAU * 60, GIO_BAT_DAU * 60 + PHUT_LAM_NGAY)
    ]
    ca_gop: list[list[int]] = []
    for s, e in cas:
        if ca_gop and s <= ca_gop[-1][1]:
            ca_gop[-1][1] = max(ca_gop[-1][1], e)
        else:
            ca_gop.append([s, e])
    return {
        "ca_san_xuat": [{"tu": _hhmm(s), "den": _hhmm(e, la_mep_phai=True)} for s, e in ca_gop],
        "nghi_giua_ca_phut": round(sum(_phut(s, e) for s, e in giua_ca), 2),
        "nghi_giua_ca": _gom_khung(giua_ca),
        "ngoai_ca_phut": round(sum(_phut(s, e) for s, e in ngoai_ca), 2),
        "ngoai_ca": _gom_khung(ngoai_ca),
        "ngay_nghi_phut": round(sum(ngay_nghi.values()), 2),
        "ngay_nghi": [{"ngay": d, "phut": round(p, 2)} for d, p in sorted(ngay_nghi.items())],
        "gia_cong_ngoai_phut": round(gia_cong, 2),
    }
