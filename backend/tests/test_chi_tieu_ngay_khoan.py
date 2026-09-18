"""CHỈ TIÊU NGÀY của tổ lương khoán / sản lượng — chỗ khai báo (chủ 16/09/2026).

Chủ: *"nó có chỉ tiêu ngày là bao nhiêu tiền đó nên là mình sẽ có phần cấu hình chỉ tiêu ngày cho bên
lương khoán / sản lượng, chưa cần phải đâu vào đâu cả, chỉ cần tạo ra đã"*.

Khai theo TỔ, mỗi dòng là một MỐC "áp dụng từ ngày" (đ/công). Chưa nối vào tính lương — các bài dưới
chỉ khoá chỗ khai: thêm mốc, sửa mốc cùng ngày, mốc hiệu lực, xoá mốc, và chặn tổ không ăn khoán.
Ngày mốc cố ý chọn 2020 / 2099 để "mốc đang hiệu lực" không phụ thuộc ngày máy chạy test.
"""
from __future__ import annotations

from tests.test_com_tang_ca import _h

GOC = "/api/luong/khoan/chi-tieu-ngay"


def _to(client, h, ten: str, *, khoan: bool) -> int:
    r = client.post("/api/departments", json={"name": ten, "has_piece_work": khoan}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_KHAI_chi_tieu_ngay_theo_moc_cho_to_khoan(client):
    """⭐ Thêm mốc · mốc tương lai chưa hiệu lực · khai lại CÙNG ngày là sửa số · xoá mốc."""
    h = _h(client)
    pb = _to(client, h, "Tổ bế chỉ tiêu", khoan=True)

    r = client.get(f"{GOC}/{pb}", headers=h)
    assert r.status_code == 200, r.text
    assert r.json() == {"department_id": pb, "hien_hanh": None, "items": []}

    r = client.put(f"{GOC}/{pb}", json={"ap_dung_tu": "2020-01-01", "so_tien": 350_000}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["hien_hanh"]["so_tien"] == 350_000

    # Mốc TƯƠNG LAI: có trong danh sách (mới nhất đứng đầu) nhưng CHƯA là chỉ tiêu hiện hành.
    r = client.put(f"{GOC}/{pb}", json={"ap_dung_tu": "2099-01-01", "so_tien": 999_000,
                                        "ghi_chu": "tăng chỉ tiêu"}, headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert [m["ap_dung_tu"] for m in d["items"]] == ["2099-01-01", "2020-01-01"]
    assert d["hien_hanh"]["ap_dung_tu"] == "2020-01-01"

    # Khai lại CÙNG ngày = SỬA số của mốc đó, không đẻ mốc trùng.
    r = client.put(f"{GOC}/{pb}", json={"ap_dung_tu": "2020-01-01", "so_tien": 360_000,
                                        "ghi_chu": "  gõ nhầm  "}, headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert len(d["items"]) == 2
    assert d["hien_hanh"]["so_tien"] == 360_000 and d["hien_hanh"]["ghi_chu"] == "gõ nhầm"

    muc_tuong_lai = next(m["id"] for m in d["items"] if m["ap_dung_tu"] == "2099-01-01")
    r = client.delete(f"{GOC}/{pb}/{muc_tuong_lai}", headers=h)
    assert r.status_code == 200, r.text
    assert [m["ap_dung_tu"] for m in r.json()["items"]] == ["2020-01-01"]


def test_CHAN_khai_chi_tieu_ngay_cho_to_khong_an_khoan(client):
    """Chỉ tiêu ngày là chỉ tiêu tiền SẢN LƯỢNG — tổ công nhật / tổ Giao hàng không khai được."""
    h = _h(client)
    thuong = _to(client, h, "Tổ văn phòng chỉ tiêu", khoan=False)
    r = client.put(f"{GOC}/{thuong}", json={"ap_dung_tu": "2020-01-01", "so_tien": 300_000},
                   headers=h)
    assert r.status_code == 400, r.text
    assert "chưa bật Lương khoán" in r.text, r.text

    gh = client.post("/api/departments", json={"name": "Tổ xe chỉ tiêu", "la_giao_hang": True},
                     headers=h)
    assert gh.status_code == 201, gh.text
    r = client.put(f"{GOC}/{gh.json()['id']}", json={"ap_dung_tu": "2020-01-01", "so_tien": 300_000},
                   headers=h)
    assert r.status_code == 400, r.text


def test_CHI_TIEU_ngay_phai_lon_hon_0_va_xoa_moc_to_khac_bi_chan(client):
    h = _h(client)
    pb = _to(client, h, "Tổ bồi chỉ tiêu", khoan=True)
    for sai in (0, -1):
        r = client.put(f"{GOC}/{pb}", json={"ap_dung_tu": "2020-01-01", "so_tien": sai}, headers=h)
        assert r.status_code == 422, (sai, r.text)

    r = client.put(f"{GOC}/{pb}", json={"ap_dung_tu": "2020-01-01", "so_tien": 300_000}, headers=h)
    muc = r.json()["items"][0]["id"]
    khac = _to(client, h, "Tổ dán chỉ tiêu", khoan=True)
    r = client.delete(f"{GOC}/{khac}/{muc}", headers=h)
    assert r.status_code == 404, "xoá được mốc của tổ khác qua đường dẫn tổ này"
    assert len(client.get(f"{GOC}/{pb}", headers=h).json()["items"]) == 1

    assert client.get(f"{GOC}/999999", headers=h).status_code == 404
