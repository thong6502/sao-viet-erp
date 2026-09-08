"""SỔ CHI TIẾT CÔNG NỢ theo từng đối tượng — docs/prd-bao-cao-cong-no.md §5.1.

Đây là thứ sổ tổng hợp KHÔNG trả lời được: *"PS Nợ 304.500.000 của NCC này gồm những phiếu chi
nào?"*. Chủ chốt 05/09/2026 chỉ đúng chỗ thiếu: tab "Chi tiết đơn & đợt" chỉ liệt kê ĐỢT GIAO
(bên Có), còn phiếu chi (bên Nợ) bị nén thành một con số `paid_amount`.

Bất biến sống còn của file này — **ĐỐI CHIẾU HAI SỔ**: luỹ kế dòng cuối của sổ chi tiết phải bằng
đúng ô "Dư cuối kỳ" của chính đối tượng đó bên sổ tổng hợp. Hai bên đọc chung một luồng chứng từ
(`_chung_tu_phai_*`), nên lệch nhau nghĩa là có chứng từ rơi mất ở một bên — và đó là loại lỗi kế
toán chỉ phát hiện ra lúc ngồi đối chiếu với NCC, tức là quá muộn.
"""
from __future__ import annotations

from tests.test_bao_cao_cong_no import _bao_cao, _dong, _ngay
from tests.test_payables_api import (
    _da_mua,
    _dong_dau_tien,
    _don,
    _ghi_dot,
    _headers,
    _phieu_chi,
    _supplier,
    _token_vai,
)


def _so_ct(client, headers, ben: str, *, doi_tuong_id=None, tu: str, den: str, expect: int = 200):
    params = {"tu_ngay": tu, "den_ngay": den}
    if doi_tuong_id is not None:
        params["doi_tuong_id"] = doi_tuong_id
    r = client.get(
        f"/api/accounting/reports/{ben}/so-chi-tiet", params=params, headers=headers
    )
    assert r.status_code == expect, r.text
    return r.json()


def _khop_so_tong_hop(client, headers, ben: str, *, ten_chua: str, tu: str, den: str) -> dict:
    """⭐ Bài đối chiếu: mở sổ chi tiết đúng đối tượng của một dòng trong sổ tổng hợp, rồi soi
    xem đầu kỳ · phát sinh · cuối kỳ của hai bên có khớp từng cột không."""
    tong = _bao_cao(client, headers, ben, tu=tu, den=den)
    dong = _dong(tong, ten_chua)
    so = _so_ct(client, headers, ben, doi_tuong_id=dong["doi_tuong_id"], tu=tu, den=den)
    for cot in ("dau_no", "dau_co", "ps_no", "ps_co", "cuoi_no", "cuoi_co"):
        assert so[cot] == dong[cot], (
            f"cột {cot} lệch giữa sổ chi tiết ({so[cot]}) và sổ tổng hợp ({dong[cot]})"
        )
    return so


# ══ Chỗ chủ chốt báo thiếu: PHIẾU CHI phải hiện thành dòng riêng ═══════════════════════════════


def test_phieu_chi_hien_thanh_dong_rieng_ben_no(client):
    """Trước bản này chỉ thấy đợt giao; tiền đã trả bị nén vào một số gộp, không tra được phiếu."""
    headers = _headers(client)
    ncc = _supplier(client, headers, name="NCC SoCT Chi")
    don = _don(client, headers, ncc["id"])
    _da_mua(client, headers, don["id"])
    dot = _ghi_dot(
        client, headers, don["id"],
        lines=[{"purchase_request_line_id": _dong_dau_tien(don), "quantity": 400}],
        ngay=_ngay(10),
    )  # 400 × 2.200 = 880.000 → bên CÓ
    _phieu_chi(
        client, headers, don["id"], 300_000,
        stage="final", delivery_id=dot["deliveries"][0]["id"],
    )

    so = _khop_so_tong_hop(
        client, headers, "payables", ten_chua="NCC SoCT Chi", tu=_ngay(30), den=_ngay(0)
    )

    loai = [d["loai"] for d in so["dong"]]
    assert "dot_giao" in loai, "thiếu dòng hàng về"
    assert "phieu_chi" in loai, "PHIẾU CHI vẫn không hiện thành dòng — đúng lỗi đang sửa"

    giao = next(d for d in so["dong"] if d["loai"] == "dot_giao")
    chi = next(d for d in so["dong"] if d["loai"] == "phieu_chi")
    assert (giao["no"], giao["co"]) == (0, 880_000), "hàng về phải nằm bên CÓ"
    assert (chi["no"], chi["co"]) == (300_000, 0), "phiếu chi phải nằm bên NỢ"
    assert chi["so_ct"], "phiếu chi phải có số chứng từ để tra"
    assert (so["cuoi_no"], so["cuoi_co"]) == (0, 580_000), "880.000 − 300.000 còn nợ 580.000"


def test_luy_ke_chay_dung_theo_tung_dong(client):
    """Luỹ kế = số dư SAU khi ghi chứng từ đó. Dòng cuối chính là dư cuối kỳ."""
    headers = _headers(client)
    ncc = _supplier(client, headers, name="NCC SoCT LuyKe")
    don = _don(client, headers, ncc["id"])
    _da_mua(client, headers, don["id"])
    dot = _ghi_dot(
        client, headers, don["id"],
        lines=[{"purchase_request_line_id": _dong_dau_tien(don), "quantity": 400}],
        ngay=_ngay(10),
    )
    _phieu_chi(
        client, headers, don["id"], 200_000,
        stage="final", delivery_id=dot["deliveries"][0]["id"],
    )

    so = _so_ct(
        client, headers, "payables",
        doi_tuong_id=ncc["id"], tu=_ngay(30), den=_ngay(0),
    )
    assert len(so["dong"]) == 2

    # Cộng tay lại đúng thứ tự để chắc luỹ kế không phải số bịa.
    luy = so["dau_no"] - so["dau_co"]
    for d in so["dong"]:
        luy += d["no"] - d["co"]
        assert (d["luy_ke_no"], d["luy_ke_co"]) == ((luy, 0) if luy > 0 else (0, -luy)), d
    assert so["dong"][-1]["luy_ke_co"] == so["cuoi_co"], "dòng cuối phải là dư cuối kỳ"


def test_chung_tu_truoc_ky_gom_vao_so_du_dau_ky_khong_thanh_dong(client):
    """Sổ chi tiết mở đầu bằng SỐ DƯ ĐẦU KỲ — chứng từ cũ nằm trong đó, không liệt kê lại."""
    headers = _headers(client)
    ncc = _supplier(client, headers, name="NCC SoCT DauKy")
    don = _don(client, headers, ncc["id"])
    _da_mua(client, headers, don["id"])
    _ghi_dot(
        client, headers, don["id"],
        lines=[{"purchase_request_line_id": _dong_dau_tien(don), "quantity": 400}],
        ngay=_ngay(20),
    )

    so = _khop_so_tong_hop(
        client, headers, "payables", ten_chua="NCC SoCT DauKy", tu=_ngay(10), den=_ngay(0)
    )
    assert (so["dau_no"], so["dau_co"]) == (0, 880_000), "hàng về trước kỳ ⇒ dư đầu kỳ bên Có"
    assert so["dong"] == [], "chứng từ trước kỳ KHÔNG được liệt kê lại trong kỳ"
    assert (so["cuoi_no"], so["cuoi_co"]) == (0, 880_000)


def test_chung_tu_sau_ky_khong_lot_vao_so(client):
    headers = _headers(client)
    ncc = _supplier(client, headers, name="NCC SoCT SauKy")
    don = _don(client, headers, ncc["id"])
    _da_mua(client, headers, don["id"])
    _ghi_dot(
        client, headers, don["id"],
        lines=[{"purchase_request_line_id": _dong_dau_tien(don), "quantity": 400}],
        ngay=_ngay(0),
    )

    so = _so_ct(
        client, headers, "payables",
        doi_tuong_id=ncc["id"], tu=_ngay(60), den=_ngay(30),
    )
    assert so["dong"] == []
    assert (so["dau_no"], so["dau_co"], so["cuoi_no"], so["cuoi_co"]) == (0, 0, 0, 0)


def test_dong_sap_theo_ngay(client):
    headers = _headers(client)
    ncc = _supplier(client, headers, name="NCC SoCT ThuTu")
    don = _don(client, headers, ncc["id"], quantity=2000)
    _da_mua(client, headers, don["id"])
    _ghi_dot(
        client, headers, don["id"],
        lines=[{"purchase_request_line_id": _dong_dau_tien(don), "quantity": 300}],
        ngay=_ngay(20),
    )
    _ghi_dot(
        client, headers, don["id"],
        lines=[{"purchase_request_line_id": _dong_dau_tien(don), "quantity": 200}],
        ngay=_ngay(5),
    )

    so = _so_ct(
        client, headers, "payables",
        doi_tuong_id=ncc["id"], tu=_ngay(30), den=_ngay(0),
    )
    ngays = [d["ngay"] for d in so["dong"]]
    assert ngays == sorted(ngays), f"sổ phải xếp theo ngày: {ngays}"


# ══ TK 131 — phía phải thu cũng phải liệt kê được chứng từ ═════════════════════════════════════


def test_phai_thu_hoa_don_ben_no_phieu_thu_ben_co(client):
    """Đối xứng với 331: hoá đơn bán làm nợ TĂNG (Nợ), phiếu thu làm nợ GIẢM (Có)."""
    from tests.test_sales_invoices_api import _invoice_payload, _sales_order

    headers = _headers(client)
    # `_invoice_payload` ghi ngày hoá đơn = HÔM NAY, nên kỳ phải ôm tới hôm nay.
    order_id, khach_id = _sales_order(suffix="SOCT1")
    r = client.post(
        "/api/accounting/sales-invoices",
        json=_invoice_payload(order_id, number="79000001", amount=400_000),
        headers=headers,
    )
    assert r.status_code == 201, r.text

    tong = _bao_cao(client, headers, "receivables", tu=_ngay(30), den=_ngay(0))
    dong_kh = next(d for d in tong["items"] if d["doi_tuong_id"] == khach_id)
    so = _so_ct(
        client, headers, "receivables",
        doi_tuong_id=khach_id, tu=_ngay(30), den=_ngay(0),
    )

    assert so["tk"] == "131"
    hd = next(d for d in so["dong"] if d["loai"] == "hoa_don")
    assert (hd["no"], hd["co"]) == (400_000, 0), "hoá đơn bán phải nằm bên NỢ"
    for cot in ("dau_no", "dau_co", "ps_no", "ps_co", "cuoi_no", "cuoi_co"):
        assert so[cot] == dong_kh[cot], f"cột {cot} lệch với sổ tổng hợp"


# ══ Phân quyền ════════════════════════════════════════════════════════════════════════════════


def test_so_chi_tiet_doi_quyen_bao_cao(client):
    """Cùng ô quyền với chính sổ tổng hợp — `bao_cao_cong_no` (tách 04/09/2026)."""
    thieu = _token_vai("soct-khong-quyen", module="cong_no_phai_tra", can_read=True)
    r = client.get(
        "/api/accounting/reports/payables/so-chi-tiet",
        params={"tu_ngay": _ngay(30), "den_ngay": _ngay(0)},
        headers={"Authorization": f"Bearer {thieu}"},
    )
    assert r.status_code == 403, r.text

    du = _token_vai("soct-co-quyen", module="bao_cao_cong_no", can_read=True)
    r2 = client.get(
        "/api/accounting/reports/payables/so-chi-tiet",
        params={"tu_ngay": _ngay(30), "den_ngay": _ngay(0)},
        headers={"Authorization": f"Bearer {du}"},
    )
    assert r2.status_code == 200, r2.text
