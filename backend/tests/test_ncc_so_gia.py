"""Bảng giá NCC trỏ về MẶT HÀNG GỐC + so giá quy về đơn vị gốc (mg 0172).

Vì sao phải có: NCC A báo "1.020.000 đ/ram", NCC B báo "24.500 đ/kg". Hai con số này KHÔNG so
trực tiếp được, mà trước đây hệ thống ghép NCC với kho bằng CHUỖI tên hàng — gõ lệch một chữ là
trượt, mà trượt thì im lặng (không lỗi, chỉ là mãi không so được giá).
"""
from __future__ import annotations

from itertools import count

from app.db import SessionLocal
from app.models.don_vi_do import DonViDo, DonViQuyDoi
from app.models.vat_lieu_kho import VatTuInAn

ADMIN = {"username": "admin", "password": "admin123"}

#: Cấp MST duy nhất cho từng NCC dựng trong file này.
_dem_mst = count(1)


def _h(client) -> dict[str, str]:
    r = client.post("/api/auth/login", json=ADMIN)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _mat_hang() -> tuple[str, int]:
    """1 vật tư đếm theo TỜ, có cặp cố định 1 ram = 500 tờ."""
    db = SessionLocal()
    try:
        if db.query(DonViDo).filter(DonViDo.ma == "to").first() is None:
            to = DonViDo(ma="to", ten="tờ", ho="to")
            ram = DonViDo(ma="ram", ten="ram", ho="to")
            kg = DonViDo(ma="kg", ten="kg", ho="khoi_luong")
            db.add_all([to, ram, kg])
            db.flush()
            db.add(DonViQuyDoi(tu_id=ram.id, den_id=to.id, he_so=500))
        m = db.query(VatTuInAn).filter(VatTuInAn.ma == "SG-01").first()
        if m is None:
            m = VatTuInAn(ma="SG-01", ten="Giấy so giá", don_vi_gia="to")
            db.add(m)
        db.commit()
        return ("vat_tu", m.id)
    finally:
        db.close()


def _ncc(client, h, ten: str, item: dict) -> int:
    # MST phải KHÁC NHAU từng NCC: từ 12/08/2026 trùng mã số thuế bị chặn (một MST = một pháp
    # nhân, trùng gần như luôn là nhập trùng hồ sơ). Trước đó mọi NCC ở đây dùng chung một mã.
    # Đánh số theo thứ tự lập, KHÔNG băm tên — `hash()` chuỗi đổi theo từng lần chạy Python.
    mst = f"01{next(_dem_mst):08d}"
    r = client.post("/api/suppliers", headers=h, json={
        "name": ten, "tax_code": mst, "phone": "0900000000",
        "email": f"{ten.lower().replace(' ', '')}@x.vn", "address": "HN",
        "contact_name": "A", "supplier_group": "giay", "items": [item],
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_so_gia_quy_ve_don_vi_goc_roi_moi_xep_hang(client):
    """NCC bán theo RAM và NCC bán theo TỜ phải so được với nhau.

    Số thật: 250.000 đ/ram ÷ 500 tờ = 500 đ/tờ — đắt hơn NCC bán thẳng 450 đ/tờ. Nhìn hai con số
    gốc (250.000 vs 450) thì tưởng ngược lại.
    """
    h = _h(client)
    loai, hid = _mat_hang()
    _ncc(client, h, "NCC Ram", {
        "hang_loai": loai, "hang_id": hid, "item_name": "Giấy so giá",
        "unit": "ram", "unit_price": 250_000, "vat_percent": 8,
    })
    _ncc(client, h, "NCC To", {
        "hang_loai": loai, "hang_id": hid, "item_name": "Giấy so giá",
        "unit": "to", "unit_price": 450, "vat_percent": 8,
    })

    r = client.get("/api/supplier-items/so-gia", headers=h,
                   params={"hang_loai": loai, "hang_id": hid})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["don_vi_goc"] == "to"
    gia = {x["supplier_name"]: x for x in d["items"]}
    assert gia["NCC Ram"]["gia_quy_doi"] == 500       # 250.000 ÷ 500 tờ
    assert gia["NCC To"]["gia_quy_doi"] == 450
    # RẺ NHẤT ĐỨNG ĐẦU — bảng này tồn tại để trả lời "mua của ai".
    assert d["items"][0]["supplier_name"] == "NCC To"
    # Giá sau VAT cũng quy theo đơn vị gốc (450 × 1,08 = 486).
    assert gia["NCC To"]["gia_quy_doi_vat"] == 486


def test_don_vi_ncc_ban_phai_doi_duoc_ve_goc(client):
    """NCC khai đơn vị nằm ngoài tập đổi được → CHẶN ngay lúc lưu bảng giá.

    Không chặn thì dòng đó vĩnh viễn trống cột "giá quy đổi" và im lặng biến mất khỏi so giá —
    người dùng tưởng NCC ấy không bán.
    """
    h = _h(client)
    loai, hid = _mat_hang()
    r = client.post("/api/suppliers", headers=h, json={
        "name": "NCC Sai DV", "tax_code": "0100000001", "phone": "0900000001",
        "email": "saidv@x.vn", "address": "HN", "contact_name": "B", "supplier_group": "giay",
        "items": [{"hang_loai": loai, "hang_id": hid, "item_name": "Giấy so giá",
                   "unit": "kg", "unit_price": 1000}],
    })
    assert r.status_code == 422, r.text
    assert "không đổi được" in r.json()["detail"]


def test_hang_ngoai_danh_muc_van_luu_duoc_nhung_khong_vao_so_gia(client):
    """NCC bán dịch vụ / gia công (ngoài danh mục vật tư) — vẫn khai được, chỉ không so giá.

    Bắt buộc gắn mặt hàng thì không khai nổi mấy dòng đó; đó là lý do cặp khoá để NULLABLE.
    """
    h = _h(client)
    loai, hid = _mat_hang()
    sid = _ncc(client, h, "NCC Gia Cong", {
        "item_name": "Gia công cán màng", "unit": "m2", "unit_price": 3000,
    })
    assert sid > 0
    r = client.get("/api/supplier-items/so-gia", headers=h,
                   params={"hang_loai": loai, "hang_id": hid})
    assert r.status_code == 200
    assert all(x["supplier_name"] != "NCC Gia Cong" for x in r.json()["items"])


def test_gan_mat_hang_phai_du_ca_cap(client):
    """Chỉ có `hang_loai` mà thiếu `hang_id` (hoặc ngược lại) → chặn, không lưu nửa vời."""
    h = _h(client)
    r = client.post("/api/suppliers", headers=h, json={
        "name": "NCC Nua Voi", "tax_code": "0100000002", "phone": "0900000002",
        "email": "nuavoi@x.vn", "address": "HN", "contact_name": "C", "supplier_group": "giay",
        "items": [{"hang_loai": "vat_tu", "item_name": "X", "unit": "to", "unit_price": 100}],
    })
    assert r.status_code == 422, r.text
