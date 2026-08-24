"""Khoán km giao hàng — nghiệm thu `docs/prd-khoan-km-giao-hang.md` §8.

Nền: tài xế ăn lương chấm công **cộng** tiền theo km. Đo bảng lương thật T05/2026, phần km
(19–22 tr) gấp ~4 lần lương cứng (~5 tr) — đây là thu nhập CHÍNH của họ, trước nay tính tay trên
bốn sheet Excel ngoài hệ thống.

Ba luật xương sống, sửa là hỏng:

* **Đơn giá + tỷ lệ CHỤP LẠI lúc ghi kết quả.** Đọc thẳng của phòng ban lúc tính lương thì chủ
  chỉnh một số là bảng lương mọi tháng cũ đổi theo — bài học `orders.commission_pct`.
* **Đi một mình ăn 100%**, không phải `pct_tai_xe`. Vì %tài xế + %phụ xe = 100 nên tổng chi cho
  một chuyến KHÔNG đổi dù đi mấy người.
* **Là CỘT `payroll_lines.khoan_km`**, không phải dòng trong Danh mục khoản thu nhập — màn danh
  mục là chỗ HCNS thêm/xoá phụ cấp, nhét khoản hệ thống vào là đặt công tắc cạnh nút xoá.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from app.db import SessionLocal
from app.models.delivery import DeliveryTrip
from app.repositories.rbac_repo import DepartmentRepository
from tests.test_giao_hang_api import (
    _admin,
    _di_toi_dang_giao,
    _don_da_chot,
    _len_kh,
    _tai_xe,
    _tao_yc,
)

PHONG_GH = "Giao hàng"


# ---------------------------------------------------------------------------------------------
# Dựng cảnh
# ---------------------------------------------------------------------------------------------
def _bat_khoi_giao_hang(*, don_gia=4330, tx=60, px=40) -> int:
    """Phòng Giao hàng bật cờ + khai ba ô khoán km. Trả `department_id`."""
    db = SessionLocal()
    try:
        repo = DepartmentRepository(db)
        pb = repo.get_by_name(PHONG_GH)
        if pb is None:
            pb = repo.create(name=PHONG_GH)
        pb.la_giao_hang = True
        pb.don_gia_km = don_gia
        pb.pct_tai_xe = tx
        pb.pct_phu_xe = px
        db.commit()
        return pb.id
    finally:
        db.close()


def _chuyen_xong(client, h, *, suffix, tai_xe, phu_xe=None, km=100):
    """Đơn → yêu cầu → kế hoạch → giao thành công. Trả `trip_id`."""
    oid, lid = _don_da_chot(suffix=suffix)
    yc = _tao_yc(client, h, oid, lid)
    body = {"request_id": yc["id"], "employee_id": tai_xe,
            "gio_lay_hang": None, "gio_du_kien_giao": None}
    r = _len_kh(client, h, yc["id"], tai_xe) if phu_xe is None else _len_kh_kem_phu_xe(
        client, h, yc["id"], tai_xe, phu_xe)
    assert r.status_code == 201, r.text
    trip = r.json()["trip"]["id"]
    _di_toi_dang_giao(client, h, trip)
    r = client.post(f"/api/giao-hang/trips/{trip}/ket-qua", json={
        "ket_qua": "thanh_cong", "km": km, "nguoi_nhan_thuc_te": "Chi Lan"}, headers=h)
    assert r.status_code == 200, r.text
    del body
    return trip


def _len_kh_kem_phu_xe(client, h, request_id, tai_xe, phu_xe, *, lay=8, giao=11):
    from tests.test_giao_hang_api import _gio
    return client.post("/api/giao-hang/plans", json={
        "request_id": request_id, "employee_id": tai_xe, "phu_xe_employee_id": phu_xe,
        "gio_lay_hang": _gio(lay), "gio_du_kien_giao": _gio(giao),
    }, headers=h)


def _tien(trip_id: int) -> dict[int, float]:
    from app.services.khoan_km_service import KhoanKmService
    db = SessionLocal()
    try:
        return KhoanKmService(db).chia_tien(db.get(DeliveryTrip, trip_id))
    finally:
        db.close()


# =============================================================================================
# #12 · #13 — chia tiền cho kíp xe
# =============================================================================================
def test_12_KIP_HAI_NGUOI_chia_60_40_va_TONG_khong_doi(client):
    """⭐ 100 km × 4.330 = 433.000. Tài xế 259.800 · phụ xe 173.200 — cộng lại ĐÚNG 433.000.

    Vế "cộng lại đúng" mới là bất biến thật: %tài xế + %phụ xe = 100 nên chuyến có phụ xe tốn
    đúng bằng chuyến đi một mình. Lệch là công ty âm thầm trả thêm (hoặc giữ lại) mà không ai
    khai điều đó ở đâu.
    """
    _bat_khoi_giao_hang()
    h = _admin(client)
    tx = _tai_xe("TX kip", phong=PHONG_GH)
    px = _tai_xe("PX kip", phong=PHONG_GH)
    trip = _chuyen_xong(client, h, suffix="km1", tai_xe=tx, phu_xe=px, km=100)

    chia = _tien(trip)
    assert chia == {tx: 259_800.0, px: 173_200.0}, chia
    assert round(sum(chia.values())) == 433_000, "tổng chi một chuyến bị đổi"


def test_13_DI_MOT_MINH_an_100_phan_tram_khong_phai_60(client):
    """⭐ Không có phụ xe ⇒ tài xế ăn TRỌN, phần 40% không rơi vào túi ai.

    Lấy thẳng `pct_tai_xe` cho mọi ca là chuyến đi một mình chỉ trả 60% — tài xế mất 40% chỉ vì
    hôm đó không ai đi cùng.
    """
    _bat_khoi_giao_hang()
    h = _admin(client)
    tx = _tai_xe("TX mot minh", phong=PHONG_GH)
    trip = _chuyen_xong(client, h, suffix="km2", tai_xe=tx, km=100)

    assert _tien(trip) == {tx: 433_000.0}


# =============================================================================================
# #14 · #15 — chặn kíp xe sai
# =============================================================================================
def test_14_MOT_NGUOI_KHONG_duoc_vao_ca_hai_o(client):
    """⭐ Không chặn thì họ ăn 60% + 40% = 100% của chính chuyến đó.

    Nhìn bảng lương KHÔNG thấy gì bất thường — tổng vẫn đúng bằng tiền một chuyến. Chỉ có điều
    đáng ra phải chia cho hai người.
    """
    _bat_khoi_giao_hang()
    h = _admin(client)
    tx = _tai_xe("TX trung minh", phong=PHONG_GH)
    oid, lid = _don_da_chot(suffix="km3")
    yc = _tao_yc(client, h, oid, lid)

    r = _len_kh_kem_phu_xe(client, h, yc["id"], tx, tx)
    assert r.status_code == 400, r.text
    assert "cùng một người" in r.json()["detail"]


def test_15_PHU_XE_trung_lich_bi_chan_va_bao_DUNG_NGUOI(client):
    """⭐ Phụ xe cũng là một con người: kíp xe SINH RA TIỀN, trùng lịch là trả hai chuyến cho
    cùng một khoảng thời gian.

    Và câu báo phải nói "Phụ xe", không phải "Tài xế" — báo sai người là cử người ta đi sửa
    nhầm ô.
    """
    _bat_khoi_giao_hang()
    h = _admin(client)
    tx1, tx2 = _tai_xe("TX a", phong=PHONG_GH), _tai_xe("TX b", phong=PHONG_GH)
    px = _tai_xe("PX ban", phong=PHONG_GH)

    o1, l1 = _don_da_chot(suffix="km4a")
    yc1 = _tao_yc(client, h, o1, l1)
    assert _len_kh_kem_phu_xe(client, h, yc1["id"], tx1, px).status_code == 201

    o2, l2 = _don_da_chot(suffix="km4b")
    yc2 = _tao_yc(client, h, o2, l2)
    r = _len_kh_kem_phu_xe(client, h, yc2["id"], tx2, px)     # cùng khung giờ
    assert r.status_code == 400, r.text
    assert "Phụ xe" in r.json()["detail"], f"báo sai người: {r.json()['detail']}"


def test_16_HAI_O_PHAN_TRAM_khong_cong_du_100_thi_chan(client):
    """Cộng ra 90 ⇒ công ty giữ 10% không khai ở đâu; ra 110 ⇒ chuyến có phụ xe đắt hơn 10%."""
    h = _admin(client)
    pb = _bat_khoi_giao_hang()
    r = client.put(f"/api/departments/{pb}", json={
        "name": PHONG_GH, "pct_tai_xe": 70, "pct_phu_xe": 40}, headers=h)
    assert r.status_code == 400, r.text
    assert "100" in r.json()["detail"]


# =============================================================================================
# #17 — chụp số, không đọc sống
# =============================================================================================
def test_17_DOI_DON_GIA_khong_lam_doi_chuyen_DA_GHI_KET_QUA(client):
    """⭐ Chuyến đã chốt phải giữ NGUYÊN số. Đọc thẳng phòng ban lúc tính lương thì chủ chỉnh
    đơn giá tháng 9 là bảng lương tháng 5 đổi theo — số cũ không tái lập được, mà không ai thấy.
    """
    _bat_khoi_giao_hang(don_gia=4330)
    h = _admin(client)
    tx = _tai_xe("TX chup gia", phong=PHONG_GH)
    trip = _chuyen_xong(client, h, suffix="km5", tai_xe=tx, km=100)
    assert _tien(trip) == {tx: 433_000.0}

    _bat_khoi_giao_hang(don_gia=9999)                 # chủ nâng giá tháng sau
    assert _tien(trip) == {tx: 433_000.0}, "chuyến đã chốt bị nắn theo đơn giá mới"


def test_chuyen_CU_chua_chup_gia_thi_KHONG_de_tien_nguoc(client):
    """Chuyến chạy trước khi có tính năng mang `don_gia_km = NULL` ⇒ bỏ qua.

    Ghi 0 vào đó là nói dối rằng "đã chụp và bằng 0"; để NULL mới phân biệt được "chưa có tính
    năng" với "phòng ban khai đơn giá 0".
    """
    _bat_khoi_giao_hang()
    h = _admin(client)
    tx = _tai_xe("TX chuyen cu", phong=PHONG_GH)
    trip = _chuyen_xong(client, h, suffix="km6", tai_xe=tx, km=100)

    db = SessionLocal()
    try:                                              # giả lập chuyến cũ
        t = db.get(DeliveryTrip, trip)
        t.don_gia_km = None
        db.commit()
    finally:
        db.close()
    assert _tien(trip) == {}


# =============================================================================================
# #1 · #18 — vào bảng lương, và KHÔNG đẻ dòng trong danh mục khoản
# =============================================================================================
def _tinh_luong(client, h, eid: int) -> dict:
    hom_nay = date.today()
    r = client.post("/api/luong/generate",
                    json={"year": hom_nay.year, "month": hom_nay.month}, headers=h)
    assert r.status_code in (200, 201), r.text
    return next(l for l in r.json()["lines"] if l["employee_id"] == eid)


def test_01_tien_km_CONG_vao_bang_luong_va_vao_gross(client):
    """⭐ Lý do cả tính năng tồn tại: km phải RA TIỀN trên bảng lương, và cộng vào tổng."""
    _bat_khoi_giao_hang()
    h = _admin(client)
    tx = _tai_xe("TX len luong", phong=PHONG_GH)
    _chuyen_xong(client, h, suffix="km7", tai_xe=tx, km=100)

    dong = _tinh_luong(client, h, tx)
    assert dong["khoan_km"] == 433_000, dong["khoan_km"]
    assert dong["gross"] >= 433_000, "khoán km không vào gross"


def test_18_DANH_MUC_khoan_thu_nhap_KHONG_moc_them_dong_nao(client):
    """⭐ Khoán km là CỘT, không phải khoản danh mục.

    Màn *Danh mục khoản thu nhập* là chỗ HCNS khai phụ cấp/thưởng rồi gán cho từng người, thêm
    xoá thoải mái. Nhét khoản hệ thống vào đó là đặt một công tắc toàn hệ thống ngay cạnh nút
    xoá — đúng lỗi đã mắc với hoa hồng và sửa ngày 24/08/2026.
    """
    _bat_khoi_giao_hang()
    h = _admin(client)
    truoc = len(client.get("/api/luong/components", headers=h).json()["items"])

    tx = _tai_xe("TX khong de khoan", phong=PHONG_GH)
    _chuyen_xong(client, h, suffix="km8", tai_xe=tx, km=100)
    _tinh_luong(client, h, tx)

    sau = client.get("/api/luong/components", headers=h).json()["items"]
    assert len(sau) == truoc, "danh mục mọc thêm dòng sau khi tính khoán km"
    assert not [c for c in sau if "km" in c["code"]], [c["code"] for c in sau]


def test_BANG_DOI_CHIEU_cong_lai_DUNG_BANG_cot_tren_bang_luong(client):
    """⭐ HCNS phải soi lại được từng chuyến — km là TÀI XẾ TỰ GÕ, khác hẳn hoa hồng (nguồn là hoá
    đơn kế toán đã xuất, đã qua tay người khác). Không có bảng này thì khoán km là tiền tự khai.

    Bất biến khoá ở đây: **tổng bảng chi tiết = đúng cột "Khoán km"**. Lệch nghĩa là một trong hai
    bên tính sai, và lúc đó không số nào tin được nữa.
    """
    _bat_khoi_giao_hang()
    h = _admin(client)
    tx = _tai_xe("TX doi chieu", phong=PHONG_GH)
    px = _tai_xe("PX doi chieu", phong=PHONG_GH)
    _chuyen_xong(client, h, suffix="km12a", tai_xe=tx, phu_xe=px, km=100)
    _chuyen_xong(client, h, suffix="km12b", tai_xe=tx, km=50)

    dong = _tinh_luong(client, h, tx)
    r = client.get(f"/api/luong/lines/{dong['id']}/khoan-km", headers=h)
    assert r.status_code == 200, r.text
    kq = r.json()

    assert len(kq["items"]) == 2, kq
    assert kq["tong"] == dong["khoan_km"], "bảng chi tiết cộng lại KHÁC cột trên bảng lương"
    assert round(sum(x["thanh_tien"] for x in kq["items"]), 2) == kq["tong"]

    # Chuyến đi cùng phụ xe ⇒ tài xế chỉ 60%; chuyến đi một mình ⇒ 100%. Hai dòng phải nói rõ
    # điều đó, không thì HCNS thấy hai chuyến cùng km mà tiền khác nhau và không hiểu vì sao.
    assert sorted(x["pct"] for x in kq["items"]) == [60.0, 100.0]
    assert {x["vai_tro"] for x in kq["items"]} == {"tai_xe"}


def test_bang_doi_chieu_cua_PHU_XE_ghi_dung_vai_tro(client):
    """Người đi phụ thấy dòng của chính chuyến đó với vai `phu_xe` và 40% — không phải 100%."""
    _bat_khoi_giao_hang()
    h = _admin(client)
    tx = _tai_xe("TX vai tro", phong=PHONG_GH)
    px = _tai_xe("PX vai tro", phong=PHONG_GH)
    _chuyen_xong(client, h, suffix="km13", tai_xe=tx, phu_xe=px, km=100)

    dong = _tinh_luong(client, h, px)
    kq = client.get(f"/api/luong/lines/{dong['id']}/khoan-km", headers=h).json()
    assert [(x["vai_tro"], x["pct"], x["thanh_tien"]) for x in kq["items"]] == [
        ("phu_xe", 40.0, 173_200.0)
    ], kq


def test_02_nguoi_KHONG_thuoc_khoi_giao_hang_thi_khong_co_tien_km(client):
    """Tổ không bật cờ ⇒ chuyến không chụp đơn giá ⇒ khoán km = 0, dù đã chạy chuyến."""
    h = _admin(client)
    tx = _tai_xe("TX to khac", phong="Sản xuất")      # tổ KHÔNG bật cờ Giao hàng
    trip = _chuyen_xong(client, h, suffix="km9", tai_xe=tx, km=100)

    assert _tien(trip) == {}
    assert _tinh_luong(client, h, tx)["khoan_km"] == 0


def _dat_bac(client, h, dept_id, bac):
    """PUT bảng bậc cho phòng. `bac` = [(up_to_km|None, don_gia), ...]."""
    r = client.put(f"/api/giao-hang/departments/{dept_id}/km-brackets",
                   json={"items": [{"up_to_km": u, "don_gia": g} for u, g in bac]}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["items"]


def test_BAC_toan_km_nhan_don_gia_cua_bac_km_roi_vao(client):
    """⭐ Chốt của chủ 24/08/2026: toàn km × đơn giá của MỘT bậc, không cộng dồn.

    Ví dụ của chủ: dưới 5km = 10.000, 5–10km = 20.000. Chuyến 8 km ⇒ 8 × 20.000 = 160.000,
    KHÔNG phải 5×10.000 + 3×20.000. Đây đúng cách bảng lương thật tính.
    """
    pb = _bat_khoi_giao_hang()
    h = _admin(client)
    _dat_bac(client, h, pb, [(5, 10_000), (10, 20_000), (None, 5_000)])
    tx = _tai_xe("TX bac", phong=PHONG_GH)

    trip = _chuyen_xong(client, h, suffix="bac1", tai_xe=tx, km=8)
    assert _tien(trip) == {tx: 160_000.0}, "8km phải ăn TRỌN giá bậc 5–10km"


def test_BAC_chuyen_3km_va_chuyen_vuot_tran_dung_bac_vo_han(client):
    """3 km rơi bậc đầu; 500 km rơi bậc ∞ (up_to_km trống)."""
    pb = _bat_khoi_giao_hang()
    h = _admin(client)
    _dat_bac(client, h, pb, [(5, 10_000), (10, 20_000), (None, 5_000)])
    tx1 = _tai_xe("TX 3km", phong=PHONG_GH)
    tx2 = _tai_xe("TX xa", phong=PHONG_GH)

    assert _tien(_chuyen_xong(client, h, suffix="bac2", tai_xe=tx1, km=3)) == {tx1: 30_000.0}
    assert _tien(_chuyen_xong(client, h, suffix="bac3", tai_xe=tx2, km=500)) == {tx2: 2_500_000.0}


def test_BAC_bien_5km_thuoc_bac_duoi(client):
    """Đúng 5 km: `km ≤ up_to_km` nên rơi bậc "≤5", không nhảy sang bậc sau."""
    pb = _bat_khoi_giao_hang()
    h = _admin(client)
    _dat_bac(client, h, pb, [(5, 10_000), (None, 20_000)])
    tx = _tai_xe("TX bien", phong=PHONG_GH)
    assert _tien(_chuyen_xong(client, h, suffix="bac4", tai_xe=tx, km=5)) == {tx: 50_000.0}


def test_BAC_chua_khai_thi_FALLBACK_ve_don_gia_phang(client):
    """Tổ chưa khai bậc nào ⇒ dùng đơn giá phẳng cũ (4.330), không ra 0."""
    _bat_khoi_giao_hang(don_gia=4330)              # KHÔNG gọi _dat_bac
    h = _admin(client)
    tx = _tai_xe("TX fallback", phong=PHONG_GH)
    assert _tien(_chuyen_xong(client, h, suffix="bac5", tai_xe=tx, km=100)) == {tx: 433_000.0}


def test_BAC_vo_han_khong_o_cuoi_bi_chan(client):
    """Bậc ∞ giữa bảng ⇒ nó nuốt mọi km từ chỗ đứng, các bậc sau thành vô nghĩa ⇒ chặn."""
    pb = _bat_khoi_giao_hang()
    h = _admin(client)
    r = client.put(f"/api/giao-hang/departments/{pb}/km-brackets", json={"items": [
        {"up_to_km": None, "don_gia": 5_000}, {"up_to_km": 10, "don_gia": 20_000}]}, headers=h)
    assert r.status_code == 400, r.text
    assert "CUỐI" in r.json()["detail"] or "cuối" in r.json()["detail"]


def test_BAC_tran_khong_tang_dan_bi_chan(client):
    """Trần lộn xộn ⇒ tra bậc (duyệt theo thứ tự) trả nhầm giá ⇒ chặn ngay lúc lưu."""
    pb = _bat_khoi_giao_hang()
    h = _admin(client)
    r = client.put(f"/api/giao-hang/departments/{pb}/km-brackets", json={"items": [
        {"up_to_km": 20, "don_gia": 10_000}, {"up_to_km": 10, "don_gia": 20_000},
        {"up_to_km": None, "don_gia": 5_000}]}, headers=h)
    assert r.status_code == 400, r.text


def test_DOI_BAC_khong_lam_doi_chuyen_DA_GHI_KET_QUA(client):
    """Chụp đơn giá tra được vào chuyến ⇒ đổi bảng bậc tháng sau, chuyến cũ giữ nguyên tiền."""
    pb = _bat_khoi_giao_hang()
    h = _admin(client)
    _dat_bac(client, h, pb, [(None, 10_000)])
    tx = _tai_xe("TX chup bac", phong=PHONG_GH)
    trip = _chuyen_xong(client, h, suffix="bac6", tai_xe=tx, km=100)
    assert _tien(trip) == {tx: 1_000_000.0}

    _dat_bac(client, h, pb, [(None, 99_000)])       # đổi giá
    assert _tien(trip) == {tx: 1_000_000.0}, "chuyến đã chốt bị nắn theo bậc mới"


def test_km_bang_0_khong_lam_vo_va_khong_ra_tien(client):
    """`km = 0` là số THẬT (xe chưa lăn bánh, khách không nghe máy) — không phải thiếu dữ liệu.

    Dùng `not km` thay cho `km is None` là nuốt luôn ca này và ca đơn giá 0.
    """
    _bat_khoi_giao_hang()
    h = _admin(client)
    tx = _tai_xe("TX km 0", phong=PHONG_GH)
    trip = _chuyen_xong(client, h, suffix="km10", tai_xe=tx, km=0)
    assert _tien(trip) == {}


def test_gio_ket_thuc_quyet_dinh_KY_chu_khong_phai_gio_lay_hang(client):
    """Chuyến chạy đêm cuối tháng sang mùng 1 ⇒ tiền thuộc kỳ chuyến ĐÓNG, cùng kỳ với số km
    được chốt. Xếp theo `gio_lay_hang` là tiền và km nằm hai kỳ khác nhau."""
    from app.services.khoan_km_service import KhoanKmService

    _bat_khoi_giao_hang()
    h = _admin(client)
    tx = _tai_xe("TX qua thang", phong=PHONG_GH)
    trip = _chuyen_xong(client, h, suffix="km11", tai_xe=tx, km=100)

    db = SessionLocal()
    try:
        t = db.get(DeliveryTrip, trip)
        t.thoi_gian_ket_thuc = datetime(2026, 3, 1, 2, 0, tzinfo=timezone.utc)
        db.commit()
        assert KhoanKmService(db).theo_ky(2026, 3).get(tx) == 433_000.0
        assert tx not in KhoanKmService(db).theo_ky(2026, 2)
    finally:
        db.close()


def test_LUU_PCT_qua_endpoint_bac_mot_lan(client):
    """⭐ Dời sang Cấu hình lương (24/08/2026): endpoint bậc nay lưu CẢ % chia kíp một lần, khỏi
    đi qua màn Phòng ban. GET trả % để màn hiện sẵn; PUT nhận % và kiểm cộng đúng 100."""
    h = _admin(client)
    pb = _bat_khoi_giao_hang()
    # Lưu bậc + % trong MỘT call.
    r = client.put(f"/api/giao-hang/departments/{pb}/km-brackets", json={
        "items": [{"up_to_km": None, "don_gia": 5000}], "pct_tai_xe": 70, "pct_phu_xe": 30},
        headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["pct_tai_xe"] == 70 and r.json()["pct_phu_xe"] == 30
    # GET trả lại đúng %.
    g = client.get(f"/api/giao-hang/departments/{pb}/km-brackets", headers=h).json()
    assert g["pct_tai_xe"] == 70 and g["pct_phu_xe"] == 30
    # % không cộng đủ 100 ⇒ chặn ngay ở endpoint này.
    bad = client.put(f"/api/giao-hang/departments/{pb}/km-brackets", json={
        "items": [{"up_to_km": None, "don_gia": 5000}], "pct_tai_xe": 70, "pct_phu_xe": 40},
        headers=h)
    assert bad.status_code == 400 and "100" in bad.json()["detail"], bad.text
