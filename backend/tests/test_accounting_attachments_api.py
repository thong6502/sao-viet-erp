"""Phiếu chi/UNC — file chứng từ đính kèm (upload/list/delete + giới hạn)."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from app.db import SessionLocal
from app.models.role import SCOPE_ALL
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password
from app.storage import LOCAL_ROOT, key_from_url


def _disk(file_url: str) -> Path:
    """Chỗ nằm thật trên đĩa của một `file_url`. Test chạy LocalStorage (không có MinIO),
    nên dùng chính `key_from_url` của app thay vì tự chắp lại quy tắc đường dẫn."""
    return LOCAL_ROOT / key_from_url(file_url)


def _headers(client) -> dict[str, str]:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _supplier(client, headers) -> dict:
    response = client.post(
        "/api/suppliers",
        json={
            "name": "Công ty Giấy Đính Kèm",
            "tax_code": "0107777777",
            "phone": "0901777777",
            "email": "attachment-supplier@example.com",
            "address": "7 Trần Phú, Hà Nội",
            "contact_name": "Trần Hoa",
            "supplier_group": "paper",
            # Dòng vật tư phải có trong danh mục mặt hàng của một NCC đang hoạt động
            # (`purchase_service._clean_department_lines` → `suppliers.has_active_item`), nếu không
            # thì YCMH bị chặn 422 ngay từ bước đầu. Tên phải khớp đúng tên dùng ở `_voucher`.
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
            # Duyệt PMH dời sang khoá `ke_toan` (11/08/2026); giữ `thu_mua:read` để đọc phiếu.
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


def _khai_coc(client, headers, purchase_id: int, so_tien: int) -> dict:
    """Khai CỌC DỰ KIẾN — bắt buộc trước khi lập phiếu ĐẶT CỌC (luật 09/08/2026), và phải khai lúc
    phiếu còn NHÁP vì duyệt xong là khoá."""
    r = client.put(
        f"/api/purchase-requests/{purchase_id}/contract",
        json={"contract_number": None, "deposit_expected": so_tien},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _voucher(client, headers, supplier_id: int) -> dict:
    source = client.post(
        "/api/department-purchase-requests",
        json={
            "source_type": "kinh_doanh",
            "purpose": "Mua giấy cần chứng từ",
            "needed_date": _needed_date(),
            "lines": [{"item_name": "Giấy Duplex", "unit": "tờ", "quantity": 1000}],
        },
        headers=headers,
    )
    assert source.status_code == 201, source.text
    purchase = client.post(
        "/api/purchase-requests",
        json={
            "supplier_id": supplier_id,
            "source_request_ids": [source.json()["id"]],
            "purpose": "Mua giấy cần chứng từ",
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
    # Phiếu dưới đây là phiếu ĐẶT CỌC 1tr ⇒ phải khai cọc dự kiến trước, lúc còn nháp.
    _khai_coc(client, headers, purchase.json()["id"], 1_000_000)
    submitted = client.post(
        f"/api/purchase-requests/{purchase.json()['id']}/submit", headers=headers
    )
    assert submitted.status_code == 200, submitted.text
    _duyet(client, purchase.json()["id"])
    created = client.post(
        "/api/accounting/payment-vouchers",
        json={
            "purchase_request_id": purchase.json()["id"],
            "voucher_type": "cash",
            "payment_stage": "advance",
            "voucher_date": "2026-07-13",
            # Hạn trả BẮT BUỘC từ 05/08/2026 — không có hạn thì phiếu không bao giờ bị báo quá hạn.
            "planned_payment_date": "2026-07-28",
            "amount": 1_000_000,
            "currency": "VND",
            "exchange_rate": 1,
            "content": "Tạm ứng mua giấy",
            "cash_recipient_name": "Trần Hoa",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    return created.json()


def _upload(client, headers, voucher_id: int, *, name="hoa-don.jpg", data=b"anh-hoa-don", mime="image/jpeg"):
    return client.post(
        f"/api/accounting/payment-vouchers/{voucher_id}/attachments",
        files={"file": (name, data, mime)},
        headers=headers,
    )


def _paid_receipt(client, headers, supplier_id: int) -> dict:
    """Phiếu chi đã chi → lập 1 phiếu thu 300k (LẬP LÀ ĐÃ THU).

    Từ 27/08/2026 phiếu thu từ phiếu chi không còn nhịp "Xác nhận đã thu" — lập xong là tiền đã
    về (chủ chốt: *"cứ lập phiếu là ra tiền rồi xác nhận cái gì nữa"*). Chỉ phiếu thu CỌC ĐƠN BÁN
    mới còn trạng thái chờ, vì nó lập trước lúc khách chuyển tiền.
    """
    voucher = _voucher(client, headers, supplier_id)
    assert voucher["status"] == "paid"
    created = client.post(
        f"/api/accounting/payment-vouchers/{voucher['id']}/receipts",
        json={
            "payer_name": "Trần Hoa",
            "receipt_method": "cash",
            "receipt_date": "2026-07-13",
            "amount": 300_000,
            "content": "Thu hồi tiền thừa",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    return created.json()


def _upload_receipt(client, headers, receipt_id: int, *, name="bien-nhan-thu.jpg", data=b"anh-thu", mime="image/jpeg"):
    return client.post(
        f"/api/accounting/payment-receipts/{receipt_id}/attachments",
        files={"file": (name, data, mime)},
        headers=headers,
    )


def _reader_token() -> str:
    db = SessionLocal()
    try:
        department = DepartmentRepository(db).get_by_name("Kế toán")
        roles = RoleRepository(db)
        role = roles.create(name="Kế toán xem chứng từ", department_id=department.id)
        # CHỈ XEM, không được gán/gỡ chứng từ — cấp `can_read` trên đủ 6 màn kế toán.
        for khoa in ("ke_toan", "phieu_chi", "phieu_thu", "cong_no_phai_tra",
                     "cong_no_phai_thu", "tk_ngan_hang"):
            roles.set_permission(role_id=role.id, module_key=khoa, can_read=True, scope=SCOPE_ALL)
        users = UserRepository(db)
        user = users.create(
            username="attachment-reader",
            name="Kế toán xem chứng từ",
            password_hash=hash_password("x"),
        )
        users.set_assignment(user, department_id=department.id, role_id=role.id, is_active=True)
        return create_access_token(str(user.id))
    finally:
        db.close()


def test_upload_list_count_and_disk(client):
    headers = _headers(client)
    voucher = _voucher(client, headers, _supplier(client, headers)["id"])
    assert voucher["attachment_count"] == 0

    jpg = _upload(client, headers, voucher["id"])
    assert jpg.status_code == 201, jpg.text
    body = jpg.json()
    assert body["file_url"].startswith(f"/api/files/ke-toan/{voucher['id']}/")
    disk_path = _disk(body["file_url"])
    assert disk_path.exists() and disk_path.read_bytes() == b"anh-hoa-don"

    pdf = _upload(client, headers, voucher["id"], name="bien-nhan.pdf", mime="application/pdf")
    assert pdf.status_code == 201, pdf.text

    listed = client.get(
        f"/api/accounting/payment-vouchers/{voucher['id']}/attachments", headers=headers
    )
    assert listed.status_code == 200
    assert [row["file_name"] for row in listed.json()["items"]] == [
        "hoa-don.jpg",
        "bien-nhan.pdf",
    ]
    refreshed = client.get(
        f"/api/accounting/payment-vouchers/{voucher['id']}", headers=headers
    ).json()
    assert refreshed["attachment_count"] == 2

    # dọn file đĩa của test
    for row in listed.json()["items"]:
        client.delete(
            f"/api/accounting/payment-vouchers/{voucher['id']}/attachments/{row['id']}",
            headers=headers,
        )


def test_upload_allowed_after_paid_blocked_after_cancelled(client):
    headers = _headers(client)
    supplier = _supplier(client, headers)
    paid = _voucher(client, headers, supplier["id"])
    assert paid["status"] == "paid"
    after_paid = _upload(client, headers, paid["id"])
    assert after_paid.status_code == 201, after_paid.text  # hóa đơn về sau khi chi

    cancelled = _voucher(client, headers, supplier["id"])
    assert (
        client.post(
            f"/api/accounting/payment-vouchers/{cancelled['id']}/cancel",
            json={"reason": "Lập nhầm"},
            headers=headers,
        ).status_code
        == 200
    )
    blocked = _upload(client, headers, cancelled["id"])
    assert blocked.status_code == 409

    # dọn file đĩa
    row = after_paid.json()
    client.delete(
        f"/api/accounting/payment-vouchers/{paid['id']}/attachments/{row['id']}",
        headers=headers,
    )


def test_upload_rejects_bad_type_oversize_and_empty(client):
    headers = _headers(client)
    voucher = _voucher(client, headers, _supplier(client, headers)["id"])

    exe = _upload(client, headers, voucher["id"], name="virus.exe", data=b"MZ", mime="application/x-msdownload")
    assert exe.status_code == 422
    big = _upload(client, headers, voucher["id"], data=b"x" * (10 * 1024 * 1024 + 1))
    assert big.status_code == 422
    empty = _upload(client, headers, voucher["id"], data=b"")
    assert empty.status_code == 422


def test_filename_sanitized_against_traversal(client):
    headers = _headers(client)
    voucher = _voucher(client, headers, _supplier(client, headers)["id"])
    nasty = _upload(client, headers, voucher["id"], name="..\\..\\hóa đơn?.jpg")
    assert nasty.status_code == 201, nasty.text
    body = nasty.json()
    assert "/" not in body["file_name"] and "\\" not in body["file_name"]
    assert ".." not in body["file_url"].split("/")[-1].split("_", 1)[0]
    disk_path = _disk(body["file_url"])
    assert disk_path.exists()
    assert disk_path.parent == LOCAL_ROOT / "ke-toan" / str(voucher["id"])
    client.delete(
        f"/api/accounting/payment-vouchers/{voucher['id']}/attachments/{body['id']}",
        headers=headers,
    )


def test_delete_removes_row_and_disk_file(client):
    headers = _headers(client)
    voucher = _voucher(client, headers, _supplier(client, headers)["id"])
    body = _upload(client, headers, voucher["id"]).json()
    disk_path = _disk(body["file_url"])
    assert disk_path.exists()

    deleted = client.delete(
        f"/api/accounting/payment-vouchers/{voucher['id']}/attachments/{body['id']}",
        headers=headers,
    )
    assert deleted.status_code == 204
    assert not disk_path.exists()
    listed = client.get(
        f"/api/accounting/payment-vouchers/{voucher['id']}/attachments", headers=headers
    )
    assert listed.json()["items"] == []
    refreshed = client.get(
        f"/api/accounting/payment-vouchers/{voucher['id']}", headers=headers
    ).json()
    assert refreshed["attachment_count"] == 0

    missing = client.delete(
        f"/api/accounting/payment-vouchers/{voucher['id']}/attachments/999999",
        headers=headers,
    )
    assert missing.status_code == 404


def test_attachment_permissions(client):
    admin_headers = _headers(client)
    voucher = _voucher(client, admin_headers, _supplier(client, admin_headers)["id"])
    reader_headers = {"Authorization": f"Bearer {_reader_token()}"}

    assert (
        client.get(
            f"/api/accounting/payment-vouchers/{voucher['id']}/attachments",
            headers=reader_headers,
        ).status_code
        == 200
    )
    assert _upload(client, reader_headers, voucher["id"]).status_code == 403
    uploaded = _upload(client, admin_headers, voucher["id"]).json()
    assert (
        client.delete(
            f"/api/accounting/payment-vouchers/{voucher['id']}/attachments/{uploaded['id']}",
            headers=reader_headers,
        ).status_code
        == 403
    )
    client.delete(
        f"/api/accounting/payment-vouchers/{voucher['id']}/attachments/{uploaded['id']}",
        headers=admin_headers,
    )


# --- Phiếu thu (PT) — đính kèm ảnh minh chứng đã thu ------------------------


def test_receipt_upload_list_count_and_disk(client):
    headers = _headers(client)
    receipt = _paid_receipt(client, headers, _supplier(client, headers)["id"])
    assert receipt["attachment_count"] == 0

    jpg = _upload_receipt(client, headers, receipt["id"])
    assert jpg.status_code == 201, jpg.text
    body = jpg.json()
    assert body["file_url"].startswith(f"/api/files/ke-toan-thu/{receipt['id']}/")
    disk_path = _disk(body["file_url"])
    assert disk_path.exists() and disk_path.read_bytes() == b"anh-thu"

    pdf = _upload_receipt(client, headers, receipt["id"], name="bao-co.pdf", mime="application/pdf")
    assert pdf.status_code == 201, pdf.text

    listed = client.get(
        f"/api/accounting/payment-receipts/{receipt['id']}/attachments", headers=headers
    )
    assert [row["file_name"] for row in listed.json()["items"]] == [
        "bien-nhan-thu.jpg",
        "bao-co.pdf",
    ]
    refreshed = client.get(
        f"/api/accounting/payment-receipts?q={receipt['code']}", headers=headers
    ).json()["items"][0]
    assert refreshed["attachment_count"] == 2

    for row in listed.json()["items"]:
        client.delete(
            f"/api/accounting/payment-receipts/{receipt['id']}/attachments/{row['id']}",
            headers=headers,
        )


def test_receipt_upload_allowed_after_received_blocked_after_cancelled(client):
    headers = _headers(client)
    supplier = _supplier(client, headers)
    received = _paid_receipt(client, headers, supplier["id"])
    # KHÔNG gọi `mark-received` nữa: phiếu vừa lập đã ở trạng thái đã thu, gọi thêm sẽ ăn 409.
    assert received["status"] == "received", received
    after_received = _upload_receipt(client, headers, received["id"])
    assert after_received.status_code == 201, after_received.text  # minh chứng sau khi thu

    cancelled = _paid_receipt(client, headers, supplier["id"])
    assert (
        client.post(
            f"/api/accounting/payment-receipts/{cancelled['id']}/cancel",
            json={"reason": "Lập nhầm"},
            headers=headers,
        ).status_code
        == 200
    )
    assert _upload_receipt(client, headers, cancelled["id"]).status_code == 409

    client.delete(
        f"/api/accounting/payment-receipts/{received['id']}/attachments/{after_received.json()['id']}",
        headers=headers,
    )


def test_receipt_upload_rejects_bad_type_and_delete(client):
    headers = _headers(client)
    receipt = _paid_receipt(client, headers, _supplier(client, headers)["id"])

    assert (
        _upload_receipt(
            client, headers, receipt["id"], name="x.exe", data=b"MZ", mime="application/x-msdownload"
        ).status_code
        == 422
    )
    body = _upload_receipt(client, headers, receipt["id"]).json()
    disk_path = _disk(body["file_url"])
    assert disk_path.exists()

    assert (
        client.delete(
            f"/api/accounting/payment-receipts/{receipt['id']}/attachments/{body['id']}",
            headers=headers,
        ).status_code
        == 204
    )
    assert not disk_path.exists()
    assert (
        client.delete(
            f"/api/accounting/payment-receipts/{receipt['id']}/attachments/999999",
            headers=headers,
        ).status_code
        == 404
    )


def test_receipt_attachment_permissions(client):
    admin_headers = _headers(client)
    receipt = _paid_receipt(client, admin_headers, _supplier(client, admin_headers)["id"])
    reader_headers = {"Authorization": f"Bearer {_reader_token()}"}

    assert (
        client.get(
            f"/api/accounting/payment-receipts/{receipt['id']}/attachments",
            headers=reader_headers,
        ).status_code
        == 200
    )
    assert _upload_receipt(client, reader_headers, receipt["id"]).status_code == 403
    uploaded = _upload_receipt(client, admin_headers, receipt["id"]).json()
    assert (
        client.delete(
            f"/api/accounting/payment-receipts/{receipt['id']}/attachments/{uploaded['id']}",
            headers=reader_headers,
        ).status_code
        == 403
    )
    client.delete(
        f"/api/accounting/payment-receipts/{receipt['id']}/attachments/{uploaded['id']}",
        headers=admin_headers,
    )
