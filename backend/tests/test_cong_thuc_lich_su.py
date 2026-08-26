"""Lịch sử công thức lượng/sản lượng (mục 3+7 "Bảng định mức") — vòng qua API thật.

Kiểm ở TẦNG ROUTER (không tầng service như `test_nhat_ky_danh_muc.py`) vì phần cần chứng minh
đúng là `catalog_base._rows()` gắn `<truong>_truoc`/`_sua_luc` vào response và route
`GET /{id}/lich-su-cong-thuc` — cả hai đều là code trong `routers/catalog_base.py`, không phải
`services/nhat_ky_danh_muc.py`.
"""
from __future__ import annotations


def _headers(client) -> dict[str, str]:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _tao_cong_doan(client, headers, **kw) -> dict:
    payload = dict(ma="IN-01", ten="In offset", nhom="print",
                   che_do_tinh="theo_san_luong", pricing_basis="per_finished_qty")
    payload.update(kw)
    r = client.post("/api/cong-doan", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_moi_tao_chua_co_lan_truoc(client, seed_credentials):
    headers = _headers(client)
    cd = _tao_cong_doan(client, headers, cong_thuc_san_luong="so_kem * 2")

    assert cd["cong_thuc_san_luong_truoc"] is None
    assert cd["cong_thuc_san_luong_sua_luc"] is None


def test_sua_cong_thuc_thi_lan_sau_thay_gia_tri_cu(client, seed_credentials):
    """⭐ Chủ chốt: sửa công thức xong, GET lại phải thấy 'Lần trước' = giá trị NGAY TRƯỚC lần đó."""
    headers = _headers(client)
    cd = _tao_cong_doan(client, headers, cong_thuc_san_luong="so_kem * 2")
    cd_id = cd["id"]

    put_1 = dict(cd)
    put_1["cong_thuc_san_luong"] = "so_kem * 3"
    r = client.put(f"/api/cong-doan/{cd_id}", json=put_1, headers=headers)
    assert r.status_code == 200, r.text
    sau_lan_1 = r.json()
    assert sau_lan_1["cong_thuc_san_luong"] == "so_kem * 3"
    assert sau_lan_1["cong_thuc_san_luong_truoc"] == "so_kem * 2"
    assert sau_lan_1["cong_thuc_san_luong_sua_luc"] is not None

    # GET danh sách cũng phải thấy y hệt — không chỉ mỗi response của PUT.
    r = client.get(f"/api/cong-doan/{cd_id}", headers=headers)
    assert r.json()["cong_thuc_san_luong_truoc"] == "so_kem * 2"

    # Sửa lần 2: "lần trước" phải nhảy sang giá trị của lần 1, không phải lần khởi tạo.
    put_2 = dict(sau_lan_1)
    put_2["cong_thuc_san_luong"] = "so_kem * 4"
    r = client.put(f"/api/cong-doan/{cd_id}", json=put_2, headers=headers)
    assert r.json()["cong_thuc_san_luong_truoc"] == "so_kem * 3"


def test_luu_ma_khong_doi_cong_thuc_thi_khong_de_lan_moi(client, seed_credentials):
    """Sửa trường KHÁC (giữ nguyên công thức) không được đẻ thêm mốc lịch sử công thức."""
    headers = _headers(client)
    cd = _tao_cong_doan(client, headers, cong_thuc_san_luong="so_kem * 2")
    cd_id = cd["id"]

    put_1 = dict(cd)
    put_1["ghi_chu"] = "đổi ghi chú, không đụng công thức"
    r = client.put(f"/api/cong-doan/{cd_id}", json=put_1, headers=headers)
    assert r.json()["cong_thuc_san_luong_truoc"] is None

    r = client.get(f"/api/cong-doan/{cd_id}/lich-su-cong-thuc", headers=headers)
    assert r.json() == []


def test_xem_them_lich_su_liet_ke_du_moi_nhat_truoc(client, seed_credentials):
    headers = _headers(client)
    cd = _tao_cong_doan(client, headers, cong_thuc_san_luong="so_kem * 2")
    cd_id = cd["id"]

    put_1 = dict(cd)
    put_1["cong_thuc_san_luong"] = "so_kem * 3"
    r1 = client.put(f"/api/cong-doan/{cd_id}", json=put_1, headers=headers).json()

    put_2 = dict(r1)
    put_2["cong_thuc_san_luong"] = "so_kem * 4"
    client.put(f"/api/cong-doan/{cd_id}", json=put_2, headers=headers)

    r = client.get(f"/api/cong-doan/{cd_id}/lich-su-cong-thuc", headers=headers)
    assert r.status_code == 200
    su = r.json()
    assert len(su) == 2
    # Mới nhất trước: lần đổi "3 → 4" phải đứng đầu.
    assert su[0]["gia_tri_cu"] == "so_kem * 3" and su[0]["gia_tri_moi"] == "so_kem * 4"
    assert su[1]["gia_tri_cu"] == "so_kem * 2" and su[1]["gia_tri_moi"] == "so_kem * 3"


def test_lich_su_cua_id_khong_ton_tai_bao_404(client, seed_credentials):
    headers = _headers(client)
    r = client.get("/api/cong-doan/999999/lich-su-cong-thuc", headers=headers)
    assert r.status_code == 404
