"""Gợi ý cho một dòng — CÙNG bộ óc với tự-xếp (`auto`), chỉ khác là không ghi gì.

Trước đây hai khối gợi ý trên màn chạy hai đường riêng và nói hai giờ khác nhau: "gợi ý máy" chỉ
soi khe trống theo mô hình cũ, còn "gợi ý khe" mới chạy đủ luật. Nay CẢ HAI gọi chung
`auto.san_va_cho` (một sàn duy nhất) và `auto.ung_vien_may` (chấm từng máy bằng đúng
`_van_de_dat_lich` mà nút Lưu dùng) — máy/khe đã đề xuất thì bấm vào là lưu được, không bao giờ đề
xuất xong lại bị chính hệ chặn.

- `goi_y`     : top-3 MÁY, sắp bằng đúng chính sách của tự-xếp (kịp hạn trước, rồi ĐIỂM `diem_may`),
  mỗi máy kèm điểm · bảng ba trục · một câu vì-sao. Kèm `bi_loai`: những máy KHÔNG vào được danh
  sách và thiếu đúng cái gì — vắng mặt im lặng là thứ làm người xếp thôi tin cái gợi ý.
  v2 vẫn KHÔNG phán máy theo khổ · số màu · định lượng (spec §6) — kể cả dưới dạng điểm.
- `goi_y_khe` : ≤3 KHE sớm nhất trên máy đang chọn, mỗi khe kèm NHÃN NGÀY thật (chủ nhật · ngày lễ ·
  ca đêm) thay vì gắn đại chữ "lý tưởng" cho một chỗ không ai đi làm.

Sàn ở đây ĐÃ theo routing: bước có tiền nhiệm chưa xếp thì khe gợi ý nằm SAU giờ ước xong của tiền
nhiệm, và kèm cảnh báo nói rõ đang chờ ai (`auto._kem_cho`) — trước đây tiền nhiệm chưa có giờ bị bỏ
qua im lặng nên hệ gợi ý cả những khe chạy trước công đoạn trước nó.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from ..xep_lich_service import _aware, _naive
from . import auto
from . import chan_doan
from . import constraint as C

_THU = ("Thứ hai", "Thứ ba", "Thứ tư", "Thứ năm", "Thứ sáu", "Thứ bảy", "Chủ nhật")


def goi_y(service, *, dong_id: int) -> dict:
    """Gợi ý MÁY cho dòng `dong_id` — chấm bằng đúng luật đặt lịch, sắp bằng đúng chính sách tự-xếp.

    Giữ nguyên hình dạng `{may_id, khe_trong, finish_neu_xep, han_lui, goi_y_may}` cho tương thích;
    ba mốc bám-máy để None (UI v2 chỉ đọc `goi_y_may`). Thuê ngoài đi theo ngày gửi/nhận, không
    chiếm máy ⇒ danh sách rỗng.
    """
    with service.ctx.dong_bang():                                # thuần đọc — xem `auto.ung_vien_may`
        return _goi_y(service, dong_id=dong_id)


def _goi_y(service, *, dong_id: int) -> dict:
    dong = service.core._get_dong(dong_id)
    rong = {"may_id": dong.may_id, "khe_trong": None, "finish_neu_xep": None,
            "han_lui": None, "goi_y_may": [], "bi_loai": [], "vi_sao_trong": None}
    shadow0 = service._shadow(dong, {})
    san, cho = auto.san_va_cho(service, dong, shadow0)
    ca = service.ctx.ca_windows()
    ket: list[str] = []
    ung_vien = auto.ung_vien_may(service, dong, san=san, chan_ngay=auto.CHAN_NGAY_MAC_DINH,
                                 ca=ca, ket=ket)
    if not ung_vien:
        return {**rong, "bi_loai": ket, "vi_sao_trong": auto._vi_sao_khong_may(
            ket, auto.CHAN_NGAY_MAC_DINH)}
    # Sắp bằng ĐÚNG chính sách tự-xếp: bốc dần máy tốt nhất còn lại nên thứ tự hiện ra khớp hệt thứ
    # tự máy sẽ tự chọn — người xem không phải đoán "sao nó xếp máy khác cái nó gợi ý".
    con = list(ung_vien)
    xep: list[dict] = []
    while con and len(xep) < 3:
        chon = auto.chon_may(con, nhanh_nhat=False)
        chon["ly_do"] = auto.ly_do_chon(chon, ung_vien, nhanh_nhat=False)
        xep.append(chon)
        con = [u for u in con if u["may_id"] != chon["may_id"]]
    return {
        **rong,
        # Máy BỊ LOẠI cũng phải nói ra. Trước đây máy vắng mặt trong danh sách là vắng mặt IM LẶNG,
        # người xếp lịch chỉ thấy "sao không có máy X" mà không có đường nào biết vì sao — trong khi
        # lý do gần như luôn là một ô dữ liệu còn trống ở Danh mục, sửa một phút là xong.
        "bi_loai": ket,
        "vi_sao_trong": None,
        "goi_y_may": [{
            "may_id": u["may_id"],
            "may_ten": u["may_ten"],
            "khe_trong": _naive(u["start"]),
            "finish": _naive(u["finish"]),
            "chiem_may_phut": u["chiem_may_phut"],
            "chiem_may_phut_min": u["chiem_may_phut_min"],
            "chiem_may_phut_max": u["chiem_may_phut_max"],
            "cung_gom": u["cung_gom"],
            "nhan_ngay": _nhan_ngay(service, u["start"], ca),
            "canh_bao": auto._kem_cho(u["canh_bao"], cho),
            "ly_do": u["ly_do"],
            "diem": u["diem"]["diem"],
            "tre_han": u["diem"]["tre_han"],
            "truc": u["diem"]["truc"],
        } for u in xep],
    }


def goi_y_khe(service, *, dong_id: int, tu, den, toi_da: int = 3) -> dict:
    """≤ `toi_da` KHE sớm nhất để xếp dòng `dong_id`, cửa sổ [tu, den] chỉ là TRẦN nhìn.

    Sàn thời gian vẫn là sàn thật (`auto.san_va_cho`) chứ không phải mép trái cửa sổ đang xem —
    kéo Gantt về tuần trước không được phép đẻ ra một khe nằm trong quá khứ.

    Đã bắt đầu là chạy LIÊN TỤC trên máy cố định nên khe bắt đầu sớm nhất cũng là khe kết thúc sớm
    nhất — duyệt mốc tăng dần, nhận cái đầu tiên không vướng luật CHẶN, tới khi đủ `toi_da`.
    """
    with service.ctx.dong_bang():                                # thuần đọc — xem `auto.ung_vien_may`
        return _goi_y_khe(service, dong_id=dong_id, tu=tu, den=den, toi_da=toi_da)


def _goi_y_khe(service, *, dong_id: int, tu, den, toi_da: int = 3) -> dict:
    dong = service.core._get_dong(dong_id)
    if not dong.may_id and getattr(dong, "department_id", None) is None:
        return {"khe": [], "ghi_chu": "Chọn máy hoặc tổ trước rồi hệ mới gợi ý được khe."}
    shadow = service._shadow(dong, {})
    dur = service._thoi_luong_v2(shadow)
    chiem = int(dur.get("chiem_may_phut") or 0)
    if dur.get("canh_bao") or chiem <= 0:
        ma = dur.get("canh_bao")
        return {"khe": [], "ghi_chu": (chan_doan.chi_tiet(service, dong, ma)[0] if ma
                                       else "Chưa tính được thời lượng bước này.")}
    chiem_max = int(dur.get("chiem_may_phut_max") or chiem)
    ca = service.ctx.ca_windows()
    san, cho = auto.san_va_cho(service, dong, shadow)
    tran = datetime.combine(den, time.min, tzinfo=timezone.utc) + timedelta(days=1)
    if san >= tran:
        vi = f" (chờ {', '.join(cho)} xong)" if cho else ""
        return {"khe": [], "ghi_chu": "Sớm nhất bước này chạy được là "
                                      f"{_naive(san):%d/%m %H:%M}{vi} — ngoài khoảng đang xem."}
    chan_ngay = max(1, (tran.date() - san.date()).days)
    khe: list[dict] = []
    for start in auto._moc_ung_vien(service, dong, shadow, san=san, chan_ngay=chan_ngay, ca=ca):
        if start >= tran:
            break
        finish = C.finish_lien_tuc(start, chiem)
        vd = service._van_de_dat_lich(
            shadow, start=start, finish=finish,
            finish_max=C.finish_lien_tuc(start, chiem_max),
            may_id=shadow.may_id, department_id=shadow.department_id,
            canh_bao=None, exclude_id=dong.id,
        )
        if any(i["muc"] == C.MUC_CHAN_DAT_LICH for i in vd):
            continue
        canh_bao = [i for i in vd if i["muc"] == C.MUC_CANH_BAO]
        khe.append({
            "start_at": _naive(start),
            "finish_at": _naive(finish),
            "chiem_may_phut": chiem,
            "chiem_may_phut_min": int(dur.get("chiem_may_phut_min") or chiem),
            "chiem_may_phut_max": chiem_max,
            "nhan_ngay": _nhan_ngay(service, start, ca),
            "canh_bao": auto._kem_cho(canh_bao, cho),
        })
        if len(khe) >= toi_da:
            break
    return {"khe": khe, "ghi_chu": None if khe else
            "Không thấy khe trống trong khoảng đang xem — mở rộng cửa sổ hoặc đổi máy."}


def _nhan_ngay(service, start: datetime, ca) -> dict:
    """Nhãn THẬT của thời điểm bắt đầu: thứ mấy · có phải ngày lễ · có rơi vào ca đêm không.

    Có cái này thì UI không còn phải gắn đại chữ "lý tưởng" cho một khe rơi vào chủ nhật hay mùng 2
    tháng 9 chỉ vì nó sạch luật — ngày lễ trong v2 CHỈ tô nền, vẫn xếp được, nên phải nói ra để người
    xếp tự quyết chứ đừng giấu.
    """
    s = _aware(start)
    d = s.date()
    le = next((x for x in service.ctx.ngay_le(d, d)), None)
    phut = s.hour * 60 + s.minute
    dem = any(qua_dem and (phut >= b or phut < e) for b, e, qua_dem in ca)
    return {
        "thu": _THU[d.weekday()],
        "cuoi_tuan": d.weekday() >= 5,
        "ngay_le": (le or {}).get("ten") or None,
        "ca_dem": bool(dem),
    }
