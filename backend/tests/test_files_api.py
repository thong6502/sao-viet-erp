"""/api/files — cửa DUY NHẤT đọc file người dùng tải lên (thay mount /static công khai cũ).

Ba điều phải đúng, nếu sai là hở đúng cái lỗ mình vừa đi bịt:
  1. chưa đăng nhập → không đọc được gì;
  2. thư mục nhạy cảm (`hr/`) còn đòi quyền module, không phải cứ đăng nhập là xem;
  3. cookie file KHÔNG dùng thay Bearer được (nếu được thì nó thành đường leo quyền).
"""
from __future__ import annotations

from app.db import SessionLocal
from app.models.role import SCOPE_ALL
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import hash_password

_LIMITED_USERNAME = "chi-xem-ke-toan"
_LIMITED_PASSWORD = "matkhau123"


def _login(client, username="admin", password="admin123") -> dict[str, str]:
    """Đăng nhập: trả Bearer header, đồng thời TestClient giữ luôn cookie `file_access`."""
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _upload_avatar(client, headers, data: bytes = b"anh-dai-dien") -> str:
    response = client.post(
        "/api/users/me/avatar",
        files={"file": ("me.png", data, "image/png")},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["avatar_url"]


def _make_limited_user() -> None:
    """Người dùng chỉ có quyền đọc `ke_toan` — dùng để chứng minh gate theo tiền tố có tác dụng."""
    db = SessionLocal()
    try:
        department = DepartmentRepository(db).get_by_name("Kế toán")
        roles = RoleRepository(db)
        role = roles.create(name="Chỉ xem kế toán", department_id=department.id)
        roles.set_permission(
            role_id=role.id, module_key="ke_toan", can_read=True, scope=SCOPE_ALL
        )
        users = UserRepository(db)
        user = users.create(
            username=_LIMITED_USERNAME,
            name="Chỉ xem kế toán",
            password_hash=hash_password(_LIMITED_PASSWORD),
        )
        users.set_assignment(user, department_id=department.id, role_id=role.id, is_active=True)
    finally:
        db.close()


def test_chua_dang_nhap_thi_khong_doc_duoc_file(client):
    assert client.get("/api/files/avatars/bat-ky.png").status_code == 401


def test_dang_nhap_thi_doc_duoc_dung_bytes(client):
    headers = _login(client)
    url = _upload_avatar(client, headers, b"anh-dai-dien")

    got = client.get(url)
    assert got.status_code == 200, got.text
    assert got.content == b"anh-dai-dien"
    # LocalStorage không giữ content-type → router đoán theo đuôi file.
    assert got.headers["content-type"].startswith("image/png")
    assert "private" in got.headers["cache-control"]


def test_chan_duong_dan_vuot_ra_ngoai_kho_file(client):
    _login(client)
    # Mã hoá %2e%2e để httpx/Starlette không tự rút gọn trước khi tới guard.
    assert client.get("/api/files/hr/%2e%2e/%2e%2e/dev.db").status_code == 400
    # Dạng thô: dù client có tự rút gọn thì tuyệt đối không được ra 200.
    assert client.get("/api/files/hr/../../dev.db").status_code != 200


def test_thieu_quyen_module_thi_khong_xem_duoc_ho_so_nhan_su(client):
    _make_limited_user()
    _login(client, _LIMITED_USERNAME, _LIMITED_PASSWORD)
    # Chặn ở tầng quyền, TRƯỚC khi chạm storage → không tồn tại vẫn phải 403, không phải 404
    # (404 sẽ rò rỉ việc hồ sơ đó có tồn tại hay không).
    assert client.get("/api/files/hr/1/ho-so.jpg").status_code == 403

    # Cùng đường dẫn, người đủ quyền: không bị 403 — file không có nên 404.
    _login(client)
    assert client.get("/api/files/hr/1/ho-so.jpg").status_code == 404


def test_logout_thi_cookie_file_het_hieu_luc(client):
    headers = _login(client)
    url = _upload_avatar(client, headers)
    assert client.get(url).status_code == 200

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get(url).status_code == 401


def test_doi_mat_khau_giet_luon_cookie_file(client):
    """`tv` trong token file: đổi mật khẩu bump token_version → cookie cũ chết theo."""
    headers = _login(client)
    url = _upload_avatar(client, headers)
    assert client.get(url).status_code == 200

    changed = client.post(
        "/api/auth/change-password",
        json={"current_password": "admin123", "new_password": "MatKhauMoi123"},
        headers=headers,
    )
    assert changed.status_code == 204, changed.text
    assert client.get(url).status_code == 401


def test_cookie_file_khong_dung_duoc_thay_bearer(client):
    """Hai token cùng ký bằng jwt_secret; claim `typ` là thứ chặn leo quyền."""
    _login(client)
    file_token = client.cookies.get("file_access")
    assert file_token

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {file_token}"})
    assert response.status_code == 401


# --- header an toàn khi phục vụ tệp -------------------------------------------------------------
# Tệp người dùng tải lên phục vụ CÙNG origin với app. Không có hai header dưới đây thì một tệp
# `.html`/`.svg` chèn script, mở thẳng đường dẫn là script chạy với quyền của người đang đăng nhập.


def _dat_tep(key: str, data: bytes) -> str:
    from app.storage import get_storage, url_from_key

    get_storage().save(key, data)
    return url_from_key(key)


def test_moi_tep_deu_mang_nosniff(client):
    _login(client)
    url = _dat_tep("avatars/hdr/0a1b2c3d_anh.png", b"png")
    assert client.get(url).headers["x-content-type-options"] == "nosniff"


def test_anh_va_pdf_mo_ngay_trong_trinh_duyet(client):
    _login(client)
    for ten in ("0a1b2c3d_anh.png", "0a1b2c3d_maket.pdf", "0a1b2c3d_anh.JPG"):
        got = client.get(_dat_tep(f"avatars/hdr/{ten}", b"x"))
        assert got.headers["content-disposition"].startswith("inline"), ten


def test_tep_co_the_chua_script_bi_ep_tai_ve(client):
    _login(client)
    for ten in ("0a1b2c3d_trang.html", "0a1b2c3d_logo.svg", "0a1b2c3d_file.ai"):
        got = client.get(_dat_tep(f"avatars/hdr/{ten}", b"<script>alert(1)</script>"))
        assert got.status_code == 200
        assert got.headers["content-disposition"].startswith("attachment"), ten


def test_ten_tai_ve_bo_ma_ngau_nhien_va_giu_dau_tieng_viet(client):
    _login(client)
    got = client.get(_dat_tep("avatars/hdr/0a1b2c3d_Maket hộp bánh.ai", b"x"))
    cd = got.headers["content-disposition"]
    # RFC 5987: tên có dấu đi qua `filename*`, mã hoá UTF-8; tiền tố token lúc lưu không lọt ra.
    assert "filename*=UTF-8''Maket%20h%E1%BB%99p%20b%C3%A1nh.ai" in cd
    assert "0a1b2c3d" not in cd
