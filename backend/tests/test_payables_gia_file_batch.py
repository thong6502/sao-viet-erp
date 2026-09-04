"""Ba việc "họ muốn" ở Công nợ phải trả (04/09/2026):

  1. File hoá đơn đính kèm ở ĐỢT GIAO thì hiện ngay trong bảng đợt của Kế toán — không phải nhảy
     sang màn Thu mua mới xem được ảnh.
  2. Popup "Hàng đã nhận" hiện ĐƠN GIÁ và THÀNH TIỀN của từng mặt hàng, không chỉ số lượng.
  3. Cùng một NCC thì chọn NHIỀU đợt giao, thanh toán MỘT LƯỢT — vẫn ra N phiếu chi riêng
     (mỗi phiếu một đợt, đúng luật cũ), chỉ gộp thao tác nhập liệu.

Dùng lại helper của `test_payables_api.py` — không chép lại luồng dựng đơn/đợt.
"""
from __future__ import annotations

from datetime import date, timedelta

from tests.test_payables_api import (
    _cong_no_ncc,
    _da_mua,
    _dong_dau_tien,
    _ghi_dot,
    _headers,
    _hom_nay,
    _khai_coc,
    _supplier,
    _don,
)

_MIME_ANH = "image/png"
_ANH_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000a4944415478da6360000002000155a2415c00000000"
    "49454e44ae426082"
)


def _dong_dot(cong_no: dict, delivery_id: int) -> dict:
    it = next(x for x in cong_no["items"] if x["delivery_id"] == delivery_id)
    return it


# ══ 2) GIÁ + THÀNH TIỀN của từng mặt hàng trong popup "Hàng đã nhận" ═════════════════════════


def test_dong_hang_co_don_gia_va_thanh_tien(client):
    """⭐ 400 tờ × 2.200đ = 880.000đ — đơn giá và thành tiền phải khớp đúng con số đó."""
    headers = _headers(client)
    ncc = _supplier(client, headers, name="NCC Gia Dong Hang")
    don = _don(client, headers, ncc["id"])
    _da_mua(client, headers, don["id"])
    dot = _ghi_dot(
        client, headers, don["id"],
        lines=[{"purchase_request_line_id": _dong_dau_tien(don), "quantity": 400}],
    )
    cong_no = _cong_no_ncc(client, headers, ncc["id"])
    row = _dong_dot(cong_no, dot["deliveries"][0]["id"])
    assert len(row["lines"]) == 1
    line = row["lines"][0]
    assert line["unit_price"] == 2200
    assert line["thanh_tien"] == 880_000
    assert line["du"] == 0
    assert line["thanh_tien"] == row["amount"], "tổng các dòng phải khớp Giá trị của cả đợt"


def test_giao_vuot_so_dat_thi_du_hien_rieng_khong_lan_vao_thanh_tien(client):
    """⭐ Giao 1000 cho đơn đặt 500: 500 đầu tính tiền, 500 dư = 0đ (chủ chốt 28/08/2026).

    Bẫy: nếu tính thành_tiền bằng `quantity × đơn giá` thay vì dùng phần TÍNH TIỀN thật sự, con
    số sẽ gấp đôi giá trị đơn đã duyệt — đúng lỗ hổng "tặng cả thì lỗ tiền chết" đã vá.
    """
    headers = _headers(client)
    ncc = _supplier(client, headers, name="NCC Giao Vuot")
    don = _don(client, headers, ncc["id"], quantity=500)
    _da_mua(client, headers, don["id"])
    dot = _ghi_dot(
        client, headers, don["id"],
        lines=[{"purchase_request_line_id": _dong_dau_tien(don), "quantity": 1000}],
    )
    cong_no = _cong_no_ncc(client, headers, ncc["id"])
    row = _dong_dot(cong_no, dot["deliveries"][0]["id"])
    line = row["lines"][0]
    assert line["quantity"] == 1000, "số lượng hiện ĐỦ — không giấu phần dư"
    assert line["du"] == 500, "phần vượt phải PHƠI RA, không lặng lẽ biến mất"
    assert line["thanh_tien"] == 500 * 2200, "chỉ 500 cái đầu được tính tiền, không phải 1000"
    assert row["amount"] == 500 * 2200, "giá trị đợt KHÔNG được gấp đôi vì hàng tặng"


# ══ 1) FILE HOÁ ĐƠN đính kèm ở đợt giao hiện trong bảng công nợ ══════════════════════════════


def test_dot_chua_co_file_thi_hoa_don_files_rong(client):
    headers = _headers(client)
    ncc = _supplier(client, headers, name="NCC Chua Co File")
    don = _don(client, headers, ncc["id"])
    _da_mua(client, headers, don["id"])
    dot = _ghi_dot(
        client, headers, don["id"],
        lines=[{"purchase_request_line_id": _dong_dau_tien(don), "quantity": 400}],
    )
    cong_no = _cong_no_ncc(client, headers, ncc["id"])
    row = _dong_dot(cong_no, dot["deliveries"][0]["id"])
    assert row["hoa_don_files"] == []


def test_upload_anh_hoa_don_o_thu_mua_thi_hien_ngay_ben_ke_toan(client):
    """⭐ File đính kèm ở Thu mua (kind=hoa_don, gắn đúng đợt) phải hiện lại ở Công nợ phải trả —
    không bắt kế toán nhảy màn mới xem được ảnh (04/09/2026)."""
    headers = _headers(client)
    ncc = _supplier(client, headers, name="NCC Co File Hoa Don")
    don = _don(client, headers, ncc["id"])
    _da_mua(client, headers, don["id"])
    dot = _ghi_dot(
        client, headers, don["id"],
        lines=[{"purchase_request_line_id": _dong_dau_tien(don), "quantity": 400}],
    )
    delivery_id = dot["deliveries"][0]["id"]

    up = client.post(
        f"/api/purchase-requests/{don['id']}/attachments",
        params={"kind": "hoa_don", "delivery_id": delivery_id},
        files={"file": ("hoa-don.png", _ANH_1PX, _MIME_ANH)},
        headers=headers,
    )
    assert up.status_code == 201, up.text

    cong_no = _cong_no_ncc(client, headers, ncc["id"])
    row = _dong_dot(cong_no, delivery_id)
    assert len(row["hoa_don_files"]) == 1
    f = row["hoa_don_files"][0]
    assert f["file_name"] == "hoa-don.png"
    assert f["file_type"] == _MIME_ANH
    assert f["file_url"]


def test_file_hop_dong_ca_don_khong_lan_vao_hoa_don_cua_dot(client):
    """File hợp đồng (`delivery_id=None`, gắn cả đơn) không được lẫn vào danh sách hoá đơn của
    một đợt cụ thể — hai loại tài liệu khác nhau, treo ở hai chỗ khác nhau."""
    headers = _headers(client)
    ncc = _supplier(client, headers, name="NCC Hop Dong Rieng")
    don = _don(client, headers, ncc["id"])
    _da_mua(client, headers, don["id"])
    dot = _ghi_dot(
        client, headers, don["id"],
        lines=[{"purchase_request_line_id": _dong_dau_tien(don), "quantity": 400}],
    )
    up = client.post(
        f"/api/purchase-requests/{don['id']}/attachments",
        params={"kind": "hop_dong"},
        files={"file": ("hop-dong.png", _ANH_1PX, _MIME_ANH)},
        headers=headers,
    )
    assert up.status_code == 201, up.text

    cong_no = _cong_no_ncc(client, headers, ncc["id"])
    row = _dong_dot(cong_no, dot["deliveries"][0]["id"])
    assert row["hoa_don_files"] == []


# ══ 3) THANH TOÁN NHIỀU ĐỢT MỘT LƯỢT ═════════════════════════════════════════════════════════


def _batch(client, headers, items, expect=201, **shared):
    body = {
        "items": items,
        "voucher_type": "cash",
        "voucher_date": _hom_nay().isoformat(),
        "cash_recipient_name": "Nguyễn Lan",
        "cash_recipient_address": "Hà Nội",
        **shared,
    }
    r = client.post("/api/accounting/payment-vouchers/batch", json=body, headers=headers)
    assert r.status_code == expect, r.text
    return r.json()


def test_thanh_toan_hai_dot_mot_luot_ra_hai_phieu_rieng(client):
    """⭐ Chọn 2 đợt của cùng một NCC → 2 `PaymentVoucher` riêng, mỗi phiếu đúng một đợt."""
    headers = _headers(client)
    ncc = _supplier(client, headers, name="NCC Batch 2 Dot")
    don = _don(client, headers, ncc["id"], quantity=1000)
    _da_mua(client, headers, don["id"])
    dong_id = _dong_dau_tien(don)
    dot1 = _ghi_dot(client, headers, don["id"], lines=[{"purchase_request_line_id": dong_id, "quantity": 300}])
    dot2 = _ghi_dot(client, headers, don["id"], lines=[{"purchase_request_line_id": dong_id, "quantity": 700}])
    d1, d2 = dot1["deliveries"][0]["id"], dot2["deliveries"][1]["id"]

    kq = _batch(
        client, headers,
        items=[
            {"purchase_request_id": don["id"], "delivery_id": d1},
            {"purchase_request_id": don["id"], "delivery_id": d2},
        ],
    )
    assert len(kq["vouchers"]) == 2
    assert {v["delivery_id"] for v in kq["vouchers"]} == {d1, d2}
    assert kq["total_amount"] == 300 * 2200 + 700 * 2200
    for v in kq["vouchers"]:
        assert v["status"] == "paid", "lập phiếu chi = tiền đã ra (Đ1), không có trạng thái chờ"

    # Cả HAI đợt của đơn này đều đã trả hết ⇒ đơn TẤT TOÁN SẠCH ⇒ biến mất hoàn toàn khỏi "Đợt
    # giao còn nợ" (đúng hợp đồng đã có từ trước, không phải hành vi mới của batch — xem
    # `test_coc_la_coc_ca_don_khong_thuoc_dot_nao`). Vế THẬT cần chứng minh — batch trả đúng số
    # tiền, đúng đợt — đã nằm trong assertion trên response `kq["vouchers"]`.
    cong_no = _cong_no_ncc(client, headers, ncc["id"])
    assert all(x["purchase_request_id"] != don["id"] for x in cong_no["items"])


def test_thanh_toan_mot_luot_qua_hai_don_khac_nhau_cung_ncc(client):
    """Batch không giới hạn trong MỘT đơn mua — cùng NCC, khác đơn vẫn gộp một lượt được."""
    headers = _headers(client)
    ncc = _supplier(client, headers, name="NCC Batch 2 Don")
    don_a = _don(client, headers, ncc["id"])
    don_b = _don(client, headers, ncc["id"])
    for d in (don_a, don_b):
        _da_mua(client, headers, d["id"])
    dot_a = _ghi_dot(client, headers, don_a["id"], lines=[{"purchase_request_line_id": _dong_dau_tien(don_a), "quantity": 400}])
    dot_b = _ghi_dot(client, headers, don_b["id"], lines=[{"purchase_request_line_id": _dong_dau_tien(don_b), "quantity": 400}])

    kq = _batch(
        client, headers,
        items=[
            {"purchase_request_id": don_a["id"], "delivery_id": dot_a["deliveries"][0]["id"]},
            {"purchase_request_id": don_b["id"], "delivery_id": dot_b["deliveries"][0]["id"]},
        ],
    )
    assert len(kq["vouchers"]) == 2
    assert {v["purchase_request_code"] for v in kq["vouchers"]} == {don_a["code"], don_b["code"]}


def test_batch_khac_ncc_thi_chan(client):
    """⭐ Chọn nhầm đợt của HAI nhà cung cấp khác nhau ⇒ chặn — đừng để phiếu mang tên NCC A trả
    hộ nợ của NCC B."""
    headers = _headers(client)
    ncc_a = _supplier(client, headers, name="NCC Batch Khac A")
    ncc_b = _supplier(client, headers, name="NCC Batch Khac B")
    don_a = _don(client, headers, ncc_a["id"])
    don_b = _don(client, headers, ncc_b["id"])
    for d in (don_a, don_b):
        _da_mua(client, headers, d["id"])
    dot_a = _ghi_dot(client, headers, don_a["id"], lines=[{"purchase_request_line_id": _dong_dau_tien(don_a), "quantity": 400}])
    dot_b = _ghi_dot(client, headers, don_b["id"], lines=[{"purchase_request_line_id": _dong_dau_tien(don_b), "quantity": 400}])

    kq = _batch(
        client, headers,
        items=[
            {"purchase_request_id": don_a["id"], "delivery_id": dot_a["deliveries"][0]["id"]},
            {"purchase_request_id": don_b["id"], "delivery_id": dot_b["deliveries"][0]["id"]},
        ],
        expect=422,
    )
    assert "cùng một nhà cung cấp" in kq["detail"].lower()

    # KHÔNG phiếu nào được tạo — thẩm định trước, ghi sau.
    cong_no_a = _cong_no_ncc(client, headers, ncc_a["id"])
    assert _dong_dot(cong_no_a, dot_a["deliveries"][0]["id"])["con_no"] == 400 * 2200


def test_batch_dot_trung_lap_thi_chan(client):
    headers = _headers(client)
    ncc = _supplier(client, headers, name="NCC Batch Trung Dot")
    don = _don(client, headers, ncc["id"])
    _da_mua(client, headers, don["id"])
    dot = _ghi_dot(client, headers, don["id"], lines=[{"purchase_request_line_id": _dong_dau_tien(don), "quantity": 400}])
    d1 = dot["deliveries"][0]["id"]

    kq = _batch(
        client, headers,
        items=[
            {"purchase_request_id": don["id"], "delivery_id": d1},
            {"purchase_request_id": don["id"], "delivery_id": d1},
        ],
        expect=422,
    )
    assert "trùng lặp" in kq["detail"].lower()


def test_batch_dot_da_tra_het_thi_chan_khong_dung_phieu_nao(client):
    """Trong 2 đợt chọn, 1 đợt ĐÃ trả hết ⇒ chặn CẢ LƯỢT, không lập lẻ đợt còn lại — thẩm định
    trước, ghi sau."""
    headers = _headers(client)
    ncc = _supplier(client, headers, name="NCC Batch Da Tra Het")
    don = _don(client, headers, ncc["id"], quantity=1000)
    _da_mua(client, headers, don["id"])
    dong_id = _dong_dau_tien(don)
    dot1 = _ghi_dot(client, headers, don["id"], lines=[{"purchase_request_line_id": dong_id, "quantity": 300}])
    dot2 = _ghi_dot(client, headers, don["id"], lines=[{"purchase_request_line_id": dong_id, "quantity": 700}])
    d1, d2 = dot1["deliveries"][0]["id"], dot2["deliveries"][1]["id"]

    # Trả hết đợt 1 trước bằng một phiếu đơn lẻ.
    _batch(client, headers, items=[{"purchase_request_id": don["id"], "delivery_id": d1}])

    kq = _batch(
        client, headers,
        items=[
            {"purchase_request_id": don["id"], "delivery_id": d1},
            {"purchase_request_id": don["id"], "delivery_id": d2},
        ],
        expect=422,
    )
    assert "đã trả hết" in kq["detail"].lower()

    cong_no = _cong_no_ncc(client, headers, ncc["id"])
    assert _dong_dot(cong_no, d2)["con_no"] == 700 * 2200, "đợt 2 KHÔNG được lập phiếu khi cả lượt bị chặn"


def test_batch_rong_thi_chan(client):
    """Danh sách rỗng bị chặn ngay ở tầng schema (`Field(min_length=1)`) — 422 vẫn đúng, chỉ
    khác câu chữ với lỗi tự viết ở tầng service (`AccountingValidationError`)."""
    headers = _headers(client)
    _batch(client, headers, items=[], expect=422)


def test_batch_khong_co_quyen_tao_phieu_chi_thi_403(client):
    """Batch dùng CHUNG quyền với lập phiếu chi đơn lẻ (`phieu_chi:create`) — không đẻ ô quyền
    riêng cho một cách thao tác khác của cùng một việc."""
    from tests.test_payables_api import _token_vai

    headers = _headers(client)
    ncc = _supplier(client, headers, name="NCC Batch Khong Quyen")
    don = _don(client, headers, ncc["id"])
    _da_mua(client, headers, don["id"])
    dot = _ghi_dot(client, headers, don["id"], lines=[{"purchase_request_line_id": _dong_dau_tien(don), "quantity": 400}])

    token = _token_vai("batch_no_perm", module="phieu_chi", can_read=True, can_create=False)
    r = client.post(
        "/api/accounting/payment-vouchers/batch",
        json={
            "items": [{"purchase_request_id": don["id"], "delivery_id": dot["deliveries"][0]["id"]}],
            "voucher_type": "cash",
            "voucher_date": _hom_nay().isoformat(),
            "cash_recipient_name": "X",
            "cash_recipient_address": "Y",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403, r.text
