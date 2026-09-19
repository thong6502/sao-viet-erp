"""Lượt xe — tiền khoán km theo CHẶNG (`docs/prd-khoan-km-giao-hang.md` §14, chủ chốt 18/09/2026).

Sổ hành trình của công ty ghi mỗi dòng là MỘT CHẶNG (điểm này → điểm kế), số km lấy từ đồng hồ, đơn
giá tra theo km của RIÊNG chặng đó; lượt về kho cũng là một chặng. Hệ thống trước đây chỉ có một ô km
cho cả chuyến ⇒ lượt về cộng vào chuyến, tra bậc theo tổng km, giá rẻ hơn (đối chiếu T08: hụt ~13%).

Chủ chốt: tiền theo chặng của LƯỢT XE; tài xế ghi SỐ ĐỒNG HỒ ở mỗi điểm (xuất phát · tới từng khách ·
về kho), máy trừ ra km; người lên đơn giao hàng lập lượt. Số viết tay lấy từ sheet `xe tải a Tùng`
tháng 8 (xe 3,5T, thang thường 18.000 · 11.200 · 8.200 · 7.200 …, kíp Tùng 60 / Triều 40).
"""
from __future__ import annotations

from datetime import date

from app.db import SessionLocal
from app.models.delivery import DeliveryTrip, LuotXe
from app.services.khoan_km_service import KhoanKmService
from tests.test_giao_hang_api import _admin, _don_da_chot, _gio, _gui_yeu_cau_xuat_kho, _tao_yc
from tests.test_khoan_km_giao_hang import PHONG_GH, _bat_khoi_giao_hang, _tai_xe
from tests.test_khoan_km_theo_muc import _muc_co_gia, _tao_xe

GOC = "/api/giao-hang"


# --- dựng cảnh -------------------------------------------------------------------------------
def _canh(client, ma_xe: str = "51D-853.66"):
    """Phòng Giao hàng (60/40) + mức thang thường + xe 3,5T + kíp Tùng/Triều. Trả (h, tx, px, xe)."""
    h = _admin(client)
    _bat_khoi_giao_hang(tx=60, px=40)
    tx = _tai_xe(f"Tung {ma_xe}", phong=PHONG_GH)
    px = _tai_xe(f"Trieu {ma_xe}", phong=PHONG_GH)
    muc = _muc_co_gia(client, h, f"Muc {ma_xe}")
    xe = _tao_xe(client, h, ma_xe, f"Xe {ma_xe}", 3.5, muc)
    return h, tx, px, xe


def _len_don(client, h, *, suffix, tx, xe, luot="moi", px=None, lay=8, giao=11, cho=201):
    """Đơn → yêu cầu → lên đơn giao hàng vào lượt (`"moi"` hoặc id lượt đang mở)."""
    oid, lid = _don_da_chot(suffix=suffix)
    yc = _tao_yc(client, h, oid, lid)
    body = {"request_id": yc["id"], "employee_id": tx, "vehicle_id": xe,
            "gio_lay_hang": _gio(lay), "gio_du_kien_giao": _gio(giao)}
    if luot is not None:
        body["luot_xe_id"] = luot
    if px is not None:
        body["phu_xe_employee_id"] = px
    r = client.post(f"{GOC}/plans", json=body, headers=h)
    assert r.status_code == cho, r.text
    return r.json()["trip"] if r.status_code == 201 else r.json()


def _lay_hang(client, h, trip_id):
    _gui_yeu_cau_xuat_kho(client, h, trip_id)
    r = client.post(f"{GOC}/trips/{trip_id}/da-lay-hang", headers=h)
    assert r.status_code == 200, r.text


def _bat_dau(client, h, trip_id, xuat_phat=None, *, cho=200):
    body = {"so_dong_ho_xuat_phat": xuat_phat} if xuat_phat is not None else None
    r = client.post(f"{GOC}/trips/{trip_id}/bat-dau-giao", json=body, headers=h)
    assert r.status_code == cho, r.text
    return r.json()


def _ket_qua(client, h, trip_id, so, *, ket_qua="thanh_cong", cho=200, **kw):
    body = {"ket_qua": ket_qua, "so_dong_ho": so, **kw}
    if ket_qua == "that_bai":
        body.update(ly_do_that_bai="Khach vang", huong_xu_ly="tra_ve")
    else:
        body.setdefault("nguoi_nhan_thuc_te", "Chi Lan")
    r = client.post(f"{GOC}/trips/{trip_id}/ket-qua", json=body, headers=h)
    assert r.status_code == cho, r.text
    return r.json()


def _ve_kho(client, h, luot_id, so, *, cho=200, **kw):
    r = client.post(f"{GOC}/luot-xe/{luot_id}/ve-kho", json={"so_dong_ho": so, **kw}, headers=h)
    assert r.status_code == cho, r.text
    return r.json()


def _chuyen(trip_id) -> DeliveryTrip:
    db = SessionLocal()
    try:
        t = db.get(DeliveryTrip, trip_id)
        db.expunge(t)
        return t
    finally:
        db.close()


def _luot(luot_id) -> LuotXe:
    db = SessionLocal()
    try:
        x = db.get(LuotXe, luot_id)
        if x is not None:
            db.expunge(x)
        return x
    finally:
        db.close()


def _tien_ky() -> dict[int, float]:
    db = SessionLocal()
    try:
        hom_nay = date.today()
        return KhoanKmService(db).theo_ky(hom_nay.year, hom_nay.month)
    finally:
        db.close()


def _vong_young_poong_aobo(client):
    """⭐ Vòng 01/08 của xe Tùng: SVN (91424) → Young Poong (91445) → AOBO (91452) → SVN (91469)."""
    h, tx, px, xe = _canh(client)
    a = _len_don(client, h, suffix="yp", tx=tx, px=px, xe=xe)
    b = _len_don(client, h, suffix="aobo", tx=tx, px=px, xe=xe, luot=a["luot"]["id"])
    for t in (a, b):
        _lay_hang(client, h, t["id"])
    _bat_dau(client, h, a["id"], 91424)
    _bat_dau(client, h, b["id"])
    _ket_qua(client, h, a["id"], 91445)
    _ket_qua(client, h, b["id"], 91452)
    return h, tx, px, a, b


# =============================================================================================
# Lập lượt — người lên đơn giao hàng
# =============================================================================================
def test_LEN_DON_luot_moi_roi_GHEP_chuyen_thu_hai_cung_tai_xe_khong_bao_trung_gio(client):
    """Gom đơn một vòng: hai chuyến cùng tài xế, cùng khung giờ, cùng lượt ⇒ KHÔNG phải trùng lịch."""
    h, tx, px, xe = _canh(client)
    a = _len_don(client, h, suffix="g1", tx=tx, px=px, xe=xe)
    assert a["luot"]["code"].startswith("LX-") and a["luot"]["so_diem"] == 1
    b = _len_don(client, h, suffix="g2", tx=tx, px=px, xe=xe, luot=a["luot"]["id"])
    assert b["luot"]["id"] == a["luot"]["id"] and b["luot"]["so_diem"] == 2

    mo = client.get(f"{GOC}/luot-xe", params={"vehicle_id": xe}, headers=h).json()["items"]
    assert [(x["code"], x["so_diem"], x["da_xuat_phat"]) for x in mo] == [(a["luot"]["code"], 2, False)]


def test_hai_luot_KHAC_nhau_cung_gio_van_la_trung_lich(client):
    h, tx, _px, xe = _canh(client)
    _len_don(client, h, suffix="t1", tx=tx, xe=xe)
    r = _len_don(client, h, suffix="t2", tx=tx, xe=xe, cho=400)
    assert "trùng giờ" in r["detail"]


def test_GHEP_vao_luot_cua_xe_KHAC_bi_chan(client):
    h, tx, _px, xe = _canh(client)
    muc = _muc_co_gia(client, h, "Muc xe hai")
    xe2 = _tao_xe(client, h, "61C-532.70", "Xe a Giang", 2.5, muc)
    a = _len_don(client, h, suffix="k1", tx=tx, xe=xe)
    r = _len_don(client, h, suffix="k2", tx=tx, xe=xe2, luot=a["luot"]["id"], lay=13, giao=15,
                 cho=400)
    assert "xe khác" in r["detail"]


def test_DOI_XE_rieng_mot_chuyen_trong_luot_bi_chan(client):
    h, tx, _px, xe = _canh(client)
    muc = _muc_co_gia(client, h, "Muc xe doi")
    xe2 = _tao_xe(client, h, "51K-774.04", "Xe a Viet", 5, muc)
    a = _len_don(client, h, suffix="dx", tx=tx, xe=xe)
    r = client.put(f"{GOC}/plans/{a['id']}", json={"vehicle_id": xe2}, headers=h)
    assert r.status_code == 400 and "không đổi xe riêng" in r.json()["detail"], r.text


def test_HUY_ke_hoach_rut_chuyen_khoi_luot_luot_rong_thi_xoa(client):
    h, tx, _px, xe = _canh(client)
    a = _len_don(client, h, suffix="h1", tx=tx, xe=xe)
    b = _len_don(client, h, suffix="h2", tx=tx, xe=xe, luot=a["luot"]["id"])
    r = client.post(f"{GOC}/plans/{b['id']}/huy", json={"ly_do": "Khach doi ngay"}, headers=h)
    assert r.status_code == 200 and r.json()["luot"] is None, r.text
    assert _luot(a["luot"]["id"]) is not None
    client.post(f"{GOC}/plans/{a['id']}/huy", json={"ly_do": "Khach huy"}, headers=h)
    assert _luot(a["luot"]["id"]) is None, "lượt không còn điểm nào mà vẫn nằm đó"


# =============================================================================================
# Số đồng hồ — tài xế
# =============================================================================================
def test_BAT_DAU_chuyen_dau_phai_co_so_xuat_phat_chuyen_sau_khong_can(client):
    h, tx, _px, xe = _canh(client)
    a = _len_don(client, h, suffix="xp1", tx=tx, xe=xe)
    b = _len_don(client, h, suffix="xp2", tx=tx, xe=xe, luot=a["luot"]["id"])
    _lay_hang(client, h, a["id"])
    _lay_hang(client, h, b["id"])
    loi = _bat_dau(client, h, a["id"], cho=400)
    assert "xuất phát" in loi["detail"]
    ra = _bat_dau(client, h, a["id"], 91388)
    assert ra["luot"]["so_dong_ho_xuat_phat"] == 91388
    _bat_dau(client, h, b["id"])      # chuyến sau cùng lượt: không phải nhập lại


def test_KET_QUA_trong_luot_ghi_so_dong_ho_khong_go_km(client):
    h, tx, _px, xe = _canh(client)
    a = _len_don(client, h, suffix="kq", tx=tx, xe=xe)
    _lay_hang(client, h, a["id"])
    _bat_dau(client, h, a["id"], 1000)
    r = client.post(f"{GOC}/trips/{a['id']}/ket-qua",
                    json={"ket_qua": "thanh_cong", "km": 18, "nguoi_nhan_thuc_te": "Chi Lan"},
                    headers=h)
    assert r.status_code == 400 and "số đồng hồ" in r.json()["detail"], r.text
    assert "nhỏ hơn số lúc xuất phát" in _ket_qua(client, h, a["id"], 999, cho=400)["detail"]
    assert "lớn bất thường" in _ket_qua(client, h, a["id"], 1501, cho=400)["detail"]
    ra = _ket_qua(client, h, a["id"], 1501, xac_nhan_km_lon=True)
    assert ra["km"] == 501 and ra["luot"]["so_dong_ho"] == 1501


def test_CHANG_theo_SO_DONG_HO_khong_theo_thu_tu_len_don(client):
    """Ghé khách nào trước là chuyện ngoài đường — ghi B trước A thì chặng vẫn tính theo đồng hồ."""
    h, tx, _px, xe = _canh(client)
    a = _len_don(client, h, suffix="o1", tx=tx, xe=xe)
    b = _len_don(client, h, suffix="o2", tx=tx, xe=xe, luot=a["luot"]["id"])
    for t in (a, b):
        _lay_hang(client, h, t["id"])
    _bat_dau(client, h, a["id"], 1000)
    _bat_dau(client, h, b["id"])
    _ket_qua(client, h, b["id"], 1030)
    assert _chuyen(b["id"]).km == 30
    _ket_qua(client, h, a["id"], 1010)            # ghi muộn: A nằm giữa xuất phát và B
    assert _chuyen(a["id"]).km == 10 and _chuyen(b["id"]).km == 20


def test_VE_KHO_bi_chan_khi_con_diem_chua_co_ket_qua_hoac_so_lui(client):
    h, tx, _px, xe = _canh(client)
    a = _len_don(client, h, suffix="v1", tx=tx, xe=xe)
    b = _len_don(client, h, suffix="v2", tx=tx, xe=xe, luot=a["luot"]["id"])
    for t in (a, b):
        _lay_hang(client, h, t["id"])
    _bat_dau(client, h, a["id"], 2000)
    _ket_qua(client, h, a["id"], 2010)
    luot = a["luot"]["id"]
    assert "chưa nhập kết quả" in _ve_kho(client, h, luot, 2050, cho=400)["detail"]
    _bat_dau(client, h, b["id"])
    _ket_qua(client, h, b["id"], 2020)
    assert "nhỏ hơn số ở điểm giao cuối" in _ve_kho(client, h, luot, 2015, cho=400)["detail"]
    assert _ve_kho(client, h, luot, 2040)["km_ve_kho"] == 20
    assert "đã về kho" in _ve_kho(client, h, luot, 2041, cho=400)["detail"]


# =============================================================================================
# Tiền — số viết tay từ sổ xe Tùng tháng 8
# =============================================================================================
def test_VONG_BA_CHANG_ra_dung_441000_nhu_so_hanh_trinh(client):
    """⭐ 21 km × 8.200 + 7 km × 11.200 + 17 km × 11.200 (về kho) = 441.000; kíp 60/40.

    Gộp cả vòng 45 km vào một ô như trước thì 45 × 7.200 = 324.000 — hụt 117.000."""
    h, tx, px, a, b = _vong_young_poong_aobo(client)
    ta, tb = _chuyen(a["id"]), _chuyen(b["id"])
    assert (ta.km, float(ta.don_gia_km)) == (21, 8200)
    assert (tb.km, float(tb.don_gia_km)) == (7, 11200)

    # Bảng chuyến: nút "Về kho" nằm ở điểm cuối (số đồng hồ lớn nhất) khi mọi điểm đã có kết quả.
    ds = {t["id"]: t for t in client.get(f"{GOC}/trips", headers=h).json()["items"]}
    assert ds[b["id"]]["luot"]["cho_ve_kho"] and ds[b["id"]]["luot"]["la_diem_cuoi"]
    assert not ds[a["id"]]["luot"]["la_diem_cuoi"]

    ve = _ve_kho(client, h, a["luot"]["id"], 91469)
    assert ve["km_ve_kho"] == 17
    luot = _luot(a["luot"]["id"])
    assert float(luot.don_gia_ve_kho) == 11200 and luot.ve_kho_trip_id == b["id"]

    tien = _tien_ky()
    assert round(tien[tx]) == 264_600 and round(tien[px]) == 176_400
    assert round(tien[tx] + tien[px]) == 441_000


def test_MOT_DON_di_va_ve_la_HAI_chang(client):
    """SVN → Hoàng Long → SVN = 2 × 18 km × 11.200 = 403.200 (gộp 36 km: 36 × 8.200 = 295.200).
    Đi một mình ⇒ tài xế ăn trọn."""
    h, tx, _px, xe = _canh(client)
    a = _len_don(client, h, suffix="hl", tx=tx, xe=xe)
    _lay_hang(client, h, a["id"])
    _bat_dau(client, h, a["id"], 91388)
    _ket_qua(client, h, a["id"], 91406)
    _ve_kho(client, h, a["luot"]["id"], 91424)
    assert round(_tien_ky()[tx]) == 403_200


def test_BANG_DOI_CHIEU_co_dong_VE_KHO_va_cong_dung_bang_tien_luong(client):
    h, tx, px, a, _b = _vong_young_poong_aobo(client)
    _ve_kho(client, h, a["luot"]["id"], 91469)
    db = SessionLocal()
    try:
        hom_nay = date.today()
        dong = KhoanKmService(db).chi_tiet(tx, hom_nay.year, hom_nay.month)
    finally:
        db.close()
    assert round(sum(d["thanh_tien"] for d in dong)) == 264_600
    ve = [d for d in dong if (d.get("ghi_chu") or "").startswith("Về kho")]
    assert len(ve) == 1 and ve[0]["km"] == 17 and round(ve[0]["thanh_tien"]) == 114_240


def test_XE_CHAY_NGOAI_SO_duoc_nhac_khi_luot_sau_xuat_phat_xa_hon_so_cuoi(client):
    h, tx, _px, xe = _canh(client)
    a = _len_don(client, h, suffix="ns1", tx=tx, xe=xe)
    _lay_hang(client, h, a["id"])
    _bat_dau(client, h, a["id"], 5000)
    _ket_qua(client, h, a["id"], 5010)
    _ve_kho(client, h, a["luot"]["id"], 5020)
    b = _len_don(client, h, suffix="ns2", tx=tx, xe=xe, lay=13, giao=15)
    assert b["luot"]["id"] != a["luot"]["id"]
    _lay_hang(client, h, b["id"])
    assert b["luot"]["goi_y_xuat_phat"] == 5020
    ra = _bat_dau(client, h, b["id"], 5050)
    assert any("ngoài sổ 30 km" in c for c in ra["canh_bao"]), ra["canh_bao"]


# =============================================================================================
# Giao thất bại vẫn ra tiền — xe đã lăn bánh (chủ chốt 24/08/2026)
# =============================================================================================
def test_GIAO_THAT_BAI_trong_luot_van_tinh_chang(client):
    h, tx, _px, xe = _canh(client)
    a = _len_don(client, h, suffix="tb", tx=tx, xe=xe)
    _lay_hang(client, h, a["id"])
    _bat_dau(client, h, a["id"], 3000)
    _ket_qua(client, h, a["id"], 3018, ket_qua="that_bai")
    assert _chuyen(a["id"]).trang_thai == "dang_tra_hang"
    _ve_kho(client, h, a["luot"]["id"], 3036)
    assert round(_tien_ky()[tx]) == 403_200


def test_GIAO_THAT_BAI_ngoai_luot_cung_ra_tien_sua_loi_truoc(client):
    """Trước 18/09/2026 chuyến thất bại chuyển ngay sang `dang_tra_hang` rồi `da_tra_hang` — mà bộ lọc
    tiền chỉ đếm `that_bai`, nên chuyến thất bại KHÔNG BAO GIỜ ra tiền, ngược câu chủ chốt."""
    h, tx, _px, xe = _canh(client)
    a = _len_don(client, h, suffix="tbc", tx=tx, xe=xe, luot=None)
    assert a["luot"] is None
    _lay_hang(client, h, a["id"])
    _bat_dau(client, h, a["id"])
    r = client.post(f"{GOC}/trips/{a['id']}/ket-qua", json={
        "ket_qua": "that_bai", "km": 18, "ly_do_that_bai": "Khach vang", "huong_xu_ly": "tra_ve"},
        headers=h)
    assert r.status_code == 200, r.text
    assert round(_tien_ky()[tx]) == 18 * 11200


def test_CHUYEN_NGOAI_LUOT_giu_duong_cu_mot_o_km(client):
    h, tx, _px, xe = _canh(client)
    a = _len_don(client, h, suffix="cu", tx=tx, xe=xe, luot=None)
    _lay_hang(client, h, a["id"])
    _bat_dau(client, h, a["id"])
    r = client.post(f"{GOC}/trips/{a['id']}/ket-qua",
                    json={"ket_qua": "thanh_cong", "km": 36, "nguoi_nhan_thuc_te": "Chi Lan"},
                    headers=h)
    assert r.status_code == 200 and r.json()["km"] == 36, r.text
    assert round(_tien_ky()[tx]) == 36 * 8200


# =============================================================================================
# Nhắc trước chốt lương · tổng km tab Nhân viên giao hàng
# =============================================================================================
def test_CANH_BAO_truoc_chot_luong_khi_con_luot_chua_ve_kho(client):
    """Quên bấm Về kho ⇒ chặng về kho không có km, không ra tiền — phải NÓI trước khi chốt kỳ."""
    from app.routers.payroll import _canh_bao_chot

    h, tx, _px, xe = _canh(client)
    a = _len_don(client, h, suffix="cb", tx=tx, xe=xe)
    _lay_hang(client, h, a["id"])
    _bat_dau(client, h, a["id"], 7000)
    _ket_qua(client, h, a["id"], 7018)
    hom_nay = date.today()
    db = SessionLocal()
    try:
        ma = KhoanKmService(db).luot_chua_ve_kho(hom_nay.year, hom_nay.month)
    finally:
        db.close()
    assert ma == [a["luot"]["code"]]
    cau = _canh_bao_chot([], luot_chua_ve_kho=ma) or ""
    assert "1 lượt xe chưa ghi số đồng hồ về kho" in cau and a["luot"]["code"] in cau

    _ve_kho(client, h, a["luot"]["id"], 7036)
    db = SessionLocal()
    try:
        assert KhoanKmService(db).luot_chua_ve_kho(hom_nay.year, hom_nay.month) == []
    finally:
        db.close()


def test_TONG_KM_tab_nhan_vien_gom_ca_chang_ve_kho(client):
    h, tx, _px, xe = _canh(client)
    a = _len_don(client, h, suffix="tk", tx=tx, xe=xe)
    _lay_hang(client, h, a["id"])
    _bat_dau(client, h, a["id"], 8000)
    _ket_qua(client, h, a["id"], 8018)
    _ve_kho(client, h, a["luot"]["id"], 8036)
    thang = date.today().strftime("%Y-%m")
    ds = client.get(f"{GOC}/nhan-vien", params={"thang": thang}, headers=h).json()["items"]
    dong = next(d for d in ds if d["employee_id"] == tx)
    assert dong["tong_km_thang"] == 36, dong


# =============================================================================================
# Gom theo lượt — MỘT lần bấm (chủ chốt 18/09/2026: giữ mỗi yêu cầu MỘT phiếu, lượt gom nhiều phiếu)
# =============================================================================================
def _yc(client, h, suffix) -> int:
    oid, lid = _don_da_chot(suffix=suffix)
    return _tao_yc(client, h, oid, lid)["id"]


def _len_luot(client, h, request_ids, *, tx, xe, luot="moi", px=None, lay=8, giao=11, cho=201):
    body = {"request_ids": request_ids, "employee_id": tx, "vehicle_id": xe,
            "gio_lay_hang": _gio(lay), "gio_du_kien_giao": _gio(giao), "luot_xe_id": luot}
    if px is not None:
        body["phu_xe_employee_id"] = px
    r = client.post(f"{GOC}/luot-xe", json=body, headers=h)
    assert r.status_code == cho, r.text
    return r.json()


def _ca_luot(client, h, luot_id, viec, body=None, *, cho=200):
    r = client.post(f"{GOC}/luot-xe/{luot_id}/{viec}", json=body, headers=h)
    assert r.status_code == cho, (viec, r.text)
    return r.json()


def test_LEN_LUOT_nhieu_yeu_cau_mot_lan_moi_yeu_cau_mot_chuyen_chung_mot_luot(client):
    """Tick 3 yêu cầu → một lần bấm ⇒ 3 chuyến, cùng một lượt, cùng kíp, không báo trùng giờ."""
    h, tx, px, xe = _canh(client)
    ids = [_yc(client, h, f"b{i}") for i in range(3)]
    kq = _len_luot(client, h, ids, tx=tx, px=px, xe=xe)
    assert kq["code"].startswith("LX-")
    assert [t["request_id"] for t in kq["trips"]] == ids
    assert {t["luot"]["id"] for t in kq["trips"]} == {kq["luot_id"]}
    assert {t["luot"]["so_diem"] for t in kq["trips"]} == {3}
    assert {(t["employee_id"], t["phu_xe_employee_id"], t["vehicle_id"]) for t in kq["trips"]} \
        == {(tx, px, xe)}

    # Một lô nữa GHÉP vào chính lượt đó (xe đang ở kho, bốc thêm đơn).
    them = _len_luot(client, h, [_yc(client, h, "b3")], tx=tx, px=px, xe=xe, luot=kq["luot_id"])
    assert them["luot_id"] == kq["luot_id"] and them["trips"][0]["luot"]["so_diem"] == 4


def test_LEN_LUOT_mot_yeu_cau_hong_thi_CA_LO_KHONG_LUU(client):
    """Tất cả hoặc không gì — lưu nửa lô thì người lên đơn phải tự dò cái nào đã vào lượt."""
    h, tx, px, xe = _canh(client)
    ok = _yc(client, h, "c1")
    da_co = _len_don(client, h, suffix="c2", tx=tx, xe=xe, lay=14, giao=16)   # đã có chuyến
    r = _len_luot(client, h, [ok, da_co["request_id"]], tx=tx, xe=xe, cho=400)
    assert da_co["request_code"] in r["detail"]     # nói RÕ yêu cầu nào hỏng
    db = SessionLocal()
    try:
        assert db.query(DeliveryTrip).filter(DeliveryTrip.request_id == ok).count() == 0
        assert db.query(LuotXe).count() == 1        # chỉ còn lượt của chuyến c2 — lượt lô hỏng không sinh
    finally:
        db.close()


def test_LEN_LUOT_khong_chon_xe_bi_chan(client):
    h, tx, px, xe = _canh(client)
    r = _len_luot(client, h, [_yc(client, h, "d1")], tx=tx, xe=None, cho=400)
    assert "xe" in r["detail"]


def test_CA_LUOT_gui_kho_moi_chuyen_MOT_PHIEU_lay_hang_bat_dau_mot_lan_roi_chi_tiet_theo_chang(client):
    """⭐ Vòng 01/08 đi bằng nút CẢ LƯỢT: SVN 91424 → AOBO 91445 → Young Poong 91452 → SVN 91469."""
    from app.models.stock_request import StockRequest

    h, tx, px, xe = _canh(client)
    kq = _len_luot(client, h, [_yc(client, h, "yp"), _yc(client, h, "aobo")], tx=tx, px=px, xe=xe)
    lid, (a, b) = kq["luot_id"], kq["trips"]

    gui = _ca_luot(client, h, lid, "yeu-cau-xuat-kho", {"ghi_chu": "Soạn trước 7h"})
    assert gui["so_chuyen"] == 2 and len(set(gui["phieu"])) == 2          # MỖI chuyến MỘT phiếu
    db = SessionLocal()
    try:
        gc = [p.ghi_chu for p in db.query(StockRequest).filter(StockRequest.ma.in_(gui["phieu"]))]
    finally:
        db.close()
    # Kho đọc ghi chú là biết những phiếu nào lên cùng một xe.
    assert all(kq["code"] in g and "Soạn trước 7h" in g for g in gc)
    _ca_luot(client, h, lid, "yeu-cau-xuat-kho", cho=400)                 # hết chuyến chờ gửi

    ct = client.get(f"{GOC}/luot-xe/{lid}", headers=h).json()
    assert (ct["so_cho_gui_kho"], ct["so_cho_lay_hang"]) == (0, 2)
    assert _ca_luot(client, h, lid, "da-lay-hang")["so_chuyen"] == 2

    # Chưa có số xuất phát ⇒ chặn, và KHÔNG chuyến nào nhích (cả lô bỏ).
    loi = _ca_luot(client, h, lid, "bat-dau-giao", cho=400)
    assert "xuất phát" in loi["detail"]
    assert {_chuyen(t["id"]).trang_thai for t in (a, b)} == {"da_lay_hang"}
    bd = _ca_luot(client, h, lid, "bat-dau-giao", {"so_dong_ho_xuat_phat": 91424})
    assert bd["so_chuyen"] == 2 and bd["canh_bao"] == []

    _ket_qua(client, h, b["id"], 91445)          # tới AOBO trước — thứ tự do đồng hồ quyết
    ct = client.get(f"{GOC}/luot-xe/{lid}", headers=h).json()
    assert (ct["cho_ve_kho"], ct["so_dang_giao"]) == (False, 1)   # còn một điểm chưa xong
    _ket_qua(client, h, a["id"], 91452)
    ct = client.get(f"{GOC}/luot-xe/{lid}", headers=h).json()
    assert (ct["cho_ve_kho"], ct["so_dong_ho_gan_nhat"]) == (True, 91452)
    _ve_kho(client, h, lid, 91469)
    ct = client.get(f"{GOC}/luot-xe/{lid}", headers=h).json()
    assert ct["cho_ve_kho"] is False
    assert [d["id"] for d in ct["diem"]] == [b["id"], a["id"]]
    assert [d["km"] for d in ct["diem"]] == [21, 7]
    assert (ct["km_ve_kho"], ct["tong_km"], ct["so_dong_ho_xuat_phat"]) == (17, 45, 91424)
    assert ct["xe_bien_so"] == "51D-853.66"


def test_CA_LUOT_bat_dau_giao_khi_con_chuyen_chua_lay_hang_thi_NHAC(client):
    h, tx, px, xe = _canh(client)
    kq = _len_luot(client, h, [_yc(client, h, f"f{i}") for i in range(3)], tx=tx, xe=xe)
    lid, trips = kq["luot_id"], kq["trips"]
    _ca_luot(client, h, lid, "yeu-cau-xuat-kho")
    for t in trips[:2]:
        r = client.post(f"{GOC}/trips/{t['id']}/da-lay-hang", headers=h)
        assert r.status_code == 200, r.text
    bd = _ca_luot(client, h, lid, "bat-dau-giao", {"so_dong_ho_xuat_phat": 5000})
    assert bd["so_chuyen"] == 2
    assert any("Còn 1 chuyến" in c for c in bd["canh_bao"])
    assert _chuyen(trips[2]["id"]).trang_thai == "dang_chuan_bi"


# =============================================================================================
# Tab "Đơn giao hàng" gom theo LƯỢT — mỗi lượt MỘT khối, trang hoá theo khối (chủ chốt 18/09/2026)
# =============================================================================================
def test_BANG_GIAO_moi_luot_mot_khoi_trang_hoa_theo_khoi_khong_cat_doi_luot(client):
    h, tx, px, xe = _canh(client)
    luot = _len_luot(client, h, [_yc(client, h, f"k{i}") for i in range(3)], tx=tx, xe=xe,
                     lay=8, giao=11)
    le = _len_don(client, h, suffix="le", tx=tx, xe=xe, luot=None, lay=14, giao=16)

    r = client.get(f"{GOC}/bang-giao", params={"page": 1, "size": 1}, headers=h)
    assert r.status_code == 200, r.text
    p1 = r.json()
    # 2 KHỐI (1 lượt 3 điểm + 1 chuyến lẻ) nhưng 4 ĐƠN giao — tab vẫn đếm đơn như trước.
    assert (p1["total"], p1["so_don"]) == (2, 4)
    # Khối mới nhất lên trước: chuyến lẻ lấy hàng 14h.
    assert p1["items"][0]["luot"] is None and p1["items"][0]["trip"]["id"] == le["id"]

    p2 = client.get(f"{GOC}/bang-giao", params={"page": 2, "size": 1}, headers=h).json()
    khoi = p2["items"][0]
    assert khoi["trip"] is None and khoi["luot"]["id"] == luot["luot_id"]
    # Trang 1 phần tử mà lượt vẫn đủ 3 điểm — không bị cắt đôi qua hai trang.
    assert len(khoi["luot"]["diem"]) == 3
    assert khoi["luot"]["so_cho_gui_kho"] == 3 and khoi["luot"]["xe_bien_so"] == "51D-853.66"
