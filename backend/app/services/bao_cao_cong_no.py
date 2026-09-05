"""Báo cáo TỔNG HỢP CÔNG NỢ theo kỳ — docs/prd-bao-cao-cong-no.md §5.1.

Khác hẳn màn Công nợ đang có, đừng nhầm hai thứ:

  • Màn Công nợ trả lời *"HÔM NAY ai nợ mình bao nhiêu, đòi ai trước"* — ảnh chụp tại hôm nay.
  • Báo cáo này trả lời *"TRONG KỲ [tu_ngay, den_ngay] mỗi đối tượng phát sinh bao nhiêu, đầu kỳ
    bao nhiêu, cuối kỳ còn bao nhiêu"* — sổ tổng hợp theo kỳ, để đối chiếu với MISA.

**KHÔNG CHỐT KỲ** (§❶bis). Không có bảng lưu số dư cuối kỳ, không có nút "Chốt". Chọn khoảng ngày
nào cũng tính lại từ chứng từ. Tồn kho phải chốt vì là số *đi đếm mới biết*; công nợ thì *cộng lại
là ra*, y như sao kê ngân hàng.

SỐ DƯ ĐẦU KỲ dựng THUẦN từ chứng từ trong hệ: mọi thứ có ngày trước `tu_ngay` gom vào ngăn đầu
kỳ. KHÔNG có chỗ khai tay nợ cũ — màn nhập số dư đầu kỳ từ file MISA đã BỎ 04/09/2026 (*"mình
không cần làm cho họ đâu"*). Hệ quả cần biết: nợ phát sinh TRƯỚC khi dùng hệ này thì báo cáo
không thấy, nên dư cuối kỳ hụt đúng bằng phần đó.

QUY ƯỚC NỘI BỘ: mọi phép cộng chạy trên **`net` = dư Nợ − dư Có** (chuẩn kế toán), tới lúc trả ra
mới tách hai cột bằng `_hai_cot`. Nhờ thế 131 và 331 dùng CHUNG một bộ máy dù dấu ngược nhau:

  • 131 phải thu: bán ra `+net` (tăng Nợ) · thu tiền `−net`.
  • 331 phải trả: hàng về `−net` (tăng Có) · trả tiền `+net`.

Số âm KHÔNG BAO GIỜ lọt ra ngoài: âm thì nhảy sang cột bên kia. Đó là luật của sổ Nợ/Có, và cũng
là cách một khách ứng trước tiền hiện lên đúng ở cột Có của TK 131.
"""
from __future__ import annotations

from datetime import date, datetime

from ..models.accounting import RECEIPT_SOURCE_PURCHASE, SALES_INVOICE_ISSUED
from .purchase_service import han_tra_dot, phan_bo_du_dot, phan_bo_tien_dot

#: Tài khoản công nợ in ra cột "TK công nợ". Cứng, vì hệ CHƯA có danh mục tài khoản kế toán —
#: `debit_account`/`credit_account` trên phiếu là chữ nhập tay (§❺). Khi nào có danh mục thật thì
#: mới lấy động; in cứng ở đây vẫn đúng với mọi dòng của hai báo cáo này.
TK_PHAI_THU = "131"
TK_PHAI_TRA = "331"

#: Khoá của dòng gom mọi khoản KHÔNG truy được về đối tượng nào (§❸ phương án A). Dùng `None` làm
#: id thật nên phải có khoá riêng để gom — không giấu tiền đi đâu cả, nhưng cũng không bịa ra một
#: khách/NCC không tồn tại.
KHONG_GAN_ID = None
KHONG_GAN_TEN_THU = "(Thu khác — không gắn khách hàng)"
KHONG_GAN_TEN_TRA = "(Chi khác — không gắn nhà cung cấp)"


def _ro_rong() -> dict[str, dict[str, int]]:
    """Sáu rổ rỗng. Đối tượng không nợ gì vẫn phải đủ 6 khoá — thiếu khoá là giao diện đọc ra
    `undefined` rồi in "NaN đ"."""
    from .accounting_service import AGING_KEYS

    return {k: {"amount": 0, "count": 0} for k in AGING_KEYS}


def _bo_ro(o: dict, tien: int, han: date | None, den_ngay: date) -> None:
    """Ném một khoản còn nợ vào đúng rổ tuổi, TÍNH TẠI `den_ngay`.

    ⚠️ Tại `den_ngay`, KHÔNG phải tại hôm nay — đó là toàn bộ lý do rổ tuổi ở báo cáo khác rổ tuổi
    ở màn Công nợ. Chọn kỳ đến 31/08 thì phải ra tuổi nợ đúng như tại 31/08, và in lại tháng sau
    vẫn ra đúng con số đó. Màn Công nợ neo vào hôm nay nên không làm được việc này.

    Mốc rổ lấy từ `AGING_BUCKETS` — đừng gõ lại số ngày ở đâu khác.
    """
    from .accounting_service import ro_tuoi

    if tien <= 0:
        return
    tre = (den_ngay - han).days if han is not None and den_ngay > han else 0
    khoa = ro_tuoi(tre)
    o["aging"][khoa]["amount"] += tien
    o["aging"][khoa]["count"] += 1


def _ro_ra_danh_sach(ro: dict[str, dict[str, int]]) -> list[dict]:
    """Bộ rổ → danh sách CÓ NHÃN, đúng thứ tự già dần. Giao diện chỉ việc in, không tự đặt tên."""
    from .accounting_service import AGING_BUCKETS

    return [
        {
            "key": b["key"],
            "label": b["label"],
            "amount": ro[b["key"]]["amount"],
            "count": ro[b["key"]]["count"],
        }
        for b in AGING_BUCKETS
    ]


def _hai_cot(net: int) -> tuple[int, int]:
    """`net` (Nợ − Có) → `(du_no, du_co)`. Đúng một trong hai khác 0."""
    return (net, 0) if net > 0 else (0, -net)


def ngay_chi(v) -> date:
    """Ngày tiền THỰC SỰ rời két. Bản sao có chủ đích của `AccountingService._ngay_chi`.

    Phải giống hệt nó: hai nơi chọn ngày khác nhau cho cùng một phiếu là báo cáo và màn công nợ
    cãi nhau, mà không ai biết bên nào đúng.
    """
    return v.paid_at.date() if v.paid_at is not None else v.voucher_date


class _Gom:
    """Máy cộng cho MỘT báo cáo: mỗi đối tượng một ô ba ngăn (đầu kỳ · phát sinh · cuối kỳ)."""

    def __init__(self, tu_ngay: date, den_ngay: date, tk: str, ten_khong_gan: str) -> None:
        self.tu_ngay = tu_ngay
        self.den_ngay = den_ngay
        self.tk = tk
        self.ten_khong_gan = ten_khong_gan
        self.o: dict[int | None, dict] = {}

    def muc(self, doi_tuong_id: int | None, ten: str | None, ma: str | None = None) -> dict:
        o = self.o.get(doi_tuong_id)
        if o is None:
            o = {
                "doi_tuong_id": doi_tuong_id,
                "ma": ma,
                "ten": (ten or "").strip() or self.ten_khong_gan,
                "tk": self.tk,
                # `net` cộng dồn; tách hai cột ở phút chót trong `ket_qua()`.
                "_dau": 0,
                "_ps_no": 0,
                "_ps_co": 0,
                "aging": _ro_rong(),
            }
            self.o[doi_tuong_id] = o
        elif ma and not o["ma"]:
            o["ma"] = ma
        return o

    def cong(self, o: dict, ngay: date, net: int) -> None:
        """Ném một chứng từ vào đúng ngăn: trước kỳ → đầu kỳ · trong kỳ → phát sinh · sau kỳ → bỏ."""
        if not net:
            return
        if ngay < self.tu_ngay:
            o["_dau"] += net
        elif ngay <= self.den_ngay:
            if net > 0:
                o["_ps_no"] += net
            else:
                o["_ps_co"] += -net
        # ngày > den_ngay: ngoài kỳ, không thuộc báo cáo này.

    def ket_qua(self, *, an_dong_trong: bool = True) -> list[dict]:
        ra: list[dict] = []
        for o in self.o.values():
            dau, ps_no, ps_co = o["_dau"], o["_ps_no"], o["_ps_co"]
            cuoi = dau + ps_no - ps_co
            if an_dong_trong and not (dau or ps_no or ps_co or cuoi):
                continue
            dau_no, dau_co = _hai_cot(dau)
            cuoi_no, cuoi_co = _hai_cot(cuoi)
            ra.append(
                {
                    "doi_tuong_id": o["doi_tuong_id"],
                    "ma": o["ma"],
                    "ten": o["ten"],
                    "tk": o["tk"],
                    "dau_no": dau_no,
                    "dau_co": dau_co,
                    "ps_no": ps_no,
                    "ps_co": ps_co,
                    "cuoi_no": cuoi_no,
                    "cuoi_co": cuoi_co,
                    "aging": o["aging"],
                }
            )
        # Dòng "không gắn đối tượng" luôn xuống CUỐI: nó không phải một đối tượng thật, để nó lẫn
        # giữa danh sách sắp theo tên là gây hiểu nhầm rằng hệ có một khách tên như thế.
        ra.sort(key=lambda r: (r["doi_tuong_id"] is None, (r["ten"] or "").lower()))
        return ra


def _tong(items: list[dict]) -> dict:
    """Dòng TỔNG CỘNG. Cộng thẳng từng cột chứ KHÔNG cộng `net` rồi tách lại.

    Cố ý: nếu tách lại thì một khách dư Nợ 10 và một khách dư Có 10 sẽ triệt tiêu thành 0/0, trong
    khi sổ phải ghi rõ "10 bên Nợ, 10 bên Có". Bản xuất của MISA cũng cộng theo cột (tổng phải thu
    cuối kỳ của họ: Nợ 36,1 tỷ VÀ Có 4,5 tỷ cùng lúc).
    """
    cot = ("dau_no", "dau_co", "ps_no", "ps_co", "cuoi_no", "cuoi_co")
    return {"so_dong": len(items), **{k: sum(i[k] for i in items) for k in cot}}


# ══════════════════════════════════════════════════════════════════════════════════
# DÒNG CHỨNG TỪ — nguồn DUY NHẤT cho cả sổ tổng hợp lẫn SỔ CHI TIẾT (§5.1)
# ══════════════════════════════════════════════════════════════════════════════════
#
# Vì sao phải gom về một chỗ: sổ chi tiết là thứ kế toán mở ra để giải thích con số của sổ tổng
# hợp ("PS Nợ 304.500.000 gồm phiếu nào?"). Nếu hai bên tự đi hỏi chứng từ theo đường riêng thì
# chỉ cần lệch một luật ngày (vd phiếu chi lấy `voucher_date` thay vì `paid_at`) là luỹ kế cuối sổ
# chi tiết không khớp dư cuối kỳ — mà lúc đó không ai biết bên nào sai. Cùng một danh sách thì
# không thể lệch, và `test_bao_cao_cong_no.py` còn canh thêm bằng bài đối chiếu hai bên.
#
# Mỗi phần tử: `net` > 0 → ghi cột NỢ · `net` < 0 → ghi cột CÓ (quy ước ở đầu file).


def _so_hoa_don(hd) -> str:
    """Số hiển thị của hoá đơn bán. Chưa điền số thì lùi về id — sổ không được có dòng trống số."""
    so = (hd.invoice_number or "").strip()
    ky_hieu = (getattr(hd, "invoice_symbol", None) or "").strip()
    if so:
        return f"{ky_hieu} {so}".strip()
    return f"HĐ #{hd.id}"


def _ncc_cua_phieu_chi(v) -> int | None:
    if v.supplier_id is not None:
        return v.supplier_id
    return v.purchase_request.supplier_id if v.purchase_request is not None else None


def _ncc_cua_hoan(p) -> int | None:
    v = p.payment_voucher
    return _ncc_cua_phieu_chi(v) if v is not None else None


def _chung_tu_phai_thu(hoa_don, phieu, khach_don, ma_khach) -> list[dict]:
    """TK 131: hoá đơn bán → NỢ (khách nợ thêm) · phiếu thu → CÓ (khách trả bớt)."""

    def _dt(kh_id: int | None, ten_lui: str | None) -> dict:
        k = ma_khach.get(kh_id) if kh_id else None
        return {
            "doi_tuong_id": kh_id,
            "ten": (k.name if k else None) or ten_lui,
            "ma": k.code if k else None,
        }

    ra: list[dict] = []
    for hd in hoa_don:
        ra.append({
            **_dt(hd.customer_id, hd.customer_name_snapshot),
            "ngay": hd.invoice_date,
            "loai": "hoa_don",
            "so_ct": _so_hoa_don(hd),
            "dien_giai": "Hoá đơn bán hàng",
            "luc": getattr(hd, "created_at", None),
            "net": int(hd.amount_vnd),
        })
    for p in phieu:
        if p.source_type == RECEIPT_SOURCE_PURCHASE:
            continue  # tiền NCC trả lại — thuộc 331, không phải 131.
        kh_id = None
        if p.sales_invoice is not None:
            kh_id = p.sales_invoice.customer_id
        elif p.order_id is not None:
            kh_id = khach_don.get(p.order_id)
        ra.append({
            **_dt(kh_id, p.customer_name_snapshot),
            "ngay": p.receipt_date,
            "loai": "phieu_thu",
            "so_ct": p.code,
            "dien_giai": (p.content or "").strip() or "Khách trả tiền",
            "luc": getattr(p, "received_at", None) or getattr(p, "created_at", None),
            "net": -int(p.amount_vnd),
        })
    return ra


def _chung_tu_phai_tra(don, chi, hoan, ma_ncc, *, den_ngay: date) -> list[dict]:
    """TK 331: đợt giao → CÓ (nợ tăng) · phiếu chi → NỢ (nợ giảm) · NCC hoàn tiền → CÓ."""

    def _dt(ncc_id: int | None, ten_lui: str | None) -> dict:
        n = ma_ncc.get(ncc_id) if ncc_id else None
        return {
            "doi_tuong_id": ncc_id,
            "ten": (n.name if n else None) or ten_lui,
            "ma": n.code if n else None,
        }

    ra: list[dict] = []
    for pr in don:
        tien_dot = phan_bo_du_dot(pr)
        for d in getattr(pr, "deliveries", None) or []:
            tien = int(tien_dot.get(d.id, {}).get("amount", 0) or 0)
            if not tien or d.delivery_date > den_ngay:
                continue
            ra.append({
                **_dt(pr.supplier_id, None),
                "ngay": d.delivery_date,
                "loai": "dot_giao",
                # Số ĐỢT TRONG ĐƠN, không phải id bản ghi — cùng bài học đã vá ở
                # `cong_no_chi_tiet_phai_tra` (đợt đầu tiên hiện thành "Đợt #20" vì id là 20).
                "so_ct": f"{pr.code} · Đợt {d.seq_no}",
                "dien_giai": "Hàng đã nhận",
                "luc": getattr(d, "created_at", None),
                "net": -tien,
            })
    for v in chi:
        ra.append({
            **_dt(_ncc_cua_phieu_chi(v), v.supplier_name_snapshot),
            "ngay": ngay_chi(v),
            "loai": "phieu_chi",
            "so_ct": v.code,
            "dien_giai": (v.content or "").strip() or "Chi trả nhà cung cấp",
            # `paid_at` là mốc tiền THẬT SỰ rời két — cùng nguồn `ngay_chi` đang dùng.
            "luc": getattr(v, "paid_at", None),
            "net": int(v.amount_vnd),
        })
    for p in hoan:
        ra.append({
            **_dt(_ncc_cua_hoan(p), p.supplier_name_snapshot),
            "ngay": p.receipt_date,
            "loai": "hoan_tien",
            "so_ct": p.code,
            "dien_giai": (p.content or "").strip() or "Nhà cung cấp hoàn tiền",
            "luc": getattr(p, "received_at", None) or getattr(p, "created_at", None),
            "net": -int(p.amount_vnd),
        })
    return ra


def _nap_phai_thu(repo, *, den_ngay: date) -> tuple[list, list, dict, dict]:
    """Nạp nguyên liệu TK 131 MỘT LẦN. Dùng chung cho sổ tổng hợp và sổ chi tiết — hai bên phải
    nhìn CÙNG một tập chứng từ, không chỉ cùng luật cộng."""
    hoa_don = [
        hd
        for hd in repo.list_sales_invoices(status=SALES_INVOICE_ISSUED)
        if hd.invoice_date <= den_ngay
    ]
    phieu = repo.phieu_thu_cho_bao_cao(den_ngay=den_ngay)
    khach_don = repo.khach_cua_don([p.order_id for p in phieu if p.order_id is not None])
    # Nạp danh mục khách MỘT LẦN cho cả ba nguồn. Trước đó dùng hai bản đồ rời nên khách chỉ có
    # phiếu thu (chưa hoá đơn nào) rơi vào nhánh tên-snapshot và MẤT mã — mà mã chính là thứ để
    # đối chiếu với sổ MISA.
    ma_khach = repo.customers_by_ids(
        {hd.customer_id for hd in hoa_don if hd.customer_id}
        | {p.sales_invoice.customer_id for p in phieu if p.sales_invoice is not None}
        | set(khach_don.values())
    )
    return hoa_don, phieu, khach_don, ma_khach


def _nap_phai_tra(repo, purchases, *, den_ngay: date) -> tuple[list, list, list, dict]:
    """Nạp nguyên liệu TK 331 MỘT LẦN — xem ghi chú ở `_nap_phai_thu`."""
    don = purchases.list_for_payables()
    chi = [v for v in repo.phieu_chi_cho_bao_cao() if ngay_chi(v) <= den_ngay]
    hoan = [
        p
        for p in repo.phieu_thu_cho_bao_cao(den_ngay=den_ngay)
        if p.source_type == RECEIPT_SOURCE_PURCHASE
    ]
    # Nạp danh mục NCC MỘT LẦN cho cả bốn nguồn. Trước đó chỉ lấy tên từ `list_for_payables`, nên
    # NCC chỉ có NỢ CŨ (chưa đơn nào trong hệ) rơi ra dòng mang tên mã MISA thay vì tên thật —
    # NCC chỉ có phiếu chi (chưa đơn nào) từng rơi ra dòng mang tên snapshot thay vì tên thật.
    ma_ncc = repo.ncc_theo_ids(
        {pr.supplier_id for pr in don if pr.supplier_id}
        | {n for n in (_ncc_cua_phieu_chi(v) for v in chi) if n}
        | {n for n in (_ncc_cua_hoan(p) for p in hoan) if n}
    )
    return don, chi, hoan, ma_ncc


def _so_chi_tiet(
    chung_tu: list[dict],
    *,
    doi_tuong_id: int | None,
    tu_ngay: date,
    den_ngay: date,
    tk: str,
    tieu_de: str,
    ten_khong_gan: str,
) -> dict:
    """Sổ chi tiết của MỘT đối tượng: số dư đầu kỳ → từng chứng từ theo ngày → luỹ kế (§5.1).

    Luỹ kế chạy trên `net` rồi mới tách hai cột, y hệt sổ tổng hợp — nên dòng cuối cùng LUÔN bằng
    ô "Dư cuối kỳ" của chính đối tượng đó bên sổ tổng hợp. Đó là chỗ tự kiểm: lệch nhau nghĩa là
    có chứng từ rơi mất, và bài test đối chiếu hai bên sẽ đỏ.

    `doi_tuong_id = None` = dòng gom các khoản KHÔNG truy được về đối tượng nào (§❸).
    """
    cua_ai = [c for c in chung_tu if c["doi_tuong_id"] == doi_tuong_id and c["net"]]

    dau = sum(c["net"] for c in cua_ai if c["ngay"] < tu_ngay)
    trong_ky = sorted(
        (c for c in cua_ai if tu_ngay <= c["ngay"] <= den_ngay),
        # Cùng một ngày thì xếp theo GIỜ ghi nhận (`luc`), rồi tới số chứng từ cho ổn định — in
        # lại sổ phải ra đúng thứ tự cũ, không phụ thuộc thứ tự SQL trả về. So bằng chuỗi ISO để
        # không vấp chuyện datetime có/không mang múi giờ.
        key=lambda c: (
            c["ngay"],
            c["luc"].isoformat() if isinstance(c.get("luc"), datetime) else "",
            c["so_ct"] or "",
        ),
    )

    dau_no, dau_co = _hai_cot(dau)
    luy = dau
    dong: list[dict] = []
    for c in trong_ky:
        luy += c["net"]
        no, co = _hai_cot(c["net"])
        lk_no, lk_co = _hai_cot(luy)
        dong.append({
            "ngay": c["ngay"],
            # Giờ:phút GHI NHẬN (phiếu chi/thu = lúc tiền chạy, còn lại = lúc nhập vào hệ). Ngày
            # nghiệp vụ trong hệ chỉ có NGÀY, không có giờ — nên đây là thứ duy nhất tách được
            # thứ tự của nhiều chứng từ cùng một ngày.
            "luc": c.get("luc"),
            "loai": c["loai"],
            "so_ct": c["so_ct"],
            "dien_giai": c["dien_giai"],
            "no": no,
            "co": co,
            "luy_ke_no": lk_no,
            "luy_ke_co": lk_co,
        })

    cuoi_no, cuoi_co = _hai_cot(luy)
    goc = cua_ai[0] if cua_ai else None
    return {
        "tk": tk,
        "tieu_de": tieu_de,
        "doi_tuong_id": doi_tuong_id,
        "ma": (goc or {}).get("ma"),
        "ten": ((goc or {}).get("ten") or "").strip() or ten_khong_gan,
        "tu_ngay": tu_ngay,
        "den_ngay": den_ngay,
        "dau_no": dau_no,
        "dau_co": dau_co,
        "dong": dong,
        "ps_no": sum(d["no"] for d in dong),
        "ps_co": sum(d["co"] for d in dong),
        "cuoi_no": cuoi_no,
        "cuoi_co": cuoi_co,
    }


# ══════════════════════════════════════════════════════════════════════════════════
# TK 131 — PHẢI THU KHÁCH HÀNG
# ══════════════════════════════════════════════════════════════════════════════════
def tong_hop_phai_thu(repo, *, tu_ngay: date, den_ngay: date) -> dict:
    """Sổ tổng hợp công nợ phải thu (TK 131) cho kỳ `[tu_ngay, den_ngay]`.

    PS Nợ = hoá đơn bán `issued` có `invoice_date` trong kỳ.
    PS Có = phiếu thu `received` có `receipt_date` trong kỳ, truy về khách qua hoá đơn hoặc đơn.

    CỌC ĐƠN HÀNG cũng là PS Có, kể cả khi chưa cấn trừ vào hoá đơn nào — khách đã đưa tiền thì
    131 phải ghi Có. Chính nhánh này làm nên cột "dư cuối kỳ bên Có" (khách ứng trước) mà bản
    xuất MISA vẫn có 4,5 tỷ.

    Phiếu thu `purchase_refund` (NCC hoàn tiền) KHÔNG thuộc 131 — nó là chuyện của 331.
    """
    gom = _Gom(tu_ngay, den_ngay, TK_PHAI_THU, KHONG_GAN_TEN_THU)
    hoa_don, phieu, khach_don, ma_khach = _nap_phai_thu(repo, den_ngay=den_ngay)

    def _muc(kh_id: int | None, ten_lui: str | None) -> dict:
        k = ma_khach.get(kh_id) if kh_id else None
        return gom.muc(kh_id, (k.name if k else None) or ten_lui, k.code if k else None)

    # --- PS Nợ (hoá đơn bán) + PS Có (phiếu thu) ---
    # Đi qua ĐÚNG luồng chứng từ mà sổ chi tiết dùng, không tự lặp lại luật ngày/dấu ở đây.
    for ct in _chung_tu_phai_thu(hoa_don, phieu, khach_don, ma_khach):
        gom.cong(gom.muc(ct["doi_tuong_id"], ct["ten"], ct["ma"]), ct["ngay"], ct["net"])

    # ── PHÂN TUỔI NỢ tại `den_ngay` (§5.3) ────────────────────────────────────────────────
    #
    # Phải tính lại phần CÒN LẠI của từng hoá đơn TÍNH TỚI `den_ngay`, không mượn
    # `remaining_amount` của `_receivable_rows` — số đó là "còn lại tính tới HÔM NAY", nên tiền
    # khách trả SAU kỳ đã bị trừ mất và tuổi nợ của kỳ cũ hoá ra nhẹ đi. In lại kỳ tháng 7 vào
    # tháng 9 mà ra số khác lần in tháng 8 thì báo cáo hết dùng được.
    #
    # Cách cấn trừ y hệt `receivable_rows`: thu ĐÍCH DANH hoá đơn trừ trước, cọc của đơn cấn FIFO
    # theo (ngày hoá đơn, id). Chép luật ở đây là có ý — bản gốc không nhận mốc ngày.
    thu_dich_danh: dict[int, int] = {}
    coc_theo_don: dict[int, int] = {}
    for p in phieu:
        if p.source_type == RECEIPT_SOURCE_PURCHASE:
            continue
        if p.sales_invoice_id is not None:
            thu_dich_danh[p.sales_invoice_id] = (
                thu_dich_danh.get(p.sales_invoice_id, 0) + int(p.amount_vnd)
            )
        elif p.order_id is not None:
            coc_theo_don[p.order_id] = coc_theo_don.get(p.order_id, 0) + int(p.amount_vnd)

    theo_don: dict[int, list] = {}
    for hd in hoa_don:
        theo_don.setdefault(hd.order_id, []).append(hd)

    for don_id, ds in theo_don.items():
        con_coc = coc_theo_don.get(don_id, 0)
        for hd in sorted(ds, key=lambda x: (x.invoice_date, x.id)):
            tien = int(hd.amount_vnd)
            truc_tiep = min(tien, thu_dich_danh.get(hd.id, 0))
            bu_coc = min(con_coc, max(0, tien - truc_tiep))
            con_coc -= bu_coc
            _bo_ro(
                _muc(hd.customer_id, hd.customer_name_snapshot),
                max(0, tien - truc_tiep - bu_coc),
                hd.due_date,
                den_ngay,
            )

    items = gom.ket_qua()
    tong_ro = _ro_rong()
    for o in gom.o.values():
        for k, v in o["aging"].items():
            tong_ro[k]["amount"] += v["amount"]
            tong_ro[k]["count"] += v["count"]

    return {
        "aging": _ro_ra_danh_sach(tong_ro),
        "tk": TK_PHAI_THU,
        "tieu_de": "TỔNG HỢP CÔNG NỢ PHẢI THU",
        "nhan_ma": "Mã khách hàng",
        "nhan_ten": "Tên khách hàng",
        "tu_ngay": tu_ngay,
        "den_ngay": den_ngay,
        "items": items,
        "tong": _tong(items),
    }


# ══════════════════════════════════════════════════════════════════════════════════
# TK 331 — PHẢI TRẢ NGƯỜI BÁN
# ══════════════════════════════════════════════════════════════════════════════════
def tong_hop_phai_tra(repo, purchases, *, tu_ngay: date, den_ngay: date) -> dict:
    """Sổ tổng hợp công nợ phải trả (TK 331) cho kỳ `[tu_ngay, den_ngay]`.

    PS Có = giá trị HÀNG ĐÃ NHẬN, theo `delivery_date` của từng đợt giao (chốt 03/09/2026: ghi nợ
    NCC theo NGÀY HÀNG VỀ, không phải ngày hoá đơn NCC — §5.4). Tiền của đợt lấy từ
    `phan_bo_du_dot`, tức là phần giao VƯỢT số đặt vẫn ghi 0đ, y hệt màn công nợ.

    PS Nợ = phiếu chi `paid`, theo ngày tiền rời két (`paid_at`, không có thì `voucher_date`).

    PS Có (thêm) = phiếu thu `purchase_refund` — NCC hoàn tiền lại thì nợ TĂNG trở lại.
    """
    gom = _Gom(tu_ngay, den_ngay, TK_PHAI_TRA, KHONG_GAN_TEN_TRA)
    don, chi, hoan, ma_ncc = _nap_phai_tra(repo, purchases, den_ngay=den_ngay)

    def _muc(ncc_id: int | None, ten_lui: str | None) -> dict:
        n = ma_ncc.get(ncc_id) if ncc_id else None
        return gom.muc(ncc_id, (n.name if n else None) or ten_lui, n.code if n else None)

    # --- PS Có (hàng đã nhận theo từng ĐỢT GIAO) + PS Nợ (phiếu chi) + PS Có (NCC hoàn tiền) ---
    # Đi qua ĐÚNG luồng chứng từ mà sổ chi tiết dùng, không tự lặp lại luật ngày/dấu ở đây.
    for ct in _chung_tu_phai_tra(don, chi, hoan, ma_ncc, den_ngay=den_ngay):
        gom.cong(gom.muc(ct["doi_tuong_id"], ct["ten"], ct["ma"]), ct["ngay"], ct["net"])

    # ── PHÂN TUỔI NỢ tại `den_ngay` (§5.3) ────────────────────────────────────────────────
    #
    # `phan_bo_tien_dot(..., den_ngay=...)` chỉ đếm tiền đã chi TỚI HẾT ngày đó, nên phần còn nợ
    # của từng đợt là con số ĐÚNG TẠI MỐC ĐANG XEM. Hạn trả lấy bằng `han_tra_dot` — cùng thang
    # 4 bậc mà màn Công nợ đang dùng, không tự đặt luật hạn riêng ở đây.
    for pr in don:
        phan_bo, _, _ = phan_bo_tien_dot(pr, den_ngay=den_ngay)
        for m in phan_bo:
            d = m["delivery"]
            if d.delivery_date > den_ngay:
                continue
            _bo_ro(
                _muc(pr.supplier_id, None),
                int(m["con_no"]),
                han_tra_dot(d, pr.supplier, pr.debt_cutoff_date),
                den_ngay,
            )

    items = gom.ket_qua()
    tong_ro = _ro_rong()
    for o in gom.o.values():
        for k, v in o["aging"].items():
            tong_ro[k]["amount"] += v["amount"]
            tong_ro[k]["count"] += v["count"]

    return {
        "aging": _ro_ra_danh_sach(tong_ro),
        "tk": TK_PHAI_TRA,
        "tieu_de": "TỔNG HỢP CÔNG NỢ PHẢI TRẢ",
        "nhan_ma": "Mã nhà cung cấp",
        "nhan_ten": "Tên nhà cung cấp",
        "tu_ngay": tu_ngay,
        "den_ngay": den_ngay,
        "items": items,
        "tong": _tong(items),
    }


# ══════════════════════════════════════════════════════════════════════════════════
# SỔ CHI TIẾT CÔNG NỢ theo MỘT đối tượng (§5.1) — "thứ kế toán cần khi ngồi đối chiếu với NCC"
# ══════════════════════════════════════════════════════════════════════════════════
def so_chi_tiet_phai_thu(
    repo, *, doi_tuong_id: int | None, tu_ngay: date, den_ngay: date
) -> dict:
    """Sổ chi tiết TK 131 của một khách hàng. `doi_tuong_id=None` = dòng "Thu khác"."""
    hoa_don, phieu, khach_don, ma_khach = _nap_phai_thu(repo, den_ngay=den_ngay)
    return _so_chi_tiet(
        _chung_tu_phai_thu(hoa_don, phieu, khach_don, ma_khach),
        doi_tuong_id=doi_tuong_id,
        tu_ngay=tu_ngay,
        den_ngay=den_ngay,
        tk=TK_PHAI_THU,
        tieu_de="SỔ CHI TIẾT CÔNG NỢ PHẢI THU",
        ten_khong_gan=KHONG_GAN_TEN_THU,
    )


def so_chi_tiet_phai_tra(
    repo, purchases, *, doi_tuong_id: int | None, tu_ngay: date, den_ngay: date
) -> dict:
    """Sổ chi tiết TK 331 của một nhà cung cấp. `doi_tuong_id=None` = dòng "Chi khác"."""
    don, chi, hoan, ma_ncc = _nap_phai_tra(repo, purchases, den_ngay=den_ngay)
    return _so_chi_tiet(
        _chung_tu_phai_tra(don, chi, hoan, ma_ncc, den_ngay=den_ngay),
        doi_tuong_id=doi_tuong_id,
        tu_ngay=tu_ngay,
        den_ngay=den_ngay,
        tk=TK_PHAI_TRA,
        tieu_de="SỔ CHI TIẾT CÔNG NỢ PHẢI TRẢ",
        ten_khong_gan=KHONG_GAN_TEN_TRA,
    )


__all__ = [
    "KHONG_GAN_TEN_THU",
    "KHONG_GAN_TEN_TRA",
    "TK_PHAI_THU",
    "TK_PHAI_TRA",
    "ngay_chi",
    "so_chi_tiet_phai_thu",
    "so_chi_tiet_phai_tra",
    "tong_hop_phai_thu",
    "tong_hop_phai_tra",
]
