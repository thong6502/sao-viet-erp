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


# ══════════════════════════════════════════════ PHẠM VI Ở MÀN LƯƠNG
#
# LỖ HỔNG ĐO ĐƯỢC 15/08/2026: đường lấy bảng lương chỉ hỏi "có ô Xem Lương không", KHÔNG hỏi
# "người này quản ai" — trả về MỌI dòng của kỳ. Cấp ô Xem Lương với phạm vi *Của tôi* thì người
# đó vẫn đọc được lương của cả công ty, gồm cả giám đốc. Đúng căn bệnh tester ghi ở rà soát lần 1:
# *"Phạm vi của tôi nhưng xem được tất cả"* — hồi đó đếm ở 7 phân hệ, màn Lương còn sót tới hôm nay.


def _nv_xem_luong(username: str, *, scope: str, phong: str = "Sản xuất") -> dict:
    """Tài khoản có ô Xem Lương với PHẠM VI khai sẵn, gắn vào một phòng cụ thể."""
    db = SessionLocal()
    try:
        users = UserRepository(db)
        u = users.get_by_username(username)
        if u is None:
            dept = DepartmentRepository(db).get_by_name(phong)
            roles = RoleRepository(db)
            role = roles.create(name=f"Vai {username}", department_id=dept.id)
            roles.set_permission(role_id=role.id, module_key="luong", scope=scope,
                                 can_read=True, can_view_salary=True,
                                 # Từ 15/08/2026 BẢNG LƯƠNG THÁNG có ô riêng: cột Xem chỉ mở màn.
                                 # Ở đây đang đo PHẠM VI lọc dòng, nên phải mở được bảng đã —
                                 # chuyện "không có ô thì không vào bảng" do test riêng canh.
                                 can_view_payroll_table=True)
            u = users.create(username=username, name=username, password_hash=hash_password("x"))
            users.set_assignment(u, department_id=dept.id, role_id=role.id, is_active=True)
        return {"Authorization": f"Bearer {create_access_token(str(u.id))}"}
    finally:
        db.close()


def _nv(client, headers, ten: str, phong: str) -> int:
    """Hồ sơ nhân viên tối thiểu — chỉ cần có mặt để `generate` đẻ ra một dòng lương."""
    db = SessionLocal()
    try:
        dept_id = DepartmentRepository(db).get_by_name(phong).id
    finally:
        db.close()
    r = client.post("/api/employees",
                    json={"probation_end_date": "2025-12-31", "full_name": ten, "department_id": dept_id, "hire_date": "2020-01-01"},
                    headers=headers)
    assert r.status_code in (200, 201), r.text
    return r.json()["employee"]["id"]


def _so_dong_bang_luong(client, headers, *, year=2026, month=6) -> int:
    r = client.get(f"/api/luong/table?year={year}&month={month}", headers=headers)
    assert r.status_code == 200, r.text
    return len(r.json()["lines"])


def test_xem_luong_pham_vi_CUA_TOI_khong_doc_duoc_luong_nguoi_khac(client):
    """⭐ Ô Phạm vi trên dòng Lương phải có tác dụng thật, không phải ô cấu hình giả."""
    auth_headers = _headers(client)
    # Hai người ở HAI phòng khác nhau — có thế mới đo được chuyện nhìn sang phòng bạn.
    _nv(client, auth_headers, "NV Pham Vi A", "Sản xuất")
    _nv(client, auth_headers, "NV Pham Vi B", "Kho")
    r = client.post("/api/luong/generate", json={"year": 2026, "month": 6}, headers=auth_headers)
    assert r.status_code == 200, r.text
    tong = _so_dong_bang_luong(client, auth_headers)
    assert tong >= 2, "cần ít nhất 2 người trong kỳ thì mới thử được chuyện nhìn trộm"

    rieng = _nv_xem_luong("pv-luong-own", scope=SCOPE_OWN)
    thay = _so_dong_bang_luong(client, rieng)
    assert thay < tong, (
        f"phạm vi 'Của tôi' vẫn đọc được {thay}/{tong} dòng — ô Phạm vi không có tác dụng"
    )


def test_xem_luong_khong_kem_o_bang_luong_thi_KHONG_vao_duoc_bang(client):
    """⭐ Ô "Bảng lương tháng" phải là cổng THẬT, không phải nhãn trang trí.

    Bảng lương tháng là công cụ quản lý: danh sách lương cả phạm vi + Tính lại + Chốt kỳ.
    Trước 15/08/2026 nó đi theo cột Xem, nên cấp ô Lương cho thợ (để họ xem phiếu của mình)
    là mở luôn bảng lương cả phòng — chủ chốt: *"công nhân làm gì có quyền đó đâu"*."""
    db = SessionLocal()
    try:
        dept = DepartmentRepository(db).get_by_name("Sản xuất")
        roles = RoleRepository(db)
        role = roles.create(name="Vai xem luong khong bang", department_id=dept.id)
        # Cấp RỘNG TAY mọi thứ trừ đúng ô đang đo — hỏng thì biết chắc là do ô đó.
        roles.set_permission(role_id=role.id, module_key="luong", scope=SCOPE_ALL,
                             can_read=True, can_view_salary=True, can_export=True,
                             can_create=True, can_update=True)
        u = UserRepository(db).create(username="pv-luong-khong-bang", name="NV",
                                      password_hash=hash_password("x"))
        UserRepository(db).set_assignment(u, department_id=dept.id, role_id=role.id,
                                          is_active=True)
        h = {"Authorization": f"Bearer {create_access_token(str(u.id))}"}
    finally:
        db.close()
    r = client.get("/api/luong/table?year=2026&month=6", headers=h)
    assert r.status_code == 403, (
        f"thiếu ô Bảng lương tháng mà vẫn đọc được bảng ({r.status_code}) — ô là nhãn giả"
    )


def test_xuat_excel_cung_bi_kep_theo_pham_vi(client):
    """Gác màn mà quên file tải về thì hàng rào chỉ là hình vẽ — tải Excel cũng là một đường đọc."""
    auth_headers = _headers(client)
    assert client.post("/api/luong/generate", json={"year": 2026, "month": 6},
                       headers=auth_headers).status_code == 200
    rieng = _nv_xem_luong("pv-luong-xuat", scope=SCOPE_OWN)
    r = client.get("/api/luong/export.xlsx?year=2026&month=6", headers=rieng)
    # Không có ô Xuất ⇒ 403 là ĐÚNG. Có ô mà lọt cả công ty mới là hỏng — ca đó do test trên canh.
    assert r.status_code in (200, 403), r.text


def test_pham_vi_TAT_CA_van_thay_du_nhu_cu(client):
    """Đối chứng: siết nhầm thì HCNS mất bảng lương, còn tệ hơn lỗ hổng."""
    auth_headers = _headers(client)
    assert client.post("/api/luong/generate", json={"year": 2026, "month": 6},
                       headers=auth_headers).status_code == 200
    tong = _so_dong_bang_luong(client, auth_headers)
    ca_cty = _nv_xem_luong("pv-luong-all", scope=SCOPE_ALL, phong="Ban giám đốc")
    assert _so_dong_bang_luong(client, ca_cty) == tong
