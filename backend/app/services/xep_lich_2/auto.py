"""Tự xếp lịch CẢ MỘT lệnh/bài — chạy đúng bộ luật `constraint` mà con người đang bấm tay.

Vì sao viết ở đây chứ không nhét vào `service`: tự-xếp là một VÒNG LẶP QUYẾT ĐỊNH (chọn máy → chọn
khe → đo hậu quả → sang bước sau), khác hẳn các hàm còn lại vốn chỉ tính-một-dòng. Tách ra để đọc
được thuật toán như đọc một trang giấy.

Ba điều làm nên "thông minh" ở đây (chứ không phải nhét bừa vào khe trống đầu tiên):

1. **Chuỗi, không phải rời rạc.** Bước sau đợi bước trước XONG (`tien_nhiem_finish`), và mỗi lần đặt
   xong là ghi ngay vào phiên ⇒ bước kế tiếp NHÌN THẤY máy vừa bị chiếm. Xếp một lệnh 6 bước ra một
   dây liền mạch, không phải 6 quyết định mù nhau.
2. **Chọn máy theo GIỜ XONG, phá hoà bằng CÔNG CANH MÁY.** Máy rảnh sớm chưa chắc xong sớm (tốc độ
   khai theo từng máy). Nhưng nếu chỉ so giờ xong thì tiêu chí "nối vào việc cùng giấy/khổ/mực"
   không bao giờ có cửa — nó chỉ thắng khi hai giờ xong BẰNG NHAU TỪNG GIÂY, gần như không xảy ra.
   Nên ở đây mở một CỬA SỔ DUNG SAI quanh giờ xong tốt nhất: mọi máy xong trong cửa sổ đó coi như
   ngang nhau, rồi mới ưu tiên máy nối được việc cùng gom + máy đang rảnh hơn.
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
from . import constraint as C

# Cửa sổ dung sai khi so giờ xong giữa các máy: 60 phút, hoặc 10% thời lượng nếu bước dài hơn 10
# tiếng. Trong cửa sổ này coi như "xong ngang nhau" → nhường cho tiêu chí công canh máy / tải máy.
# Số này CỐ Ý thô: nó chỉ đổi THỨ TỰ ĐỀ XUẤT, không đụng bất kỳ công thức thời gian nào.
DUNG_SAI_PHUT = 60
DUNG_SAI_TY_LE = 0.10

# Trần ngày dò tới khi tìm khe cho một bước (kể từ sàn thời gian của bước đó).
CHAN_NGAY_MAC_DINH = 60
# Trần mốc ứng viên xét cho MỘT bước — chặn vòng chấm thoái hoá khi lịch quá dày.
TRAN_UNG_VIEN = 400

# Vì sao một bước không-chọn-máy chưa tính được thời lượng — nói thẳng thứ dữ liệu đang thiếu.
_LY_DO_THIEU = {
    "may_chua_toc_do": "Máy chưa khai tốc độ nên chưa tính được thời lượng chạy.",
    "chua_quy_doi": "Đơn vị của bước chưa quy đổi được về đơn vị tốc độ máy.",
    "thue_ngoai_chua_lich": "Bước thuê ngoài chưa khai ngày gửi/nhận (hoặc số ngày gia công).",
}


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
    cùng một bước trên hai máy ra hai con số. Máy chưa khai tốc độ ⇒ None (không hứa giờ xong nào)."""
    lcd = _buoc_goc(service, dong)
    if lcd is None:
        return None
    d = thoi_luong_buoc(lcd, may, service.core._sl_tinh(lcd, may))
    chiem = int(round(d.get("chiem_may_phut") or 0))
    if chiem <= 0:
        return None
    return {
        "chiem_may_phut": chiem,
        "chiem_may_phut_min": int(round(d.get("chiem_may_phut_min") or chiem)),
        "chiem_may_phut_max": int(round(d.get("chiem_may_phut_max") or chiem)),
    }


# ============================ SÀN THỜI GIAN + MỐC ỨNG VIÊN ============================
def san_thoi_gian(service, dong, shadow) -> datetime:
    """Sớm nhất bước này được phép bắt đầu — MỘT sàn duy nhất, gộp đủ bốn nguồn ràng buộc.

    `max(bây giờ · bàn giao sang SX · mọi tiền nhiệm đã xếp xong · ca đầu ngày vật tư hứa về)`.
    Gộp một chỗ để gợi ý máy, gợi ý khe và tự-xếp không bao giờ nói ba giờ khác nhau — lỗi cũ là mỗi
    nhánh tự lấy một sàn riêng.
    """
    som = service.core._boi_canh_chuoi(dong)[0]
    for f in service.ctx.tien_nhiem_finish(shadow):
        fa = _aware(f)
        if fa is not None and (som is None or fa > som):
            som = fa
    ngay_ve = service.ctx.ngay_vat_tu(dong)
    if ngay_ve is not None:
        ca = service.ctx.ca_windows()
        bat_dau_som = min((b for b, _, _ in ca), default=C.GIO_BAT_DAU * 60)
        nguong = datetime(ngay_ve.year, ngay_ve.month, ngay_ve.day,
                          tzinfo=timezone.utc) + timedelta(minutes=int(bat_dau_som))
        if som is None or nguong > som:
            som = nguong
    return som


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
                  chan_ngay: int, ca) -> tuple[datetime | None, list[dict]]:
    """Khe SỚM NHẤT không vướng luật CHẶN ĐẶT LỊCH, kèm các cảnh báo còn lại của khe đó.

    Chạy liên tục nên khe bắt đầu sớm nhất cũng là khe kết thúc sớm nhất — duyệt mốc tăng dần rồi
    nhận cái đầu tiên sạch là tối ưu, không cần quét hết.
    """
    for start in _moc_ung_vien(service, dong, shadow, san=san, chan_ngay=chan_ngay, ca=ca):
        finish = C.finish_lien_tuc(start, chiem)
        vd = service._van_de_dat_lich(
            shadow, start=start, finish=finish,
            finish_max=C.finish_lien_tuc(start, chiem_max),
            may_id=shadow.may_id, department_id=shadow.department_id,
            canh_bao=None, exclude_id=dong.id,
        )
        if any(i["muc"] == C.MUC_CHAN_DAT_LICH for i in vd):
            continue
        return start, [i for i in vd if i["muc"] == C.MUC_CANH_BAO]
    return None, []


# ============================ CHỌN MÁY ============================
def ung_vien_may(service, dong, *, san: datetime, chan_ngay: int, ca) -> list[dict]:
    """Mọi máy làm được bước này, kèm khe sớm nhất + giờ xong + hai tiêu chí phá hoà."""
    # Vòng chấm này THUẦN ĐỌC mà lặp rất dày: mỗi máy × mỗi mốc ứng viên đều hỏi lại đúng bấy nhiêu
    # câu (ca xưởng · vùng khoá máy · việc đã xếp · quân số tổ · tiền nhiệm · hai hạn). Đóng băng ctx
    # trong đúng MỘT lượt chấm ⇒ mỗi câu chỉ chạm DB một lần, kết quả không đổi một ly.
    # CỐ Ý không bọc ở ngoài `tu_xep`: sau mỗi bước vừa ghi, máy đã bị chiếm thêm — ảnh chụp cũ sẽ
    # nói dối và bước sau sẽ đè lên bước trước.
    with service.ctx.dong_bang():
        return _ung_vien_may(service, dong, san=san, chan_ngay=chan_ngay, ca=ca)


def _ung_vien_may(service, dong, *, san: datetime, chan_ngay: int, ca) -> list[dict]:
    core = service.core
    lsx = core.lsx_repo.get(dong.lsx_id) if dong.lsx_id else None
    gom = core._gom_key(lsx)
    ra: list[dict] = []
    for may in core._may_lam_duoc(dong):
        d = _thoi_luong_tren_may(service, dong, may)
        if d is None:
            continue
        shadow = service._shadow(dong, {"may_id": may.id})
        start, canh_bao = _khe_dau_tien(
            service, dong, shadow, chiem=d["chiem_may_phut"], chiem_max=d["chiem_may_phut_max"],
            san=san, chan_ngay=chan_ngay, ca=ca,
        )
        if start is None:
            continue
        finish = C.finish_lien_tuc(start, d["chiem_may_phut"])
        ra.append({
            "may_id": may.id,
            "may_ten": may.ten,
            "start": start,
            "finish": finish,
            "canh_bao": canh_bao,
            "cung_gom": core._lien_ke_cung_gom(may.id, start, gom, exclude_id=dong.id),
            "tai_ngay": service._tai_may_ngay(
                may.id, start, finish, service.ctx.khoang_may_da_xep(may.id, dong.id)),
            **d,
        })
    return ra


def chon_may(ung_vien: list[dict], *, nhanh_nhat: bool) -> dict | None:
    """Chốt một máy trong danh sách ứng viên.

    `nhanh_nhat=True` ⇒ thuần giờ xong (lượt cứu hạn). Ngược lại: lấy giờ xong tốt nhất làm mốc, mở
    CỬA SỔ DUNG SAI quanh nó, rồi trong nhóm ngang nhau đó mới ưu tiên máy nối được việc cùng gom
    (khỏi canh máy lại) → máy đang ít tải hơn → thời lượng ngắn hơn → giờ xong sớm hơn.
    """
    if not ung_vien:
        return None
    tot = min(u["finish"] for u in ung_vien)
    if nhanh_nhat:
        return min(ung_vien, key=lambda u: (u["finish"], u["chiem_may_phut"], u["may_id"]))
    chiem_tot = min(u["chiem_may_phut"] for u in ung_vien if u["finish"] == tot)
    tol = max(DUNG_SAI_PHUT, int(chiem_tot * DUNG_SAI_TY_LE))
    gan = [u for u in ung_vien if (u["finish"] - tot).total_seconds() / 60.0 <= tol]
    return min(gan, key=lambda u: (not u["cung_gom"], u["tai_ngay"], u["chiem_may_phut"],
                                   u["finish"], u["may_id"]))


def ly_do_chon(chon: dict, ung_vien: list[dict], *, nhanh_nhat: bool) -> str:
    """Câu giải thích NGẮN vì sao máy này — để người xếp lịch soi lại được quyết định của máy."""
    if len(ung_vien) <= 1:
        return "Chỉ một máy làm được bước này."
    tot = min(u["finish"] for u in ung_vien)
    tre_phut = int(round((chon["finish"] - tot).total_seconds() / 60.0))
    if nhanh_nhat:
        return "Lượt cứu hạn: chọn máy cho giờ xong sớm nhất."
    if chon["cung_gom"] and tre_phut > 0:
        return (f"Nối ngay sau việc cùng giấy · khổ · bộ mực nên gần như khỏi canh lại máy "
                f"(chịu xong muộn hơn {tre_phut} phút so với máy nhanh nhất).")
    if chon["cung_gom"]:
        return "Xong sớm nhất, lại nối ngay sau việc cùng giấy · khổ · bộ mực nên khỏi canh lại máy."
    if tre_phut > 0:
        return f"Xong chênh {tre_phut} phút so với máy nhanh nhất nhưng máy này đang rảnh hơn."
    return "Xong sớm nhất trong các máy làm được bước này."


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


def _xep_theo_thoi_luong_san(service, dong, shadow, *, san, chan_ngay, ca, ly_do) -> dict:
    """Nhánh dùng chung cho bước KHÔNG chọn máy (thuê ngoài · làm tay theo tổ): thời lượng đã cố
    định sẵn, chỉ còn việc tìm khe sớm nhất."""
    dur = service._thoi_luong_v2(shadow)
    chiem = int(dur.get("chiem_may_phut") or 0)
    if chiem <= 0 or dur.get("canh_bao"):
        return {"ok": False, "ly_do": _LY_DO_THIEU.get(dur.get("canh_bao"))
                                     or "Chưa tính được thời lượng bước này."}
    chiem_max = int(dur.get("chiem_may_phut_max") or chiem)
    start, canh_bao = _khe_dau_tien(service, dong, shadow, chiem=chiem, chiem_max=chiem_max,
                                    san=san, chan_ngay=chan_ngay, ca=ca)
    if start is None:
        return {"ok": False,
                "ly_do": f"Không tìm được khe hợp lệ trong {chan_ngay} ngày tới (tổ kín người "
                         f"hoặc vướng ràng buộc khác)."}
    finish = C.finish_lien_tuc(start, chiem)
    _ap(dong, may_id=None, start=start, finish=finish)
    return {"ok": True, "may_id": None, "may_ten": None, "start": start, "finish": finish,
            "chiem_may_phut": chiem,
            "chiem_may_phut_min": int(dur.get("chiem_may_phut_min") or chiem),
            "chiem_may_phut_max": chiem_max,
            "canh_bao": canh_bao, "so_may_xet": 0, "ly_do": ly_do}


def xep_mot_buoc(service, dong, *, chan_ngay: int, nhanh_nhat: bool) -> dict:
    """Xếp MỘT dòng. Trả `{ok, ...}`; `ok=False` kèm `ly_do` và KHÔNG ghi gì vào dòng."""
    ca = service.ctx.ca_windows()
    shadow0 = service._shadow(dong, {})
    san = san_thoi_gian(service, dong, shadow0)
    loai = getattr(dong, "loai_buoc", None)

    if loai == LB_THUE_NGOAI:
        return _xep_theo_thoi_luong_san(
            service, dong, shadow0, san=san, chan_ngay=chan_ngay, ca=ca,
            ly_do="Bước gửi ngoài — xếp theo lead-time gửi → nhận, không chiếm máy.")
    if loai == LB_TO:
        return _xep_theo_thoi_luong_san(
            service, dong, shadow0, san=san, chan_ngay=chan_ngay, ca=ca,
            ly_do="Bước làm tay — xếp vào khe sớm nhất tổ còn đủ người.")

    ung_vien = ung_vien_may(service, dong, san=san, chan_ngay=chan_ngay, ca=ca)
    if not ung_vien:
        return {"ok": False, "ly_do": "Không máy nào làm được bước này còn khe trống trong "
                                      f"{chan_ngay} ngày tới — hoặc máy chưa khai tốc độ nên chưa "
                                      "tính được thời lượng."}
    chon = chon_may(ung_vien, nhanh_nhat=nhanh_nhat)
    _ap(dong, may_id=chon["may_id"], start=chon["start"], finish=chon["finish"])
    return {"ok": True, "may_id": chon["may_id"], "may_ten": chon["may_ten"],
            "start": chon["start"], "finish": chon["finish"],
            "chiem_may_phut": chon["chiem_may_phut"],
            "chiem_may_phut_min": chon["chiem_may_phut_min"],
            "chiem_may_phut_max": chon["chiem_may_phut_max"],
            "canh_bao": chon["canh_bao"], "so_may_xet": len(ung_vien),
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
