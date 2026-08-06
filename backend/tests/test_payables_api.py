"""Công nợ phải trả + số thực nhận + lùi 'Đã nhận hàng'.

Ba luật xương sống được canh ở đây:

1. **Không giấu nợ.** Hàng đã về mà kế toán chưa lập phiếu chi thì món nợ đó vẫn phải hiện (rổ
   "chưa vào sổ"). Bỏ rổ này là bảng công nợ sạch bong trong khi vẫn đang nợ NCC — kiểu sai nguy
   hiểm nhất vì nhìn vào tưởng không nợ ai.
2. **Nợ theo hàng THỰC NHẬN**, không theo số đặt. NCC giao 80% mà ghi nợ 100% là kế toán chi thừa.
3. **Lùi 'Đã nhận hàng' phải kéo YCMH khỏi 'Xong'.** Quên vế này thì phòng ban nhìn vào tưởng đủ
   hàng trong khi phiếu đã lùi về 'Đã mua'.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import text

from app.db import SessionLocal
from app.models.role import SCOPE_ALL
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password
from app.services import accounting_service


def _headers(client) -> dict[str, str]:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _needed_date(days: int = 30) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def _supplier(
    client,
    headers,
    *,
    name: str = "NCC Công Nợ",
    item: str = "Giấy Duplex",
    unit: str = "tờ",
) -> dict:
    # Mã số thuế / điện thoại / email phải KHÁC nhau giữa các NCC ⇒ suy từ tên cho mỗi test một bộ
    # riêng, khỏi đụng nhau khi cả file dùng chung một DB.
    dau = f"{abs(hash(name)) % 10**8:08d}"
    response = client.post(
        "/api/suppliers",
        json={
            "name": name,
            "tax_code": f"01{dau}",
            "phone": f"09{dau}",
            "email": f"ncc{dau}@example.com",
            "address": "Hà Nội",
            "contact_name": "Nguyễn Lan",
            "supplier_group": "paper",
            # Dòng phiếu mua phải nằm trong danh mục mặt hàng của NCC, nếu không bị chặn 422.
            "items": [{"item_name": item, "unit": unit, "unit_price": 2200, "vat_percent": 0}],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _token_vai(username: str, *, module: str, **quyen) -> str:
    """Tài khoản có đúng bộ quyền cần thử. Dùng cho các ca 403."""
    db = SessionLocal()
    try:
        users = UserRepository(db)
        u = users.get_by_username(username)
        if u is None:
            bgd = DepartmentRepository(db).get_by_name("Ban giám đốc")
            roles = RoleRepository(db)
            role = roles.create(name=f"Vai {username}", department_id=bgd.id)
            roles.set_permission(role_id=role.id, module_key=module, scope=SCOPE_ALL, **quyen)
            u = users.create(username=username, name=username, password_hash=hash_password("x"))
            users.set_assignment(u, department_id=bgd.id, role_id=role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def _duyet(client, purchase_id: int) -> None:
    """Người lập không tự duyệt được phiếu của mình ⇒ phải có người duyệt riêng."""
    token = _token_vai("cn-approver", module="thu_mua", can_read=True, can_approve=True)
    r = client.post(
        f"/api/purchase-requests/{purchase_id}/approve",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text


def _don(client, headers, supplier_id: int, *, quantity: int = 1000) -> dict:
    """Dựng một PMH đã duyệt. 1000 tờ × 2.200đ = 2.200.000đ."""
    source = client.post(
        "/api/department-purchase-requests",
        json={
            "source_type": "kinh_doanh",
            "purpose": "Mua giấy",
            "needed_date": _needed_date(),
            "lines": [{"item_name": "Giấy Duplex", "unit": "tờ", "quantity": quantity}],
        },
        headers=headers,
    )
    assert source.status_code == 201, source.text
    src = source.json()
    purchase = client.post(
        "/api/purchase-requests",
        json={
            "supplier_id": supplier_id,
            "source_request_ids": [src["id"]],
            "purpose": "Mua giấy",
            "needed_date": _needed_date(),
            "lines": [
                {
                    "item_name": "Giấy Duplex",
                    "unit": "tờ",
                    "quantity": quantity,
                    "expected_unit_price": 2200,
                    "discount_percent": 0,
                    "vat_percent": 0,
                }
            ],
        },
        headers=headers,
    )
    assert purchase.status_code == 201, purchase.text
    body = purchase.json()
    assert client.post(f"/api/purchase-requests/{body['id']}/submit", headers=headers).status_code == 200
    _duyet(client, body["id"])
    body["source_id"] = src["id"]
    return body


def _ve_hang(client, headers, purchase_id: int, *, lines: list[dict] | None = None) -> dict:
    assert client.post(
        f"/api/purchase-requests/{purchase_id}/mark-purchased", headers=headers
    ).status_code == 200
    r = client.post(
        f"/api/purchase-requests/{purchase_id}/mark-received",
        json={"lines": lines or []},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _phieu_chi(client, headers, purchase_id: int, amount: int, *, han: str | None = None) -> dict:
    r = client.post(
        "/api/accounting/payment-vouchers",
        json={
            "purchase_request_id": purchase_id,
            "voucher_type": "cash",
            "payment_stage": "advance",
            "voucher_date": date.today().isoformat(),
            "planned_payment_date": han or (date.today() + timedelta(days=15)).isoformat(),
            "amount": amount,
            "currency": "VND",
            "exchange_rate": 1,
            "content": "Trả tiền giấy",
            "cash_recipient_name": "Nguyễn Lan",
            "cash_recipient_address": "Hà Nội",
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


def _cong_no(client, headers) -> dict:
    r = client.get("/api/accounting/payables", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _cong_no_ncc(client, headers, supplier_id: int) -> dict:
    r = client.get(f"/api/accounting/payables/{supplier_id}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# --- rổ 🔴 "chưa vào sổ" — chống GIẤU NỢ ------------------------------------


def test_hang_ve_chua_lap_phieu_van_hien_la_no(client):
    """Đây là test quan trọng nhất cả file.

    Nếu công nợ chỉ đếm phiếu chi đang chờ chi thì đơn đã về hàng mà kế toán chưa kịp lập phiếu sẽ
    VÔ HÌNH — bảng báo 0 trong khi thực tế đang nợ 2,2 triệu."""
    headers = _headers(client)
    supplier = _supplier(client, headers)
    don = _don(client, headers, supplier["id"])
    _ve_hang(client, headers, don["id"])

    tong = _cong_no(client, headers)
    muc = next(m for m in tong["items"] if m["supplier_id"] == supplier["id"])
    assert muc["unrecorded_amount"] == 2_200_000
    assert muc["waiting_amount"] == 0
    assert muc["total_due"] == 2_200_000
    assert muc["order_count"] == 1

    chi_tiet = _cong_no_ncc(client, headers, supplier["id"])
    assert [x["code"] for x in chi_tiet["unrecorded"]] == [don["code"]]
    assert chi_tiet["waiting"] == []


def test_don_da_duyet_chua_ve_hang_khong_phai_la_no(client):
    """Đặt hàng chưa nợ ai. Tính nợ từ lúc duyệt đơn là đẻ nợ ảo cho hàng còn chưa rời kho NCC."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Chua Ve Hang")
    _don(client, headers, supplier["id"])

    tong = _cong_no(client, headers)
    assert not [m for m in tong["items"] if m["supplier_id"] == supplier["id"]]


def test_lap_phieu_thi_no_chuyen_tu_chua_vao_so_sang_cho_chi(client):
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Chuyen Ro")
    don = _don(client, headers, supplier["id"])
    _ve_hang(client, headers, don["id"])
    _phieu_chi(client, headers, don["id"], 2_200_000)

    muc = next(m for m in _cong_no(client, headers)["items"] if m["supplier_id"] == supplier["id"])
    assert muc["unrecorded_amount"] == 0
    assert muc["waiting_amount"] == 2_200_000
    assert muc["total_due"] == 2_200_000, "chuyển rổ thì TỔNG không được đổi"


# --- trả nhiều đợt: KHÔNG được biến mất khỏi công nợ ------------------------


def test_tra_mot_phan_van_con_no(client):
    """Đơn 2,2tr chi 1tr rồi ⇒ vẫn nợ 1,2tr. Đây là chỗ dễ làm đơn trả dở biến mất khỏi bảng."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Tra Nhieu Dot")
    don = _don(client, headers, supplier["id"])
    _ve_hang(client, headers, don["id"])
    phieu = _phieu_chi(client, headers, don["id"], 1_000_000)
    assert client.post(
        f"/api/accounting/payment-vouchers/{phieu['id']}/mark-paid",
        json={"bank_reference": None},
        headers=headers,
    ).status_code == 200

    muc = next(m for m in _cong_no(client, headers)["items"] if m["supplier_id"] == supplier["id"])
    assert muc["total_due"] == 1_200_000
    assert muc["unrecorded_amount"] == 1_200_000, "phần chưa ai lập phiếu vẫn là nợ chưa vào sổ"


def test_tra_xong_thi_roi_khoi_cong_no_va_vao_ro_da_tra(client):
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Tra Xong")
    don = _don(client, headers, supplier["id"])
    _ve_hang(client, headers, don["id"])
    phieu = _phieu_chi(client, headers, don["id"], 2_200_000)
    assert client.post(
        f"/api/accounting/payment-vouchers/{phieu['id']}/mark-paid",
        json={"bank_reference": None},
        headers=headers,
    ).status_code == 200

    # NCC trả hết vẫn GIỮ dòng trên bảng — nhờ cột "Đã trả trong kỳ". Biến mất là quay lại đúng
    # câu hỏi không trả lời được: "làm sao biết mình đã trả hết".
    muc = next(m for m in _cong_no(client, headers)["items"] if m["supplier_id"] == supplier["id"])
    assert muc["total_due"] == 0
    assert muc["order_count"] == 0, "đơn đã trả xong KHÔNG đếm vào 'Đơn còn nợ'"
    assert muc["paid_in_period"] == 2_200_000

    chi_tiet = _cong_no_ncc(client, headers, supplier["id"])
    assert chi_tiet["unrecorded"] == [] and chi_tiet["waiting"] == []
    # Rổ ✅ liệt kê từng LẦN CHI, cộng lại đúng bằng cột "Đã trả".
    assert [x["purchase_code"] for x in chi_tiet["paid"]] == [don["code"]]
    assert sum(x["amount"] for x in chi_tiet["paid"]) == chi_tiet["paid_in_period"] == 2_200_000


def test_phieu_huy_khong_tinh_la_no(client):
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Phieu Huy")
    don = _don(client, headers, supplier["id"])
    _ve_hang(client, headers, don["id"])
    phieu = _phieu_chi(client, headers, don["id"], 2_200_000)
    assert client.post(
        f"/api/accounting/payment-vouchers/{phieu['id']}/cancel",
        json={"reason": "Lập nhầm"},
        headers=headers,
    ).status_code == 200

    muc = next(m for m in _cong_no(client, headers)["items"] if m["supplier_id"] == supplier["id"])
    assert muc["waiting_amount"] == 0
    assert muc["unrecorded_amount"] == 2_200_000, "huỷ phiếu thì nợ quay về rổ CHƯA VÀO SỔ, không mất"


# --- quá hạn: phải đi qua seam ngày, không phụ thuộc đồng hồ thật -----------


def test_qua_han_dem_theo_seam_ngay(client, monkeypatch):
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Qua Han")
    don = _don(client, headers, supplier["id"])
    _ve_hang(client, headers, don["id"])
    han = date.today() + timedelta(days=15)
    _phieu_chi(client, headers, don["id"], 2_200_000, han=han.isoformat())

    muc = next(m for m in _cong_no(client, headers)["items"] if m["supplier_id"] == supplier["id"])
    assert muc["overdue_amount"] == 0, "chưa tới hạn thì chưa quá hạn"

    # Đẩy 'hôm nay' qua hạn 5 ngày. Chọc SEAM chứ không cắm ngày cứng — cắm cứng là hẹn giờ cho
    # test tự đỏ vài tháng sau.
    monkeypatch.setattr(accounting_service, "_business_today", lambda: han + timedelta(days=5))
    muc = next(m for m in _cong_no(client, headers)["items"] if m["supplier_id"] == supplier["id"])
    assert muc["overdue_amount"] == 2_200_000
    chi_tiet = _cong_no_ncc(client, headers, supplier["id"])
    assert chi_tiet["waiting"][0]["overdue_days"] == 5


# --- số thực nhận ----------------------------------------------------------


def test_khai_nhan_thieu_thi_no_giam_va_chan_lap_phieu_vuot(client):
    """NCC giao 800/1000 tờ ⇒ nợ 1,76tr, không phải 2,2tr. Và kế toán KHÔNG lập nổi phiếu 2,2tr."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Giao Thieu")
    don = _don(client, headers, supplier["id"])
    line_id = don["lines"][0]["id"]
    sau = _ve_hang(
        client, headers, don["id"], lines=[{"line_id": line_id, "received_quantity": 800}]
    )
    assert sau["total_estimate"] == 2_200_000, "giá trị ĐƠN ĐẶT không đổi"
    assert sau["received_total"] == 1_760_000

    muc = next(m for m in _cong_no(client, headers)["items"] if m["supplier_id"] == supplier["id"])
    assert muc["unrecorded_amount"] == 1_760_000

    vuot = client.post(
        "/api/accounting/payment-vouchers",
        json={
            "purchase_request_id": don["id"],
            "voucher_type": "cash",
            "payment_stage": "advance",
            "voucher_date": date.today().isoformat(),
            "amount": 2_200_000,
            "currency": "VND",
            "exchange_rate": 1,
            "content": "Trả đủ tiền đặt",
            "cash_recipient_name": "Nguyễn Lan",
            "cash_recipient_address": "Hà Nội",
        },
        headers=headers,
    )
    assert vuot.status_code in (409, 422), vuot.text
    assert _phieu_chi(client, headers, don["id"], 1_760_000)["amount_vnd"] == 1_760_000


def test_khong_khai_gi_thi_y_nhu_truoc(client):
    """`received_quantity` NULL = nhận đủ. Nhờ vậy phiếu lập trước 05/08/2026 không tự đổi số."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Khong Khai")
    don = _don(client, headers, supplier["id"])
    sau = _ve_hang(client, headers, don["id"])
    assert sau["lines"][0]["received_quantity"] is None
    assert sau["received_total"] == sau["total_estimate"] == 2_200_000


def test_khong_cho_khai_nhan_nhieu_hon_dat(client):
    """Khai vống là chi vượt giá trị đơn giám đốc đã duyệt mà không qua duyệt lại."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Khai Vong")
    don = _don(client, headers, supplier["id"])
    assert client.post(
        f"/api/purchase-requests/{don['id']}/mark-purchased", headers=headers
    ).status_code == 200
    r = client.post(
        f"/api/purchase-requests/{don['id']}/mark-received",
        json={"lines": [{"line_id": don["lines"][0]["id"], "received_quantity": 1200}]},
        headers=headers,
    )
    assert r.status_code == 422, r.text
    assert "nhiều hơn số đặt" in r.json()["detail"]


def test_sua_so_thuc_nhan_xuong_duoi_so_da_cam_ket_bi_chan(client):
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Sua Xuong")
    don = _don(client, headers, supplier["id"])
    line_id = don["lines"][0]["id"]
    _ve_hang(client, headers, don["id"])
    _phieu_chi(client, headers, don["id"], 2_200_000)

    r = client.put(
        f"/api/purchase-requests/{don['id']}/received-quantities",
        json={"lines": [{"line_id": line_id, "received_quantity": 500}]},
        headers=headers,
    )
    assert r.status_code == 409, r.text
    assert "thấp hơn số đã chi" in r.json()["detail"]


def test_sua_so_thuc_nhan_doi_2_can_quyen_duyet(client):
    """Đợt 1 về 600, đợt 2 về nốt ⇒ sửa lên 1000. Nhưng phải là người có quyền duyệt."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Hai Dot")
    don = _don(client, headers, supplier["id"])
    line_id = don["lines"][0]["id"]
    _ve_hang(client, headers, don["id"], lines=[{"line_id": line_id, "received_quantity": 600}])

    token = _token_vai("cn-nhanvien", module="thu_mua", can_read=True, can_update=True)
    tu_choi = client.put(
        f"/api/purchase-requests/{don['id']}/received-quantities",
        json={"lines": [{"line_id": line_id, "received_quantity": 1000}]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert tu_choi.status_code == 403, tu_choi.text

    ok = client.put(
        f"/api/purchase-requests/{don['id']}/received-quantities",
        json={"lines": [{"line_id": line_id, "received_quantity": 1000}]},
        headers=headers,
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["received_total"] == 2_200_000


# --- lùi 'Đã nhận hàng' ----------------------------------------------------


def test_lui_da_nhan_hang_keo_yeu_cau_khoi_xong(client):
    """Vế dễ quên nhất: lùi phiếu mà để YCMH đứng nguyên 'Xong' thì phòng ban tưởng đủ hàng."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Lui")
    don = _don(client, headers, supplier["id"])
    _ve_hang(client, headers, don["id"])
    truoc = client.get(f"/api/department-purchase-requests/{don['source_id']}", headers=headers)
    assert truoc.json()["status"] == "done"

    r = client.post(
        f"/api/purchase-requests/{don['id']}/undo-received",
        json={"reason": "Bấm nhầm, hàng chưa về"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "purchased"
    sau = client.get(f"/api/department-purchase-requests/{don['source_id']}", headers=headers)
    assert sau.json()["status"] == "in_purchase"

    # Lùi rồi thì hết nợ — hàng chưa về thì chưa nợ ai.
    assert not [m for m in _cong_no(client, headers)["items"] if m["supplier_id"] == supplier["id"]]


def test_yeu_cau_hai_phieu_lui_mot_phieu_thi_roi_khoi_xong(client):
    """Một YCMH tách thành HAI phiếu (mỗi NCC một phiếu).

    'Xong' nghĩa là bộ phận đã nhận đủ hàng ⇒ chỉ đúng khi MỌI phiếu đã về. Lùi một phiếu là chưa
    đủ hàng nữa, YCMH phải rời 'Xong' ngay. Đây là ca `_moi_phieu_da_ve_hang` sinh ra để lo, và
    cũng là chỗ dễ viết ẩu thành "cứ lùi là kéo xuống" hoặc "lùi rồi vẫn để nguyên"."""
    headers = _headers(client)
    ncc_a = _supplier(client, headers, name="NCC Tach A")
    ncc_b = _supplier(client, headers, name="NCC Tach B", item="Băng keo", unit="cuộn")
    source = client.post(
        "/api/department-purchase-requests",
        json={
            "source_type": "kinh_doanh",
            "purpose": "Mua hai thứ hai nơi",
            "needed_date": _needed_date(),
            "lines": [
                {"item_name": "Giấy Duplex", "unit": "tờ", "quantity": 500},
                {"item_name": "Băng keo", "unit": "cuộn", "quantity": 500},
            ],
        },
        headers=headers,
    )
    assert source.status_code == 201, source.text
    src_id = source.json()["id"]

    # Gọi API tạo phiếu HAI LẦN không làm được: phiếu đầu giữ chỗ yêu cầu nguồn, lần hai bị chặn.
    # Phải đi đường tạo CẢ MẺ — cũng chính là đường thu mua dùng thật.
    batch = client.post(
        "/api/purchase-requests/batch",
        json={
            "source_request_ids": [src_id],
            "purpose": "Mua hai thứ hai nơi",
            "needed_date": _needed_date(),
            "lines": [
                {
                    "item_name": "Giấy Duplex",
                    "unit": "tờ",
                    "quantity": 500,
                    "expected_unit_price": 2200,
                    "supplier_id": ncc_a["id"],
                },
                {
                    "item_name": "Băng keo",
                    "unit": "cuộn",
                    "quantity": 500,
                    "expected_unit_price": 2200,
                    "supplier_id": ncc_b["id"],
                },
            ],
        },
        headers=headers,
    )
    assert batch.status_code == 201, batch.text
    phieu = batch.json()["items"]
    assert len(phieu) == 2
    phieu_ids = []
    for p in phieu:
        assert client.post(f"/api/purchase-requests/{p['id']}/submit", headers=headers).status_code == 200
        _duyet(client, p["id"])
        phieu_ids.append(p["id"])

    # Về hàng phiếu thứ nhất — YCMH CHƯA xong vì phiếu kia còn chưa về.
    _ve_hang(client, headers, phieu_ids[0])
    giua_chung = client.get(f"/api/department-purchase-requests/{src_id}", headers=headers)
    assert giua_chung.json()["status"] != "done"

    # Về nốt phiếu thứ hai — giờ mới Xong.
    _ve_hang(client, headers, phieu_ids[1])
    assert client.get(
        f"/api/department-purchase-requests/{src_id}", headers=headers
    ).json()["status"] == "done"

    # Lùi MỘT phiếu ⇒ không còn đủ hàng ⇒ YCMH phải rời 'Xong' ngay.
    r = client.post(
        f"/api/purchase-requests/{phieu_ids[1]}/undo-received",
        json={"reason": "Kiểm lại thấy chưa giao"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert client.get(
        f"/api/department-purchase-requests/{src_id}", headers=headers
    ).json()["status"] == "in_purchase"

    # Phiếu còn lại KHÔNG bị đụng tới — và nợ của nó vẫn còn nguyên.
    assert client.get(
        f"/api/purchase-requests/{phieu_ids[0]}", headers=headers
    ).json()["status"] == "received"
    con_no = {m["supplier_id"]: m for m in _cong_no(client, headers)["items"]}
    ncc_con_no = phieu[0]["supplier_id"]
    ncc_da_lui = phieu[1]["supplier_id"]
    assert con_no[ncc_con_no]["total_due"] == 1_100_000, "phiếu còn lại vẫn nợ nguyên"
    assert ncc_da_lui not in con_no, "phiếu đã lùi thì hết nợ — hàng chưa về thì chưa nợ ai"


def test_lui_bi_chan_khi_da_co_phieu_chi_da_chi(client):
    """Tiền đã rời két rồi thì không quay lại khai 'chưa nhận hàng' được."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Lui Da Chi")
    don = _don(client, headers, supplier["id"])
    _ve_hang(client, headers, don["id"])
    phieu = _phieu_chi(client, headers, don["id"], 1_000_000)
    assert client.post(
        f"/api/accounting/payment-vouchers/{phieu['id']}/mark-paid",
        json={"bank_reference": None},
        headers=headers,
    ).status_code == 200

    r = client.post(
        f"/api/purchase-requests/{don['id']}/undo-received",
        json={"reason": "Thử lùi"},
        headers=headers,
    )
    assert r.status_code == 409, r.text
    assert "ĐÃ CHI" in r.json()["detail"]


def test_lui_van_duoc_khi_phieu_moi_dang_cho_chi(client):
    """Phiếu mới lập, tiền chưa ra ⇒ lùi bình thường."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Lui Cho Chi")
    don = _don(client, headers, supplier["id"])
    _ve_hang(client, headers, don["id"])
    _phieu_chi(client, headers, don["id"], 1_000_000)

    r = client.post(
        f"/api/purchase-requests/{don['id']}/undo-received",
        json={"reason": "Hàng trả lại NCC"},
        headers=headers,
    )
    assert r.status_code == 200, r.text


def test_nhan_vien_khong_duoc_lui_va_phai_ghi_ly_do(client):
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Lui Quyen")
    don = _don(client, headers, supplier["id"])
    _ve_hang(client, headers, don["id"])

    token = _token_vai("cn-nhanvien2", module="thu_mua", can_read=True, can_update=True)
    tu_choi = client.post(
        f"/api/purchase-requests/{don['id']}/undo-received",
        json={"reason": "Tôi muốn lùi"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert tu_choi.status_code == 403, tu_choi.text

    thieu_ly_do = client.post(
        f"/api/purchase-requests/{don['id']}/undo-received", json={"reason": "  "}, headers=headers
    )
    assert thieu_ly_do.status_code == 422, thieu_ly_do.text


# --- hạn trả bắt buộc + badge cho phiếu cũ ---------------------------------


def test_lap_phieu_thieu_han_tra_bi_chan(client):
    """Không có hạn thì phiếu KHÔNG BAO GIỜ vào cột Quá hạn — kế toán nhìn bảng thấy sạch trong
    khi đang trễ. Chặn từ gốc."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Thieu Han")
    don = _don(client, headers, supplier["id"])
    _ve_hang(client, headers, don["id"])

    r = client.post(
        "/api/accounting/payment-vouchers",
        json={
            "purchase_request_id": don["id"],
            "voucher_type": "cash",
            "payment_stage": "advance",
            "voucher_date": date.today().isoformat(),
            "amount": 1_000_000,
            "currency": "VND",
            "exchange_rate": 1,
            "content": "Trả tiền giấy",
            "cash_recipient_name": "Nguyễn Lan",
            "cash_recipient_address": "Hà Nội",
        },
        headers=headers,
    )
    assert r.status_code == 422, r.text
    assert "hạn trả tiền" in r.json()["detail"].lower()


def test_phieu_cu_thieu_han_hien_ra_nhung_khong_tinh_qua_han(client):
    """Phiếu lập TRƯỚC khi hạn trả thành bắt buộc: vẫn phải thấy, gắn dấu để đi đặt hạn — nhưng
    KHÔNG được cộng vào cột Quá hạn (không có hạn thì lấy gì mà so)."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Han Cu")
    don = _don(client, headers, supplier["id"])
    _ve_hang(client, headers, don["id"])
    phieu = _phieu_chi(client, headers, don["id"], 1_000_000)

    # Giả lập phiếu cũ: xoá hạn thẳng dưới DB, đúng như dữ liệu có trước 05/08/2026.
    db = SessionLocal()
    try:
        db.execute(
            text("UPDATE payment_vouchers SET planned_payment_date = NULL WHERE id = :i"),
            {"i": phieu["id"]},
        )
        db.commit()
    finally:
        db.close()

    muc = next(m for m in _cong_no(client, headers)["items"] if m["supplier_id"] == supplier["id"])
    assert muc["waiting_amount"] == 1_000_000, "vẫn là nợ chờ chi"
    assert muc["overdue_amount"] == 0, "không có hạn thì không so được, đừng đếm bừa vào quá hạn"

    dong = _cong_no_ncc(client, headers, supplier["id"])["waiting"][0]
    assert dong["planned_payment_date"] is None, "giao diện dựa vào đây để gắn badge Chưa đặt hạn"
    assert dong["overdue_days"] == 0


def test_chot_ngay_chi_chan_cai_vo_ly_khong_chan_qua_khu(client):
    """Quá khứ là HỢP LỆ, cố ý không chặn.

    Hoá đơn về muộn ⇒ phiếu phải mang ngày chi tiêu thật mới vào đúng kỳ kế toán. Hạn trả quá khứ
    cũng vậy: nhập phiếu cho khoản ĐÃ trễ thì giữ đúng ngày để nó hiện đỏ ngay, ép sang tương lai
    là làm giả nợ.

    Chỉ chặn ba thứ vô lý: chứng từ ở tương lai, hoá đơn ở tương lai, hạn trả TRƯỚC ngày chứng từ."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Chot Ngay")
    don = _don(client, headers, supplier["id"])
    _ve_hang(client, headers, don["id"])
    hom_nay = date.today()

    def _lap(**doi):
        payload = {
            "purchase_request_id": don["id"],
            "voucher_type": "cash",
            "payment_stage": "advance",
            "voucher_date": hom_nay.isoformat(),
            "planned_payment_date": (hom_nay + timedelta(days=15)).isoformat(),
            "amount": 100_000,
            "currency": "VND",
            "exchange_rate": 1,
            "content": "Trả tiền giấy",
            "cash_recipient_name": "Nguyễn Lan",
            "cash_recipient_address": "Hà Nội",
        }
        payload.update(doi)
        return client.post("/api/accounting/payment-vouchers", json=payload, headers=headers)

    # HỢP LỆ: cả ngày chứng từ lẫn hạn trả đều ở quá khứ — khoản đã trễ, nhập bù.
    cu = _lap(
        voucher_date=(hom_nay - timedelta(days=40)).isoformat(),
        planned_payment_date=(hom_nay - timedelta(days=10)).isoformat(),
    )
    assert cu.status_code == 201, cu.text
    # Và nó phải hiện QUÁ HẠN ngay, đúng sự thật.
    muc = next(m for m in _cong_no(client, headers)["items"] if m["supplier_id"] == supplier["id"])
    assert muc["overdue_amount"] == 100_000

    tuong_lai = _lap(voucher_date=(hom_nay + timedelta(days=1)).isoformat())
    assert tuong_lai.status_code == 422 and "tương lai" in tuong_lai.json()["detail"]

    hd_tuong_lai = _lap(invoice_date=(hom_nay + timedelta(days=1)).isoformat())
    assert hd_tuong_lai.status_code == 422 and "hóa đơn" in hd_tuong_lai.json()["detail"]

    han_truoc = _lap(
        voucher_date=hom_nay.isoformat(),
        planned_payment_date=(hom_nay - timedelta(days=5)).isoformat(),
    )
    assert han_truoc.status_code == 422, han_truoc.text
    assert "trước ngày chứng từ" in han_truoc.json()["detail"]


# --- số hoá đơn phân biệt các đợt giao -------------------------------------


def test_hoa_don_phan_biet_cac_dot_giao_cua_cung_mot_don(client):
    """Ba đợt giao cùng một đơn ⇒ ba phiếu chi. Thiếu số hoá đơn thì ba dòng trông y hệt nhau."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Nhieu Dot HD")
    don = _don(client, headers, supplier["id"])
    _ve_hang(client, headers, don["id"])
    for so_hd, tien in (("HD-A", 1_000_000), ("HD-B", 1_200_000)):
        r = client.post(
            "/api/accounting/payment-vouchers",
            json={
                "purchase_request_id": don["id"],
                "voucher_type": "cash",
                "payment_stage": "partial",
                "voucher_date": date.today().isoformat(),
                "planned_payment_date": (date.today() + timedelta(days=15)).isoformat(),
                "amount": tien,
                "currency": "VND",
                "exchange_rate": 1,
                "content": f"Trả theo {so_hd}",
                "invoice_number": so_hd,
                "invoice_date": date.today().isoformat(),
                "cash_recipient_name": "Nguyễn Lan",
                "cash_recipient_address": "Hà Nội",
            },
            headers=headers,
        )
        assert r.status_code == 201, r.text

    cho_chi = _cong_no_ncc(client, headers, supplier["id"])["waiting"]
    assert {x["invoice_number"] for x in cho_chi} == {"HD-A", "HD-B"}
    assert all(x["purchase_code"] == don["code"] for x in cho_chi), "cùng một đơn nguồn"


# --- ô tìm lôi được NCC đã im lặng lâu -------------------------------------


def test_o_tim_loi_duoc_ncc_khong_no_khong_giao_dich(client):
    """NCC không nợ gì và không giao dịch trong kỳ thì KHÔNG nằm trên bảng — đúng.

    Nhưng gõ tên vào ô tìm thì phải ra, nếu không lại không tra được "mình đã trả hết chưa"."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Im Lang")
    _don(client, headers, supplier["id"])  # đơn mới duyệt, hàng chưa về ⇒ chưa nợ

    binh_thuong = _cong_no(client, headers)
    assert not [m for m in binh_thuong["items"] if m["supplier_id"] == supplier["id"]]

    r = client.get("/api/accounting/payables?q=Im Lang", headers=headers)
    assert r.status_code == 200, r.text
    muc = next(m for m in r.json()["items"] if m["supplier_id"] == supplier["id"])
    assert muc["total_due"] == 0 and muc["paid_in_period"] == 0


# --- kỳ chỉ cắt phần ĐÃ TRẢ, không cắt nợ ----------------------------------


def test_ky_khong_cat_no_va_xem_duoc_lich_su_cu(client):
    """Hai luật cùng lúc:

    1. **Nợ chưa trả KHÔNG rơi theo kỳ.** Đơn nợ từ nửa năm trước hôm nay vẫn hiện đủ — cách tính
       nợ không hề nhìn ngày, chỉ nhìn hàng đã nhận trừ tiền đã chi.
    2. **Khoản đã chi cũ rơi khỏi kỳ**, nhưng nút "Xem lịch sử cũ hơn" phải với tới được. Không có
       nó thì NCC trả hết từ lâu tra ra "không nợ" mà chẳng thấy đã trả những gì."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Ky Cu")
    don = _don(client, headers, supplier["id"])
    _ve_hang(client, headers, don["id"])
    phieu = _phieu_chi(client, headers, don["id"], 2_200_000)
    assert client.post(
        f"/api/accounting/payment-vouchers/{phieu['id']}/mark-paid",
        json={"bank_reference": None},
        headers=headers,
    ).status_code == 200

    # Đẩy lần chi lùi về 6 tháng trước — ra NGOÀI kỳ 3 tháng.
    db = SessionLocal()
    try:
        cu = date.today() - timedelta(days=180)
        db.execute(
            text("UPDATE payment_vouchers SET paid_at = :t, voucher_date = :d WHERE id = :i"),
            {"t": datetime.combine(cu, datetime.min.time()), "d": cu, "i": phieu["id"]},
        )
        db.commit()
    finally:
        db.close()

    # Ngoài kỳ ⇒ không còn dòng trên bảng, nhưng ô TÌM vẫn lôi ra được.
    assert not [m for m in _cong_no(client, headers)["items"] if m["supplier_id"] == supplier["id"]]
    tim = client.get("/api/accounting/payables?q=Ky Cu", headers=headers)
    muc = next(m for m in tim.json()["items"] if m["supplier_id"] == supplier["id"])
    assert muc["total_due"] == 0 and muc["paid_in_period"] == 0

    # Theo kỳ: rổ đã chi rỗng. Nới toàn bộ lịch sử: thấy lại lần chi 6 tháng trước.
    theo_ky = _cong_no_ncc(client, headers, supplier["id"])
    assert theo_ky["paid"] == [] and theo_ky["all_history"] is False

    r = client.get(
        f"/api/accounting/payables/{supplier['id']}?all_history=true", headers=headers
    )
    assert r.status_code == 200, r.text
    het = r.json()
    assert het["all_history"] is True
    assert len(het["paid"]) == 1 and het["paid_in_period"] == 2_200_000


def test_no_cu_nua_nam_van_hien_du(client):
    """Nợ CHƯA trả thì kỳ không đụng tới — đây là vế phải yên tâm nhất."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC No Cu")
    don = _don(client, headers, supplier["id"])
    _ve_hang(client, headers, don["id"])

    db = SessionLocal()
    try:
        db.execute(
            text("UPDATE purchase_requests SET created_at = :t WHERE id = :i"),
            {"t": datetime.now() - timedelta(days=200), "i": don["id"]},
        )
        db.commit()
    finally:
        db.close()

    muc = next(m for m in _cong_no(client, headers)["items"] if m["supplier_id"] == supplier["id"])
    assert muc["total_due"] == 2_200_000, "nợ cũ không được tự biến mất theo kỳ"
    assert muc["unrecorded_amount"] == 2_200_000


# --- quyền -----------------------------------------------------------------


def test_khong_co_quyen_ke_toan_thi_khong_xem_duoc_cong_no(client):
    token = _token_vai("cn-ngoai-ke-toan", module="thu_mua", can_read=True)
    r = client.get("/api/accounting/payables", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403, r.text
