"""Đề nghị kho → phiếu nhập/xuất → lô & giá vốn — VERIFY THẬT (spec-kho-de-nghi).

Kiểm đúng những luật mà spec hứa, bằng HTTP thật chứ không gọi service trực tiếp:

  §5  Mọi phiếu phải ứng theo đề nghị ĐÃ DUYỆT; không cho ứng vượt số duyệt.
  §6  Mỗi lần nhập = 1 lô riêng, giá riêng; xuất đích danh ăn nhiều lô = nhiều giá vốn.
  §7  Ba ngưỡng → 5 mức tồn.
  §9  Người đề nghị KHÔNG thấy tồn/giá; thủ kho KHÔNG duyệt; kho KHÔNG thấy giá vốn.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.models.role import SCOPE_ALL, SCOPE_OWN
from app.models.material import Material
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


def _mk_material(code: str) -> int:
    db = SessionLocal()
    try:
        m = Material(code=code, name=f"Vật tư {code}", material_type="paper", unit="to")
        db.add(m)
        db.commit()
        return m.id
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
    # Vai chỉ có `create` (không post) — sau khi GỘP quyền: vẫn lập + TỰ ghi sổ + hủy được.
    _mk_user("t_lapphieu", "Kho", dict(
        can_read=True, can_create=True, scope=SCOPE_ALL, can_view_stock=True))
    # Kế toán kho: có post + duyệt + thấy giá vốn nhưng KHÔNG create → sau gộp KHÔNG ghi sổ được nữa.
    _mk_user("t_ketoan", "Kế toán", dict(
        can_read=True, scope=SCOPE_ALL, can_approve=True, can_post=True, can_view_stock=True,
        can_view_cost=True))
    return kho_id, mat_id


def _approved_request(client, *, kho_id: int, loai: str, mat_id: int, qty: float,
                      gia: int | None = None) -> dict:
    """Tạo đề nghị — GIỜ tạo là 'approved' NGAY (bỏ bước duyệt). Trả JSON đề nghị đã duyệt.
    `gia` = đơn giá NHẬP người đề nghị khai (phiếu kế thừa; kho không sửa)."""
    dn = _login(client, "t_denghi")
    line = {"material_id": mat_id, "dvt": "to", "sl_de_nghi": qty}
    if gia is not None:
        line["don_gia"] = gia
    r = client.post("/api/kho/de-nghi", headers=dn, json={
        "loai": loai, "kho_id": kho_id, "lines": [line],
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["trang_thai"] == "approved", body
    return body


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


# --- Bỏ bước duyệt: tạo là 'approved' luôn -----------------------------------

def test_tao_de_nghi_la_duyet_luon(client):
    """Chủ 06/08/2026: BỎ bước duyệt. Tạo đề nghị là `approved` NGAY, mỗi dòng `sl_duyet =
    sl_de_nghi`, có người duyệt (= người tạo) + mốc duyệt — kho thấy & cấp được ngay."""
    kho_id, mat_id = _setup(client)
    dn = _login(client, "t_denghi")
    r = client.post("/api/kho/de-nghi", headers=dn, json={
        "loai": "XUAT", "kho_id": kho_id,
        "lines": [{"material_id": mat_id, "dvt": "to", "sl_de_nghi": 12}],
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["trang_thai"] == "approved"
    assert body["lines"][0]["sl_duyet"] == 12
    assert body["nguoi_duyet_ten"] is not None and body["duyet_luc"] is not None


# --- §5 Phiếu phải ứng theo đề nghị ------------------------------------------

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


# Bỏ 3 test cũ theo luồng DUYỆT (duyệt-cắt-số-lượng · không-duyệt-vượt · không-tự-duyệt): tạo đề
# nghị nay là 'approved' nguyên số, không còn endpoint /duyet nên các kịch bản đó không còn tồn tại.


# --- §6 Lô & giá đích danh ----------------------------------------------------

def test_moi_lan_nhap_tao_lo_rieng_voi_gia_rieng(client):
    """Kịch bản trong spec: nhập đợt 1 giá 100k, đợt 2 giá 200k → 2 lô, 2 giá."""
    kho_id, mat_id = _setup(client)
    _nhap(client, kho_id=kho_id, mat_id=mat_id, qty=10, gia=100_000)
    _nhap(client, kho_id=kho_id, mat_id=mat_id, qty=10, gia=200_000)

    kt = _login(client, "t_ketoan")
    r = client.get("/api/kho/phieu/lo/danh-sach",
                   params={"material_id": mat_id, "kho_id": kho_id}, headers=kt)
    assert r.status_code == 200, r.text
    lots = r.json()
    assert len(lots) == 2
    assert sorted(x["don_gia_nhap"] for x in lots) == [100_000, 200_000]
    assert all(x["sl_con_lai"] == 10 for x in lots)


def test_xuat_an_nhieu_lo_thi_gia_von_tinh_dich_danh(client):
    """Xuất 15 = 10 (lô 100k) + 5 (lô 200k). Đích danh TRỪ LÔ giữ nguyên ở DB (tồn còn 5),
    NHƯNG chi tiết phiếu gộp 2 lô lẻ thành 1 dòng/mã với ĐƠN GIÁ BÌNH QUÂN gia quyền."""
    kho_id, mat_id = _setup(client)
    _nhap(client, kho_id=kho_id, mat_id=mat_id, qty=10, gia=100_000)
    _nhap(client, kho_id=kho_id, mat_id=mat_id, qty=10, gia=200_000)

    req = _approved_request(client, kho_id=kho_id, loai="XUAT", mat_id=mat_id, qty=15)
    line_id = req["lines"][0]["id"]
    tk = _login(client, "t_thukho")

    # Gợi ý phân bổ FEFO→FIFO: lô nhập trước đi trước.
    r = client.get("/api/kho/phieu/lo/goi-y", headers=tk,
                   params={"material_id": mat_id, "kho_id": kho_id, "so_luong": 15})
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
    # Chi tiết XUẤT gộp 2 lô lẻ thành 1 dòng/mã (lot_id/ma_lo = None), đơn giá BÌNH QUÂN gia quyền.
    assert len(v["lines"]) == 1
    line = v["lines"][0]
    assert line["so_luong"] == 15
    # DÒNG PHIẾU mang SL đề nghị (đọc-nối từ dòng đề nghị gốc) để đối chiếu đề nghị vs thực xuất.
    assert line["sl_de_nghi"] == 15
    assert line["lot_id"] is None and line["ma_lo"] is None
    # (10×100k + 5×200k)/15 = 133 333 → thành tiền qua đơn giá bình quân = 1 999 995.
    assert line["don_gia"] == 133_333
    assert line["thanh_tien"] == 1_999_995
    assert v["gia_von"] == 1_999_995

    # Tồn còn đúng 5 (lô 200k), lô 100k đã rỗng.
    lots = client.get("/api/kho/phieu/lo/danh-sach", headers=kt,
                      params={"material_id": mat_id, "kho_id": kho_id}).json()
    assert sum(x["sl_con_lai"] for x in lots) == 5


def test_xuat_gop_mot_dong_don_gia_binh_quan(client):
    """1 mã lấy 2 lô GIÁ KHÁC nhau (500@2000 + 500@5000) → chi tiết phiếu XUẤT trả ĐÚNG 1 dòng/mã:
    so_luong=1000, don_gia=3500 (bình quân gia quyền), thanh_tien=3.500.000, lot_id/ma_lo=None."""
    kho_id, mat_id = _setup(client)
    _nhap(client, kho_id=kho_id, mat_id=mat_id, qty=500, gia=2_000)
    _nhap(client, kho_id=kho_id, mat_id=mat_id, qty=500, gia=5_000)

    req = _approved_request(client, kho_id=kho_id, loai="XUAT", mat_id=mat_id, qty=1000)
    line_id = req["lines"][0]["id"]
    tk = _login(client, "t_thukho")
    alloc = client.get("/api/kho/phieu/lo/goi-y", headers=tk,
                       params={"material_id": mat_id, "kho_id": kho_id, "so_luong": 1000}).json()
    assert [x["so_luong"] for x in alloc["lines"]] == [500, 500]  # FEFO: lô 2000 trước, lô 5000 sau
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
    assert len(v["lines"]) == 1
    line = v["lines"][0]
    assert line["so_luong"] == 1000
    assert line["lot_id"] is None and line["ma_lo"] is None
    assert line["don_gia"] == 3_500
    assert line["thanh_tien"] == 3_500_000
    assert v["gia_von"] == 3_500_000


def test_phieu_nhap_dong_mang_sl_de_nghi(client):
    """Nhánh NHẬP của `_serialize`: mỗi DÒNG PHIẾU nhập mang `sl_de_nghi` (đọc-nối từ đề nghị) —
    tách bạch với `so_luong` thực nhận (ở đây nhập thiếu: đề nghị 10, thực nhận 8)."""
    kho_id, mat_id = _setup(client)
    req = _approved_request(client, kho_id=kho_id, loai="NHAP", mat_id=mat_id, qty=10, gia=1_000)
    line_id = req["lines"][0]["id"]
    tk = _login(client, "t_thukho")
    r = client.post("/api/kho/phieu", headers=tk, json={
        "request_id": req["id"], "kho_id": kho_id,
        "lines": [{"request_line_id": line_id, "so_luong": 8, "ly_do": "NCC giao thiếu"}],
    })
    assert r.status_code == 201, r.text
    v = r.json()
    assert v["lines"][0]["sl_de_nghi"] == 10  # số đã XIN
    assert v["lines"][0]["so_luong"] == 8      # số THỰC nhận


def test_khong_cho_xuat_am_kho(client):
    """BRD §1.5: không xuất âm. Xuất quá tồn của lô → 400, tồn không đổi."""
    kho_id, mat_id = _setup(client)
    _nhap(client, kho_id=kho_id, mat_id=mat_id, qty=5, gia=100_000)
    req = _approved_request(client, kho_id=kho_id, loai="XUAT", mat_id=mat_id, qty=10)
    tk = _login(client, "t_thukho")
    lot_id = client.get("/api/kho/phieu/lo/danh-sach", headers=tk,
                        params={"material_id": mat_id, "kho_id": kho_id}).json()[0]["id"]
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
                      params={"material_id": mat_id}).json()
    assert lots[0]["ma_lo"] and lots[0]["sl_con_lai"] == 10
    assert lots[0]["don_gia_nhap"] is None


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
        "loai": "XUAT", "kho_id": kho_id, "lines": [{"material_id": mat_id, "dvt": "to", "sl_de_nghi": 7}],
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
        "material_id": mat_id, "kho_id": kho_id,
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
        "material_id": mat_id, "kho_id": kho_id, "nguong_ton": 50, "nguong_can_ton": 10,
    })
    assert r.status_code == 400


def test_khong_co_quyen_thi_khong_khai_duoc_nguong(client):
    kho_id, mat_id = _setup(client)
    kt = _login(client, "t_ketoan")  # có view_cost nhưng KHÔNG có set_threshold
    r = client.put("/api/kho/nguong-ton", headers=kt, json={
        "material_id": mat_id, "kho_id": kho_id, "nguong_ton": 5,
    })
    assert r.status_code == 403


# --- SoD & trạng thái đề nghị theo phiếu (spec §5, §9.2) ----------------------

def test_lap_phieu_gop_quyen_tu_ghi_so(client):
    """ĐÃ GỘP quyền (bỏ SoD): vai có `create` lập phiếu VÀ tự ghi sổ luôn; vai KHÔNG có `create`
    (vd Kế toán kho chỉ post/duyệt) KHÔNG ghi sổ được nữa — ghi sổ nay gác chính `create`."""
    kho_id, mat_id = _setup(client)
    req = _approved_request(client, kho_id=kho_id, loai="NHAP", mat_id=mat_id, qty=10)
    lp = _login(client, "t_lapphieu")  # có create (không post) → đã gộp nên ghi sổ được luôn
    r = client.post("/api/kho/phieu", headers=lp, json={
        "request_id": req["id"], "kho_id": kho_id,
        "lines": [{"request_line_id": req["lines"][0]["id"], "so_luong": 10, "don_gia": 1000}],
    })
    assert r.status_code == 201, r.text  # lập nháp OK
    vid = r.json()["id"]
    # Vai KHÔNG có create (Kế toán kho: chỉ post/duyệt) không còn ghi sổ được — quyền nay là create.
    kt = _login(client, "t_ketoan")
    assert client.post(f"/api/kho/phieu/{vid}/ghi-so", headers=kt).status_code == 403
    # Chính người lập (có create) tự ghi sổ được — không cần ai khác chốt sổ.
    assert client.post(f"/api/kho/phieu/{vid}/ghi-so", headers=lp).status_code == 200


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


def test_vi_tri_lo_nhap_va_sua(client):
    """Vị trí cất lô: khai ở dòng phiếu NHẬP → ghi sổ CHÉP sang lô; sửa được qua endpoint."""
    kho_id, mat_id = _setup(client)
    req = _approved_request(client, kho_id=kho_id, loai="NHAP", mat_id=mat_id, qty=10)
    tk = _login(client, "t_thukho")
    r = client.post("/api/kho/phieu", headers=tk, json={
        "request_id": req["id"], "kho_id": kho_id,
        "lines": [{"request_line_id": req["lines"][0]["id"], "so_luong": 10,
                   "don_gia": 1000, "vi_tri": "A1-Kệ 3"}],
    })
    assert r.status_code == 201, r.text
    vid = r.json()["id"]
    assert client.post(f"/api/kho/phieu/{vid}/ghi-so", headers=tk).status_code == 200

    def _lots():
        return client.get("/api/kho/phieu/lo/danh-sach", headers=tk,
                          params={"material_id": mat_id, "kho_id": kho_id}).json()

    lot = _lots()[0]
    assert lot["vi_tri"] == "A1-Kệ 3"   # khai lúc NHẬP → chép sang lô khi ghi sổ

    # Sửa vị trí qua endpoint (quyền create — thủ kho cầm hàng).
    r = client.patch(f"/api/kho/phieu/lo/{lot['id']}/vi-tri", headers=tk, json={"vi_tri": "B2-Kệ 5"})
    assert r.status_code == 200, r.text
    assert r.json()["vi_tri"] == "B2-Kệ 5"
    assert _lots()[0]["vi_tri"] == "B2-Kệ 5"


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


def test_quy_doi_va_gia_khai_o_de_nghi_theo_vao_phieu(client):
    """Quy đổi + đơn giá khai Ở ĐỀ NGHỊ (hàng mới) → phiếu KHÔNG khai lại, kho tạo mã kèm quy đổi
    và lô mang đúng giá đề nghị."""
    kho_id, _ = _setup(client)
    dn = _login(client, "t_denghi")
    r = client.post("/api/kho/de-nghi", headers=dn, json={
        "loai": "NHAP", "kho_id": kho_id,
        "lines": [{"ten_tu_do": "Giấy Ream QĐ", "dvt": "to", "sl_de_nghi": 1000,
                   "don_gia": 500, "don_vi_phu": "ream", "he_so_quy_doi": 500}],
    })
    assert r.status_code == 201, r.text
    body = r.json()
    rid, line_id = body["id"], body["lines"][0]["id"]
    # Đề nghị GIỮ lại giá + quy đổi người đề nghị khai.
    assert body["lines"][0]["don_gia"] == 500
    assert body["lines"][0]["don_vi_phu"] == "ream"
    assert float(body["lines"][0]["he_so_quy_doi"]) == 500
    # Đề nghị tạo là 'approved' ngay (bỏ bước duyệt) → kho lập phiếu được luôn.
    assert body["trang_thai"] == "approved"
    # Kho lập phiếu: KHÔNG gửi giá/quy đổi — chỉ SL. Backend lấy hết từ đề nghị.
    tk = _login(client, "t_thukho")
    r = client.post("/api/kho/phieu", headers=tk, json={
        "request_id": rid, "kho_id": kho_id,
        "lines": [{"request_line_id": line_id, "so_luong": 1000}],
    })
    assert r.status_code == 201, r.text
    vid = r.json()["id"]
    assert client.post(f"/api/kho/phieu/{vid}/ghi-so", headers=tk).status_code == 200
    # Mã tự tạo mang đúng QUY ĐỔI khai ở đề nghị (đọc thẳng DB cho chắc).
    db = SessionLocal()
    try:
        m = db.query(Material).filter(Material.name == "Giấy Ream QĐ").first()
        assert m is not None and m.don_vi_phu == "ream" and float(m.he_so_quy_doi) == 500
    finally:
        db.close()
    # Lô mang đúng GIÁ khai ở đề nghị (xem qua vai có view_cost).
    kt = _login(client, "t_ketoan")
    lots = client.get(f"/api/kho/phieu/lo/danh-sach?kho_id={kho_id}", headers=kt).json()
    lot = [x for x in lots if x["material_name"] == "Giấy Ream QĐ"][0]
    assert lot["don_gia_nhap"] == 500


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
                       params={"material_id": mat_id, "kho_id": kho_id, "so_luong": 15}).json()
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
    h = client.get(f"/api/kho/phieu/vat-tu/{mat_id}/lich-su", headers=kt,
                   params={"kho_id": kho_id})
    assert h.status_code == 200, h.text
    data = h.json()
    assert data["on_hand"] == 5
    # NHẬP: 2 lô (giữ cả lô đã xuất hết), mang giá riêng.
    assert len(data["nhap"]) == 2
    assert sorted(l["don_gia_nhap"] for l in data["nhap"]) == [100_000, 200_000]
    assert sorted(l["sl_con_lai"] for l in data["nhap"]) == [0, 5]
    assert all(l["sl_ban_dau"] == 10 for l in data["nhap"])
    # SL đề nghị nối vào từng lô NHẬP (mỗi lô sinh từ đề nghị nhập 10).
    assert all(l["sl_de_nghi"] == 10 for l in data["nhap"])
    # XUẤT: 2 dòng phân bổ, đều trỏ về phiếu xuất + có mã lô + giá vốn đích danh.
    assert len(data["xuat"]) == 2
    assert sorted(x["so_luong"] for x in data["xuat"]) == [5, 10]
    assert all(x["ma_lo"] and x["voucher_id"] == vid for x in data["xuat"])
    assert sorted(x["don_gia"] for x in data["xuat"]) == [100_000, 200_000]
    # SL đề nghị nối vào từng dòng XUẤT (cùng 1 dòng đề nghị xuất 15).
    assert all(x["sl_de_nghi"] == 15 for x in data["xuat"])

    # Thủ kho (KHÔNG view_cost) → giá bị ẩn cả hai phía (không lọt qua response).
    h2 = client.get(f"/api/kho/phieu/vat-tu/{mat_id}/lich-su", headers=tk,
                    params={"kho_id": kho_id}).json()
    assert all(l["don_gia_nhap"] is None for l in h2["nhap"])
    assert all(x["don_gia"] is None for x in h2["xuat"])
    # SL đề nghị KHÔNG phải tiền → vẫn hiện dù thiếu view_cost.
    assert all(l["sl_de_nghi"] == 10 for l in h2["nhap"])
    assert all(x["sl_de_nghi"] == 15 for x in h2["xuat"])


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
