"""Accounting purchase inbox, Phiếu chi and UNC integration tests.

HAI LUẬT chi phối mọi ca dựng dữ liệu ở đây (chủ chốt 09/08/2026):

- Phiếu **THANH TOÁN** (`payment_stage != "advance"`) bắt buộc gắn một ĐỢT GIAO có thật.
- Phiếu **ĐẶT CỌC** (`advance`) bắt buộc phiếu mua đã khai CỌC DỰ KIẾN, và trần cọc = cọc dự kiến
  − cọc đã chi. `_cash_payload()` mặc định là phiếu đặt cọc, nên `_purchase()` khai sẵn cọc dự kiến
  bằng giá trị đơn (2.200.000đ) — khai lúc còn nháp, vì duyệt xong là khoá.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from app.db import SessionLocal
from app.models.role import SCOPE_ALL
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password


def _headers(client) -> dict[str, str]:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _supplier(client, headers) -> dict:
    response = client.post(
        "/api/suppliers",
        json={
            "name": "Công ty Giấy Kế Toán",
            "tax_code": "0108888888",
            "phone": "0901888888",
            "email": "accounting-supplier@example.com",
            "address": "18 Nguyễn Trãi, Hà Nội",
            "contact_name": "Nguyễn Lan",
            "supplier_group": "paper",
            # Dòng vật tư phải có trong danh mục mặt hàng của một NCC đang hoạt động
            # (`purchase_service._clean_department_lines` → `suppliers.has_active_item`), nếu không
            # thì YCMH bị chặn 422 ngay từ bước đầu. Tên phải khớp đúng tên dùng ở `_purchase`.
            "items": [
                {"item_name": "Giấy Duplex", "unit": "tờ", "unit_price": 2200, "vat_percent": 8}
            ],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _needed_date(days: int = 30) -> str:
    """Ngày cần hàng phải >= hôm nay (`purchase_service._business_today`, giờ VN). Cắm cứng một
    ngày cụ thể là tự hẹn giờ cho test vỡ — cả file này từng đỏ vì `2026-07-20` trôi vào quá khứ.
    Đệm 30 ngày nên chênh múi giờ CI (UTC) với VN không đụng tới."""
    return (date.today() + timedelta(days=days)).isoformat()


def _khai_coc(client, headers, purchase_id: int, so_tien: int) -> dict:
    """Khai CỌC DỰ KIẾN — bắt buộc trước khi lập bất kỳ phiếu ĐẶT CỌC nào (09/08/2026).

    Gọi khi phiếu còn NHÁP: cọc dự kiến khoá sau khi duyệt (đó là con số người duyệt đã đồng ý)."""
    r = client.put(
        f"/api/purchase-requests/{purchase_id}/contract",
        json={"contract_number": None, "deposit_expected": so_tien},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["deposit_expected"] == so_tien
    return r.json()


def _purchase(client, headers, supplier_id: int, *, coc: int = 2_200_000) -> tuple[dict, dict]:
    """PMH 1.000 tờ × 2.200đ = 2.200.000đ, đã duyệt, đã khai cọc dự kiến `coc`.

    `coc` mặc định bằng đúng giá trị đơn để mọi ca cũ giữ nguyên con số; `coc=0` = KHÔNG khai, dùng
    cho ca thử chặn."""
    source = client.post(
        "/api/department-purchase-requests",
        json={
            "source_type": "kinh_doanh",
            "purpose": "Mua giấy cho đơn in",
            "needed_date": _needed_date(),
            "lines": [{"item_name": "Giấy Duplex", "unit": "tờ", "quantity": 1000}],
        },
        headers=headers,
    )
    assert source.status_code == 201, source.text
    source_body = source.json()
    purchase = client.post(
        "/api/purchase-requests",
        json={
            "supplier_id": supplier_id,
            "source_request_ids": [source_body["id"]],
            "purpose": "Mua giấy cho đơn in",
            "needed_date": _needed_date(),
            "lines": [
                {
                    "item_name": "Giấy Duplex",
                    "unit": "tờ",
                    "quantity": 1000,
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
    submitted = client.post(f"/api/purchase-requests/{body['id']}/submit", headers=headers)
    assert submitted.status_code == 200, submitted.text
    _duyet(client, body["id"])
    return client.get(f"/api/purchase-requests/{body['id']}", headers=headers).json(), source_body


def _duyet(client, purchase_id: int) -> None:
    """Duyệt PMH bằng tài khoản KHÁC người lập.

    Từ 04/08/2026: (a) đường gộp "duyệt + lập phiếu chi một cú bấm" đã bỏ — kế toán chỉ lập phiếu
    chi cho PMH ĐÃ DUYỆT; (b) người lập không tự duyệt được phiếu của mình. Nên test phải có người
    duyệt riêng, đúng như ngoài đời: giám đốc duyệt, kế toán mới viết phiếu chi.
    """
    db = SessionLocal()
    try:
        users = UserRepository(db)
        u = users.get_by_username("acct-approver")
        if u is None:
            bgd = DepartmentRepository(db).get_by_name("Ban giám đốc")
            roles = RoleRepository(db)
            role = roles.create(name="Duyet PMH cho ke toan", department_id=bgd.id)
            # Duyệt PMH dời sang khoá `ke_toan` ngày 11/08/2026 (nút chỉ có ở màn Đơn mua hàng
            # bên Kế toán). Vẫn cấp `thu_mua:read` để người duyệt đọc được phiếu trước khi ký.
            roles.set_permission(role_id=role.id, module_key="ke_toan",
                                 can_read=True, can_approve=True, scope=SCOPE_ALL)
            roles.set_permission(role_id=role.id, module_key="thu_mua",
                                 can_read=True, scope=SCOPE_ALL)
            u = users.create(username="acct-approver", name="GD Duyet",
                             password_hash=hash_password("x"))
            users.set_assignment(u, department_id=bgd.id, role_id=role.id, is_active=True)
        token = create_access_token(str(u.id))
    finally:
        db.close()
    r = client.post(f"/api/purchase-requests/{purchase_id}/approve",
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text


def _cash_payload(amount: int) -> dict:
    return {
        "voucher_type": "cash",
        "payment_stage": "advance",
        "voucher_date": "2026-07-10",
        "planned_payment_date": "2026-07-11",
        "amount": amount,
        "currency": "VND",
        "exchange_rate": 1,
        "content": "Tạm ứng mua giấy",
        "cash_recipient_name": "Nguyễn Lan",
        "cash_recipient_address": "18 Nguyễn Trãi, Hà Nội",
    }


def _bank_accounts(client, headers, supplier_id: int) -> tuple[dict, dict]:
    company = client.post(
        "/api/accounting/company-bank-accounts",
        json={
            "account_holder": "CÔNG TY SAO VIỆT NHẬT",
            "account_number": "123456789",
            "bank_name": "Vietcombank",
            "bank_branch": "Hà Nội",
            "currency": "VND",
            "is_default": True,
        },
        headers=headers,
    )
    assert company.status_code == 201, company.text
    beneficiary = client.post(
        "/api/accounting/supplier-bank-accounts",
        json={
            "supplier_id": supplier_id,
            "account_holder": "CÔNG TY GIẤY KẾ TOÁN",
            "account_number": "987654321",
            "bank_name": "BIDV",
            "bank_branch": "Hà Nội",
            "currency": "VND",
            "is_default": True,
        },
        headers=headers,
    )
    assert beneficiary.status_code == 201, beneficiary.text
    return company.json(), beneficiary.json()


def test_approve_and_create_cash_voucher_tracks_partial_payment(client):
    headers = _headers(client)
    supplier = _supplier(client, headers)
    purchase, source = _purchase(client, headers, supplier["id"])

    created = client.post(
        "/api/accounting/payment-vouchers",
        json={**_cash_payload(1_000_000), "purchase_request_id": purchase['id']},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    voucher = created.json()
    assert re.fullmatch(r"PC-\d{6}-[A-Z0-9]{4}", voucher["code"])
    assert voucher["status"] == "paid"
    assert voucher["amount_vnd"] == 1_000_000
    assert voucher["purchase_request_code"] == purchase["code"]
    assert voucher["purchase_created_by_name"] == "Admin"
    assert voucher["source_request_codes"] == [source["code"]]

    # Lập phiếu chi ĐÃ LÀ hành vi chi tiền (06/08/2026) — không còn bước "xác nhận đã chi",
    # nên tiền vào `paid_amount` ngay chứ không nằm ở rổ "chờ chi" nào cả.
    refreshed = client.get(f"/api/purchase-requests/{purchase['id']}", headers=headers).json()
    assert refreshed["status"] == "approved"
    assert refreshed["paid_amount"] == 1_000_000
    assert refreshed["net_paid"] == 1_000_000
    # Hàng CHƯA về ⇒ chưa nợ ai đồng nào, dù đã ứng trước 1 triệu.
    assert refreshed["gia_tri_da_giao"] == 0
    assert refreshed["outstanding_amount"] == 0
    # Trần ĐẶT CỌC còn lại = CỌC DỰ KIẾN đã khai (2,2tr) − cọc đã chi (1tr) — 09/08/2026.
    assert refreshed["tran_dat_coc"] == 1_200_000

    found = client.get(f"/api/accounting/payment-vouchers?q={source['code']}", headers=headers)
    assert found.status_code == 200
    body = found.json()
    assert body["total"] == 1
    # Tổng API-level: cộng trên toàn bộ kết quả khớp bộ lọc, không phải trang hiện tại.
    assert body["total_paid_amount"] == 1_000_000
    assert body["total_waiting_amount"] == 0
    assert body["total_receipt_received_amount"] == 0
    # Dải nhóm PMH: "Đã chi" của cả PMH nằm trên từng phiếu chi.
    assert body["items"][0]["purchase_paid_amount"] == 1_000_000


def test_unc_nhap_truc_tiep_tai_khoan_thu_huong_va_chan_chi_vuot(client):
    headers = _headers(client)
    supplier = _supplier(client, headers)
    purchase, _ = _purchase(client, headers, supplier["id"])
    # `_purchase()` đã duyệt sẵn (bằng tài khoản khác người lập) — duyệt lại là 409.
    company, _beneficiary = _bank_accounts(client, headers, supplier["id"])

    payload = {
        "purchase_request_id": purchase["id"],
        "voucher_type": "bank_transfer",
        "payment_stage": "advance",
        "voucher_date": "2026-07-10",
        "planned_payment_date": "2026-07-25",
        "amount": 1_500_000,
        "currency": "VND",
        "exchange_rate": 1,
        "content": "Chuyển khoản mua giấy",
        "company_bank_account_id": company["id"],
        # NCC không còn có danh mục tài khoản: thông tin thụ hưởng đi thẳng vào chứng từ.
        "beneficiary_account_holder": "CÔNG TY GIẤY KẾ TOÁN",
        "beneficiary_account_number": "987654321",
        "beneficiary_bank_name": "BIDV",
        "beneficiary_bank_branch": "Hà Nội",
        "bank_fee_bearer": "payer",
    }
    missing_beneficiary = client.post(
        "/api/accounting/payment-vouchers",
        json={**payload, "beneficiary_account_number": ""},
        headers=headers,
    )
    assert missing_beneficiary.status_code == 422
    assert "số tài khoản" in missing_beneficiary.json()["detail"]

    created = client.post("/api/accounting/payment-vouchers", json=payload, headers=headers)
    assert created.status_code == 201, created.text
    voucher = created.json()
    assert re.fullmatch(r"UNC-\d{6}-[A-Z0-9]{4}", voucher["code"])
    assert voucher["company_account_number"] == "123456789"
    assert voucher["beneficiary_account_number"] == "987654321"
    assert voucher["beneficiary_account_holder"] == "CÔNG TY GIẤY KẾ TOÁN"
    assert voucher["beneficiary_bank_name"] == "BIDV"
    assert voucher["supplier_bank_account_id"] is None

    assert voucher["status"] == "paid"

    too_much = {**payload, "amount": 700_001}
    over = client.post("/api/accounting/payment-vouchers", json=too_much, headers=headers)
    assert over.status_code == 422
    assert "vượt quá" in over.json()["detail"]


def test_tra_truoc_khi_hang_ve_phai_di_duong_dat_coc(client):
    """Hàng chưa về thì CHƯA NỢ ai — phiếu THANH TOÁN bị chặn, phải đi đường ĐẶT CỌC.

    Trần của hai loại phiếu khác nhau có chủ ý (06/08/2026 §5.4): thanh toán trần theo CÔNG NỢ đã
    phát sinh, đặt cọc trần theo CỌC DỰ KIẾN đã khai (đổi gốc 09/08/2026, trước đó là giá trị đơn).
    Nhập nhèm hai đường là kế toán trả đủ tiền cho đơn mà hàng còn nằm ở kho NCC, rồi màn Công nợ
    báo nợ 0 trong khi phiếu chi đã viết đủ — hai con số chửi nhau.

    Từ 09/08/2026 phiếu thanh toán bị chặn SỚM HƠN một nhịp: hàng chưa về thì đơn chưa có đợt giao
    nào, mà thanh toán bắt buộc gắn đợt ⇒ chặn ngay ở cửa đó, kèm lời chỉ đường sang phiếu đặt cọc."""
    headers = _headers(client)
    supplier = _supplier(client, headers)
    purchase, _ = _purchase(client, headers, supplier["id"])

    chan = client.post(
        "/api/accounting/payment-vouchers",
        json={
            "purchase_request_id": purchase["id"],
            **_cash_payload(2_200_000),
            "payment_stage": "final",
        },
        headers=headers,
    )
    assert chan.status_code == 422
    assert "chưa có đợt giao" in chan.json()["detail"]
    assert "ĐẶT CỌC" in chan.json()["detail"]

    # Cùng số tiền, đi đường đặt cọc thì qua — và ra thẳng trạng thái "đã chi".
    coc = client.post(
        "/api/accounting/payment-vouchers",
        json={
            "purchase_request_id": purchase["id"],
            **_cash_payload(2_200_000),
            "payment_stage": "advance",
        },
        headers=headers,
    )
    assert coc.status_code == 201, coc.text
    assert coc.json()["payment_stage"] == "advance"
    assert coc.json()["status"] == "paid"


def test_phieu_dat_coc_doi_khai_coc_du_kien_truoc(client):
    """Đường ĐẶT CỌC không phải cửa mở toang: chưa khai Cọc dự kiến trên phiếu mua thì chặn 422
    (luật 09/08/2026).

    Đây là vế thứ hai của test ngay trên: chặn thanh toán mà để cọc chi thoải mái tới giá trị đơn
    thì "đi đường đặt cọc" trở thành cách lách, ứng trước bao nhiêu cũng được."""
    headers = _headers(client)
    supplier = _supplier(client, headers)
    purchase, _ = _purchase(client, headers, supplier["id"], coc=0)  # KHÔNG khai cọc
    assert purchase["deposit_expected"] == 0
    assert purchase["tran_dat_coc"] == 0

    chan = client.post(
        "/api/accounting/payment-vouchers",
        json={**_cash_payload(100_000), "purchase_request_id": purchase["id"]},
        headers=headers,
    )
    assert chan.status_code == 422
    assert "Cọc dự kiến" in chan.json()["detail"]
    # Chặn thật — không phiếu chi nào được đẻ ra.
    ds = client.get(f"/api/accounting/payment-vouchers?q={purchase['code']}", headers=headers)
    assert ds.json()["total"] == 0


def test_foreign_currency_reserves_vnd_and_blocks_purchase_cancellation(client):
    headers = _headers(client)
    supplier = _supplier(client, headers)
    purchase, _ = _purchase(client, headers, supplier["id"])
    # `_purchase()` đã duyệt sẵn (bằng tài khoản khác người lập) — duyệt lại là 409.

    payload = {
        "purchase_request_id": purchase["id"],
        **_cash_payload(100),
        "currency": "USD",
        "exchange_rate": 20_000,
    }
    created = client.post("/api/accounting/payment-vouchers", json=payload, headers=headers)
    assert created.status_code == 201, created.text
    voucher = created.json()
    assert voucher["amount"] == 100
    assert voucher["amount_vnd"] == 2_000_000

    refreshed = client.get(f"/api/purchase-requests/{purchase['id']}", headers=headers).json()
    assert refreshed["paid_amount"] == 2_000_000
    # Cọc dự kiến khai 2,2tr, phiếu cọc ngoại tệ quy đổi 2tr ⇒ còn 200k được ứng tiếp.
    assert refreshed["tran_dat_coc"] == 200_000

    blocked = client.post(
        f"/api/purchase-requests/{purchase['id']}/cancel",
        json={"reason": "Không mua nữa"},
        headers=headers,
    )
    assert blocked.status_code == 409
    assert "chứng từ thanh toán" in blocked.json()["detail"]

    cancelled_voucher = client.post(
        f"/api/accounting/payment-vouchers/{voucher['id']}/cancel",
        json={"reason": "Lập nhầm tỷ giá"},
        headers=headers,
    )
    assert cancelled_voucher.status_code == 200, cancelled_voucher.text
    cancelled_purchase = client.post(
        f"/api/purchase-requests/{purchase['id']}/cancel",
        json={"reason": "Không mua nữa"},
        headers=headers,
    )
    assert cancelled_purchase.status_code == 200, cancelled_purchase.text


def _accounting_user_token(*, approve: bool, manage_status: bool = False) -> str:
    db = SessionLocal()
    try:
        departments = DepartmentRepository(db)
        department = departments.get_by_name("Kế toán")
        roles = RoleRepository(db)
        role = roles.create(
            name="Kế toán duyệt" if approve else "Kế toán chỉ xem",
            department_id=department.id,
        )
        # Từ 10/08/2026 phân hệ Kế toán tách 6 màn, mỗi màn một khoá. Một người kế toán ngoài đời
        # chạm cả 6 nên fixture cấp cả 6 — đúng như migration 0178 sao chép quyền cũ sang.
        # ⚠️ Động từ ĐỔI TÊN: LẬP phiếu nay là `can_create` (trước núp dưới `can_approve`), nên
        # `approve=True` của fixture phải đổ vào `can_create` chứ không thì test dựng ra một
        # người "được duyệt mà không lập được phiếu" — không mô tả ai ngoài đời.
        for khoa in ("ke_toan", "cong_no_phai_tra", "cong_no_phai_thu", "tk_ngan_hang"):
            roles.set_permission(role_id=role.id, module_key=khoa, can_read=True,
                                 can_update=approve, scope=SCOPE_ALL)
        for khoa in ("phieu_chi", "phieu_thu"):
            roles.set_permission(
                role_id=role.id,
                module_key=khoa,
                can_read=True,
                can_create=approve,
                can_approve=approve,
                can_manage_status=manage_status,
                scope=SCOPE_ALL,
            )
        users = UserRepository(db)
        user = users.create(
            username="accounting-approver" if approve else "accounting-reader",
            name="Kế toán duyệt" if approve else "Kế toán xem",
            password_hash=hash_password("x"),
        )
        users.set_assignment(
            user, department_id=department.id, role_id=role.id, is_active=True
        )
        return create_access_token(str(user.id))
    finally:
        db.close()


def test_doc_no_shared_counter_across_voucher_types(client):
    """Số IN trên mẫu: PC00001, PC00002… — tiền mặt và UNC dùng CHUNG một bộ đếm
    (cùng quyển phiếu chi), trong khi mã nội bộ vẫn PC-…/UNC-…"""
    headers = _headers(client)
    supplier = _supplier(client, headers)
    purchase, _ = _purchase(client, headers, supplier["id"])
    company, _beneficiary = _bank_accounts(client, headers, supplier["id"])

    cash = client.post(
        "/api/accounting/payment-vouchers",
        json={**_cash_payload(500_000), "purchase_request_id": purchase['id']},
        headers=headers,
    )
    assert cash.status_code == 201, cash.text
    assert cash.json()["doc_no"] == "PC00001"
    assert cash.json()["code"].startswith("PC-")

    bank = client.post(
        "/api/accounting/payment-vouchers",
        json={
            "purchase_request_id": purchase["id"],
            "voucher_type": "bank_transfer",
            # Hàng chưa về ⇒ vẫn là tiền ứng trước. `partial` bị chặn vì chưa phát sinh nợ.
            "payment_stage": "advance",
            "voucher_date": "2026-07-10",
            "amount": 400_000,
            "currency": "VND",
            "exchange_rate": 1,
            "content": "Chuyển khoản đợt 2",
            "company_bank_account_id": company["id"],
            "beneficiary_account_holder": "CÔNG TY GIẤY KẾ TOÁN",
            "beneficiary_account_number": "987654321",
            "beneficiary_bank_name": "BIDV",
            "bank_fee_bearer": "payer",
        },
        headers=headers,
    )
    assert bank.status_code == 201, bank.text
    # Chung bộ đếm → PC00002 dù mã nội bộ là UNC-…
    assert bank.json()["doc_no"] == "PC00002"
    assert bank.json()["code"].startswith("UNC-")


def test_receipt_doc_no_has_own_counter(client):
    headers = _headers(client)
    supplier = _supplier(client, headers)
    purchase, _ = _purchase(client, headers, supplier["id"])
    voucher = _paid_cash_voucher(client, headers, purchase["id"], 2_200_000)
    assert voucher["doc_no"] == "PC00001"

    receipt = client.post(
        f"/api/accounting/payment-vouchers/{voucher['id']}/receipts",
        json=_receipt_payload(300_000),
        headers=headers,
    )
    assert receipt.status_code == 201, receipt.text
    assert receipt.json()["doc_no"] == "PT00001"  # bộ đếm riêng, không nối tiếp PC


def test_lap_phieu_chi_loi_thi_khong_de_lai_phieu_mo_coi(client, monkeypatch):
    """Lập phiếu chi hỏng giữa chừng thì KHÔNG được để lại phiếu chi dở dang.

    Bản cũ của test này canh một hazard của đường GỘP "duyệt + lập phiếu chi một cú bấm": lưu phiếu
    lỗi mà PMH đã bị đẩy sang 'đã duyệt' thì phiếu kẹt ở trạng thái duyệt rồi mà không có chứng từ.
    Đường gộp đã bỏ hẳn (04/08/2026) nên hazard đó không còn: duyệt là bước riêng, lập phiếu chi
    KHÔNG đụng tới trạng thái PMH. Giờ canh vế còn ý nghĩa — hỏng thì không đẻ ra phiếu chi nào."""
    from app.repositories.accounting_repo import AccountingRepository

    headers = _headers(client)
    supplier = _supplier(client, headers)
    purchase, _ = _purchase(client, headers, supplier["id"])

    def boom(self, voucher):
        raise RuntimeError("DB nổ giữa chừng")

    monkeypatch.setattr(AccountingRepository, "save_voucher", boom)
    try:
        client.post(
            "/api/accounting/payment-vouchers",
            json={**_cash_payload(500_000), "purchase_request_id": purchase['id']},
            headers=headers,
        )
    except RuntimeError:
        pass  # TestClient dội lỗi ra — đúng kỳ vọng
    monkeypatch.undo()

    # PMH giữ nguyên 'đã duyệt' — lập phiếu chi không đụng trạng thái nó.
    refreshed = client.get(f"/api/purchase-requests/{purchase['id']}", headers=headers)
    assert refreshed.json()["status"] == "approved"
    # Và không có phiếu chi mồ côi nào được tạo.
    ds = client.get(f"/api/accounting/payment-vouchers?q={purchase['code']}", headers=headers)
    assert ds.json()["total"] == 0


def test_search_by_doc_no_and_debit_credit_roundtrip(client):
    headers = _headers(client)
    supplier = _supplier(client, headers)
    purchase, _ = _purchase(client, headers, supplier["id"])
    created = client.post(
        "/api/accounting/payment-vouchers",
        json={**{**_cash_payload(500_000), "debit_account": "242, 1331", "credit_account": "1111"}, "purchase_request_id": purchase['id']},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    voucher = created.json()
    assert voucher["debit_account"] == "242, 1331"
    assert voucher["credit_account"] == "1111"

    # Tra cứu theo số in trên phiếu (kể cả gõ chữ thường).
    for term in (voucher["doc_no"], voucher["doc_no"].lower()):
        found = client.get(f"/api/accounting/payment-vouchers?q={term}", headers=headers)
        assert found.status_code == 200
        assert [row["id"] for row in found.json()["items"]] == [voucher["id"]]

    # PHIẾU ĐÃ LẬP THÌ KHÔNG SỬA (chủ chốt 07/08/2026): phiếu chi phát hành ra là tiền đã rời két,
    # sửa nó là làm tờ giấy đang nằm ở chỗ NCC khác với bản trong máy. Sai thì HUỶ rồi lập lại —
    # dấu vết còn đủ hai bản. Endpoint PUT đã gỡ hẳn.
    updated = client.put(
        f"/api/accounting/payment-vouchers/{voucher['id']}",
        json={
            "purchase_request_id": purchase["id"],
            **_cash_payload(500_000),
            "debit_account": "156",
        },
        headers=headers,
    )
    assert updated.status_code == 405, updated.text

    # Còn sửa được đúng một thứ: ĐÍNH KÈM tài liệu — hoá đơn/UNC thường về sau khi chi.
    tep = client.post(
        f"/api/accounting/payment-vouchers/{voucher['id']}/attachments",
        files={"file": ("hd.png", b"anh-hoa-don", "image/png")},
        headers=headers,
    )
    assert tep.status_code == 201, tep.text


def test_voucher_accepts_payload_without_accounts_and_rejects_too_long(client):
    headers = _headers(client)
    supplier = _supplier(client, headers)
    purchase, _ = _purchase(client, headers, supplier["id"])

    # Payload cũ (không có debit/credit) vẫn phải chạy.
    ok = client.post(
        "/api/accounting/payment-vouchers",
        json={**_cash_payload(500_000), "purchase_request_id": purchase['id']},
        headers=headers,
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["debit_account"] is None

    too_long = client.post(
        "/api/accounting/payment-vouchers",
        json={
            "purchase_request_id": purchase["id"],
            **_cash_payload(100_000),
            "debit_account": "x" * 65,
        },
        headers=headers,
    )
    assert too_long.status_code == 422


def test_receipt_payer_address_and_accounts_roundtrip(client):
    headers = _headers(client)
    supplier = _supplier(client, headers)
    purchase, _ = _purchase(client, headers, supplier["id"])
    voucher = _paid_cash_voucher(client, headers, purchase["id"], 2_200_000)

    created = client.post(
        f"/api/accounting/payment-vouchers/{voucher['id']}/receipts",
        json={
            **_receipt_payload(300_000),
            "payer_address": "36/30/27 Bùi Tư Toàn, Phường An Lạc, TP Hồ Chí Minh",
            "debit_account": "1111",
            "credit_account": "141",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["payer_address"].startswith("36/30/27 Bùi Tư Toàn")
    assert body["debit_account"] == "1111"
    assert body["credit_account"] == "141"

    # Payload không có 3 trường mới vẫn hợp lệ.
    plain = client.post(
        f"/api/accounting/payment-vouchers/{voucher['id']}/receipts",
        json=_receipt_payload(100_000),
        headers=headers,
    )
    assert plain.status_code == 201, plain.text
    assert plain.json()["payer_address"] is None


def test_cancelled_voucher_keeps_doc_no(client):
    headers = _headers(client)
    supplier = _supplier(client, headers)
    purchase, _ = _purchase(client, headers, supplier["id"])
    created = client.post(
        "/api/accounting/payment-vouchers",
        json={**_cash_payload(500_000), "purchase_request_id": purchase['id']},
        headers=headers,
    ).json()
    cancelled = client.post(
        f"/api/accounting/payment-vouchers/{created['id']}/cancel",
        json={"reason": "Lập nhầm"},
        headers=headers,
    )
    assert cancelled.status_code == 200
    # Phiếu hủy vẫn giữ số trong quyển (chuẩn kế toán VN).
    assert cancelled.json()["doc_no"] == created["doc_no"]


def _receipt_payload(amount: int, **overrides) -> dict:
    payload = {
        "payer_name": "Nguyễn Văn Mua",
        "receipt_method": "cash",
        "receipt_date": "2026-07-13",
        "amount": amount,
        "content": "Thu hồi tiền thừa mua giấy",
    }
    payload.update(overrides)
    return payload


def _paid_cash_voucher(client, headers, purchase_id: int, amount: int) -> dict:
    created = client.post(
        "/api/accounting/payment-vouchers",
        json={**_cash_payload(amount), "purchase_request_id": purchase_id},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    voucher = created.json()
    assert voucher["status"] == "paid"
    return voucher


def test_khong_lap_duoc_phieu_thu_tren_phieu_chi_da_huy(client):
    """Phiếu thu là tiền chi ra tiêu không hết nộp về — phải có phiếu chi GỐC còn hiệu lực.

    Trước 06/08/2026 luật này được canh bằng "chỉ phiếu `paid` mới lập phiếu thu được", vì phiếu mới
    lập nằm ở `waiting`. Nay phiếu lập ra ĐÃ LÀ `paid` nên ca cần canh chỉ còn phiếu đã HUỶ: gắn
    phiếu thu vào đó là đẻ một khoản thu không có gốc, cộng ngược thành nợ ảo."""
    headers = _headers(client)
    supplier = _supplier(client, headers)
    purchase, _ = _purchase(client, headers, supplier["id"])
    voucher = client.post(
        "/api/accounting/payment-vouchers",
        json={**_cash_payload(1_000_000), "purchase_request_id": purchase['id']},
        headers=headers,
    )
    assert voucher.status_code == 201, voucher.text
    vid = voucher.json()["id"]
    assert client.post(
        f"/api/accounting/payment-vouchers/{vid}/cancel",
        json={"reason": "Lập nhầm"},
        headers=headers,
    ).status_code == 200

    blocked = client.post(
        f"/api/accounting/payment-vouchers/{vid}/receipts",
        json=_receipt_payload(100_000),
        headers=headers,
    )
    assert blocked.status_code == 409


def test_receipt_cannot_exceed_voucher_amount(client):
    headers = _headers(client)
    supplier = _supplier(client, headers)
    purchase, _ = _purchase(client, headers, supplier["id"])
    voucher = _paid_cash_voucher(client, headers, purchase["id"], 2_200_000)

    over = client.post(
        f"/api/accounting/payment-vouchers/{voucher['id']}/receipts",
        json=_receipt_payload(2_300_000),
        headers=headers,
    )
    assert over.status_code == 422
    assert "vượt quá" in over.json()["detail"]

    first = client.post(
        f"/api/accounting/payment-vouchers/{voucher['id']}/receipts",
        json=_receipt_payload(300_000),
        headers=headers,
    )
    assert first.status_code == 201, first.text
    receipt = first.json()
    assert receipt["code"].startswith("PT-")
    assert receipt["status"] == "waiting_receipt"
    assert receipt["payment_voucher_code"] == voucher["code"]
    assert receipt["payer_name"] == "Nguyễn Văn Mua"

    # Phiếu thu đang chờ vẫn chiếm chỗ trong hạn mức thu.
    second_over = client.post(
        f"/api/accounting/payment-vouchers/{voucher['id']}/receipts",
        json=_receipt_payload(2_000_000),
        headers=headers,
    )
    assert second_over.status_code == 422

    # Update chính phiếu đó lên full số đã chi được (exclude self).
    full = client.put(
        f"/api/accounting/payment-receipts/{receipt['id']}",
        json=_receipt_payload(2_200_000),
        headers=headers,
    )
    assert full.status_code == 200, full.text
    assert full.json()["amount_vnd"] == 2_200_000


def test_receipt_received_reopens_purchase_available(client):
    """Phiếu thu ĐÃ THU hạ `net_paid` xuống — nhưng KHÔNG mở lại trần ĐẶT CỌC nữa.

    ⚠️ Ý ĐỒ NỬA SAU ĐÃ ĐỔI NGƯỢC (luật 09/08/2026), tên hàm giữ nguyên theo luật cũ để còn truy
    được: trước đó trần cọc = giá trị đơn − đã chi RÒNG, nên nộp lại 300k là mở lại đúng 300k quyền
    ứng trước. Nay trần cọc = CỌC DỰ KIẾN đã khai − cọc ĐÃ CHI, và "đã chi" đếm số thô trên phiếu
    cọc, không trừ phiếu thu. Tiền nộp lại vì thế không đẻ thêm quyền ứng trước — muốn ứng thêm thì
    phải có thoả thuận cọc mới, mà số đó đã khoá từ lúc duyệt.

    Vế còn nguyên giá trị: tiền đã về két thì không được biến thành NỢ ẢO."""
    headers = _headers(client)
    supplier = _supplier(client, headers)
    purchase, _ = _purchase(client, headers, supplier["id"])
    voucher = _paid_cash_voucher(client, headers, purchase["id"], 2_200_000)

    before = client.get(f"/api/purchase-requests/{purchase['id']}", headers=headers).json()
    # Đơn chưa về hàng nên chưa nợ; tiền ứng ra đã lấp trọn trần đặt cọc.
    assert before["tran_dat_coc"] == 0

    receipt = client.post(
        f"/api/accounting/payment-vouchers/{voucher['id']}/receipts",
        json=_receipt_payload(300_000),
        headers=headers,
    ).json()

    waiting_state = client.get(f"/api/purchase-requests/{purchase['id']}", headers=headers).json()
    assert waiting_state["tran_dat_coc"] == 0  # chờ thu: tiền chưa về
    assert waiting_state["receipt_received_amount"] == 0

    received = client.post(
        f"/api/accounting/payment-receipts/{receipt['id']}/mark-received",
        json={"bank_reference": None},
        headers=headers,
    )
    assert received.status_code == 200, received.text
    assert received.json()["status"] == "received"

    after = client.get(f"/api/purchase-requests/{purchase['id']}", headers=headers).json()
    assert after["paid_amount"] == 2_200_000  # số thô giữ nguyên
    assert after["receipt_received_amount"] == 300_000
    assert after["net_paid"] == 1_900_000
    # ĐỔI NGƯỢC 09/08/2026: tiền THU VỀ không mở lại trần đặt cọc — cọc dự kiến 2,2tr đã chi hết.
    assert after["tran_dat_coc"] == 0
    # Hàng vẫn chưa về nên vẫn chưa nợ ai — đây chính là ca "nợ ảo" của bản cũ:
    # trước 06/08/2026 chỗ này ra 300.000đ "còn nợ NCC" trong khi tiền đã về két.
    assert after["gia_tri_da_giao"] == 0
    assert after["outstanding_amount"] == 0

    voucher_after = client.get(
        f"/api/accounting/payment-vouchers/{voucher['id']}", headers=headers
    ).json()
    assert voucher_after["receipt_received_amount"] == 300_000
    assert voucher_after["receipt_pending_amount"] == 0

    listed = client.get(
        f"/api/accounting/payment-vouchers?q={voucher['code']}", headers=headers
    ).json()
    assert listed["total_paid_amount"] == 2_200_000
    assert listed["total_receipt_received_amount"] == 300_000

    # Và vì trần cọc không mở lại, phiếu cọc bổ sung 300k nay BỊ CHẶN (trước 09/08/2026 nó qua).
    topup = client.post(
        "/api/accounting/payment-vouchers",
        json={"purchase_request_id": purchase["id"], **_cash_payload(300_000)},
        headers=headers,
    )
    assert topup.status_code == 422, topup.text
    assert "đặt cọc" in topup.json()["detail"]
    over = client.post(
        "/api/accounting/payment-vouchers",
        json={"purchase_request_id": purchase["id"], **_cash_payload(1)},
        headers=headers,
    )
    assert over.status_code == 422


def test_receipt_payer_and_method_validation(client):
    headers = _headers(client)
    supplier = _supplier(client, headers)
    purchase, _ = _purchase(client, headers, supplier["id"])
    voucher = _paid_cash_voucher(client, headers, purchase["id"], 2_200_000)
    receipts_url = f"/api/accounting/payment-vouchers/{voucher['id']}/receipts"

    missing_payer = client.post(
        receipts_url, json=_receipt_payload(100_000, payer_name=" "), headers=headers
    )
    assert missing_payer.status_code == 422

    bank_missing_account = client.post(
        receipts_url,
        json=_receipt_payload(100_000, receipt_method="bank_transfer"),
        headers=headers,
    )
    assert bank_missing_account.status_code == 422

    company, _beneficiary = _bank_accounts(client, headers, supplier["id"])
    bank_ok = client.post(
        receipts_url,
        json=_receipt_payload(
            100_000, receipt_method="bank_transfer", company_bank_account_id=company["id"]
        ),
        headers=headers,
    )
    assert bank_ok.status_code == 201, bank_ok.text
    body = bank_ok.json()
    assert body["company_account_number"] == "123456789"

    missing_reference = client.post(
        f"/api/accounting/payment-receipts/{body['id']}/mark-received",
        json={"bank_reference": None},
        headers=headers,
    )
    assert missing_reference.status_code == 422
    received = client.post(
        f"/api/accounting/payment-receipts/{body['id']}/mark-received",
        json={"bank_reference": "VCB-BAOCO-001"},
        headers=headers,
    )
    assert received.status_code == 200, received.text
    assert received.json()["bank_reference"] == "VCB-BAOCO-001"


def test_receipt_update_cancel_lifecycle_and_listing(client):
    headers = _headers(client)
    supplier = _supplier(client, headers)
    purchase, _ = _purchase(client, headers, supplier["id"])
    voucher = _paid_cash_voucher(client, headers, purchase["id"], 2_200_000)
    receipts_url = f"/api/accounting/payment-vouchers/{voucher['id']}/receipts"

    receipt = client.post(receipts_url, json=_receipt_payload(500_000), headers=headers).json()
    updated = client.put(
        f"/api/accounting/payment-receipts/{receipt['id']}",
        json=_receipt_payload(700_000, payer_name="Trần Thị Nộp"),
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["amount_vnd"] == 700_000
    assert updated.json()["payer_name"] == "Trần Thị Nộp"

    cancelled = client.post(
        f"/api/accounting/payment-receipts/{receipt['id']}/cancel",
        json={"reason": "Lập nhầm số tiền"},
        headers=headers,
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"

    # Hủy xong thì hạn mức thu được trả lại — lập full số đã chi được.
    fresh = client.post(receipts_url, json=_receipt_payload(2_200_000), headers=headers)
    assert fresh.status_code == 201, fresh.text
    received = client.post(
        f"/api/accounting/payment-receipts/{fresh.json()['id']}/mark-received",
        json={"bank_reference": None},
        headers=headers,
    )
    assert received.status_code == 200

    # Đã thu rồi thì không sửa/hủy được nữa.
    assert (
        client.put(
            f"/api/accounting/payment-receipts/{fresh.json()['id']}",
            json=_receipt_payload(1_000_000),
            headers=headers,
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/accounting/payment-receipts/{fresh.json()['id']}/cancel",
            json={"reason": "thử hủy"},
            headers=headers,
        ).status_code
        == 409
    )

    # Danh sách: lọc theo mã PC nguồn + trạng thái.
    listed = client.get(
        f"/api/accounting/payment-receipts?q={voucher['code']}&status=received",
        headers=headers,
    )
    assert listed.status_code == 200
    codes = [row["code"] for row in listed.json()["items"]]
    assert codes == [fresh.json()["code"]]


def test_receipt_permissions(client):
    admin_headers = _headers(client)
    supplier = _supplier(client, admin_headers)
    purchase, _ = _purchase(client, admin_headers, supplier["id"])
    voucher = _paid_cash_voucher(client, admin_headers, purchase["id"], 2_200_000)

    reader_headers = {"Authorization": f"Bearer {_accounting_user_token(approve=False)}"}
    approver_headers = {"Authorization": f"Bearer {_accounting_user_token(approve=True)}"}

    assert (
        client.get("/api/accounting/payment-receipts", headers=reader_headers).status_code == 200
    )
    assert (
        client.post(
            f"/api/accounting/payment-vouchers/{voucher['id']}/receipts",
            json=_receipt_payload(100_000),
            headers=reader_headers,
        ).status_code
        == 403
    )
    created = client.post(
        f"/api/accounting/payment-vouchers/{voucher['id']}/receipts",
        json=_receipt_payload(100_000),
        headers=approver_headers,
    )
    assert created.status_code == 201, created.text
    # approve nhưng không có manage_status thì không xác nhận đã thu được.
    assert (
        client.post(
            f"/api/accounting/payment-receipts/{created.json()['id']}/mark-received",
            json={"bank_reference": None},
            headers=approver_headers,
        ).status_code
        == 403
    )


def test_vouchers_group_sort_keeps_same_pmh_adjacent(client):
    """sort=-group: phiếu cùng PMH đứng liền nhau, nhóm có phiếu mới nhất lên đầu."""
    headers = _headers(client)
    supplier = _supplier(client, headers)
    purchase_a, _ = _purchase(client, headers, supplier["id"])
    purchase_b, _ = _purchase(client, headers, supplier["id"])

    a1 = client.post(
        "/api/accounting/payment-vouchers",
        json={**_cash_payload(500_000), "purchase_request_id": purchase_a['id']},
        headers=headers,
    )
    assert a1.status_code == 201, a1.text
    b1 = client.post(
        "/api/accounting/payment-vouchers",
        json={**_cash_payload(400_000), "purchase_request_id": purchase_b['id']},
        headers=headers,
    )
    assert b1.status_code == 201, b1.text
    # Chi bổ sung cho PMH A SAU CÙNG — nhóm A phải nổi lên đầu, A1+A2 liền nhau.
    a2 = client.post(
        "/api/accounting/payment-vouchers",
        json={"purchase_request_id": purchase_a["id"], **_cash_payload(300_000)},
        headers=headers,
    )
    assert a2.status_code == 201, a2.text

    listed = client.get(
        "/api/accounting/payment-vouchers?sort=-group&size=50", headers=headers
    )
    assert listed.status_code == 200, listed.text
    codes = [row["code"] for row in listed.json()["items"]]
    expected = [a1.json()["code"], a2.json()["code"], b1.json()["code"]]
    assert codes == expected, codes
    assert all("T" in row["created_at"] for row in listed.json()["items"])

    filtered = client.get(
        "/api/accounting/payment-vouchers?sort=-group&status=paid&size=50",
        headers=headers,
    )
    assert filtered.status_code == 200
    assert [row["code"] for row in filtered.json()["items"]] == expected


def test_accounting_read_can_trace_department_requests(client):
    """Kế toán (chỉ ke_toan:read) truy vết được YCMH nguồn từ PMH/Phiếu chi."""
    admin_headers = _headers(client)
    supplier = _supplier(client, admin_headers)
    _, source = _purchase(client, admin_headers, supplier["id"])
    reader_headers = {"Authorization": f"Bearer {_accounting_user_token(approve=False)}"}

    listed = client.get(
        f"/api/department-purchase-requests?q={source['code']}", headers=reader_headers
    )
    assert listed.status_code == 200, listed.text
    assert [row["code"] for row in listed.json()["items"]] == [source["code"]]
    detail = client.get(
        f"/api/department-purchase-requests/{source['id']}", headers=reader_headers
    )
    assert detail.status_code == 200, detail.text


def test_accounting_approve_permission_also_allows_voucher_creation(client):
    admin_headers = _headers(client)
    supplier = _supplier(client, admin_headers)
    purchase, _ = _purchase(client, admin_headers, supplier["id"])
    reader_headers = {"Authorization": f"Bearer {_accounting_user_token(approve=False)}"}
    approver_headers = {"Authorization": f"Bearer {_accounting_user_token(approve=True)}"}

    assert client.get("/api/accounting/inbox", headers=reader_headers).status_code == 200
    assert (
        client.post(
            "/api/accounting/payment-vouchers",
            json={**_cash_payload(500_000), "purchase_request_id": purchase['id']},
            headers=reader_headers,
        ).status_code
        == 403
    )
    allowed = client.post(
        "/api/accounting/payment-vouchers",
        json={**_cash_payload(500_000), "purchase_request_id": purchase['id']},
        headers=approver_headers,
    )
    assert allowed.status_code == 201, allowed.text
    assert allowed.json()["created_by_name"] == "Kế toán duyệt"
    # `mark-paid` đã bị GỠ HẲN 06/08/2026 — lập phiếu chi là chi luôn, không còn bước xác nhận.
    assert (
        client.post(
            f"/api/accounting/payment-vouchers/{allowed.json()['id']}/mark-paid",
            json={"bank_reference": None},
            headers=approver_headers,
        ).status_code
        == 404
    )


# --- PHIẾU CHI TỪ PHIẾU TẠM ỨNG LƯƠNG (chủ chốt 18/08/2026) -----------------------------------
#
# Bốn chốt: chỉ phiếu ĐÃ DUYỆT · một tạm ứng một phiếu chi · lập TAY (không tự sinh khi duyệt) ·
# đã lập phiếu chi thì KHÔNG huỷ được tạm ứng. Áp cho cả `tam_ung` lẫn `luong_dot_1`.


def _nv_tam_ung(client, headers, *, ten="NV Tạm Ứng"):
    db = SessionLocal()
    try:
        dept_id = DepartmentRepository(db).get_by_name("Sản xuất").id
    finally:
        db.close()
    r = client.post("/api/employees", json={"probation_end_date": "2025-12-31",
        "full_name": ten, "department_id": dept_id, "hire_date": "2020-01-01",
        "gender": "male", "status": "active",
    }, headers=headers)
    assert r.status_code in (200, 201), r.text
    return r.json()["employee"]["id"]


def _tam_ung(client, headers, eid, *, amount=3_000_000, kind="tam_ung", duyet=True):
    r = client.post("/api/luong/advances", json={
        "employee_id": eid, "period_year": 2026, "period_month": 8,
        "advance_date": "2026-08-01", "amount": amount, "reason": "việc nhà", "kind": kind,
    }, headers=headers)
    assert r.status_code in (200, 201), r.text
    adv = r.json()
    aid = adv.get("id") or adv.get("advance", {}).get("id")
    if duyet:
        d = client.post(f"/api/luong/advances/{aid}/approve", json={}, headers=headers)
        assert d.status_code == 200, d.text
    return aid


def _pc_tu_tam_ung(client, headers, aid, *, amount=999, expect=201):
    """Payload cố ý gửi SỐ TIỀN SAI — service phải lấy số của phiếu tạm ứng, không lấy số này."""
    r = client.post("/api/accounting/payment-vouchers", json={
        "salary_advance_id": aid,
        "source_type": "salary_advance",
        "voucher_type": "cash",
        "payment_stage": "other",
        "voucher_date": "2026-08-01",
        "amount": amount,
        "currency": "VND",
        "exchange_rate": 1,
        "content": "Chi tạm ứng lương tháng 8/2026",
        "cash_recipient_name": "Ai Đó Khác",
    }, headers=headers)
    assert r.status_code == expect, r.text
    return r.json()


def test_phieu_chi_tu_tam_ung_da_duyet(client):
    """Lập được, và SỐ TIỀN + NGƯỜI NHẬN lấy từ phiếu tạm ứng chứ không lấy từ payload."""
    headers = _headers(client)
    eid = _nv_tam_ung(client, headers, ten="NV Ứng Một")
    aid = _tam_ung(client, headers, eid, amount=3_000_000)

    pc = _pc_tu_tam_ung(client, headers, aid, amount=999)
    assert pc["source_type"] == "salary_advance"
    assert pc["salary_advance_id"] == aid
    assert pc["amount"] == 3_000_000          # KHÔNG phải 999 của payload
    assert pc["cash_recipient_name"] == "NV Ứng Một"   # KHÔNG phải "Ai Đó Khác"
    assert pc["code"].startswith("PC-")
    # Lập phiếu chi = tiền đã ra (chốt 06/08/2026) ⇒ phiếu sinh ra đã là đã chi.
    assert pc["status"] == "paid"
    # Mã nguồn in trên chứng từ là MÃ PHIẾU TẠM ỨNG, để lần ngược từ sổ quỹ.
    assert pc["purchase_request_code"].startswith("TU")


def test_phieu_chi_CHI_cho_tam_ung_da_duyet(client):
    """Phiếu chờ duyệt / từ chối / đã huỷ đều KHÔNG lập được phiếu chi."""
    headers = _headers(client)
    eid = _nv_tam_ung(client, headers, ten="NV Ứng Hai")

    cho_duyet = _tam_ung(client, headers, eid, duyet=False)
    _pc_tu_tam_ung(client, headers, cho_duyet, expect=422)

    tu_choi = _tam_ung(client, headers, eid, duyet=False)
    client.post(f"/api/luong/advances/{tu_choi}/reject", json={}, headers=headers)
    _pc_tu_tam_ung(client, headers, tu_choi, expect=422)


def test_mot_tam_ung_chi_mot_phieu_chi(client):
    headers = _headers(client)
    eid = _nv_tam_ung(client, headers, ten="NV Ứng Ba")
    aid = _tam_ung(client, headers, eid)
    _pc_tu_tam_ung(client, headers, aid)
    _pc_tu_tam_ung(client, headers, aid, expect=409)   # lần hai bị chặn


def test_da_lap_phieu_chi_thi_KHONG_huy_duoc_tam_ung(client):
    """Tiền đã rời két ⇒ huỷ tạm ứng là mất dấu chứng từ. Phải huỷ phiếu chi trước."""
    headers = _headers(client)
    eid = _nv_tam_ung(client, headers, ten="NV Ứng Bốn")
    aid = _tam_ung(client, headers, eid)

    huy_som = client.post(f"/api/luong/advances/{aid}/cancel", headers=headers)
    assert huy_som.status_code == 200, huy_som.text      # chưa có phiếu chi thì huỷ được

    aid2 = _tam_ung(client, headers, eid)
    pc = _pc_tu_tam_ung(client, headers, aid2)
    huy = client.post(f"/api/luong/advances/{aid2}/cancel", headers=headers)
    assert huy.status_code == 400, huy.text
    assert pc["code"] in huy.json()["detail"]

    # Huỷ phiếu chi xong thì huỷ tạm ứng được.
    client.post(f"/api/accounting/payment-vouchers/{pc['id']}/cancel",
                json={"reason": "chi nhầm"}, headers=headers)
    lai = client.post(f"/api/luong/advances/{aid2}/cancel", headers=headers)
    assert lai.status_code == 200, lai.text


def test_luong_dot_1_cung_lap_duoc_phieu_chi(client):
    """Chủ chốt: lương đợt 1 cũng là tiền ra khỏi két ⇒ cũng lập phiếu chi."""
    headers = _headers(client)
    eid = _nv_tam_ung(client, headers, ten="NV Đợt Một")
    aid = _tam_ung(client, headers, eid, amount=5_000_000, kind="luong_dot_1")
    pc = _pc_tu_tam_ung(client, headers, aid)
    assert pc["amount"] == 5_000_000 and pc["salary_advance_id"] == aid


def test_payload_DUNG_NHU_FE_GUI_khong_co_ten_nguoi_nhan(client):
    """Mối nối FE↔BE: `client.ts::createVoucherFromAdvance` KHÔNG gửi `cash_recipient_name`
    (backend tự lấy tên nhân viên). Test này canh đúng payload đó, để đổi schema mà quên FE là đỏ."""
    headers = _headers(client)
    eid = _nv_tam_ung(client, headers, ten="NV Đúng Payload")
    aid = _tam_ung(client, headers, eid, amount=2_500_000)

    r = client.post("/api/accounting/payment-vouchers", json={
        # y hệt những gì client.ts ghép: input + 4 khoá cứng, KHÔNG có cash_recipient_name.
        "salary_advance_id": aid,
        "amount": 2_500_000,
        "voucher_type": "cash",
        "voucher_date": "2026-08-01",
        "content": "Tạm ứng lương tháng 8/2026 — NV Đúng Payload",
        "source_type": "salary_advance",
        "payment_stage": "other",
        "currency": "VND",
        "exchange_rate": 1,
    }, headers=headers)
    assert r.status_code == 201, r.text
    pc = r.json()
    assert pc["cash_recipient_name"] == "NV Đúng Payload"   # backend tự điền
    assert pc["amount"] == 2_500_000 and pc["salary_advance_id"] == aid
