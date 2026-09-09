"""HTTP contract + cổng quyền của module Tài sản. Dùng fixture `client` (app thật, SQLite RAM).

Hao mòn lũy kế trên API tính tới hết tháng TRƯỚC tháng hiện tại, nên test nào đụng tới nó phải
tính kỳ vọng bằng chính engine với `thang_da_tinh()` — ghi số cứng là qua tháng sau test đỏ.
"""
import re

from app.services.tai_san.khau_hao import Moc, luy_ke_den
from app.services.tai_san.service import thang_da_tinh


def _token(client, seed_credentials):
    r = client.post("/api/auth/login", json=seed_credentials)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _komori(client, h):
    r = client.post("/api/tai-san", headers=h, json={
        "ten": "May in Komori 4 mau", "loai": "tscd", "so_thang": 120,
        "ngay_su_dung": "2026-03-10", "nguon_vao": "ghi_tang",
        "chi_phi": [{"dien_giai": "Nguyen gia", "so_tien": 3300000000}],
    })
    assert r.status_code == 201, r.text
    return r.json()


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
        "ghi_chu": "211 / 6274 - to In",
    })
    assert r.status_code == 201, r.text
    ts = r.json()
    assert ts["nguyen_gia"] == 3300000000
    assert ts["ghi_chu"] == "211 / 6274 - to In"
    assert ts["con_lai"] == ts["nguyen_gia"] - ts["hao_mon_luy_ke"]
    assert re.fullmatch(r"\d{4}-\d{2}", ts["luy_ke_den"])
    nam, thang = thang_da_tinh()
    assert ts["luy_ke_den"] == f"{nam:04d}-{thang:02d}"

    ds = client.get("/api/tai-san", headers=h).json()
    assert ds["total"] == 1
    assert ds["items"][0]["ma"] == ts["ma"]

    ct = client.get(f"/api/tai-san/{ts['id']}", headers=h).json()
    assert len(ct["chi_phi"]) == 3
    assert all((d["nam"], d["thang"]) <= (nam, thang) for d in ct["khau_hao"])
    assert (ct["khau_hao"][-1]["luy_ke"] if ct["khau_hao"] else 0) == ct["hao_mon_luy_ke"]

    du_kien = client.get(f"/api/tai-san/{ts['id']}/du-kien", headers=h).json()
    assert du_kien[0]["muc_trich"] == 19516129
    assert du_kien[0]["dien_giai"] == "Dùng từ 10/03: tháng đầu trích 22/31 ngày"
    assert du_kien[0]["su_kien"] == [{
        "loai": "dau", "nhan": "Tháng đầu 22/31 ngày",
        "chi_tiet": "Dùng từ 10/03: tháng đầu trích 22/31 ngày",
    }]
    assert du_kien[1]["dien_giai"] is None and du_kien[1]["su_kien"] == []
    assert du_kien[-1]["dien_giai"].startswith("Hết khấu hao")
    assert sum(d["muc_trich"] for d in du_kien) == 3300000000


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
    assert ts["hao_mon_dau_ky"] == 116250000
    assert ts["thang_da_trich_dau_ky"] == 31
    ky_vong = luy_ke_den(
        [Moc(tu_ngay=__import__("datetime").date(2026, 1, 1), nguyen_gia=450000000,
             co_so_trich=333750000, so_thang_con=89, luy_ke_dau=116250000)],
        *thang_da_tinh(),
    )
    assert ts["hao_mon_luy_ke"] == ky_vong
    assert ts["con_lai"] == 450000000 - ky_vong
    assert client.get(f"/api/tai-san/{ts['id']}/du-kien", headers=h).json()[0]["muc_trich"] == 3750000


def test_bang_khau_hao_thang_tinh_tai_cho(client, seed_credentials):
    h = _token(client, seed_credentials)
    _komori(client, h)
    bang = client.get("/api/tai-san/thang/2026/3", headers=h).json()
    assert bang["tong_muc_trich"] == 19516129
    assert bang["items"][0]["luy_ke"] == 19516129
    assert bang["items"][0]["so_luong"] == 1
    assert bang["items"][0]["dien_giai"] == "Dùng từ 10/03: tháng đầu trích 22/31 ngày"
    assert "trang_thai" not in bang                     # không còn kỳ mở/chốt
    assert client.get("/api/tai-san/thang/2026/2", headers=h).json()["items"] == []
    # hỏi lại vẫn thế — không có nút tính, không có gì để chốt
    assert client.get("/api/tai-san/thang/2026/3", headers=h).json()["tong_muc_trich"] == 19516129
    # đường kỳ cũ không còn
    assert client.post("/api/tai-san/ky/2026/3/tinh", headers=h).status_code == 404
    assert client.get("/api/tai-san/ky", headers=h).status_code == 422   # rơi vào /{tai_san_id}
    assert client.get("/api/tai-san/thang/2026/13", headers=h).status_code == 422


def test_excel_bang_thang(client, seed_credentials):
    h = _token(client, seed_credentials)
    _komori(client, h)
    r = client.get("/api/tai-san/thang/2026/3/excel", headers=h)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert "khau-hao-03-2026.xlsx" in r.headers["content-disposition"]


def test_bien_dong_qua_api(client, seed_credentials):
    h = _token(client, seed_credentials)
    ts = client.post("/api/tai-san", headers=h, json={
        "ten": "May dao xen Polar", "loai": "tscd", "so_thang": 120,
        "ngay_su_dung": "2026-01-01", "nguon_vao": "ghi_tang",
        "chi_phi": [{"dien_giai": "Nguyen gia", "so_tien": 450000000}],
    }).json()
    r = client.post(f"/api/tai-san/{ts['id']}/bien-dong", headers=h, json={
        "loai": "nang_cap", "ngay": "2026-02-01", "so_tien": 50000000, "so_thang_con_lai": 100,
        "ly_do": "Thay dau dao",
    })
    assert r.status_code == 201, r.text
    ct = client.get(f"/api/tai-san/{ts['id']}", headers=h).json()
    assert len(ct["bien_dong"]) == 1
    assert ct["nguyen_gia"] == 500000000 and ct["so_thang_con"] == 100
    assert ct["moc_tu_ngay"] == "2026-02-01"
    assert "chenh_lech_thanh_ly" not in ct                     # ghi giảm đã bỏ
    # đường ghi giảm cũ không còn nhận
    r = client.post(f"/api/tai-san/{ts['id']}/bien-dong", headers=h, json={
        "loai": "ghi_giam", "ngay": "2026-03-01", "ly_do": "Thanh ly",
    })
    assert r.status_code == 422


def test_sua_o_so_sau_khi_co_chung_tu_thi_409(client, seed_credentials):
    h = _token(client, seed_credentials)
    ts = _komori(client, h)
    assert client.put(f"/api/tai-san/{ts['id']}", headers=h, json={"so_thang": 96}).status_code == 200
    r = client.post(f"/api/tai-san/{ts['id']}/bien-dong", headers=h, json={
        "loai": "nang_cap", "ngay": "2026-04-01", "so_tien": 1000000, "so_thang_con_lai": 90,
    })
    assert r.status_code == 201, r.text
    assert client.put(f"/api/tai-san/{ts['id']}", headers=h, json={"so_thang": 60}).status_code == 409
    assert client.put(f"/api/tai-san/{ts['id']}", headers=h, json={"ten": "Doi ten"}).status_code == 200
    # xoá thì luôn được (ghi giảm đã bỏ — xoá là lối ra cho món không dùng nữa)
    assert client.delete(f"/api/tai-san/{ts['id']}", headers=h).status_code == 204
    assert client.get(f"/api/tai-san/{ts['id']}", headers=h).status_code == 404


def test_route_thang_khong_bi_nuot_boi_route_id(client, seed_credentials):
    h = _token(client, seed_credentials)
    assert client.get("/api/tai-san/thang/2026/3", headers=h).status_code == 200


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
