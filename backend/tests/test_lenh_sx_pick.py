"""PICK ấn phẩm → LỆNH (nhiều ấn phẩm/lệnh) — VERIFY THẬT (spec § pick, plan kind-yawning-storm).

Kiểm luồng người kế hoạch CHỦ ĐỘNG pick gom ấn phẩm thành lệnh:
  - `POST /api/lenh-sx/lenh` gom nhiều ấn phẩm (cùng đơn) → 1 LỆNH nháp + n BÀI CON; đích SL = Σ.
  - Pick DẦN: đơn ở lại sổ hàng chờ tới khi MỌI ấn phẩm đã lên lệnh; ấn phẩm đã pick rời sổ.
  - Cổng cấu trúc (KHÔNG phán nghiệp vụ): ptp không thuộc đơn → 422; ptp đã có lệnh → 409 (chống trùng).
  - `GET /api/lenh-sx/an-pham/{ptp}` CÔ LẬP THƯƠNG MẠI: quy cách + routing gốc, KHÔNG lộ trường giá.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

from app.db import SessionLocal
from app.models.cong_doan import CongDoan
from app.models.khuon_be import KhuonBe
from app.models.lenh_san_xuat import LENH_DANG_CHAY, LenhSanXuat
from app.models.order import Order, OrderLine
from app.models.phieu_tinh_gia import PhieuThanhPhan, PhieuThanhPham, PhieuTinhGia


def _headers(client) -> dict[str, str]:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _seed_multi(
    *, order_no: str, qtys: list[int], released: bool = True,
    delivery_committed_date: date | None = None,
) -> tuple[int, list[int]]:
    """1 Đơn ĐÃ CHỐT + N ấn phẩm (mỗi ấn phẩm 1 dòng đơn qty riêng). Trả (order_id, [ptp_id...])."""
    db = SessionLocal()
    try:
        ptg = PhieuTinhGia(ma=f"PTG-{order_no}", ten_san_pham="Bộ ấn phẩm", so_luong=0)
        db.add(ptg)
        db.flush()
        order = Order(
            order_no=order_no, status="ordered", is_rush=False,
            san_xuat_released_at=(datetime.now(timezone.utc) if released else None),
            delivery_committed_date=delivery_committed_date,
        )
        db.add(order)
        db.flush()
        ptp_ids: list[int] = []
        for i, q in enumerate(qtys, start=1):
            ptp = PhieuThanhPhan(phieu_id=ptg.id, thu_tu=i, ten=f"Ấn phẩm {i}", so_luong=q)
            db.add(ptp)
            db.flush()
            ptp_ids.append(ptp.id)
            db.add(OrderLine(
                order_id=order.id, description=f"Sản phẩm {i}", qty=q,
                don_vi_tinh="cái", phieu_thanh_phan_id=ptp.id,
            ))
        db.commit()
        return order.id, ptp_ids
    finally:
        db.close()


def test_tao_lenh_gom_nhieu_an_pham(client):
    h = _headers(client)
    oid, ptps = _seed_multi(order_no="DH-PICK-GOM", qtys=[300, 200])

    r = client.post(
        "/api/lenh-sx/lenh",
        json={"order_id": oid, "phieu_thanh_phan_ids": ptps}, headers=h,
    )
    assert r.status_code == 201, r.text
    lenh_id = r.json()["id"]
    assert r.json()["phieu_thanh_phan_id"] == ptps[0]  # ấn phẩm đại diện = bài con đầu

    d = client.get(f"/api/lenh-sx/lenh/{lenh_id}", headers=h).json()
    assert len(d["items"]) == 2                                   # giữ ĐỦ 2 bài con
    assert {it["phieu_thanh_phan_id"] for it in d["items"]} == set(ptps)
    assert d["muc_tieu_sl"] == 500                                # đích SL = Σ (300 + 200)

    # gom hết ấn phẩm → đơn rời sổ hàng chờ
    assert all(x["order_id"] != oid for x in client.get("/api/lenh-sx/hang-cho", headers=h).json())


def test_pick_dan_don_o_lai_toi_khi_het_an_pham(client):
    h = _headers(client)
    oid, ptps = _seed_multi(order_no="DH-PICK-DAN", qtys=[100, 200, 300])

    # pick 1 ấn phẩm → còn 2 ấn phẩm chưa lên lệnh → đơn VẪN ở sổ, chỉ hiện 2 ấn phẩm còn lại
    r1 = client.post(
        "/api/lenh-sx/lenh",
        json={"order_id": oid, "phieu_thanh_phan_ids": [ptps[0]]}, headers=h,
    )
    assert r1.status_code == 201, r1.text
    rows = [x for x in client.get("/api/lenh-sx/hang-cho", headers=h).json() if x["order_id"] == oid]
    assert len(rows) == 1
    con_lai = {a["phieu_thanh_phan_id"] for a in rows[0]["an_pham"]}
    assert con_lai == {ptps[1], ptps[2]}                          # ấn phẩm đã pick rời sổ

    # pick nốt 2 ấn phẩm còn lại → đơn rời sổ
    r2 = client.post(
        "/api/lenh-sx/lenh",
        json={"order_id": oid, "phieu_thanh_phan_ids": [ptps[1], ptps[2]]}, headers=h,
    )
    assert r2.status_code == 201, r2.text
    assert all(x["order_id"] != oid for x in client.get("/api/lenh-sx/hang-cho", headers=h).json())


def test_pick_ptp_ngoai_don_bi_chan_422(client):
    h = _headers(client)
    oid, _ = _seed_multi(order_no="DH-PICK-OUT", qtys=[100])
    r = client.post(
        "/api/lenh-sx/lenh",
        json={"order_id": oid, "phieu_thanh_phan_ids": [999_999]}, headers=h,
    )
    assert r.status_code == 422, r.text


def test_pick_ptp_da_co_lenh_bi_chan_409(client):
    h = _headers(client)
    oid, ptps = _seed_multi(order_no="DH-PICK-DUP", qtys=[100, 200])
    assert client.post(
        "/api/lenh-sx/lenh",
        json={"order_id": oid, "phieu_thanh_phan_ids": [ptps[0]]}, headers=h,
    ).status_code == 201
    # pick lại ấn phẩm đã nằm trong lệnh khác → 409 (chống trùng)
    r = client.post(
        "/api/lenh-sx/lenh",
        json={"order_id": oid, "phieu_thanh_phan_ids": [ptps[0]]}, headers=h,
    )
    assert r.status_code == 409, r.text


def test_an_pham_chi_tiet_co_lap_thuong_mai(client):
    """Drawer chi tiết ấn phẩm CHỈ trả kỹ thuật — LỌC SẠCH mọi trường giá (không xuống kỹ thuật)."""
    h = _headers(client)
    db = SessionLocal()
    try:
        ptg = PhieuTinhGia(ma="PTG-DRAWER", ten_san_pham="Tờ rơi", so_luong=1000)
        db.add(ptg)
        db.flush()
        ptp = PhieuThanhPhan(
            phieu_id=ptg.id, thu_tu=1, ten="Tờ rơi A5", so_luong=1000,
            quy_cach_in="hai_mat", so_mau_a=4, so_mau_b=4, kho_in_dai=650, kho_in_rong=860,
            # các trường GIÁ — PHẢI không lộ ra drawer:
            don_gia_giay=12345, che_ban_don_gia=6789, don_gia_cong_in=222, gia_von_tp=999999,
        )
        db.add(ptp)
        db.flush()
        db.add(PhieuThanhPham(
            thanh_phan_id=ptp.id, thu_tu=1, cong_doan_id=None, ten="Cán màng",
            don_gia=54321, nha_cung_cap="Xưởng ngoài A",
        ))
        db.commit()
        ptp_id = ptp.id
    finally:
        db.close()

    r = client.get(f"/api/lenh-sx/an-pham/{ptp_id}", headers=h)
    assert r.status_code == 200, r.text
    data = r.json()
    # kỹ thuật CÓ mặt
    assert data["ten"] == "Tờ rơi A5"
    assert data["quy_cach_in"] == "hai_mat"
    assert data["so_mau_a"] == 4 and data["so_mau_b"] == 4
    assert len(data["routing"]) == 1
    assert data["routing"][0]["ten"] == "Cán màng"
    assert data["routing"][0]["nha_cung_cap"] == "Xưởng ngoài A"
    # THƯƠNG MẠI: không có bất kỳ khóa giá nào + không lộ giá trị giá trong payload
    blob = json.dumps(data)
    for gia_key in ("don_gia", "gia_von", "che_ban_don_gia"):
        assert gia_key not in blob, f"Lộ trường giá '{gia_key}' xuống drawer kỹ thuật"
    for gia_val in ("12345", "6789", "54321", "999999"):
        assert gia_val not in blob, f"Lộ GIÁ TRỊ giá '{gia_val}' xuống drawer kỹ thuật"


def test_an_pham_chi_tiet_note_va_so_kem(client):
    """Note kỹ thuật theo sản phẩm xuống drawer + số kẽm suy đúng; phiếu chưa tính → SL = None (không bịa)."""
    h = _headers(client)
    db = SessionLocal()
    try:
        ptg = PhieuTinhGia(ma="PTG-NOTE", ten_san_pham="Hộp", so_luong=500)
        db.add(ptg)
        db.flush()
        ptp = PhieuThanhPhan(
            phieu_id=ptg.id, thu_tu=1, ten="Nắp hộp", so_luong=500,
            quy_cach_in="hai_mat", so_mau_a=4, so_mau_b=2, so_to_per_sp=2,
            ghi_chu_ky_thuat="Canh màu như mẫu · kẽm cũ L203 · bù hao 1%",
        )
        db.add(ptp)
        db.flush()
        ptp_id = ptp.id
        db.commit()
    finally:
        db.close()

    d = client.get(f"/api/lenh-sx/an-pham/{ptp_id}", headers=h).json()
    assert d["ghi_chu_ky_thuat"] == "Canh màu như mẫu · kẽm cũ L203 · bù hao 1%"
    assert d["so_kem"] == 12                 # 2 mặt: (4+2) × 2 tờ/SP
    assert d["so_luong_can"] is None         # phiếu chưa tính snapshot → không bịa số


def test_sua_quy_cach_bai_con_override(client):
    """Kế thừa báo giá làm MẶC ĐỊNH nhưng SỬA được ở lệnh nháp (override per bài con); số kẽm tính lại;
    chặn sửa khi lệnh không còn nháp."""
    h = _headers(client)
    oid, ptps = _seed_multi(order_no="DH-QC-OV", qtys=[500])
    r = client.post(
        "/api/lenh-sx/lenh",
        json={"order_id": oid, "phieu_thanh_phan_ids": ptps}, headers=h,
    )
    assert r.status_code == 201, r.text
    lenh_id = r.json()["id"]

    d = client.get(f"/api/lenh-sx/lenh/{lenh_id}", headers=h).json()
    item_id = d["items"][0]["id"]
    assert item_id is not None

    # drawer mở từ LỆNH NHÁP → editable, chưa override gì
    dt = client.get(f"/api/lenh-sx/an-pham/{ptps[0]}?lenh_item_id={item_id}", headers=h).json()
    assert dt["editable"] is True
    assert dt["overridden"] == []

    # SỬA quy cách in: 2 mặt · 4/4 màu · số con 8
    put = client.put(
        f"/api/lenh-sx/bai-con/{item_id}/quy-cach",
        json={"so_mau_a": 4, "so_mau_b": 4, "quy_cach_in": "hai_mat", "so_con": 8}, headers=h,
    )
    assert put.status_code == 200, put.text
    e = put.json()
    assert e["so_mau_a"] == 4 and e["so_mau_b"] == 4 and e["quy_cach_in"] == "hai_mat"
    assert e["so_con"] == 8
    assert e["so_kem"] == 8                                   # 2 mặt: (4+4) × 1 tờ/SP
    assert set(e["overridden"]) >= {"so_mau_a", "so_mau_b", "quy_cach_in", "so_con"}

    # giá trị hiệu lực GIỮ khi đọc lại (không đụng báo giá)
    again = client.get(f"/api/lenh-sx/an-pham/{ptps[0]}?lenh_item_id={item_id}", headers=h).json()
    assert again["so_con"] == 8 and again["so_kem"] == 8

    # đọc THUẦN báo giá (không kèm lenh_item_id) → KHÔNG dính override + không editable
    goc = client.get(f"/api/lenh-sx/an-pham/{ptps[0]}", headers=h).json()
    assert goc["editable"] is False and goc["overridden"] == []

    # Lệnh hủy → không còn nháp → sửa quy cách bị chặn 409
    assert client.post(f"/api/lenh-sx/lenh/{lenh_id}/huy", headers=h).status_code == 200
    blocked = client.put(
        f"/api/lenh-sx/bai-con/{item_id}/quy-cach", json={"so_con": 2}, headers=h,
    )
    assert blocked.status_code == 409, blocked.text


def test_an_pham_chi_tiet_404_khi_khong_ton_tai(client):
    h = _headers(client)
    r = client.get("/api/lenh-sx/an-pham/987654", headers=h)
    assert r.status_code == 404, r.text


# ============================================================ ① Hạn giao + ② routing copy
def test_lenh_ke_thua_han_giao_khach_luc_bung(client):
    """① Hạn KHÁCH của lệnh = snapshot `Order.delivery_committed_date` lúc bung (chảy vào thuộc tính lệnh)."""
    h = _headers(client)
    han = date(2026, 8, 15)
    oid, ptps = _seed_multi(order_no="DH-HAN-KT", qtys=[300], delivery_committed_date=han)
    r = client.post(
        "/api/lenh-sx/lenh",
        json={"order_id": oid, "phieu_thanh_phan_ids": ptps}, headers=h,
    )
    assert r.status_code == 201, r.text
    assert r.json()["han_giao_khach"] == "2026-08-15"   # kế thừa đơn
    assert r.json()["han_giao_noi_bo"] is None          # nội bộ để planner nhập
    d = client.get(f"/api/lenh-sx/lenh/{r.json()['id']}", headers=h).json()
    assert d["han_giao_khach"] == "2026-08-15"          # chảy vào detail


def test_routing_copy_giu_ghi_chu_va_quy_cach(client):
    """② `_copy_routing_from_ptp` chép ghi chú kỹ thuật + quy cách BƯỚC (so_mat/so_vi_tri) → tổ hết trơ."""
    h = _headers(client)
    oid, ptps = _seed_multi(order_no="DH-ROUTE-CP", qtys=[500])
    db = SessionLocal()
    try:
        # 2 công đoạn finishing gắn vào ấn phẩm đại diện, có ghi chú + quy cách.
        db.add(PhieuThanhPham(
            thanh_phan_id=ptps[0], thu_tu=1, cong_doan_id=None, ten="Cán màng",
            so_mat=2, ghi_chu="cán mờ",
        ))
        db.add(PhieuThanhPham(
            thanh_phan_id=ptps[0], thu_tu=2, cong_doan_id=None, ten="Ép kim",
            so_vi_tri=3, nha_cung_cap="Xưởng ngoài B",
        ))
        db.commit()
    finally:
        db.close()

    r = client.post(
        "/api/lenh-sx/lenh",
        json={"order_id": oid, "phieu_thanh_phan_ids": ptps}, headers=h,
    )
    assert r.status_code == 201, r.text
    routing = client.get(f"/api/lenh-sx/lenh/{r.json()['id']}", headers=h).json()["routing"]
    assert len(routing) == 2
    can, ep = routing[0], routing[1]
    assert can["ghi_chu"] == "cán mờ" and can["quy_cach"] == "2 mặt"
    assert ep["quy_cach"] == "3 vị trí · thuê ngoài"       # so_vi_tri + thuê ngoài


def test_sua_han_giao_nhap_ok_sau_phat_khoa_409(client):
    """① Sửa hạn khi NHÁP OK; đóng băng sau phát → 409 (chưa có ô quyền đổi-hạn sau phát)."""
    h = _headers(client)
    oid, ptps = _seed_multi(order_no="DH-HAN-EDIT", qtys=[200])
    lenh_id = client.post(
        "/api/lenh-sx/lenh",
        json={"order_id": oid, "phieu_thanh_phan_ids": ptps}, headers=h,
    ).json()["id"]

    # NHÁP: set cả 2 hạn OK
    ok = client.put(
        f"/api/lenh-sx/lenh/{lenh_id}/han-giao",
        json={"han_giao_khach": "2026-09-01", "han_giao_noi_bo": "2026-08-28"}, headers=h,
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["han_giao_khach"] == "2026-09-01"
    assert ok.json()["han_giao_noi_bo"] == "2026-08-28"

    # đóng băng: đưa lệnh sang dang_chay (mô phỏng đã phát) → sửa hạn bị chặn 409
    db = SessionLocal()
    try:
        db.get(LenhSanXuat, lenh_id).trang_thai = LENH_DANG_CHAY
        db.commit()
    finally:
        db.close()
    blocked = client.put(
        f"/api/lenh-sx/lenh/{lenh_id}/han-giao",
        json={"han_giao_noi_bo": "2026-08-20"}, headers=h,
    )
    assert blocked.status_code == 409, blocked.text


# ============================================================ ③ Khuôn bế + ④ Lịch chạy
def test_gan_khuon_be_va_can_khuon(client):
    """③ Lệnh có công đoạn BẾ → `can_khuon`=True; gán khuôn từ danh mục → detail hiện khuôn (mã · tên)."""
    h = _headers(client)
    oid, ptps = _seed_multi(order_no="DH-KHUON", qtys=[500])
    db = SessionLocal()
    try:
        cd = CongDoan(ma="CD-BE-T", ten="Bế", nhom="finishing", tooling_type="khuon_be")
        db.add(cd)
        db.flush()
        db.add(PhieuThanhPham(thanh_phan_id=ptps[0], thu_tu=1, cong_doan_id=cd.id, ten="Bế"))
        kb = KhuonBe(ma="KB-T01", ten="Khuôn hộp test", so_ke="A1")
        db.add(kb)
        db.commit()
        kb_id = kb.id
    finally:
        db.close()

    lenh_id = client.post(
        "/api/lenh-sx/lenh", json={"order_id": oid, "phieu_thanh_phan_ids": ptps}, headers=h,
    ).json()["id"]

    d = client.get(f"/api/lenh-sx/lenh/{lenh_id}", headers=h).json()
    assert d["can_khuon"] is True                 # có bước bế → cần khuôn
    assert d["khuon_be_id"] is None and d["khuon_be_label"] is None

    r = client.put(f"/api/lenh-sx/lenh/{lenh_id}/khuon", json={"khuon_be_id": kb_id}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["khuon_be_id"] == kb_id
    d2 = client.get(f"/api/lenh-sx/lenh/{lenh_id}", headers=h).json()
    assert d2["khuon_be_id"] == kb_id
    assert d2["khuon_be_label"] == "KB-T01 · Khuôn hộp test"

    # gán khuôn không tồn tại → 422
    assert client.put(
        f"/api/lenh-sx/lenh/{lenh_id}/khuon", json={"khuon_be_id": 999999}, headers=h,
    ).status_code == 422


def test_lich_chay_xep_va_reorder(client):
    """④ Xếp lệnh vào ô (máy, ngày, thứ tự) → lich-chay phản ánh; reorder set lại `thu_tu_chay`."""
    h = _headers(client)
    oid, ptps = _seed_multi(order_no="DH-LICH", qtys=[100, 200])
    a = client.post("/api/lenh-sx/lenh", json={"order_id": oid, "phieu_thanh_phan_ids": [ptps[0]]}, headers=h).json()["id"]
    b = client.post("/api/lenh-sx/lenh", json={"order_id": oid, "phieu_thanh_phan_ids": [ptps[1]]}, headers=h).json()["id"]

    # xếp lệnh a vào máy 7, ngày 2026-08-01, thứ tự 1
    r = client.put(
        f"/api/lenh-sx/lenh/{a}/lich-chay",
        json={"may_id": 7, "ngay_chay": "2026-08-01", "thu_tu_chay": 1}, headers=h,
    )
    assert r.status_code == 200, r.text

    rows = {x["lenh_id"]: x for x in client.get("/api/lenh-sx/lich-chay", headers=h).json()}
    assert a in rows and b in rows                 # cả 2 lệnh mở đều liệt kê
    assert rows[a]["may_id"] == 7 and rows[a]["ngay_chay"] == "2026-08-01" and rows[a]["thu_tu_chay"] == 1
    assert rows[b]["ngay_chay"] is None            # chưa xếp → khay "Chưa xếp"

    # reorder trong ô: b trước a → thu_tu_chay b=1, a=2
    assert client.post("/api/lenh-sx/lich-chay/reorder", json={"lenh_ids": [b, a]}, headers=h).status_code == 200
    rows2 = {x["lenh_id"]: x for x in client.get("/api/lenh-sx/lich-chay", headers=h).json()}
    assert rows2[b]["thu_tu_chay"] == 1 and rows2[a]["thu_tu_chay"] == 2
