"""Nhãn công đoạn (`/api/cong-doan-tags`) — bản sao luật của nhãn khách hàng, gắn cho một BƯỚC.

Bước trỏ bằng cặp (buoc_loai, buoc_id) không FK, nên test dùng buoc_id bất kỳ (không cần dựng bước thật).
"""
from __future__ import annotations

ADMIN = {"username": "admin", "password": "admin123"}


def _token(client) -> str:
    return client.post("/api/auth/login", json=ADMIN).json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_gan_nhan_dedup_va_vao_kho(client):
    token = _token(client)
    base = "/api/cong-doan-tags/lsx/101"

    r = client.post(base, json={"label": "Thuê ngoài"}, headers=_h(token))
    assert r.status_code == 201
    tag_id = r.json()["id"]

    # Gán trùng khác hoa-thường → trả nhãn cũ, không đúp.
    r = client.post(base, json={"label": "thuê ngoài"}, headers=_h(token))
    assert r.json()["id"] == tag_id

    items = client.get(base, headers=_h(token)).json()["items"]
    assert [t["label"] for t in items] == ["Thuê ngoài"]

    # Nhãn gõ tay tại chỗ tự VÀO KHO.
    kho = {r["label"] for r in client.get("/api/cong-doan-tags/kho", headers=_h(token)).json()["items"]}
    assert "Thuê ngoài" in kho

    # Nhãn rỗng → 400.
    assert client.post(base, json={"label": "   "}, headers=_h(token)).status_code == 422 \
        or client.post(base, json={"label": " "}, headers=_h(token)).status_code == 400


def test_go_nhan_khoi_buoc(client):
    token = _token(client)
    base = "/api/cong-doan-tags/bai_ghep/7"
    tag_id = client.post(base, json={"label": "Ưu tiên"}, headers=_h(token)).json()["id"]
    assert client.delete(f"{base}/{tag_id}", headers=_h(token)).status_code == 204
    assert client.get(base, headers=_h(token)).json()["items"] == []


def test_kho_them_dedup_va_xoa(client):
    token = _token(client)
    r = client.post("/api/cong-doan-tags/kho", json={"label": "Cán màng"}, headers=_h(token))
    assert r.status_code == 201
    moi_id = r.json()["id"]
    # Thêm lại khác hoa-thường → trả dòng cũ, không đúp.
    assert client.post("/api/cong-doan-tags/kho", json={"label": "cán màng"},
                       headers=_h(token)).json()["id"] == moi_id

    assert client.delete(f"/api/cong-doan-tags/kho/{moi_id}", headers=_h(token)).status_code == 200
    con = {r["label"] for r in client.get("/api/cong-doan-tags/kho", headers=_h(token)).json()["items"]}
    assert "Cán màng" not in con


def test_xoa_nhan_kho_go_luon_khoi_buoc_dang_mang(client):
    token = _token(client)
    base = "/api/cong-doan-tags/lsx/202"
    client.post(base, json={"label": "Bế ngoài"}, headers=_h(token))
    kho = client.get("/api/cong-doan-tags/kho", headers=_h(token)).json()["items"]
    dong = next(r for r in kho if r["label"] == "Bế ngoài")
    assert dong["so_buoc"] == 1

    r = client.delete(f"/api/cong-doan-tags/kho/{dong['id']}", headers=_h(token))
    assert r.status_code == 200 and r.json()["so_buoc_da_go"] == 1
    assert client.get(base, headers=_h(token)).json()["items"] == []


def test_loai_buoc_sai_bi_chan(client):
    token = _token(client)
    r = client.post("/api/cong-doan-tags/khong_ton_tai/1", json={"label": "X"}, headers=_h(token))
    assert r.status_code == 400
