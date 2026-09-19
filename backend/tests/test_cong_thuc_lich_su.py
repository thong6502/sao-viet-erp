"""Lịch sử công thức lượng (mục 3+7 "Bảng định mức") — vòng qua API thật.

Kiểm ở TẦNG ROUTER (không tầng service như `test_nhat_ky_danh_muc.py`) vì phần cần chứng minh
đúng là `catalog_base._rows()` gắn `<truong>_truoc`/`_sua_luc` vào response và route
`GET /{id}/lich-su-cong-thuc` — cả hai đều là code trong `routers/catalog_base.py`, không phải
`services/nhat_ky_danh_muc.py`.

Chạy trên GIẤY (`cong_thuc_luong`) — danh mục DUY NHẤT còn bật `cong_thuc_truong`. Công đoạn thôi
bật từ 18/09/2026 cùng lúc gỡ `cong_thuc_san_luong` (mg `0324`).
"""
from __future__ import annotations

URL = "/api/vat-lieu-kho/giay"
CT_1 = "dinh_luong * dai_nguyen * rong_nguyen * to_nguyen"
CT_2 = "dinh_luong * dai_nguyen * rong_nguyen * to_nguyen * 2"
CT_3 = "dinh_luong * dai_nguyen * rong_nguyen * to_nguyen * 3"


def _headers(client) -> dict[str, str]:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _tao_giay(client, headers, **kw) -> dict:
    cl = client.post("/api/vat-lieu-kho/chung-loai-giay", json=dict(ma="CL-LS1", ten="Couché"),
                     headers=headers)
    assert cl.status_code == 201, cl.text
    payload = dict(ma="GI-LS1", ten="Giấy thử lịch sử", gsm=250, don_vi_gia="kg", don_gia=28000,
                   chung_loai_giay_id=cl.json()["id"])
    payload.update(kw)
    r = client.post(URL, json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_moi_tao_chua_co_lan_truoc(client, seed_credentials):
    headers = _headers(client)
    g = _tao_giay(client, headers, cong_thuc_luong=CT_1)

    assert g["cong_thuc_luong_truoc"] is None
    assert g["cong_thuc_luong_sua_luc"] is None


def test_sua_cong_thuc_thi_lan_sau_thay_gia_tri_cu(client, seed_credentials):
    """⭐ Chủ chốt: sửa công thức xong, GET lại phải thấy 'Lần trước' = giá trị NGAY TRƯỚC lần đó."""
    headers = _headers(client)
    g = _tao_giay(client, headers, cong_thuc_luong=CT_1)
    g_id = g["id"]

    put_1 = dict(g)
    put_1["cong_thuc_luong"] = CT_2
    r = client.put(f"{URL}/{g_id}", json=put_1, headers=headers)
    assert r.status_code == 200, r.text
    sau_lan_1 = r.json()
    assert sau_lan_1["cong_thuc_luong"] == CT_2
    assert sau_lan_1["cong_thuc_luong_truoc"] == CT_1
    assert sau_lan_1["cong_thuc_luong_sua_luc"] is not None

    # GET chi tiết cũng phải thấy y hệt — không chỉ mỗi response của PUT.
    r = client.get(f"{URL}/{g_id}", headers=headers)
    assert r.json()["cong_thuc_luong_truoc"] == CT_1

    # Sửa lần 2: "lần trước" phải nhảy sang giá trị của lần 1, không phải lần khởi tạo.
    put_2 = dict(sau_lan_1)
    put_2["cong_thuc_luong"] = CT_3
    r = client.put(f"{URL}/{g_id}", json=put_2, headers=headers)
    assert r.json()["cong_thuc_luong_truoc"] == CT_2


def test_luu_ma_khong_doi_cong_thuc_thi_khong_de_lan_moi(client, seed_credentials):
    """Sửa trường KHÁC (giữ nguyên công thức) không được đẻ thêm mốc lịch sử công thức."""
    headers = _headers(client)
    g = _tao_giay(client, headers, cong_thuc_luong=CT_1)
    g_id = g["id"]

    put_1 = dict(g)
    put_1["ghi_chu"] = "đổi ghi chú, không đụng công thức"
    r = client.put(f"{URL}/{g_id}", json=put_1, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["cong_thuc_luong_truoc"] is None

    r = client.get(f"{URL}/{g_id}/lich-su-cong-thuc", headers=headers)
    assert r.json() == []


def test_xem_them_lich_su_liet_ke_du_moi_nhat_truoc(client, seed_credentials):
    headers = _headers(client)
    g = _tao_giay(client, headers, cong_thuc_luong=CT_1)
    g_id = g["id"]

    put_1 = dict(g)
    put_1["cong_thuc_luong"] = CT_2
    r1 = client.put(f"{URL}/{g_id}", json=put_1, headers=headers).json()

    put_2 = dict(r1)
    put_2["cong_thuc_luong"] = CT_3
    client.put(f"{URL}/{g_id}", json=put_2, headers=headers)

    r = client.get(f"{URL}/{g_id}/lich-su-cong-thuc", headers=headers)
    assert r.status_code == 200
    su = r.json()
    assert len(su) == 2
    # Mới nhất trước: lần đổi "2 → 3" phải đứng đầu.
    assert su[0]["gia_tri_cu"] == CT_2 and su[0]["gia_tri_moi"] == CT_3
    assert su[1]["gia_tri_cu"] == CT_1 and su[1]["gia_tri_moi"] == CT_2


def test_lich_su_cua_id_khong_ton_tai_bao_404(client, seed_credentials):
    headers = _headers(client)
    r = client.get(f"{URL}/999999/lich-su-cong-thuc", headers=headers)
    assert r.status_code == 404


def test_cong_doan_khong_con_lich_su_cong_thuc(client, seed_credentials):
    """Công đoạn gỡ ô công thức sản lượng ra (mg `0324`) ⇒ route lịch sử của nó cũng không còn."""
    headers = _headers(client)
    r = client.get("/api/cong-doan/1/lich-su-cong-thuc", headers=headers)
    assert r.status_code in (404, 405)
