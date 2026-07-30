"""Quy đổi đơn vị — HÀM THUẦN, không giữ state, không đụng DB (caller nạp danh mục rồi truyền vào).

Hai loại quy đổi, cố tình tách rời vì bản chất khác nhau:

1. **Cùng họ — thuần số học.** `doi()`: m² ↔ cm², kg ↔ tấn, ram ↔ tờ. Chỉ cần `he_so_goc` của danh
   mục `don_vi_do`, đúng ở mọi nơi mọi lúc.

2. **Khác họ — phải có QUY CÁCH của lệnh.** `doi_theo_quy_cach()`: câu "1 tờ bằng mấy kg" KHÔNG có
   đáp án chung — tờ 65×86 Ford 70 là 0,039 kg, tờ 79×109 Couché 300 là 0,258 kg. Bốn cầu dưới đây
   mỗi cầu khai rõ cần biến gì; **thiếu biến thì trả `thieu`, KHÔNG đoán** — số đoán ra chảy thẳng
   vào tiền khoán và tồn kho.

Cầu luôn nhả ra **đơn vị GỐC của họ đích** (cm² · kg · tờ · con · cuốn), rồi `doi()` đưa tiếp về đơn
vị người ta hỏi (m², tấn…). Nhờ vậy thêm đơn vị mới trong họ không phải sửa cầu.

Mọi kết quả đều kèm `dien_giai` khoe cách tính (`241 tờ × 86,0 × 65,0 = 1.347.190 cm² = 134,7 m²`) —
người đọc kiểm được bằng mắt, và khi số sai thì biết sai ở đâu.
"""
from __future__ import annotations

# --- Mã đơn vị mà CODE tham chiếu (danh mục có thể thêm đơn vị khác thoải mái) ----------------
DV_TO = "to"
DV_RAM = "ram"
DV_CAI = "cai"
DV_CUON = "cuon"
DV_CM2 = "cm2"
DV_M2 = "m2"
DV_KG = "kg"
DV_TAN = "tan"

HO_DIEN_TICH = "dien_tich"
HO_KHOI_LUONG = "khoi_luong"
HO_TO = "to"
# Mọi cách đếm "một thành phẩm xong" (cái · con · cuốn · bộ · hộp) nằm CHUNG một họ, hệ số 1: bước
# lệnh gọi `cai` còn bảng khoán của tổ gọi "cuốn"/"hộp", nhưng đó là cùng một thứ được đếm.
HO_THANH_PHAM = "thanh_pham"

# Biến quy cách mỗi cầu cần — hiện nguyên văn cho người dùng khi thiếu.
NHAN_BIEN = {
    "kho_in_dai": "khổ tờ in (dài)",
    "kho_in_rong": "khổ tờ in (rộng)",
    "gsm": "định lượng giấy (g/m²)",
    "so_con": "số con trên tờ",
}


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


def don_vi_goc_cua_ho(ho: str, dvs: dict[str, dict]) -> dict | None:
    """Đơn vị gốc của họ = dòng có he_so_goc = 1. Không có ⇒ danh mục khai thiếu."""
    ho = (ho or "").strip().lower()
    for d in dvs.values():
        if d["ho"] == ho and abs(d["he_so_goc"] - 1.0) < 1e-9:
            return d
    return None


def doi(gia_tri: float, tu: str, den: str, dvs: dict[str, dict]) -> dict:
    """Đổi trong CÙNG họ. Trả `{gia_tri, don_vi, dien_giai}`; không đổi được thì `{thieu, ly_do}`."""
    tu_k, den_k = (tu or "").strip().lower(), (den or "").strip().lower()
    a, b = dvs.get(tu_k), dvs.get(den_k)
    if a is None or b is None:
        thieu = [x for x, o in ((tu_k, a), (den_k, b)) if o is None]
        return {"thieu": thieu, "ly_do": f"Đơn vị chưa khai trong danh mục: {', '.join(thieu)}."}
    # Cùng đơn vị (kể cả khi một bên gọi bằng mã "to", bên kia bằng tên "tờ") → khỏi phép tính.
    if tu_k == den_k or a["ma"] == b["ma"]:
        return {"gia_tri": _f(gia_tri), "don_vi": b["ten"],
                "dien_giai": f"{_so(gia_tri)} {b['ten']}"}
    if a["ho"] != b["ho"]:
        return {
            "thieu": ["quy_cach"],
            "ly_do": f"{a['ten']} và {b['ten']} khác họ quy đổi — cần quy cách của lệnh "
                     f"(khổ / định lượng / số con) mới đổi được.",
        }
    ket_qua = _f(gia_tri) * a["he_so_goc"] / b["he_so_goc"]
    if abs(a["he_so_goc"] - b["he_so_goc"]) < 1e-9:
        # Hai đơn vị cùng họ, cùng hệ số (cái ↔ cuốn ↔ hộp): chỉ là cách GỌI khác, đừng in "÷ 1".
        return {"gia_tri": ket_qua, "don_vi": b["ten"],
                "dien_giai": f"{_so(gia_tri)} {a['ten']} = {_so(ket_qua)} {b['ten']}"}
    if abs(a["he_so_goc"] - 1.0) < 1e-9:
        dg = f"{_so(gia_tri)} {a['ten']} ÷ {_so(b['he_so_goc'])} = {_so(ket_qua)} {b['ten']}"
    elif abs(b["he_so_goc"] - 1.0) < 1e-9:
        dg = f"{_so(gia_tri)} {a['ten']} × {_so(a['he_so_goc'])} = {_so(ket_qua)} {b['ten']}"
    else:
        dg = (f"{_so(gia_tri)} {a['ten']} × {_so(a['he_so_goc'])} ÷ {_so(b['he_so_goc'])} "
              f"= {_so(ket_qua)} {b['ten']}")
    return {"gia_tri": ket_qua, "don_vi": b["ten"], "dien_giai": dg}


# --- Bốn cầu qua họ khác (cần quy cách của lệnh) -----------------------------------------------
#
# Mỗi cầu: (họ đích) → hàm(gia_tri, quy_cach) trả (giá trị theo ĐƠN VỊ GỐC của họ đích, diễn giải)
# hoặc (None, danh sách biến thiếu).


def _to_sang_cm2(sl: float, qc: dict) -> tuple[float | None, str | list[str]]:
    dai, rong = _f(qc.get("kho_in_dai")), _f(qc.get("kho_in_rong"))
    thieu = [k for k, v in (("kho_in_dai", dai), ("kho_in_rong", rong)) if v <= 0]
    if thieu:
        return None, thieu
    dai_cm, rong_cm = dai / 10.0, rong / 10.0
    val = sl * dai_cm * rong_cm
    return val, f"{_so(sl)} tờ × {_so(dai_cm)} cm × {_so(rong_cm)} cm = {_so(val)} cm²"


def _to_sang_kg(sl: float, qc: dict) -> tuple[float | None, str | list[str]]:
    dai, rong, gsm = _f(qc.get("kho_in_dai")), _f(qc.get("kho_in_rong")), _f(qc.get("gsm"))
    thieu = [k for k, v in (("kho_in_dai", dai), ("kho_in_rong", rong), ("gsm", gsm)) if v <= 0]
    if thieu:
        return None, thieu
    dai_m, rong_m = dai / 1000.0, rong / 1000.0
    val = sl * dai_m * rong_m * gsm / 1000.0
    return val, (f"{_so(sl)} tờ × {_so(dai_m)} m × {_so(rong_m)} m × {_so(gsm)} g/m² ÷ 1.000 "
                 f"= {_so(val)} kg")


def _to_sang_con(sl: float, qc: dict) -> tuple[float | None, str | list[str]]:
    con = _f(qc.get("so_con"))
    if con <= 0:
        return None, ["so_con"]
    val = sl * con
    return val, f"{_so(sl)} tờ × {_so(con)} con/tờ = {_so(val)} con"


# (họ nguồn, họ đích) → cầu. BA cầu, không hơn.
#
# Cố tình KHÔNG có cầu "con → cuốn ÷ số tay": nghe hợp lý nhưng sai bản chất. Bước lệnh đếm `cai`
# nghĩa là đếm THÀNH PHẨM (1.000 cuốn sách / 1.000 thẻ) — chia thêm số tay là ra 200 cuốn, sai 5
# lần. Số tay chỉ liên quan tới TỜ IN (đã xử ở `so_to_per_sp` của engine tính giá), không liên quan
# tới việc đếm thành phẩm ở bước sau xén.
CAU = {
    (HO_TO, HO_DIEN_TICH): _to_sang_cm2,
    (HO_TO, HO_KHOI_LUONG): _to_sang_kg,
    (HO_TO, HO_THANH_PHAM): _to_sang_con,
}


def doi_theo_quy_cach(gia_tri: float, tu: str, den: str, quy_cach: dict | None,
                      dvs: dict[str, dict]) -> dict:
    """Đổi qua họ khác bằng quy cách lệnh. Cùng họ thì rơi về `doi()` cho gọn ở phía gọi."""
    tu_k, den_k = (tu or "").strip().lower(), (den or "").strip().lower()
    a, b = dvs.get(tu_k), dvs.get(den_k)
    if a is None or b is None:
        return doi(gia_tri, tu_k, den_k, dvs)      # trả nguyên lỗi "chưa khai đơn vị"
    if a["ho"] == b["ho"]:
        return doi(gia_tri, tu_k, den_k, dvs)

    cau = CAU.get((a["ho"], b["ho"]))
    if cau is None:
        return {
            "thieu": ["cau"],
            "ly_do": f"Chưa có cách đổi {a['ten']} → {b['ten']} (họ {a['ho']} → {b['ho']}).",
        }
    goc = don_vi_goc_cua_ho(b["ho"], dvs)
    if goc is None:
        return {"thieu": ["don_vi_goc"],
                "ly_do": f"Họ {b['ho']} chưa khai đơn vị gốc (hệ số = 1) trong danh mục."}

    val, dg = cau(_f(gia_tri), quy_cach or {})
    if val is None:
        ten_thieu = [NHAN_BIEN.get(k, k) for k in dg]     # dg = list biến thiếu
        return {"thieu": list(dg),
                "ly_do": f"Lệnh chưa có {', '.join(ten_thieu)} nên không đổi được "
                         f"{a['ten']} → {b['ten']}."}

    # Cầu ra đơn vị GỐC của họ đích; nếu người ta hỏi đơn vị khác trong họ thì đi tiếp bằng hệ số.
    if goc["ma"] == b["ma"]:
        return {"gia_tri": val, "don_vi": b["ten"], "dien_giai": dg}
    buoc2 = doi(val, goc["ma"], b["ma"], dvs)
    if "gia_tri" not in buoc2:
        return buoc2
    return {
        "gia_tri": buoc2["gia_tri"],
        "don_vi": b["ten"],
        "dien_giai": f"{dg} = {_so(buoc2['gia_tri'])} {b['ten']}",
    }


def tien_khoan(sl_buoc: float, don_vi_buoc: str, don_vi_gia: str, don_gia: float,
               quy_cach: dict | None, dvs: dict[str, dict]) -> dict:
    """Tiền khoán DỰ KIẾN của 1 bước = SL bước (đổi sang đơn vị đơn giá) × đơn giá.

    Trả `{sl, don_vi, tien, dien_giai}` hoặc `{thieu, ly_do}` — cùng hình dạng với các hàm trên để
    phía gọi chỉ cần kiểm `"tien" in kq`.
    """
    kq = doi_theo_quy_cach(sl_buoc, don_vi_buoc, don_vi_gia, quy_cach, dvs)
    if "gia_tri" not in kq:
        return kq
    tien = round(kq["gia_tri"] * _f(don_gia))
    return {
        "sl": kq["gia_tri"],
        "don_vi": kq["don_vi"],
        "tien": float(tien),
        "dien_giai": f"{kq['dien_giai']} × {_tien(don_gia)} đ/{kq['don_vi']} = {_tien(tien)} đ",
    }
