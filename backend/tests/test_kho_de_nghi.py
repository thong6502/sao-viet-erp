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
    line = {"hang_loai": mat_id[0], "hang_id": mat_id[1], "dvt": "to", "sl_de_nghi": qty}
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
        "lines": [{"hang_loai": mat_id[0], "hang_id": mat_id[1], "dvt": "to", "sl_de_nghi": 12}],
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["trang_thai"] == "approved"
    assert body["lines"][0]["sl_duyet"] == 12
    assert body["nguoi_duyet_ten"] is not None and body["duyet_luc"] is not None


# --- mg 0175: dòng đề nghị khai được "xin cho LỆNH nào" ----------------------

def test_dong_de_nghi_de_trong_lenh_van_lap_duoc(client):
    """Xin lặt vặt (băng dính, giẻ lau) KHÔNG thuộc lệnh nào — luồng kho cũ không được vỡ."""
    kho_id, mat_id = _setup(client)
    dn = _login(client, "t_denghi")
    r = client.post("/api/kho/de-nghi", headers=dn, json={
        "loai": "XUAT", "kho_id": kho_id,
        "lines": [{"hang_loai": mat_id[0], "hang_id": mat_id[1], "dvt": "to", "sl_de_nghi": 5}],
    })
    assert r.status_code == 201, r.text
    assert r.json()["lines"][0]["lsx_id"] is None
    assert r.json()["lines"][0]["lsx_ma"] is None


def test_dong_de_nghi_gan_lenh_khong_ton_tai_thi_bao_loi(client):
    """Id lệnh sai phải NỔ, không im lặng bỏ.

    Im lặng thì dòng đó vĩnh viễn không khớp lệnh nào trong bảng cân đối, và triệu chứng duy nhất
    là "sao lệnh này cấp rồi mà vẫn báo thiếu" — không ai lần ra được nguyên nhân.
    """
    kho_id, mat_id = _setup(client)
    dn = _login(client, "t_denghi")
    r = client.post("/api/kho/de-nghi", headers=dn, json={
        "loai": "XUAT", "kho_id": kho_id,
        "lines": [{"hang_loai": mat_id[0], "hang_id": mat_id[1], "dvt": "to",
                   "sl_de_nghi": 5, "lsx_id": 999_999}],
    })
    assert r.status_code == 400, r.text
    assert "999999" in r.text or "999_999" in r.text or "không tồn tại" in r.text


def test_cung_mat_hang_cho_hai_lenh_khac_nhau_la_hai_dong_hop_le(client):
    """Trước mg 0175, "1 mặt hàng = 1 dòng" chặn cả ca này. Gộp lại thì mất thông tin phần nào cho
    lệnh nào — đúng thứ bảng cân đối cần để trừ đã-cấp vào đúng chỗ."""
    kho_id, mat_id = _setup(client)
    dn = _login(client, "t_denghi")
    r = client.post("/api/kho/de-nghi", headers=dn, json={
        "loai": "XUAT", "kho_id": kho_id,
        "lines": [
            {"hang_loai": mat_id[0], "hang_id": mat_id[1], "dvt": "to", "sl_de_nghi": 5},
            {"hang_loai": mat_id[0], "hang_id": mat_id[1], "dvt": "to", "sl_de_nghi": 7},
        ],
    })
    # Cùng mặt hàng, CÙNG (không) lệnh ⇒ vẫn là trùng, phải chặn như cũ.
    assert r.status_code == 400, r.text


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
                   params={"hang_loai": mat_id[0], "hang_id": mat_id[1], "kho_id": kho_id}, headers=kt)
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
                      params={"hang_loai": mat_id[0], "hang_id": mat_id[1], "kho_id": kho_id}).json()
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
                       params={"hang_loai": mat_id[0], "hang_id": mat_id[1], "kho_id": kho_id, "so_luong": 1000}).json()
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
                          params={"hang_loai": mat_id[0], "hang_id": mat_id[1], "kho_id": kho_id}).json()

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
    # Tạo đề nghị là 'approved' NGAY (bỏ bước duyệt) → kho lập phiếu được luôn.
    assert body["trang_thai"] == "approved"
    # Kho lập phiếu: KHÔNG gửi giá/quy đổi — chỉ SL. Backend lấy hết từ đề nghị.
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
    h2 = client.get(f"/api/kho/phieu/mat-hang/{mat_id[0]}/{mat_id[1]}/lich-su", headers=tk,
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


# --- Task 8: màn kho hiện tổ/công đoạn/giờ cần (task-8-ruling-man-kho) -------

def _gan_boi_canh_san_xuat(stock_request_id: int, *, can_luc, ten_cong_doan: str, ma_goi: str) -> int:
    """Trỏ MỘT yêu cầu kho đã có sẵn vào một 'lần đề nghị cấp vật tư công đoạn' — dựng TẮT qua
    `SessionLocal()` thay vì đi hết luồng sản xuất thật (phát hành gói → tổ đề nghị), luồng đó
    cần LSX/routing/phân công tổ trưởng đầy đủ, quá nặng cho file test KHO này (task-8-ruling-man-kho,
    Ruling 34 cho phép). Chỉ dựng đủ NOT NULL tối thiểu của `SanXuatGoiPhatHanh`/`SanXuatCongViec`
    để `boi_canh_san_xuat` join ra được `ten_cong_doan`. Trả `cong_viec_id` để test đối chiếu.
    """
    from app.models.san_xuat import SanXuatCongViec, SanXuatGoiPhatHanh
    from app.models.san_xuat_vat_tu import DN_LAN_DAU, SanXuatVatTuDeNghi

    db = SessionLocal()
    try:
        goi = SanXuatGoiPhatHanh(ma=ma_goi)
        db.add(goi)
        db.flush()
        cv = SanXuatCongViec(goi_id=goi.id, ten_cong_doan=ten_cong_doan)
        db.add(cv)
        db.flush()
        dn = SanXuatVatTuDeNghi(
            cong_viec_id=cv.id, lan_so=1, loai=DN_LAN_DAU, can_luc=can_luc,
            stock_request_id=stock_request_id,
        )
        db.add(dn)
        db.commit()
        return cv.id
    finally:
        db.close()


def test_api_yeu_cau_sinh_tu_san_xuat_co_can_luc_va_cong_doan(client):
    """Yêu cầu SINH TỪ đề nghị cấp vật tư công đoạn: GET trả `can_luc`/`san_xuat_cong_viec_id`/
    `san_xuat_cong_doan_ten`, và dòng phản chiếu đúng `sl_chot_thuc_xuat`/`sl_con_lai` sau khi kho
    điều chỉnh (xin 100 · xuất 100 · điều chỉnh còn 70 ⇒ chốt 70, còn lại 0)."""
    from datetime import datetime, timezone

    kho_id, mat_id = _setup(client)
    nhap = _nhap(client, kho_id=kho_id, mat_id=mat_id, qty=100, gia=1_000)
    lot_id = nhap["lines"][0]["lot_id"]
    req = _approved_request(client, kho_id=kho_id, loai="XUAT", mat_id=mat_id, qty=100)
    # CỐ Ý một ngày-giờ KHÔNG trùng "bây giờ" lúc chạy test (không chỉ khác ngày hôm nay — khác cả
    # giờ:phút với `created_at` sẽ có) — assert bên dưới soát cả giờ:phút để phân biệt được với
    # `created_at` (task-8-review.md Important 2: `startswith("2026-08-31")` từng đúng ăn may vì
    # hôm chạy test CHÍNH LÀ 2026-08-31).
    can_luc = datetime(2026, 9, 2, 13, 30, tzinfo=timezone.utc)
    cv_id = _gan_boi_canh_san_xuat(
        req["id"], can_luc=can_luc, ten_cong_doan="In offset 4 màu", ma_goi="GOI-T8-1")

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

    r = client.get(f"/api/kho/de-nghi/{req['id']}", headers=tk)
    assert r.status_code == 200, r.text
    body = r.json()
    # Soát cả GIỜ:PHÚT, không chỉ ngày — nếu repo lỡ trả nhầm `created_at` (lúc test chạy, "bây
    # giờ") thay vì `can_luc` thật thì assert này phải ĐỎ ngay (Important 2, kiểm đột biến ở §báo
    # cáo). `created_at` không thể trùng NGẪU NHIÊN đúng 13:30:00 của một ngày trong tương lai.
    assert body["can_luc"] is not None and body["can_luc"].startswith("2026-09-02T13:30")
    assert body["san_xuat_cong_viec_id"] == cv_id
    assert body["san_xuat_cong_doan_ten"] == "In offset 4 màu"
    assert body["lines"][0]["sl_chot_thuc_xuat"] == 70
    assert body["lines"][0]["sl_con_lai"] == 0


def test_api_yeu_cau_kho_thuong_khong_co_boi_canh_san_xuat(client):
    """Yêu cầu do bộ phận khác lập (không sinh từ đề nghị cấp vật tư công đoạn) vẫn trả 3 field
    đó nhưng đều null — FE không phải phân nhánh."""
    kho_id, mat_id = _setup(client)
    req = _approved_request(client, kho_id=kho_id, loai="XUAT", mat_id=mat_id, qty=10)
    tk = _login(client, "t_thukho")

    r = client.get(f"/api/kho/de-nghi/{req['id']}", headers=tk)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["can_luc"] is None
    assert body["san_xuat_cong_viec_id"] is None
    assert body["san_xuat_cong_doan_ten"] is None
    assert body["lines"][0]["sl_chot_thuc_xuat"] is None


def test_api_danh_sach_yeu_cau_sinh_tu_sx_khong_n_plus_1(client, monkeypatch):
    """Đường DANH SÁCH (hộp yêu cầu kho) với ÍT NHẤT 3 yêu cầu sinh từ sản xuất phải nạp bối cảnh
    (tổ/công đoạn/giờ cần) bằng ĐÚNG MỘT câu SQL chạm bảng `san_xuat_vat_tu_de_nghi`, không phải N
    câu theo từng yêu cầu — N+1 với N=1 nhìn y hệt truy vấn gộp nên phải dựng ÍT NHẤT 3
    (task-8-ruling-man-kho, Ruling 34).

    Đếm SQL THẬT qua sự kiện `before_cursor_execute` của SQLAlchemy (đúng engine mà `conftest.py`
    dùng cho `client`/`db` — `from app.db import Base, engine`), KHÔNG chỉ đếm số lần gọi hàm
    `boi_canh_san_xuat`: đếm lượt gọi chỉ khoá "router gọi 1 lần", không khoá "1 truy vấn" — hai
    thứ khác nhau, ai sửa `boi_canh_san_xuat` thành vòng lặp N truy vấn bên trong (vd lọc thêm theo
    `lan_so` mới nhất bằng cách hỏi từng `request_id`) thì đếm-lượt-gọi vẫn xanh mà đếm-SQL mới bắt
    được (task-8-review.md Important 1 — đã chứng minh bằng kiểm đột biến, xem báo cáo vòng sửa).
    Giữ luôn assert đếm-lượt-gọi vì hai vế bắt hai lỗi khác nhau (gọi hàm nhiều lần khác với hàm gọi
    ít nhưng tự N+1 bên trong)."""
    from datetime import datetime, timezone

    from sqlalchemy import event

    import app.repositories.san_xuat_vat_tu_repo as sxvt_repo
    from app.db import engine

    kho_id, mat_id = _setup(client)
    can_luc = datetime(2026, 8, 31, 8, 0, tzinfo=timezone.utc)
    req_ids = []
    for i in range(3):
        req = _approved_request(client, kho_id=kho_id, loai="XUAT", mat_id=mat_id, qty=10 + i)
        _gan_boi_canh_san_xuat(
            req["id"], can_luc=can_luc, ten_cong_doan=f"Công đoạn {i}", ma_goi=f"GOI-T8-NP1-{i}")
        req_ids.append(req["id"])

    calls: list[list[int]] = []
    goc = sxvt_repo.SanXuatVatTuRepository.boi_canh_san_xuat

    def _dem(self, ids):
        calls.append(list(ids))
        return goc(self, ids)

    monkeypatch.setattr(sxvt_repo.SanXuatVatTuRepository, "boi_canh_san_xuat", _dem)

    sqls: list[str] = []

    def _ghi_sql(conn, cursor, statement, params, context, executemany):
        sqls.append(statement)

    event.listen(engine, "before_cursor_execute", _ghi_sql)
    try:
        tk = _login(client, "t_thukho")
        r = client.get("/api/kho/de-nghi", headers=tk, params={"loai": "XUAT", "size": 200})
    finally:
        event.remove(engine, "before_cursor_execute", _ghi_sql)

    assert r.status_code == 200, r.text
    items = {it["id"]: it for it in r.json()["items"] if it["id"] in req_ids}
    assert len(items) == 3
    assert all(items[i]["san_xuat_cong_doan_ten"] for i in req_ids)
    assert len(calls) == 1, f"boi_canh_san_xuat phải gọi ĐÚNG 1 lần cho cả trang, gọi {len(calls)} lần"
    cham_bang = [s for s in sqls if "san_xuat_vat_tu_de_nghi" in s]
    assert len(cham_bang) == 1, (
        f"boi_canh_san_xuat phải là ĐÚNG 1 câu SQL chạm san_xuat_vat_tu_de_nghi cho cả trang, "
        f"chạm {len(cham_bang)} câu:\n" + "\n---\n".join(cham_bang)
    )


def test_api_can_luc_ve_gio_nha_may_du_db_tra_aware(client, monkeypatch):
    """`san_xuat_vat_tu_de_nghi.can_luc` là cột `DateTime(timezone=True)`: Postgres `timestamptz`
    trả về datetime AWARE (`+00:00`), SQLite của bộ test luôn trả naive. API PHẢI cắt tzinfo trước
    khi ra JSON — FE kho (`fmtGioCan`, `isOverdue`) đọc naive = giờ NHÀ MÁY, gặp chuỗi có `Z` là
    `new Date()` dịch thêm +7h và thủ kho thấy "cần lúc 20:30" cho ca chiều 13:30.

    Ép `boi_canh_san_xuat` trả AWARE để tái hiện đúng thứ Postgres trả — chạy trên SQLite thì
    không có đường nào khác chạm được ca này (đã đo trên Postgres thật, DB dùng-một-lần).
    """
    from datetime import datetime, timezone

    import app.repositories.san_xuat_vat_tu_repo as sxvt_repo

    kho_id, mat_id = _setup(client)
    req = _approved_request(client, kho_id=kho_id, loai="XUAT", mat_id=mat_id, qty=10)
    cv_id = _gan_boi_canh_san_xuat(
        req["id"], can_luc=datetime(2026, 9, 2, 13, 30),
        ten_cong_doan="Cán màng", ma_goi="GOI-T10-TZ")

    goc = sxvt_repo.SanXuatVatTuRepository.boi_canh_san_xuat

    def _aware(self, ids):
        ra = goc(self, ids)
        for v in ra.values():
            if v.get("can_luc") is not None and v["can_luc"].tzinfo is None:
                v["can_luc"] = v["can_luc"].replace(tzinfo=timezone.utc)
        return ra

    monkeypatch.setattr(sxvt_repo.SanXuatVatTuRepository, "boi_canh_san_xuat", _aware)

    tk = _login(client, "t_thukho")
    r = client.get(f"/api/kho/de-nghi/{req['id']}", headers=tk)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["san_xuat_cong_viec_id"] == cv_id
    # Không "Z", không "+07:00", không "+00:00" — chuỗi trần đúng giờ tổ trưởng gõ.
    assert body["can_luc"] == "2026-09-02T13:30:00", body["can_luc"]
