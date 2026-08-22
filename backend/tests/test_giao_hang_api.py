"""Giao hàng — 17 điều kiện nghiệm thu của `docs/prd-giao-hang.md` §12.

Mỗi test dưới đây ứng một dòng nghiệm thu, ghi số hiệu ở docstring. Đây là hàng rào duy nhất giữ
cho phần thiết kế khỏi bị "sửa cho gọn" rồi vỡ — bốn luật hay bị đụng nhất:

* "đã giao bao nhiêu" là `SUM`, không cột cộng dồn;
* một yêu cầu chỉ MỘT chuyến đang chạy (điều kiện giữ cho trạng thái tầng 1 tính được);
* trùng lịch tài xế thì CHẶN, sát giờ thì CẢNH BÁO — hai vế khác nhau;
* `km >= 0` chứ không `> 0`.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.db import SessionLocal
from app.models.customer import Customer
from app.models.employee import Employee
from app.models.order import Order, OrderLine, STATUS_ORDERED
from app.models.role import SCOPE_ALL, SCOPE_OWN
from app.repositories.rbac_repo import DepartmentRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.security import create_access_token, hash_password

MODULE = "giao_hang"


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _admin(client) -> dict[str, str]:
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return _h(r.json()["access_token"])


def _don_da_chot(*, suffix: str, qty: int = 100) -> tuple[int, int]:
    """Đơn hàng bán ĐÃ CHỐT + 1 dòng hàng. Trả (order_id, order_line_id)."""
    db = SessionLocal()
    try:
        kh = Customer(code=f"KH-GH-{suffix}", name=f"Khach giao hang {suffix}")
        db.add(kh)
        db.flush()
        order = Order(
            order_no=f"DH-GH-{suffix}", customer_id=kh.id, status=STATUS_ORDERED,
            delivery_address="12 Le Loi, Q1", delivery_contact_name="Chi Lan",
            delivery_contact_phone="0901234567",
        )
        order.lines.append(OrderLine(description="Hop giay", qty=qty, don_vi_tinh="hop",
                                     line_total=1_000_000, vat_pct_estimate=0))
        db.add(order)
        db.commit()
        return order.id, order.lines[0].id
    finally:
        db.close()


def _tai_xe(ten: str, *, phong: str = "Sản xuất") -> int:
    db = SessionLocal()
    try:
        dept = DepartmentRepository(db).get_by_name(phong)
        e = Employee(code=f"NVGH{abs(hash(ten)) % 9000 + 1000}", full_name=ten,
                     department_id=dept.id, hire_date=date(2020, 1, 1))
        db.add(e)
        db.commit()
        return e.id
    finally:
        db.close()


def _vai(username: str, *, scope: str = SCOPE_ALL, phong: str = "Sản xuất", **o) -> str:
    """Tài khoản có ô `giao_hang` khai đúng những cờ truyền vào. Trả token."""
    db = SessionLocal()
    try:
        users = UserRepository(db)
        u = users.get_by_username(username)
        if u is None:
            dept = DepartmentRepository(db).get_by_name(phong)
            roles = RoleRepository(db)
            role = roles.create(name=f"Vai {username}", department_id=dept.id)
            roles.set_permission(role_id=role.id, module_key=MODULE, scope=scope, **o)
            u = users.create(username=username, name=username, password_hash=hash_password("x"))
            users.set_assignment(u, department_id=dept.id, role_id=role.id, is_active=True)
        return create_access_token(str(u.id))
    finally:
        db.close()


def _gio(gio: int, phut: int = 0, *, cong_ngay: int = 1) -> str:
    t = datetime.now(timezone.utc) + timedelta(days=cong_ngay)
    return t.replace(hour=gio, minute=phut, second=0, microsecond=0).isoformat()


def _kho_va_mat_hang() -> tuple[int, int]:
    """Một kho + một mặt hàng trong danh mục Vật tư khác. Trả (kho_id, hang_id).

    Giao hàng lập yêu cầu xuất kho THẬT nên phải chọn mặt hàng CÓ TRONG DANH MỤC — luật siết
    08/08/2026 của kho, áp cho giao hàng y hệt mọi bộ phận. Đây chính là "khai sản phẩm ở Giấy /
    Vật tư khác rồi mới vào kho nhập số lượng" mà xưởng đang làm.
    """
    from app.models.kho_hang import KhoHang
    from app.models.vat_lieu_kho import VatTuInAn

    db = SessionLocal()
    try:
        kho = db.query(KhoHang).filter(KhoHang.ma == "KTP").one_or_none()
        if kho is None:
            kho = KhoHang(ma="KTP", ten="Kho thanh pham")
            db.add(kho)
            db.flush()
        h = db.query(VatTuInAn).filter(VatTuInAn.ma == "TP001").one_or_none()
        if h is None:
            h = VatTuInAn(ma="TP001", ten="Hop giay thanh pham", don_vi_gia="cai")
            db.add(h)
            db.flush()
        db.commit()
        return kho.id, h.id
    finally:
        db.close()


def _tao_yc(client, h, order_id, line_id, qty=40, ngay=None) -> dict:
    """Yêu cầu giao. KHÔNG khai mặt hàng — máy chủ tự khai vào danh mục từ mô tả dòng đơn."""
    r = client.post("/api/giao-hang/requests", json={
        "order_id": order_id,
        "ngay_can_giao": (ngay or (date.today() + timedelta(days=3))).isoformat(),
        "lines": [{"order_line_id": line_id, "qty": qty}],
    }, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def _len_kh(client, h, request_id, employee_id, *, lay=8, giao=11, ngay=1):
    return client.post("/api/giao-hang/plans", json={
        "request_id": request_id, "employee_id": employee_id,
        "gio_lay_hang": _gio(lay, cong_ngay=ngay),
        "gio_du_kien_giao": _gio(giao, cong_ngay=ngay),
    }, headers=h)


def _gui_yeu_cau_xuat_kho(client, h, trip_id) -> dict:
    """Bấm gửi YÊU CẦU XUẤT KHO. Chỉ chọn kho — dòng hàng máy suy ra từ yêu cầu giao."""
    kho_id, _ = _kho_va_mat_hang()
    r = client.post(f"/api/giao-hang/plans/{trip_id}/yeu-cau-xuat-kho",
                    json={"kho_id": kho_id}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def _di_toi_dang_giao(client, h, trip_id) -> None:
    """Gửi yêu cầu xuất kho → tài xế bấm Đã lấy hàng → Bắt đầu giao.

    Không có bước "duyệt": `StockRequestService.create()` duyệt luôn (bỏ bước duyệt 06/08/2026),
    kho lập phiếu ngay. Giao hàng không cần chờ gì thêm ở tầng dữ liệu.
    """
    _gui_yeu_cau_xuat_kho(client, h, trip_id)
    for buoc in ("da-lay-hang", "bat-dau-giao"):
        r = client.post(f"/api/giao-hang/trips/{trip_id}/{buoc}", headers=h)
        assert r.status_code == 200, (buoc, r.text)


# =============================================================================================
# #1 · #2 — nhiều yêu cầu một đơn, không vượt số còn phải giao
# =============================================================================================
def test_01_mot_don_tao_duoc_nhieu_yeu_cau(client):
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="01")
    a = _tao_yc(client, h, oid, lid, qty=40)
    b = _tao_yc(client, h, oid, lid, qty=30)
    assert a["code"] != b["code"]
    assert a["code"].startswith("YCGH-")


def test_02_khong_duoc_yeu_cau_vuot_so_con_phai_giao(client):
    """⭐ Yêu cầu MỞ cũng phải bị trừ, không thì lập hai phiếu liên tiếp là vượt đơn."""
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="02", qty=100)
    _tao_yc(client, h, oid, lid, qty=70)
    r = client.post("/api/giao-hang/requests", json={
        "order_id": oid, "ngay_can_giao": (date.today() + timedelta(days=2)).isoformat(),
        "lines": [{"order_line_id": lid, "qty": 40}],
    }, headers=h)
    assert r.status_code == 400, r.text
    assert "còn phải giao" in r.json()["detail"]


def test_02b_con_phai_giao_tra_dung_so(client):
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="02b", qty=100)
    _tao_yc(client, h, oid, lid, qty=40)
    r = client.get(f"/api/giao-hang/orders/{oid}/con-phai-giao", headers=h)
    assert r.status_code == 200, r.text
    dong = r.json()["lines"][0]
    assert dong["qty_dat"] == 100 and dong["da_giao"] == 0 and dong["con_phai_giao"] == 60


# =============================================================================================
# #3 — một yêu cầu chỉ MỘT chuyến đang chạy
# =============================================================================================
def test_03_mot_yeu_cau_chi_MOT_chuyen(client):
    """⭐ Siết từ 22/08/2026: trước chỉ chặn chuyến ĐANG CHẠY, nay chặn chuyến THỨ HAI.

    Chủ: "mỗi yêu cầu giao hàng là một chuyến giao cho nó dễ; muốn giao lại thì phải gửi yêu cầu
    mới cho dễ hiểu." Một yêu cầu = một kết cục.
    """
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="03")
    yc = _tao_yc(client, h, oid, lid)
    nv = _tai_xe("Tai xe 03")
    assert _len_kh(client, h, yc["id"], nv).status_code == 201
    lan_hai = _len_kh(client, h, yc["id"], nv, lay=14, giao=16)
    assert lan_hai.status_code == 400, lan_hai.text
    assert "lập yêu cầu giao mới" in lan_hai.json()["detail"]


# =============================================================================================
# #4 — trùng lịch thì CHẶN, sát giờ thì CẢNH BÁO
# =============================================================================================
def test_04_trung_lich_tai_xe_bi_chan(client):
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="04")
    yc1 = _tao_yc(client, h, oid, lid, qty=30)
    yc2 = _tao_yc(client, h, oid, lid, qty=30)
    nv = _tai_xe("Tai xe 04")
    assert _len_kh(client, h, yc1["id"], nv, lay=8, giao=11).status_code == 201
    # 10–12 giao nhau với 8–11 ⇒ CHẶN.
    r = _len_kh(client, h, yc2["id"], nv, lay=10, giao=12)
    assert r.status_code == 400, r.text
    assert "trùng giờ" in r.json()["detail"]


def test_04b_sat_gio_thi_CANH_BAO_chu_khong_chan(client):
    """⭐ Bản gốc viết "cảnh báo và không cho lưu" — hai vế đá nhau. Sát giờ phải CHO LƯU."""
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="04b")
    yc1 = _tao_yc(client, h, oid, lid, qty=30)
    yc2 = _tao_yc(client, h, oid, lid, qty=30)
    nv = _tai_xe("Tai xe 04b")
    assert _len_kh(client, h, yc1["id"], nv, lay=8, giao=11).status_code == 201
    # 11:10 cách chuyến trước 10 phút — không trùng, nhưng dưới 30 phút.
    r = client.post("/api/giao-hang/plans", json={
        "request_id": yc2["id"], "employee_id": nv,
        "gio_lay_hang": _gio(11, 10), "gio_du_kien_giao": _gio(13),
    }, headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["canh_bao"], "sát giờ mà không cảnh báo gì thì cảnh báo để làm gì"


def test_04c_cham_mep_khong_tinh_la_trung(client):
    """Giao xong 11:00, chuyến sau lấy hàng 11:00 — chạm mép, KHÔNG phải trùng."""
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="04c")
    yc1 = _tao_yc(client, h, oid, lid, qty=30)
    yc2 = _tao_yc(client, h, oid, lid, qty=30)
    nv = _tai_xe("Tai xe 04c")
    assert _len_kh(client, h, yc1["id"], nv, lay=8, giao=11).status_code == 201
    assert _len_kh(client, h, yc2["id"], nv, lay=11, giao=13).status_code == 201


# =============================================================================================
# #5 — tài xế phạm vi "Của tôi" chỉ thấy chuyến của mình
# =============================================================================================
def test_05_tai_xe_pham_vi_cua_toi_chi_thay_chuyen_cua_minh(client):
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="05")
    yc = _tao_yc(client, h, oid, lid)
    nv_khac = _tai_xe("Tai xe nguoi khac")
    r = _len_kh(client, h, yc["id"], nv_khac)
    assert r.status_code == 201, r.text
    trip_id = r.json()["trip"]["id"]

    tok = _vai("tx-pham-vi-05", scope=SCOPE_OWN, can_read=True, can_create=True)
    ds = client.get("/api/giao-hang/trips", headers=_h(tok))
    assert ds.status_code == 200, ds.text
    assert ds.json()["items"] == [], "phạm vi Của tôi mà vẫn thấy chuyến người khác"
    # Gọi thẳng id cũng phải 403 — lọc danh sách mà quên gác đường id là hàng rào vẽ trên màn.
    r2 = client.post(f"/api/giao-hang/trips/{trip_id}/bat-dau-giao", headers=_h(tok))
    assert r2.status_code == 403, r2.text


# =============================================================================================
# #6 — không nhập km thì không đóng được chuyến; km >= 0
# =============================================================================================
def _chuyen_dang_giao(client, h, suffix) -> int:
    oid, lid = _don_da_chot(suffix=suffix)
    yc = _tao_yc(client, h, oid, lid, qty=40)
    nv = _tai_xe(f"Tai xe {suffix}")
    r = _len_kh(client, h, yc["id"], nv)
    assert r.status_code == 201, r.text
    trip_id = r.json()["trip"]["id"]
    _di_toi_dang_giao(client, h, trip_id)
    return trip_id


def test_06_thieu_km_thi_khong_dong_duoc_chuyen(client):
    h = _admin(client)
    trip = _chuyen_dang_giao(client, h, "06")
    r = client.post(f"/api/giao-hang/trips/{trip}/ket-qua",
                    json={"ket_qua": "thanh_cong", "nguoi_nhan_thuc_te": "Anh Ba"}, headers=h)
    assert r.status_code == 422, r.text


def test_06b_km_bang_0_la_HOP_LE(client):
    """⭐ `km >= 0`, KHÔNG phải `> 0`: khách không nghe máy khi xe chưa lăn bánh thì 0 km là THẬT."""
    h = _admin(client)
    trip = _chuyen_dang_giao(client, h, "06b")
    r = client.post(f"/api/giao-hang/trips/{trip}/ket-qua", json={
        "ket_qua": "that_bai", "km": 0, "ly_do_that_bai": "Khach khong nghe may",
        "huong_xu_ly": "tra_ve",
    }, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["km"] == 0


def test_06c_km_lon_bat_thuong_bi_hoi_lai_nhung_xac_nhan_thi_qua(client):
    """Gõ nhầm 180 thành 1800 mới là lỗi hay gặp — chặn mềm, không chặn cứng."""
    h = _admin(client)
    trip = _chuyen_dang_giao(client, h, "06c")
    body = {"ket_qua": "thanh_cong", "km": 1800, "nguoi_nhan_thuc_te": "Anh Ba"}
    r = client.post(f"/api/giao-hang/trips/{trip}/ket-qua", json=body, headers=h)
    assert r.status_code == 400 and "bất thường" in r.json()["detail"], r.text
    r2 = client.post(f"/api/giao-hang/trips/{trip}/ket-qua",
                     json={**body, "xac_nhan_km_lon": True}, headers=h)
    assert r2.status_code == 200, r2.text


# =============================================================================================
# #7 · #8 · #9 — thất bại KHÔNG cộng, thành công cộng đúng, giao lại không nhân đôi
# =============================================================================================
def test_07_giao_that_bai_KHONG_lam_tang_da_giao(client):
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="07", qty=100)
    yc = _tao_yc(client, h, oid, lid, qty=40)
    nv = _tai_xe("Tai xe 07")
    trip = _len_kh(client, h, yc["id"], nv).json()["trip"]["id"]
    _di_toi_dang_giao(client, h, trip)
    r = client.post(f"/api/giao-hang/trips/{trip}/ket-qua", json={
        "ket_qua": "that_bai", "km": 18, "ly_do_that_bai": "Kho dong cua",
        "huong_xu_ly": "tra_ve",
    }, headers=h)
    assert r.status_code == 200, r.text
    con = client.get(f"/api/giao-hang/orders/{oid}/con-phai-giao", headers=h).json()
    assert con["lines"][0]["da_giao"] == 0, "chuyến hỏng mà vẫn cộng vào đã giao"


def test_08_giao_thanh_cong_cong_dung_so(client):
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="08", qty=100)
    yc = _tao_yc(client, h, oid, lid, qty=40)
    nv = _tai_xe("Tai xe 08")
    trip = _len_kh(client, h, yc["id"], nv).json()["trip"]["id"]
    _di_toi_dang_giao(client, h, trip)
    assert client.post(f"/api/giao-hang/trips/{trip}/ket-qua", json={
        "ket_qua": "thanh_cong", "km": 22, "nguoi_nhan_thuc_te": "Anh Ba",
    }, headers=h).status_code == 200
    con = client.get(f"/api/giao-hang/orders/{oid}/con-phai-giao", headers=h).json()
    assert con["lines"][0]["da_giao"] == 40
    assert con["lines"][0]["con_phai_giao"] == 60


def test_08b_giao_thieu_cong_dung_phan_thuc_nhan(client):
    """⭐ Ca hay gặp nhất ngoài đời: yêu cầu 40, khách nhận 25."""
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="08b", qty=100)
    yc = _tao_yc(client, h, oid, lid, qty=40)
    nv = _tai_xe("Tai xe 08b")
    trip = _len_kh(client, h, yc["id"], nv).json()["trip"]["id"]
    _di_toi_dang_giao(client, h, trip)
    r = client.post(f"/api/giao-hang/trips/{trip}/ket-qua", json={
        "ket_qua": "giao_thieu", "km": 20, "nguoi_nhan_thuc_te": "Anh Ba",
        "so_thuc_nhan": [{"order_line_id": lid, "qty": 25}],
    }, headers=h)
    assert r.status_code == 200, r.text
    con = client.get(f"/api/giao-hang/orders/{oid}/con-phai-giao", headers=h).json()
    assert con["lines"][0]["da_giao"] == 25
    # 15 còn lại của yêu cầu vẫn bị GIỮ CHỖ, chưa trả về "còn phải giao" của đơn.
    assert con["lines"][0]["con_phai_giao"] == 60


def test_09_giao_lai_bang_YEU_CAU_MOI_khong_nhan_doi_so_luong(client):
    """⭐ Yêu cầu 1 thất bại → trả hàng về kho → lập YÊU CẦU MỚI → giao thành công.

    Đã giao = 40 (không phải 80). Trước 22/08/2026 giao lại là thêm chuyến vào yêu cầu cũ; nay
    yêu cầu cũ đã đóng, phần 40 quay lại "còn phải giao" của đơn nên lập lại được.
    """
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="09", qty=100)
    yc = _tao_yc(client, h, oid, lid, qty=40)
    nv = _tai_xe("Tai xe 09")

    t1 = _len_kh(client, h, yc["id"], nv, lay=8, giao=10).json()["trip"]["id"]
    _di_toi_dang_giao(client, h, t1)
    client.post(f"/api/giao-hang/trips/{t1}/ket-qua", json={
        "ket_qua": "that_bai", "km": 18, "ly_do_that_bai": "Khach di vang",
        "huong_xu_ly": "tra_ve"}, headers=h)
    client.post(f"/api/giao-hang/trips/{t1}/da-tra-hang", headers=h)

    # Yêu cầu CŨ không xếp thêm chuyến được nữa.
    assert _len_kh(client, h, yc["id"], nv, lay=8, giao=10, ngay=2).status_code == 400

    yc2 = _tao_yc(client, h, oid, lid, qty=40)
    t2r = _len_kh(client, h, yc2["id"], nv, lay=8, giao=10, ngay=2)
    assert t2r.status_code == 201, t2r.text
    t2 = t2r.json()["trip"]["id"]
    assert t2 != t1
    _di_toi_dang_giao(client, h, t2)
    assert client.post(f"/api/giao-hang/trips/{t2}/ket-qua", json={
        "ket_qua": "thanh_cong", "km": 22, "nguoi_nhan_thuc_te": "Anh Ba"},
        headers=h).status_code == 200

    con = client.get(f"/api/giao-hang/orders/{oid}/con-phai-giao", headers=h).json()
    assert con["lines"][0]["da_giao"] == 40, "giao lại làm nhân đôi số lượng"
    # Km nay tính THEO TỪNG YÊU CẦU, không cộng dồn trong một yêu cầu nữa: 18 ở lần hỏng,
    # 22 ở lần giao được. Tổng quãng đường của cả việc này vẫn là 40, chỉ nằm ở hai chứng từ.
    ct1 = client.get(f"/api/giao-hang/requests/{yc['id']}", headers=h).json()
    ct2 = client.get(f"/api/giao-hang/requests/{yc2['id']}", headers=h).json()
    assert [t["km"] for t in ct1["trips"]] == [18]
    assert [t["km"] for t in ct2["trips"]] == [22]
    assert ct2["request"]["trang_thai"] == "da_giao_du"


# =============================================================================================
# #10 — mọi lần đổi trạng thái có lịch sử
# =============================================================================================
def test_10_moi_lan_doi_trang_thai_deu_co_lich_su(client):
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="10")
    yc = _tao_yc(client, h, oid, lid)
    nv = _tai_xe("Tai xe 10")
    trip = _len_kh(client, h, yc["id"], nv).json()["trip"]["id"]
    _di_toi_dang_giao(client, h, trip)
    ls = client.get(f"/api/giao-hang/requests/{yc['id']}", headers=h).json()["lich_su"]
    # API trả MỚI NHẤT TRƯỚC (20/08/2026) — đảo lại để đọc theo thứ tự việc thật sự xảy ra.
    di_qua = [x["den_trang_thai"] for x in reversed(ls)]
    # Bốn bước: lên kế hoạch → gửi yêu cầu xuất kho → tài xế lấy hàng → lên đường. Không còn
    # "chờ lấy hàng" vì không ai báo "đã soạn xong" nữa (chủ chốt 19/08/2026).
    assert di_qua == ["da_len_ke_hoach", "dang_chuan_bi", "da_lay_hang", "dang_giao"], di_qua
    assert all(x["nguoi_thao_tac_id"] for x in ls), "có dòng lịch sử không ghi ai bấm"


# =============================================================================================
# #12 · #13 · #14 · #15 · #16 · #17
# =============================================================================================
def test_12_huy_don_ban_khi_con_yeu_cau_mo_thi_bi_chan(client):
    """Thông báo phải nêu ĐÚNG mã yêu cầu đang mở, đừng bắt người ta đi mò."""
    from app.repositories.delivery_repo import DeliveryRepository
    from app.repositories.employee_repo import EmployeeRepository
    from app.repositories.order_repo import OrderRepository
    from app.repositories.rbac_repo import DepartmentRepository as DR
    from app.repositories.user_repo import UserRepository as UR
    from app.services.delivery_service import DeliveryError, DeliveryService

    h = _admin(client)
    oid, lid = _don_da_chot(suffix="12")
    yc = _tao_yc(client, h, oid, lid)
    db = SessionLocal()
    try:
        svc = DeliveryService(DeliveryRepository(db), OrderRepository(db),
                              EmployeeRepository(db), UR(db), DR(db))
        try:
            svc.chan_huy_don_khi_con_yeu_cau_mo(oid)
            raise AssertionError("huỷ đơn khi còn yêu cầu mở mà không bị chặn")
        except DeliveryError as e:
            assert yc["code"] in str(e), str(e)
    finally:
        db.close()


def test_13_len_ke_hoach_KHONG_tu_gui_kho_bam_tay_moi_gui(client):
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="13")
    yc = _tao_yc(client, h, oid, lid)
    nv = _tai_xe("Tai xe 13")
    trip = _len_kh(client, h, yc["id"], nv, lay=8).json()["trip"]["id"]
    # ⭐ Lên kế hoạch xong CHƯA gửi kho gì cả — hệ KHÔNG tự sinh.
    ds = client.get("/api/giao-hang/trips", headers=h).json()["items"]
    assert next(t for t in ds if t["id"] == trip)["yeu_cau_kho_ma"] is None

    ra = _gui_yeu_cau_xuat_kho(client, h, trip)
    # Mã do KHO cấp (DNX…), không phải mã riêng của Giao hàng — vì đây là chứng từ của họ.
    assert ra["ma"].startswith("DNX"), ra
    ds = client.get("/api/giao-hang/trips", headers=h).json()["items"]
    assert next(t for t in ds if t["id"] == trip)["yeu_cau_kho_ma"] == ra["ma"]


def test_14_YEU_CAU_MOI_cung_phai_gui_yeu_cau_xuat_kho(client):
    """⭐ Không có lối tắt — yêu cầu nào cũng phải qua kho (PRD §6).

    Từ 22/08/2026 "giao lại" là YÊU CẦU MỚI, nên câu hỏi thành: yêu cầu lập sau một lần giao hỏng
    có phải đi lại trọn quy trình không. Có.
    """
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="14")
    yc = _tao_yc(client, h, oid, lid)
    nv = _tai_xe("Tai xe 14")
    t1 = _len_kh(client, h, yc["id"], nv, lay=8, giao=10).json()["trip"]["id"]
    _di_toi_dang_giao(client, h, t1)
    client.post(f"/api/giao-hang/trips/{t1}/ket-qua", json={
        "ket_qua": "that_bai", "km": 12, "ly_do_that_bai": "Khach hen hom khac",
        "huong_xu_ly": "tra_ve"}, headers=h)
    client.post(f"/api/giao-hang/trips/{t1}/da-tra-hang", headers=h)

    yc2 = _tao_yc(client, h, oid, lid)
    t2 = _len_kh(client, h, yc2["id"], nv, lay=8, giao=10, ngay=2).json()["trip"]["id"]
    ra = _gui_yeu_cau_xuat_kho(client, h, t2)
    assert ra["ma"].startswith("DNX"), "yêu cầu mới không gửi được yêu cầu xuất kho"


def test_KHONG_CON_ket_qua_hen_lai(client):
    """⭐ `hen_lai` là trạng thái TREO — chuyến chưa xong mà cũng không kết thúc, hàng nằm trên xe
    không biết tới bao giờ. Gỡ ngày 22/08/2026; khai nó phải BÁO LỖI chứ không âm thầm bỏ qua."""
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="hl")
    yc = _tao_yc(client, h, oid, lid)
    trip = _len_kh(client, h, yc["id"], _tai_xe("Tai xe hl")).json()["trip"]["id"]
    _di_toi_dang_giao(client, h, trip)
    r = client.post(f"/api/giao-hang/trips/{trip}/ket-qua",
                    json={"ket_qua": "hen_lai", "km": 5}, headers=h)
    assert r.status_code == 400, r.text


def test_KHONG_CON_huong_xu_ly_cho_giao_lai(client):
    """⭐ "Chờ giao lại" giữ hàng trên xe trong khi sổ kho ghi đã xuất — chính chỗ đó che mất lỗi
    "trả hàng về không vào sổ" suốt thời gian qua. Nay chỉ còn trả về kho."""
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="cgl")
    yc = _tao_yc(client, h, oid, lid)
    trip = _len_kh(client, h, yc["id"], _tai_xe("Tai xe cgl")).json()["trip"]["id"]
    _di_toi_dang_giao(client, h, trip)
    r = client.post(f"/api/giao-hang/trips/{trip}/ket-qua", json={
        "ket_qua": "that_bai", "km": 5, "ly_do_that_bai": "Khach vang",
        "huong_xu_ly": "cho_giao_lai"}, headers=h)
    assert r.status_code == 400, r.text


def test_15_doi_gio_sau_khi_da_gui_kho_thi_CANH_BAO_chu_khong_huy_ho(client):
    """⭐ Yêu cầu kho là chứng từ CỦA HỌ — huỷ hộ là đụng vào sổ sách bên đó.

    Bản trước tôi tự huỷ đề nghị rồi bắt gửi lại. Làm thế với chứng từ của kho là vượt ranh giới:
    quản lý tự vào màn Kho huỷ nếu cần, hệ chỉ CẢNH BÁO.
    """
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="15")
    yc = _tao_yc(client, h, oid, lid)
    nv = _tai_xe("Tai xe 15")
    trip = _len_kh(client, h, yc["id"], nv, lay=8, giao=10).json()["trip"]["id"]
    ma_cu = _gui_yeu_cau_xuat_kho(client, h, trip)["ma"]

    r = client.put(f"/api/giao-hang/plans/{trip}",
                   json={"gio_lay_hang": _gio(15), "gio_du_kien_giao": _gio(17)}, headers=h)
    assert r.status_code == 200, r.text
    assert any("yêu cầu xuất kho" in c for c in r.json()["canh_bao"]), r.json()

    # Yêu cầu kho KHÔNG bị đụng tới.
    ds = client.get("/api/giao-hang/trips", headers=h).json()["items"]
    assert next(t for t in ds if t["id"] == trip)["yeu_cau_kho_ma"] == ma_cu


def test_16_kho_KHONG_can_o_giao_hang_de_lam_viec(client):
    """Kho thấy yêu cầu xuất trong Hộp yêu cầu của CHÍNH HỌ, đi theo ô `kho` sẵn có.

    Không còn endpoint nào của Giao hàng dành cho kho — nên vai kho không mở được màn Giao hàng
    là ĐÚNG, và họ vẫn làm việc bình thường bên màn Kho.
    """
    db = SessionLocal()
    try:
        dept = DepartmentRepository(db).get_by_name("Sản xuất")
        roles = RoleRepository(db)
        role = roles.create(name="Vai kho giao hang", department_id=dept.id)
        roles.set_permission(role_id=role.id, module_key="kho", scope=SCOPE_ALL,
                             can_read=True, can_create=True)
        u = UserRepository(db).create(username="kho-gh-16", name="Kho",
                                      password_hash=hash_password("x"))
        UserRepository(db).set_assignment(u, department_id=dept.id, role_id=role.id,
                                          is_active=True)
        kho = _h(create_access_token(str(u.id)))
    finally:
        db.close()

    assert client.get("/api/giao-hang/trips", headers=kho).status_code == 403
    # Nhưng Hộp yêu cầu của họ thì mở bình thường.
    assert client.get("/api/kho/de-nghi", headers=kho).status_code in (200, 404)


def test_17_tai_xe_khong_lay_duoc_hang_khi_CHUA_GUI_KHO(client):
    """Chưa có giấy thì hàng chưa ra được cửa kho — bấm ở đây là ghi chuyện chưa xảy ra."""
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="17")
    yc = _tao_yc(client, h, oid, lid)
    nv = _tai_xe("Tai xe 17")
    trip = _len_kh(client, h, yc["id"], nv).json()["trip"]["id"]

    assert client.post(f"/api/giao-hang/trips/{trip}/da-lay-hang", headers=h).status_code == 400
    assert client.post(f"/api/giao-hang/trips/{trip}/bat-dau-giao", headers=h).status_code == 400

    _gui_yeu_cau_xuat_kho(client, h, trip)
    assert client.post(f"/api/giao-hang/trips/{trip}/da-lay-hang", headers=h).status_code == 200


def test_ngay_can_giao_QUA_KHU_bi_chan_luc_lap(client):
    """⭐ Chủ chốt 20/08/2026: "nay ngày 20 tôi lập phiếu thì sao mà chọn được ngày 19".

    Bản đầu chỉ CẢNH BÁO, viện lý do "nhập bù đơn hôm qua". Sai: yêu cầu giao là việc SẮP LÀM,
    không phải sổ ghi việc đã làm — hàng chưa ra khỏi kho thì không có gì để nhập bù. Ngày quá
    khứ ở đây chỉ có thể là gõ nhầm, mà gõ nhầm kéo lệch cả hàng chờ giao lẫn thống kê trễ hạn.
    """
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="qk")
    r = client.post("/api/giao-hang/requests", json={
        "order_id": oid,
        "ngay_can_giao": (date.today() - timedelta(days=1)).isoformat(),
        "lines": [{"order_line_id": lid, "qty": 10}],
    }, headers=h)
    assert r.status_code == 400, r.text
    assert "quá khứ" in r.text


def test_ngay_can_giao_HOM_NAY_van_lap_duoc(client):
    """Chặn "trước hôm nay", KHÔNG chặn "hôm nay" — giao trong ngày là chuyện thường.

    Ranh giới lệch một ngày ở đây là chặn mất đúng ca hay dùng nhất.
    """
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="hn")
    r = client.post("/api/giao-hang/requests", json={
        "order_id": oid, "ngay_can_giao": date.today().isoformat(),
        "lines": [{"order_line_id": lid, "qty": 10}],
    }, headers=h)
    assert r.status_code == 201, r.text


def test_SUA_yeu_cau_cung_khong_lui_duoc_ve_qua_khu(client):
    """⭐ Cửa vào THỨ HAI. Chặn lúc lập mà để hở lúc sửa thì coi như không chặn."""
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="qk2")
    yc = _tao_yc(client, h, oid, lid)
    r = client.put(f"/api/giao-hang/requests/{yc['id']}", json={
        "ngay_can_giao": (date.today() - timedelta(days=3)).isoformat(),
    }, headers=h)
    assert r.status_code == 400, r.text
    assert "quá khứ" in r.text


def test_gio_lay_hang_QUA_KHU_bi_chan(client):
    """⭐ Cùng lý do với ngày cần giao: kế hoạch chuyến là việc SẮP LÀM.

    Xếp chuyến lấy hàng lúc 8h sáng hôm qua thì tài xế không có cách nào làm, mà nó kéo lệch cả
    bảng chuyến trong ngày lẫn thống kê trễ hạn.
    """
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="gqk")
    yc = _tao_yc(client, h, oid, lid)
    nv = _tai_xe("Tai xe gqk")
    hom_qua = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    r = client.post("/api/giao-hang/plans", json={
        "request_id": yc["id"], "employee_id": nv,
        "gio_lay_hang": hom_qua,
        "gio_du_kien_giao": (datetime.now(timezone.utc) - timedelta(hours=20)).isoformat(),
    }, headers=h)
    assert r.status_code == 400, r.text
    assert "quá khứ" in r.text


def test_DOI_ke_hoach_ve_gio_qua_khu_bi_chan(client):
    """Cửa vào thứ hai của giờ — chặn lúc lên mà hở lúc đổi thì coi như không chặn."""
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="gqk2")
    yc = _tao_yc(client, h, oid, lid)
    nv = _tai_xe("Tai xe gqk2")
    trip = _len_kh(client, h, yc["id"], nv, lay=8).json()["trip"]["id"]
    r = client.put(f"/api/giao-hang/plans/{trip}", json={
        "gio_lay_hang": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
    }, headers=h)
    assert r.status_code == 400, r.text
    assert "quá khứ" in r.text


def test_doi_MOI_TAI_XE_tren_chuyen_cu_KHONG_bi_chan_oan(client):
    """⭐ Chỉ kiểm giờ NGƯỜI DÙNG VỪA GỬI, không kiểm giờ cũ của chuyến.

    Chuyến xếp từ hôm qua mà nay chỉ đổi tài xế: giờ cũ đã thành quá khứ, kiểm cả cụm là chặn
    oan đúng thao tác vô hại nhất — và lúc đó không ai sửa nổi chuyến trễ.
    """
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="gqk3")
    yc = _tao_yc(client, h, oid, lid)
    nv = _tai_xe("Tai xe gqk3")
    trip = _len_kh(client, h, yc["id"], nv, lay=8).json()["trip"]["id"]

    # Đẩy giờ của chuyến về quá khứ bằng DB (giống chuyến xếp từ hôm qua).
    db = SessionLocal()
    try:
        from app.models.delivery import DeliveryTrip
        t = db.get(DeliveryTrip, trip)
        t.gio_lay_hang = datetime.now(timezone.utc) - timedelta(days=1)
        t.gio_du_kien_giao = datetime.now(timezone.utc) - timedelta(hours=22)
        db.commit()
    finally:
        db.close()

    nv2 = _tai_xe("Tai xe gqk3b")
    r = client.put(f"/api/giao-hang/plans/{trip}", json={"employee_id": nv2}, headers=h)
    assert r.status_code == 200, r.text


def test_kho_LAP_PHIEU_thi_chuyen_hien_da_chuan_bi_xong(client):
    """⭐ Chủ chốt 20/08/2026: kho lập phiếu ⇒ Giao hàng hiện "Kho đã chuẩn bị xong".

    SUY RA từ `stock_vouchers`, không phải cột lưu — kho thao tác trên màn của HỌ và không bấm
    gì trên màn Giao hàng, nên cột lưu ở đây sớm muộn lệch với sổ kho.
    """
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="lp")
    yc = _tao_yc(client, h, oid, lid)
    nv = _tai_xe("Tai xe lp")
    trip = _len_kh(client, h, yc["id"], nv, lay=8).json()["trip"]["id"]
    _gui_yeu_cau_xuat_kho(client, h, trip)

    def co_phieu() -> bool:
        ds = client.get("/api/giao-hang/trips", headers=h).json()["items"]
        return next(t for t in ds if t["id"] == trip)["kho_da_lap_phieu"]

    assert co_phieu() is False, "chưa lập phiếu mà đã báo chuẩn bị xong"

    # Kho lập phiếu — đúng bảng của họ, không đụng gì bên Giao hàng.
    db = SessionLocal()
    try:
        from app.models.stock_request import StockRequest
        from app.models.stock_voucher import VOUCHER_DRAFT, VOUCHER_XUAT, StockVoucher
        req = (db.query(StockRequest)
                 .filter(StockRequest.delivery_trip_id == trip).one())
        db.add(StockVoucher(ma="PX-TEST-LP", loai=VOUCHER_XUAT, request_id=req.id,
                            kho_id=req.kho_id, trang_thai=VOUCHER_DRAFT,
                            ngay=date.today(), nguoi_lap_id=1))
        db.commit()
    finally:
        db.close()

    assert co_phieu() is True, "kho đã lập phiếu mà Giao hàng vẫn báo đang chuẩn bị"


def test_lich_su_trang_thai_MOI_NHAT_LEN_DAU(client):
    """⭐ Chủ chốt 20/08/2026. Việc vừa xảy ra phải nằm trên cùng.

    Chỗ này dễ sai vì router gom lịch sử theo TỪNG CHUYẾN rồi mới theo thời gian.

    Từ 22/08/2026 một yêu cầu chỉ có MỘT chuyến, nên test đi qua nhiều BƯỚC của cùng một chuyến —
    vẫn đủ bắt lỗi xếp sai thứ tự.
    """
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="ls", qty=100)
    yc = _tao_yc(client, h, oid, lid, qty=40)
    nv = _tai_xe("Tai xe ls")

    t1 = _len_kh(client, h, yc["id"], nv, lay=8).json()["trip"]["id"]
    _di_toi_dang_giao(client, h, t1)       # qua 3 mốc: chuẩn bị → đã lấy hàng → đang giao
    r = client.post(f"/api/giao-hang/trips/{t1}/ket-qua", json={
        "ket_qua": "giao_thieu", "km": 10, "nguoi_nhan_thuc_te": "Chi Lan",
        "so_thuc_nhan": [{"order_line_id": lid, "qty": 20}],
    }, headers=h)
    assert r.status_code == 200, r.text

    ds = client.get(f"/api/giao-hang/requests/{yc['id']}", headers=h).json()["lich_su"]
    assert len(ds) >= 2, ds
    moc = [(x["luc"], x["id"]) for x in ds]
    assert moc == sorted(moc, reverse=True), f"lịch sử không xếp mới-nhất-trước: {moc}"


def test_he_TU_KHAI_mat_hang_kho_tu_mo_ta_dong_don(client):
    """⭐ Sản phẩm in là hàng ĐẶT RIÊNG — không có sẵn trong danh mục để mà chọn.

    Bắt người lập "chọn mặt hàng kho" là bắt chọn một thứ chưa tồn tại (chủ chốt 19/08/2026).
    Hệ tự khai, TÊN lấy nguyên văn mô tả trên đơn để kho tìm được.

    Đây là LƯỚI AN TOÀN của Giao hàng cho đơn chốt trước mg 0203 — đường chính là
    `OrderService.confirm()`. Cùng một hàm nên mã sinh ra giống hệt.
    """
    from app.models.vat_lieu_kho import VatTuInAn

    h = _admin(client)
    oid, lid = _don_da_chot(suffix="tk")
    _tao_yc(client, h, oid, lid)

    db = SessionLocal()
    try:
        # Mã là MỘT DÃY CHUNG, không kèm mã khách (21/08/2026 — thành phẩm không thuộc về ai).
        mh = (db.query(VatTuInAn).filter(VatTuInAn.ten == "Hop giay").one_or_none())
        assert mh is not None, "không tự khai mặt hàng nào"
        assert mh.ma.startswith("TP-"), mh.ma
        assert mh.don_vi_gia == "hop"           # đơn vị của dòng đơn
        assert mh.la_thanh_pham, "thiếu cờ ⇒ dòng rơi sang màn Vật tư khác"
    finally:
        db.close()


def test_tu_khai_KHONG_de_ra_ma_trung(client):
    """Get-or-create theo `(khách, tên chuẩn hoá)` ⇒ lập yêu cầu lần hai không đẻ thêm dòng."""
    from app.models.vat_lieu_kho import VatTuInAn

    h = _admin(client)
    oid, lid = _don_da_chot(suffix="tk2", qty=100)
    _tao_yc(client, h, oid, lid, qty=30)
    _tao_yc(client, h, oid, lid, qty=30)

    db = SessionLocal()
    try:
        n = db.query(VatTuInAn).filter(VatTuInAn.la_thanh_pham.is_(True)).count()
        assert n == 1, f"đẻ ra {n} dòng danh mục cho cùng một dòng đơn"
    finally:
        db.close()


def test_dong_xuat_kho_SUY_RA_tu_yeu_cau_giao(client):
    """⭐ Không ai gõ tay dòng hàng — máy lấy đúng mặt hàng + phần CÒN PHẢI GIAO của yêu cầu."""
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="17e", qty=100)
    yc = _tao_yc(client, h, oid, lid, qty=40)
    trip = _len_kh(client, h, yc["id"], _tai_xe("Tai xe 17e")).json()["trip"]["id"]
    r = client.get(f"/api/giao-hang/plans/{trip}/hang-can-xuat", headers=h)
    assert r.status_code == 200, r.text
    ds = r.json()
    assert len(ds) == 1
    assert ds[0]["sl_de_nghi"] == 40, ds      # đúng số của yêu cầu, không phải số của đơn
    assert ds[0]["dvt"] == "hop"   # đơn vị của dòng đơn, không phải đơn vị ai đó gõ
    assert ds[0]["hang_ten"], "thiếu tên mặt hàng thì giao diện hiện mã trần"


def test_gui_yeu_cau_xuat_kho_hai_lan_bi_chan(client):
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="17c")
    yc = _tao_yc(client, h, oid, lid)
    trip = _len_kh(client, h, yc["id"], _tai_xe("Tai xe 17c")).json()["trip"]["id"]
    _gui_yeu_cau_xuat_kho(client, h, trip)
    kho_id, hang_id = _kho_va_mat_hang()
    r = client.post(f"/api/giao-hang/plans/{trip}/yeu-cau-xuat-kho", json={
        "kho_id": kho_id,
        "lines": [{"hang_loai": "vat_tu", "hang_id": hang_id, "dvt": "cai", "sl_de_nghi": 5}],
    }, headers=h)
    # Chặn ở đâu cũng được, miễn là CHẶN: gửi xong chuyến sang "kho đang chuẩn bị" nên lần hai
    # đã vướng luật trạng thái trước khi tới luật trùng. Test khoá HÀNH VI, không khoá câu chữ.
    assert r.status_code == 400, r.text


# =============================================================================================
# Cổng quyền — mỗi ô mở đúng một tab
# =============================================================================================
def test_o_len_ke_hoach_la_cong_that(client):
    """Có Xem + Thao tác mà thiếu ô Lên kế hoạch ⇒ KHÔNG phân công được."""
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="q1")
    yc = _tao_yc(client, h, oid, lid)
    nv = _tai_xe("Tai xe q1")
    tok = _vai("gh-khong-plan", can_read=True, can_create=True)
    r = _len_kh(client, _h(tok), yc["id"], nv)
    assert r.status_code == 403, r.text


def test_o_nhan_vien_giao_hang_la_cong_that(client):
    """Cấp rộng tay mọi thứ trừ đúng ô đang đo — hỏng thì biết chắc do ô đó."""
    tok = _vai("gh-khong-drivers", can_read=True, can_create=True, can_plan=True,
               can_cancel=True)
    r = client.get("/api/giao-hang/nhan-vien", headers=_h(tok))
    assert r.status_code == 403, r.text


def test_ghi_la_ghi_thieu_thao_tac_thi_khong_tao_duoc_yeu_cau(client):
    """Gửi yêu cầu giao cho đơn của CHÍNH MÌNH vẫn đòi ô Thao tác (luật 15/08/2026)."""
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="q3")
    tok = _vai("gh-chi-xem", can_read=True)
    r = client.post("/api/giao-hang/requests", json={
        "order_id": oid, "ngay_can_giao": (date.today() + timedelta(days=2)).isoformat(),
        "lines": [{"order_line_id": lid, "qty": 10}],
    }, headers=_h(tok))
    assert r.status_code == 403, r.text


# =============================================================================================
# Luật lẻ của PRD
# =============================================================================================
def test_chi_tao_duoc_tu_don_DA_CHOT(client):
    h = _admin(client)
    db = SessionLocal()
    try:
        kh = Customer(code="KH-GH-draft", name="Khach nhap")
        db.add(kh)
        db.flush()
        o = Order(order_no="DH-GH-draft", customer_id=kh.id, status="draft")
        o.lines.append(OrderLine(description="Hop", qty=50, don_vi_tinh="hop",
                                 line_total=1, vat_pct_estimate=0))
        db.add(o)
        db.commit()
        oid, lid = o.id, o.lines[0].id
    finally:
        db.close()
    r = client.post("/api/giao-hang/requests", json={
        "order_id": oid, "ngay_can_giao": (date.today() + timedelta(days=2)).isoformat(),
        "lines": [{"order_line_id": lid, "qty": 10}],
    }, headers=h)
    assert r.status_code == 400 and "ĐÃ CHỐT" in r.json()["detail"], r.text


# Test "ngày quá khứ chỉ CẢNH BÁO" GỠ 20/08/2026 — nó ghim luật CŨ.
# Luật mới CHẶN CỨNG, ở cả hai cửa vào; xem ba test `test_ngay_can_giao_*` phía trên.


def test_dia_chi_la_SNAPSHOT_khong_doc_song_tu_don(client):
    """Sửa địa chỉ đơn tháng sau thì phiếu giao cũ vẫn phải giữ địa chỉ đã giao THẬT."""
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="snap")
    yc = _tao_yc(client, h, oid, lid)
    assert yc["dia_chi"] == "12 Le Loi, Q1"
    assert yc["nguoi_nhan"] == "Chi Lan"
    db = SessionLocal()
    try:
        o = db.get(Order, oid)
        o.delivery_address = "999 Doi Roi"
        db.commit()
    finally:
        db.close()
    lai = client.get(f"/api/giao-hang/requests/{yc['id']}", headers=h).json()["request"]
    assert lai["dia_chi"] == "12 Le Loi, Q1", "địa chỉ đọc-sống từ đơn, không phải snapshot"


def test_da_len_ke_hoach_thi_khong_sua_duoc_yeu_cau(client):
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="lock")
    yc = _tao_yc(client, h, oid, lid)
    nv = _tai_xe("Tai xe lock")
    assert _len_kh(client, h, yc["id"], nv).status_code == 201
    r = client.put(f"/api/giao-hang/requests/{yc['id']}",
                   json={"ghi_chu": "doi"}, headers=h)
    assert r.status_code == 400 and "lên kế hoạch" in r.json()["detail"], r.text


def test_giao_thieu_ma_nhan_du_thi_bao_chon_nham(client):
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="gt-du", qty=100)
    yc = _tao_yc(client, h, oid, lid, qty=40)
    nv = _tai_xe("Tai xe gt-du")
    trip = _len_kh(client, h, yc["id"], nv).json()["trip"]["id"]
    _di_toi_dang_giao(client, h, trip)
    r = client.post(f"/api/giao-hang/trips/{trip}/ket-qua", json={
        "ket_qua": "giao_thieu", "km": 20, "nguoi_nhan_thuc_te": "Anh Ba",
        "so_thuc_nhan": [{"order_line_id": lid, "qty": 40}],
    }, headers=h)
    assert r.status_code == 400 and "Giao thành công" in r.json()["detail"], r.text


def _nv_co_tai_khoan(ten: str, username: str, *, phong: str = "Sản xuất", **o) -> int:
    """Hồ sơ NV NỐI với một tài khoản có ô `giao_hang` khai theo `o`. Trả employee_id."""
    from app.models.employee import Employee as _E

    db = SessionLocal()
    try:
        dept = DepartmentRepository(db).get_by_name(phong)
        roles = RoleRepository(db)
        role = roles.create(name=f"Vai {username}", department_id=dept.id)
        if o:
            roles.set_permission(role_id=role.id, module_key=MODULE, scope=SCOPE_ALL, **o)
        users = UserRepository(db)
        u = users.create(username=username, name=ten, password_hash=hash_password("x"))
        users.set_assignment(u, department_id=dept.id, role_id=role.id, is_active=True)
        e = _E(code=f"NV{username[:6].upper()}", full_name=ten, department_id=dept.id,
               hire_date=date(2020, 1, 1), user_id=u.id)
        db.add(e)
        db.commit()
        return e.id
    finally:
        db.close()


def test_roster_CHI_liet_ke_nguoi_vao_duoc_man_giao_hang(client):
    """⭐ Chọn phải người không mở được màn Giao hàng là chuyến TẮC.

    Tài xế còn phải bấm *Đã lấy hàng* rồi nhập kết quả + km. Ai không có ô `giao_hang` thì nhận
    chuyến xong không ai đóng được — bày họ ra ô chọn là bày một lựa chọn hỏng.
    """
    _tai_xe("Tho khong co tai khoan")                       # không có `user_id`
    _nv_co_tai_khoan("Ke toan khong lien quan", "kt-roster")  # có tài khoản, KHÔNG có ô
    co = _nv_co_tai_khoan("Tai xe that", "tx-roster", can_read=True, can_create=True)

    tok = _vai("gh-roster-loc", can_read=True, can_plan=True)
    r = client.get("/api/giao-hang/tai-xe-chon", headers=_h(tok))
    assert r.status_code == 200, r.text
    ten = {x["full_name"] for x in r.json()["items"]}
    assert "Tai xe that" in ten
    assert "Tho khong co tai khoan" not in ten, "người không có tài khoản đăng nhập vẫn lọt"
    assert "Ke toan khong lien quan" not in ten, "người không có ô giao_hang vẫn lọt"
    assert next(x for x in r.json()["items"] if x["id"] == co)["co_thao_tac"] is True


def test_roster_bao_ro_ai_KHONG_ghi_duoc_ket_qua(client):
    """Mở được màn nhưng thiếu ô Thao tác ⇒ vẫn chọn được, nhưng phải báo trước.

    Không loại hẳn: có thể quản lý cố ý phân công rồi tự nhập kết quả hộ. Nhưng phải nói ra lúc
    chọn, đừng để phát hiện khi tài xế đang đứng ở kho.
    """
    eid = _nv_co_tai_khoan("Tai xe chi xem", "tx-chi-xem", can_read=True)
    tok = _vai("gh-roster-canh-bao", can_read=True, can_plan=True)
    r = client.get("/api/giao-hang/tai-xe-chon", headers=_h(tok))
    assert r.status_code == 200, r.text
    ds = r.json()["items"]
    dong = next(x for x in ds if x["id"] == eid)
    assert dong["co_thao_tac"] is False


def test_roster_tai_xe_gac_bang_o_LEN_KE_HOACH_khong_phai_nhan_su(client):
    """⭐ Có đường roster riêng vì `/api/employees` gác bằng ô `nhan_su`.

    Quản lý Giao hàng không nhất thiết có ô đó; bắt cấp thêm `nhan_su` chỉ để chọn tài xế là mở
    toang hồ sơ nhân sự cả công ty. Hệ đã làm y vậy cho màn Đi muộn / về sớm.
    """
    _nv_co_tai_khoan("Tai xe roster", "tx-roster-gate", can_read=True, can_create=True)
    co_plan = _vai("gh-roster-co", can_read=True, can_plan=True)
    r = client.get("/api/giao-hang/tai-xe-chon", headers=_h(co_plan))
    assert r.status_code == 200, r.text
    assert any(x["full_name"] == "Tai xe roster" for x in r.json()["items"]), r.text
    # Chỉ trả id · mã · tên · phòng · hai cờ quyền — KHÔNG phơi lương / BHXH / hồ sơ.
    assert set(r.json()["items"][0]) == {
        "id", "code", "full_name", "department", "co_tai_khoan", "co_thao_tac",
    }

    khong_plan = _vai("gh-roster-khong", can_read=True, can_create=True)
    assert client.get("/api/giao-hang/tai-xe-chon",
                      headers=_h(khong_plan)).status_code == 403


# =============================================================================================
# Real-time cho TÀI XẾ (20/08/2026) — CLAUDE.md: gửi nội bộ phải tức thì
# =============================================================================================
def _bat_day(monkeypatch) -> list[tuple[int, dict]]:
    """Bắt mọi lời gọi `hub.publish`. Trả danh sách `(user_id, event)`."""
    from app import realtime

    ra: list[tuple[int, dict]] = []
    monkeypatch.setattr(realtime.hub, "publish", lambda uid, ev: ra.append((uid, ev)))
    return ra


def _uid_cua(employee_id: int) -> int:
    db = SessionLocal()
    try:
        return db.get(Employee, employee_id).user_id
    finally:
        db.close()


def test_PHAN_CHUYEN_day_realtime_toi_tai_xe(client, monkeypatch):
    """⭐ Tài xế không ngồi canh màn hình — họ đang ở kho hoặc trên đường."""
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="rt1")
    yc = _tao_yc(client, h, oid, lid)
    nv = _nv_co_tai_khoan("Tai xe rt1", "taixert1", can_read=True)

    day = _bat_day(monkeypatch)
    _len_kh(client, h, yc["id"], nv, lay=8)

    cua_toi = [e for uid, e in day if uid == _uid_cua(nv) and e["type"] == "giao_hang_chuyen"]
    assert cua_toi, f"không đẩy gì tới tài xế: {day}"
    assert cua_toi[0]["viec"] == "phan_chuyen"
    assert cua_toi[0]["request_code"] == yc["code"]


def test_GUI_KHO_day_realtime_toi_tai_xe(client, monkeypatch):
    """Chủ chốt 20/08/2026: "mỗi lần gửi đơn xuống kho cũng phải thông báo đến tài xế"."""
    h = _admin(client)
    oid, lid = _don_da_chot(suffix="rt2")
    yc = _tao_yc(client, h, oid, lid)
    nv = _nv_co_tai_khoan("Tai xe rt2", "taixert2", can_read=True)
    trip = _len_kh(client, h, yc["id"], nv, lay=8).json()["trip"]["id"]

    day = _bat_day(monkeypatch)
    _gui_yeu_cau_xuat_kho(client, h, trip)

    viec = [e["viec"] for uid, e in day if uid == _uid_cua(nv)]
    assert "gui_kho" in viec, f"không báo tài xế lúc gửi kho: {day}"


def test_KHO_LAP_PHIEU_day_realtime_toi_tai_xe(client, monkeypatch):
    """⭐ Mốc THẬT SỰ làm tài xế lên đường — và nó xảy ra bên màn Kho.

    Móc nằm ở `services/delivery_notify`, `routers/kho_voucher` chỉ gọi một dòng. Hàm đó tự nuốt
    lỗi nên không đường nào làm hỏng việc lập phiếu của kho.
    """
    from app.services.delivery_notify import bao_tai_xe_kho_lap_phieu
    from app.models.stock_request import StockRequest

    h = _admin(client)
    oid, lid = _don_da_chot(suffix="rt3")
    yc = _tao_yc(client, h, oid, lid)
    nv = _nv_co_tai_khoan("Tai xe rt3", "taixert3", can_read=True)
    trip = _len_kh(client, h, yc["id"], nv, lay=8).json()["trip"]["id"]
    _gui_yeu_cau_xuat_kho(client, h, trip)

    db = SessionLocal()
    try:
        req_id = db.query(StockRequest).filter(StockRequest.delivery_trip_id == trip).one().id
    finally:
        db.close()

    day = _bat_day(monkeypatch)
    db = SessionLocal()
    try:
        bao_tai_xe_kho_lap_phieu(db, req_id, "PX-RT3")
    finally:
        db.close()

    cua_toi = [e for uid, e in day if uid == _uid_cua(nv)]
    assert cua_toi and cua_toi[0]["viec"] == "kho_xong", f"không báo tài xế lúc kho lập phiếu: {day}"


def test_lap_phieu_VAT_TU_THUONG_khong_de_ra_tieng_dong_nao(client, monkeypatch):
    """Mọi phiếu vật tư thường đi qua cùng móc đó — không được sinh thông báo nào."""
    from app.services.delivery_notify import bao_tai_xe_kho_lap_phieu

    day = _bat_day(monkeypatch)
    db = SessionLocal()
    try:
        bao_tai_xe_kho_lap_phieu(db, None, "PX-THUONG")
        bao_tai_xe_kho_lap_phieu(db, 999999, "PX-THUONG")
    finally:
        db.close()
    assert day == [], day


# =============================================================================================
# Tab Nhân viên — BỘ PHẬN giao hàng + KM theo THÁNG (20/08/2026)
# =============================================================================================
def _bat_co_giao_hang(phong: str = "Sản xuất") -> None:
    db = SessionLocal()
    try:
        depts = DepartmentRepository(db)
        depts.set_la_giao_hang(depts.get_by_name(phong), True)
    finally:
        db.close()


def test_nhan_vien_liet_ke_theo_BO_PHAN_ke_ca_nguoi_CHUA_co_chuyen(client):
    """⭐ Tài xế mới tuyển phải hiện ra — không hiện thì không ai phân chuyến cho họ được.

    Trước 20/08/2026 tab này bỏ qua ai chưa có chuyến nào.
    """
    h = _admin(client)
    _bat_co_giao_hang()
    nv = _tai_xe("Tai xe moi tuyen")

    ds = client.get("/api/giao-hang/nhan-vien", headers=h).json()["items"]
    assert any(x["employee_id"] == nv for x in ds),         f"nhân viên thuộc bộ phận giao hàng nhưng không hiện: {[x['ho_ten'] for x in ds]}"


def test_KM_THANG_cong_ca_chuyen_NGAY_KHAC_trong_thang(client):
    """⭐ Chuyến xong HÔM KHÁC trong tháng phải vào cột THÁNG, và KHÔNG vào cột NGÀY.

    Chỉ kiểm "có cột tong_km_thang" thì hàm tháng tính y hệt hàm ngày vẫn xanh — đã cắn đúng vậy
    lúc viết test đầu (20/08/2026).
    """
    from app.models.delivery import DeliveryTrip

    h = _admin(client)
    _bat_co_giao_hang()
    oid, lid = _don_da_chot(suffix="kmt")
    yc = _tao_yc(client, h, oid, lid)
    nv = _tai_xe("Tai xe km thang")
    trip = _len_kh(client, h, yc["id"], nv, lay=8).json()["trip"]["id"]

    # NGÀY KHÁC nhưng CÙNG THÁNG với hôm nay. Mọi tháng đều có ít nhất 28 ngày nên cặp (1, 2)
    # luôn cho một ngày khác hôm nay — không phụ thuộc hôm nay là ngày mấy.
    hom = date.today()
    ngay_khac = hom.replace(day=2 if hom.day == 1 else 1)

    db = SessionLocal()
    try:
        t = db.get(DeliveryTrip, trip)
        t.trang_thai = "thanh_cong"
        t.km = 77
        t.thoi_gian_ket_thuc = datetime.combine(ngay_khac, datetime.min.time(),
                                                tzinfo=timezone.utc)
        db.commit()
    finally:
        db.close()

    ds = client.get("/api/giao-hang/nhan-vien", headers=h).json()["items"]
    dong = next(x for x in ds if x["employee_id"] == nv)
    assert dong["tong_km_thang"] == 77, dong
    assert dong["tong_km"] == 0, f"chuyến hôm khác KHÔNG được vào cột ngày: {dong}"


def test_LOC_THEO_THANG_doi_cot_thang_nhung_KHONG_doi_cot_ngay(client):
    """⭐ Chủ chốt 20/08/2026: "cho nó filter theo tháng, tôi muốn xem tháng sau như nào".

    `ngay` và `thang` là HAI tham số rời, cố ý. Gộp một tham số thì xem tháng sau là cột
    "hôm nay" nhảy sang ngày 1 tháng sau — một con số không có nghĩa gì.
    """
    from app.models.delivery import DeliveryTrip

    h = _admin(client)
    _bat_co_giao_hang()
    oid, lid = _don_da_chot(suffix="loc")
    yc = _tao_yc(client, h, oid, lid)
    nv = _tai_xe("Tai xe loc thang")
    trip = _len_kh(client, h, yc["id"], nv, lay=8).json()["trip"]["id"]

    hom = date.today()
    # Chuyến xong THÁNG TRƯỚC — tháng này không được thấy, xem tháng trước thì phải thấy.
    thang_truoc = (hom.replace(day=1) - timedelta(days=1))
    db = SessionLocal()
    try:
        t = db.get(DeliveryTrip, trip)
        t.trang_thai = "thanh_cong"
        t.km = 55
        t.thoi_gian_ket_thuc = datetime.combine(thang_truoc, datetime.min.time(),
                                                tzinfo=timezone.utc)
        db.commit()
    finally:
        db.close()

    def km_thang(param: str | None) -> int:
        duong = "/api/giao-hang/nhan-vien" + (f"?thang={param}" if param else "")
        ds = client.get(duong, headers=h).json()["items"]
        return next(x for x in ds if x["employee_id"] == nv)["tong_km_thang"]

    assert km_thang(None) == 0, "tháng này không có chuyến nào mà vẫn cộng"
    assert km_thang(f"{thang_truoc:%Y-%m}") == 55, "xem tháng trước mà không thấy chuyến của nó"


def test_thang_sai_dinh_dang_bi_chan_o_cong(client):
    """`thang` phải đúng `YYYY-MM` — chuỗi lạ thì 422 ở cổng, không rơi vào `int()` rồi 500."""
    h = _admin(client)
    r = client.get("/api/giao-hang/nhan-vien?thang=thang-sau", headers=h)
    assert r.status_code == 422, r.text


def test_O_CHON_TAI_XE_va_TAB_NHAN_VIEN_cung_MOT_danh_sach(client):
    """⭐ Chủ chốt 20/08/2026: "lên đơn giao hàng chỉ lấy nhân viên trong tab nhân viên".

    Trước đó hai chỗ trả lời câu "ai là tài xế" bằng hai luật: tab lọc theo BỘ PHẬN, ô chọn lọc
    theo QUYỀN RBAC — nên ô chọn mời cả Admin và thủ kho, tài xế thật lẫn giữa họ.
    """
    h = _admin(client)
    _bat_co_giao_hang()                       # bật cờ cho phòng "Sản xuất"
    tx = _tai_xe("Tai xe that")               # thuộc phòng đã bật cờ
    # Người CÓ quyền giao hàng nhưng KHÔNG thuộc bộ phận giao hàng — đúng ca Admin/thủ kho.
    ngoai = _nv_co_tai_khoan("Nguoi ngoai bp", "ngoaibp", phong="Kho", can_read=True)

    chon = {x["id"] for x in client.get("/api/giao-hang/tai-xe-chon", headers=h).json()["items"]}
    tab = {x["employee_id"] for x in client.get("/api/giao-hang/nhan-vien", headers=h).json()["items"]}

    assert tx in chon, "tài xế thật không có trong ô chọn"
    assert ngoai not in chon, "ô chọn vẫn mời người ngoài bộ phận giao hàng"
    assert chon == tab, f"ô chọn và tab Nhân viên lệch nhau: chỉ ở ô chọn={chon - tab}, chỉ ở tab={tab - chon}"


def test_o_chon_van_MOI_nguoi_CHUA_co_tai_khoan(client):
    """Tài xế chưa được cấp login vẫn phân chuyến được — `da-lay-hang`/`ket-qua` gác bằng ô
    Thao tác nên quản lý bấm hộ được, chuyến KHÔNG tắc.

    Chỉ đánh dấu `co_thao_tac=False` để người phân công biết ai tự bấm được.
    """
    h = _admin(client)
    _bat_co_giao_hang()
    tx = _tai_xe("Tai xe chua co login")
    ds = client.get("/api/giao-hang/tai-xe-chon", headers=h).json()["items"]
    dong = next((x for x in ds if x["id"] == tx), None)
    assert dong is not None, "loại mất tài xế chưa có tài khoản"
    assert dong["co_thao_tac"] is False, dong


def test_CHUA_khai_bo_phan_thi_LUI_ve_luat_cu(client):
    """Chưa tick phòng nào ⇒ ô chọn không được RỖNG, không thì không ai phân chuyến được nữa.

    Lùi về luật cũ (có tài khoản mở được màn Giao hàng) — cùng khuôn `la_kinh_doanh`.
    """
    h = _admin(client)
    nv = _nv_co_tai_khoan("Co quyen giao", "coquyengh", can_read=True)
    ds = client.get("/api/giao-hang/tai-xe-chon", headers=h).json()["items"]
    assert any(x["id"] == nv for x in ds), f"ô chọn rỗng khi chưa khai bộ phận: {ds}"
