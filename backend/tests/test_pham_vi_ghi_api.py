"""GHI KHÔNG ĐƯỢC RỘNG HƠN ĐỌC — phạm vi nhìn phải áp cho cả đường ghi.

Trước 05/08/2026 chỉ đường ĐỌC kiểm phạm vi (`get_request`, `list_requests`); toàn bộ đường GHI tra
thẳng theo id. Cổng quyền ở router chỉ hỏi *"có quyền `thu_mua:update` không"*, KHÔNG hỏi phiếu đó
của ai. Nhân viên không nhìn thấy phiếu đồng nghiệp trong danh sách (nhận 404) nhưng gọi thẳng theo
id thì sửa / xoá / gửi duyệt / đánh dấu đã nhận hàng đều được — mà "đã nhận hàng" thì **đẻ ra công
nợ** trên bàn kế toán. Id là số chạy, đoán được.

Trớ trêu: `cancel` đã có chốt sở hữu riêng từ 04/08, còn `delete` thì không — huỷ phiếu người khác
bị chặn mà XOÁ HẲN lại được. File này canh cho cả cụm, không chỉ một hàm.

Mọi ca đều mong **404**, không phải 403: trả 403 là tự khai ra "có phiếu này nhưng anh không được
đụng" — đúng thứ không nên nói với người ngoài phạm vi.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.db import SessionLocal
from app.models.role import SCOPE_ALL, SCOPE_OWN
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password


def _headers(client) -> dict[str, str]:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _needed_date(days: int = 30) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def _nhan_vien_thu_mua(username: str, *, scope: str = SCOPE_OWN, phong: str = "Mua hàng") -> dict:
    """Nhân viên thu mua thật: có đủ quyền thao tác, nhưng phạm vi nhìn bị co."""
    db = SessionLocal()
    try:
        users = UserRepository(db)
        u = users.get_by_username(username)
        if u is None:
            dept = DepartmentRepository(db).get_by_name(phong)
            roles = RoleRepository(db)
            role = roles.create(name=f"Vai {username}", department_id=dept.id)
            roles.set_permission(
                role_id=role.id, module_key="thu_mua", scope=scope,
                can_read=True, can_create=True, can_update=True, can_delete=True, can_cancel=True,
            )
            u = users.create(username=username, name=username, password_hash=hash_password("x"))
            users.set_assignment(u, department_id=dept.id, role_id=role.id, is_active=True)
        return {"Authorization": f"Bearer {create_access_token(str(u.id))}"}
    finally:
        db.close()


def _token_duyet(username: str, *, scope: str = SCOPE_ALL, phong: str = "Ban giám đốc") -> dict:
    db = SessionLocal()
    try:
        users = UserRepository(db)
        u = users.get_by_username(username)
        if u is None:
            dept = DepartmentRepository(db).get_by_name(phong)
            roles = RoleRepository(db)
            role = roles.create(name=f"Vai {username}", department_id=dept.id)
            # 11/08/2026: DUYỆT PMH dời sang khoá `ke_toan`; còn "đánh dấu nhận hàng / lùi phiếu"
            # tách thành ô riêng `thu_mua:manage_status`. Cấp CÙNG phạm vi ở cả hai khoá — test này
            # kiểm hàng rào PHẠM VI, nên phải giữ phạm vi giống nhau, đừng để lệch.
            roles.set_permission(role_id=role.id, module_key="thu_mua", scope=scope,
                                 can_read=True, can_update=True, can_manage_status=True)
            roles.set_permission(role_id=role.id, module_key="ke_toan", scope=scope,
                                 can_read=True, can_approve=True)
            u = users.create(username=username, name=username, password_hash=hash_password("x"))
            users.set_assignment(u, department_id=dept.id, role_id=role.id, is_active=True)
        return {"Authorization": f"Bearer {create_access_token(str(u.id))}"}
    finally:
        db.close()


def _supplier(client, headers, *, name: str) -> dict:
    dau = f"{abs(hash(name)) % 10**8:08d}"
    r = client.post(
        "/api/suppliers",
        json={
            "name": name, "tax_code": f"01{dau}", "phone": f"09{dau}",
            "email": f"ncc{dau}@example.com", "address": "Hà Nội", "contact_name": "Nguyễn Lan",
            "supplier_group": "paper",
            "items": [{"item_name": "Giấy Duplex", "unit": "tờ", "unit_price": 2200, "vat_percent": 0}],
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


def _phieu_cua(client, headers, supplier_id: int, *, admin) -> dict:
    """Lập một phiếu mua bằng ĐÚNG tài khoản `headers` (để nó thuộc về người đó).

    Yêu cầu nguồn do BỘ PHẬN tạo (ở đây mượn admin) — thu mua không có quyền tạo yêu cầu hộ phòng
    ban, đó là đúng luồng thật."""
    src = client.post(
        "/api/department-purchase-requests",
        json={
            "source_type": "kinh_doanh", "purpose": "Mua giấy",
            "needed_date": _needed_date(),
            "lines": [{"item_name": "Giấy Duplex", "unit": "tờ", "quantity": 1000}],
        },
        headers=admin,
    )
    assert src.status_code == 201, src.text
    r = client.post(
        "/api/purchase-requests",
        json={
            "supplier_id": supplier_id, "source_request_ids": [src.json()["id"]],
            "purpose": "Mua giấy", "needed_date": _needed_date(),
            "lines": [{
                "item_name": "Giấy Duplex", "unit": "tờ", "quantity": 1000,
                "expected_unit_price": 2200, "discount_percent": 0, "vat_percent": 0,
            }],
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


# --- người ngoài phạm vi KHÔNG ghi được -------------------------------------


def test_nhan_vien_khong_dung_duoc_phieu_nhap_cua_dong_nghiep(client):
    """⭐ Ca chính. A không thấy phiếu của B trong danh sách, nhưng biết id thì làm được gì?

    Kỳ vọng: KHÔNG gì cả. Và phải là 404 — trả 403 là xác nhận phiếu đó có tồn tại."""
    admin = _headers(client)
    ncc = _supplier(client, admin, name="NCC Pham Vi Ghi")
    b = _nhan_vien_thu_mua("pv-nvB")
    phieu = _phieu_cua(client, b, ncc["id"], admin=admin)
    pid = phieu["id"]

    a = _nhan_vien_thu_mua("pv-nvA")

    # Đường ĐỌC đã chặn sẵn từ trước — nhắc lại để thấy hai bên nay nói cùng một câu.
    assert client.get(f"/api/purchase-requests/{pid}", headers=a).status_code == 404

    sua = client.put(
        f"/api/purchase-requests/{pid}",
        json={
            "supplier_id": ncc["id"], "source_request_ids": [phieu["sources"][0]["department_request_id"]],
            "purpose": "Đổi trộm", "needed_date": _needed_date(),
            "lines": [{
                "item_name": "Giấy Duplex", "unit": "tờ", "quantity": 1,
                "expected_unit_price": 999999, "discount_percent": 0, "vat_percent": 0,
            }],
        },
        headers=a,
    )
    assert sua.status_code == 404, f"SỬA được phiếu người khác: {sua.text}"

    assert client.post(f"/api/purchase-requests/{pid}/submit", headers=a).status_code == 404
    assert client.delete(f"/api/purchase-requests/{pid}", headers=a).status_code == 404

    # Phiếu của B vẫn nguyên vẹn: đúng người lập, đúng giá, vẫn là nháp.
    con = client.get(f"/api/purchase-requests/{pid}", headers=b).json()
    assert con["status"] == "draft"
    assert con["lines"][0]["expected_unit_price"] == 2200, "giá bị người ngoài sửa"


def test_nguoi_ngoai_khong_danh_dau_nhan_hang_ho_duoc(client):
    """🔴 Nặng nhất: bấm "đã nhận hàng" là ĐẺ RA CÔNG NỢ trên màn kế toán."""
    admin = _headers(client)
    ncc = _supplier(client, admin, name="NCC Nhan Ho")
    b = _nhan_vien_thu_mua("pv-nvB2")
    phieu = _phieu_cua(client, b, ncc["id"], admin=admin)
    pid = phieu["id"]
    assert client.post(f"/api/purchase-requests/{pid}/submit", headers=b).status_code == 200
    assert client.post(
        f"/api/purchase-requests/{pid}/approve", headers=_token_duyet("pv-gd")
    ).status_code == 200

    a = _nhan_vien_thu_mua("pv-nvA2")
    assert client.post(f"/api/purchase-requests/{pid}/mark-purchased", headers=a).status_code == 404
    # B tự đánh dấu đã mua, rồi A thử nhận hàng hộ.
    assert client.post(f"/api/purchase-requests/{pid}/mark-purchased", headers=b).status_code == 200
    nhan_ho = client.post(
        f"/api/purchase-requests/{pid}/mark-received", json={"lines": []}, headers=a
    )
    assert nhan_ho.status_code == 404, f"NHẬN HÀNG HỘ được ⇒ đẻ công nợ: {nhan_ho.text}"

    # Không có món nợ nào được sinh ra.
    tong = client.get("/api/accounting/payables", headers=admin).json()
    assert not [m for m in tong["items"] if m["supplier_id"] == ncc["id"]]


def test_truong_bo_phan_khong_lui_duoc_phieu_bo_phan_khac(client):
    """Hai đường đòi quyền DUYỆT cũng phải theo phạm vi — có `approve` không có nghĩa là với tới
    mọi bộ phận."""
    admin = _headers(client)
    ncc = _supplier(client, admin, name="NCC Lui Khac Bo Phan")
    b = _nhan_vien_thu_mua("pv-nvB3")
    phieu = _phieu_cua(client, b, ncc["id"], admin=admin)
    pid = phieu["id"]
    for buoc, h in (("submit", b), ("approve", _token_duyet("pv-gd")),
                    ("mark-purchased", b)):
        assert client.post(f"/api/purchase-requests/{pid}/{buoc}", headers=h,
                           json={}).status_code == 200, buoc
    assert client.post(f"/api/purchase-requests/{pid}/mark-received",
                       json={"lines": []}, headers=b).status_code == 200

    # Trưởng bộ phận KHÁC: có `approve` nhưng phạm vi chỉ trong bộ phận mình.
    ngoai = _token_duyet("pv-tp-khac", scope="department", phong="Kho")
    lui = client.post(f"/api/purchase-requests/{pid}/undo-received",
                      json={"reason": "thử lùi hộ"}, headers=ngoai)
    assert lui.status_code == 404, f"lùi được phiếu bộ phận khác: {lui.text}"

    sua_nhan = client.put(
        f"/api/purchase-requests/{pid}/received-quantities",
        json={"lines": [{"line_id": phieu["lines"][0]["id"], "received_quantity": 1}]},
        headers=ngoai,
    )
    assert sua_nhan.status_code == 404, f"sửa được số nhận của bộ phận khác: {sua_nhan.text}"


def test_nguoi_trong_pham_vi_van_lam_duoc_binh_thuong(client):
    """Siết phạm vi KHÔNG được chặn nhầm người có quyền thật — nếu không thì cả xưởng đứng."""
    admin = _headers(client)
    ncc = _supplier(client, admin, name="NCC Van Chay")
    b = _nhan_vien_thu_mua("pv-nvB4")
    phieu = _phieu_cua(client, b, ncc["id"], admin=admin)
    pid = phieu["id"]

    assert client.post(f"/api/purchase-requests/{pid}/submit", headers=b).status_code == 200
    assert client.post(f"/api/purchase-requests/{pid}/approve",
                       headers=_token_duyet("pv-gd")).status_code == 200
    assert client.post(f"/api/purchase-requests/{pid}/mark-purchased", headers=b).status_code == 200
    assert client.post(f"/api/purchase-requests/{pid}/mark-received",
                       json={"lines": []}, headers=b).status_code == 200
    # Giám đốc scope `all` với tới mọi phiếu.
    assert client.post(f"/api/purchase-requests/{pid}/undo-received",
                       json={"reason": "kiểm lại"},
                       headers=_token_duyet("pv-gd")).status_code == 200
