"""Tests cho persistence Phiếu tính giá THEO THÀNH PHẦN (/api/phieu-tinh-gia).

SEED_DEMO=false → danh mục Giấy/Công đoạn rỗng, nên seed thẳng qua model (SessionLocal bám
cùng StaticPool connection app dùng) để có đầu vào cho engine ra số > 0.
"""
from __future__ import annotations

import pytest

from app.db import SessionLocal
from app.models.cong_doan import CongDoan
from app.models.vat_lieu_kho import GiayNguyen


@pytest.fixture
def token(client, seed_credentials) -> str:
    resp = client.post("/api/auth/login", json=seed_credentials)
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def auth_headers(token) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed_catalog() -> tuple[int, int]:
    """Seed 1 giấy (theo tờ) + 1 công đoạn cán (per_area_sides) → (giay_id, cong_doan_id)."""
    db = SessionLocal()
    try:
        giay = GiayNguyen(ma="G-TEST-1", ten="Couche 150 test", gsm=150,
                          kho_dai=1090, kho_rong=790, don_vi_gia="to", don_gia=2000)
        db.add(giay)
        cd = CongDoan(ma="CD-TEST-CAN", ten="Cán màng test", nhom="finishing",
                      che_do_tinh="theo_san_luong", pricing_basis="per_area_sides",
                      run_rate=0.05, setup_cost=50000, kieu_bu_hao="khong")
        db.add(cd)
        db.flush()
        ids = (giay.id, cd.id)
        db.commit()
        return ids
    finally:
        db.close()


def _component(giay_id: int, cong_doan_id: int | None = None) -> dict:
    tp = {
        "ten": "Tờ ruột", "giay_id": giay_id, "so_con": 2, "quy_cach_in": "mot_mat",
        "so_mau_a": 4, "che_ban_don_gia": 90000, "don_gia_cong_in": 120,
    }
    if cong_doan_id is not None:
        tp["thanh_phams"] = [
            {"ten": "Cán màng", "cong_doan_id": cong_doan_id, "dien_tich": 100, "so_mat": 1},
            {"ten": "Bế", "don_gia": 200},
        ]
    return tp


def test_create_draft_and_list(client, auth_headers):
    # Nháp trắng: không thành phần → zeros.
    resp = client.post("/api/phieu-tinh-gia", json={"ten_san_pham": "SP nháp"}, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["ma"].startswith("PTG-")
    assert body["tong_gia_von"] == 0
    assert body["ktv"]  # tên KTV = admin
    assert body["thanh_phans"] == []

    # Xuất hiện trong list nhẹ (không result / thành phần lồng).
    lst = client.get("/api/phieu-tinh-gia", headers=auth_headers)
    assert lst.status_code == 200
    data = lst.json()
    assert data["total"] >= 1
    row = next(it for it in data["items"] if it["id"] == body["id"])
    assert "ngay" in row and "result" not in row and row["so_thanh_phan"] == 0


def test_create_with_components_computes(client, auth_headers):
    giay_id, cd_id = _seed_catalog()
    resp = client.post("/api/phieu-tinh-gia", json={
        "ten_san_pham": "Tờ rơi", "so_luong": 3000,
        "thanh_phans": [_component(giay_id, cd_id)],
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["tong_gia_von"] > 0
    assert body["gia_von_don"] > 0
    assert body["result"] is not None and "groups" in body["result"]
    # 1 thành phần lồng + finishing.
    assert len(body["thanh_phans"]) == 1
    comp = body["thanh_phans"][0]
    assert comp["gia_von_tp"] > 0
    assert len(comp["thanh_phams"]) == 2
    # 2 nhóm (Nguyên vật liệu · Công đoạn) — không còn A/B/C/D; tổng = Σ nhóm.
    groups = body["result"]["groups"]
    assert [g["idx"] for g in groups] == ["nvl", "cong_doan"]
    assert body["result"]["grand_total"] == round(sum(g["subtotal"] for g in groups), 2)


def test_multi_component_sums(client, auth_headers):
    giay_id, cd_id = _seed_catalog()
    one = client.post("/api/phieu-tinh-gia", json={
        "so_luong": 2000, "thanh_phans": [_component(giay_id)],
    }, headers=auth_headers).json()
    two = client.post("/api/phieu-tinh-gia", json={
        "so_luong": 2000, "thanh_phans": [_component(giay_id), _component(giay_id)],
    }, headers=auth_headers).json()
    # 2 thành phần giống nhau → tổng gấp đôi 1 thành phần.
    assert two["tong_gia_von"] == pytest.approx(one["tong_gia_von"] * 2, rel=1e-6)


def test_get_by_id(client, auth_headers):
    resp = client.post("/api/phieu-tinh-gia", json={"ten_san_pham": "X"}, headers=auth_headers)
    pid = resp.json()["id"]
    got = client.get(f"/api/phieu-tinh-gia/{pid}", headers=auth_headers)
    assert got.status_code == 200
    assert got.json()["id"] == pid
    assert client.get("/api/phieu-tinh-gia/999999", headers=auth_headers).status_code == 404


def test_put_replaces_children_and_recomputes(client, auth_headers):
    giay_id, cd_id = _seed_catalog()
    pid = client.post("/api/phieu-tinh-gia", json={"ten_san_pham": "K"}, headers=auth_headers).json()["id"]
    # Nháp → PUT thêm thành phần → tính ra tiền.
    put = client.put(f"/api/phieu-tinh-gia/{pid}", json={
        "so_luong": 5000, "thanh_phans": [_component(giay_id, cd_id)],
    }, headers=auth_headers)
    assert put.status_code == 200, put.text
    body = put.json()
    assert body["tong_gia_von"] > 0
    assert len(body["thanh_phans"]) == 1

    # PUT lại với danh sách thành phần RỖNG → replace-all → về 0 + không còn con.
    put2 = client.put(f"/api/phieu-tinh-gia/{pid}", json={"thanh_phans": []}, headers=auth_headers)
    assert put2.status_code == 200
    assert put2.json()["tong_gia_von"] == 0
    assert put2.json()["thanh_phans"] == []


def test_search_filter(client, auth_headers):
    client.post("/api/phieu-tinh-gia", json={"ten_san_pham": "Danh thiếp cao cấp"}, headers=auth_headers)
    client.post("/api/phieu-tinh-gia", json={"ten_san_pham": "Tờ rơi A5"}, headers=auth_headers)

    q = client.get("/api/phieu-tinh-gia?q=Danh thiếp", headers=auth_headers).json()
    assert q["total"] >= 1
    assert all("danh thiếp" in (it["ten_san_pham"] or "").lower() for it in q["items"])


def test_delete(client, auth_headers):
    giay_id, cd_id = _seed_catalog()
    pid = client.post("/api/phieu-tinh-gia", json={
        "so_luong": 1000, "thanh_phans": [_component(giay_id, cd_id)],
    }, headers=auth_headers).json()["id"]
    dele = client.request("DELETE", f"/api/phieu-tinh-gia/{pid}", headers=auth_headers)
    assert dele.status_code == 200
    assert dele.json() == {"ok": True}
    assert client.get(f"/api/phieu-tinh-gia/{pid}", headers=auth_headers).status_code == 404


def _kd_headers(username: str, role_name: str = "NV Sales") -> dict[str, str]:
    """Header cho 1 user phòng Kinh doanh (tạo nếu chưa có)."""
    from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
    from app.repositories.user_repo import UserRepository
    from app.security import create_access_token, hash_password
    db = SessionLocal()
    try:
        users = UserRepository(db)
        u = users.get_by_username(username)
        if u is None:
            kd = DepartmentRepository(db).get_by_name("Kinh doanh")
            role = RoleRepository(db).get_by_name_and_department(role_name, kd.id)
            u = users.create(username=username, name=username, password_hash=hash_password("x"))
            users.set_assignment(u, department_id=kd.id, role_id=role.id, is_active=True)
        return {"Authorization": f"Bearer {create_access_token(str(u.id))}"}
    finally:
        db.close()


def test_phieu_tinh_gia_scope(client, auth_headers):
    """P8 §10: NV Sales scope 'Của tôi' chỉ thấy phiếu MÌNH lập; TP KD (phòng) thấy cả phòng; admin thấy hết."""
    h1 = _kd_headers("ptg_sale1")
    h2 = _kd_headers("ptg_sale2")
    htp = _kd_headers("ptg_tpkd", "Trưởng phòng KD")
    p1 = client.post("/api/phieu-tinh-gia", json={"ten_san_pham": "SP sale1", "so_luong": 100}, headers=h1)
    p2 = client.post("/api/phieu-tinh-gia", json={"ten_san_pham": "SP sale2", "so_luong": 100}, headers=h2)
    assert p1.status_code == 201 and p2.status_code == 201, (p1.text, p2.text)
    id1, id2 = p1.json()["id"], p2.json()["id"]

    ids1 = {x["id"] for x in client.get("/api/phieu-tinh-gia", headers=h1).json()["items"]}
    assert id1 in ids1 and id2 not in ids1              # sale1 chỉ thấy phiếu của mình
    idstp = {x["id"] for x in client.get("/api/phieu-tinh-gia", headers=htp).json()["items"]}
    assert id1 in idstp and id2 in idstp                # TP KD thấy cả phòng
    idsa = {x["id"] for x in client.get("/api/phieu-tinh-gia", headers=auth_headers).json()["items"]}
    assert id1 in idsa and id2 in idsa                  # admin (all) thấy hết
    # sale1 KHÔNG mở/sửa/xóa được phiếu của sale2 (ngoài phạm vi → 404).
    assert client.get(f"/api/phieu-tinh-gia/{id2}", headers=h1).status_code == 404
