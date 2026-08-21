"""Bốn bug của phân hệ Cấu hình danh mục — vá 15/08/2026, đây là lưới chặn tái phát.

Cả bốn đều là lỗi CÂM: không ai thấy stack trace, chỉ thấy màn hình nói sai.

  1. Nhật ký của ĐƠN VỊ trộn với nhật ký của CẶP QUY ĐỔI — hai bảng đánh số riêng nhưng ghi chung
     một chuỗi target `don_vi_do:<id>`.
  2. Tab Nhật ký của LOẠI SẢN PHẨM luôn rỗng — service không nhận `audit` nên không ghi dòng nào,
     trong khi router nhật ký đã map sẵn loại này.
  3. Ô chọn BÙ HAO ở màn Công đoạn rỗng trơn — router bù hao khoá chặt `dm_bu_hao:read`, frontend
     nuốt 403 thành danh sách rỗng.
  4. Xem được DANH SÁCH nhưng mở CHI TIẾT ăn 403 — list dùng OR-gate, detail dùng quyền chặt.
"""
from __future__ import annotations

import pytest

from tests.test_catalog_costing_read import _h, _token_for_role


def _admin(client) -> dict[str, str]:
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return _h(r.json()["access_token"])


# ── 1. Nhật ký đơn vị KHÔNG được lẫn nhật ký cặp quy đổi ─────────────────────────
def test_nhat_ky_cap_quy_doi_khong_tron_voi_don_vi(client):
    h = _admin(client)
    a = client.post("/api/don-vi", json={"ma": "zzta", "ten": "ZZ Tấn"}, headers=h)
    b = client.post("/api/don-vi", json={"ma": "zzkg", "ten": "ZZ Ký"}, headers=h)
    assert a.status_code == 201 and b.status_code == 201, (a.text, b.text)
    a_id, b_id = a.json()["id"], b.json()["id"]

    cap = client.post("/api/don-vi/quy-doi",
                      json={"tu_id": a_id, "den_id": b_id, "he_so": 1000}, headers=h)
    assert cap.status_code == 201, cap.text
    cap_id = cap.json()["id"]

    # Nhật ký của ĐƠN VỊ: chỉ có dòng của chính nó, không có dòng nào của cặp.
    nk_dv = client.get(f"/api/nhat-ky-danh-muc/don_vi_do/{a_id}", headers=h).json()["items"]
    assert nk_dv, "tạo đơn vị phải ghi nhật ký"
    assert not [x for x in nk_dv if "cap" in x["action"]], \
        f"nhật ký đơn vị #{a_id} lẫn dòng của cặp quy đổi: {nk_dv}"

    # Nhật ký của CẶP: nằm dưới loại riêng, và có dòng tạo.
    nk_cap = client.get(f"/api/nhat-ky-danh-muc/don_vi_quy_doi/{cap_id}", headers=h)
    assert nk_cap.status_code == 200, nk_cap.text
    assert [x for x in nk_cap.json()["items"] if x["action"] == "create_don_vi_cap"]


# ── 2. Loại sản phẩm phải ghi nhật ký ────────────────────────────────────────────
def test_loai_san_pham_co_nhat_ky(client):
    h = _admin(client)
    r = client.post("/api/loai-san-pham",
                    json={"ma": "ZZSP", "ten": "ZZ Sản phẩm", "structural_type": "flat"},
                    headers=h)
    assert r.status_code == 201, r.text
    sp_id = r.json()["id"]

    nk = client.get(f"/api/nhat-ky-danh-muc/loai_san_pham/{sp_id}", headers=h)
    assert nk.status_code == 200, nk.text
    assert nk.json()["items"], "tab Nhật ký của Loại sản phẩm đang RỖNG — service chưa ghi audit"

    client.put(f"/api/loai-san-pham/{sp_id}",
               json={"ma": "ZZSP", "ten": "ZZ Sản phẩm (đổi tên)", "structural_type": "flat"},
               headers=h)
    items = client.get(f"/api/nhat-ky-danh-muc/loai_san_pham/{sp_id}", headers=h).json()["items"]
    assert any(x["action"] == "dm_sua" for x in items), items


# ── 3. Người khai Công đoạn phải ĐỌC được bù hao (nhưng không khai được) ─────────
def test_bu_hao_doc_duoc_boi_nguoi_khai_cong_doan(client):
    """`cong_doan.bu_hao_id` trỏ thẳng sang bù hao — không đọc được thì ô chọn rỗng IM LẶNG."""
    token = _token_for_role("cd-only", [("dm_cong_doan", "all")])
    assert client.get("/api/bu-hao", headers=_h(token)).status_code == 200
    # GHI thì vẫn phải đúng quyền của chính danh mục bù hao.
    assert client.post("/api/bu-hao", json={"ma": "ZZBH", "ten": "ZZ"},
                       headers=_h(token)).status_code == 403


# ── 4. Ai LIỆT KÊ được thì phải MỞ được chi tiết ─────────────────────────────────
@pytest.mark.parametrize("prefix,payload", [
    ("/api/cong-doan", {"ma": "ZZCD", "ten": "ZZ Công đoạn", "nhom": "finishing",
                        "pricing_basis": "per_finished_qty"}),
    ("/api/may-thiet-bi", {"ma": "ZZMAY", "ten": "ZZ Máy", "loai_may": "Máy in",
                           "so_nhan_cong": 1}),
    ("/api/loai-san-pham", {"ma": "ZZSP2", "ten": "ZZ SP2", "structural_type": "flat"}),
    ("/api/don-vi", {"ma": "zzdv", "ten": "ZZ Đơn vị"}),
])
def test_detail_mo_cho_ai_list_duoc(client, prefix, payload):
    """Trước bản vá: list 200 nhưng detail 403 — người dùng bấm vào một dòng là ăn lỗi câm."""
    h = _admin(client)
    tao = client.post(prefix, json=payload, headers=h)
    assert tao.status_code == 201, tao.text
    item_id = tao.json()["id"]

    token = _token_for_role("tg-only", [("tinh_gia_thanh", "all")])
    assert client.get(prefix, headers=_h(token)).status_code == 200, f"{prefix} list"
    assert client.get(f"{prefix}/{item_id}", headers=_h(token)).status_code == 200, \
        f"{prefix}/{{id}} — liệt kê được mà mở chi tiết thì 403"


def test_bang_quy_doi_doc_duoc_boi_nguoi_kho(client):
    """Người Kho chọn được ĐVT thì cũng phải đọc được bảng quy đổi của nó."""
    token = _token_for_role("kho-only", [("kho", "all")])
    for ep in ("/api/don-vi", "/api/don-vi/quy-doi", "/api/don-vi/ho", "/api/don-vi/bien"):
        assert client.get(ep, headers=_h(token)).status_code == 200, ep


# ── 5. Hỏi "còn ai dùng không" trước khi xoá ─────────────────────────────────────
def test_kiem_xoa_tra_du_thu_hop_thoai_can(client):
    """Một endpoint chung cho 8 màn — hộp thoại xoá tự quyết bằng số, không đoán."""
    h = _admin(client)
    bh = client.post("/api/bu-hao", json={"ma": "ZZBH9", "ten": "ZZ Bù hao"}, headers=h)
    assert bh.status_code == 201, bh.text
    bh_id = bh.json()["id"]

    r = client.get(f"/api/danh-muc/bu_hao/{bh_id}/kiem-xoa", headers=h)
    assert r.status_code == 200, r.text
    assert r.json() == {"xoa_han_duoc": True, "chan": [], "keo_theo": []}

    # Gắn một công đoạn tra mã này ⇒ hết xoá hẳn được, và câu trả lời phải nêu SỐ.
    cd = client.post("/api/cong-doan",
                     json={"ma": "ZZCD9", "ten": "ZZ CĐ", "nhom": "finishing",
                           "pricing_basis": "per_finished_qty",
                           "kieu_bu_hao": "tra_bang", "bu_hao_id": bh_id}, headers=h)
    assert cd.status_code == 201, cd.text

    sau = client.get(f"/api/danh-muc/bu_hao/{bh_id}/kiem-xoa", headers=h).json()
    assert sau["xoa_han_duoc"] is False
    assert sau["chan"] == ["1 công đoạn tra mã này"], sau


@pytest.mark.parametrize("prefix,payload", [
    ("/api/cong-doan", {"ma": "ZZCD8", "ten": "ZZ CĐ8", "nhom": "finishing",
                        "pricing_basis": "per_finished_qty"}),
    ("/api/bu-hao", {"ma": "ZZBH8", "ten": "ZZ BH8"}),
    ("/api/loai-san-pham", {"ma": "ZZSP8", "ten": "ZZ SP8", "structural_type": "flat"}),
])
def test_ngung_dung_va_bat_lai_khong_can_gui_ca_ban_ghi(client, prefix, payload):
    """Nút "Ngừng dùng" / "Bật lại" đổi ĐÚNG MỘT trường — phải có đường gửi đúng một trường.

    Trước 15/08/2026 màn gọi `PUT /{id}` với mỗi `{"active": false}`. `PUT` nhận schema ĐẦY ĐỦ nên
    Pydantic chặn ngay ở cổng: 422 "field required" cho `ma`/`ten`/`nhom`… — service không bao giờ
    chạy tới. Màn nuốt 422 thành "Request failed" nên bấm xong KHÔNG THẤY GÌ XẢY RA, ở cả bốn danh
    mục xoá mềm. Lưới cũ chỉ thử ở tầng service nên không chạm đường này.
    """
    h = _admin(client)
    tao = client.post(prefix, json=payload, headers=h)
    assert tao.status_code == 201, tao.text
    item_id = tao.json()["id"]

    # PUT một phần vẫn 422 — đó là hành vi ĐÚNG của schema đầy đủ, không phải thứ cần nới.
    assert client.put(f"{prefix}/{item_id}", json={"active": False}, headers=h).status_code == 422

    ngung = client.patch(f"{prefix}/{item_id}/active", json={"active": False}, headers=h)
    assert ngung.status_code == 200, ngung.text
    assert ngung.json()["active"] is False
    # Ngừng rồi thì rơi khỏi danh sách mặc định, và tìm thấy ở luồng "đã ngừng".
    assert item_id not in [r["id"] for r in client.get(f"{prefix}?active=true", headers=h).json()["items"]]
    assert item_id in [r["id"] for r in client.get(f"{prefix}?active=false", headers=h).json()["items"]]

    bat = client.patch(f"{prefix}/{item_id}/active", json={"active": True}, headers=h)
    assert bat.status_code == 200 and bat.json()["active"] is True


def test_dat_active_can_quyen_ghi(client):
    """Vai chỉ ĐỌC không được tắt một dòng danh mục — nút kia gác quyền, cổng này cũng phải gác."""
    h = _admin(client)
    r = client.post("/api/bu-hao", json={"ma": "ZZBH7", "ten": "ZZ BH7"}, headers=h)
    assert r.status_code == 201, r.text
    token = _token_for_role("chi-doc-tg", [("tinh_gia_thanh", "all")])
    assert client.patch(f"/api/bu-hao/{r.json()['id']}/active",
                        json={"active": False}, headers=_h(token)).status_code == 403


def test_kiem_xoa_loai_la_tra_404_va_can_quyen_xoa(client):
    h = _admin(client)
    assert client.get("/api/danh-muc/khong_co/1/kiem-xoa", headers=h).status_code == 404
    # Vai chỉ ĐỌC được danh mục thì không được hỏi câu này (nó lộ số liệu nghiệp vụ).
    token = _token_for_role("chi-doc-bh", [("tinh_gia_thanh", "all")])
    assert client.get("/api/danh-muc/bu_hao/1/kiem-xoa", headers=_h(token)).status_code == 403
