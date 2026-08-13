"""Công nợ phải trả + đợt giao + lùi/đóng đơn.

Bốn luật xương sống được canh ở đây (docs/prd-mua-hang-cong-no.md, chốt 06/08/2026):

1. **Không giấu nợ.** Hàng về tới đâu nợ tới đó. Giao 1/3 đợt mà bảng công nợ hiện 0đ là kiểu sai
   nguy hiểm nhất — nhìn vào tưởng không nợ ai.
2. **Không thừa nợ.** Chưa giao đợt nào thì chưa nợ đồng nào, dù đơn to bao nhiêu và dù ai bấm gì.
3. **Không nợ ảo.** Ứng trước rồi nộp lại phần thừa phải ra 0đ, không được để lại một món nợ ma
   trên bàn kế toán.
4. **Lùi/Đóng đơn phải kéo YCMH về đúng chỗ.** Quên vế này thì phòng ban nhìn vào tưởng đủ hàng.

Công thức: `cong_no = max(0, giá trị hàng ĐÃ GIAO − (đã chi − đã thu về))`. Phiếu ĐẶT CỌC cũng là
một phiếu chi nên cọc tự khấu trừ ngay từ đợt giao đầu tiên.

Phiếu chi lập ra là ĐÃ CHI — không còn trạng thái "chờ chi", không còn rổ 🟡.

HAI LUẬT THÊM (chủ chốt 09/08/2026) — mọi test dựng dữ liệu ở file này phải theo:

5. **Phiếu THANH TOÁN bắt buộc gắn ĐỢT GIAO.** Đơn chưa có đợt nào ⇒ chặn 422. Hệ quả: đơn đi
   đường CŨ (`mark-received`, không có đợt) chỉ còn trả được bằng phiếu ĐẶT CỌC.
6. **Phiếu ĐẶT CỌC bắt buộc khai CỌC DỰ KIẾN trước** (`PUT /purchase-requests/{id}/contract`), và
   trần cọc = cọc dự kiến − cọc ĐÃ CHI. Chưa khai ⇒ chặn 422. Dùng `_don(..., coc=N)` /
   `_khai_coc()` để khai — khai phải xong TRƯỚC khi duyệt vì duyệt rồi là khoá.
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


def _hom_nay() -> date:
    """Hôm nay theo ĐỒNG HỒ XƯỞNG (Asia/Bangkok) — cùng nguồn với `_business_today` của service.

    KHÔNG dùng `date.today()` ở file này: runner CI chạy giờ UTC, nên từ 17h UTC trở đi xưởng đã
    sang ngày mới còn `date.today()` vẫn là hôm qua. Test "ngày mai bị chặn" khi đó gửi lên đúng
    HÔM NAY của service ⇒ cửa chặn không nổ, 201 thay vì 422. Đã nổ thật trên CI 10/08/2026 20:04
    UTC; chạy cùng bộ test lúc sáng lại xanh — kiểu test thối theo giờ trong ngày."""
    return accounting_service._business_today()


def _headers(client) -> dict[str, str]:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _needed_date(days: int = 30) -> str:
    return (_hom_nay() + timedelta(days=days)).isoformat()


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
    # Ô duyệt PMH dời sang khoá `ke_toan` ngày 11/08/2026 — nút Duyệt / Từ chối chỉ có ở màn
    # "Đơn mua hàng (Kế toán)" nên ô quyền cũng về đó.
    token = _token_vai("cn-approver", module="ke_toan", can_read=True, can_approve=True)
    r = client.post(
        f"/api/purchase-requests/{purchase_id}/approve",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text


def _khai_coc(client, headers, purchase_id: int, so_tien: int) -> dict:
    """Khai CỌC DỰ KIẾN trên phiếu mua — bắt buộc trước khi lập bất kỳ phiếu ĐẶT CỌC nào
    (chủ chốt 09/08/2026).

    Phải gọi khi phiếu còn NHÁP/CHỜ DUYỆT: cọc dự kiến khoá sau khi duyệt (đó là con số người
    duyệt đã đồng ý), nên `_don(..., coc=...)` gọi hàm này trước bước gửi duyệt."""
    r = client.put(
        f"/api/purchase-requests/{purchase_id}/contract",
        json={"contract_number": None, "deposit_expected": so_tien},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["deposit_expected"] == so_tien
    return r.json()


def _don(
    client,
    headers,
    supplier_id: int,
    *,
    quantity: int = 1000,
    duyet: bool = True,
    coc: int = 0,
) -> dict:
    """Dựng một PMH đã duyệt. 1000 tờ × 2.200đ = 2.200.000đ.

    `duyet=False` để nguyên ở NHÁP — dùng cho ca phải khai trước khi duyệt.
    `coc=N` khai luôn CỌC DỰ KIẾN N đồng trước khi gửi duyệt — bắt buộc cho mọi test lập phiếu
    ĐẶT CỌC, vì từ 09/08/2026 chưa khai thì phiếu cọc bị chặn 422."""
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
    if coc:
        _khai_coc(client, headers, body["id"], coc)
    if duyet:
        assert client.post(
            f"/api/purchase-requests/{body['id']}/submit", headers=headers
        ).status_code == 200
        _duyet(client, body["id"])
    body["source_id"] = src["id"]
    return body


def _don_nhap(client, headers, supplier_id: int, *, quantity: int = 1000) -> dict:
    """Như `_don` nhưng DỪNG Ở NHÁP — dùng cho ca phải khai trước khi duyệt (VD cọc dự kiến)."""
    don = _don(client, headers, supplier_id, quantity=quantity, duyet=False)
    return don


def _gui_va_duyet(client, headers, purchase_id: int) -> None:
    assert client.post(
        f"/api/purchase-requests/{purchase_id}/submit", headers=headers
    ).status_code == 200
    _duyet(client, purchase_id)


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


def _phieu_chi(
    client,
    headers,
    purchase_id: int,
    amount: int,
    *,
    stage: str = "advance",
    delivery_id: int | None = None,
    expect: int = 201,
) -> dict:
    """Lập một phiếu chi. Phiếu sinh ra ĐÃ LÀ 'đã chi' — không còn bước xác nhận.

    Mặc định `stage="advance"` = phiếu ĐẶT CỌC ⇒ đơn phải khai cọc dự kiến trước (`_don(coc=…)`).
    `stage="final"` = phiếu THANH TOÁN ⇒ bắt buộc truyền `delivery_id` của một đợt giao có thật."""
    r = client.post(
        "/api/accounting/payment-vouchers",
        json={
            "purchase_request_id": purchase_id,
            "voucher_type": "cash",
            "payment_stage": stage,
            "delivery_id": delivery_id,
            "voucher_date": _hom_nay().isoformat(),
            "amount": amount,
            "currency": "VND",
            "exchange_rate": 1,
            "content": "Trả tiền giấy",
            "cash_recipient_name": "Nguyễn Lan",
            "cash_recipient_address": "Hà Nội",
        },
        headers=headers,
    )
    assert r.status_code == expect, r.text
    return r.json()


def _da_mua(client, headers, purchase_id: int) -> None:
    assert client.post(
        f"/api/purchase-requests/{purchase_id}/mark-purchased", headers=headers
    ).status_code == 200


def _ghi_dot(
    client,
    headers,
    purchase_id: int,
    *,
    lines: list[dict],
    ngay: str | None = None,
    han: str | None = None,
    so_hd: str | None = None,
    ngay_hd: str | None = None,
    expect: int = 200,
) -> dict:
    """Ghi một đợt giao. `lines` = [{"purchase_request_line_id": .., "quantity": ..}].

    KHÔNG có ô tiền: tiền của đợt do máy tính từ đơn giá đã chốt trên phiếu (chủ 07/08/2026)."""
    r = client.post(
        f"/api/purchase-requests/{purchase_id}/deliveries",
        json={
            "delivery_date": ngay or _hom_nay().isoformat(),
            "due_date": han,
            "invoice_number": so_hd,
            "invoice_date": ngay_hd,
            "lines": lines,
        },
        headers=headers,
    )
    assert r.status_code == expect, r.text
    return r.json()


def _dong_dau_tien(don: dict) -> int:
    return don["lines"][0]["id"]


def _cong_no(client, headers) -> dict:
    r = client.get("/api/accounting/payables", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _cong_no_ncc(client, headers, supplier_id: int) -> dict:
    r = client.get(f"/api/accounting/payables/{supplier_id}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# --- nợ theo ĐỢT GIAO: chống GIẤU NỢ và THỪA NỢ -----------------------------


def test_giao_mot_dot_thi_no_dung_bang_gia_tri_dot_do(client):
    """Test quan trọng nhất cả file — chống GIẤU NỢ.

    Trước 06/08/2026 nợ chỉ hiện khi cả đơn được bấm "Đã nhận hàng". Đơn giao 3 đợt, mới về đợt 1
    thì đơn còn ở "Đã mua" ⇒ màn công nợ hiện **0đ** trong khi đã nợ thật. Nay hàng về tới đâu nợ
    tới đó."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Giao Nhieu Dot")
    don = _don(client, headers, supplier["id"])
    _da_mua(client, headers, don["id"])

    sau = _ghi_dot(
        client, headers, don["id"],
        lines=[{"purchase_request_line_id": _dong_dau_tien(don), "quantity": 400}],
    )
    # 400 tờ x 2.200đ = 880.000đ
    assert sau["status"] == "partially_received"
    assert sau["gia_tri_da_giao"] == 880_000
    assert sau["outstanding_amount"] == 880_000
    assert sau["total_estimate"] == 2_200_000, "giá trị ĐƠN ĐẶT không đổi"

    muc = next(m for m in _cong_no(client, headers)["items"] if m["supplier_id"] == supplier["id"])
    assert muc["total_due"] == 880_000
    assert muc["order_count"] == 1

    chi_tiet = _cong_no_ncc(client, headers, supplier["id"])
    assert [x["con_no"] for x in chi_tiet["items"]] == [880_000]
    assert chi_tiet["items"][0]["seq_no"] == 1


def test_chua_giao_dot_nao_thi_khong_no_dong_nao(client):
    """Chống THỪA NỢ. Đặt hàng chưa nợ ai — kể cả khi đơn đã duyệt, đã đánh dấu đã mua."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Chua Ve Hang")
    don = _don(client, headers, supplier["id"])
    _da_mua(client, headers, don["id"])

    sau = client.get(f"/api/purchase-requests/{don['id']}", headers=headers).json()
    assert sau["gia_tri_da_giao"] == 0
    assert sau["outstanding_amount"] == 0
    assert not [
        m for m in _cong_no(client, headers)["items"] if m["supplier_id"] == supplier["id"]
    ]


def test_giao_du_thi_tu_chuyen_sang_da_nhan_hang(client):
    """Trạng thái nhận hàng là số SUY RA từ các đợt giao, không ai gõ tay."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Giao Du")
    don = _don(client, headers, supplier["id"])
    _da_mua(client, headers, don["id"])
    dong = _dong_dau_tien(don)

    b1 = _ghi_dot(client, headers, don["id"], lines=[{"purchase_request_line_id": dong, "quantity": 600}])
    assert b1["status"] == "partially_received"
    # YCMH chưa được báo "Hoàn tất" khi hàng mới về một phần.
    ycmh = client.get(f"/api/department-purchase-requests/{don['source_id']}", headers=headers)
    assert ycmh.json()["status"] == "in_purchase"

    b2 = _ghi_dot(client, headers, don["id"], lines=[{"purchase_request_line_id": dong, "quantity": 400}])
    assert b2["status"] == "received"
    assert b2["gia_tri_da_giao"] == 2_200_000
    ycmh = client.get(f"/api/department-purchase-requests/{don['source_id']}", headers=headers)
    assert ycmh.json()["status"] == "done"


def test_khong_cho_giao_vuot_so_dat(client):
    """Khai vống là bơm thẳng vào công nợ một món nợ chưa từng phát sinh."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Giao Vuot")
    don = _don(client, headers, supplier["id"])
    _da_mua(client, headers, don["id"])
    dong = _dong_dau_tien(don)

    _ghi_dot(client, headers, don["id"], lines=[{"purchase_request_line_id": dong, "quantity": 900}])
    r = client.post(
        f"/api/purchase-requests/{don['id']}/deliveries",
        json={
            "delivery_date": _hom_nay().isoformat(),
            "lines": [{"purchase_request_line_id": dong, "quantity": 200}],
        },
        headers=headers,
    )
    assert r.status_code == 422, r.text
    assert "chỉ còn 100" in r.json()["detail"]


def test_dong_don_chot_no_theo_so_da_giao(client):
    """NCC giao thiếu rồi thôi: "Đóng đơn" chốt nợ theo số đã giao, phần chưa giao rơi khỏi công nợ."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Dong Don")
    don = _don(client, headers, supplier["id"])
    _da_mua(client, headers, don["id"])
    _ghi_dot(
        client, headers, don["id"],
        lines=[{"purchase_request_line_id": _dong_dau_tien(don), "quantity": 700}],
    )

    thieu_ly_do = client.post(
        f"/api/purchase-requests/{don['id']}/close", json={"reason": " "}, headers=headers
    )
    assert thieu_ly_do.status_code == 422

    r = client.post(
        f"/api/purchase-requests/{don['id']}/close",
        json={"reason": "NCC hết hàng, không giao nữa"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "received"
    assert r.json()["outstanding_amount"] == 1_540_000  # 700 x 2.200


# --- cọc: một phiếu chi, tự khấu trừ vào đợt đầu ----------------------------


def test_dong_don_khi_chua_giao_dot_nao_bi_chan(client):
    """Đóng một đơn CHƯA giao đợt nào là đẻ NỢ MA.

    Không chặn thì phiếu sang `received` với 0 đợt ⇒ công nợ rơi vào nhánh phiếu-cũ và ghi nguyên
    giá trị đơn, dù không món hàng nào về. Giao diện chỉ hiện nút ở "Giao một phần" nên bấm tay
    không tới được — nhưng id là số chạy, gọi thẳng API là qua. Chốt phải ở service."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Dong Don Rong")
    don = _don(client, headers, supplier["id"])
    _da_mua(client, headers, don["id"])

    r = client.post(
        f"/api/purchase-requests/{don['id']}/close",
        json={"reason": "NCC báo hết hàng"},
        headers=headers,
    )
    assert r.status_code == 409, r.text
    assert "HUỶ đơn" in r.json()["detail"]

    # Và công nợ vẫn phải là 0 — không có nợ ma nào được sinh ra.
    sau = client.get(f"/api/purchase-requests/{don['id']}", headers=headers).json()
    assert sau["status"] == "purchased"
    assert sau["outstanding_amount"] == 0
    assert not [
        m for m in _cong_no(client, headers)["items"] if m["supplier_id"] == supplier["id"]
    ]


def test_coc_la_coc_ca_don_khong_thuoc_dot_nao(client):
    """Cọc = một phiếu chi `advance`, và nó là cọc của **CẢ ĐƠN**.

    Chủ bác bỏ bản đầu (06/08/2026): bản đó phân bổ cọc theo kiểu "giao trước trả trước", tức nhét
    cọc vào đợt 1 ⇒ bảng hiện *"đợt 1 đã trả 600.000"* trong khi thực tế KHÔNG ai trả đồng nào cho
    riêng đợt đó. Người đối chiếu với NCC theo từng đợt sẽ không khớp được với sao kê.

    Nay: cột "đã trả" của đợt chỉ đếm tiền trả ĐÍCH DANH đợt đó; cọc đứng thành dòng riêng."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Coc")
    # Cọc dự kiến phải khai TRƯỚC khi lập phiếu cọc (09/08/2026).
    don = _don(client, headers, supplier["id"], coc=600_000)
    _phieu_chi(client, headers, don["id"], 600_000, stage="advance")

    _da_mua(client, headers, don["id"])
    sau = _ghi_dot(
        client, headers, don["id"],
        lines=[{"purchase_request_line_id": _dong_dau_tien(don), "quantity": 400}],
    )
    # Đợt 1 trị giá 880.000đ, đã ứng 600.000đ => tổng còn nợ 280.000đ.
    assert sau["gia_tri_da_giao"] == 880_000
    assert sau["net_paid"] == 600_000
    assert sau["outstanding_amount"] == 280_000

    chi_tiet = _cong_no_ncc(client, headers, supplier["id"])
    dot = chi_tiet["items"][0]
    # HAI CỘT KHÁC NHAU, cố ý:
    assert dot["paid"] == 0, "KHÔNG ai trả riêng cho đợt này — cột này phải khớp sao kê từng đợt"
    assert dot["coc_bu"] == 600_000, "cọc của cả đơn CHIẾU xuống đợt, không phải tiền trả cho đợt"
    # ...nhưng CÒN NỢ thì trừ cả hai: cọc đã trả rồi, để đợt báo nợ nguyên giá trị là mời trả 2 lần.
    assert dot["con_no"] == 280_000
    assert chi_tiet["coc_chung_amount"] == 600_000
    assert chi_tiet["coc_chung"][0]["da_dung"] == 600_000
    assert chi_tiet["coc_chung"][0]["con_du"] == 0
    assert chi_tiet["total_due"] == 280_000

    # Trả tiếp 280.000 ĐÍCH DANH đợt 1 ⇒ đợt hết nợ và RỜI KHỎI danh sách "còn nợ".
    _phieu_chi(
        client, headers, don["id"], 280_000, stage="final", delivery_id=dot["delivery_id"]
    )
    lai = _cong_no_ncc(client, headers, supplier["id"])
    assert lai["total_due"] == 0
    assert lai["items"] == [], "đợt đã đủ tiền thì không được nằm ở danh sách CÒN NỢ nữa"


def test_dong_da_tra_noi_ro_dot_may(client):
    """Rổ "Đã trả" phải ghi ĐỢT MẤY, không được "trả theo đợt" chung chung (chủ 07/08/2026).

    Người cầm sao kê NCC đối chiếu từng dòng cần biết dòng nào ứng với đợt nào; thiếu số đợt thì
    hai đợt của cùng một đơn hiện y hệt nhau."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Dot May")
    don = _don(client, headers, supplier["id"], coc=100_000)
    _phieu_chi(client, headers, don["id"], 100_000, stage="advance")
    _da_mua(client, headers, don["id"])
    dong = _dong_dau_tien(don)
    sau = _ghi_dot(client, headers, don["id"], lines=[{"purchase_request_line_id": dong, "quantity": 300}])
    sau = _ghi_dot(client, headers, don["id"], lines=[{"purchase_request_line_id": dong, "quantity": 300}])
    d1, d2 = sau["deliveries"][0]["id"], sau["deliveries"][1]["id"]
    _phieu_chi(client, headers, don["id"], 200_000, stage="final", delivery_id=d1)
    _phieu_chi(client, headers, don["id"], 300_000, stage="final", delivery_id=d2)

    da_tra = _cong_no_ncc(client, headers, supplier["id"])["paid"]
    theo_seq = {x["amount"]: x["delivery_seq_no"] for x in da_tra}
    assert theo_seq[200_000] == 1
    assert theo_seq[300_000] == 2
    assert theo_seq[100_000] is None, "phiếu đặt cọc không gắn đợt nào"


def test_coc_phu_het_dot_thi_dot_khong_con_bao_no(client):
    """Ca chủ bắt được 07/08/2026: cọc 100k + trả đợt 900k, hoá đơn 1tr ⇒ đợt phải HẾT nợ.

    Bản trước cột `con_no` của đợt không trừ cọc, nên đợt vẫn hiện "còn nợ 100.000" kèm nút Lập
    phiếu chi trong khi tổng dưới cùng đã về 0 — mời kế toán trả lần thứ hai."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Coc Phu Het")
    don = _don(client, headers, supplier["id"], coc=100_000)
    _phieu_chi(client, headers, don["id"], 100_000, stage="advance")
    _da_mua(client, headers, don["id"])
    sau = _ghi_dot(
        client, headers, don["id"],
        lines=[{"purchase_request_line_id": _dong_dau_tien(don), "quantity": 500}],
    )
    dot_id = sau["deliveries"][0]["id"]  # 500 x 2.200 = 1.100.000
    _phieu_chi(client, headers, don["id"], 1_000_000, stage="final", delivery_id=dot_id)

    chi_tiet = _cong_no_ncc(client, headers, supplier["id"])
    assert chi_tiet["total_due"] == 0
    assert chi_tiet["items"] == [], "hết nợ thì không còn dòng nào, cũng không còn nút Lập phiếu chi"
    lai = client.get(f"/api/purchase-requests/{don['id']}", headers=headers).json()
    assert lai["outstanding_amount"] == 0


def test_phieu_mua_phoi_ra_cac_phieu_dat_coc_da_lap(client):
    """Form phiếu chi cần biết đơn ĐÃ có phiếu cọc để cảnh báo khi sắp lập phiếu cọc thứ hai.

    Cảnh báo chứ KHÔNG chặn (chủ chốt 07/08/2026): ứng thêm là ca có thật, và mỗi lần tiền rời két
    phải là một chứng từ riêng — sửa phiếu cũ lên số to hơn là làm phiếu không khớp lần chi thật.

    Từ 09/08/2026 "không chặn" có thêm một mép: nhiều phiếu cọc vẫn được, miễn TỔNG không vượt cọc
    dự kiến đã khai. Ở đây khai đúng 150.000 = 100.000 + 50.000 nên cả hai phiếu đều lọt."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Coc Hai Lan")
    don = _don(client, headers, supplier["id"], coc=150_000)
    truoc = client.get(f"/api/purchase-requests/{don['id']}", headers=headers).json()
    assert truoc["coc_da_lap"] == [] and truoc["coc_da_chi"] == 0

    p1 = _phieu_chi(client, headers, don["id"], 100_000, stage="advance")
    sau = client.get(f"/api/purchase-requests/{don['id']}", headers=headers).json()
    assert [c["code"] for c in sau["coc_da_lap"]] == [p1["code"]]
    assert sau["coc_da_chi"] == 100_000

    # Vẫn lập được phiếu cọc thứ hai — chỉ cảnh báo trên giao diện.
    p2 = _phieu_chi(client, headers, don["id"], 50_000, stage="advance")
    cuoi = client.get(f"/api/purchase-requests/{don['id']}", headers=headers).json()
    assert {c["code"] for c in cuoi["coc_da_lap"]} == {p1["code"], p2["code"]}
    assert cuoi["coc_da_chi"] == 150_000


def test_ung_truoc_roi_nop_lai_phan_thua_thi_het_no(client):
    """Ca NỢ ẢO của bản cũ: tạm ứng 10tr, mua hết 8,5tr, nộp lại 1,5tr.

    Bản trước 06/08/2026 ra "còn nợ 1,5tr" trong khi tiền đã về két, vì nó đo nợ theo GIÁ TRỊ ĐƠN
    trừ tiền đã chi. Nay đo theo HÀNG ĐÃ VỀ nên ra đúng 0."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC No Ao")
    # Đơn 5.000 tờ x 2.200 = 11.000.000đ, thoả thuận tạm ứng 10.000.000đ.
    don = _don(client, headers, supplier["id"], quantity=5000, coc=10_000_000)
    phieu = _phieu_chi(client, headers, don["id"], 10_000_000, stage="advance")

    _da_mua(client, headers, don["id"])
    # Hàng về 3.864 tờ = 8.500.800đ
    _ghi_dot(
        client, headers, don["id"],
        lines=[{"purchase_request_line_id": _dong_dau_tien(don), "quantity": 3864}],
    )
    client.post(f"/api/purchase-requests/{don['id']}/close",
                json={"reason": "Chốt theo số thực giao"}, headers=headers)

    # NCC nộp lại phần thừa.
    thua = 10_000_000 - 8_500_800
    receipt = client.post(
        f"/api/accounting/payment-vouchers/{phieu['id']}/receipts",
        json={
            "payer_name": "Nguyễn Lan",
            "receipt_method": "cash",
            "receipt_date": _hom_nay().isoformat(),
            "amount": thua,
            "currency": "VND",
            "exchange_rate": 1,
            "content": "Nộp lại tiền thừa",
        },
        headers=headers,
    )
    assert receipt.status_code == 201, receipt.text
    assert client.post(
        f"/api/accounting/payment-receipts/{receipt.json()['id']}/mark-received",
        json={"bank_reference": None},
        headers=headers,
    ).status_code == 200

    sau = client.get(f"/api/purchase-requests/{don['id']}", headers=headers).json()
    assert sau["gia_tri_da_giao"] == 8_500_800
    assert sau["net_paid"] == 8_500_800
    assert sau["outstanding_amount"] == 0, "tiền đã về két thì KHÔNG được còn nợ ma"
    assert not [
        m
        for m in _cong_no(client, headers)["items"]
        if m["supplier_id"] == supplier["id"] and m["total_due"] > 0
    ]


# --- số tiền đợt giao: theo HOÁ ĐƠN, không phải theo đơn giá ----------------


def test_tien_dot_giao_do_MAY_TINH_tu_so_luong(client):
    """Tiền của đợt = số lượng thực nhận × đơn giá đã chốt. KHÔNG ai gõ tay (chủ 07/08/2026).

    Vòng này từng đi hai lần: 06/08 mở ô "Số tiền theo hoá đơn" cho gõ tay, 07/08 chủ đảo lại —
    *"không cho sửa nữa, dựa vào số lượng thực tế tính ra tiền luôn"*. Ô gõ tay đẻ ra đúng cái lệch
    mà chính chủ bắt được: chi tiết PMH hiện một số, ngoài bảng hiện số khác cho cùng một đợt.

    Gửi kèm `amount` cũng phải bị BỎ QUA — client cũ hoặc người gọi thẳng API không được có đường
    ghi đè con số này."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Tien May Tinh")
    don = _don(client, headers, supplier["id"])  # 1.000 tờ x 2.200 = 2.200.000đ
    _da_mua(client, headers, don["id"])

    r = client.post(
        f"/api/purchase-requests/{don['id']}/deliveries",
        json={
            "delivery_date": _hom_nay().isoformat(),
            # Cố tình nhét số tiền vào — server phải phớt lờ.
            "amount": 999_999_999,
            "lines": [{"purchase_request_line_id": _dong_dau_tien(don), "quantity": 500}],
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    dot = r.json()["deliveries"][0]
    assert dot["amount"] == 1_100_000, "500 × 2.200 — không phải số client gửi lên"
    assert "amount_goi_y" not in dot, "thôi còn khái niệm số gợi ý"
    assert r.json()["gia_tri_da_giao"] == 1_100_000
    assert r.json()["outstanding_amount"] == 1_100_000


# --- trần lập phiếu chi -----------------------------------------------------


def test_tran_thanh_toan_theo_no_tran_dat_coc_theo_don(client):
    """Hai trần khác nhau có chủ ý: thanh toán <= CÔNG NỢ, đặt cọc <= CỌC DỰ KIẾN ĐÃ KHAI.

    Vế cọc đổi gốc 09/08/2026: trước đó trần cọc lấy theo GIÁ TRỊ ĐƠN, nên đơn 2,2tr ứng trước được
    tới 2,2tr trong khi hai bên chỉ thoả thuận cọc 1tr. Nay trần bám con số đã khai — nên ở đây khai
    1.000.000 (KHÁC giá trị đơn) để test chứng minh trần lấy từ đâu."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Tran Phieu")
    don = _don(client, headers, supplier["id"], coc=1_000_000)
    _da_mua(client, headers, don["id"])
    sau = _ghi_dot(
        client, headers, don["id"],
        lines=[{"purchase_request_line_id": _dong_dau_tien(don), "quantity": 500}],
    )
    dot_id = sau["deliveries"][0]["id"]
    assert sau["outstanding_amount"] == 1_100_000
    assert sau["tran_dat_coc"] == 1_000_000, "trần cọc = số đã khai, KHÔNG phải giá trị đơn 2,2tr"

    vuot = _phieu_chi(
        client, headers, don["id"], 1_100_001, stage="final", delivery_id=dot_id, expect=422
    )
    assert "thanh toán" in vuot["detail"]

    vuot_coc = _phieu_chi(client, headers, don["id"], 1_000_001, stage="advance", expect=422)
    assert "đặt cọc" in vuot_coc["detail"]

    ok = _phieu_chi(client, headers, don["id"], 1_100_000, stage="final", delivery_id=dot_id)
    assert ok["status"] == "paid"
    assert ok["delivery_id"] == dot_id
    assert ok["delivery_seq_no"] == 1


def test_tran_thanh_toan_theo_TUNG_DOT_khong_theo_ca_don(client):
    """Lỗi chủ bắt được 07/08/2026 — GIẤU NỢ qua đường trả thừa.

    Trần phiếu thanh toán từng lấy công nợ CẢ ĐƠN, nên kế toán chọn "Đợt 2" rồi gõ số lớn hơn giá
    trị đợt đó vẫn qua. Phần thừa chảy vào rổ cọc chung rồi lặng lẽ trả hộ Đợt 1 ⇒ món nợ của đợt 1
    biến mất khỏi màn Công nợ mà không ai bấm gì.

    Nay trần bám ĐÚNG đợt đang chọn. Trả cho nhiều đợt thì lập nhiều phiếu."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Tran Theo Dot")
    don = _don(client, headers, supplier["id"])  # 1.000 tờ x 2.200 = 2.200.000đ
    _da_mua(client, headers, don["id"])
    dong = _dong_dau_tien(don)
    _ghi_dot(client, headers, don["id"], lines=[{"purchase_request_line_id": dong, "quantity": 400}])
    sau = _ghi_dot(client, headers, don["id"], lines=[{"purchase_request_line_id": dong, "quantity": 300}])
    d1 = sau["deliveries"][0]["id"]  # 400 x 2.200 = 880.000
    d2 = sau["deliveries"][1]["id"]  # 300 x 2.200 = 660.000
    assert sau["outstanding_amount"] == 1_540_000

    # Trả cho ĐỢT 2 nhưng gõ số của cả hai đợt ⇒ CHẶN, dù vẫn trong công nợ cả đơn.
    vuot = _phieu_chi(
        client, headers, don["id"], 1_540_000, stage="final", delivery_id=d2, expect=422
    )
    assert "đợt 2" in vuot["detail"]

    # Đúng số của đợt 2 thì qua.
    _phieu_chi(client, headers, don["id"], 660_000, stage="final", delivery_id=d2)

    # ĐỢT 1 VẪN CÒN NỢ — đây là chỗ trước kia nó biến mất.
    chi_tiet = _cong_no_ncc(client, headers, supplier["id"])
    assert [x["delivery_id"] for x in chi_tiet["items"]] == [d1]
    assert chi_tiet["items"][0]["con_no"] == 880_000
    assert chi_tiet["total_due"] == 880_000


def test_coc_khong_bi_tran_dot_chan(client):
    """Cọc KHÔNG bị trần theo đợt chặn — nó là tiền chi khi hàng chưa về, không thuộc đợt nào.

    Trần của nó là CỌC DỰ KIẾN đã khai (09/08/2026), độc lập hoàn toàn với giá trị hàng đã về."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Coc Van Rong")
    don = _don(client, headers, supplier["id"], coc=2_200_000)
    _da_mua(client, headers, don["id"])
    _ghi_dot(
        client, headers, don["id"],
        lines=[{"purchase_request_line_id": _dong_dau_tien(don), "quantity": 100}],
    )
    # Hàng mới về 220.000đ nhưng vẫn ứng trước được trọn 2.200.000đ đã khai.
    ok = _phieu_chi(client, headers, don["id"], 2_200_000, stage="advance")
    assert ok["amount_vnd"] == 2_200_000


def test_phieu_thanh_toan_phai_chon_dot_khi_don_co_dot_giao(client):
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Chon Dot")
    don = _don(client, headers, supplier["id"])
    _da_mua(client, headers, don["id"])
    _ghi_dot(
        client, headers, don["id"],
        lines=[{"purchase_request_line_id": _dong_dau_tien(don), "quantity": 500}],
    )
    thieu = _phieu_chi(client, headers, don["id"], 100_000, stage="final", expect=422)
    assert "chọn đợt giao" in thieu["detail"]


# --- luật 09/08/2026: thanh toán PHẢI có đợt giao, cọc PHẢI khai trước ------


def test_chua_co_dot_giao_nao_thi_khong_lap_duoc_phieu_thanh_toan(client):
    """Luật 1 (chủ chốt 09/08/2026). Đơn chưa ghi đợt giao nào ⇒ phiếu THANH TOÁN bị chặn.

    Trước đó đơn không có đợt vẫn chi được với `delivery_id = null`: tiền ra khỏi két mà không có
    mốc "hàng về đợt nào" ⇒ công nợ biết TỔNG đã trả nhưng không biết đợt nào xong, còn cột Quá hạn
    (đếm theo hạn của TỪNG đợt) không quy được về đâu. Nay muốn trả tiền thì ghi đợt trước — hoặc đi
    đường ĐẶT CỌC nếu hàng thật sự chưa về."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Chua Co Dot")
    don = _don(client, headers, supplier["id"])
    _da_mua(client, headers, don["id"])

    chan = _phieu_chi(client, headers, don["id"], 100_000, stage="final", expect=422)
    assert "chưa có đợt giao" in chan["detail"]
    assert "ĐẶT CỌC" in chan["detail"], "báo lỗi phải chỉ luôn đường đi tiếp"
    # Chặn thật: không có phiếu chi nào được đẻ ra.
    assert client.get(f"/api/purchase-requests/{don['id']}", headers=headers).json()["paid_amount"] == 0

    # Ghi đợt giao xong thì đúng số tiền đó đi lọt, và phiếu mang theo số đợt.
    sau = _ghi_dot(
        client, headers, don["id"],
        lines=[{"purchase_request_line_id": _dong_dau_tien(don), "quantity": 500}],
    )
    dot_id = sau["deliveries"][0]["id"]
    ok = _phieu_chi(client, headers, don["id"], 100_000, stage="final", delivery_id=dot_id)
    assert ok["delivery_id"] == dot_id
    assert ok["delivery_seq_no"] == 1


def test_chua_khai_coc_du_kien_thi_khong_lap_duoc_phieu_dat_coc(client):
    """Luật 2 (chủ chốt 09/08/2026). Chưa khai Cọc dự kiến ⇒ phiếu ĐẶT CỌC bị chặn.

    Không khai mà vẫn chi được thì con số "Cọc dự kiến" chỉ là trang trí, và không có gì để đối
    chiếu với thoả thuận đã ký."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Chua Khai Coc")
    don = _don(client, headers, supplier["id"])  # KHÔNG khai cọc
    truoc = client.get(f"/api/purchase-requests/{don['id']}", headers=headers).json()
    assert truoc["deposit_expected"] == 0
    assert truoc["tran_dat_coc"] == 0, "chưa khai thì trần cọc bằng 0, không phải giá trị đơn"

    chan = _phieu_chi(client, headers, don["id"], 100_000, stage="advance", expect=422)
    assert "Cọc dự kiến" in chan["detail"]

    # Và đơn ĐÃ DUYỆT thì không khai vá được nữa — nên phải khai từ lúc còn nháp.
    muon = client.put(
        f"/api/purchase-requests/{don['id']}/contract",
        json={"contract_number": None, "deposit_expected": 100_000},
        headers=headers,
    )
    assert muon.status_code == 409, muon.text

    # Đơn khai đàng hoàng từ đầu thì cùng số tiền đó đi lọt.
    don_ok = _don(client, headers, supplier["id"], coc=100_000)
    assert _phieu_chi(client, headers, don_ok["id"], 100_000, stage="advance")["amount_vnd"] == 100_000


def test_khai_coc_10tr_thi_lap_duoc_nhieu_phieu_mien_tong_khong_vuot(client):
    """Trần cọc = cọc dự kiến − cọc ĐÃ CHI: khai 10tr thì 3tr + 7tr đều qua, thêm 1đ là chặn.

    Nhiều phiếu cọc là ca có thật (ứng đợt một rồi ứng thêm), nên luật đếm theo TỔNG chứ không cấm
    phiếu thứ hai. Đơn ở đây trị giá 22tr — cố ý to hơn số khai, để chứng minh trần bám con số đã
    thoả thuận chứ không bám giá trị đơn."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Coc Nhieu Lan")
    don = _don(client, headers, supplier["id"], quantity=10_000, coc=10_000_000)  # đơn 22.000.000đ

    def _tran() -> int:
        return client.get(f"/api/purchase-requests/{don['id']}", headers=headers).json()["tran_dat_coc"]

    assert _tran() == 10_000_000

    _phieu_chi(client, headers, don["id"], 3_000_000, stage="advance")
    assert _tran() == 7_000_000
    _phieu_chi(client, headers, don["id"], 7_000_000, stage="advance")
    assert _tran() == 0

    them = _phieu_chi(client, headers, don["id"], 1, stage="advance", expect=422)
    assert "đặt cọc" in them["detail"]
    sau = client.get(f"/api/purchase-requests/{don['id']}", headers=headers).json()
    assert sau["coc_da_chi"] == 10_000_000, "đúng số đã khai, không hơn một đồng"


def test_tran_coc_khong_bi_tien_thanh_toan_dot_giao_dam_vao(client):
    """Hai hạn mức ĐỘC LẬP: trần cọc KHÔNG trừ tiền đã thanh toán cho đợt giao.

    Trừ vào đây thì càng trả tiền hàng càng hết quyền ứng trước — trong khi cọc và tiền hàng là hai
    thoả thuận khác nhau."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Hai Han Muc")
    don = _don(client, headers, supplier["id"], coc=1_000_000)  # đơn 2,2tr, cọc thoả thuận 1tr
    _da_mua(client, headers, don["id"])
    sau = _ghi_dot(
        client, headers, don["id"],
        lines=[{"purchase_request_line_id": _dong_dau_tien(don), "quantity": 1000}],
    )
    dot_id = sau["deliveries"][0]["id"]

    def _tran() -> int:
        return client.get(f"/api/purchase-requests/{don['id']}", headers=headers).json()["tran_dat_coc"]

    _phieu_chi(client, headers, don["id"], 400_000, stage="advance")
    assert _tran() == 600_000

    # Trả 1tr ĐÍCH DANH đợt giao — trần cọc không được nhúc nhích.
    _phieu_chi(client, headers, don["id"], 1_000_000, stage="final", delivery_id=dot_id)
    assert _tran() == 600_000, "tiền hàng KHÔNG được ăn vào hạn mức cọc"

    # ...và 600.000đ cọc còn lại vẫn chi được trọn vẹn.
    assert _phieu_chi(client, headers, don["id"], 600_000, stage="advance")["amount_vnd"] == 600_000
    assert _tran() == 0


def test_dot_da_co_phieu_chi_thi_khong_sua_khong_xoa(client):
    """Tiền đã ra thì không được đổi số hàng dưới chân nó."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Khoa Dot")
    don = _don(client, headers, supplier["id"])
    _da_mua(client, headers, don["id"])
    sau = _ghi_dot(
        client, headers, don["id"],
        lines=[{"purchase_request_line_id": _dong_dau_tien(don), "quantity": 500}],
    )
    dot_id = sau["deliveries"][0]["id"]
    _phieu_chi(client, headers, don["id"], 500_000, stage="final", delivery_id=dot_id)

    sua = client.put(
        f"/api/purchase-requests/{don['id']}/deliveries/{dot_id}",
        json={"delivery_date": _hom_nay().isoformat(), "lines": None},
        headers=headers,
    )
    assert sua.status_code == 409
    xoa = client.delete(
        f"/api/purchase-requests/{don['id']}/deliveries/{dot_id}", headers=headers
    )
    assert xoa.status_code == 409


def test_sua_dot_giao_cap_nhat_dong_tai_cho_khong_trung_unique(client):
    """Gửi lại cùng dòng khi sửa từng gây 500 do INSERT mới trước DELETE dòng cũ."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Sua Dot Tai Cho")
    don = _don(client, headers, supplier["id"])
    _da_mua(client, headers, don["id"])
    line_id = _dong_dau_tien(don)
    sau = _ghi_dot(
        client, headers, don["id"],
        lines=[{"purchase_request_line_id": line_id, "quantity": 400}],
    )
    dot_id = sau["deliveries"][0]["id"]

    sua = client.put(
        f"/api/purchase-requests/{don['id']}/deliveries/{dot_id}",
        json={
            "delivery_date": _hom_nay().isoformat(),
            "note": "Đã đối chiếu lại",
            "lines": [
                {"purchase_request_line_id": line_id, "quantity": 450, "note": "Nhận thực tế"}
            ],
        },
        headers=headers,
    )
    assert sua.status_code == 200, sua.text
    dot = sua.json()["deliveries"][0]
    assert dot["note"] == "Đã đối chiếu lại"
    assert len(dot["lines"]) == 1
    assert dot["lines"][0]["quantity"] == 450
    assert dot["lines"][0]["note"] == "Nhận thực tế"


# --- trả nhiều đợt: KHÔNG được biến mất khỏi công nợ ------------------------


def test_tra_mot_phan_van_con_no(client):
    """Đơn 2,2tr chi 1tr rồi => vẫn nợ 1,2tr. Đây là chỗ dễ làm đơn trả dở biến mất khỏi bảng.

    Đơn đi đường CŨ (`mark-received`, không có đợt giao) nên từ 09/08/2026 chỉ trả được bằng phiếu
    ĐẶT CỌC — và muốn thế thì phải khai cọc dự kiến trước."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Tra Nhieu Dot")
    don = _don(client, headers, supplier["id"], coc=1_000_000)
    _ve_hang(client, headers, don["id"])
    _phieu_chi(client, headers, don["id"], 1_000_000)

    muc = next(m for m in _cong_no(client, headers)["items"] if m["supplier_id"] == supplier["id"])
    assert muc["total_due"] == 1_200_000


def test_tra_xong_thi_roi_khoi_cong_no_va_vao_ro_da_tra(client):
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Tra Xong")
    don = _don(client, headers, supplier["id"], coc=2_200_000)
    _ve_hang(client, headers, don["id"])
    _phieu_chi(client, headers, don["id"], 2_200_000)

    # NCC trả hết vẫn GIỮ dòng trên bảng — nhờ cột "Đã trả trong kỳ". Biến mất là quay lại đúng
    # câu hỏi không trả lời được: "làm sao biết mình đã trả hết".
    muc = next(m for m in _cong_no(client, headers)["items"] if m["supplier_id"] == supplier["id"])
    assert muc["total_due"] == 0
    assert muc["order_count"] == 0, "đơn đã trả xong KHÔNG đếm vào 'Đơn còn nợ'"
    assert muc["paid_in_period"] == 2_200_000

    chi_tiet = _cong_no_ncc(client, headers, supplier["id"])
    assert chi_tiet["items"] == []
    # Rổ da tra liệt kê từng LẦN CHI, cộng lại đúng bằng cột "Đã trả".
    assert [x["purchase_code"] for x in chi_tiet["paid"]] == [don["code"]]
    assert sum(x["amount"] for x in chi_tiet["paid"]) == chi_tiet["paid_in_period"] == 2_200_000


def test_phieu_huy_khong_tinh_la_no(client):
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Phieu Huy")
    don = _don(client, headers, supplier["id"], coc=2_200_000)
    _ve_hang(client, headers, don["id"])
    phieu = _phieu_chi(client, headers, don["id"], 2_200_000)
    assert client.post(
        f"/api/accounting/payment-vouchers/{phieu['id']}/cancel",
        json={"reason": "Lập nhầm"},
        headers=headers,
    ).status_code == 200

    muc = next(m for m in _cong_no(client, headers)["items"] if m["supplier_id"] == supplier["id"])
    assert muc["total_due"] == 2_200_000, "huỷ phiếu thì món nợ quay lại, không mất"


# --- quá hạn: theo hạn trả của ĐỢT GIAO -------------------------------------


def test_qua_han_dem_theo_han_cua_dot_giao(client, monkeypatch):
    """Hạn trả thuộc về ĐỢT GIAO (ưu tiên ngày hóa đơn + số ngày NCC cho nợ), không thuộc phiếu chi —
    phiếu chi là tiền đã ra, nó không có hạn."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Qua Han")
    don = _don(client, headers, supplier["id"])
    _da_mua(client, headers, don["id"])
    han = _hom_nay() + timedelta(days=15)
    _ghi_dot(
        client, headers, don["id"],
        lines=[{"purchase_request_line_id": _dong_dau_tien(don), "quantity": 1000}],
        han=han.isoformat(),
    )

    muc = next(m for m in _cong_no(client, headers)["items"] if m["supplier_id"] == supplier["id"])
    assert muc["overdue_amount"] == 0, "chưa tới hạn thì chưa quá hạn"
    assert muc["no_han_amount"] == 2_200_000

    # Đẩy 'hôm nay' qua hạn 5 ngày. Chọc SEAM chứ không cắm ngày cứng — cắm cứng là hẹn giờ cho
    # test tự đỏ vài tháng sau.
    monkeypatch.setattr(accounting_service, "_business_today", lambda: han + timedelta(days=5))
    muc = next(m for m in _cong_no(client, headers)["items"] if m["supplier_id"] == supplier["id"])
    assert muc["overdue_amount"] == 2_200_000
    chi_tiet = _cong_no_ncc(client, headers, supplier["id"])
    assert chi_tiet["items"][0]["overdue_days"] == 5


def test_ncc_chua_khai_so_ngay_cho_no_thi_dot_khong_co_han(client):
    """`credit_days` NULL = chưa đặt hạn => đợt KHÔNG vào cột Quá hạn, nhưng phải gắn cờ để giao
    diện lôi lên đầu. Im lặng ở đây là một món nợ không ai canh."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Chua Dat Han")
    don = _don(client, headers, supplier["id"])
    _da_mua(client, headers, don["id"])
    _ghi_dot(
        client, headers, don["id"],
        lines=[{"purchase_request_line_id": _dong_dau_tien(don), "quantity": 1000}],
    )

    chi_tiet = _cong_no_ncc(client, headers, supplier["id"])
    dong = chi_tiet["items"][0]
    assert dong["due_date"] is None
    assert dong["chua_dat_han"] is True
    assert dong["overdue_days"] == 0
    assert chi_tiet["overdue_amount"] == 0


def _sua_ncc(client, headers, supplier: dict, **doi) -> dict:
    body = {
        "name": supplier["name"],
        "tax_code": supplier["tax_code"],
        "phone": supplier["phone"],
        "email": supplier["email"],
        "address": supplier["address"],
        "contact_name": supplier["contact_name"],
        "supplier_group": supplier["supplier_group"],
        "items": [
            {"item_name": "Giấy Duplex", "unit": "tờ", "unit_price": 2200, "vat_percent": 0}
        ],
        **doi,
    }
    r = client.put(f"/api/suppliers/{supplier['id']}", json=body, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_so_ngay_cho_no_cua_ncc_suy_ra_han_tra(client):
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Co So Ngay")
    sua = _sua_ncc(client, headers, supplier, credit_limit=1_000_000, credit_days=30)
    assert sua["credit_days"] == 30

    don = _don(client, headers, supplier["id"])
    _da_mua(client, headers, don["id"])
    ngay_giao = _hom_nay() - timedelta(days=10)
    ngay_hoa_don = _hom_nay() - timedelta(days=3)
    sau = _ghi_dot(
        client, headers, don["id"],
        lines=[{"purchase_request_line_id": _dong_dau_tien(don), "quantity": 1000}],
        ngay=ngay_giao.isoformat(),
        ngay_hd=ngay_hoa_don.isoformat(),
    )
    assert sau["deliveries"][0]["due_date"] == (
        ngay_hoa_don + timedelta(days=30)
    ).isoformat()
    assert sau["deliveries"][0]["chua_dat_han"] is False

    # Nợ 2,2tr > hạn mức 1tr => CẢNH BÁO, không chặn gì.
    tong = _cong_no(client, headers)
    muc = next(m for m in tong["items"] if m["supplier_id"] == supplier["id"])
    assert muc["vuot_han_muc"] is True
    assert muc["vuot_bao_nhieu"] == 1_200_000
    assert tong["vuot_han_muc_count"] >= 1


def test_vuot_han_muc_khong_chan_lap_don_moi(client):
    """Đ6: cảnh báo MỀM. Chặn cứng là đúng lúc gấp nhất thì hệ khoá đường mua."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Vuot Han Muc")
    _sua_ncc(client, headers, supplier, credit_limit=1)
    don = _don(client, headers, supplier["id"])
    _ve_hang(client, headers, don["id"])
    # Lập tiếp một đơn nữa cho chính NCC đang vượt hạn mức — vẫn phải qua.
    don2 = _don(client, headers, supplier["id"])
    lai = client.get(f"/api/purchase-requests/{don2['id']}", headers=headers).json()
    assert lai["status"] == "approved", "vượt hạn mức KHÔNG được chặn đường duyệt đơn"

    tin = client.get(
        f"/api/purchase-requests/{don2['id']}/supplier-credit", headers=headers
    )
    assert tin.status_code == 200, tin.text
    assert tin.json()["vuot_han_muc"] is True


# --- hoá đơn: nhiều đợt chung một số ----------------------------------------


def test_mot_hoa_don_phu_nhieu_dot_giao(client):
    """NCC giao 3 đợt rồi mới xuất MỘT hoá đơn chung — gán một lần cho cả ba."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Mot Hoa Don")
    don = _don(client, headers, supplier["id"])
    _da_mua(client, headers, don["id"])
    dong = _dong_dau_tien(don)
    sau = None
    for sl in (300, 300, 400):
        sau = _ghi_dot(
            client, headers, don["id"],
            lines=[{"purchase_request_line_id": dong, "quantity": sl}],
        )
    ids = [d["id"] for d in sau["deliveries"]]
    assert len(ids) == 3

    r = client.post(
        f"/api/purchase-requests/{don['id']}/invoice",
        json={
            "delivery_ids": ids,
            "invoice_number": "HD-0001",
            "invoice_date": _hom_nay().isoformat(),
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert {d["invoice_number"] for d in r.json()["deliveries"]} == {"HD-0001"}


# --- hợp đồng + cọc dự kiến -------------------------------------------------


def test_so_hop_dong_va_coc_du_kien_khong_dung_vao_cong_no(client):
    """`deposit_expected` chỉ để NHẮC. Cho nó vào công thức là trừ cọc hai lần khi kế toán lập cả
    phiếu chi đặt cọc."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Hop Dong")
    don = _don_nhap(client, headers, supplier["id"])
    r = client.put(
        f"/api/purchase-requests/{don['id']}/contract",
        json={"contract_number": "HD-2026/07", "deposit_expected": 500_000},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["contract_number"] == "HD-2026/07"
    assert r.json()["deposit_expected"] == 500_000

    _gui_va_duyet(client, headers, don["id"])
    # ĐÃ DUYỆT thì cọc dự kiến khoá — đó là con số người duyệt đã đồng ý.
    khoa = client.put(
        f"/api/purchase-requests/{don['id']}/contract",
        json={"contract_number": "HD-2026/07", "deposit_expected": 900_000},
        headers=headers,
    )
    assert khoa.status_code == 409, khoa.text
    # Nhưng SỐ HỢP ĐỒNG vẫn sửa được — hợp đồng thường ký sau khi duyệt.
    doi_hd = client.put(
        f"/api/purchase-requests/{don['id']}/contract",
        json={"contract_number": "HD-2026/07-B", "deposit_expected": 500_000},
        headers=headers,
    )
    assert doi_hd.status_code == 200, doi_hd.text

    _da_mua(client, headers, don["id"])
    sau = _ghi_dot(
        client, headers, don["id"],
        lines=[{"purchase_request_line_id": _dong_dau_tien(don), "quantity": 1000}],
    )
    # Chưa chi đồng nào => nợ nguyên giá trị hàng, KHÔNG bị trừ 500k "cọc dự kiến".
    assert sau["outstanding_amount"] == 2_200_000


# --- số thực nhận ----------------------------------------------------------


def test_khai_nhan_thieu_thi_no_giam_va_chan_lap_phieu_vuot(client):
    """NCC giao 800/1000 tờ ⇒ nợ 1,76tr, không phải 2,2tr. Và kế toán KHÔNG lập nổi phiếu 2,2tr.

    Ý đồ giữ nguyên; chỉ ĐƯỜNG DỰNG DỮ LIỆU đổi: từ 09/08/2026 phiếu THANH TOÁN bắt buộc gắn đợt
    giao, nên số nhận thiếu ở đây khai bằng một ĐỢT GIAO 800 tờ thay cho `mark-received`. (Đường
    khai thiếu kiểu cũ vẫn được canh ở `test_khong_khai_gi_thi_y_nhu_truoc` và các test sửa số thực
    nhận ngay dưới.)"""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Giao Thieu")
    don = _don(client, headers, supplier["id"])
    _da_mua(client, headers, don["id"])
    sau = _ghi_dot(
        client, headers, don["id"],
        lines=[{"purchase_request_line_id": _dong_dau_tien(don), "quantity": 800}],
    )
    dot_id = sau["deliveries"][0]["id"]
    assert sau["total_estimate"] == 2_200_000, "giá trị ĐƠN ĐẶT không đổi"
    assert sau["received_total"] == 1_760_000
    assert sau["gia_tri_da_giao"] == 1_760_000

    muc = next(m for m in _cong_no(client, headers)["items"] if m["supplier_id"] == supplier["id"])
    assert muc["total_due"] == 1_760_000

    # Phiếu THANH TOÁN bị chặn ở đúng số nợ đã phát sinh (1,76tr) — không cho trả theo số ĐẶT.
    vuot = _phieu_chi(
        client, headers, don["id"], 2_200_000, stage="final", delivery_id=dot_id, expect=422
    )
    assert "thanh toán" in vuot["detail"]
    assert _phieu_chi(
        client, headers, don["id"], 1_760_000, stage="final", delivery_id=dot_id
    )["amount_vnd"] == 1_760_000


def test_don_cu_khai_nhan_thieu_thi_cong_no_giam_theo_so_thuc_nhan(client):
    """Đường CŨ (mark-received, KHÔNG đợt giao): khai nhận 800/1000 ⇒ nợ 1,76tr chứ không 2,2tr.

    Vế này vốn nằm trong `test_khai_nhan_thieu_thi_no_giam_va_chan_lap_phieu_vuot`. Test đó nay
    dựng bằng ĐỢT GIAO (luật 09/08/2026 bắt phiếu thanh toán phải gắn đợt), nên nhánh
    `da_giao is None` của `purchase_money` — dùng cho mọi đơn CHƯA có đợt — mất người canh.

    Kiểm bằng đột biến: đổi nhánh đó thành `gia_tri_da_giao = total` mà cả suite vẫn xanh, tức là
    công nợ đơn cũ có thể âm thầm nhảy từ 1,76tr lên 2,2tr không ai biết. Test này bịt chỗ đó."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Don Cu Giao Thieu")
    don = _don(client, headers, supplier["id"])
    sau = _ve_hang(
        client, headers, don["id"],
        lines=[{"line_id": don["lines"][0]["id"], "received_quantity": 800}],
    )
    assert sau["total_estimate"] == 2_200_000, "giá trị ĐƠN ĐẶT không đổi"
    assert sau["received_total"] == 1_760_000
    assert sau["outstanding_amount"] == 1_760_000

    muc = next(m for m in _cong_no(client, headers)["items"] if m["supplier_id"] == supplier["id"])
    assert muc["total_due"] == 1_760_000


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
    """Đơn KHÔNG theo đợt giao (sửa số thực nhận chỉ có ở đường cũ) nên tiền ra bằng phiếu ĐẶT CỌC
    — khai cọc dự kiến 2,2tr trước cho hợp luật 09/08/2026."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Sua Xuong")
    don = _don(client, headers, supplier["id"], coc=2_200_000)
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
    don = _don(client, headers, supplier["id"], coc=1_000_000)
    _ve_hang(client, headers, don["id"])
    _phieu_chi(client, headers, don["id"], 1_000_000)

    r = client.post(
        f"/api/purchase-requests/{don['id']}/undo-received",
        json={"reason": "Thử lùi"},
        headers=headers,
    )
    assert r.status_code == 409, r.text
    assert "ĐÃ CHI" in r.json()["detail"]


def test_huy_phieu_chi_xong_thi_lui_duoc(client):
    """Từ 06/08/2026 không còn trạng thái "chờ chi" — lập phiếu là tiền đã ra.

    Nên đường duy nhất để lùi một đơn đã có phiếu chi là HUỶ phiếu chi trước (ghi nhận nhầm), rồi
    mới lùi. Giữ được cửa sửa sai mà không cho ai lùi trạng thái khi tiền đang nằm ngoài két."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Lui Sau Huy")
    don = _don(client, headers, supplier["id"], coc=1_000_000)
    _ve_hang(client, headers, don["id"])
    phieu = _phieu_chi(client, headers, don["id"], 1_000_000)

    assert client.post(
        f"/api/accounting/payment-vouchers/{phieu['id']}/cancel",
        json={"reason": "Lập nhầm"},
        headers=headers,
    ).status_code == 200

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


# --- hạn trả: đã chuyển từ phiếu chi lên ĐỢT GIAO --------------------------


def test_phieu_chi_khong_con_doi_han_tra(client):
    """Hạn trả trên phiếu chi thành DORMANT từ 06/08/2026.

    Phiếu chi là tiền ĐÃ RA — nó không có hạn để mà trễ. Hạn trả nay thuộc về đợt giao (ưu tiên
    ngày hóa đơn + số ngày NCC cho nợ), vì đó mới là chỗ món nợ phát sinh và cần bị canh. Bắt hạn ở đây nữa là bắt
    kế toán gõ một con số không ai đọc."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Khong Doi Han")
    don = _don(client, headers, supplier["id"], coc=1_000_000)
    _ve_hang(client, headers, don["id"])

    r = client.post(
        "/api/accounting/payment-vouchers",
        json={
            "purchase_request_id": don["id"],
            "voucher_type": "cash",
            "payment_stage": "advance",
            "voucher_date": _hom_nay().isoformat(),
            "amount": 1_000_000,
            "currency": "VND",
            "exchange_rate": 1,
            "content": "Trả tiền giấy",
            "cash_recipient_name": "Nguyễn Lan",
            "cash_recipient_address": "Hà Nội",
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "paid"


def test_don_cu_khong_co_dot_giao_van_hien_no_o_muc_phieu(client):
    """Phiếu lập TRƯỚC 06/08/2026 không có đợt giao nào.

    Nợ của nó không quy được về đợt nên hiện ở mức PHIẾU, và vì không có hạn trả thì KHÔNG được
    đếm vào Quá hạn — nhưng vẫn phải gắn cờ `chua_dat_han` để giao diện lôi lên đầu. Đây chính là
    cầu tương thích ngược: đơn cũ giữ nguyên từng đồng, không cần backfill."""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Don Cu")
    don = _don(client, headers, supplier["id"])
    _ve_hang(client, headers, don["id"])

    chi_tiet = _cong_no_ncc(client, headers, supplier["id"])
    assert len(chi_tiet["items"]) == 1
    dong = chi_tiet["items"][0]
    assert dong["delivery_id"] is None, "đơn cũ không có đợt nào"
    assert dong["code"] == don["code"]
    assert dong["con_no"] == 2_200_000
    assert dong["chua_dat_han"] is True
    assert dong["overdue_days"] == 0
    assert chi_tiet["overdue_amount"] == 0


def test_chot_ngay_chi_chan_cai_vo_ly_khong_chan_qua_khu(client):
    """Quá khứ là HỢP LỆ, cố ý không chặn.

    Hoá đơn về muộn ⇒ phiếu phải mang ngày chi tiêu thật mới vào đúng kỳ kế toán. Ép sang hôm nay
    là làm sai kỳ.

    Chỉ chặn hai thứ vô lý: chứng từ ở tương lai, hoá đơn ở tương lai. (Hạn trả đã rời khỏi phiếu
    chi từ 06/08/2026 — nó thuộc về đợt giao.)"""
    headers = _headers(client)
    supplier = _supplier(client, headers, name="NCC Chot Ngay")
    # Khai cọc dư sức cho cả ba lần thử 100k — để mỗi phiếu hỏng đúng vì NGÀY, không phải vì trần.
    don = _don(client, headers, supplier["id"], coc=500_000)
    _ve_hang(client, headers, don["id"])
    hom_nay = _hom_nay()

    def _lap(**doi):
        payload = {
            "purchase_request_id": don["id"],
            "voucher_type": "cash",
            "payment_stage": "advance",
            "voucher_date": hom_nay.isoformat(),
            "amount": 100_000,
            "currency": "VND",
            "exchange_rate": 1,
            "content": "Trả tiền giấy",
            "cash_recipient_name": "Nguyễn Lan",
            "cash_recipient_address": "Hà Nội",
        }
        payload.update(doi)
        return client.post("/api/accounting/payment-vouchers", json=payload, headers=headers)

    # HỢP LỆ: ngày chứng từ ở quá khứ — khoản đã chi từ tháng trước, nhập bù.
    cu = _lap(voucher_date=(hom_nay - timedelta(days=40)).isoformat())
    assert cu.status_code == 201, cu.text
    assert cu.json()["paid_at"].startswith((hom_nay - timedelta(days=40)).isoformat())

    tuong_lai = _lap(voucher_date=(hom_nay + timedelta(days=1)).isoformat())
    assert tuong_lai.status_code == 422 and "tương lai" in tuong_lai.json()["detail"]

    hd_tuong_lai = _lap(invoice_date=(hom_nay + timedelta(days=1)).isoformat())
    assert hd_tuong_lai.status_code == 422 and "hóa đơn" in hd_tuong_lai.json()["detail"]


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
    don = _don(client, headers, supplier["id"], coc=2_200_000)
    _ve_hang(client, headers, don["id"])
    phieu = _phieu_chi(client, headers, don["id"], 2_200_000)

    # Đẩy lần chi lùi về 6 tháng trước — ra NGOÀI kỳ 3 tháng.
    db = SessionLocal()
    try:
        cu = _hom_nay() - timedelta(days=180)
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
    assert muc["no_han_amount"] == 2_200_000


# --- quyền -----------------------------------------------------------------


def test_khong_co_quyen_ke_toan_thi_khong_xem_duoc_cong_no(client):
    token = _token_vai("cn-ngoai-ke-toan", module="thu_mua", can_read=True)
    r = client.get("/api/accounting/payables", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403, r.text
