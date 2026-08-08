"""Đề nghị kho → phiếu nhập/xuất → lô & giá vốn — VERIFY THẬT (spec-kho-de-nghi).

Kiểm đúng những luật mà spec hứa, bằng HTTP thật chứ không gọi service trực tiếp:

  §5  Mọi phiếu phải ứng theo đề nghị ĐÃ DUYỆT; không cho ứng vượt số duyệt.
  §6  Mỗi lần nhập = 1 lô riêng, giá riêng; xuất đích danh ăn nhiều lô = nhiều giá vốn.
  §7  Ba ngưỡng → 5 mức tồn.
  §9  Người đề nghị KHÔNG thấy tồn/giá; thủ kho KHÔNG duyệt; kho KHÔNG thấy giá vốn.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.models.don_vi_do import DonViDo, DonViQuyDoi
from app.models.role import SCOPE_ALL, SCOPE_OWN
from app.models.vat_lieu_kho import VatTuInAn
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import hash_password

PW = "pw123456"


def _admin(client) -> dict[str, str]:
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _login(client, username: str) -> dict[str, str]:
    r = client.post("/api/auth/login", json={"username": username, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _mk_user(username: str, dept_name: str, perms: dict) -> int:
    """1 user + 1 vai trò mang đúng ô quyền `kho` cần test."""
    db = SessionLocal()
    try:
        depts, roles, users = DepartmentRepository(db), RoleRepository(db), UserRepository(db)
        dept = depts.get_by_name(dept_name) or depts.create(name=dept_name)
        role = roles.get_by_name_and_department(f"Vai {username}", dept.id) or roles.create(
            name=f"Vai {username}", department_id=dept.id
        )
        roles.set_permission(role_id=role.id, module_key="kho", **perms)
        u = users.create(username=username, name=username, password_hash=hash_password(PW))
        users.set_assignment(u, department_id=dept.id, role_id=role.id, is_active=True)
        return u.id
    finally:
        db.close()


def _mk_material(code: str) -> tuple[str, int]:
    """1 mặt hàng trong DANH MỤC GỐC (Vật tư khác) + đơn vị `to` để quy đổi chạy được.

    Kho không còn sổ hàng riêng (`materials`) từ mg 0171 — mọi thứ nhập kho phải có sẵn ở đây.
    Trả CẶP `(hang_loai, hang_id)` vì hai danh mục có hai dãy id riêng.
    """
    db = SessionLocal()
    try:
        if db.query(DonViDo).filter(DonViDo.ma == "to").first() is None:
            to = DonViDo(ma="to", ten="tờ", ho="to")
            ram = DonViDo(ma="ram", ten="ram", ho="to")
            db.add_all([to, ram])
            db.flush()
            # 1 ram = 500 tờ — cặp SỐ CỐ ĐỊNH, không cần khổ giấy nên luôn chạy được.
            db.add(DonViQuyDoi(tu_id=ram.id, den_id=to.id, he_so=500))
        m = db.query(VatTuInAn).filter(VatTuInAn.ma == code).first()
        if m is None:
            m = VatTuInAn(ma=code, ten=f"Vật tư {code}", don_vi_gia="to")
            db.add(m)
        db.commit()
        return ("vat_tu", m.id)
    finally:
        db.close()


def _mk_kho(client, headers) -> int:
    r = client.post("/api/kho", json={"ten": "Kho NVL"}, headers=headers)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _setup(client):
    """Bộ nhân vật tối thiểu: người đề nghị · người duyệt · thủ kho · kế toán."""
    admin = _admin(client)
    kho_id = _mk_kho(client, admin)
    mat_id = _mk_material("GY-KHO-1")

    _mk_user("t_denghi", "Sản xuất", dict(
        can_read=True, scope=SCOPE_OWN, can_request=True))
    _mk_user("t_duyet", "Sản xuất", dict(
        can_read=True, scope=SCOPE_OWN, can_request=True, can_approve=True))
    # Thủ kho (ở đây là vai kho ĐẦY ĐỦ cho các test lô/giá): lập phiếu + GHI SỔ + xem tồn,
    # KHÔNG duyệt, KHÔNG xem giá vốn. (SoD create≠post kiểm ở test riêng bên dưới.)
    _mk_user("t_thukho", "Kho", dict(
        can_read=True, can_create=True, can_post=True, scope=SCOPE_ALL, can_view_stock=True,
        can_set_threshold=True))
    # Chỉ LẬP phiếu, KHÔNG ghi sổ — dùng để kiểm SoD (create không kèm post).
    _mk_user("t_lapphieu", "Kho", dict(
        can_read=True, can_create=True, scope=SCOPE_ALL, can_view_stock=True))
    # Kế toán kho: GHI SỔ (can_post) + duyệt + thấy giá vốn, KHÔNG lập phiếu (SoD như seed thật).
    _mk_user("t_ketoan", "Kế toán", dict(
        can_read=True, scope=SCOPE_ALL, can_approve=True, can_post=True, can_view_stock=True,
        can_view_cost=True))
    return kho_id, mat_id


def _approved_request(client, *, kho_id: int, loai: str, mat_id: int, qty: float,
                      gia: int | None = None) -> dict:
    """Tạo đề nghị → trình → duyệt. Trả JSON đề nghị đã duyệt.
    `gia` = đơn giá NHẬP người đề nghị khai (phiếu kế thừa; kho không sửa)."""
    dn = _login(client, "t_denghi")
    line = {"hang_loai": mat_id[0], "hang_id": mat_id[1], "dvt": "to", "sl_de_nghi": qty}
    if gia is not None:
        line["don_gia"] = gia
    r = client.post("/api/kho/de-nghi", headers=dn, json={
        "loai": loai, "kho_id": kho_id, "lines": [line],
    })
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    assert client.post(f"/api/kho/de-nghi/{rid}/trinh-duyet", headers=dn).status_code == 200
    duyet = _login(client, "t_duyet")
    r = client.post(f"/api/kho/de-nghi/{rid}/duyet", headers=duyet, json={})
    assert r.status_code == 200, r.text
    return r.json()


def _nhap(client, *, kho_id: int, mat_id: int, qty: float, gia: int) -> dict:
    """Một lượt nhập trọn vẹn: đề nghị → duyệt → phiếu → ghi sổ. Trả phiếu đã ghi sổ."""
    # Giá khai Ở ĐỀ NGHỊ (người đề nghị); phiếu KHÔNG gửi giá — kho không sửa, kế thừa từ đề nghị.
    req = _approved_request(client, kho_id=kho_id, loai="NHAP", mat_id=mat_id, qty=qty, gia=gia)
    tk = _login(client, "t_thukho")
    r = client.post("/api/kho/phieu", headers=tk, json={
        "request_id": req["id"], "kho_id": kho_id,
        "lines": [{"request_line_id": req["lines"][0]["id"], "so_luong": qty}],
    })
    assert r.status_code == 201, r.text
    vid = r.json()["id"]
    r = client.post(f"/api/kho/phieu/{vid}/ghi-so", headers=tk)
    assert r.status_code == 200, r.text
    return r.json()


# --- §5 Phiếu phải ứng theo đề nghị ------------------------------------------

def test_khong_co_de_nghi_duyet_thi_khong_lap_duoc_phieu(client):
    kho_id, mat_id = _setup(client)
    dn = _login(client, "t_denghi")
    r = client.post("/api/kho/de-nghi", headers=dn, json={
        "loai": "NHAP", "kho_id": kho_id, "lines": [{"hang_loai": mat_id[0], "hang_id": mat_id[1], "dvt": "to", "sl_de_nghi": 10}],
    })
    req = r.json()  # còn ở trạng thái Nháp, CHƯA duyệt

    tk = _login(client, "t_thukho")
    r = client.post("/api/kho/phieu", headers=tk, json={
        "request_id": req["id"], "kho_id": kho_id,
        "lines": [{"request_line_id": req["lines"][0]["id"], "so_luong": 10, "don_gia": 1000}],
    })
    assert r.status_code == 400
    assert "đã duyệt" in r.json()["detail"]


def test_khong_cho_ung_vuot_so_da_duyet(client):
    kho_id, mat_id = _setup(client)
    req = _approved_request(client, kho_id=kho_id, loai="NHAP", mat_id=mat_id, qty=10)
    tk = _login(client, "t_thukho")
    r = client.post("/api/kho/phieu", headers=tk, json={
        "request_id": req["id"], "kho_id": kho_id,
        "lines": [{"request_line_id": req["lines"][0]["id"], "so_luong": 11, "don_gia": 1000}],
    })
    assert r.status_code == 400
    assert "vượt số đã duyệt" in r.json()["detail"]


def test_duyet_cat_bot_so_luong_thi_chan_theo_so_duyet(client):
    """Duyệt 8/10 → ứng 9 phải bị chặn (chặn theo SL DUYỆT, không phải SL đề nghị)."""
    kho_id, mat_id = _setup(client)
    dn = _login(client, "t_denghi")
    r = client.post("/api/kho/de-nghi", headers=dn, json={
        "loai": "NHAP", "kho_id": kho_id, "lines": [{"hang_loai": mat_id[0], "hang_id": mat_id[1], "dvt": "to", "sl_de_nghi": 10}],
    })
    req = r.json()
    line_id = req["lines"][0]["id"]
    client.post(f"/api/kho/de-nghi/{req['id']}/trinh-duyet", headers=dn)
    duyet = _login(client, "t_duyet")
    r = client.post(f"/api/kho/de-nghi/{req['id']}/duyet", headers=duyet,
                    json={"approved_qty": {str(line_id): 8}})
    assert r.status_code == 200, r.text
    assert r.json()["lines"][0]["sl_duyet"] == 8

    tk = _login(client, "t_thukho")
    r = client.post("/api/kho/phieu", headers=tk, json={
        "request_id": req["id"], "kho_id": kho_id,
        "lines": [{"request_line_id": line_id, "so_luong": 9, "don_gia": 1000}],
    })
    assert r.status_code == 400


def test_khong_duyet_vuot_so_de_nghi(client):
    kho_id, mat_id = _setup(client)
    dn = _login(client, "t_denghi")
    r = client.post("/api/kho/de-nghi", headers=dn, json={
        "loai": "XUAT", "kho_id": kho_id, "lines": [{"hang_loai": mat_id[0], "hang_id": mat_id[1], "dvt": "to", "sl_de_nghi": 5}],
    })
    req = r.json()
    client.post(f"/api/kho/de-nghi/{req['id']}/trinh-duyet", headers=dn)
    duyet = _login(client, "t_duyet")
    r = client.post(f"/api/kho/de-nghi/{req['id']}/duyet", headers=duyet,
                    json={"approved_qty": {str(req["lines"][0]["id"]): 99}})
    assert r.status_code == 400
    assert "vượt số lượng đề nghị" in r.json()["detail"]


def test_khong_tu_duyet_de_nghi_cua_minh(client):
    """SoD: người tạo không tự duyệt, kể cả khi vai có `can_approve`."""
    kho_id, mat_id = _setup(client)
    duyet = _login(client, "t_duyet")
    r = client.post("/api/kho/de-nghi", headers=duyet, json={
        "loai": "XUAT", "kho_id": kho_id, "lines": [{"hang_loai": mat_id[0], "hang_id": mat_id[1], "dvt": "to", "sl_de_nghi": 3}],
    })
    req = r.json()
    client.post(f"/api/kho/de-nghi/{req['id']}/trinh-duyet", headers=duyet)
    r = client.post(f"/api/kho/de-nghi/{req['id']}/duyet", headers=duyet, json={})
    assert r.status_code == 400
    assert "tự duyệt" in r.json()["detail"]


# --- §6 Lô & giá đích danh ----------------------------------------------------

def test_moi_lan_nhap_tao_lo_rieng_voi_gia_rieng(client):
    """Kịch bản trong spec: nhập đợt 1 giá 100k, đợt 2 giá 200k → 2 lô, 2 giá."""
    kho_id, mat_id = _setup(client)
    _nhap(client, kho_id=kho_id, mat_id=mat_id, qty=10, gia=100_000)
    _nhap(client, kho_id=kho_id, mat_id=mat_id, qty=10, gia=200_000)

    kt = _login(client, "t_ketoan")
    r = client.get("/api/kho/phieu/lo/danh-sach",
                   params={"hang_loai": mat_id[0], "hang_id": mat_id[1], "kho_id": kho_id}, headers=kt)
    assert r.status_code == 200, r.text
    lots = r.json()
    assert len(lots) == 2
    assert sorted(x["don_gia_nhap"] for x in lots) == [100_000, 200_000]
    assert all(x["sl_con_lai"] == 10 for x in lots)


def test_xuat_an_nhieu_lo_thi_gia_von_tinh_dich_danh(client):
    """Xuất 15 = 10 (lô 100k) + 5 (lô 200k) → giá vốn 2.000.000, không phải giá bình quân."""
    kho_id, mat_id = _setup(client)
    _nhap(client, kho_id=kho_id, mat_id=mat_id, qty=10, gia=100_000)
    _nhap(client, kho_id=kho_id, mat_id=mat_id, qty=10, gia=200_000)

    req = _approved_request(client, kho_id=kho_id, loai="XUAT", mat_id=mat_id, qty=15)
    line_id = req["lines"][0]["id"]
    tk = _login(client, "t_thukho")

    # Gợi ý phân bổ FEFO→FIFO: lô nhập trước đi trước.
    r = client.get("/api/kho/phieu/lo/goi-y", headers=tk,
                   params={"hang_loai": mat_id[0], "hang_id": mat_id[1], "kho_id": kho_id, "so_luong": 15})
    assert r.status_code == 200, r.text
    alloc = r.json()
    assert alloc["thieu"] == 0
    assert [x["so_luong"] for x in alloc["lines"]] == [10, 5]
    # Thủ kho KHÔNG có can_view_cost → gợi ý không kèm giá.
    assert all(x["don_gia_nhap"] is None for x in alloc["lines"])

    r = client.post("/api/kho/phieu", headers=tk, json={
        "request_id": req["id"], "kho_id": kho_id,
        "lines": [
            {"request_line_id": line_id, "so_luong": x["so_luong"], "lot_id": x["lot_id"]}
            for x in alloc["lines"]
        ],
    })
    assert r.status_code == 201, r.text
    vid = r.json()["id"]
    assert client.post(f"/api/kho/phieu/{vid}/ghi-so", headers=tk).status_code == 200

    kt = _login(client, "t_ketoan")
    v = client.get(f"/api/kho/phieu/{vid}", headers=kt).json()
    assert v["gia_von"] == 10 * 100_000 + 5 * 200_000

    # Tồn còn đúng 5 (lô 200k), lô 100k đã rỗng.
    lots = client.get("/api/kho/phieu/lo/danh-sach", headers=kt,
                      params={"hang_loai": mat_id[0], "hang_id": mat_id[1], "kho_id": kho_id}).json()
    assert sum(x["sl_con_lai"] for x in lots) == 5


def test_khong_cho_xuat_am_kho(client):
    """BRD §1.5: không xuất âm. Xuất quá tồn của lô → 400, tồn không đổi."""
    kho_id, mat_id = _setup(client)
    _nhap(client, kho_id=kho_id, mat_id=mat_id, qty=5, gia=100_000)
    req = _approved_request(client, kho_id=kho_id, loai="XUAT", mat_id=mat_id, qty=10)
    tk = _login(client, "t_thukho")
    lot_id = client.get("/api/kho/phieu/lo/danh-sach", headers=tk,
                        params={"hang_loai": mat_id[0], "hang_id": mat_id[1], "kho_id": kho_id}).json()[0]["id"]
    r = client.post("/api/kho/phieu", headers=tk, json={
        "request_id": req["id"], "kho_id": kho_id,
        "lines": [{"request_line_id": req["lines"][0]["id"], "so_luong": 10, "lot_id": lot_id}],
    })
    assert r.status_code == 201, r.text  # lập phiếu nháp thì được
    r = client.post(f"/api/kho/phieu/{r.json()['id']}/ghi-so", headers=tk)
    assert r.status_code == 400  # ghi sổ mới chặn
    assert "không đủ" in r.json()["detail"]


def test_phieu_nhap_ung_dan_lam_nhieu_dot(client):
    """1 đề nghị ↔ nhiều phiếu: ứng 6 rồi 4 → Đã cấp một phần → Hoàn tất."""
    kho_id, mat_id = _setup(client)
    req = _approved_request(client, kho_id=kho_id, loai="NHAP", mat_id=mat_id, qty=10)
    line_id = req["lines"][0]["id"]
    tk = _login(client, "t_thukho")

    for qty, mong_doi in ((6, "partial"), (4, "done")):
        # Đợt 1 cấp 6/10 = THIẾU → phải kèm lý do; đợt 2 cấp 4/4 = đủ, không cần.
        r = client.post("/api/kho/phieu", headers=tk, json={
            "request_id": req["id"], "kho_id": kho_id,
            "lines": [{"request_line_id": line_id, "so_luong": qty, "don_gia": 1000,
                       "ly_do": "NCC giao đợt 1 thiếu" if qty < 10 else None}],
        })
        assert r.status_code == 201, r.text
        assert client.post(f"/api/kho/phieu/{r.json()['id']}/ghi-so", headers=tk).status_code == 200
        got = client.get(f"/api/kho/de-nghi/{req['id']}", headers=tk).json()
        assert got["trang_thai"] == mong_doi

    # Ứng đủ rồi thì phiếu thứ 3 phải bị chặn.
    r = client.post("/api/kho/phieu", headers=tk, json={
        "request_id": req["id"], "kho_id": kho_id,
        "lines": [{"request_line_id": line_id, "so_luong": 1, "don_gia": 1000}],
    })
    assert r.status_code == 400


# --- §9 Phân quyền ------------------------------------------------------------

def test_nguoi_de_nghi_khong_thay_ton_va_khong_thay_gia(client):
    kho_id, mat_id = _setup(client)
    _nhap(client, kho_id=kho_id, mat_id=mat_id, qty=10, gia=100_000)
    req = _approved_request(client, kho_id=kho_id, loai="XUAT", mat_id=mat_id, qty=3)

    dn = _login(client, "t_denghi")
    got = client.get(f"/api/kho/de-nghi/{req['id']}", headers=dn,
                     params={"kho_id": kho_id}).json()
    line = got["lines"][0]
    # Đèn tín hiệu VẪN có (biết còn/sắp hết) nhưng con số tồn thì KHÔNG.
    assert line["muc_ton"] is not None
    assert line["ton_kha_dung"] is None


def test_thu_kho_thay_ton_nhung_khong_thay_gia_von(client):
    kho_id, mat_id = _setup(client)
    v = _nhap(client, kho_id=kho_id, mat_id=mat_id, qty=10, gia=100_000)
    tk = _login(client, "t_thukho")

    got = client.get(f"/api/kho/phieu/{v['id']}", headers=tk).json()
    assert got["gia_von"] is None
    assert got["lines"][0]["don_gia"] is None
    assert got["lines"][0]["thanh_tien"] is None
    # Nhưng lô thì vẫn chọn được (có mã lô + số còn lại), chỉ thiếu cột giá.
    lots = client.get("/api/kho/phieu/lo/danh-sach", headers=tk,
                      params={"hang_loai": mat_id[0], "hang_id": mat_id[1]}).json()
    assert lots[0]["ma_lo"] and lots[0]["sl_con_lai"] == 10
    assert lots[0]["don_gia_nhap"] is None


def test_thu_kho_khong_duyet_duoc_de_nghi(client):
    """BRD §2.6 b8 — kho tiếp nhận phiếu ĐÃ DUYỆT, kho không phải người duyệt."""
    kho_id, mat_id = _setup(client)
    dn = _login(client, "t_denghi")
    r = client.post("/api/kho/de-nghi", headers=dn, json={
        "loai": "XUAT", "kho_id": kho_id, "lines": [{"hang_loai": mat_id[0], "hang_id": mat_id[1], "dvt": "to", "sl_de_nghi": 2}],
    })
    req = r.json()
    client.post(f"/api/kho/de-nghi/{req['id']}/trinh-duyet", headers=dn)
    tk = _login(client, "t_thukho")
    r = client.post(f"/api/kho/de-nghi/{req['id']}/duyet", headers=tk, json={})
    assert r.status_code == 403


def test_nguoi_de_nghi_khong_lap_duoc_phieu(client):
    kho_id, mat_id = _setup(client)
    req = _approved_request(client, kho_id=kho_id, loai="NHAP", mat_id=mat_id, qty=5)
    dn = _login(client, "t_denghi")
    r = client.post("/api/kho/phieu", headers=dn, json={
        "request_id": req["id"], "kho_id": kho_id,
        "lines": [{"request_line_id": req["lines"][0]["id"], "so_luong": 5, "don_gia": 1000}],
    })
    assert r.status_code == 403


def test_nguoi_de_nghi_chi_thay_de_nghi_cua_minh(client):
    """Scope `own` — đây là cách người đề nghị bị chặn khỏi dữ liệu kho."""
    kho_id, mat_id = _setup(client)
    _approved_request(client, kho_id=kho_id, loai="XUAT", mat_id=mat_id, qty=2)  # của t_denghi

    duyet = _login(client, "t_duyet")
    r = client.post("/api/kho/de-nghi", headers=duyet, json={
        "loai": "XUAT", "kho_id": kho_id, "lines": [{"hang_loai": mat_id[0], "hang_id": mat_id[1], "dvt": "to", "sl_de_nghi": 7}],
    })
    assert r.status_code == 201

    dn = _login(client, "t_denghi")
    items = client.get("/api/kho/de-nghi", headers=dn).json()["items"]
    assert all(x["nguoi_tao_ten"] == "t_denghi" for x in items)
    # Thủ kho (scope all) thì thấy cả hai.
    tk = _login(client, "t_thukho")
    assert client.get("/api/kho/de-nghi", headers=tk).json()["total"] >= 2


# --- §7 Ngưỡng tồn -------------------------------------------------------------

def test_nguong_ton_doi_mau_den_tin_hieu(client):
    kho_id, mat_id = _setup(client)
    _nhap(client, kho_id=kho_id, mat_id=mat_id, qty=10, gia=100_000)
    tk = _login(client, "t_thukho")
    r = client.put("/api/kho/nguong-ton", headers=tk, json={
        "hang_loai": mat_id[0], "hang_id": mat_id[1], "kho_id": kho_id,
        "nguong_ton": 12, "nguong_can_ton": 20,
    })
    assert r.status_code == 200, r.text

    req = _approved_request(client, kho_id=kho_id, loai="XUAT", mat_id=mat_id, qty=1)
    got = client.get(f"/api/kho/de-nghi/{req['id']}", headers=tk,
                     params={"kho_id": kho_id}).json()
    # Tồn 10 ≤ ngưỡng tồn 12 → 🟠 cần mua gấp.
    assert got["lines"][0]["muc_ton"] == "can_mua"


def test_nguong_can_ton_phai_lon_hon_nguong_ton(client):
    kho_id, mat_id = _setup(client)
    tk = _login(client, "t_thukho")
    r = client.put("/api/kho/nguong-ton", headers=tk, json={
        "hang_loai": mat_id[0], "hang_id": mat_id[1], "kho_id": kho_id, "nguong_ton": 50, "nguong_can_ton": 10,
    })
    assert r.status_code == 400


def test_khong_co_quyen_thi_khong_khai_duoc_nguong(client):
    kho_id, mat_id = _setup(client)
    kt = _login(client, "t_ketoan")  # có view_cost nhưng KHÔNG có set_threshold
    r = client.put("/api/kho/nguong-ton", headers=kt, json={
        "hang_loai": mat_id[0], "hang_id": mat_id[1], "kho_id": kho_id, "nguong_ton": 5,
    })
    assert r.status_code == 403


# --- SoD & trạng thái đề nghị theo phiếu (spec §5, §9.2) ----------------------

def test_lap_phieu_can_post_moi_ghi_so_duoc(client):
    """SoD create ≠ post: vai chỉ `create` lập được phiếu NHÁP nhưng KHÔNG ghi sổ; vai có `post`
    (Kế toán kho) mới ghi sổ (chốt tồn)."""
    kho_id, mat_id = _setup(client)
    req = _approved_request(client, kho_id=kho_id, loai="NHAP", mat_id=mat_id, qty=10)
    lp = _login(client, "t_lapphieu")  # có create, KHÔNG post
    r = client.post("/api/kho/phieu", headers=lp, json={
        "request_id": req["id"], "kho_id": kho_id,
        "lines": [{"request_line_id": req["lines"][0]["id"], "so_luong": 10, "don_gia": 1000}],
    })
    assert r.status_code == 201, r.text  # lập nháp OK
    vid = r.json()["id"]
    assert client.post(f"/api/kho/phieu/{vid}/ghi-so", headers=lp).status_code == 403  # thiếu post
    kt = _login(client, "t_ketoan")  # có post
    assert client.post(f"/api/kho/phieu/{vid}/ghi-so", headers=kt).status_code == 200


def test_lap_phieu_day_de_nghi_ra_khoi_can_cap(client):
    """Lập phiếu (nháp) → đề nghị rời 'Cần cấp' (approved) sang 'Đang chuẩn bị' (preparing);
    hủy phiếu nháp (BẮT BUỘC lý do) → đề nghị 'Đã hủy' (cancelled) KẾT THÚC + lưu lý do."""
    kho_id, mat_id = _setup(client)
    req = _approved_request(client, kho_id=kho_id, loai="NHAP", mat_id=mat_id, qty=10)
    assert req["trang_thai"] == "approved"
    tk = _login(client, "t_thukho")
    r = client.post("/api/kho/phieu", headers=tk, json={
        "request_id": req["id"], "kho_id": kho_id,
        "lines": [{"request_line_id": req["lines"][0]["id"], "so_luong": 10, "don_gia": 1000}],
    })
    vid = r.json()["id"]

    def _req():
        return client.get(f"/api/kho/de-nghi/{req['id']}", headers=tk).json()

    assert _req()["trang_thai"] == "preparing"  # đã lập phiếu → rời 'Cần cấp'
    # Hủy phiếu BẮT BUỘC lý do — thiếu lý do thì 422.
    assert client.post(f"/api/kho/phieu/{vid}/huy", headers=tk).status_code == 422
    r = client.post(f"/api/kho/phieu/{vid}/huy", headers=tk, json={"ly_do": "Hết hàng, không cấp"})
    assert r.status_code == 200, r.text
    got = _req()
    assert got["trang_thai"] == "cancelled"           # hủy phiếu nháp → đề nghị 'Đã hủy' (kết thúc)
    assert got["ly_do_huy"] == "Hết hàng, không cấp"   # lý do lưu ở đề nghị


def test_cap_thieu_bat_buoc_ly_do_va_hien_o_de_nghi(client):
    """Cấp/nhập ÍT HƠN còn phải cấp → phải nhập LÝ DO; lý do ghi vào đề nghị (kho phản hồi)."""
    kho_id, mat_id = _setup(client)
    req = _approved_request(client, kho_id=kho_id, loai="NHAP", mat_id=mat_id, qty=10)
    line_id = req["lines"][0]["id"]
    tk = _login(client, "t_thukho")
    # Thiếu (7/10) mà KHÔNG có lý do → chặn.
    r = client.post("/api/kho/phieu", headers=tk, json={
        "request_id": req["id"], "kho_id": kho_id,
        "lines": [{"request_line_id": line_id, "so_luong": 7, "don_gia": 1000}],
    })
    assert r.status_code == 400 and "LÝ DO" in r.json()["detail"]
    # Có lý do → OK, và đề nghị trả lại lý do ở dòng.
    r = client.post("/api/kho/phieu", headers=tk, json={
        "request_id": req["id"], "kho_id": kho_id,
        "lines": [{"request_line_id": line_id, "so_luong": 7, "don_gia": 1000,
                   "ly_do": "NCC giao thiếu 3"}],
    })
    assert r.status_code == 201, r.text
    got = client.get(f"/api/kho/de-nghi/{req['id']}", headers=tk).json()
    assert got["lines"][0]["ly_do_thieu"] == "NCC giao thiếu 3"


def test_nhap_theo_don_vi_khac_thi_ton_quy_ve_don_vi_goc(client):
    """Nhập "2 ram" của mặt hàng đếm theo TỜ → lô phải ghi 1.000 tờ, giá quy về đ/tờ.

    Đây là luật xương sống của việc đổi gốc (mg 0171): người ta khai theo đơn vị tiện tay, còn
    tồn kho chỉ có MỘT thang — đơn vị gốc của mặt hàng. Cộng nhầm hai thang là "10 ram + 500 tờ"
    ra một con số vô nghĩa mà không ai thấy dòng lỗi nào.
    """
    kho_id, mat_id = _setup(client)
    dn = _login(client, "t_denghi")
    # 1 ram = 500 tờ (cặp cố định trong `_mk_material`). Giá khai 250.000 đ/ram.
    r = client.post("/api/kho/de-nghi", headers=dn, json={
        "loai": "NHAP", "kho_id": kho_id,
        "lines": [{"hang_loai": mat_id[0], "hang_id": mat_id[1], "dvt": "ram",
                   "sl_de_nghi": 2, "don_gia": 250_000}],
    })
    assert r.status_code == 201, r.text
    body = r.json()
    ln = body["lines"][0]
    # Đề nghị GIỮ đúng con số người ta khai, kèm số đã quy đổi để họ thấy trước cái sẽ vào tồn.
    assert ln["dvt"] == "ram" and ln["sl_de_nghi"] == 2
    assert ln["sl_quy_doi"] == 1000 and ln["don_vi_goc"] == "tờ"
    assert ln["canh_bao_dv"] is None

    rid, line_id = body["id"], ln["id"]
    client.post(f"/api/kho/de-nghi/{rid}/trinh-duyet", headers=dn)
    client.post(f"/api/kho/de-nghi/{rid}/duyet", headers=_login(client, "t_duyet"), json={})
    tk = _login(client, "t_thukho")
    r = client.post("/api/kho/phieu", headers=tk, json={
        "request_id": rid, "kho_id": kho_id,
        "lines": [{"request_line_id": line_id, "so_luong": 2}],
    })
    assert r.status_code == 201, r.text
    vid = r.json()["id"]
    assert client.post(f"/api/kho/phieu/{vid}/ghi-so", headers=tk).status_code == 200

    # LÔ ghi theo đơn vị gốc: 2 ram = 1.000 tờ, và 250.000 đ/ram = 500 đ/tờ.
    kt = _login(client, "t_ketoan")
    lots = client.get(f"/api/kho/phieu/lo/danh-sach?kho_id={kho_id}", headers=kt).json()
    lot = [x for x in lots if x["hang_id"] == mat_id[1]][0]
    assert lot["sl_con_lai"] == 1000
    assert lot["don_gia_nhap"] == 500


def test_don_vi_khong_doi_duoc_thi_chan_ngay_luc_khai(client):
    """Đơn vị ngoài tập đổi được của mặt hàng → CHẶN, kèm lý do nói rõ dùng được đơn vị nào.

    Thà từ chối còn hơn lấy hệ số 1: hệ số 1 sai thì tồn kho sai mà không có dòng lỗi nào.
    """
    kho_id, mat_id = _setup(client)
    dn = _login(client, "t_denghi")
    r = client.post("/api/kho/de-nghi", headers=dn, json={
        "loai": "NHAP", "kho_id": kho_id,
        "lines": [{"hang_loai": mat_id[0], "hang_id": mat_id[1], "dvt": "kg", "sl_de_nghi": 5}],
    })
    assert r.status_code == 400, r.text
    assert "không đổi được" in r.json()["detail"]


def test_khong_con_duong_de_nghi_hang_go_tay(client):
    """SIẾT: bỏ hẳn `ten_tu_do`. Dòng không trỏ mặt hàng trong danh mục thì không lưu được."""
    kho_id, _ = _setup(client)
    dn = _login(client, "t_denghi")
    r = client.post("/api/kho/de-nghi", headers=dn, json={
        "loai": "NHAP", "kho_id": kho_id,
        "lines": [{"ten_tu_do": "Giấy lạ", "dvt": "to", "sl_de_nghi": 10}],
    })
    assert r.status_code == 422, r.text


def test_lich_su_nhap_xuat_theo_vat_tu(client):
    """Popup màn Tồn kho: endpoint lịch-sử tách NHẬP (lô, kể cả đã hết) và XUẤT (dòng phiếu đã
    ghi sổ, đích danh lô); giá vốn ẩn khi thiếu `view_cost`."""
    kho_id, mat_id = _setup(client)
    _nhap(client, kho_id=kho_id, mat_id=mat_id, qty=10, gia=100_000)
    _nhap(client, kho_id=kho_id, mat_id=mat_id, qty=10, gia=200_000)

    # Xuất 15 = 10 (lô 100k) + 5 (lô 200k) → lô 100k rỗng, lô 200k còn 5.
    req = _approved_request(client, kho_id=kho_id, loai="XUAT", mat_id=mat_id, qty=15)
    line_id = req["lines"][0]["id"]
    tk = _login(client, "t_thukho")
    alloc = client.get("/api/kho/phieu/lo/goi-y", headers=tk,
                       params={"hang_loai": mat_id[0], "hang_id": mat_id[1], "kho_id": kho_id, "so_luong": 15}).json()
    r = client.post("/api/kho/phieu", headers=tk, json={
        "request_id": req["id"], "kho_id": kho_id,
        "lines": [
            {"request_line_id": line_id, "so_luong": x["so_luong"], "lot_id": x["lot_id"]}
            for x in alloc["lines"]
        ],
    })
    vid = r.json()["id"]
    assert client.post(f"/api/kho/phieu/{vid}/ghi-so", headers=tk).status_code == 200

    # Kế toán (view_cost) → thấy đủ giá.
    kt = _login(client, "t_ketoan")
    h = client.get(f"/api/kho/phieu/mat-hang/{mat_id[0]}/{mat_id[1]}/lich-su", headers=kt,
                   params={"kho_id": kho_id})
    assert h.status_code == 200, h.text
    data = h.json()
    assert data["on_hand"] == 5
    # NHẬP: 2 lô (giữ cả lô đã xuất hết), mang giá riêng.
    assert len(data["nhap"]) == 2
    assert sorted(l["don_gia_nhap"] for l in data["nhap"]) == [100_000, 200_000]
    assert sorted(l["sl_con_lai"] for l in data["nhap"]) == [0, 5]
    assert all(l["sl_ban_dau"] == 10 for l in data["nhap"])
    # XUẤT: 2 dòng phân bổ, đều trỏ về phiếu xuất + có mã lô + giá vốn đích danh.
    assert len(data["xuat"]) == 2
    assert sorted(x["so_luong"] for x in data["xuat"]) == [5, 10]
    assert all(x["ma_lo"] and x["voucher_id"] == vid for x in data["xuat"])
    assert sorted(x["don_gia"] for x in data["xuat"]) == [100_000, 200_000]

    # Thủ kho (KHÔNG view_cost) → giá bị ẩn cả hai phía (không lọt qua response).
    h2 = client.get(f"/api/kho/phieu/mat-hang/{mat_id[0]}/{mat_id[1]}/lich-su", headers=tk,
                    params={"kho_id": kho_id}).json()
    assert all(l["don_gia_nhap"] is None for l in h2["nhap"])
    assert all(x["don_gia"] is None for x in h2["xuat"])


def test_dinh_kem_hoa_don_vao_phieu(client):
    """Đính kèm hóa đơn/chứng từ (ảnh/PDF) vào phiếu: upload → list → xóa qua HTTP thật."""
    kho_id, mat_id = _setup(client)
    req = _approved_request(client, kho_id=kho_id, loai="NHAP", mat_id=mat_id, qty=10)
    tk = _login(client, "t_thukho")
    r = client.post("/api/kho/phieu", headers=tk, json={
        "request_id": req["id"], "kho_id": kho_id,
        "lines": [{"request_line_id": req["lines"][0]["id"], "so_luong": 10, "don_gia": 1000}],
    })
    vid = r.json()["id"]
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    up = client.post(
        f"/api/kho/phieu/{vid}/attachments", headers=tk,
        files={"file": ("hoadon.png", png, "image/png")},
    )
    assert up.status_code == 201, up.text
    aid = up.json()["id"]
    lst = client.get(f"/api/kho/phieu/{vid}/attachments", headers=tk)
    assert lst.status_code == 200 and len(lst.json()["items"]) == 1
    # Loại file lạ bị chặn.
    bad = client.post(
        f"/api/kho/phieu/{vid}/attachments", headers=tk,
        files={"file": ("virus.exe", b"MZ", "application/x-msdownload")},
    )
    assert bad.status_code == 400
    assert client.delete(f"/api/kho/phieu/{vid}/attachments/{aid}", headers=tk).status_code == 204
