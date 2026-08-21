"""Tự xếp lịch CẢ MỘT lệnh/bài — chạy đúng bộ luật `constraint` mà con người đang bấm tay.

Vì sao viết ở đây chứ không nhét vào `service`: tự-xếp là một VÒNG LẶP QUYẾT ĐỊNH (chọn máy → chọn
khe → đo hậu quả → sang bước sau), khác hẳn các hàm còn lại vốn chỉ tính-một-dòng. Tách ra để đọc
được thuật toán như đọc một trang giấy.

Ba điều làm nên "thông minh" ở đây (chứ không phải nhét bừa vào khe trống đầu tiên):

1. **Chuỗi, không phải rời rạc.** Bước sau đợi bước trước XONG (`tien_nhiem_finish`), và mỗi lần đặt
   xong là ghi ngay vào phiên ⇒ bước kế tiếp NHÌN THẤY máy vừa bị chiếm. Xếp một lệnh 6 bước ra một
   dây liền mạch, không phải 6 quyết định mù nhau.
2. **Chọn máy bằng ĐIỂM, không đua "xong sớm nhất".** Đích của xưởng là KỊP HẠN chứ không phải sớm
   nhất — xong trước hạn 3 ngày hay 5 ngày là như nhau, mà đua sớm thì máy khoẻ luôn bị bài đầu
   tiên vơ mất. Nay mọi máy KỊP HẠN được chấm bằng `diem_may` trên ba trục (đệm tới hạn · nối
   việc cùng gom · san tải), chọn máy điểm cao nhất; chỉ khi KHÔNG máy nào kịp mới quay về đua giờ
   xong. Xem `diem_may` để biết vì sao chỉ ba trục đó — và vì sao khổ máy CỐ Ý không được chấm.
3. **Nhìn hạn trước khi chốt.** Xếp xong cả chuỗi mà trễ hạn SX thì chạy LƯỢT HAI ở chế độ "nhanh
   nhất tuyệt đối" (dung sai = 0, bỏ hết tiêu chí êm ái). Lượt nào xong sớm hơn thì giữ lượt đó.

Thời lượng dùng để đặt lịch luôn là mức TRUNG BÌNH (`chiem_may_phut`); min/max đi kèm chỉ để màn
Gantt vẽ "râu" cho biết bước này co giãn tới đâu — KHÔNG dùng để đặt giờ (§3.3).

KHÔNG tự phán máy hợp khổ/màu/định lượng (spec §6) — vẫn là "máy đề xuất, người quyết". Mọi khe đặt
ra đều đã qua `_van_de_dat_lich`, nên không bao giờ ghi được một cách đặt mà bấm tay sẽ bị chặn.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from ...models.bai_ghep_cong_doan import BaiGhepCongDoan
from ...models.lsx import LB_THUE_NGOAI, LB_TO
from ...models.xep_lich import NGUON_LSX, TT_DA_XEP
from ..lsx_service import thoi_luong_buoc
from ..xep_lich_service import _aware, _naive
from . import chan_doan as CD
from . import constraint as C
from . import diem_may as DM
from . import routing as R

# Trần ngày dò tới khi tìm khe cho một bước (kể từ sàn thời gian của bước đó).
CHAN_NGAY_MAC_DINH = 60
# Trần mốc ứng viên xét cho MỘT bước — chặn vòng chấm thoái hoá khi lịch quá dày.
TRAN_UNG_VIEN = 400



# ============================ THỜI LƯỢNG THEO TỪNG MÁY ============================
def _buoc_goc(service, dong):
    """Bước routing gốc của dòng (`LsxCongDoan` / `BaiGhepCongDoan`) — nguồn tốc độ & sản lượng."""
    if dong.nguon == NGUON_LSX:
        return service.core._lcd(dong.lsx_cong_doan_id)
    if dong.bai_ghep_cong_doan_id:
        return service.db.get(BaiGhepCongDoan, dong.bai_ghep_cong_doan_id)
    return None


def _thoi_luong_tren_may(service, dong, may) -> dict | None:
    """Ba mức thời lượng của bước NẾU chạy trên `may` — tốc độ/chuẩn bị là thuộc tính của MÁY nên
    cùng một bước trên hai máy ra hai con số. Tính không ra ⇒ None (không hứa giờ xong nào); vì sao
    không ra thì hỏi `_thieu_gi_tren_may`."""
    lcd = _buoc_goc(service, dong)
    if lcd is None:
        return None
    d = thoi_luong_buoc(lcd, may, service.core._sl_tinh(lcd, may))
    # CỬA TẦNG 0 (21/08/2026) — chỉ nhận máy engine THẬT SỰ tính được giờ chạy trên nó.
    # Bệnh cũ: chỗ này chỉ loại khi `chiem <= 0`, mà máy chưa khai tốc độ vẫn ra `chiem > 0` nhờ
    # phần chuẩn bị + phát sinh cộng vào (`chay = 0`). Hậu quả nhìn thấy trên màn: bước "Ghi kẽm
    # CTP" được gợi ý ba máy in offset, cả ba đều "45 phút" — đúng bằng `phat_sinh_phut` của bước,
    # nghĩa là chúng đứng đầu bảng CHÍNH VÌ không chạy được việc. `phuong_phap` là chữ ký của
    # engine (`may` · `to` · `chua_quy_doi` · `thieu_nang_suat`); khác `may` là con số kia không
    # phải giờ chạy của máy này, không được phép đem đi hứa giờ xong.
    if (d.get("dien_giai") or {}).get("phuong_phap") != "may":
        return None
    chiem = int(round(d.get("chiem_may_phut") or 0))
    if chiem <= 0:
        return None
    return {
        "chiem_may_phut": chiem,
        "chiem_may_phut_min": int(round(d.get("chiem_may_phut_min") or chiem)),
        "chiem_may_phut_max": int(round(d.get("chiem_may_phut_max") or chiem)),
    }


def _thieu_gi_tren_may(service, dong, may) -> str:
    """Vì sao MÁY NÀY chưa nhận được bước — hỏi lại engine với đúng máy đó rồi để `chan_doan` gọi tên.

    Trước đây sổ ghi một câu ngoặc-đơn hai-khả-năng ("chưa khai tốc độ (hoặc đơn vị chưa quy đổi
    được)"), người đọc vẫn phải tự đoán thiếu cái nào. Chỉ chạy cho máy BỊ LOẠI nên không tốn gì
    trên đường thường.
    """
    shadow = service._shadow(dong, {"may_id": may.id})
    ma = (service._thoi_luong_v2(shadow) or {}).get("canh_bao")
    return CD.chi_tiet(service, shadow, ma)[0] if ma else "chưa tính được thời lượng chạy."


# ============================ SÀN THỜI GIAN + MỐC ỨNG VIÊN ============================
def san_va_cho(service, dong, shadow) -> tuple[datetime, list[str]]:
    """(sớm nhất bước này được phép bắt đầu, tên các tiền nhiệm còn phải ƯỚC vì chưa xếp).

    `max(sàn cơ bản · giờ xong của MỌI tiền nhiệm)`. Cả hai vế nằm ở `routing` nên tự-xếp, gợi ý máy
    và gợi ý khe dùng chung MỘT sàn — lỗi cũ là mỗi nhánh tự lấy một sàn rồi nói ba giờ khác nhau.

    Trả kèm danh sách `cho` để nơi gọi gắn cảnh báo "giờ này mới là ƯỚC" (`_kem_cho`): sàn có thể
    được đẩy xuống bởi một bước chưa ai xếp, và người xếp phải biết điều đó.
    """
    ca = service.ctx.ca_windows()
    som = R.san_co_ban(service, dong, ca)
    finishes, cho = R.tien_nhiem_finish(service, shadow, ca)
    for f in finishes:
        if f is not None and (som is None or f > som):
            som = f
    return som, cho


def _moc_ung_vien(service, dong, shadow, *, san: datetime, chan_ngay: int,
                  ca: list[tuple[int, int, bool]]) -> list[datetime]:
    """Mốc bắt đầu ứng viên ≥ `san`, tăng dần, đã khử trùng.

    Một khe chỉ "mở ra" tại bốn loại thời điểm: chính cái sàn · đầu mỗi ca từng ngày · ngay sau một
    việc/vùng-khoá vừa nhả máy · lúc tổ vừa rảnh bớt người. Rà đúng bấy nhiêu mốc là đủ phủ — giữa
    hai mốc thì tình trạng máy không đổi, dời thêm một phút chẳng mở thêm chỗ nào.
    """
    tran = san + timedelta(days=max(1, int(chan_ngay)))
    moc: set[datetime] = {san}
    ngay = san.date()
    het = tran.date()
    while ngay <= het:
        base = datetime.combine(ngay, time.min, tzinfo=timezone.utc)
        for bat_dau, _, _ in ca:
            moc.add(base + timedelta(minutes=int(bat_dau)))
        ngay = ngay + timedelta(days=1)
    if shadow.may_id:
        for _, f in service.ctx.khoang_may_da_xep(shadow.may_id, dong.id):
            if f is not None:
                moc.add(_aware(f))
        for _, f in service.ctx.khoang_chan_may(shadow.may_id):
            if f is not None:
                moc.add(_aware(f))
    if shadow.department_id:
        for _, f, _n in service.ctx.placements_to(shadow.department_id, dong.id):
            if f is not None:
                moc.add(_aware(f))
    trong = sorted(m for m in moc if san <= m <= tran)
    return trong[:TRAN_UNG_VIEN]


def _khe_dau_tien(service, dong, shadow, *, chiem: int, chiem_max: int, san: datetime,
                  chan_ngay: int, ca) -> tuple[datetime | None, list[dict], str | None]:
    """Khe SỚM NHẤT không vướng luật CHẶN ĐẶT LỊCH, kèm các cảnh báo còn lại của khe đó.

    Chạy liên tục nên khe bắt đầu sớm nhất cũng là khe kết thúc sớm nhất — duyệt mốc tăng dần rồi
    nhận cái đầu tiên sạch là tối ưu, không cần quét hết.

    Không tìm ra khe nào thì trả kèm MỘT MỆNH ĐỀ vì-sao dựng từ SỔ ĐẾM luật đã chặn trên TOÀN BỘ
    mốc đã dò (`chan_doan.vi_sao_khong_co_khe`) — kể luật ở mốc đầu tiên là kể nhầm, vì mốc đầu hay
    vướng thứ vặt trong khi thứ bịt cả cửa sổ mới là cái người ta cần gỡ.
    """
    dem: dict[str, int] = {}
    mo_ta: dict[str, str] = {}
    so_moc = 0
    for start in _moc_ung_vien(service, dong, shadow, san=san, chan_ngay=chan_ngay, ca=ca):
        so_moc += 1
        finish = C.finish_lien_tuc(start, chiem)
        vd = service._van_de_dat_lich(
            shadow, start=start, finish=finish,
            finish_max=C.finish_lien_tuc(start, chiem_max),
            may_id=shadow.may_id, department_id=shadow.department_id,
            canh_bao=None, exclude_id=dong.id,
        )
        chan = [i for i in vd if i["muc"] == C.MUC_CHAN_DAT_LICH]
        if chan:
            for i in chan:
                ma = i.get("ma") or "khac"
                dem[ma] = dem.get(ma, 0) + 1
                mo_ta.setdefault(ma, i.get("mo_ta") or ma)
            continue
        return start, [i for i in vd if i["muc"] == C.MUC_CANH_BAO], None
    return None, [], CD.vi_sao_khong_co_khe(dem, mo_ta, so_moc=so_moc, chan_ngay=chan_ngay)


# ============================ CHỌN MÁY ============================
def ung_vien_may(service, dong, *, san: datetime, chan_ngay: int, ca,
                 ket: list[str] | None = None) -> list[dict]:
    """Mọi máy làm được bước này, kèm khe sớm nhất + giờ xong + hai tiêu chí phá hoà.

    `ket` (tuỳ chọn) là sổ ghi vì sao từng máy bị loại — chỉ nơi cần báo thất bại mới truyền vào."""
    # Vòng chấm này THUẦN ĐỌC mà lặp rất dày: mỗi máy × mỗi mốc ứng viên đều hỏi lại đúng bấy nhiêu
    # câu (ca xưởng · vùng khoá máy · việc đã xếp · quân số tổ · tiền nhiệm · hai hạn). Đóng băng ctx
    # trong đúng MỘT lượt chấm ⇒ mỗi câu chỉ chạm DB một lần, kết quả không đổi một ly.
    # CỐ Ý không bọc ở ngoài `tu_xep`: sau mỗi bước vừa ghi, máy đã bị chiếm thêm — ảnh chụp cũ sẽ
    # nói dối và bước sau sẽ đè lên bước trước.
    with service.ctx.dong_bang():
        return _ung_vien_may(service, dong, san=san, chan_ngay=chan_ngay, ca=ca, ket=ket)


def _ung_vien_may(service, dong, *, san: datetime, chan_ngay: int, ca,
                  ket: list[str] | None = None) -> list[dict]:
    core = service.core
    lsx = core.lsx_repo.get(dong.lsx_id) if dong.lsx_id else None
    gom = core._gom_key(lsx)
    ra: list[dict] = []
    for may in core._may_lam_duoc(dong):
        d = _thoi_luong_tren_may(service, dong, may)
        if d is None:
            if ket is not None:
                ket.append(f"{may.ten}: {_thieu_gi_tren_may(service, dong, may)}")
            continue
        shadow = service._shadow(dong, {"may_id": may.id})
        start, canh_bao, vi_sao = _khe_dau_tien(
            service, dong, shadow, chiem=d["chiem_may_phut"], chiem_max=d["chiem_may_phut_max"],
            san=san, chan_ngay=chan_ngay, ca=ca,
        )
        if start is None:
            if ket is not None:
                ket.append(f"{may.ten}: {vi_sao or 'không còn khe trống'}.")
            continue
        finish = C.finish_lien_tuc(start, d["chiem_may_phut"])
        ra.append({
            "may_id": may.id,
            "may_ten": may.ten,
            "start": start,
            "finish": finish,
            "canh_bao": canh_bao,
            "cung_gom": core._lien_ke_cung_gom(may.id, start, gom, exclude_id=dong.id),
            # `co_gom` khác `cung_gom`: lệnh CHƯA đủ quy cách để dựng khoá gom thì trục "đổi bài rẻ"
            # KHÔNG ĐO ĐƯỢC — khác hẳn với đo được rồi thấy không nối được (`cung_gom = False`).
            "co_gom": gom is not None,
            "tai_ngay": service._tai_may_ngay(
                may.id, start, finish, service.ctx.khoang_may_da_xep(may.id, dong.id)),
            **d,
        })
    han_sx, han_giao = service.ctx.hai_han(dong)
    DM.cham_tat_ca(ra, han=han_sx or han_giao, ca=ca)
    return ra


def chon_may(ung_vien: list[dict], *, nhanh_nhat: bool) -> dict | None:
    """Chốt một máy trong danh sách ứng viên.

    `nhanh_nhat=True` ⇒ thuần giờ xong (lượt cứu hạn — lúc đó chỉ còn một câu hỏi: cứu được bao
    nhiêu). Ngược lại: **lọc lấy nhóm KỊP HẠN trước, rồi trong nhóm đó chọn ĐIỂM cao nhất**
    (`diem_may`), giờ xong chỉ còn là cái phá hoà.

    Lọc-rồi-chấm chứ không cộng-hết-vào-một-điểm là cố ý: trễ hạn không phải "kém đi vài điểm", nó
    là hỏng việc. Cho một máy trễ hạn cạnh tranh bằng điểm khổ + điểm gom thì sớm muộn nó sẽ thắng.

    Không máy nào kịp ⇒ rơi về đua giờ xong: đằng nào cũng trễ, trễ ít nhất vẫn hơn.
    """
    if not ung_vien:
        return None
    if nhanh_nhat:
        return min(ung_vien, key=lambda u: (u["finish"], u["chiem_may_phut"], u["may_id"]))
    kip = [u for u in ung_vien if not u["diem"]["tre_han"]]
    if not kip:
        return min(ung_vien, key=lambda u: (u["finish"], u["chiem_may_phut"], u["may_id"]))
    return sorted(kip, key=lambda u: (-u["diem"]["diem"], u["finish"], u["may_id"]))[0]


def ly_do_chon(chon: dict, ung_vien: list[dict], *, nhanh_nhat: bool) -> str:
    """Câu giải thích NGẮN vì sao máy này — để người xếp lịch soi lại được quyết định của máy.

    Đọc thẳng từ bảng điểm nên câu chữ và con số LUÔN khớp cách chọn: kể tối đa hai điểm mạnh, và
    nếu máy có một trục yếu thì nói LUÔN chỗ yếu đó. Giấu chỗ yếu là cách nhanh nhất để người xếp
    thôi tin cái gợi ý — họ nhìn ra ngay máy khổ lớn đang chạy tờ bé, mà máy thì im như không thấy.
    """
    if nhanh_nhat:
        return "Lượt cứu hạn: chọn máy cho giờ xong sớm nhất."
    if len(ung_vien) <= 1:
        return "Chỉ một máy làm được bước này."
    diem = chon.get("diem") or {}
    cau = " ".join(diem.get("manh") or []) or "Xong sớm nhất trong các máy làm được bước này."
    tru = diem.get("tru")
    return f"{cau} Đổi lại: {tru[:1].lower() + tru[1:]}" if tru else cau


# ============================ ĐẶT MỘT BƯỚC ============================
def _ap(dong, *, may_id, start, finish) -> None:
    """Ghi quyết định vào dòng — dùng ĐÚNG lối `luu` để bước sau nhìn thấy máy vừa bị chiếm
    (`da_xep_khac_tren_may` lọc `trang_thai == TT_DA_XEP`, autoflush lo phần còn lại)."""
    if may_id is not None:
        dong.may_id = may_id
    dong.start_at = start
    dong.finish_at = finish
    dong.trang_thai = TT_DA_XEP
    dong.blocked_reason = None


def _kem_cho(canh_bao: list[dict], cho: list[str]) -> list[dict]:
    """Bước đứng sau một tiền nhiệm CHƯA xếp thì giờ của nó mới là số ƯỚC — nói thẳng ra, đừng để
    người xếp nhìn thanh Gantt mà tưởng giờ đã chắc. Chỉ CẢNH BÁO: không chặn ai vì số máy tự đoán."""
    if not cho:
        return canh_bao
    return list(canh_bao) + [C.issue(
        "cho_tien_nhiem_chua_xep", C.MUC_CANH_BAO,
        f"Giờ này tính theo ƯỚC của {', '.join(cho)} — bước đó chưa được xếp.",
        nguon="tien_nhiem", goi_y="Xếp bước trước xong rồi soi lại giờ bước này.",
        doi_tuong=", ".join(cho))]


def _vi_sao_khong_may(ket: list[str], chan_ngay: int) -> str:
    """Không máy nào nhận được bước ⇒ đọc lại sổ loại máy. Có sổ thì kể tên (tối đa 3 máy), rỗng
    mới rơi về câu chung — vì rỗng nghĩa là danh mục không có máy nào làm được bước này."""
    if not ket:
        return ("Không máy nào trong danh mục làm được bước này — chưa khai công đoạn này cho máy "
                "nào ở Danh mục → Máy & thiết bị.")
    them = f" · và {len(ket) - 3} máy khác." if len(ket) > 3 else ""
    return f"Không máy nào xếp được trong {chan_ngay} ngày tới. " + " ".join(ket[:3]) + them


def _xep_theo_thoi_luong_san(service, dong, shadow, *, san, chan_ngay, ca, ly_do,
                             cho: list[str] | None = None) -> dict:
    """Nhánh dùng chung cho bước KHÔNG chọn máy (thuê ngoài · làm tay theo tổ): thời lượng đã cố
    định sẵn, chỉ còn việc tìm khe sớm nhất."""
    dur = service._thoi_luong_v2(shadow)
    chiem = int(dur.get("chiem_may_phut") or 0)
    if chiem <= 0 or dur.get("canh_bao"):
        ma = dur.get("canh_bao")
        return {"ok": False,
                "ly_do": (CD.chi_tiet(service, dong, ma)[0] if ma
                          else "Chưa tính được thời lượng bước này.")}
    chiem_max = int(dur.get("chiem_may_phut_max") or chiem)
    start, canh_bao, vi_sao = _khe_dau_tien(service, dong, shadow, chiem=chiem,
                                            chiem_max=chiem_max, san=san,
                                            chan_ngay=chan_ngay, ca=ca)
    if start is None:
        return {"ok": False,
                "ly_do": f"Không tìm được khe hợp lệ trong {chan_ngay} ngày tới"
                         + (f" — {vi_sao}." if vi_sao else ".")}
    finish = C.finish_lien_tuc(start, chiem)
    _ap(dong, may_id=None, start=start, finish=finish)
    return {"ok": True, "may_id": None, "may_ten": None, "start": start, "finish": finish,
            "chiem_may_phut": chiem,
            "chiem_may_phut_min": int(dur.get("chiem_may_phut_min") or chiem),
            "chiem_may_phut_max": chiem_max,
            "canh_bao": _kem_cho(canh_bao, cho or []), "so_may_xet": 0, "ly_do": ly_do}


def xep_mot_buoc(service, dong, *, chan_ngay: int, nhanh_nhat: bool) -> dict:
    """Xếp MỘT dòng. Trả `{ok, ...}`; `ok=False` kèm `ly_do` và KHÔNG ghi gì vào dòng."""
    ca = service.ctx.ca_windows()
    shadow0 = service._shadow(dong, {})
    san, cho = san_va_cho(service, dong, shadow0)
    loai = getattr(dong, "loai_buoc", None)

    if loai == LB_THUE_NGOAI:
        return _xep_theo_thoi_luong_san(
            service, dong, shadow0, san=san, chan_ngay=chan_ngay, ca=ca, cho=cho,
            ly_do="Bước gửi ngoài — xếp theo lead-time gửi → nhận, không chiếm máy.")
    if loai == LB_TO:
        return _xep_theo_thoi_luong_san(
            service, dong, shadow0, san=san, chan_ngay=chan_ngay, ca=ca, cho=cho,
            ly_do="Bước làm tay — xếp vào khe sớm nhất tổ còn đủ người.")

    ket: list[str] = []
    ung_vien = ung_vien_may(service, dong, san=san, chan_ngay=chan_ngay, ca=ca, ket=ket)
    if not ung_vien:
        return {"ok": False, "ly_do": _vi_sao_khong_may(ket, chan_ngay)}
    chon = chon_may(ung_vien, nhanh_nhat=nhanh_nhat)
    _ap(dong, may_id=chon["may_id"], start=chon["start"], finish=chon["finish"])
    return {"ok": True, "may_id": chon["may_id"], "may_ten": chon["may_ten"],
            "start": chon["start"], "finish": chon["finish"],
            "chiem_may_phut": chon["chiem_may_phut"],
            "chiem_may_phut_min": chon["chiem_may_phut_min"],
            "chiem_may_phut_max": chon["chiem_may_phut_max"],
            "canh_bao": _kem_cho(chon["canh_bao"], cho), "so_may_xet": len(ung_vien),
            "ly_do": ly_do_chon(chon, ung_vien, nhanh_nhat=nhanh_nhat)}


# ============================ XẾP CẢ CHUỖI ============================
def _khoi_phuc(rows, anh: dict[int, tuple]) -> None:
    """Trả các dòng về đúng trạng thái trước lượt thử (lượt 1 thua lượt 2 thì phải hoàn nguyên)."""
    for r in rows:
        may_id, dept_id, start, finish, tt, ly_do = anh[r.id]
        r.may_id, r.department_id = may_id, dept_id
        r.start_at, r.finish_at = start, finish
        r.trang_thai, r.blocked_reason = tt, ly_do


def _chup(rows) -> dict[int, tuple]:
    return {r.id: (r.may_id, r.department_id, r.start_at, r.finish_at,
                   r.trang_thai, r.blocked_reason) for r in rows}


def _mot_luot(service, rows, *, chan_ngay: int, nhanh_nhat: bool) -> dict:
    """Một lượt xếp toàn chuỗi theo thứ tự routing. Trả kết quả + giờ xong cuối chuỗi."""
    da_xep: list[dict] = []
    bo_qua: list[dict] = []
    for r in rows:
        kq = xep_mot_buoc(service, r, chan_ngay=chan_ngay, nhanh_nhat=nhanh_nhat)
        if kq.get("ok"):
            da_xep.append({"dong_id": r.id, "thu_tu": int(r.source_thu_tu or 0), **kq})
        else:
            bo_qua.append({"dong_id": r.id, "thu_tu": int(r.source_thu_tu or 0),
                           "ly_do": kq.get("ly_do") or "Không xếp được."})
        service.db.flush()          # bước sau phải NHÌN THẤY máy/tổ vừa bị chiếm
    fins = [k["finish"] for k in da_xep if k.get("finish") is not None]
    return {"da_xep": da_xep, "bo_qua": bo_qua, "finish_chuoi": max(fins) if fins else None}


def _diem_luot(kq: dict) -> tuple:
    """So hai lượt: xếp được NHIỀU bước hơn thắng, rồi mới tới xong sớm hơn."""
    fin = kq["finish_chuoi"]
    return (-len(kq["da_xep"]), fin or datetime.max.replace(tzinfo=timezone.utc))


def tu_xep(service, *, nguon: str, id: int, actor, ghi_de: bool = False,
           chan_ngay: int = CHAN_NGAY_MAC_DINH) -> dict:
    """Tự xếp toàn bộ bước CHƯA có giờ (hoặc TẤT CẢ nếu `ghi_de`) của một lệnh/bài.

    Dòng ĐÃ KHOÁ (`is_locked`) không bao giờ bị đụng — người ta khoá là có ý.

    Chạy lượt 1 ở chế độ êm (ưu tiên gom giảm công canh máy). Nếu chuỗi xong TRỄ hạn SX thì chạy
    tiếp lượt 2 "nhanh nhất tuyệt đối" rồi giữ lượt tốt hơn. Không trễ ⇒ khỏi lượt 2 (đỡ một vòng
    quét, và lượt êm vốn tốt hơn cho xưởng).
    """
    if nguon == NGUON_LSX:
        rows = service.repo.by_lsx(id)
        han_sx, han_giao = service.ctx.hai_han(_ns(lsx_id=id))
    else:
        rows = service.repo.by_bai_ghep(id)
        han_sx, han_giao = service.ctx.hai_han(_ns(bai_ghep_id=id))
    rows = sorted(rows, key=lambda r: (int(r.source_thu_tu or 0), r.id))
    lam = [r for r in rows if not r.is_locked and (ghi_de or r.start_at is None)]
    # Xếp theo ĐỒ THỊ phụ thuộc, không theo `thu_tu`: cạnh routing được phép ngược `thu_tu` (LSX
    # 26-0020 chạy B1→B6→B2→…), mà đặt bước sau trước bước trước thì sàn của nó thiếu mất tiền
    # nhiệm ⇒ chuỗi gãy. DAG trùng `thu_tu` (đại đa số lệnh) vẫn ra đúng thứ tự cũ.
    lam = R.thu_tu_xep(lam, R.canh_giua_dong(service.db, lam))
    lam_ids = {r.id for r in lam}
    giu = [r for r in rows if r.id not in lam_ids]

    if not lam:
        return _ket_qua(service, nguon, id, {"da_xep": [], "bo_qua": [], "finish_chuoi": None},
                        rows=rows, han_sx=han_sx, han_giao=han_giao, luot=0,
                        giu=len(giu),
                        tom_tat="Không có bước nào cần xếp — mọi bước đã có giờ hoặc đang khoá.")

    anh = _chup(lam)
    luot1 = _mot_luot(service, lam, chan_ngay=chan_ngay, nhanh_nhat=False)
    chon, so_luot = luot1, 1
    tre1 = _tre_ngay(luot1["finish_chuoi"], han_sx)
    if tre1 is not None and tre1 > 0:
        chup1 = _chup(lam)
        _khoi_phuc(lam, anh)
        service.db.flush()
        luot2 = _mot_luot(service, lam, chan_ngay=chan_ngay, nhanh_nhat=True)
        if _diem_luot(luot2) < _diem_luot(luot1):
            chon, so_luot = luot2, 2
        else:
            _khoi_phuc(lam, chup1)
            service.db.flush()

    service.audit.create(
        actor_user_id=getattr(actor, "id", None), action="xep_lich_2_tu_xep",
        target=f"{nguon}:{id}",
        detail=(f"Tự xếp lịch: {len(chon['da_xep'])} bước xếp được, {len(chon['bo_qua'])} bước "
                f"bỏ qua, {len(giu)} bước giữ nguyên (lượt {so_luot})."),
    )
    service.repo.commit()
    return _ket_qua(service, nguon, id, chon, rows=rows, han_sx=han_sx, han_giao=han_giao,
                    luot=so_luot, giu=len(giu))


def _ns(**kw):
    from types import SimpleNamespace
    kw.setdefault("lsx_id", None)
    kw.setdefault("bai_ghep_id", None)
    return SimpleNamespace(**kw)


def _tre_ngay(finish, han_sx) -> int | None:
    if finish is None or han_sx is None:
        return None
    return (finish.date() - han_sx).days


def _ket_qua(service, nguon, id, kq, *, rows, han_sx, han_giao, luot, giu: int = 0,
             tom_tat: str | None = None) -> dict:
    """Gói kết quả cho UI: từng bước đã xếp (kèm lý do chọn máy) · bước bỏ qua · hạn & độ trễ."""
    nhan = service._nap_nhan(rows)
    ten = {r.id: (nhan.lsx_cd.get(r.lsx_cong_doan_id) if r.nguon == NGUON_LSX
                  else nhan.bg_cd.get(r.bai_ghep_cong_doan_id)) for r in rows}
    finish = kq["finish_chuoi"]
    tre = _tre_ngay(finish, han_sx)
    da_xep = [{
        "dong_id": k["dong_id"], "thu_tu": k["thu_tu"],
        "cong_doan_ten": ten.get(k["dong_id"]),
        "may_id": k.get("may_id"), "may_ten": k.get("may_ten"),
        "start_at": _naive(k["start"]), "finish_at": _naive(k["finish"]),
        "chiem_may_phut": k["chiem_may_phut"],
        "chiem_may_phut_min": k["chiem_may_phut_min"],
        "chiem_may_phut_max": k["chiem_may_phut_max"],
        "so_may_xet": k.get("so_may_xet", 0),
        "ly_do": k["ly_do"],
        "canh_bao": k.get("canh_bao") or [],
    } for k in kq["da_xep"]]
    bo_qua = [{"dong_id": b["dong_id"], "thu_tu": b["thu_tu"],
               "cong_doan_ten": ten.get(b["dong_id"]), "ly_do": b["ly_do"]}
              for b in kq["bo_qua"]]
    if tom_tat is None:
        phan = [f"Xếp được {len(da_xep)} bước"]
        if bo_qua:
            phan.append(f"{len(bo_qua)} bước chưa xếp được")
        if giu:
            phan.append(f"{giu} bước giữ nguyên (đã có giờ hoặc đang khoá)")
        if tre is not None:
            phan.append(f"trễ hạn SX {tre} ngày" if tre > 0 else
                        (f"còn dư {-tre} ngày trước hạn SX" if tre < 0 else "vừa đúng hạn SX"))
        if luot == 2:
            phan.append("đã chạy thêm lượt cứu hạn")
        tom_tat = " · ".join(phan) + "."
    return {
        "nguon": nguon, "id": id, "luot": luot,
        "da_xep": da_xep, "bo_qua": bo_qua,
        "so_giu_nguyen": giu,
        "finish_chuoi": _naive(finish),
        "han_sx": han_sx, "han_giao": han_giao,
        "tre_han_sx": bool(tre is not None and tre > 0),
        "tre_ngay": tre if (tre is not None and tre > 0) else None,
        "tom_tat": tom_tat,
    }
