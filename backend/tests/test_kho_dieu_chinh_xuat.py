"""Điều chỉnh phiếu xuất khi SX dùng ít hơn số đã xuất (spec-de-nghi-cap-vat-tu-cong-doan §2.3, §5.5).

Hai bảng số phải phân biệt được:
  · xin 100, xuất 100, điều chỉnh còn 70 ⇒ chốt 70, CÒN LẠI 0, Hoàn tất;
  · xin 100, kho mới xuất 70, KHÔNG điều chỉnh ⇒ chốt NULL, CÒN LẠI 30, Cấp một phần.
Trước đây `dieu_chinh_xuat` chỉ hạ `sl_da_ung` nên hai ca trên trông y hệt nhau — tổ trưởng nhìn
thấy "còn thiếu 30" ở ca đầu, đi hỏi kho một câu vô nghĩa.

Riêng ca kho đang cấp DỞ (chưa đạt mục tiêu hiệu lực) mà bị điều chỉnh: chốt KHÔNG được ghi, vì
ghi vô điều kiện sẽ đóng nhầm yêu cầu trong khi phần chưa xuất còn nguyên (Ruling 18).
"""
from __future__ import annotations

from app.db import SessionLocal
from app.models.stock_request import REQ_DONE, REQ_PARTIAL, StockRequest, StockRequestLine
from app.services.stock_request_service import StockRequestService

from tests.test_kho_de_nghi import _approved_request, _login, _nhap, _setup


def test_dieu_chinh_ghi_chot_thuc_xuat_va_dong_yeu_cau(client):
    """xin 100 · xuất 100 · điều chỉnh 100→70 ⇒ chốt 70, CÒN LẠI 0, Hoàn tất."""
    kho_id, mat_id = _setup(client)
    nhap = _nhap(client, kho_id=kho_id, mat_id=mat_id, qty=100, gia=1_000)
    lot_id = nhap["lines"][0]["lot_id"]
    req = _approved_request(client, kho_id=kho_id, loai="XUAT", mat_id=mat_id, qty=100)
    tk = _login(client, "t_thukho")
    r = client.post("/api/kho/phieu", headers=tk, json={
        "request_id": req["id"], "kho_id": kho_id,
        "lines": [{"request_line_id": req["lines"][0]["id"], "so_luong": 100, "lot_id": lot_id}],
    })
    assert r.status_code == 201, r.text
    vid = r.json()["id"]
    r = client.post(f"/api/kho/phieu/{vid}/ghi-so", headers=tk)
    assert r.status_code == 200, r.text
    line_id = r.json()["lines"][0]["id"]

    r = client.post(f"/api/kho/phieu/{vid}/dieu-chinh-xuat", headers=tk, json={
        "lines": [{"line_id": line_id, "so_luong_moi": 70}],
        "ly_do": "SX dùng không hết, trả lại 30",
    })
    assert r.status_code == 200, r.text

    with SessionLocal() as s:
        ln = s.get(StockRequestLine, req["lines"][0]["id"])
        assert float(ln.sl_de_nghi) == 100
        assert float(ln.sl_duyet) == 100  # KHÔNG hạ
        assert float(ln.sl_da_ung) == 70
        assert float(ln.sl_chot_thuc_xuat) == 70
        assert StockRequestService.con_lai(ln) == 0
        rq = s.get(StockRequest, req["id"])
        assert rq.trang_thai == REQ_DONE


def test_xuat_thieu_ma_khong_dieu_chinh_thi_van_con_lai(client):
    """xin 100 · kho mới xuất 70, KHÔNG điều chỉnh ⇒ chốt vẫn NULL, CÒN LẠI 30, Cấp một phần."""
    kho_id, mat_id = _setup(client)
    nhap = _nhap(client, kho_id=kho_id, mat_id=mat_id, qty=100, gia=1_000)
    lot_id = nhap["lines"][0]["lot_id"]
    req = _approved_request(client, kho_id=kho_id, loai="XUAT", mat_id=mat_id, qty=100)
    tk = _login(client, "t_thukho")
    r = client.post("/api/kho/phieu", headers=tk, json={
        "request_id": req["id"], "kho_id": kho_id,
        "lines": [{"request_line_id": req["lines"][0]["id"], "so_luong": 70,
                   "lot_id": lot_id, "ly_do": "NCC giao thiếu"}],
    })
    assert r.status_code == 201, r.text
    vid = r.json()["id"]
    assert client.post(f"/api/kho/phieu/{vid}/ghi-so", headers=tk).status_code == 200

    with SessionLocal() as s:
        ln = s.get(StockRequestLine, req["lines"][0]["id"])
        assert ln.sl_chot_thuc_xuat is None
        assert StockRequestService.con_lai(ln) == 30
        rq = s.get(StockRequest, req["id"])
        assert rq.trang_thai == REQ_PARTIAL


def test_dieu_chinh_hai_lan_thi_chot_bang_tong_thuc_xuat_hien_tai(client):
    """Chốt là TỔNG đã xuất hiện tại, không phải hiệu của lần điều chỉnh cuối: 100→80→60 ⇒ chốt 60."""
    kho_id, mat_id = _setup(client)
    nhap = _nhap(client, kho_id=kho_id, mat_id=mat_id, qty=100, gia=1_000)
    lot_id = nhap["lines"][0]["lot_id"]
    req = _approved_request(client, kho_id=kho_id, loai="XUAT", mat_id=mat_id, qty=100)
    tk = _login(client, "t_thukho")
    r = client.post("/api/kho/phieu", headers=tk, json={
        "request_id": req["id"], "kho_id": kho_id,
        "lines": [{"request_line_id": req["lines"][0]["id"], "so_luong": 100, "lot_id": lot_id}],
    })
    assert r.status_code == 201, r.text
    vid = r.json()["id"]
    r = client.post(f"/api/kho/phieu/{vid}/ghi-so", headers=tk)
    assert r.status_code == 200, r.text
    line_id = r.json()["lines"][0]["id"]

    r = client.post(f"/api/kho/phieu/{vid}/dieu-chinh-xuat", headers=tk, json={
        "lines": [{"line_id": line_id, "so_luong_moi": 80}],
        "ly_do": "SX dùng không hết đợt 1, trả lại 20",
    })
    assert r.status_code == 200, r.text
    r = client.post(f"/api/kho/phieu/{vid}/dieu-chinh-xuat", headers=tk, json={
        "lines": [{"line_id": line_id, "so_luong_moi": 60}],
        "ly_do": "SX dùng không hết đợt 2, trả lại 20",
    })
    assert r.status_code == 200, r.text

    with SessionLocal() as s:
        ln = s.get(StockRequestLine, req["lines"][0]["id"])
        assert float(ln.sl_chot_thuc_xuat) == 60


def test_dieu_chinh_khi_kho_moi_cap_mot_phan_thi_khong_chot(client):
    """xin 100 · xuất 60 · điều chỉnh 60→50 ⇒ chốt vẫn NULL, CÒN LẠI 50, vẫn 'Cấp một phần'.

    Ghi chốt vô điều kiện sẽ tính còn lại = max(50-50,0) = 0 rồi đóng nhầm yêu cầu, trong khi 50
    tờ ban đầu (100-60=40 chưa xuất, cộng 10 vừa bị trả) chưa hề được xuất (Ruling 18).
    """
    kho_id, mat_id = _setup(client)
    nhap = _nhap(client, kho_id=kho_id, mat_id=mat_id, qty=100, gia=1_000)
    lot_id = nhap["lines"][0]["lot_id"]
    req = _approved_request(client, kho_id=kho_id, loai="XUAT", mat_id=mat_id, qty=100)
    tk = _login(client, "t_thukho")
    r = client.post("/api/kho/phieu", headers=tk, json={
        "request_id": req["id"], "kho_id": kho_id,
        "lines": [{"request_line_id": req["lines"][0]["id"], "so_luong": 60,
                   "lot_id": lot_id, "ly_do": "Cấp đợt 1"}],
    })
    assert r.status_code == 201, r.text
    vid = r.json()["id"]
    r = client.post(f"/api/kho/phieu/{vid}/ghi-so", headers=tk)
    assert r.status_code == 200, r.text
    line_id = r.json()["lines"][0]["id"]

    r = client.post(f"/api/kho/phieu/{vid}/dieu-chinh-xuat", headers=tk, json={
        "lines": [{"line_id": line_id, "so_luong_moi": 50}],
        "ly_do": "SX dùng không hết, trả lại 10",
    })
    assert r.status_code == 200, r.text

    with SessionLocal() as s:
        ln = s.get(StockRequestLine, req["lines"][0]["id"])
        assert ln.sl_chot_thuc_xuat is None
        assert StockRequestService.con_lai(ln) == 50
        rq = s.get(StockRequest, req["id"])
        assert rq.trang_thai == REQ_PARTIAL
