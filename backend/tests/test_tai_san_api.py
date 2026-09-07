"""HTTP contract + cổng quyền của module Tài sản. Dùng fixture `client` (app thật, SQLite RAM)."""


def _token(client, seed_credentials):
    r = client.post("/api/auth/login", json=seed_credentials)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_can_dang_nhap_moi_xem_duoc(client):
    assert client.get("/api/tai-san").status_code == 401


def test_ghi_tang_roi_doc_lai(client, seed_credentials):
    h = _token(client, seed_credentials)
    r = client.post("/api/tai-san", headers=h, json={
        "ten": "May in Komori 4 mau", "loai": "tscd", "so_thang": 120,
        "ngay_su_dung": "2026-03-10", "nguon_vao": "ghi_tang",
        "chi_phi": [
            {"dien_giai": "Gia mua", "so_tien": 3200000000},
            {"dien_giai": "Van chuyen", "so_tien": 40000000},
            {"dien_giai": "Lap dat chay thu", "so_tien": 60000000},
        ],
        "ghi_chu_hach_toan": "211 / 6274 - to In",
    })
    assert r.status_code == 201, r.text
    ts = r.json()
    assert ts["nguyen_gia"] == 3300000000
    assert ts["ghi_chu_hach_toan"] == "211 / 6274 - to In"
    assert ts["con_lai"] == 3300000000

    ds = client.get("/api/tai-san", headers=h).json()
    assert ds["total"] == 1
    assert ds["items"][0]["ma"] == ts["ma"]

    ct = client.get(f"/api/tai-san/{ts['id']}", headers=h).json()
    assert len(ct["chi_phi"]) == 3

    du_kien = client.get(f"/api/tai-san/{ts['id']}/du-kien", headers=h).json()
    assert du_kien[0]["muc_trich"] == 19516129


def test_loc_va_phan_trang_o_may_chu(client, seed_credentials):
    h = _token(client, seed_credentials)
    for i in range(3):
        client.post("/api/tai-san", headers=h, json={
            "ten": f"Tam cao su {i}", "loai": "ccdc", "so_luong": 12, "don_gia": 2400000,
            "so_thang": 24, "ngay_su_dung": "2026-07-01", "nguon_vao": "ghi_tang",
        })
    r = client.get("/api/tai-san?loai=ccdc&limit=2&offset=0", headers=h).json()
    assert r["total"] == 3
    assert len(r["items"]) == 2


def test_nap_dau_ky_qua_api(client, seed_credentials):
    h = _token(client, seed_credentials)
    r = client.post("/api/tai-san", headers=h, json={
        "ten": "May dao xen Polar", "loai": "tscd", "so_thang": 120,
        "ngay_su_dung": "2023-06-01", "nguon_vao": "dau_ky", "moc_tu_ngay": "2026-01-01",
        "chi_phi": [{"dien_giai": "Nguyen gia", "so_tien": 450000000}],
        "thang_da_trich_dau_ky": 31, "hao_mon_dau_ky": 116250000,
    })
    assert r.status_code == 201, r.text
    ts = r.json()
    assert ts["hao_mon_luy_ke"] == 116250000
    assert ts["con_lai"] == 333750000
    assert client.get(f"/api/tai-san/{ts['id']}/du-kien", headers=h).json()[0]["muc_trich"] == 3750000


def test_luong_ky_tinh_chot_mo(client, seed_credentials):
    h = _token(client, seed_credentials)
    client.post("/api/tai-san", headers=h, json={
        "ten": "May in Komori 4 mau", "loai": "tscd", "so_thang": 120,
        "ngay_su_dung": "2026-03-10", "nguon_vao": "ghi_tang",
        "chi_phi": [{"dien_giai": "Nguyen gia", "so_tien": 3300000000}],
    })
    bang = client.post("/api/tai-san/ky/2026/3/tinh", headers=h).json()
    assert bang["tong_muc_trich"] == 19516129
    assert bang["trang_thai"] == "mo"

    assert client.post("/api/tai-san/ky/2026/3/chot", headers=h).status_code == 200
    assert client.post("/api/tai-san/ky/2026/3/tinh", headers=h).status_code == 409
    assert client.get("/api/tai-san/ky/2026/3/bang", headers=h).json()["trang_thai"] == "da_chot"

    assert client.post("/api/tai-san/ky/2026/3/mo", headers=h).status_code == 200
    assert client.post("/api/tai-san/ky/2026/3/tinh", headers=h).status_code == 200


def test_bien_dong_qua_api(client, seed_credentials):
    h = _token(client, seed_credentials)
    ts = client.post("/api/tai-san", headers=h, json={
        "ten": "May dao xen Polar", "loai": "tscd", "so_thang": 120,
        "ngay_su_dung": "2026-01-01", "nguon_vao": "ghi_tang",
        "chi_phi": [{"dien_giai": "Nguyen gia", "so_tien": 450000000}],
    }).json()
    r = client.post(f"/api/tai-san/{ts['id']}/bien-dong", headers=h, json={
        "loai": "ghi_giam", "ngay": "2026-02-01", "ly_do": "Thanh ly", "gia_ban": 200000000,
    })
    assert r.status_code == 201, r.text
    ct = client.get(f"/api/tai-san/{ts['id']}", headers=h).json()
    assert ct["trang_thai"] == "da_giam"
    assert len(ct["bien_dong"]) == 1
    assert ct["chenh_lech_thanh_ly"] == -250000000


def test_route_ky_khong_bi_nuot_boi_route_id(client, seed_credentials):
    h = _token(client, seed_credentials)
    assert client.get("/api/tai-san/ky", headers=h).status_code == 200


def test_loai_bien_dong_la_khong_hop_le_thi_422(client, seed_credentials):
    h = _token(client, seed_credentials)
    ts = client.post("/api/tai-san", headers=h, json={
        "ten": "May in test", "loai": "tscd", "so_thang": 120,
        "ngay_su_dung": "2026-01-01", "nguon_vao": "ghi_tang",
        "chi_phi": [{"dien_giai": "Nguyen gia", "so_tien": 100000000}],
    }).json()
    r = client.post(f"/api/tai-san/{ts['id']}/bien-dong", headers=h, json={
        "loai": "khong_co_that", "ngay": "2026-02-01",
    })
    assert r.status_code == 422


def test_luong_kiem_ke_qua_api(client, seed_credentials):
    h = _token(client, seed_credentials)
    for ten in ("May A", "May B"):
        client.post("/api/tai-san", headers=h, json={
            "ten": ten, "loai": "tscd", "so_thang": 120,
            "ngay_su_dung": "2026-01-01", "nguon_vao": "ghi_tang",
            "chi_phi": [{"dien_giai": "NG", "so_tien": 100000000}],
        })
    r = client.post("/api/tai-san/kiem-ke", headers=h, json={"ngay": "2026-12-31"})
    assert r.status_code == 201, r.text
    dot = r.json()
    assert len(dot["dong"]) == 2
    assert dot["dong"][0]["ma"].startswith("TS-")

    d0, d1 = dot["dong"]
    client.put(f"/api/tai-san/kiem-ke/{dot['id']}/dong/{d0['id']}", headers=h,
               json={"ket_qua": "co", "tinh_trang": "Con tot"})
    client.put(f"/api/tai-san/kiem-ke/{dot['id']}/dong/{d1['id']}", headers=h,
               json={"ket_qua": "khong_thay"})
    client.post(f"/api/tai-san/kiem-ke/{dot['id']}/phat-hien", headers=h,
                json={"ten_phat_hien": "May dan keo chua vao so"})

    ket = client.post(f"/api/tai-san/kiem-ke/{dot['id']}/ket-thuc", headers=h).json()
    assert [x["ten"] for x in ket["thieu"]] == ["May B"]
    assert [x["ten"] for x in ket["thua"]] == ["May dan keo chua vao so"]
    # đợt đã kết thì khoá
    assert client.put(f"/api/tai-san/kiem-ke/{dot['id']}/dong/{d0['id']}", headers=h,
                      json={"ket_qua": "co"}).status_code == 409


def test_route_kiem_ke_khong_bi_nuot_boi_route_id(client, seed_credentials):
    h = _token(client, seed_credentials)
    assert client.get("/api/tai-san/kiem-ke", headers=h).status_code == 200
