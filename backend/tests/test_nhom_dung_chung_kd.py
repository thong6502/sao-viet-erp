"""Nhóm DÙNG CHUNG (khối Kinh doanh) — hai người ở phạm vi "Của tôi" dùng chung dữ liệu.

Phạm vi có ba nấc: Của tôi · Cả phòng · Tất cả. Nhu cầu ở giữa nấc 1 và nấc 2: anh A và anh B
làm chung nên phải thấy + sửa được phiếu của nhau, mà KHÔNG kéo cả phòng vào. Nhóm dùng chung
mở rộng đúng nghĩa "Của tôi" cho bốn màn `tinh_gia_thanh` · `bao_gia` · `don_hang_ban` ·
`khach_hang`, và CHỈ bốn màn đó — Lương/Hồ sơ/Chấm công vẫn là "chỉ mình tôi".

Nhóm MỞ RỘNG DỮ LIỆU, KHÔNG nâng quyền: ô quyền vẫn tính theo vai người đang thao tác.
"""
from __future__ import annotations

import pytest

from app.models.nhom_dung_chung import NhomDungChung, NhomDungChungThanhVien
from app.repositories.org_scope import nhom_dung_chung_user_ids
from tests.conftest import phien_da_seed


@pytest.fixture
def db():
    yield from phien_da_seed()


def test_hai_bang_ton_tai_va_ghi_duoc(db):
    nhom = NhomDungChung(ten="Cặp KD 1", created_by=None)
    db.add(nhom)
    db.flush()
    db.add(NhomDungChungThanhVien(nhom_id=nhom.id, user_id=1, added_by=None))
    db.add(NhomDungChungThanhVien(nhom_id=nhom.id, user_id=2, added_by=None))
    db.flush()
    assert db.query(NhomDungChungThanhVien).filter_by(nhom_id=nhom.id).count() == 2


def test_khong_thuoc_nhom_thi_chi_chinh_minh(db):
    assert nhom_dung_chung_user_ids(db, 7) == {7}


def test_cung_nhom_thi_thay_nhau(db):
    nhom = NhomDungChung(ten="Cặp KD 2", created_by=None)
    db.add(nhom)
    db.flush()
    db.add(NhomDungChungThanhVien(nhom_id=nhom.id, user_id=10, added_by=None))
    db.add(NhomDungChungThanhVien(nhom_id=nhom.id, user_id=11, added_by=None))
    db.flush()
    assert nhom_dung_chung_user_ids(db, 10) == {10, 11}
    assert nhom_dung_chung_user_ids(db, 11) == {10, 11}


def test_nhieu_nhom_thi_lay_hop(db):
    a = NhomDungChung(ten="Cặp A", created_by=None)
    b = NhomDungChung(ten="Cặp B", created_by=None)
    db.add_all([a, b])
    db.flush()
    db.add_all([
        NhomDungChungThanhVien(nhom_id=a.id, user_id=20, added_by=None),
        NhomDungChungThanhVien(nhom_id=a.id, user_id=21, added_by=None),
        NhomDungChungThanhVien(nhom_id=b.id, user_id=20, added_by=None),
        NhomDungChungThanhVien(nhom_id=b.id, user_id=22, added_by=None),
    ])
    db.flush()
    assert nhom_dung_chung_user_ids(db, 20) == {20, 21, 22}
    assert nhom_dung_chung_user_ids(db, 21) == {20, 21}


# ============================ Đầu-cuối qua API ============================
# Hai người CÙNG phòng, vai CÙNG phạm vi "Của tôi". Chưa gộp nhóm thì không thấy của nhau;
# gộp rồi thì thấy + sửa được. Người thứ ba cùng phòng nhưng khác nhóm vẫn không thấy gì.

def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _sale_own(username: str, **perm) -> tuple[int, str]:
    """Tạo user phòng Kinh doanh, vai riêng phạm vi "Của tôi". Trả (user_id, token)."""
    from app.db import SessionLocal
    from app.models.role import SCOPE_OWN
    from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
    from app.repositories.user_repo import UserRepository
    from app.security import create_access_token, hash_password

    s = SessionLocal()
    try:
        users, depts, roles = UserRepository(s), DepartmentRepository(s), RoleRepository(s)
        kd = depts.get_by_name("Kinh doanh")
        role = roles.get_by_name_and_department(f"role-{username}", kd.id)
        if role is None:
            role = roles.create(name=f"role-{username}", department_id=kd.id)
        for khoa in ("tinh_gia_thanh", "bao_gia", "don_hang_ban", "khach_hang"):
            roles.set_permission(role_id=role.id, module_key=khoa, scope=SCOPE_OWN, **perm)
        u = users.get_by_username(username)
        if u is None:
            u = users.create(username=username, name=username,
                             password_hash=hash_password("x"))
        users.set_assignment(u, department_id=kd.id, role_id=role.id, is_active=True)
        return u.id, create_access_token(str(u.id))
    finally:
        s.close()


def _gop_nhom(ten: str, user_ids: list[int]) -> None:
    from app.db import SessionLocal
    s = SessionLocal()
    try:
        nhom = NhomDungChung(ten=ten, created_by=None)
        s.add(nhom)
        s.flush()
        for uid in user_ids:
            s.add(NhomDungChungThanhVien(nhom_id=nhom.id, user_id=uid, added_by=None))
        s.commit()
    finally:
        s.close()


_QUYEN = dict(can_read=True, can_create=True, can_update=True, can_view_cost=True)


def test_chua_gop_nhom_thi_khong_thay_phieu_cua_nhau(client):
    _, tok_a = _sale_own("ndc_a", **_QUYEN)
    _, tok_b = _sale_own("ndc_b", **_QUYEN)
    p = client.post("/api/phieu-tinh-gia", headers=_h(tok_a),
                    json={"ten_san_pham": "SP của A", "so_luong": 100})
    assert p.status_code == 201, p.text
    pid = p.json()["id"]
    assert client.get(f"/api/phieu-tinh-gia/{pid}", headers=_h(tok_b)).status_code == 404


def test_cung_nhom_thi_thay_va_sua_duoc_phieu_cua_nhau(client):
    uid_a, tok_a = _sale_own("ndc_a2", **_QUYEN)
    uid_b, tok_b = _sale_own("ndc_b2", **_QUYEN)
    _, tok_c = _sale_own("ndc_c2", **_QUYEN)
    p = client.post("/api/phieu-tinh-gia", headers=_h(tok_a),
                    json={"ten_san_pham": "SP của A", "so_luong": 100})
    assert p.status_code == 201, p.text
    pid = p.json()["id"]

    _gop_nhom("Cặp A-B", [uid_a, uid_b])

    # B mở được, sửa được
    assert client.get(f"/api/phieu-tinh-gia/{pid}", headers=_h(tok_b)).status_code == 200
    r = client.put(f"/api/phieu-tinh-gia/{pid}", headers=_h(tok_b),
                   json={"ten_san_pham": "SP của A (B sửa)"})
    assert r.status_code == 200, r.text
    # Người lập KHÔNG đổi — nhóm chỉ mở rộng dữ liệu, không sang tên
    assert r.json()["ktv"] == "ndc_a2"
    # Phiếu của A cũng hiện trong DANH SÁCH của B
    ids = {x["id"] for x in client.get("/api/phieu-tinh-gia", headers=_h(tok_b)).json()["items"]}
    assert pid in ids
    # C cùng phòng nhưng khác nhóm: vẫn không thấy
    assert client.get(f"/api/phieu-tinh-gia/{pid}", headers=_h(tok_c)).status_code == 404


def test_cung_nhom_thi_thay_khach_hang_cua_nhau(client):
    uid_a, tok_a = _sale_own("ndc_a3", **_QUYEN)
    uid_b, tok_b = _sale_own("ndc_b3", **_QUYEN)
    r = client.post("/api/customers", headers=_h(tok_a),
                    json={"name": "Công ty Nhóm Chung", "customer_type": "cong_ty"})
    assert r.status_code in (200, 201), r.text
    cid = r.json().get("id") or r.json().get("customer", {}).get("id")

    assert client.get(f"/api/customers/{cid}", headers=_h(tok_b)).status_code == 404
    _gop_nhom("Cặp A-B khách", [uid_a, uid_b])
    assert client.get(f"/api/customers/{cid}", headers=_h(tok_b)).status_code == 200


# ============================ API quản lý nhóm ============================
# Gộp nhóm = cho người này thấy dữ liệu của người kia ⇒ cùng loại với CẤP QUYỀN, nên gác bằng
# ô đã có `phong_ban:manage_permissions`, không đẻ ô mới.

def _user_voi_quyen(username: str, module_key: str, **perm) -> str:
    from app.db import SessionLocal
    from app.models.role import SCOPE_ALL
    from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
    from app.repositories.user_repo import UserRepository
    from app.security import create_access_token, hash_password

    s = SessionLocal()
    try:
        users, depts, roles = UserRepository(s), DepartmentRepository(s), RoleRepository(s)
        kd = depts.get_by_name("Kinh doanh")
        role = roles.get_by_name_and_department(f"role-{username}", kd.id)
        if role is None:
            role = roles.create(name=f"role-{username}", department_id=kd.id)
        roles.set_permission(role_id=role.id, module_key=module_key, scope=SCOPE_ALL, **perm)
        u = users.get_by_username(username)
        if u is None:
            u = users.create(username=username, name=username,
                             password_hash=hash_password("x"))
        users.set_assignment(u, department_id=kd.id, role_id=role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        s.close()


def test_thieu_quyen_khong_tao_duoc_nhom(client):
    token = _user_voi_quyen("ndc_thuong", "tinh_gia_thanh", can_read=True)
    r = client.post("/api/nhom-dung-chung", headers=_h(token),
                    json={"ten": "Cặp lén", "user_ids": []})
    assert r.status_code == 403


def test_co_quyen_thi_tao_sua_xoa_duoc_nhom(client):
    uid_a, _ = _sale_own("ndc_api_a", **_QUYEN)
    uid_b, _ = _sale_own("ndc_api_b", **_QUYEN)
    token = _user_voi_quyen("ndc_qtri", "phong_ban",
                            can_read=True, can_manage_permissions=True)

    r = client.post("/api/nhom-dung-chung", headers=_h(token),
                    json={"ten": "Cặp KD 9", "user_ids": [uid_a, uid_b]})
    assert r.status_code == 201, r.text
    nhom_id = r.json()["id"]
    assert {t["user_id"] for t in r.json()["thanh_viens"]} == {uid_a, uid_b}

    ds = client.get("/api/nhom-dung-chung", headers=_h(token))
    assert ds.status_code == 200
    assert any(n["id"] == nhom_id for n in ds.json())

    r = client.patch(f"/api/nhom-dung-chung/{nhom_id}", headers=_h(token),
                     json={"ten": "Cặp KD 9 (đổi tên)", "user_ids": [uid_a]})
    assert r.status_code == 200, r.text
    assert r.json()["ten"] == "Cặp KD 9 (đổi tên)"
    assert [t["user_id"] for t in r.json()["thanh_viens"]] == [uid_a]

    assert client.delete(f"/api/nhom-dung-chung/{nhom_id}", headers=_h(token)).status_code == 200
    assert all(n["id"] != nhom_id for n in client.get("/api/nhom-dung-chung",
                                                      headers=_h(token)).json())


def test_ten_nhom_trung_bi_chan(client):
    token = _user_voi_quyen("ndc_qtri2", "phong_ban",
                            can_read=True, can_manage_permissions=True)
    assert client.post("/api/nhom-dung-chung", headers=_h(token),
                       json={"ten": "Cặp trùng", "user_ids": []}).status_code == 201
    r = client.post("/api/nhom-dung-chung", headers=_h(token),
                    json={"ten": "Cặp trùng", "user_ids": []})
    assert r.status_code == 409


def test_go_khoi_nhom_thi_het_thay_du_lieu(client):
    uid_a, tok_a = _sale_own("ndc_go_a", **_QUYEN)
    uid_b, tok_b = _sale_own("ndc_go_b", **_QUYEN)
    token = _user_voi_quyen("ndc_qtri3", "phong_ban",
                            can_read=True, can_manage_permissions=True)
    pid = client.post("/api/phieu-tinh-gia", headers=_h(tok_a),
                      json={"ten_san_pham": "SP của A", "so_luong": 10}).json()["id"]
    nhom_id = client.post("/api/nhom-dung-chung", headers=_h(token),
                          json={"ten": "Cặp gỡ", "user_ids": [uid_a, uid_b]}).json()["id"]
    assert client.get(f"/api/phieu-tinh-gia/{pid}", headers=_h(tok_b)).status_code == 200

    client.patch(f"/api/nhom-dung-chung/{nhom_id}", headers=_h(token),
                 json={"user_ids": [uid_a]})
    assert client.get(f"/api/phieu-tinh-gia/{pid}", headers=_h(tok_b)).status_code == 404
