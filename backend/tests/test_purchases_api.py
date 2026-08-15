"""Tests for the Thu mua API: suppliers + purchase-request approval flow."""
from __future__ import annotations

import zlib

import re
from datetime import date, timedelta

import pytest

from app.db import SessionLocal
from app.models.role import SCOPE_ALL, SCOPE_OWN
from app.models.purchase import Supplier, SupplierItem
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password


@pytest.fixture
def token(client, seed_credentials) -> str:
    resp = client.post("/api/auth/login", json=seed_credentials)
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def auth_headers(token) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _buyer_token() -> str:
    db = SessionLocal()
    try:
        users = UserRepository(db)
        existing = users.get_by_username("buyer-no-approve")
        if existing is not None:
            return create_access_token(str(existing.id))
        kd = DepartmentRepository(db).get_by_name("Kinh doanh")
        roles = RoleRepository(db)
        role = roles.create(name="Nhan vien mua hang", department_id=kd.id)
        _cap_ba_man_thu_mua(
            roles, role.id,
            can_read=True,
            can_create=True,
            can_update=True,
            can_delete=False,
            can_cancel=True,
            can_request=True,
            scope=SCOPE_ALL,
        )
        u = users.create(username="buyer-no-approve", name="Buyer", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=kd.id, role_id=role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def _buyer_approver_token() -> str:
    db = SessionLocal()
    try:
        users = UserRepository(db)
        existing = users.get_by_username("buyer-approve")
        if existing is not None:
            return create_access_token(str(existing.id))
        kd = DepartmentRepository(db).get_by_name("Kinh doanh")
        roles = RoleRepository(db)
        role = roles.create(name="Truong mua hang", department_id=kd.id)
        # Duyệt PMH dời sang khoá `ke_toan` (11/08/2026) — fixture này mô tả người VỪA làm thu mua
        # VỪA được trao quyền duyệt, nên phải cấp cả hai bên.
        roles.set_permission(role_id=role.id, module_key="ke_toan",
                             can_read=True, can_approve=True, scope=SCOPE_ALL)
        _cap_ba_man_thu_mua(
            roles, role.id,
            can_read=True,
            can_create=True,
            can_update=True,
            can_delete=False,
            can_cancel=True,
            can_approve=True,
            # Ô mới (11/08/2026): sửa số nhận · mở lại đơn · đóng đơn — tách khỏi `can_approve`.
            can_manage_status=True,
            can_request=True,
            scope=SCOPE_ALL,
        )
        u = users.create(username="buyer-approve", name="Buyer Approver", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=kd.id, role_id=role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def _sales_token() -> str:
    db = SessionLocal()
    try:
        users = UserRepository(db)
        existing = users.get_by_username("purchase-sales")
        if existing is not None:
            return create_access_token(str(existing.id))
        kd = DepartmentRepository(db).get_by_name("Kinh doanh")
        sales_role = RoleRepository(db).get_by_name_and_department("NV Sales", kd.id)
        u = users.create(username="purchase-sales", name="Sales", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=kd.id, role_id=sales_role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def _sales2_token() -> str:
    db = SessionLocal()
    try:
        users = UserRepository(db)
        existing = users.get_by_username("purchase-sales-2")
        if existing is not None:
            return create_access_token(str(existing.id))
        kd = DepartmentRepository(db).get_by_name("Kinh doanh")
        sales_role = RoleRepository(db).get_by_name_and_department("NV Sales", kd.id)
        u = users.create(username="purchase-sales-2", name="Sales 2", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=kd.id, role_id=sales_role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


# Từ 10/08/2026 phân hệ Thu mua tách làm BA MÀN, mỗi màn một ô quyền riêng:
#   thu_mua = Mua hàng · nha_cung_cap = Nhà cung cấp · yeu_cau_mua_hang = Yêu cầu mua hàng.
# Vai "nhân viên/trưởng bộ phận mua hàng" ngoài đời chạm cả ba nên test cấp cả ba với CÙNG bộ cờ —
# đúng như migration 0177 sao chép quyền cũ sang. Test nào muốn kiểm từng màn ĐỘC LẬP thì cấp tay
# đúng một khoá (xem test_ba_man_thu_mua_gac_bang_ba_khoa_doc_lap).
_MODULE_THU_MUA_DU_BA_MAN = ("thu_mua", "nha_cung_cap", "yeu_cau_mua_hang")


def _cap_ba_man_thu_mua(roles, role_id: int, **co) -> None:
    for khoa in _MODULE_THU_MUA_DU_BA_MAN:
        roles.set_permission(role_id=role_id, module_key=khoa, **co)


def _vai_dung_mot_man(khoa: str, uname: str, **co) -> str:
    """Tạo tài khoản chỉ được cấp ĐÚNG MỘT màn của phân hệ Thu mua, trả token."""
    db = SessionLocal()
    try:
        users = UserRepository(db)
        existing = users.get_by_username(uname)
        if existing is not None:
            return create_access_token(str(existing.id))
        kd = DepartmentRepository(db).get_by_name("Kinh doanh")
        roles = RoleRepository(db)
        role = roles.create(name=f"Chi man {khoa}", department_id=kd.id)
        roles.set_permission(role_id=role.id, module_key=khoa, scope=SCOPE_ALL, **co)
        u = users.create(username=uname, name=uname, password_hash=hash_password("x"))
        users.set_assignment(u, department_id=kd.id, role_id=role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def test_ba_man_thu_mua_gac_bang_ba_khoa_doc_lap(client):
    """Mỗi màn Thu mua một ô quyền RIENG — cấp màn này KHONG mo cua man kia.

    Y chu chot 10/08/2026: "cu cap quyen la duoc phep". Truoc do ca phan he dung chung mot khoa
    `thu_mua`, nen bat NCC cho ke toan la ho co luon quyen tren phieu mua; con man Yeu cau mua hang
    thi nguoc lai — BA endpoint tao/sua/huy chi doi DANG NHAP, ai cung day duoc yeu cau chi tien vao
    hang doi cua bo phan mua hang.

    Test nay giu ca hai chieu cua hang rao: co khoa dung man thi VAO duoc, khong co thi 403.
    """
    chi_ncc = _vai_dung_mot_man("nha_cung_cap", "chi-man-ncc",
                                can_read=True, can_create=True, can_update=True)
    chi_ycmh = _vai_dung_mot_man("yeu_cau_mua_hang", "chi-man-ycmh",
                                 can_read=True, can_create=True, can_update=True)

    h_ncc = {"Authorization": f"Bearer {chi_ncc}"}
    h_ycmh = {"Authorization": f"Bearer {chi_ycmh}"}

    # 1) Nguoi CHI co man Nha cung cap: vao duoc danh muc NCC...
    assert client.get("/api/suppliers", headers=h_ncc).status_code == 200
    # ...nhung KHONG cham duoc man Mua hang (phieu mua) va KHONG lap duoc yeu cau.
    assert client.get("/api/purchase-requests", headers=h_ncc).status_code == 403
    r = client.post("/api/department-purchase-requests",
                    json=_department_request_payload(), headers=h_ncc)
    assert r.status_code == 403, r.text

    # 2) Nguoi CHI co man Yeu cau mua hang: lap duoc yeu cau...
    r2 = client.post("/api/department-purchase-requests",
                     json=_department_request_payload(), headers=h_ycmh)
    assert r2.status_code == 201, r2.text
    # Ô chọn Vật tư của YCMH đọc danh mục bằng chính quyền YCMH; tắt Thu mua không được làm nó
    # trắng. Chỉ là cửa đọc picker, không mở CRUD danh mục.
    assert client.get("/api/vat-lieu-kho/mat-hang", headers=h_ycmh).status_code == 200
    # ...nhung KHONG mo duoc danh muc NCC va KHONG cham duoc phieu mua.
    # DANH SÁCH NCC: từ 12/08/2026 người xử lý YCMH ĐỌC ĐƯỢC (chủ chốt: "chưa được cấp quyền nhà
    # cung cấp sao nó lại không gợi ý nhà cung cấp"). Xử lý một yêu cầu mua là phải CHỌN nhà cung
    # cấp, mà ô chọn lấy dữ liệu từ đúng endpoint này. ĐỌC ≠ sửa danh mục — vế sửa vẫn 403.
    assert client.get("/api/suppliers", headers=h_ycmh).status_code == 200
    assert client.post("/api/suppliers", json={"name": "NCC lau"},
                       headers=h_ycmh).status_code == 403
    assert client.get("/api/purchase-requests", headers=h_ycmh).status_code == 403
    # Endpoint badge không được rò số sự kiện của hai màn người này không có quyền.
    assert client.get(
        "/api/module-notifications/summary", headers=h_ycmh
    ).json() == {"thu_mua": 0, "ke_toan": 0}
    assert client.post(
        "/api/module-notifications/thu_mua/mark-read", headers=h_ycmh
    ).status_code == 403


def test_badge_thu_mua_ke_toan_luu_trang_thai_da_doc(client, auth_headers):
    """Gửi duyệt → Kế toán có badge; vào màn/mark-read → refresh vẫn 0; duyệt → Thu mua có badge."""
    supplier = _supplier(client, auth_headers, name="NCC Badge Hai Chieu")
    pr = _create_purchase_request(client, auth_headers, supplier["id"])
    approver_headers = _h_duyet()

    # Phiếu nháp chưa phải thông báo gửi Kế toán.
    before = client.get("/api/module-notifications/summary", headers=approver_headers)
    assert before.status_code == 200, before.text
    assert before.json()["ke_toan"] == 0

    sent = client.post(
        f"/api/purchase-requests/{pr['id']}/submit", headers=auth_headers
    )
    assert sent.status_code == 200, sent.text
    assert client.get(
        "/api/module-notifications/summary", headers=approver_headers
    ).json()["ke_toan"] == 1

    seen = client.post(
        "/api/module-notifications/ke_toan/mark-read", headers=approver_headers
    )
    assert seen.status_code == 204, seen.text
    assert client.get(
        "/api/module-notifications/summary", headers=approver_headers
    ).json()["ke_toan"] == 0

    approved = client.post(
        f"/api/purchase-requests/{pr['id']}/approve", headers=approver_headers
    )
    assert approved.status_code == 200, approved.text
    # Admin là người lập/Thu mua, khác người duyệt nên nhận thông báo ngược lại.
    assert client.get(
        "/api/module-notifications/summary", headers=auth_headers
    ).json()["thu_mua"] == 1


def test_tao_ycmh_bao_ngay_cho_thu_mua_va_luu_den_khi_doc(client, auth_headers):
    """Phòng ban tạo YCMH -> Thu mua có badge ngay, refresh còn, vào màn mới hết."""
    requester_token = _vai_dung_mot_man(
        "yeu_cau_mua_hang",
        "nguoi-tao-ycmh-bao-thu-mua",
        can_read=True,
        can_create=True,
        can_update=True,
    )
    requester_headers = {"Authorization": f"Bearer {requester_token}"}

    before = client.get("/api/module-notifications/summary", headers=auth_headers)
    assert before.status_code == 200, before.text
    assert before.json()["thu_mua"] == 0

    created = client.post(
        "/api/department-purchase-requests",
        json=_department_request_payload(),
        headers=requester_headers,
    )
    assert created.status_code == 201, created.text

    # Đếm từ bản ghi server nên tải lại trang vẫn còn, không phụ thuộc người dùng đã mở Mua hàng.
    first = client.get("/api/module-notifications/summary", headers=auth_headers)
    second = client.get("/api/module-notifications/summary", headers=auth_headers)
    assert first.json()["thu_mua"] == second.json()["thu_mua"] == 1

    seen = client.post(
        "/api/module-notifications/thu_mua/mark-read", headers=auth_headers
    )
    assert seen.status_code == 204, seen.text
    assert client.get(
        "/api/module-notifications/summary", headers=auth_headers
    ).json()["thu_mua"] == 0


def test_khong_co_quyen_thi_khong_lap_duoc_yeu_cau_mua_hang(client):
    """Tai khoan chi DANG NHAP, khong duoc cap gi: khong lap/sua/huy duoc yeu cau mua hang.

    Day dung la lo hong da vá: truoc 10/08/2026 ba endpoint nay nhan moi tai khoan dang nhap.
    """
    tok = _vai_dung_mot_man("dashboard", "chi-dang-nhap", can_read=True)
    h = {"Authorization": f"Bearer {tok}"}

    assert client.post("/api/department-purchase-requests",
                       json=_department_request_payload(), headers=h).status_code == 403
    assert client.put("/api/department-purchase-requests/1",
                      json=_department_request_payload(), headers=h).status_code == 403
    assert client.post("/api/department-purchase-requests/1/cancel",
                       json={"reason": "x"}, headers=h).status_code == 403


def _requester_token() -> str:
    db = SessionLocal()
    try:
        users = UserRepository(db)
        existing = users.get_by_username("purchase-requester")
        if existing is not None:
            return create_access_token(str(existing.id))
        kd = DepartmentRepository(db).get_by_name("Kinh doanh")
        roles = RoleRepository(db)
        role = roles.create(name="Nguoi duoc yeu cau mua", department_id=kd.id)
        roles.set_permission(
            role_id=role.id,
            module_key="thu_mua",
            can_read=True,
            can_request=True,
            scope=SCOPE_ALL,
        )
        # Bộ phận đề nghị: LẬP + SỬA yêu cầu trên màn Yêu cầu mua hàng. Trước 10/08/2026 ba endpoint
        # này chỉ đòi đăng nhập nên fixture không cần cấp gì — nay phải cấp mới gọi được.
        roles.set_permission(
            role_id=role.id,
            module_key="yeu_cau_mua_hang",
            can_read=True,
            can_create=True,
            can_update=True,
            scope=SCOPE_ALL,
        )
        u = users.create(username="purchase-requester", name="Requester", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=kd.id, role_id=role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def _nguoi_duyet_token() -> str:
    """Tài khoản DUYỆT phiếu mua — KHÁC người lập.

    Từ 04/08/2026 người lập phiếu không tự duyệt được phiếu của mình (tách vai: ai đề xuất chi tiền
    thì không được là người đồng ý chi). Test nào lập rồi duyệt bằng cùng một tài khoản là đang mô
    tả một tình huống không được phép xảy ra ngoài đời.

    Đặt ở BAN GIÁM ĐỐC chứ không ở Mua hàng — vai thuộc bộ phận Mua hàng bị migration 0159 gỡ
    quyền duyệt, để ở đó là test tự mâu thuẫn với luật vừa đặt.
    """
    db = SessionLocal()
    try:
        users = UserRepository(db)
        existing = users.get_by_username("purchase-approver")
        if existing is not None:
            return create_access_token(str(existing.id))
        bgd = DepartmentRepository(db).get_by_name("Ban giám đốc")
        roles = RoleRepository(db)
        role = roles.create(name="Nguoi duyet phieu mua", department_id=bgd.id)
        # DUYỆT / TỪ CHỐI PMH dời sang khoá `ke_toan` ngày 11/08/2026 — nút chỉ có ở màn
        # "Đơn mua hàng (Kế toán)", nên ô quyền cũng nằm ở đó. `thu_mua` giữ lại phần đọc + huỷ.
        roles.set_permission(
            role_id=role.id,
            module_key="ke_toan",
            can_read=True,
            can_approve=True,
            scope=SCOPE_ALL,
        )
        roles.set_permission(
            role_id=role.id,
            module_key="thu_mua",
            can_read=True,
            can_cancel=True,
            can_manage_status=True,
            scope=SCOPE_ALL,
        )
        u = users.create(username="purchase-approver", name="Nguoi duyet",
                         password_hash=hash_password("x"))
        users.set_assignment(u, department_id=bgd.id, role_id=role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def _h_duyet() -> dict[str, str]:
    return {"Authorization": f"Bearer {_nguoi_duyet_token()}"}


_ITEMS_MAC_DINH = [
    {"item_name": "Giay Duplex 350gsm", "unit": "to", "unit_price": 2200, "vat_percent": 8},
    {"item_name": "Keo can mang", "unit": "kg", "unit_price": 80000, "vat_percent": 8},
]


def _supplier(client, headers, name: str = "Cong ty Giay An Phat", items=None) -> dict:
    """NCC mặc định bán ĐÚNG hai thứ mà `_request_payload` đặt.

    Từ 04/08/2026 phiếu mua kiểm từng dòng có nằm trong danh mục mặt hàng của CHÍNH NCC đó không.
    Trước đó không kiểm gì nên test dựng NCC rỗng vẫn đặt được — tức đang kiểm một tình huống
    không tồn tại ngoài đời (đặt hàng của người không bán thứ đó).
    Truyền `items=[]` khi cần một NCC KHÔNG bán gì, để thử đúng hàng rào này.
    """
    resp = client.post(
        "/api/suppliers",
        json={
            "name": name,
            # MST suy từ TÊN: từ 12/08/2026 hai NCC không được trùng mã số thuế, mà fixture này
            # dựng hàng chục NCC trong một file test. Suy từ tên ⇒ mỗi NCC một mã, còn hai lần gọi
            # CÙNG TÊN vẫn ra cùng mã và vẫn vướng luật trùng TÊN (kiểm trước MST).
            "tax_code": f"01{abs(zlib.crc32(name.encode())) % 10**8:08d}",
            "phone": "0901000001",
            "email": "ncc@example.com",
            "address": "12 Nguyen Trai, TP.HCM",
            "contact_name": "Ms Lan",
            "supplier_group": "paper",
            "payment_terms": "Cong no 30 ngay",
            "items": _ITEMS_MAC_DINH if items is None else items,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _ensure_catalog_supplier() -> None:
    db = SessionLocal()
    try:
        existing = db.query(Supplier).filter(Supplier.name == "NCC Catalog Vat Tu").first()
        if existing is not None:
            return
        supplier = Supplier(
            name="NCC Catalog Vat Tu",
            tax_code="0100000999",
            phone="0900000999",
            email="catalog@example.com",
            address="Kho catalog",
            contact_name="Catalog",
            supplier_group="paper",
            status="active",
        )
        supplier.items = [
            SupplierItem(
                item_name="Giay Duplex 350gsm",
                unit="to",
                unit_price=2200,
                vat_percent=8,
            ),
            SupplierItem(
                item_name="Keo can mang",
                unit="kg",
                unit_price=80000,
                vat_percent=8,
            ),
        ]
        db.add(supplier)
        db.commit()
    finally:
        db.close()


def _request_payload(supplier_id: int | None = None) -> dict:
    return {
        "supplier_id": supplier_id,
        "source_request_ids": [],
        "purpose": "Mua giay cho don hang carton",
        "needed_date": (date.today() + timedelta(days=30)).isoformat(),
        "expected_receipt_date": (date.today() + timedelta(days=35)).isoformat(),
        "note": "Can bao gia truoc khi mua",
        "lines": [
            {
                "item_name": "Giay Duplex 350gsm",
                "unit": "to",
                "quantity": 1000,
                "expected_unit_price": 2200,
            },
            {
                "item_name": "Keo can mang",
                "unit": "kg",
                "quantity": 5,
                "expected_unit_price": 80000,
                "note": "Hang san xuat gap",
            },
        ],
    }


def _department_request_payload() -> dict:
    _ensure_catalog_supplier()
    return {
        "source_type": "kinh_doanh",
        "related_document_type": "sales_order",
        "related_document_code": "DH-260710-001",
        "purpose": "Thieu giay cho don hang carton",
        "needed_date": (date.today() + timedelta(days=30)).isoformat(),
        "note": "Sale tao yeu cau tu don hang",
        "lines": [
            {
                "item_name": "Giay Duplex 350gsm",
                "unit": "to",
                "quantity": 1000,
            }
        ],
    }


def _create_department_request(client, headers) -> dict:
    resp = client.post(
        "/api/department-purchase-requests",
        json=_department_request_payload(),
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_purchase_request(client, headers, supplier_id: int, source_ids: list[int] | None = None) -> dict:
    if source_ids is None:
        source_ids = [_create_department_request(client, headers)["id"]]
    payload = _request_payload(supplier_id)
    payload["source_request_ids"] = source_ids
    resp = client.post(
        "/api/purchase-requests",
        json=payload,
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_supplier_crud_and_toggle(client, auth_headers):
    supplier = _supplier(client, auth_headers)
    assert supplier["name"] == "Cong ty Giay An Phat"
    assert supplier["status"] == "active"
    # `items` khai lúc TẠO phải quay về đủ — trước đây chỗ này chỉ khẳng định danh sách rỗng nên
    # không ai canh đường ghi mặt hàng ngay từ bước tạo NCC.
    assert [i["item_name"] for i in supplier["items"]] == ["Giay Duplex 350gsm", "Keo can mang"]

    listed = client.get("/api/suppliers?q=an phat", headers=auth_headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    updated = client.put(
        f"/api/suppliers/{supplier['id']}",
        json={
            "name": "Cong ty Giay An Phat 2",
            "tax_code": "0101234567",
            "phone": "0901000002",
            "email": "ncc2@example.com",
            "address": "99 Nguyen Trai, TP.HCM",
            "contact_name": "Ms Lan",
            "supplier_group": "paper",
            "status": "active",
            "items": [
                {
                    "item_name": "Giay Duplex 350gsm",
                    "unit": "to",
                    "unit_price": 2200,
                    "vat_percent": 8,
                    "note": "Bao gia thang 7",
                },
                {
                    "item_name": "Keo can mang",
                    "unit": "kg",
                    "unit_price": 80000,
                    "vat_percent": 8,
                },
            ],
        },
        headers=auth_headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["phone"] == "0901000002"
    assert [item["item_name"] for item in updated.json()["items"]] == [
        "Giay Duplex 350gsm",
        "Keo can mang",
    ]
    assert updated.json()["items"][0]["unit_price"] == 2200
    assert updated.json()["items"][0]["vat_percent"] == 8

    toggled = client.patch(f"/api/suppliers/{supplier['id']}/toggle-active", headers=auth_headers)
    assert toggled.status_code == 200
    assert toggled.json()["status"] == "inactive"


def test_supplier_required_contact_fields(client, auth_headers):
    missing_email = {
        "name": "NCC Thieu Email",
        "tax_code": "0109999999",
        "phone": "0909999999",
        "address": "1 Le Loi",
        "contact_name": "Anh Nam",
        "supplier_group": "paper",
    }
    resp = client.post("/api/suppliers", json=missing_email, headers=auth_headers)
    assert resp.status_code == 422

    blank_fields = {
        "name": "NCC Blank",
        "tax_code": " ",
        "phone": "0909999999",
        "email": "blank@example.com",
        "address": " ",
        "contact_name": "Anh Nam",
        "supplier_group": "paper",
    }
    resp = client.post("/api/suppliers", json=blank_fields, headers=auth_headers)
    assert resp.status_code == 422
    assert "Mã số thuế" in resp.json()["detail"]
    assert "Địa chỉ" in resp.json()["detail"]


def test_supplier_item_catalog_deduplicates_by_item_name(client, auth_headers):
    _ensure_catalog_supplier()
    db = SessionLocal()
    try:
        supplier = Supplier(
            name="NCC Catalog Gia Tot",
            tax_code="0100000888",
            phone="0900000888",
            email="catalog2@example.com",
            address="Kho catalog 2",
            contact_name="Catalog 2",
            supplier_group="paper",
            status="active",
        )
        supplier.items = [
            SupplierItem(
                item_name="Giay Duplex 350gsm",
                unit="to",
                unit_price=1800,
                vat_percent=8,
            )
        ]
        db.add(supplier)
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/supplier-items/catalog", headers=auth_headers)

    assert resp.status_code == 200
    matches = [
        item for item in resp.json()["items"] if item["item_name"] == "Giay Duplex 350gsm"
    ]
    assert len(matches) == 1
    assert matches[0]["supplier_count"] == 2
    assert matches[0]["min_unit_price"] == 1800


def test_department_purchase_request_uses_actor_department(client):
    requester_headers = {"Authorization": f"Bearer {_requester_token()}"}
    payload = _department_request_payload()
    payload.pop("source_type")

    resp = client.post(
        "/api/department-purchase-requests",
        json=payload,
        headers=requester_headers,
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["source_type"] == "kinh_doanh"
    assert body["requesting_department_name"] == "Kinh doanh"


def test_department_purchase_request_rejects_past_needed_date(client, auth_headers):
    payload = _department_request_payload()
    payload["needed_date"] = (date.today() - timedelta(days=1)).isoformat()

    resp = client.post(
        "/api/department-purchase-requests",
        json=payload,
        headers=auth_headers,
    )

    assert resp.status_code == 422
    assert "Ngay can hang" in resp.json()["detail"]


def test_department_purchase_request_update_before_purchase_request(client, auth_headers):
    source = _create_department_request(client, auth_headers)
    payload = _department_request_payload()
    payload["purpose"] = "Cap nhat vat tu cho don hang carton"
    payload["needed_date"] = (date.today() + timedelta(days=45)).isoformat()
    payload["note"] = "Da sua truoc khi thu mua lap PMH"
    payload["lines"] = [
        {
            "item_name": "Keo can mang",
            "unit": "kg",
            "quantity": 500,
            "note": "Doi sang keo can mang",
        }
    ]

    resp = client.put(
        f"/api/department-purchase-requests/{source['id']}",
        json=payload,
        headers=auth_headers,
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == source["id"]
    assert body["code"] == source["code"]
    # GỘP mục đích + ghi chú thành MỘT nội dung (chủ chốt 07/08/2026). Client cũ vẫn gửi hai ô
    # `purpose` + `note`, server nối lại — bắt mọi nơi gọi API đổi cùng lúc với giao diện là
    # chuyện không xảy ra được.
    assert body["purpose"] == (
        "Cap nhat vat tu cho don hang carton — Da sua truoc khi thu mua lap PMH"
    )
    assert body["needed_date"] == payload["needed_date"]
    assert body["lines"][0]["item_name"] == "Keo can mang"
    assert body["lines"][0]["quantity"] == 500


def test_department_purchase_request_rejects_material_without_active_supplier(client, auth_headers):
    """YCMH chỉ được chọn hàng đã có NCC đang khai bán."""
    payload = _department_request_payload()
    payload["lines"][0].update({"hang_loai": "giay", "hang_id": 123})

    created = client.post(
        "/api/department-purchase-requests",
        json=payload,
        headers=auth_headers,
    )

    assert created.status_code == 422, created.text
    assert "nha cung cap" in created.json()["detail"].lower()


def test_department_purchase_request_update_permissions_and_status(client, auth_headers):
    requester_headers = {"Authorization": f"Bearer {_requester_token()}"}
    sales2_headers = {"Authorization": f"Bearer {_sales2_token()}"}
    source = _create_department_request(client, requester_headers)
    payload = _department_request_payload()
    payload["purpose"] = "Nguoi khac sua"

    denied = client.put(
        f"/api/department-purchase-requests/{source['id']}",
        json=payload,
        headers=sales2_headers,
    )
    assert denied.status_code == 403

    supplier = _supplier(client, auth_headers, name="NCC Khoa Sua YCMH")
    pr = _create_purchase_request(client, auth_headers, supplier["id"], [source["id"]])
    locked = client.put(
        f"/api/department-purchase-requests/{source['id']}",
        json=payload,
        headers=requester_headers,
    )
    assert pr["sources"][0]["code"] == source["code"]
    assert locked.status_code == 409


def test_department_purchase_request_list_is_scoped_by_department(client, auth_headers):
    requester_headers = {"Authorization": f"Bearer {_requester_token()}"}
    sales_headers = {"Authorization": f"Bearer {_sales_token()}"}
    kinh_doanh_source = _create_department_request(client, requester_headers)
    admin_source = _create_department_request(client, auth_headers)

    sales_list = client.get(
        "/api/department-purchase-requests",
        headers=sales_headers,
    )
    admin_list = client.get(
        "/api/department-purchase-requests",
        headers=auth_headers,
    )
    sales_detail = client.get(
        f"/api/department-purchase-requests/{admin_source['id']}",
        headers=sales_headers,
    )

    assert sales_list.status_code == 200
    sales_codes = {row["code"] for row in sales_list.json()["items"]}
    assert kinh_doanh_source["code"] in sales_codes
    assert admin_source["code"] not in sales_codes
    assert sales_detail.status_code == 404

    assert admin_list.status_code == 200
    admin_codes = {row["code"] for row in admin_list.json()["items"]}
    assert kinh_doanh_source["code"] in admin_codes
    assert admin_source["code"] in admin_codes


def test_phieu_mua_chan_mat_hang_ncc_khong_ban(client, auth_headers):
    """⭐ Một phiếu mua là thoả thuận với MỘT nhà cung cấp, nên mọi dòng phải là thứ NCC đó bán.

    Trước 04/08/2026 chỗ này KHÔNG kiểm gì: chọn NCC A rồi ghi mặt hàng chỉ NCC B bán thì phiếu
    vẫn tạo được, im lặng, tới lúc gửi đơn cho NCC mới vỡ. Đây là hàng rào cho việc tách phiếu
    theo NCC — không có nó thì "mỗi mặt hàng đi theo NCC của nó" chỉ là lời hứa.
    """
    ncc_giay = _supplier(client, auth_headers)          # bán Giay Duplex + Keo can mang
    ncc_khac = _supplier(client, auth_headers, name="Cong ty Bang Keo Minh Long",
                         items=[{"item_name": "Bang keo trong 5cm", "unit": "cuon",
                                 "unit_price": 12000, "vat_percent": 8}])

    def _gui(supplier_id, source_id):
        body = _request_payload(supplier_id)
        body["source_request_ids"] = [source_id]
        return client.post("/api/purchase-requests", json=body, headers=auth_headers)

    # Yêu cầu nguồn để dành riêng: phiếu tạo THÀNH CÔNG sẽ giữ chỗ yêu cầu của nó, còn hai lần bị
    # chặn thì hỏng ở khâu kiểm dòng hàng — trước cả bước giữ chỗ — nên yêu cầu kia vẫn còn trống.
    src_ok = _create_department_request(client, auth_headers)
    src_chan = _create_department_request(client, auth_headers)

    # Cùng payload, chỉ đổi NCC: bên bán thì được, bên không bán thì chặn.
    ok = _gui(ncc_giay["id"], src_ok["id"])
    assert ok.status_code == 201, ok.text

    chan = _gui(ncc_khac["id"], src_chan["id"])
    assert chan.status_code == 422, chan.text
    assert "khong ban" in chan.json()["detail"], chan.text

    # Mặt hàng NGƯNG BÁN cũng không đặt mới được nữa — `has_active_item` (đường YÊU CẦU mua) bỏ
    # sót vế `is_active` này. Tắt thẳng dưới DB vì `SupplierItemIn` không nhận trường `is_active`.
    db = SessionLocal()
    try:
        row = db.query(SupplierItem).filter(
            SupplierItem.supplier_id == ncc_giay["id"],
            SupplierItem.item_name == "Giay Duplex 350gsm",
        ).first()
        row.is_active = False
        db.commit()
    finally:
        db.close()
    ngung = _gui(ncc_giay["id"], src_chan["id"])
    assert ngung.status_code == 422, ngung.text


def _batch_body(source_id, lines):
    return {
        "source_request_ids": [source_id],
        "purpose": "Mua hang cua nhieu nha cung cap",
        "needed_date": (date.today() + timedelta(days=30)).isoformat(),
        "lines": lines,
    }


def test_tach_phieu_theo_ncc_trong_mot_lan(client, auth_headers):
    """⭐ Yêu cầu chứa hàng của HAI nhà cung cấp → ra HAI phiếu, mỗi phiếu một NCC.

    Đây là chỗ mà gọi API tạo phiếu hai lần KHÔNG làm được: phiếu đầu giữ chỗ yêu cầu nguồn, lần
    hai bị chặn ngay. Nên phải có đường tạo cả mẻ.
    """
    ncc_giay = _supplier(client, auth_headers)
    ncc_keo = _supplier(client, auth_headers, name="Cong ty Bang Keo Minh Long",
                        items=[{"item_name": "Bang keo trong 5cm", "unit": "cuon",
                                "unit_price": 12000, "vat_percent": 8}])
    source = _create_department_request(client, auth_headers)

    res = client.post("/api/purchase-requests/batch", headers=auth_headers, json=_batch_body(
        source["id"],
        [
            {"item_name": "Giay Duplex 350gsm", "unit": "to", "quantity": 1000,
             "expected_unit_price": 2200, "supplier_id": ncc_giay["id"]},
            {"item_name": "Bang keo trong 5cm", "unit": "cuon", "quantity": 10,
             "expected_unit_price": 12000, "supplier_id": ncc_keo["id"]},
        ],
    ))
    assert res.status_code == 201, res.text
    phieu = res.json()["items"]
    assert len(phieu) == 2, "hai NCC phải ra hai phiếu"
    assert {p["supplier_id"] for p in phieu} == {ncc_giay["id"], ncc_keo["id"]}
    # Mỗi phiếu chỉ giữ dòng của NCC mình, và cả hai cùng trỏ về một yêu cầu nguồn.
    for p in phieu:
        assert len(p["lines"]) == 1
        assert [s["department_request_id"] for s in p["sources"]] == [source["id"]]


def test_tach_phieu_kiem_het_truoc_khi_tao_cai_nao(client, auth_headers):
    """Nhóm thứ hai sai (NCC không bán thứ đó) ⇒ KHÔNG được để lại phiếu của nhóm đầu.

    Phiếu mồ côi kiểu đó còn giữ chỗ luôn yêu cầu nguồn, người dùng bấm lại lần nữa là tắc mà
    không hiểu vì sao.

    ⚠️ Test này canh việc **kiểm hết trước khi dựng phiếu nào** — đó là hàng rào thật. Việc
    `create_many` gom một commit là lớp thứ hai, và test này KHÔNG chứng minh được lớp đó (đã thử:
    đổi `create_many` thành commit từng cái thì test vẫn xanh, vì vỡ xảy ra trước khi tới đó)."""
    ncc_giay = _supplier(client, auth_headers)
    ncc_keo = _supplier(client, auth_headers, name="Cong ty Bang Keo Minh Long",
                        items=[{"item_name": "Bang keo trong 5cm", "unit": "cuon",
                                "unit_price": 12000, "vat_percent": 8}])
    source = _create_department_request(client, auth_headers)

    res = client.post("/api/purchase-requests/batch", headers=auth_headers, json=_batch_body(
        source["id"],
        [
            {"item_name": "Giay Duplex 350gsm", "unit": "to", "quantity": 1000,
             "expected_unit_price": 2200, "supplier_id": ncc_giay["id"]},
            # NCC keo KHÔNG bán giấy → cả mẻ phải hỏng.
            {"item_name": "Giay Duplex 350gsm", "unit": "to", "quantity": 5,
             "expected_unit_price": 2200, "supplier_id": ncc_keo["id"]},
        ],
    ))
    assert res.status_code == 422, res.text

    danh_sach = client.get("/api/purchase-requests", headers=auth_headers).json()
    assert danh_sach["total"] == 0, "hỏng cả mẻ mà vẫn còn phiếu ⇒ có phiếu mồ côi"
    # Yêu cầu nguồn phải còn nguyên "chờ Thu mua", không bị giữ chỗ dở dang.
    con_lai = client.get(f"/api/department-purchase-requests/{source['id']}",
                         headers=auth_headers).json()
    assert con_lai["status"] == "open"


def test_yeu_cau_chi_xong_khi_moi_phieu_da_ve_hang(client, auth_headers):
    """⭐ Tách hai phiếu: phiếu giấy về hàng trước KHÔNG được làm yêu cầu thành "Xong".

    Trước 04/08/2026 `mark_received` set thẳng mọi yêu cầu nguồn sang Xong ⇒ bộ phận đề nghị nhìn
    vào tưởng đủ hàng trong khi băng keo còn chưa về."""
    ncc_giay = _supplier(client, auth_headers)
    ncc_keo = _supplier(client, auth_headers, name="Cong ty Bang Keo Minh Long",
                        items=[{"item_name": "Bang keo trong 5cm", "unit": "cuon",
                                "unit_price": 12000, "vat_percent": 8}])
    source = _create_department_request(client, auth_headers)
    phieu = client.post("/api/purchase-requests/batch", headers=auth_headers, json=_batch_body(
        source["id"],
        [
            {"item_name": "Giay Duplex 350gsm", "unit": "to", "quantity": 1000,
             "expected_unit_price": 2200, "supplier_id": ncc_giay["id"]},
            {"item_name": "Bang keo trong 5cm", "unit": "cuon", "quantity": 10,
             "expected_unit_price": 12000, "supplier_id": ncc_keo["id"]},
        ],
    )).json()["items"]

    def _trang_thai_yeu_cau():
        return client.get(f"/api/department-purchase-requests/{source['id']}",
                          headers=auth_headers).json()["status"]

    def _ve_hang(pid):
        for buoc in ("submit", "approve", "mark-purchased", "mark-received"):
            # Duyệt phải là người KHÁC người lập; mấy bước còn lại vẫn là việc của thu mua.
            h = _h_duyet() if buoc == "approve" else auth_headers
            r = client.post(f"/api/purchase-requests/{pid}/{buoc}", headers=h, json={})
            assert r.status_code == 200, f"{buoc}: {r.text}"

    _ve_hang(phieu[0]["id"])
    assert _trang_thai_yeu_cau() != "done", "mới một phiếu về hàng mà đã báo Xong"

    _ve_hang(phieu[1]["id"])
    assert _trang_thai_yeu_cau() == "done", "cả hai phiếu về rồi thì phải Xong"


def test_nguoi_lap_khong_duoc_tu_duyet(client, auth_headers):
    """⭐ TÁCH VAI: ai đề xuất chi tiền thì không được là người đồng ý chi.

    Dùng admin — người CÓ ĐỦ quyền duyệt — để chứng minh chốt này chặn theo *ai lập phiếu*, chứ
    không phải chỉ nhờ thiếu quyền. Chốt ở service mới là khoá thật: phân quyền là cấu hình, ai
    cũng bật lại được ở màn Phân quyền mà không ai hay.
    """
    supplier = _supplier(client, auth_headers)
    pr = _create_purchase_request(client, auth_headers, supplier["id"])
    assert client.post(f"/api/purchase-requests/{pr['id']}/submit",
                       headers=auth_headers).status_code == 200

    tu_duyet = client.post(f"/api/purchase-requests/{pr['id']}/approve", headers=auth_headers)
    assert tu_duyet.status_code == 403, tu_duyet.text

    # Phiếu KHÔNG được đổi trạng thái sau cú bấm bị chặn.
    con = client.get(f"/api/purchase-requests/{pr['id']}", headers=auth_headers).json()
    assert con["status"] == "pending_approval"

    # Người khác duyệt thì được.
    assert client.post(f"/api/purchase-requests/{pr['id']}/approve",
                       headers=_h_duyet()).status_code == 200


def test_tu_TU_CHOI_phieu_cua_minh_van_duoc(client, auth_headers):
    """Chỉ chặn DUYỆT, cố ý KHÔNG chặn TỪ CHỐI: từ chối phiếu của chính mình là tự rút lại, vô
    hại — chặn nốt thì phiếu kẹt, không ai gỡ được."""
    supplier = _supplier(client, auth_headers)
    pr = _create_purchase_request(client, auth_headers, supplier["id"])
    client.post(f"/api/purchase-requests/{pr['id']}/submit", headers=auth_headers)
    r = client.post(f"/api/purchase-requests/{pr['id']}/reject",
                    json={"reason": "Tự rút lại"}, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "rejected"


def test_nguoi_chi_co_quyen_huy_chi_don_duoc_phieu_nhap_cua_minh(client, auth_headers):
    """⭐ Huỷ phiếu ĐÃ GỬI DUYỆT là quyết định của người duyệt, không phải của thu mua.

    Người chỉ có `cancel` (nhân viên mua hàng) được dọn phiếu nháp của CHÍNH MÌNH — giữ việc tự
    dọn nháp — nhưng không giết được phiếu đang nằm trên bàn giám đốc, cũng không đụng phiếu của
    người khác."""
    buyer_headers = {"Authorization": f"Bearer {_buyer_token()}"}
    supplier = _supplier(client, buyer_headers, name="NCC Huy")

    # a) Phiếu nháp của CHÍNH MÌNH → huỷ được.
    cua_minh = _create_purchase_request(client, buyer_headers, supplier["id"])
    r = client.post(f"/api/purchase-requests/{cua_minh['id']}/cancel",
                    json={"reason": "Đặt nhầm"}, headers=buyer_headers)
    assert r.status_code == 200, r.text

    # b) Phiếu nháp của NGƯỜI KHÁC → không được.
    cua_nguoi_khac = _create_purchase_request(client, auth_headers, supplier["id"])
    r = client.post(f"/api/purchase-requests/{cua_nguoi_khac['id']}/cancel",
                    json={"reason": "Xen vào"}, headers=buyer_headers)
    assert r.status_code == 403, r.text

    # c) Phiếu của mình nhưng ĐÃ GỬI DUYỆT → không được nữa.
    da_gui = _create_purchase_request(client, buyer_headers, supplier["id"])
    assert client.post(f"/api/purchase-requests/{da_gui['id']}/submit",
                       headers=buyer_headers).status_code == 200
    r = client.post(f"/api/purchase-requests/{da_gui['id']}/cancel",
                    json={"reason": "Đổi ý"}, headers=buyer_headers)
    assert r.status_code == 403, r.text

    # d) Nhưng người CÓ quyền duyệt thì huỷ được phiếu đã gửi duyệt đó.
    r = client.post(f"/api/purchase-requests/{da_gui['id']}/cancel",
                    json={"reason": "Giám đốc dừng"}, headers=_h_duyet())
    assert r.status_code == 200, r.text


def test_coc_du_kien_khong_duoc_vuot_tong_don(client, auth_headers):
    """⭐ CỌC DỰ KIẾN không được lớn hơn TỔNG DỰ KIẾN của đơn (chủ chốt 15/08/2026).

    Không chỉ là con số vô nghĩa: `tran_dat_coc` = cọc dự kiến − cọc đã chi, nên số khai thừa
    thành HẠN MỨC CHI THẬT — kế toán lập được phiếu cọc 10tr cho đơn 2,2tr, tiền rời két rồi mới
    có người hỏi. Test này đi tới tận chỗ đó chứ không dừng ở việc khai."""
    supplier = _supplier(client, auth_headers, name="NCC Coc Vuot")
    # 1000 tờ × 2.200 + 5 kg × 80.000 = 2.600.000đ
    don = _create_purchase_request(client, auth_headers, supplier["id"])
    assert don["total_estimate"] == 2_600_000

    r = client.put(f"/api/purchase-requests/{don['id']}/contract",
                   json={"contract_number": None, "deposit_expected": 2_600_001},
                   headers=auth_headers)
    assert r.status_code == 422, r.text
    assert "lớn hơn tổng dự kiến" in r.json()["detail"]

    # Đúng bằng tổng thì CHO — trả trước 100% là chuyện có thật.
    r = client.put(f"/api/purchase-requests/{don['id']}/contract",
                   json={"contract_number": None, "deposit_expected": 2_600_000},
                   headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["tran_dat_coc"] == 2_600_000, "trần chi cọc phải bám đúng số đã khai"


def test_khong_lach_duoc_bang_cach_SUA_HANG_NHO_LAI(client, auth_headers):
    """Vế bịt lỗ: khai cọc lúc đơn còn to, rồi sửa dòng hàng nhỏ lại.

    Chặn mỗi lúc khai là lách được đúng bằng hai thao tác — mà đơn nhỏ lại thì trần chi cọc vẫn
    giữ nguyên số cũ, tức là lỗ hổng y hệt chỉ đi vòng hơn."""
    supplier = _supplier(client, auth_headers, name="NCC Sua Nho Lai")
    don = _create_purchase_request(client, auth_headers, supplier["id"])
    assert client.put(f"/api/purchase-requests/{don['id']}/contract",
                      json={"contract_number": None, "deposit_expected": 2_000_000},
                      headers=auth_headers).status_code == 200

    def _sua(so_luong: float):
        return client.put(
            f"/api/purchase-requests/{don['id']}",
            json={
                "supplier_id": supplier["id"], "content": "Mua giấy",
                "needed_date": don["needed_date"],
                "source_request_ids": [s["department_request_id"] for s in don["sources"]],
                # Tên/ĐVT phải KHỚP bảng giá của chính NCC này, nếu không vướng luật khác
                # trước (NCC không bán món đó) và test hoá ra canh nhầm chỗ.
                "lines": [{"item_name": "Giay Duplex 350gsm", "unit": "to",
                           "quantity": so_luong, "expected_unit_price": 2200}],
            },
            headers=auth_headers,
        )

    r = _sua(100)          # 100 × 2.200 = 220.000đ < cọc 2tr
    assert r.status_code == 422, r.text
    assert "hạ cọc dự kiến" in r.json()["detail"]

    # Hạ cọc trước thì sửa được — đường lui phải còn, nếu không đơn kẹt vĩnh viễn.
    assert client.put(f"/api/purchase-requests/{don['id']}/contract",
                      json={"contract_number": None, "deposit_expected": 200_000},
                      headers=auth_headers).status_code == 200
    assert _sua(100).status_code == 200


def test_dien_thoai_ncc_phai_du_10_so(client, auth_headers):
    """Số điện thoại NCC phải đủ 10 chữ số (chủ chốt 15/08/2026).

    Gõ thiếu/thừa một số thì gọi không được, mà cái sai đó chỉ lộ ra đúng lúc cần gọi gấp.

    Chặn ở TẦNG SERVICE nên áp cho cả TẠO lẫn SỬA — vá mỗi đường tạo là hồ sơ vẫn hỏng được
    bằng nút Sửa."""
    ho_so = {
        "name": "NCC So Dien Thoai", "tax_code": "0100777001",
        "email": "sdt@x.vn", "address": "HN", "contact_name": "A",
        "supplier_group": "giay",
    }
    r = client.post("/api/suppliers", json={**ho_so, "phone": "090123456"}, headers=auth_headers)
    assert r.status_code == 422, r.text
    assert "10 chữ số" in r.json()["detail"]

    r = client.post("/api/suppliers", json={**ho_so, "phone": "09012345678"}, headers=auth_headers)
    assert r.status_code == 422, "11 số cũng phải chặn"

    r = client.post("/api/suppliers", json={**ho_so, "phone": "090abc4567"}, headers=auth_headers)
    assert r.status_code == 422, "có chữ cái mà vẫn lọt"

    # Dấu cách / gạch KHÔNG phải lỗi — người ta hay gõ "090 123 4567". Nhận, và lưu dạng gọn.
    r = client.post("/api/suppliers", json={**ho_so, "phone": "090 123 4567"}, headers=auth_headers)
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert r.json()["phone"] == "0901234567", "phải lưu dạng đã bỏ dấu cách"

    # SỬA cũng chặn.
    r = client.put(f"/api/suppliers/{sid}",
                   json={**ho_so, "phone": "0901"}, headers=auth_headers)
    assert r.status_code == 422, "sửa lọt thì hồ sơ vẫn hỏng được"


def test_email_ncc_phai_co_a_cong(client, auth_headers):
    """Email thiếu @ (hoặc thiếu đuôi) thì thư gửi đi không bao giờ tới — chặn ngay lúc lưu."""
    ho_so = {
        "name": "NCC Email", "tax_code": "0100777002", "phone": "0901234500",
        "address": "HN", "contact_name": "A", "supplier_group": "giay",
    }
    for xau in ("khongcoacong.vn", "thieu@duoi", "co dau cach@x.vn", "@x.vn", "a@"):
        r = client.post("/api/suppliers", json={**ho_so, "email": xau}, headers=auth_headers)
        assert r.status_code == 422, f"lọt email sai: {xau!r} — {r.text}"

    r = client.post("/api/suppliers", json={**ho_so, "email": "ke.toan@congty.com.vn"},
                    headers=auth_headers)
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    r = client.put(f"/api/suppliers/{sid}", json={**ho_so, "email": "hong"}, headers=auth_headers)
    assert r.status_code == 422, "sửa lọt thì hồ sơ vẫn hỏng được"


def test_seed_bo_phan_mua_hang_khong_co_quyen_duyet(client):
    """Vai của bộ phận Mua hàng không được cấp `thu_mua.can_approve`.

    ⚠️ `_full()` TỰ BẬT `can_approve` — nên chỗ khai phải ghi đè False. Bỏ dòng cấp thêm là chưa
    đủ, mà nhìn code lại tưởng đã gỡ. Test này canh đúng cái bẫy đó."""
    client
    db = SessionLocal()
    try:
        mua_hang = DepartmentRepository(db).get_by_name("Mua hàng")
        assert mua_hang is not None
        roles = RoleRepository(db)
        vai = roles.list_by_department(mua_hang.id)
        assert vai, "không có vai nào ở bộ phận Mua hàng ⇒ test này rỗng, không có răng"
        con_quyen = [
            r.name for r in vai
            if (p := roles.get_permission(r.id, "thu_mua")) is not None and p.can_approve
        ]
        assert con_quyen == [], f"vai bộ phận Mua hàng còn quyền duyệt: {con_quyen}"
    finally:
        db.close()


def _ke_toan_token() -> str:
    """Kế toán: có `ke_toan` scope ALL, KHÔNG có `thu_mua` gì cả."""
    db = SessionLocal()
    try:
        users = UserRepository(db)
        u = users.get_by_username("ke-toan-xem-pmh")
        if u is not None:
            return create_access_token(str(u.id))
        kt = DepartmentRepository(db).get_by_name("Kế toán")
        roles = RoleRepository(db)
        role = roles.create(name="Ke toan xem PMH", department_id=kt.id)
        roles.set_permission(role_id=role.id, module_key="ke_toan",
                             can_read=True, can_create=True, scope=SCOPE_ALL)
        u = users.create(username="ke-toan-xem-pmh", name="Ke toan",
                         password_hash=hash_password("x"))
        users.set_assignment(u, department_id=kt.id, role_id=role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def test_nhan_vien_mua_hang_chi_thay_phieu_cua_minh(client, auth_headers):
    """⭐ Chủ 04/08/2026: *"tôi là nhân viên chỉ thấy đơn của tôi thôi"*.

    Trước đây `list_requests` KHÔNG nhận `actor` — ai có `thu_mua:read` là thấy phiếu toàn công ty,
    bất kể vai khai scope gì. Kiểm ở CẢ danh sách LẪN chi tiết: chặn danh sách mà để chi tiết mở
    thì biết id là đọc được hết, chẳng chặn được gì.
    """
    buyer_headers = {"Authorization": f"Bearer {_buyer_token()}"}
    supplier = _supplier(client, auth_headers, name="NCC Pham Vi")

    cua_admin = _create_purchase_request(client, auth_headers, supplier["id"])
    cua_buyer = _create_purchase_request(client, buyer_headers, supplier["id"])

    # `_buyer_token` khai scope ALL nên mặc định vẫn thấy hết — hạ về `own` để thử đúng luật.
    db = SessionLocal()
    try:
        u = UserRepository(db).get_by_username("buyer-no-approve")
        roles = RoleRepository(db)
        p = roles.get_permission(u.role_id, "thu_mua")
        p.scope = SCOPE_OWN
        db.commit()
    finally:
        db.close()

    ds = client.get("/api/purchase-requests", headers=buyer_headers).json()
    ma = {r["code"] for r in ds["items"]}
    assert cua_buyer["code"] in ma
    assert cua_admin["code"] not in ma, "nhân viên đang thấy phiếu của người khác"

    # Chi tiết cũng phải chặn — 404 chứ không 403, đừng xác nhận phiếu đó có tồn tại.
    assert client.get(f"/api/purchase-requests/{cua_admin['id']}",
                      headers=buyer_headers).status_code == 404
    assert client.get(f"/api/purchase-requests/{cua_buyer['id']}",
                      headers=buyer_headers).status_code == 200


def test_nhan_vien_thu_mua_van_thay_YCMH_cua_moi_phong_ban(client, auth_headers):
    """⭐ HAI DANH SÁCH KHÁC NHAU, đừng gộp phạm vi:

    · YCMH = đơn các phòng ban gửi TỚI thu mua → **hộp việc**, phải thấy hết.
    · PMH  = phiếu do chính thu mua lập → nhân viên chỉ thấy của mình.

    Ngày 04/08/2026 tôi hạ scope `thu_mua` xuống `own` cho yêu cầu "nhân viên chỉ thấy đơn của
    tôi" (nói về PMH) và làm MÙ LUÔN hộp việc — nhân viên thu mua mở màn ra thấy 0 yêu cầu, không
    lập được phiếu cho ai. Chủ phát hiện trên màn thật, không phải test. Đây là chốt bịt lại.
    """
    buyer_headers = {"Authorization": f"Bearer {_buyer_token()}"}
    # Hạ scope thu_mua của nhân viên xuống `own` — đúng cấu hình thật sau migration 0161.
    db = SessionLocal()
    try:
        u = UserRepository(db).get_by_username("buyer-no-approve")
        RoleRepository(db).get_permission(u.role_id, "thu_mua").scope = SCOPE_OWN
        db.commit()
    finally:
        db.close()

    # YCMH do NGƯỜI KHÁC, PHÒNG KHÁC lập.
    cua_phong_khac = _create_department_request(client, auth_headers)

    ds = client.get("/api/department-purchase-requests", headers=buyer_headers)
    assert ds.status_code == 200, ds.text
    ma = {r["code"] for r in ds.json()["items"]}
    assert cua_phong_khac["code"] in ma, (
        "nhân viên thu mua không thấy yêu cầu của phòng ban khác ⇒ hộp việc trống, "
        "không lập được phiếu mua cho ai")


def test_ke_toan_van_thay_HET_don_mua_hang(client, auth_headers):
    """⭐ Vế dễ vỡ nhất khi thêm lọc phạm vi.

    Kế toán KHÔNG có quyền `thu_mua` ⇒ nếu chỉ hỏi mỗi module đó thì `scope_for` trả None, bị co
    về "của mình", và màn Đơn mua hàng thành RỖNG — kế toán không lập được phiếu chi cho ai. Đúng
    cái bẫy đã sập với YCMH sáng nay; `PURCHASE_REQUEST_READER_MODULES` là chỗ chặn nó."""
    kt_headers = {"Authorization": f"Bearer {_ke_toan_token()}"}
    supplier = _supplier(client, auth_headers, name="NCC Ke Toan Nhin")
    cua_admin = _create_purchase_request(client, auth_headers, supplier["id"])

    # Còn NHÁP thì hộp thư kế toán KHÔNG được có (chủ 04/08/2026) — thu mua còn đang sửa.
    ds = client.get("/api/accounting/inbox", headers=kt_headers)
    assert ds.status_code == 200, ds.text
    assert cua_admin["code"] not in {r["code"] for r in ds.json()["items"]}, (
        "đơn nháp lọt vào hộp thư kế toán")

    # Gửi duyệt xong thì phải thấy — đây mới là vế "kế toán thấy HẾT, không bị co phạm vi".
    assert client.post(f"/api/purchase-requests/{cua_admin['id']}/submit",
                       headers=auth_headers).status_code == 200
    ds = client.get("/api/accounting/inbox", headers=kt_headers)
    assert cua_admin["code"] in {r["code"] for r in ds.json()["items"]}
    # Và đọc được chi tiết để lập phiếu chi.
    assert client.get(f"/api/purchase-requests/{cua_admin['id']}",
                      headers=kt_headers).status_code == 200


def test_purchase_request_full_lifecycle(client, auth_headers):
    supplier = _supplier(client, auth_headers)
    source = _create_department_request(client, auth_headers)
    assert re.fullmatch(r"YCMH-\d{6}-[A-Z0-9]{4}", source["code"])
    assert source["lines"][0]["expected_unit_price"] == 0

    pr = _create_purchase_request(client, auth_headers, supplier["id"], [source["id"]])

    assert re.fullmatch(r"PMH-\d{6}-[A-Z0-9]{4}", pr["code"])
    assert pr["status"] == "draft"
    assert pr["supplier_name"] == supplier["name"]
    assert pr["sources"][0]["code"] == source["code"]
    assert pr["created_by_name"] == "Admin"
    assert pr["approved_by_name"] is None
    assert pr["total_estimate"] == 2_600_000
    assert [line["line_total"] for line in pr["lines"]] == [2_200_000, 400_000]
    linked_source = client.get(f"/api/department-purchase-requests/{source['id']}", headers=auth_headers)
    assert linked_source.status_code == 200
    assert linked_source.json()["status"] == "pending_approval"

    submitted = client.post(f"/api/purchase-requests/{pr['id']}/submit", headers=auth_headers)
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "pending_approval"
    assert submitted.json()["submitted_at"] is not None
    linked_source = client.get(f"/api/department-purchase-requests/{source['id']}", headers=auth_headers)
    assert linked_source.json()["status"] == "pending_approval"

    # Duyệt bằng tài khoản KHÁC người lập — admin lập thì admin không tự duyệt được nữa.
    approved = client.post(f"/api/purchase-requests/{pr['id']}/approve", headers=_h_duyet())
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["status"] == "approved"
    assert body["approved_by_name"] == "Nguoi duyet"
    assert body["approved_at"] is not None
    linked_source = client.get(f"/api/department-purchase-requests/{source['id']}", headers=auth_headers)
    assert linked_source.json()["status"] == "in_purchase"

    blocked = client.put(
        f"/api/purchase-requests/{pr['id']}",
        json={**_request_payload(supplier["id"]), "source_request_ids": [source["id"]]},
        headers=auth_headers,
    )
    assert blocked.status_code == 409

    purchased = client.post(f"/api/purchase-requests/{pr['id']}/mark-purchased", headers=auth_headers)
    assert purchased.status_code == 200
    assert purchased.json()["status"] == "purchased"

    received = client.post(f"/api/purchase-requests/{pr['id']}/mark-received", headers=auth_headers)
    assert received.status_code == 200
    assert received.json()["status"] == "received"
    done_source = client.get(f"/api/department-purchase-requests/{source['id']}", headers=auth_headers)
    assert done_source.json()["status"] == "done"


def test_pmh_bi_tu_choi_khong_duoc_tao_don_moi_tu_cung_ycmh(client, auth_headers):
    """Từ chối PMH -> sửa/gửi lại PMH cũ; cả trạng thái lẫn API phải chặn tạo đơn trùng."""
    supplier = _supplier(client, auth_headers, name="NCC Chan PMH Trung")
    source = _create_department_request(client, auth_headers)
    pr = _create_purchase_request(client, auth_headers, supplier["id"], [source["id"]])
    assert client.post(
        f"/api/purchase-requests/{pr['id']}/submit", headers=auth_headers
    ).status_code == 200
    rejected = client.post(
        f"/api/purchase-requests/{pr['id']}/reject",
        json={"reason": "Cần sửa lại giá"},
        headers=_h_duyet(),
    )
    assert rejected.status_code == 200, rejected.text

    source_after = client.get(
        f"/api/department-purchase-requests/{source['id']}", headers=auth_headers
    )
    assert source_after.json()["status"] == "pending_approval", (
        "YCMH về open sẽ làm hiện lại nút Tạo đơn"
    )

    duplicate_payload = _request_payload(supplier["id"])
    duplicate_payload["source_request_ids"] = [source["id"]]
    duplicate = client.post(
        "/api/purchase-requests", json=duplicate_payload, headers=auth_headers
    )
    assert duplicate.status_code == 422, duplicate.text

    corrected_payload = _request_payload(supplier["id"])
    corrected_payload["source_request_ids"] = [source["id"]]
    corrected_payload["purpose"] = "Đã sửa giá theo phản hồi Kế toán"
    corrected = client.put(
        f"/api/purchase-requests/{pr['id']}",
        json=corrected_payload,
        headers=auth_headers,
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["id"] == pr["id"]
    assert corrected.json()["status"] == "rejected"

    resubmitted = client.post(
        f"/api/purchase-requests/{pr['id']}/submit", headers=auth_headers
    )
    assert resubmitted.status_code == 200, resubmitted.text
    assert resubmitted.json()["status"] == "pending_approval"


def test_purchase_request_line_discount_and_vat(client, auth_headers):
    supplier = _supplier(client, auth_headers)
    source = _create_department_request(client, auth_headers)
    payload = _request_payload(supplier["id"])
    payload["source_request_ids"] = [source["id"]]
    payload["lines"] = [
        {
            "item_name": "Giay Duplex 350gsm",
            "unit": "to",
            "quantity": 1000,
            "expected_unit_price": 2200,
            "discount_percent": 10,
            "vat_percent": 8,
        }
    ]

    resp = client.post("/api/purchase-requests", json=payload, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    line = body["lines"][0]
    assert line["discount_amount"] == 220_000
    assert line["vat_amount"] == 158_400
    assert line["line_total"] == 2_138_400
    assert body["total_estimate"] == 2_138_400
    assert body["expected_receipt_date"] == payload["expected_receipt_date"]


def test_purchase_request_delete_only_draft(client, auth_headers):
    supplier = _supplier(client, auth_headers)
    draft = _create_purchase_request(client, auth_headers, supplier["id"])
    assert client.delete(f"/api/purchase-requests/{draft['id']}", headers=auth_headers).status_code == 204

    pending = _create_purchase_request(client, auth_headers, supplier["id"])
    assert client.post(f"/api/purchase-requests/{pending['id']}/submit", headers=auth_headers).status_code == 200
    assert client.delete(f"/api/purchase-requests/{pending['id']}", headers=auth_headers).status_code == 409


def test_o_gop_con_ghi_chu_thi_van_hop_le(client, auth_headers):
    """Mục đích + ghi chú nay là MỘT ô. Xoá mục đích mà còn ghi chú ⇒ nội dung vẫn có chữ."""
    supplier = _supplier(client, auth_headers)
    source = _create_department_request(client, auth_headers)
    payload = _request_payload(supplier["id"])
    payload["source_request_ids"] = [source["id"]]
    payload["purpose"] = " "
    payload["note"] = "Can bao gia truoc khi mua"
    resp = client.post("/api/purchase-requests", json=payload, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["content"] == "Can bao gia truoc khi mua"


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _file_vat_tu(rows, header=("Tên hàng*", "Đơn vị*", "Đơn giá*", "VAT %", "Ghi chú")) -> bytes:
    from io import BytesIO

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    if header:
        ws.append(list(header))
    for row in rows:
        ws.append(list(row))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _nhap(client, headers, data: bytes):
    return client.post(
        "/api/suppliers/items/import",
        files={"file": ("vat-tu.xlsx", data, XLSX_MIME)},
        headers=headers,
    )


def test_mau_va_xuat_vat_tu_ra_file_xlsx(client, auth_headers):
    """Mẫu tải về phải ĐỌC LẠI ĐƯỢC bằng chính đường nhập — mẫu mà sai tiêu đề là vô dụng."""
    mau = client.get("/api/suppliers/items/template.xlsx", headers=auth_headers)
    assert mau.status_code == 200, mau.text
    assert mau.headers["content-type"].startswith(XLSX_MIME)
    assert mau.content[:2] == b"PK"  # .xlsx là zip

    doc_lai = _nhap(client, auth_headers, mau.content)
    assert doc_lai.status_code == 200, doc_lai.text
    ten = [i["item_name"] for i in doc_lai.json()["items"]]
    assert "Giấy Duplex 350gsm" in ten

    supplier = _supplier(client, auth_headers)
    xuat = client.get(
        f"/api/suppliers/{supplier['id']}/items/export.xlsx", headers=auth_headers
    )
    assert xuat.status_code == 200, xuat.text
    assert "attachment" in xuat.headers["content-disposition"]
    vong_lai = _nhap(client, auth_headers, xuat.content)
    assert vong_lai.status_code == 200, vong_lai.text
    # Xuất ra rồi nhập lại phải ra ĐÚNG danh mục cũ — đây là đường người dùng hay đi nhất
    # (xuất về sửa giá trong Excel rồi nhập lại).
    assert {(i["item_name"], i["unit"]) for i in vong_lai.json()["items"]} == {
        (i["item_name"], i["unit"]) for i in supplier["items"]
    }


def test_nhap_vat_tu_dong_hong_khong_huy_dong_lanh(client, auth_headers):
    data = _file_vat_tu([
        ("Giay Couche 150gsm", "to", 1500, 8, "OK"),
        ("", "to", 1000, 8, "thieu ten"),
        ("Muc in đen", "", 500000, 10, "thieu don vi"),
        ("Muc in xanh", "kg", "khong-phai-so", 10, ""),
        ("Muc in do", "kg", 0, 10, "gia 0"),
        ("Bang keo", "cuon", 12000, 200, "VAT qua 100"),
        ("Pallet go", "cai", 250000, 5, ""),
    ])
    resp = _nhap(client, auth_headers, data)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert [i["item_name"] for i in body["items"]] == ["Giay Couche 150gsm", "Pallet go"]
    assert body["total_rows"] == 7
    # Số dòng phải là số dòng NGƯỜI DÙNG thấy trong Excel (tính cả dòng tiêu đề).
    assert [e["row"] for e in body["errors"]] == [3, 4, 5, 6, 7]


def test_nhap_vat_tu_trung_trong_file_thi_lay_dong_duoi(client, auth_headers):
    data = _file_vat_tu([
        ("Giay Duplex 350gsm", "to", 2200, 8, "gia cu"),
        ("  giay duplex 350GSM ", "TO", 2500, 8, "gia moi"),
    ])
    body = _nhap(client, auth_headers, data).json()
    assert len(body["items"]) == 1, "cùng tên cùng ĐVT thì KHÔNG được đẻ dòng thứ hai"
    assert body["items"][0]["unit_price"] == 2500
    assert body["errors"] and body["errors"][0]["row"] == 3


def test_nhap_vat_tu_chan_file_hong_thieu_cot_va_qua_tran(client, auth_headers):
    hong = _nhap(client, auth_headers, b"day khong phai file excel")
    assert hong.status_code == 422
    assert "Excel" in hong.json()["detail"]

    thieu_cot = _file_vat_tu([("Giay", "to", 1000, 8, "")], header=("A", "B", "C", "D", "E"))
    resp = _nhap(client, auth_headers, thieu_cot)
    assert resp.status_code == 422
    assert "Tên hàng" in resp.json()["detail"]

    chi_tieu_de = _file_vat_tu([])
    resp = _nhap(client, auth_headers, chi_tieu_de)
    assert resp.status_code == 422

    qua_tran = _file_vat_tu([(f"Vat tu {i}", "cai", 1000 + i, 8, "") for i in range(501)])
    resp = _nhap(client, auth_headers, qua_tran)
    assert resp.status_code == 422
    assert "500" in resp.json()["detail"]


def test_nhap_vat_tu_chap_gia_co_dau_phan_cach(client, auth_headers):
    """Excel trả về đủ kiểu tuỳ ô định dạng gì — chặn ở đây là người dùng phải sửa tay 200 dòng."""
    data = _file_vat_tu([
        ("Giay Ford A4", "ram", "2.200", "8", ""),
        ("Giay Ford A3", "ram", "4,400", "8,5", ""),
        ("Giay Ford A2", "ram", 8800.0, "10%", ""),
    ])
    body = _nhap(client, auth_headers, data).json()
    assert body["errors"] == []
    assert [i["unit_price"] for i in body["items"]] == [2200, 4400, 8800]
    assert [i["vat_percent"] for i in body["items"]] == [8, 8.5, 10]


def test_o_gop_khong_bi_cat_500_ky_tu(client, auth_headers):
    """Giao dien MOI chi gui `content`, KHONG gui `purpose`.

    Cot `purpose` chi con giu ban cat 500 ky tu cho phieu cu, nen tran cua no khong duoc phep
    chan noi dung dai — nguoi khai go het 600 chu roi an 422 la mat trang."""
    dai = ("Thieu giay cho don hang carton. " * 30).strip()  # ~960 ky tu
    assert len(dai) > 500

    ycmh_payload = _department_request_payload()
    ycmh_payload.pop("purpose")
    ycmh_payload.pop("note")
    ycmh_payload["content"] = dai
    ycmh = client.post(
        "/api/department-purchase-requests", json=ycmh_payload, headers=auth_headers
    )
    assert ycmh.status_code == 201, ycmh.text
    assert ycmh.json()["content"] == dai

    supplier = _supplier(client, auth_headers)
    pmh_payload = _request_payload(supplier["id"])
    pmh_payload.pop("purpose")
    pmh_payload.pop("note")
    pmh_payload["content"] = dai
    pmh_payload["source_request_ids"] = [ycmh.json()["id"]]
    pmh = client.post("/api/purchase-requests", json=pmh_payload, headers=auth_headers)
    assert pmh.status_code == 201, pmh.text
    assert pmh.json()["content"] == dai
    # Phieu mua lap tu YCMH: nguon phai tra ve NGUYEN VAN noi dung, khong phai ban cat.
    assert pmh.json()["sources"][0]["content"] == dai


def test_o_gop_trong_ca_hai_thi_bao_loi(client, auth_headers):
    """Bo `purpose` khoi schema roi thi cho trong van phai bi chan — o nay VAN bat buoc."""
    payload = _department_request_payload()
    payload.pop("purpose")
    payload.pop("note")
    payload["content"] = "   "
    resp = client.post(
        "/api/department-purchase-requests", json=payload, headers=auth_headers
    )
    assert resp.status_code == 422, resp.text
    assert "Noi dung" in resp.json()["detail"]


def test_purchase_request_required_header_and_line_fields(client, auth_headers):
    supplier = _supplier(client, auth_headers)
    source = _create_department_request(client, auth_headers)

    missing_supplier = _request_payload(supplier["id"])
    missing_supplier["source_request_ids"] = [source["id"]]
    missing_supplier.pop("supplier_id")
    assert (
        client.post("/api/purchase-requests", json=missing_supplier, headers=auth_headers).status_code
        == 422
    )

    missing_source = _request_payload(supplier["id"])
    resp = client.post("/api/purchase-requests", json=missing_source, headers=auth_headers)
    assert resp.status_code == 422

    # Ô GỘP (07/08/2026): mục đích + ghi chú nay là MỘT nội dung ⇒ phải trống CẢ HAI mới là trống.
    # (Ca "xoá mục đích nhưng còn ghi chú vẫn qua" test riêng ở dưới — ở đây tạo phiếu thành công
    # sẽ GIỮ CHỖ yêu cầu nguồn, làm hỏng các vế kiểm còn lại của chính test này.)
    blank_purpose = _request_payload(supplier["id"])
    blank_purpose["source_request_ids"] = [source["id"]]
    blank_purpose["purpose"] = " "
    blank_purpose["note"] = " "
    resp = client.post("/api/purchase-requests", json=blank_purpose, headers=auth_headers)
    assert resp.status_code == 422
    assert "Nội dung" in resp.json()["detail"]

    missing_needed_date = _request_payload(supplier["id"])
    missing_needed_date["source_request_ids"] = [source["id"]]
    missing_needed_date.pop("needed_date")
    assert (
        client.post("/api/purchase-requests", json=missing_needed_date, headers=auth_headers).status_code
        == 422
    )

    past_expected_receipt = _request_payload(supplier["id"])
    past_expected_receipt["source_request_ids"] = [source["id"]]
    past_expected_receipt["expected_receipt_date"] = (date.today() - timedelta(days=1)).isoformat()
    resp = client.post("/api/purchase-requests", json=past_expected_receipt, headers=auth_headers)
    assert resp.status_code == 422
    assert "Ngay du kien nhan hang" in resp.json()["detail"]

    # ⭐ Nhận hàng SỚM hơn ngày cần thì PHẢI cho (chủ 03/08/2026). Đây là trường hợp MONG MUỐN —
    # bản trước chặn nó, tức cấm đúng cái tốt và ép mọi kế hoạch về sát hạn hoặc trễ.
    som_hon_ngay_can = _request_payload(supplier["id"])
    som_hon_ngay_can["source_request_ids"] = [source["id"]]
    som_hon_ngay_can["needed_date"] = (date.today() + timedelta(days=20)).isoformat()
    som_hon_ngay_can["expected_receipt_date"] = (date.today() + timedelta(days=10)).isoformat()
    resp = client.post("/api/purchase-requests", json=som_hon_ngay_can, headers=auth_headers)
    assert resp.status_code == 201, resp.text

    bad_line = _request_payload(supplier["id"])
    bad_line["source_request_ids"] = [source["id"]]
    bad_line["lines"][0]["unit"] = " "
    resp = client.post("/api/purchase-requests", json=bad_line, headers=auth_headers)
    assert resp.status_code == 422
    assert "Đơn vị tính" in resp.json()["detail"]

    zero_price = _request_payload(supplier["id"])
    zero_price["source_request_ids"] = [source["id"]]
    zero_price["lines"][0]["expected_unit_price"] = 0
    assert (
        client.post("/api/purchase-requests", json=zero_price, headers=auth_headers).status_code
        == 422
    )

    second_source = _create_department_request(client, auth_headers)
    multiple_sources = _request_payload(supplier["id"])
    multiple_sources["source_request_ids"] = [source["id"], second_source["id"]]
    resp = client.post("/api/purchase-requests", json=multiple_sources, headers=auth_headers)
    assert resp.status_code == 422
    assert "chi duoc gan 1" in resp.json()["detail"]


def test_purchase_request_validates_active_supplier(client, auth_headers):
    supplier = _supplier(client, auth_headers, name="NCC Tam Ngung")
    source = _create_department_request(client, auth_headers)
    assert client.patch(f"/api/suppliers/{supplier['id']}/toggle-active", headers=auth_headers).status_code == 200

    payload = _request_payload(supplier["id"])
    payload["source_request_ids"] = [source["id"]]
    resp = client.post(
        "/api/purchase-requests",
        json=payload,
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_purchase_permissions(client, auth_headers):
    sales_headers = {"Authorization": f"Bearer {_sales_token()}"}
    sales2_headers = {"Authorization": f"Bearer {_sales2_token()}"}
    requester_headers = {"Authorization": f"Bearer {_requester_token()}"}
    buyer_headers = {"Authorization": f"Bearer {_buyer_token()}"}
    approver_headers = {"Authorization": f"Bearer {_buyer_approver_token()}"}

    assert client.get("/api/suppliers", headers=sales_headers).status_code == 403
    assert client.get("/api/purchase-requests", headers=sales_headers).status_code == 403
    assert client.get("/api/department-purchase-requests", headers=sales_headers).status_code == 200
    denied = client.get("/api/department-purchase-requests/can-create", headers=sales_headers)
    assert denied.status_code == 200 and denied.json()["can_create"] is False
    blocked_source = client.post(
        "/api/department-purchase-requests",
        json=_department_request_payload(),
        headers=sales_headers,
    )
    assert blocked_source.status_code == 403
    permitted = client.get("/api/department-purchase-requests/can-create", headers=requester_headers)
    assert permitted.status_code == 200 and permitted.json()["can_create"] is True
    sales_source = client.post(
        "/api/department-purchase-requests",
        json=_department_request_payload(),
        headers=requester_headers,
    )
    assert sales_source.status_code == 201, sales_source.text
    source_id = sales_source.json()["id"]
    assert (
        client.post(
            f"/api/department-purchase-requests/{source_id}/cancel",
            json={"reason": "Nguoi khac huy"},
            headers=sales2_headers,
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/department-purchase-requests/{source_id}/cancel",
            json={"reason": "Nguoi tao huy"},
            headers=requester_headers,
        ).status_code
        == 200
    )
    admin_source = client.post(
        "/api/department-purchase-requests",
        json=_department_request_payload(),
        headers=auth_headers,
    ).json()
    assert (
        client.post(
            f"/api/department-purchase-requests/{admin_source['id']}/cancel",
            json={"reason": "Admin huy"},
            headers=auth_headers,
        ).status_code
        == 200
    )

    supplier = _supplier(client, buyer_headers, name="NCC Buyer")
    buyer_pr = _create_purchase_request(client, buyer_headers, supplier["id"])
    assert client.post(f"/api/purchase-requests/{buyer_pr['id']}/submit", headers=buyer_headers).status_code == 200
    assert client.post(f"/api/purchase-requests/{buyer_pr['id']}/approve", headers=buyer_headers).status_code == 403
    assert client.post(f"/api/purchase-requests/{buyer_pr['id']}/approve", headers=approver_headers).status_code == 200


# --- lịch sử trạng thái (đợt 2, chủ chốt 07/08/2026) -------------------------


def test_lich_su_ghi_dong_khi_nguoi_bam(client, auth_headers):
    """Người bấm ⇒ dòng lịch sử có TÊN và `source='nguoi'`."""
    supplier = _supplier(client, auth_headers)
    source = _create_department_request(client, auth_headers)
    payload = _request_payload(supplier["id"])
    payload["source_request_ids"] = [source["id"]]
    pmh = client.post("/api/purchase-requests", json=payload, headers=auth_headers).json()

    assert client.post(
        f"/api/purchase-requests/{pmh['id']}/submit", headers=auth_headers
    ).status_code == 200

    body = client.get(f"/api/purchase-requests/{pmh['id']}", headers=auth_headers).json()
    ls = body["status_history"]
    assert ls[0]["from_status"] == "draft"
    assert ls[0]["to_status"] == "pending_approval"
    assert ls[0]["source"] == "nguoi"
    assert ls[0]["changed_by_name"]


def test_lich_su_ghi_dong_MAY_khi_ycmh_tu_suy(client, auth_headers):
    """YCMH đổi trạng thái do MÁY suy từ phiếu con ⇒ `source='may'`, không tên người.

    Không phân biệt người/máy thì lịch sử hiện một dòng đổi trạng thái không tên ai, người đọc
    tưởng mất dữ liệu."""
    supplier = _supplier(client, auth_headers)
    source = _create_department_request(client, auth_headers)
    payload = _request_payload(supplier["id"])
    payload["source_request_ids"] = [source["id"]]
    client.post("/api/purchase-requests", json=payload, headers=auth_headers)

    ycmh = client.get(
        f"/api/department-purchase-requests/{source['id']}", headers=auth_headers
    ).json()
    may = [h for h in ycmh["status_history"] if h["source"] == "may"]
    assert may, "YCMH bị giữ chỗ khi thu mua lập phiếu — phải có dòng do MÁY đổi"
    assert may[0]["changed_by_name"] is None


def test_lich_su_khong_de_dong_rac_khi_trang_thai_khong_doi(client, auth_headers):
    """Suy lại mà ra TRÙNG trạng thái cũ thì không ghi gì.

    YCMH được suy lại ở MỌI thao tác chạm phiếu con; ghi cả lần không đổi thì mỗi cú bấm đẻ một
    dòng rác và lịch sử thành vô dụng."""
    supplier = _supplier(client, auth_headers)
    source = _create_department_request(client, auth_headers)
    payload = _request_payload(supplier["id"])
    payload["source_request_ids"] = [source["id"]]
    pmh = client.post("/api/purchase-requests", json=payload, headers=auth_headers).json()

    truoc = len(
        client.get(
            f"/api/department-purchase-requests/{source['id']}", headers=auth_headers
        ).json()["status_history"]
    )
    # Sửa phiếu mua: KHÔNG đụng trạng thái ⇒ YCMH suy lại ra trùng, không được đẻ dòng nào.
    sua = dict(payload)
    sua["purpose"] = "Doi noi dung, khong doi trang thai"
    client.put(f"/api/purchase-requests/{pmh['id']}", json=sua, headers=auth_headers)
    sau = len(
        client.get(
            f"/api/department-purchase-requests/{source['id']}", headers=auth_headers
        ).json()["status_history"]
    )
    assert sau == truoc


def test_ly_do_huy_khong_de_len_noi_dung(client, auth_headers):
    """Lý do huỷ vào cột RIÊNG. Trước 07/08/2026 `cancel()` chạy `row.note = reason` — GHI ĐÈ mất
    ghi chú của người lập."""
    supplier = _supplier(client, auth_headers)
    source = _create_department_request(client, auth_headers)
    payload = _request_payload(supplier["id"])
    payload["source_request_ids"] = [source["id"]]
    pmh = client.post("/api/purchase-requests", json=payload, headers=auth_headers).json()
    noi_dung_goc = client.get(
        f"/api/purchase-requests/{pmh['id']}", headers=auth_headers
    ).json()["content"]

    r = client.post(
        f"/api/purchase-requests/{pmh['id']}/cancel",
        json={"reason": "Doi nha cung cap khac"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = client.get(f"/api/purchase-requests/{pmh['id']}", headers=auth_headers).json()
    assert body["content"] == noi_dung_goc, "nội dung gốc KHÔNG được bị đè"
    assert body["reject_reason"] == "Doi nha cung cap khac"
    assert body["status_history"][0]["reason"] == "Doi nha cung cap khac"


# --- badge thông báo Thu mua (notify-summary, đợt 2) -------------------------


def _notify(client, headers, expect: int = 200) -> dict:
    r = client.get("/api/purchase-requests/notify-summary", headers=headers)
    assert r.status_code == expect, r.text
    return r.json() if expect == 200 else {}


def _pmh_bi_tu_choi(client, headers, supplier_id: int) -> dict:
    """PMH đi trọn đường tới BỊ TỪ CHỐI và vẫn giữ YCMH nguồn để sửa/gửi lại."""
    pr = _create_purchase_request(client, headers, supplier_id)
    assert client.post(
        f"/api/purchase-requests/{pr['id']}/submit", headers=headers
    ).status_code == 200
    r = client.post(
        f"/api/purchase-requests/{pr['id']}/reject",
        json={"reason": "Gia cao hon du toan"},
        headers=_h_duyet(),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "rejected"
    return r.json()


def test_chi_tiet_ycmh_hien_so_da_giao_theo_dot(client, auth_headers):
    """Chi tiet YEU CAU phai noi giao BAO NHIEU, khong chi noi "giao mot phan".

    Loi truoc 09/08/2026: `_tinh_trang_tung_dong` doc THANG `pl.received_quantity` — cot DORMANT
    voi moi phieu theo doi bang DOT GIAO. Hang ve 2/3 dot ma chi tiet yeu cau van bao "chua nhan
    gi" ⇒ bo phan tuong thu mua chua lam, goi dien giuc nham. Phai di qua `qty_thuc_nhan` de ba
    man (Yeu cau · Mua hang · Cong no) noi CUNG MOT so.
    """
    supplier = _supplier(client, auth_headers)
    source = _create_department_request(client, auth_headers)

    payload = _request_payload(supplier["id"])
    payload["source_request_ids"] = [source["id"]]
    payload["lines"][0]["department_request_line_id"] = source["lines"][0]["id"]
    pr = client.post("/api/purchase-requests", json=payload, headers=auth_headers).json()
    assert client.post(
        f"/api/purchase-requests/{pr['id']}/submit", headers=auth_headers
    ).status_code == 200
    assert client.post(
        f"/api/purchase-requests/{pr['id']}/approve", headers=_h_duyet()
    ).status_code == 200
    assert client.post(
        f"/api/purchase-requests/{pr['id']}/mark-purchased", headers=auth_headers
    ).status_code == 200

    dong = pr["lines"][0]
    assert dong["quantity"] == 1000

    # Giao DO: 400/1000 — dung ca ma man dang khong noi duoc so.
    r = client.post(
        f"/api/purchase-requests/{pr['id']}/deliveries",
        json={
            "delivery_date": date.today().isoformat(),
            "lines": [{"purchase_request_line_id": dong["id"], "quantity": 400}],
        },
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text

    ct = client.get(
        f"/api/department-purchase-requests/{source['id']}", headers=auth_headers
    ).json()
    ff = next(l["fulfilment"] for l in ct["lines"] if l["fulfilment"] is not None)
    assert ff["purchase_status"] == "partially_received"
    assert ff["ordered_quantity"] == 1000
    assert ff["received_quantity"] == 400, "phai la TONG cac dot, khong phai cot received_quantity"

    # Giao them dot 2 ⇒ so phai CONG DON, khong phai de len.
    assert client.post(
        f"/api/purchase-requests/{pr['id']}/deliveries",
        json={
            "delivery_date": date.today().isoformat(),
            "lines": [{"purchase_request_line_id": dong["id"], "quantity": 350}],
        },
        headers=auth_headers,
    ).status_code == 200

    ct2 = client.get(
        f"/api/department-purchase-requests/{source['id']}", headers=auth_headers
    ).json()
    ff2 = next(l["fulfilment"] for l in ct2["lines"] if l["fulfilment"] is not None)
    assert ff2["received_quantity"] == 750


def test_lich_su_don_mua_co_cac_moc_dot_giao_va_so_luong(client, auth_headers):
    """Đợt giao không nhất thiết đổi trạng thái, nhưng bắt buộc hiện trong lịch sử Đơn mua."""
    supplier = _supplier(client, auth_headers)
    source = _create_department_request(client, auth_headers)
    payload = _request_payload(supplier["id"])
    payload["source_request_ids"] = [source["id"]]
    pr = client.post("/api/purchase-requests", json=payload, headers=auth_headers).json()
    assert client.post(f"/api/purchase-requests/{pr['id']}/submit", headers=auth_headers).status_code == 200
    assert client.post(f"/api/purchase-requests/{pr['id']}/approve", headers=_h_duyet()).status_code == 200
    assert client.post(f"/api/purchase-requests/{pr['id']}/mark-purchased", headers=auth_headers).status_code == 200

    first = client.post(
        f"/api/purchase-requests/{pr['id']}/deliveries",
        json={
            "delivery_date": date.today().isoformat(),
            "lines": [{"purchase_request_line_id": pr["lines"][0]["id"], "quantity": 400}],
        },
        headers=auth_headers,
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["deliveries"][0]["lines"][0]["quantity"] == 400
    created = next(item for item in body["activity_history"] if item["event_type"] == "delivery_created")
    assert "Đợt 1" in created["detail"]
    assert "400" in created["detail"]
    assert created["actor_name"] == "Admin"

    delivery_id = body["deliveries"][0]["id"]
    updated = client.put(
        f"/api/purchase-requests/{pr['id']}/deliveries/{delivery_id}",
        json={
            "delivery_date": date.today().isoformat(),
            "lines": [{"purchase_request_line_id": pr["lines"][0]["id"], "quantity": 450}],
        },
        headers=auth_headers,
    )
    assert updated.status_code == 200, updated.text
    assert any(item["event_type"] == "delivery_updated" for item in updated.json()["activity_history"])

    deleted = client.delete(
        f"/api/purchase-requests/{pr['id']}/deliveries/{delivery_id}", headers=auth_headers
    )
    assert deleted.status_code == 200, deleted.text
    activity = deleted.json()["activity_history"]
    assert any(item["event_type"] == "delivery_deleted" for item in activity)
    assert any(item["event_type"] == "status" for item in activity)


def test_chi_tiet_ycmh_phieu_khong_co_dot_giao_van_theo_luat_cu(client, auth_headers):
    """Phieu CHUA co dot giao nao (moi phieu lap truoc 06/08/2026) phai giu nguyen luat cu.

    `received_quantity` = None nghia la CHUA CO TIN, khong phai "nhan 0" — doi thanh 0 la moi don
    cu tut ve nhan 0 va giao dien bao giao thieu hang loat.
    """
    supplier = _supplier(client, auth_headers)
    source = _create_department_request(client, auth_headers)
    payload = _request_payload(supplier["id"])
    payload["source_request_ids"] = [source["id"]]
    payload["lines"][0]["department_request_line_id"] = source["lines"][0]["id"]
    pr = client.post("/api/purchase-requests", json=payload, headers=auth_headers).json()
    assert pr["id"]

    ct = client.get(
        f"/api/department-purchase-requests/{source['id']}", headers=auth_headers
    ).json()
    ff = next(l["fulfilment"] for l in ct["lines"] if l["fulfilment"] is not None)
    assert ff["received_quantity"] is None, "chua co dot giao + chua khai ⇒ CHUA CO TIN"
    assert ff["ordered_quantity"] == 1000


def _dot_giao_qua_han(client, headers, supplier_id: int) -> dict:
    """Một đợt giao ĐÃ QUÁ HẠN trả và KHÔNG có phiếu chi nào ⇒ còn nợ nguyên."""
    pr = _create_purchase_request(client, headers, supplier_id)
    assert client.post(
        f"/api/purchase-requests/{pr['id']}/submit", headers=headers
    ).status_code == 200
    assert client.post(
        f"/api/purchase-requests/{pr['id']}/approve", headers=_h_duyet()
    ).status_code == 200
    assert client.post(
        f"/api/purchase-requests/{pr['id']}/mark-purchased", headers=headers
    ).status_code == 200
    r = client.post(
        f"/api/purchase-requests/{pr['id']}/deliveries",
        json={
            "delivery_date": (date.today() - timedelta(days=20)).isoformat(),
            "due_date": (date.today() - timedelta(days=5)).isoformat(),
            "lines": [{"purchase_request_line_id": pr["lines"][0]["id"], "quantity": 100}],
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _ha_scope_thu_mua_ve_own(username: str) -> None:
    db = SessionLocal()
    try:
        u = UserRepository(db).get_by_username(username)
        RoleRepository(db).get_permission(u.role_id, "thu_mua").scope = SCOPE_OWN
        db.commit()
    finally:
        db.close()


def test_notify_summary_dem_dung_ba_con_so(client, auth_headers):
    """Ba con số việc-phải-làm của Thu mua, dựng từ ca dữ liệu thật."""
    supplier = _supplier(client, auth_headers, name="NCC Badge Thu Mua")

    # a) Một YCMH để nguyên 'Chờ mua' — việc đang nằm trên bàn thu mua.
    _create_department_request(client, auth_headers)
    # b) Một PMH bị từ chối; YCMH nguồn vẫn bị giữ nên KHÔNG cộng vào hàng "chờ lập đơn".
    _pmh_bi_tu_choi(client, auth_headers, supplier["id"])
    # c) Một đợt giao quá hạn còn nợ (YCMH nguồn của đơn này đã sang 'Đang mua', không đếm).
    _dot_giao_qua_han(client, auth_headers, supplier["id"])

    assert _notify(client, auth_headers) == {
        "ycmh_cho_lap_phieu": 1,
        "pmh_bi_tu_choi": 1,
        "dot_giao_qua_han": 1,
    }


def test_notify_summary_pmh_bi_tu_choi_gui_lai_thi_thoi_dem(client, auth_headers):
    """Gửi lại chính PMH bị từ chối thì việc sửa phiếu đã xử lý, badge phải hết."""
    supplier = _supplier(client, auth_headers, name="NCC Badge Gui Lai")
    tu_choi = _pmh_bi_tu_choi(client, auth_headers, supplier["id"])
    assert _notify(client, auth_headers)["pmh_bi_tu_choi"] == 1

    gui_lai = client.post(
        f"/api/purchase-requests/{tu_choi['id']}/submit", headers=auth_headers
    )
    assert gui_lai.status_code == 200, gui_lai.text

    s = _notify(client, auth_headers)
    assert s["pmh_bi_tu_choi"] == 0
    assert s["ycmh_cho_lap_phieu"] == 0


def test_notify_summary_dem_theo_pham_vi_nguoi_xem(client, auth_headers):
    """⭐ RÀNG BUỘC SỐ 1 — badge đếm theo PHẠM VI CỦA NGƯỜI XEM.

    Đếm toàn công ty cho người chỉ thấy phiếu của mình thì badge báo 2 mà mở màn ra có 1: người
    dùng mất tin vào con số. Test giữ CẢ HAI vế, vì chúng dùng hai phép lọc khác nhau:

    · `pmh_bi_tu_choi` = PHIẾU MUA ⇒ theo `_purchase_scope`: nhân viên scope `own` đếm ít hơn admin.
    · `ycmh_cho_lap_phieu` = HỘP VIỆC ⇒ nhân viên thu mua scope `own` vẫn phải đếm đủ mọi phòng.
      Siết luôn cả số này theo `_purchase_scope` là lặp lại sự cố 04/08/2026 (badge 0 trong khi
      màn YCMH đầy việc).
    """
    buyer_headers = {"Authorization": f"Bearer {_buyer_token()}"}
    supplier = _supplier(client, auth_headers, name="NCC Badge Pham Vi")

    _pmh_bi_tu_choi(client, auth_headers, supplier["id"])   # của admin
    _pmh_bi_tu_choi(client, buyer_headers, supplier["id"])  # của nhân viên
    _ha_scope_thu_mua_ve_own("buyer-no-approve")

    cua_admin = _notify(client, auth_headers)
    cua_buyer = _notify(client, buyer_headers)

    assert cua_admin["pmh_bi_tu_choi"] == 2
    assert cua_buyer["pmh_bi_tu_choi"] == 1, (
        "nhân viên scope `own` đang đếm cả phiếu của người khác")
    assert cua_buyer["ycmh_cho_lap_phieu"] == cua_admin["ycmh_cho_lap_phieu"] == 0, (
        "hộp việc YCMH bị co theo scope phiếu mua ⇒ nhân viên thu mua nhìn badge 0 mà màn đầy việc")


def test_notify_summary_khong_ro_cong_no_cho_nguoi_khong_co_ke_toan(client, auth_headers):
    """⭐ RÀNG BUỘC SỐ 2 — `dot_giao_qua_han` là số CÔNG NỢ, chỉ người có `ke_toan:read` mới thấy.

    Người chỉ có quyền thu mua nhận 0 (và vì FE cộng thẳng ba số, 0 nghĩa là không cộng vào badge
    của họ)."""
    buyer_headers = {"Authorization": f"Bearer {_buyer_token()}"}
    supplier = _supplier(client, auth_headers, name="NCC Badge Cong No")
    _dot_giao_qua_han(client, auth_headers, supplier["id"])

    assert _notify(client, auth_headers)["dot_giao_qua_han"] == 1, (
        "admin có `ke_toan:read` mà không thấy đợt quá hạn ⇒ test dưới đây rỗng")
    assert _notify(client, buyer_headers)["dot_giao_qua_han"] == 0, (
        "rò tình hình công nợ cho người chỉ có quyền thu mua")


def test_notify_summary_can_quyen_thu_mua_read(client):
    """Không có `thu_mua:read` thì không có badge — 403, đúng cổng của mọi đường đọc thu mua."""
    sales_headers = {"Authorization": f"Bearer {_sales_token()}"}
    _notify(client, sales_headers, expect=403)


def test_vai_trong_tron_khong_doc_duoc_yeu_cau_mua_hang(client, auth_headers):
    """CỬA HỞ đo được 10/08/2026: vai không cấp ô nào vẫn đọc được YCMH.

    Màn này cố ý mở cho 6 nhóm đề nghị vật tư (báo giá · kho · sản xuất · vật tư · kế toán · thu
    mua) nên KHÔNG gác riêng `thu_mua`. Nhưng "mở cho 6 nhóm" khác hẳn "mở cho mọi tài khoản đăng
    nhập" — đó là chỗ hở, và đây là test canh."""
    from app.db import SessionLocal
    from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
    from app.repositories.user_repo import UserRepository
    from app.security import create_access_token, hash_password

    db = SessionLocal()
    try:
        depts, roles, users = DepartmentRepository(db), RoleRepository(db), UserRepository(db)
        dept = depts.get_by_name("Sản xuất")
        role = roles.get_by_name_and_department("Vai Trong Tron YCMH", dept.id)
        if role is None:
            role = roles.create(name="Vai Trong Tron YCMH", department_id=dept.id)
        u = users.get_by_username("trong-tron-ycmh")
        if u is None:
            u = users.create(username="trong-tron-ycmh", name="Trong Tron",
                             password_hash=hash_password("x"))
        users.set_assignment(u, department_id=dept.id, role_id=role.id, is_active=True)
        db.commit()
        tok = create_access_token(str(u.id))
    finally:
        db.close()

    r = client.get("/api/department-purchase-requests?size=1",
                   headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403, f"vai trống trơn KHÔNG được đọc YCMH: {r.text}"

    # Người CÓ quyền vẫn đọc bình thường — hàng rào không được chặn nhầm.
    assert client.get(
        "/api/department-purchase-requests?size=1", headers=auth_headers
    ).status_code == 200


def test_ba_viec_sau_khi_nhan_hang_doi_o_rieng_khong_phai_o_duyet(client, auth_headers):
    """Sửa số nhận · Mở lại đơn · Đóng đơn đòi ô **Thao tác** (`thu_mua:update`).

    Ba nấc, ghi lại để đừng quay vòng:
      • trước 11/08/2026 — mượn cờ `can_approve`, câu báo lỗi ghi "chỉ người có quyền duyệt": SAI
        NGHĨA, đây là việc sửa đơn sau khi hàng về, chẳng liên quan duyệt chi tiền;
      • 11/08/2026 — tách ra ô riêng `manage_status`;
      • 12/08/2026 — GỘP về ô "Thao tác" sau khi chủ chốt test: *"quyền Sửa / đảo trạng thái đơn
        sau khi nhận hàng vô dụng, bỏ đi được không"*. Ba việc đó là việc thường ngày của chính
        người lập phiếu; tách ra chỉ thêm một ô phải nhớ tick.

    Vế GIỮ NGUYÊN: người chỉ có ô Xem thì không đảo được trạng thái, và câu báo lỗi KHÔNG được
    nói "quyền duyệt".
    """
    supplier = _supplier(client, auth_headers, name="NCC Trang Thai")
    pr = _create_purchase_request(client, auth_headers, supplier["id"])
    client.post(f"/api/purchase-requests/{pr['id']}/submit", headers=auth_headers)
    client.post(f"/api/purchase-requests/{pr['id']}/approve", headers=_h_duyet())
    client.post(f"/api/purchase-requests/{pr['id']}/receive", headers=auth_headers)

    # Người CHỈ CÓ Ô XEM ⇒ không lùi được trạng thái.
    db = SessionLocal()
    try:
        kd = DepartmentRepository(db).get_by_name("Kinh doanh")
        roles, users = RoleRepository(db), UserRepository(db)
        vai = roles.create(name="Thu mua khong doi trang thai", department_id=kd.id)
        roles.set_permission(role_id=vai.id, module_key="thu_mua", can_read=True,
                             scope=SCOPE_ALL)
        u = users.create(username="tm-khong-doi-tt", name="TM", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=kd.id, role_id=vai.id, is_active=True)
        db.commit()
        thieu_o = {"Authorization": f"Bearer {create_access_token(str(u.id))}"}
    finally:
        db.close()

    r = client.post(f"/api/purchase-requests/{pr['id']}/undo-received",
                    json={"reason": "dem lai"}, headers=thieu_o)
    assert r.status_code == 403, f"chỉ có ô Xem mà vẫn lùi được trạng thái: {r.status_code}"
    assert "duyệt" not in r.json()["detail"].lower(), (
        "câu báo lỗi vẫn nói 'quyền duyệt' — sai nghĩa, đây là ô sửa/đảo trạng thái đơn"
    )


# ══════════════════════════════ Thu mua & Kế toán, đợt 12/08/2026


def _ncc(client, headers, *, name, tax_code, expect=201):
    """Tạo NCC với đủ trường bắt buộc — chỉ TÊN và MST là thứ đang muốn thử."""
    r = client.post("/api/suppliers",
                    json={"name": name, "tax_code": tax_code, "phone": "0900000000",
                          "email": "x@example.com", "address": "1 Le Loi",
                          "contact_name": "A", "supplier_group": "paper",
                          "payment_terms": "Cong no 30 ngay", "items": []},
                    headers=headers)
    assert r.status_code == expect, r.text
    return r.json() if r.status_code < 400 else r


def test_ma_so_thue_khong_duoc_trung(client, auth_headers):
    """MST là ĐỊNH DANH PHÁP LÝ. Hai hồ sơ cùng MST = một nhà cung cấp bị nhập hai lần: công nợ
    chẻ đôi, đối chiếu hoá đơn ra hai kết quả, không ai biết phiếu chi nên gắn hồ sơ nào."""
    _ncc(client, auth_headers, name="NCC MST Goc", tax_code="0188888888")
    lai = _ncc(client, auth_headers, name="NCC Khac Ten", tax_code="0188888888", expect=409)
    assert "0188888888" in lai.json()["detail"]
    assert "NCC MST Goc" in lai.json()["detail"], "câu báo phải chỉ ĐÍCH DANH hồ sơ đang giữ mã"


def test_API_van_bat_buoc_khai_MST(client, auth_headers):
    """Đo được 12/08/2026: schema `SupplierIn` đã bắt buộc `tax_code` (min_length 1) TỪ TRƯỚC —
    không có đường nào tạo NCC mà bỏ trống mã số thuế.

    Ghi lại vì nó đổi nghĩa của luật chống trùng vừa thêm: luật đó KHÔNG thể chặn nhầm nhóm "hộ
    kinh doanh không có MST", đơn giản vì nhóm đó chưa bao giờ khai được. Nhánh "bỏ trống thì bỏ
    qua" trong `_chan_trung_mst` vẫn giữ — nó đỡ cho người gọi nội bộ và cho ngày ai đó nới schema.
    """
    r = client.post("/api/suppliers",
                    json={"name": "NCC Khong MST", "phone": "0900000000",
                          "email": "x@example.com", "address": "1 Le Loi",
                          "contact_name": "A", "supplier_group": "paper",
                          "payment_terms": "Cong no 30 ngay", "items": []},
                    headers=auth_headers)
    assert r.status_code == 422, f"bỏ trống MST mà vẫn tạo được: {r.status_code}"


def test_sua_NCC_giu_nguyen_mst_cua_chinh_no(client, auth_headers):
    """Sửa tên mà không đụng MST thì không được tự vướng luật trùng với CHÍNH MÌNH."""
    ncc = _ncc(client, auth_headers, name="NCC Sua Ten", tax_code="0177777777")
    sua = client.put(f"/api/suppliers/{ncc['id']}",
                     json={"name": "NCC Sua Ten (moi)", "tax_code": "0177777777",
                           "phone": "0900000000", "email": "x@example.com",
                           "address": "1 Le Loi", "contact_name": "A",
                           "supplier_group": "paper", "payment_terms": "Cong no 30 ngay",
                           "items": []},
                     headers=auth_headers)
    assert sua.status_code == 200, sua.text


def test_danh_sach_NCC_moi_nhat_len_dau(client, auth_headers):
    """Trước 12/08/2026 xếp theo TÊN — NCC vừa khai xong nằm tận trang sau, người khai phải đi
    tìm chính thứ mình vừa tạo."""
    # ⚠️ TÊN PHẢI NGƯỢC CHIỀU THỨ TỰ TẠO. Bản đầu đặt "Zzz" tạo trước / "Aaa" tạo sau — xếp theo
    # tên hay theo thời gian đều ra "Aaa" đứng đầu, nên đột biến "về lại xếp theo tên" KHÔNG CẮN.
    _ncc(client, auth_headers, name="Aaa Tao Truoc", tax_code="0111111111")
    _ncc(client, auth_headers, name="Zzz Tao Sau", tax_code="0122222222")
    ten = [x["name"] for x in client.get("/api/suppliers", headers=auth_headers).json()["items"]]
    assert ten.index("Zzz Tao Sau") < ten.index("Aaa Tao Truoc"), (
        f"vẫn đang xếp theo tên chứ không theo thời điểm tạo: {ten[:4]}"
    )


def test_o_Thao_tac_LA_DU_de_dao_trang_thai_don(client, auth_headers):
    """Vế THÀNH CÔNG của việc gộp quyền — trước đây KHÔNG ca nào chạy nó.

    Đột biến "bỏ hẳn kiểm quyền, luôn ném 403" vẫn xanh cả file: mọi ca đều chỉ kiểm chiều BỊ
    CHẶN. Không có vế này thì gộp `manage_status` → `update` mà lỡ gác nhầm sang một ô không ai
    có, cả bộ test vẫn im.
    """
    supplier = _supplier(client, auth_headers, name="NCC Thao Tac Du")
    pr = _create_purchase_request(client, auth_headers, supplier["id"])
    client.post(f"/api/purchase-requests/{pr['id']}/submit", headers=auth_headers)
    client.post(f"/api/purchase-requests/{pr['id']}/approve", headers=_h_duyet())
    # ⚠️ Endpoint là `mark-received`, KHÔNG phải `/receive` — gọi sai thì phiếu đứng ở "Đã mua"
    # và ca đo báo "Chỉ phiếu đã nhận hàng mới lùi được", tưởng lỗi quyền. Hai ca cũ ở file này
    # cũng gọi sai y hệt, nhưng chúng chỉ kiểm chiều BỊ CHẶN nên không lộ ra.
    dm = client.post(f"/api/purchase-requests/{pr['id']}/mark-purchased", headers=auth_headers)
    assert dm.status_code == 200, dm.text
    dn = client.post(f"/api/purchase-requests/{pr['id']}/mark-received",
                     json={"lines": []}, headers=auth_headers)
    assert dn.status_code == 200, dn.text

    db = SessionLocal()
    try:
        kd = DepartmentRepository(db).get_by_name("Kinh doanh")
        roles, users = RoleRepository(db), UserRepository(db)
        vai = roles.create(name="Thu mua co Thao tac", department_id=kd.id)
        # ĐÚNG ô "Thao tác", KHÔNG có ô duyệt, KHÔNG có ô riêng nào khác.
        roles.set_permission(role_id=vai.id, module_key="thu_mua", can_read=True,
                             can_create=True, can_update=True, scope=SCOPE_ALL)
        u = users.create(username="tm-co-thao-tac", name="TM", password_hash=hash_password("x"))
        users.set_assignment(u, department_id=kd.id, role_id=vai.id, is_active=True)
        db.commit()
        h = {"Authorization": f"Bearer {create_access_token(str(u.id))}"}
    finally:
        db.close()

    r = client.post(f"/api/purchase-requests/{pr['id']}/undo-received",
                    json={"reason": "dem lai"}, headers=h)
    assert r.status_code == 200, f"có ô Thao tác mà vẫn không lùi được: {r.text}"
