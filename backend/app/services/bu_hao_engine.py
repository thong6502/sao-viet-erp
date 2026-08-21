"""Bù hao engine — hàm THUẦN tra số tờ bù hao. Không I/O, không ORM.

Nối Công đoạn ↔ module Bù hao. Mỗi công đoạn khai `kieu_bu_hao`:
  - `tra_bang` → TRỎ 1 mã bù hao (`bu_hao_id`) ở module Bù hao; engine tra bậc số lượng:
      chọn bậc [sl_tu..sl_den] chứa SL → giá trị (tờ | %).
  - `co_dinh` → cộng thẳng `so_to_bu_hao` tờ (ép kim, UV… — không theo bảng).
  - `khong` → 0.

Bậc số lượng theo quy ước "X trở xuống / X–Y" ⇒ chặn trên bao gồm: dòng chứa SL khi
`sl_tu < SL ≤ sl_den` (bậc cuối `sl_den = None` ⇒ SL > sl_tu). `don_vi='pct'` ⇒ giá trị %×SL.
"""
from __future__ import annotations


def _f(v, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def tra_bac_raw(bac: list[dict], sl: float) -> dict | None:
    """Bậc KHỚP với `sl`, trả nguyên dict để đọc được `don_vi`. None nếu không bậc nào chứa."""
    sl = _f(sl)
    for b in (bac or []):
        lo = _f(b.get("sl_tu"))
        hi = b.get("sl_den")
        in_band = sl > lo if hi in (None, "") else (lo < sl <= _f(hi))
        if in_band:
            return b
    return None


def tra_bac(bac: list[dict], sl: float) -> float:
    """Tra giá trị bù hao từ danh sách bậc số lượng của 1 dòng bù hao. Trả 0.0 nếu không khớp."""
    b = tra_bac_raw(bac, sl)
    if b is None:
        return 0.0
    gt = _f(b.get("gia_tri"))
    return gt * _f(sl) / 100.0 if b.get("don_vi") == "pct" else gt


def bu_hao_cong_doan(cd: dict, *, rows: list[dict], sl: float) -> float:
    """Số tờ bù hao của 1 công đoạn theo `kieu_bu_hao`.

    rows = danh sách dòng bù hao [{id, ma, bac:[…]}] (toàn bộ danh mục Bù hao).
    """
    kieu = cd.get("kieu_bu_hao", "khong")
    if kieu == "co_dinh":
        return _f(cd.get("so_to_bu_hao"))
    if kieu == "tra_bang":
        bid = cd.get("bu_hao_id")
        if bid is None:
            return 0.0
        row = next((r for r in rows if r.get("id") == bid), None)
        return tra_bac(row.get("bac") or [], sl) if row else 0.0
    return 0.0


def tong_bu_hao(cong_doans: list[dict], *, rows: list[dict], sl: float,
                pct_yeu_cau: float = 0.0) -> float:
    """Tổng số tờ bù hao 1 đơn = Σ bù hao mỗi công đoạn + %_yêu_cầu × SL (nếu đơn yêu cầu)."""
    total = sum(bu_hao_cong_doan(cd, rows=rows, sl=sl) for cd in cong_doans)
    return total + _f(sl) * _f(pct_yeu_cau) / 100.0


def hao_buoc(cd: dict, *, rows: list[dict], sl: float) -> tuple[float, float]:
    """Hao của 1 công đoạn ở mức thông lượng `sl`, TÁCH ĐÔI: `(số tờ cố định, tỷ lệ %)`.

    Đi ngược cần hai thứ này riêng vì chúng áp khác nhau: tờ cố định thì CỘNG, còn % thì CHIA
    (`vào = (ra + tờ) / (1 − %)`). Gộp sẵn thành một số như `bu_hao_cong_doan` là mất phần %.
    """
    kieu = cd.get("kieu_bu_hao", "khong")
    if kieu == "co_dinh":
        return _f(cd.get("so_to_bu_hao")), 0.0
    if kieu == "tra_bang":
        bid = cd.get("bu_hao_id")
        if bid is None:
            return 0.0, 0.0
        row = next((r for r in rows if r.get("id") == bid), None)
        b = tra_bac_raw(row.get("bac") or [], sl) if row else None
        if b is None:
            return 0.0, 0.0
        gt = _f(b.get("gia_tri"))
        return (0.0, gt) if b.get("don_vi") == "pct" else (gt, 0.0)
    return 0.0, 0.0


def chuoi_nguoc(cong_doans: list[dict], *, rows: list[dict], to_can: float) -> list[dict]:
    """ĐI NGƯỢC chuỗi công đoạn: từ số tờ tốt cần ở CUỐI, lần ngược ra số tờ phải vào ĐẦU.

    Mỗi bước hỏi đúng một câu "để nhả ra `ra` tờ tốt thì phải nhận vào bao nhiêu?":

        vào = (ra + tờ_cố_định) / (1 − %/100)

    Bậc bù hao tra theo `ra` — số tờ tốt phải ra khỏi CHÍNH bước đó, đã biết ngay khi xử lý
    bước nên KHÔNG cần lặp hội tụ. Nhờ vậy bước đầu chuỗi (in) rơi vào bậc CAO hơn bước cuối
    (xén), đúng thực tế; cộng xuôi phẳng theo một `to_net` chung thì mọi bước tra cùng một bậc.

    Trả về theo thứ tự XUÔI, cùng chỉ số với `cong_doans`: `[{vao, ra, hao}]` (số thực, chưa
    làm tròn — caller tự `ceil` khi cần số tờ nguyên).
    """
    return chuoi_nguoc_dv(
        [{"cd": cd} for cd in (cong_doans or [])], rows=rows, to_can=to_can
    )[0]


def chuoi_nguoc_dv(buoc: list[dict], *, rows: list[dict], to_can: float,
                   he_so: dict | None = None) -> tuple[list[dict], list[str]]:
    """Như `chuoi_nguoc` nhưng CÓ QUY ĐỔI ĐƠN VỊ ở từng bước — bản engine thật dùng.

    `buoc` = `[{cd, dv_vao, dv_ra, ten}]` theo thứ tự XUÔI, thêm hai khoá TUỲ CHỌN
    `tram_vao`/`tram_ra`. `he_so` = `{(trạm_vào, trạm_ra): số}` do CALLER cấp, vì hệ số thuộc về
    PHIẾU chứ không thuộc danh mục công đoạn (`con` từ bình bài, `so_manh_xa` từ khổ giấy). Cặp đổi
    đơn vị mà thiếu hệ số → tạm 1 và kêu warning, thà lộ ra còn hơn chia bằng số đoán.

    ⚠️ TRA HỆ SỐ VÀ SO LIỀN MẠCH ĐỀU THEO **TRẠM**, không theo mã đơn vị (11/08/2026). Xưởng khai
    được đơn vị riêng cho từng chặng dòng giấy (mã `to_in` gắn cờ trạm *tờ in*), mà bảng hệ số thì
    chỉ có 5 trạm — tra theo mã là cặp không khớp, ăn hệ số 1 và số giấy sai. Không truyền trạm thì
    lùi về chính mã, giữ nguyên hành vi cho caller cũ. Giá trị TRẢ RA vẫn là MÃ để hiển thị/ghi DB.

    Mỗi bước hỏi "để nhả ra `ra` (đơn vị RA) thì phải nhận vào bao nhiêu (đơn vị VÀO)?":

        ra_quy = ra / hệ_số               # đưa về đơn vị ĐẦU VÀO của bước
        vào    = (ra_quy + cố_định) / (1 − %/100)

    Bậc bù hao tra theo `ra` — ĐÚNG đơn vị của bước. Đây là điểm chính: bước đóng gói đếm CON thì
    tra bậc theo số con (5.000), không phải theo số tờ (24) như bản phẳng trước.

    Trả `(kết_quả, warnings)`; kết quả theo thứ tự XUÔI: `[{vao, ra, hao, dv_vao, dv_ra}]`.
    """
    hs_map = he_so or {}
    canh = list(buoc or [])
    warnings: list[str] = []

    def _tv(b: dict) -> str | None:
        return b.get("tram_vao") or b.get("dv_vao")

    def _tr(b: dict) -> str | None:
        return b.get("tram_ra") or b.get("dv_ra")

    # Chuỗi phải LIỀN MẠCH: chặng ra của bước trước = chặng vào của bước sau. So bằng TRẠM chứ
    # không bằng mã — hai bước khai hai mã khác nhau cho cùng một chặng là chuyện hợp lệ. Lệch thật
    # thì engine KHÔNG được tự bắc cầu, chỉ nói ra để người khai đi sửa.
    for truoc, sau in zip(canh, canh[1:]):
        if _tr(truoc) != _tv(sau):
            warnings.append(
                f"Bước '{truoc.get('ten') or '?'}' ra {truoc.get('dv_ra')} nhưng bước "
                f"'{sau.get('ten') or '?'}' vào {sau.get('dv_vao')} — chuỗi đứt đơn vị."
            )

    ra = _f(to_can)
    out: list[dict] = []
    for b in reversed(canh):
        dv_vao, dv_ra = b.get("dv_vao"), b.get("dv_ra")
        tram_vao, tram_ra = _tv(b), _tr(b)
        hs = 1.0
        if tram_vao != tram_ra:
            hs = _f(hs_map.get((tram_vao, tram_ra)))
            if hs <= 0:
                hs = 1.0
                warnings.append(
                    f"Bước '{b.get('ten') or '?'}' đổi {dv_vao} → {dv_ra} nhưng chưa biết hệ số "
                    f"quy đổi — tạm tính 1."
                )
        ra_quy = ra / hs
        fixed, pct = hao_buoc(b.get("cd") or {}, rows=rows, sl=ra)
        pct = min(max(pct, 0.0), 99.0)          # chặn chia cho 0 và hao âm
        # `fixed` khai ở ĐƠN VỊ VÀO của bước — bước "Xả giấy" (`to_nguyen → to`) thì hao xả là số
        # TỜ NGUYÊN phí khi pha, cộng thẳng (KHÔNG chia hs). Đừng "sửa" thành fixed/hs: mô hình tách
        # xả giấy khỏi in, In thật là `to → to`. Xem test_chuoi_nguoc_dv_cau_to_nguyen_sang_to_in.
        vao = (ra_quy + fixed) / (1.0 - pct / 100.0)
        # Trả kèm TRẠM: caller đọc số ra khỏi chuỗi tại một ranh giới (số tờ in, số tờ nguyên) và
        # phải hỏi theo trạm — dò theo mã thì đơn vị riêng của xưởng không khớp, mốc rơi về 0.
        out.append({"vao": vao, "ra": ra, "hao": vao - ra_quy,
                    "dv_vao": dv_vao, "dv_ra": dv_ra,
                    "tram_vao": tram_vao, "tram_ra": tram_ra})
        ra = vao
    out.reverse()
    return out, warnings
