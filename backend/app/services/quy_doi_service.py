"""Quy đổi đơn vị — HÀM THUẦN, không giữ state, không đụng DB (caller nạp danh mục rồi truyền vào).

Nguồn chân lý là BẢNG CẶP người dùng khai: "1 tấn = 1.000 kg", "1 ram = 500 tờ". Khai một chiều là
đủ — máy đi ngược bằng 1/hệ số. Cặp chưa khai thẳng thì dò đường qua trung gian (hỏi tấn → g thì đi
qua kg). Không có khái niệm "nhóm" hay "đơn vị chuẩn" nào cả: hai đơn vị đổi được cho nhau khi và
chỉ khi có đường cặp nối chúng.

Hệ số của một cặp được phép là **CÔNG THỨC** thay vì con số — quy đổi ĐỘNG. "1 tờ bằng mấy kg"
không có đáp án chung (tờ 65×86 Ford 70 là 0,039 kg, tờ 79×109 Couché 300 là 0,258 kg) nhưng TÍNH
ĐƯỢC từ khổ + định lượng, nên nó vẫn là một dòng khai được: `1 tờ = dinh_luong * dai * rong` kg.
Biến do **NƠI GỌI** bơm vào (`ngu_canh`) chứ danh mục không tự đoán: chỉ nơi gọi mới biết bước này
đang đếm tờ NGUYÊN (mua giấy) hay tờ IN (chạy máy) — hai thứ khác khổ nên khác cân. Cạnh động
thiếu biến thì bị LOẠI khỏi đồ thị, và câu trả lời nói rõ thiếu gì.

Mọi kết quả kèm `dien_giai` khoe cách tính (`241 tờ × 0,168 kg/tờ = 40,49 kg`) — người đọc kiểm
được bằng mắt; thiếu dữ liệu thì nói thiếu gì, KHÔNG đoán.
"""
from __future__ import annotations

import re

from .bien_cong_thuc import LOAI_QUY_DOI, bien_cho, ngu_canh_lenh
from .thanh_phan_engine import MATH_FUNCS

# 🔴 TÁM HẰNG MÃ ĐƠN VỊ ĐÃ XOÁ 15/08/2026 (`DV_TO · DV_RAM · DV_CAI · DV_CUON · DV_CM2 · DV_M2 ·
# DV_KG · DV_TAN`). Đo trước khi xoá: KHÔNG nơi nào import từ file này — 9 chỗ dùng `DV_TO` và 5
# chỗ dùng `DV_CAI` đều lấy bản ở `models/lsx.py`. Sáu cái còn lại 0 chỗ dùng.
#
# Tệ hơn cả rác: tiêu đề cũ ghi "Mã đơn vị mà CODE tham chiếu" khiến người đọc tưởng phép quy đổi
# tra theo mã cứng. KHÔNG — `doi()` chỉ dò đồ thị cặp trong DB, xưởng khai đơn vị tên gì cũng chạy.

# Biến dùng được trong công thức quy đổi — tên là VAI TRÒ ("khổ của tờ đang đếm"), không phải tên
# cột của giấy. Nhãn hiện nguyên văn cho người dùng khi thiếu. Dài/rộng tính bằng MÉT, định lượng
# bằng kg/m².
#
# LẤY TỪ TỪ ĐIỂN CHUNG (`bien_cong_thuc`) — trước đây khai riêng ở đây, thành ra hệ có hai bộ từ
# vựng công thức không ai đối chiếu. Thêm biến thì sửa từ điển, không sửa chỗ này.
BIEN = {b["ma"]: b["nhan"] for b in bien_cho(LOAI_QUY_DOI)}

_TU = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _so(v: float) -> str:
    """Số theo lối Việt: dấu . nhóm nghìn, dấu , thập phân, bỏ phần thập phân vô nghĩa.

    Số NHỎ giữ tới 4 chữ số thập phân: làm tròn 2 chữ số biến 0,2035 tấn thành "0,20 tấn", rồi
    diễn giải đọc ra thành "0,20 × 150.000 = 30.521" — người xem tưởng máy tính sai.
    """
    n = float(v)
    dec = 4 if 0 < abs(n) < 10 else 2
    s = f"{round(n, dec):,.{dec}f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    if "," in s:
        s = s.rstrip("0").rstrip(",")
    return s


def _tien(v: float) -> str:
    """Tiền: tròn về ĐỒNG. Lương/khoán không có xu, hiện 20.207,85 đ là nhiễu."""
    return f"{round(float(v)):,}".replace(",", ".")


def don_vi_map(rows) -> dict[str, dict]:
    """list[DonViDo] (hoặc dict) → tra cứu {khoá: {ma, ten, ho, he_so_goc}}.

    Đánh chỉ mục theo CẢ MÃ LẪN TÊN vì hai nơi gọi tên khác nhau: bảng đơn giá khoán lưu **chữ hiển
    thị** người dùng gõ ("m²", "tấn" — chốt "đơn vị gõ tự do"), còn bước lệnh dùng **mã** ("to",
    "cai"). Nếu chỉ tra theo mã thì đơn giá 150 đ/m² vĩnh viễn báo "chưa khai đơn vị" dù danh mục
    có m² — đúng lỗi vừa gặp khi thử. Mã luôn THẮNG tên khi trùng khoá.
    """
    out: dict[str, dict] = {}
    alias: dict[str, dict] = {}
    for r in rows or []:
        if isinstance(r, dict):
            ma, ten, ho, hs = r.get("ma"), r.get("ten"), r.get("ho"), r.get("he_so_goc")
        else:
            ma, ten, ho, hs = r.ma, r.ten, r.ho, r.he_so_goc
        if not ma:
            continue
        ma = str(ma).strip().lower()
        d = {
            "ma": ma,
            "ten": ten or ma,
            "ho": (ho or "khac").strip().lower(),
            "he_so_goc": _f(hs) or 1.0,
        }
        out[ma] = d
        ten_k = str(ten or "").strip().lower()
        if ten_k and ten_k != ma:
            alias.setdefault(ten_k, d)
    for k, v in alias.items():
        out.setdefault(k, v)          # mã đã chiếm khoá thì giữ mã
    return out


def ten_dv(ma: str, dvs: dict[str, dict]) -> str:
    return (dvs.get((ma or "").strip().lower()) or {}).get("ten") or ma


def ngu_canh(quy_cach: dict | None) -> dict[str, float]:
    """Quy cách của việc đang làm → BIẾN cho công thức quy đổi.

    Thân hàm đã CHUYỂN sang `bien_cong_thuc.ngu_canh_lenh` (11/08/2026) để nằm cạnh
    `ngu_canh_phieu` — hai hàm bơm số cho cùng một bộ biến phải nhìn thấy nhau. Giữ tên này làm
    cửa vào cho quy đổi vì đây là chỗ mọi lối quy đổi đi qua.
    """
    return ngu_canh_lenh(quy_cach)


def bien_trong(cong_thuc: str) -> list[str]:
    """Tên biến xuất hiện trong công thức (bỏ tên hàm) — dùng cho cả UI gợi ý lẫn báo thiếu."""
    return sorted({t for t in _TU.findall(cong_thuc or "") if t not in MATH_FUNCS})


def _doc_cap(r) -> tuple[str, str, float]:
    """Một dòng cặp → `(mã từ, mã đến, hệ số)`.

    🔴 Phần tử thứ TƯ (`cong_thuc`) đã GỠ 14/08/2026 cùng quy đổi động. Nếu bạn đang sửa hàm này:
    năm nơi đọc nó phải sửa CÙNG LƯỢT — vụ 13/08 vỡ đúng vì đổi 4→3 mà một chỗ còn đọc `[3]`.
    """
    if isinstance(r, dict):
        tu, den, hs = r.get("tu_ma"), r.get("den_ma"), _f(r.get("he_so"))
    else:
        tu, den, hs = getattr(r, "tu_ma", None), getattr(r, "den_ma", None), _f(r.he_so)
    return str(tu or "").strip().lower(), str(den or "").strip().lower(), hs


def cum_tinh(ma: str, rows) -> set[str]:
    """Mọi đơn vị với tới `ma` qua cặp quy đổi. Gồm cả chính `ma`.

    "Cụm" = một phép đo được gọi bằng nhiều tên: `kg · tấn · g`, `m² · cm²`, `tờ · ram`. Đổi qua
    lại bằng hằng số, không phụ thuộc lệnh nào — từ 14/08/2026 MỌI cặp đều thế, không còn cạnh
    động nào để phải loại trừ.

    Dùng cho hai việc: chặn khai công thức lượng thứ hai trong cùng cụm, và cho công thức khai ở
    một đơn vị LAN sang cả cụm (khai ở `kg` thì `tấn` dùng chung).
    """
    goc = str(ma or "").strip().lower()
    if not goc:
        return set()
    ke: dict[str, set[str]] = {}
    for r in rows or []:
        tu, den, _hs = _doc_cap(r)
        if not tu or not den:
            continue
        ke.setdefault(tu, set()).add(den)
        ke.setdefault(den, set()).add(tu)
    ra, hang_doi = {goc}, [goc]
    while hang_doi:
        for kia in ke.get(hang_doi.pop(), ()):
            if kia not in ra:
                ra.add(kia)
                hang_doi.append(kia)
    return ra


def cap_map(rows) -> dict[str, dict[str, float]]:
    """list[DonViQuyDoi] → đồ thị {ma_tu: {ma_den: he_so}}, CẢ HAI CHIỀU.

    Khai "1 tấn = 1.000 kg" là đủ để đổi ngược kg → tấn (nhân 1/1.000) — bắt khai hai dòng thì
    sớm muộn hai dòng lệch nhau. Rows phải kèm mã hai đầu (`tu_ma`/`den_ma`) vì hàm này thuần,
    không truy DB.

    🔴 GỠ 14/08/2026: nhánh dòng-CÔNG-THỨC (`ctx` + `gia_dinh_du_bien`). Hệ không còn quy đổi ĐỘNG
    — công thức nay khai ở CHÍNH đơn vị / mặt hàng và trả LƯỢNG, không có đích. Nhờ vậy đồ thị cặp
    thành hằng số thuần: đổi `tấn → kg` ra một đáp án bất kể đang đứng ở lệnh nào.
    """
    g: dict[str, dict[str, float]] = {}
    for r in rows or []:
        tu, den, hs = _doc_cap(r)
        if not tu or not den or tu == den or hs <= 0:
            continue
        g.setdefault(tu, {})[den] = hs
        g.setdefault(den, {})[tu] = 1.0 / hs
    return g


def duong_di(tu: str, den: str, cap: dict[str, dict[str, float]]) -> list[str] | None:
    """Đường ngắn nhất tu → den trên đồ thị cặp (BFS). None = không có đường nào.

    BFS chứ không DFS: đường qua ÍT chặng nhất thì sai số nhân dồn ít nhất, và diễn giải cũng
    ngắn hơn cho người đọc.
    """
    tu, den = (tu or "").strip().lower(), (den or "").strip().lower()
    if tu == den:
        return [tu]
    if tu not in cap:
        return None
    tu_dau: dict[str, str | None] = {tu: None}
    hang_doi = [tu]
    while hang_doi:
        cur = hang_doi.pop(0)
        for ke in cap.get(cur, {}):
            if ke in tu_dau:
                continue
            tu_dau[ke] = cur
            if ke == den:
                duong = [ke]
                while tu_dau[duong[-1]] is not None:
                    duong.append(tu_dau[duong[-1]])       # type: ignore[index]
                return list(reversed(duong))
            hang_doi.append(ke)
    return None


def he_so_duong(duong: list[str], cap: dict[str, dict[str, float]]) -> float:
    """Nhân dồn hệ số dọc đường: [tan, kg, g] → 1.000 × 1.000 = 1.000.000."""
    hs = 1.0
    for i in range(len(duong) - 1):
        hs *= cap[duong[i]][duong[i + 1]]
    return hs


def doi(gia_tri: float, tu: str, den: str, dvs: dict[str, dict],
        cap: dict[str, dict[str, float]] | None = None) -> dict:
    """Đổi theo CẶP đã khai (đi vòng qua trung gian nếu cần).

    Trả `{gia_tri, don_vi, dien_giai}`; không có đường thì `{thieu, ly_do}` nói rõ thiếu cặp nào.
    """
    tu_k, den_k = (tu or "").strip().lower(), (den or "").strip().lower()
    a, b = dvs.get(tu_k), dvs.get(den_k)
    if a is None or b is None:
        thieu = [x for x, o in ((tu_k, a), (den_k, b)) if o is None]
        return {"thieu": thieu, "ly_do": f"Đơn vị chưa khai trong danh mục: {', '.join(thieu)}."}
    # Cùng đơn vị (kể cả khi một bên gọi bằng mã "to", bên kia bằng tên "tờ") → khỏi phép tính.
    if tu_k == den_k or a["ma"] == b["ma"]:
        return {"gia_tri": _f(gia_tri), "don_vi": b["ten"],
                "dien_giai": f"{_so(gia_tri)} {b['ten']}"}

    duong = duong_di(a["ma"], b["ma"], cap or {})
    if duong is None:
        return {
            "thieu": ["cap"],
            "ly_do": f"Chưa khai quy đổi giữa {a['ten']} và {b['ten']} — thêm ở "
                     f"Cấu hình danh mục → Đơn vị & quy đổi.",
        }
    hs = he_so_duong(duong, cap or {})
    ket_qua = _f(gia_tri) * hs
    if len(duong) > 2:
        # Đi vòng thì NÓI RÕ đường: người xem phải biết con số đến từ đâu để còn kiểm.
        qua = " → ".join(ten_dv(m, dvs) for m in duong)
        dg = (f"{_so(gia_tri)} {a['ten']} × {_so(hs)} = {_so(ket_qua)} {b['ten']} "
              f"(qua {qua})")
    elif abs(hs - 1.0) < 1e-9:
        # Hai đơn vị đếm như nhau (cái ↔ cuốn ↔ hộp): chỉ là cách GỌI khác, đừng in "× 1".
        dg = f"{_so(gia_tri)} {a['ten']} = {_so(ket_qua)} {b['ten']}"
    else:
        dg = f"{_so(gia_tri)} {a['ten']} × {_so(hs)} = {_so(ket_qua)} {b['ten']}"
    return {"gia_tri": ket_qua, "don_vi": b["ten"], "dien_giai": dg}


# 🔴 KHỐI "QUY ĐỔI ĐỘNG" ĐÃ GỠ HẲN 14/08/2026 (chủ chốt: hệ không hỗ trợ `kg = f() g` nữa).
#
# Ba hàm chỉ sống vì cạnh động, nay xoá cùng nó:
#     `_canh_tren_duong` · `_dong_tren_duong`  — dò xem cạnh động nào nằm trên đường đi
#     `_chu_thich_dong`                        — câu "1 tờ = 0,168 kg (định lượng 0,3 × …)"
#     `_thieu_bien`                            — báo "chưa biết Định lượng giấy nên không đổi được"
#
# Công thức nay khai ở CHÍNH đơn vị (`don_vi_do.cong_thuc`) và CHÍNH mặt hàng
# (`vat_tu_in_an.cong_thuc_luong` · `giay_nguyen.cong_thuc_luong`) — trả LƯỢNG, KHÔNG có đích.
# Xem `LsxService._luong_vat_tu` (ba đường RIÊNG → CHUNG) và `KeHoachVatTuService._ve_goc`.


def doi_theo_quy_cach(gia_tri: float, tu: str, den: str, quy_cach: dict | None,
                      dvs: dict[str, dict], cap_rows=None) -> dict:
    """Đổi bằng CẶP đã khai. Cặp nay chỉ còn hệ số cố định, nên đây là phép thuần.

    `quy_cach` GIỮ trong chữ ký nhưng KHÔNG dùng nữa (14/08/2026) — trước đây nó cấp định lượng/khổ
    để thay vào công thức của cạnh động. Chưa rút khỏi chữ ký vì có 20 chỗ gọi trên 8 file; rút cùng
    lượt với việc gỡ cạnh động là đúng cái đã làm vỡ ba lần hôm 13/08. Rút ở lượt sau.
    """
    del quy_cach            # nói thẳng là bỏ, đừng để người đọc tưởng còn ăn
    tu_k, den_k = (tu or "").strip().lower(), (den or "").strip().lower()
    return doi(gia_tri, tu_k, den_k, dvs, cap_map(list(cap_rows or [])))


# --- Đơn vị dùng được cho MỘT mặt hàng ---------------------------------------------------------


def canh_quy_cach(don_vi_dong_goi: str | None, he_so_dong_goi, don_vi_goc: str | None) -> list[dict]:
    """Cạnh quy đổi RIÊNG của một mặt hàng: "1 <đóng gói> = <hệ số> <đơn vị gốc>".

    Không khai vào bảng cặp chung được: "1 thùng = 3 kg" đúng với keo nhưng sai với mực — hệ số
    này thuộc về MÓN, không thuộc về cặp đơn vị. Trả về đúng hình dạng dòng cặp (`tu_ma`/`den_ma`/
    `he_so`) để nối thẳng vào `cap_rows` — `cap_map` nuốt được, khỏi đẻ đường code đồ thị thứ hai.
    """
    tu = (don_vi_dong_goi or "").strip().lower()
    den = (don_vi_goc or "").strip().lower()
    hs = _f(he_so_dong_goi)
    if not tu or not den or tu == den or hs <= 0:
        return []
    return [{"tu_ma": tu, "den_ma": den, "he_so": hs}]


def don_vi_dung_duoc(goc: str, dvs: dict[str, dict], cap_rows=None,
                     quy_cach: dict | None = None) -> list[dict]:
    """Mọi đơn vị đổi được từ `goc` — nguồn cho dropdown "chọn đơn vị" ở Kho / NCC.

    `duong_di` chỉ trả lời "đi từ A tới B được không"; ở đây cần hỏi ngược lại "đứng ở A thì tới
    được những đâu", nên BFS LOANG cả đồ thị thay vì tìm một đích.

    Danh sách theo MÓN nhờ cạnh riêng của nó (quy cách đóng gói) — nơi gọi nối thêm
    `canh_quy_cach(...)` vào `cap_rows`.

    `quy_cach` GIỮ trong chữ ký nhưng KHÔNG dùng nữa (14/08/2026): trước đây nó bật/tắt cạnh động
    theo việc có đủ biến hay không. Không còn cạnh động thì danh sách chỉ phụ thuộc bảng cặp.

    Trả list `{ma, ten, he_so, he_so_ve_goc, la_goc, dien_giai}`, thứ tự BFS nên đơn vị gốc đứng
    đầu rồi tới các đơn vị gần nhất. Hai hệ số ngược nhau đều được trả vì hai phía dùng hai chiều:
    hiện tồn theo đơn vị khác thì nhân `he_so`, còn quy số người dùng nhập về gốc thì nhân
    `he_so_ve_goc` — bắt nơi gọi tự nghịch đảo là mời một lớp bug im lặng vào giữa số tồn kho.
    """
    goc_k = (goc or "").strip().lower()
    g = dvs.get(goc_k)
    if g is None:
        return []
    del quy_cach            # nói thẳng là bỏ, đừng để người đọc tưởng còn ăn
    ma_goc = g["ma"]
    cap = cap_map(list(cap_rows or []))

    he_so: dict[str, float] = {ma_goc: 1.0}
    hang_doi = [ma_goc]
    while hang_doi:
        cur = hang_doi.pop(0)
        for ke, hs in cap.get(cur, {}).items():
            if ke in he_so:
                continue
            he_so[ke] = he_so[cur] * hs
            hang_doi.append(ke)

    out: list[dict] = []
    for ma, hs in he_so.items():
        dv = dvs.get(ma)
        if dv is None or hs <= 0:
            continue          # cặp trỏ tới đơn vị đã gỡ khỏi danh mục — bỏ, đừng hiện mã trần
        la_goc = ma == ma_goc
        out.append({
            "ma": ma,
            "ten": dv["ten"],
            "he_so": hs,
            "he_so_ve_goc": 1.0 / hs,
            "la_goc": la_goc,
            "dien_giai": ("Đơn vị gốc" if la_goc
                          else f"1 {dv['ten']} = {_so(1.0 / hs)} {g['ten']}"),
        })
    return out


def tien_khoan(sl_buoc: float, don_vi_buoc: str, don_vi_gia: str, don_gia: float,
               quy_cach: dict | None, dvs: dict[str, dict], cap_rows=None) -> dict:
    """Tiền khoán DỰ KIẾN của 1 bước = SL bước (đổi sang đơn vị đơn giá) × đơn giá.

    Trả `{sl, don_vi, tien, dien_giai}` hoặc `{thieu, ly_do}` — cùng hình dạng với các hàm trên để
    phía gọi chỉ cần kiểm `"tien" in kq`.
    """
    kq = doi_theo_quy_cach(sl_buoc, don_vi_buoc, don_vi_gia, quy_cach, dvs, cap_rows)
    if "gia_tri" not in kq:
        return kq
    tien = round(kq["gia_tri"] * _f(don_gia))
    return {
        "sl": kq["gia_tri"],
        "don_vi": kq["don_vi"],
        "tien": float(tien),
        "dien_giai": f"{kq['dien_giai']} × {_tien(don_gia)} đ/{kq['don_vi']} = {_tien(tien)} đ",
    }
