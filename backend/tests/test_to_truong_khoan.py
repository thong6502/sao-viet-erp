"""TỔ TRƯỞNG ăn THƯỞNG hay ăn CHIA theo sản lượng tổ — chỗ khai báo (chủ 19/09/2026).

Chủ: *"Ông A làm được 100k thì công ty sẽ thưởng 5% dựa trên 100k, còn Ông B ăn chia ấy làm được 100k,
ông B lấy 5% rồi còn 95% lại chia đều cho cả tổ: giờ tôi cần chỗ nhập liệu trước còn đấu vào lương để
làm sau"*.

Khai theo TỔ, mỗi dòng là một MỐC "áp dụng từ ngày". Chưa nối vào tính lương — các bài dưới chỉ khoá chỗ
khai: thêm mốc, sửa mốc cùng ngày, mốc hiệu lực, xoá mốc, tỷ lệ hợp lệ, và chặn tổ không ăn khoán.
Ngày mốc cố ý chọn 2020 / 2021 / 2099 để "mốc đang hiệu lực" không phụ thuộc ngày máy chạy test.
"""
from __future__ import annotations

from tests.test_com_tang_ca import _h

GOC = "/api/luong/khoan/to-truong"


def _to(client, h, ten: str, *, khoan: bool) -> int:
    r = client.post("/api/departments", json={"name": ten, "has_piece_work": khoan}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_KHAI_che_do_to_truong_theo_moc_cho_to_khoan(client):
    """⭐ Thêm mốc · mốc tương lai chưa hiệu lực · khai lại CÙNG ngày là sửa · 'không áp dụng' lưu 0% ·
    xoá mốc."""
    h = _h(client)
    pb = _to(client, h, "Tổ bế tổ trưởng", khoan=True)

    r = client.get(f"{GOC}/{pb}", headers=h)
    assert r.status_code == 200, r.text
    assert r.json() == {"department_id": pb, "hien_hanh": None, "items": []}

    # Ông A: ăn thưởng 5%.
    r = client.put(f"{GOC}/{pb}", json={"ap_dung_tu": "2020-01-01", "che_do": "thuong", "ty_le": 5},
                   headers=h)
    assert r.status_code == 200, r.text
    hh = r.json()["hien_hanh"]
    assert (hh["che_do"], hh["ty_le"]) == ("thuong", 5)

    # Mốc TƯƠNG LAI: có trong danh sách (mới nhất đứng đầu) nhưng CHƯA là chế độ hiện hành.
    r = client.put(f"{GOC}/{pb}", json={"ap_dung_tu": "2099-01-01", "che_do": "chia", "ty_le": 5},
                   headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert [m["ap_dung_tu"] for m in d["items"]] == ["2099-01-01", "2020-01-01"]
    assert d["hien_hanh"]["ap_dung_tu"] == "2020-01-01"

    # Khai lại CÙNG ngày = SỬA mốc đó (đổi cả chế độ lẫn tỷ lệ), không đẻ mốc trùng.
    r = client.put(f"{GOC}/{pb}", json={"ap_dung_tu": "2020-01-01", "che_do": "chia", "ty_le": 7.5,
                                        "ghi_chu": "  họp tổ  "}, headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert len(d["items"]) == 2
    hh = d["hien_hanh"]
    assert (hh["che_do"], hh["ty_le"], hh["ghi_chu"]) == ("chia", 7.5, "họp tổ")

    # "Không áp dụng" từ 2021: tỷ lệ gõ kèm bị bỏ, lưu 0; thành chế độ hiện hành (2021 ≤ hôm nay).
    r = client.put(f"{GOC}/{pb}", json={"ap_dung_tu": "2021-01-01", "che_do": "khong", "ty_le": 9},
                   headers=h)
    assert r.status_code == 200, r.text
    hh = r.json()["hien_hanh"]
    assert (hh["ap_dung_tu"], hh["che_do"], hh["ty_le"]) == ("2021-01-01", "khong", 0)

    muc_tuong_lai = next(m["id"] for m in r.json()["items"] if m["ap_dung_tu"] == "2099-01-01")
    r = client.delete(f"{GOC}/{pb}/{muc_tuong_lai}", headers=h)
    assert r.status_code == 200, r.text
    assert [m["ap_dung_tu"] for m in r.json()["items"]] == ["2021-01-01", "2020-01-01"]


def test_CHAN_khai_che_do_to_truong_cho_to_khong_an_khoan(client):
    """Thưởng / chia tính trên SẢN LƯỢNG tổ — tổ công nhật / tổ Giao hàng không khai được."""
    h = _h(client)
    thuong = _to(client, h, "Tổ văn phòng tổ trưởng", khoan=False)
    r = client.put(f"{GOC}/{thuong}", json={"ap_dung_tu": "2020-01-01", "che_do": "thuong",
                                            "ty_le": 5}, headers=h)
    assert r.status_code == 400, r.text
    assert "chưa bật Lương khoán" in r.text, r.text

    gh = client.post("/api/departments", json={"name": "Tổ xe tổ trưởng", "la_giao_hang": True},
                     headers=h)
    assert gh.status_code == 201, gh.text
    r = client.put(f"{GOC}/{gh.json()['id']}", json={"ap_dung_tu": "2020-01-01", "che_do": "chia",
                                                     "ty_le": 5}, headers=h)
    assert r.status_code == 400, r.text


def test_TY_LE_to_truong_hop_le_va_xoa_moc_to_khac_bi_chan(client):
    h = _h(client)
    pb = _to(client, h, "Tổ bồi tổ trưởng", khoan=True)
    moc = {"ap_dung_tu": "2020-01-01"}

    # Ăn thưởng / ăn chia mà 0% là khai hụt.
    for che_do in ("thuong", "chia"):
        r = client.put(f"{GOC}/{pb}", json={**moc, "che_do": che_do, "ty_le": 0}, headers=h)
        assert r.status_code == 400, (che_do, r.text)
        assert "lớn hơn 0" in r.text, r.text
    # Ăn chia 100% = tổ trưởng lấy hết, không còn gì chia cho tổ.
    r = client.put(f"{GOC}/{pb}", json={**moc, "che_do": "chia", "ty_le": 100}, headers=h)
    assert r.status_code == 400, r.text
    assert "nhỏ hơn 100%" in r.text, r.text
    # Ngoài 0–100 và chế độ lạ: chặn ngay ở schema.
    for sai in ({"che_do": "thuong", "ty_le": 101}, {"che_do": "thuong", "ty_le": -1},
                {"che_do": "an_het", "ty_le": 5}):
        r = client.put(f"{GOC}/{pb}", json={**moc, **sai}, headers=h)
        assert r.status_code == 422, (sai, r.text)
    assert client.get(f"{GOC}/{pb}", headers=h).json()["items"] == []

    r = client.put(f"{GOC}/{pb}", json={**moc, "che_do": "thuong", "ty_le": 5}, headers=h)
    muc = r.json()["items"][0]["id"]
    khac = _to(client, h, "Tổ dán tổ trưởng", khoan=True)
    r = client.delete(f"{GOC}/{khac}/{muc}", headers=h)
    assert r.status_code == 404, "xoá được mốc của tổ khác qua đường dẫn tổ này"
    assert len(client.get(f"{GOC}/{pb}", headers=h).json()["items"]) == 1

    assert client.get(f"{GOC}/999999", headers=h).status_code == 404
