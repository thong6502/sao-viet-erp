"""Người ăn KHOÁN không có tiền GIỜ tăng ca (0đ, không phải 1×) — `docs/prd-khoan-khong-tien-tang-ca.md` (14/09/2026).

Phản hồi của khách, chủ chuyển lời: *"khoán sản lượng với khoán km nó không có ăn tăng ca, vì tăng ca
nó là làm thêm giờ thì nó thêm sản lượng, là nó ăn tiền sản lượng rồi … tiền cơm tăng ca thì vẫn được
nhận"*. Bốn câu chủ chốt:

1. Làm NGUYÊN NGÀY Chủ nhật / lễ ⇒ VẪN ăn phần thêm (+100% / +300%). Chỉ GIỜ tăng ca ra 0đ
   (chủ nhắc lại 14/09: "không có tiền tăng ca luôn" — không phải trả 1×).
2. Chế độ khoán tính theo TỔ: tổ bật Lương khoán / sản lượng + tổ bật cờ Giao hàng.
3. Công tắc Tăng ca của tổ khoán không đem tiền giờ tăng ca trở lại — nó còn quyết cơm tăng ca.
4. Sửa lỗi: tắt công tắc Tăng ca mà người có ngày off1x vẫn ra cơm tăng ca.

⚠️ Rủi ro pháp lý (NĐ 145/2020 Đ55.2) đã báo chủ trước khi chốt — xem PRD §5.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from app.db import SessionLocal
from app.repositories.employee_repo import EmployeeRepository
from app.repositories.payroll_repo import PayrollRepository
from app.repositories.rbac_repo import DepartmentRepository
from app.services.payroll_service import PayrollService
from tests.test_com_tang_ca import (
    MUC, NAM, THANG, _ca_hanh_chinh, _h, _khai_com_tc, _lam_ngay, _ngay_lam_viec, _ngay_nghi, _nv,
    _phieu_tang_ca,
)
from tests.test_luong_api import _sal

# Lương cơ bản 26tr / 26 công ⇒ 1.000.000 đ/công · 125.000 đ/giờ (8 giờ/công).
LUONG = 26_000_000
GIO = 125_000


# --- dựng cảnh -------------------------------------------------------------------------------
def _svc(db) -> PayrollService:
    return PayrollService(PayrollRepository(db), EmployeeRepository(db), attendance=None,
                          departments=DepartmentRepository(db))


def _emp():
    return SimpleNamespace(status="active", hire_date=date(2020, 1, 1), gender="male",
                           payroll_group=None, pay_grade_key=None, dependents_count=0)


def _tinh(svc, params, **kw) -> dict:
    return svc._compute(employee=_emp(), salary=_sal(luong_vi_tri=LUONG), params=params,
                        standard_cong=26, on=date(2026, 6, 1), **kw)


def _to(ten: str, *, khoan: bool = False, giao_hang: bool = False, cha: int | None = None) -> int:
    db = SessionLocal()
    try:
        pb = DepartmentRepository(db).create(name=ten, parent_id=cha)
        pb.has_piece_work = khoan
        pb.la_giao_hang = giao_hang
        db.commit()
        return pb.id
    finally:
        db.close()


def _chuyen_to(eid: int, dept_id: int) -> None:
    db = SessionLocal()
    try:
        EmployeeRepository(db).get_by_id(eid).department_id = dept_id
        db.commit()
    finally:
        db.close()


def _khai_com_tc_va_tat_khop_ca(client, h) -> None:
    """Khai cơm tăng ca. TẮT luôn luật "ca phải khớp giờ công chuẩn": gọi Cấu hình lương TRƯỚC khi
    tạo ca là dựng dòng tham số với luật đó BẬT, rồi ca 08:00–17:00 (9 giờ) của helper bị chặn —
    `test_com_tang_ca.py` né được chỉ vì nó tạo ca trước."""
    _khai_com_tc(client, h)
    r = client.put("/api/luong/params", json={"ca_khop_gio_chuan": False}, headers=h)
    assert r.status_code == 200, r.text


def _tinh_lai(client, h) -> dict:
    r = client.post("/api/luong/generate", json={"year": NAM, "month": THANG}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _dong(bang: dict, eid: int) -> dict:
    return next(l for l in bang["lines"] if l["employee_id"] == eid)


# =============================================================================================
# Engine — từng rổ tiền, số viết tay
# =============================================================================================
def test_KHOAN_khong_co_tien_GIO_tang_ca_ca_ba_loai_ngay(client):
    """⭐ 2h tăng ca ngày thường + 1h ngày nghỉ tuần + 1h ngày lễ.

    Tổ thường: 125.000 × (2 × 1,5 + 1 × 2 + 1 × 3) = 1.000.000. Người ăn khoán: 0 — cả ba loại ngày.
    """
    client
    db = SessionLocal()
    try:
        svc = _svc(db)
        params = svc.get_params()
        gio = dict(actual_cong=26, ot_minutes=240, ot_restday_minutes=60, ot_holiday_minutes=60)
        thuong = _tinh(svc, params, **gio, che_do_khoan=False)
        khoan = _tinh(svc, params, **gio, che_do_khoan=True)
        assert thuong["ot_pay"] == GIO * 8 == 1_000_000
        assert khoan["ot_pay"] == 0
        assert thuong["gross"] - khoan["gross"] == 1_000_000
        assert khoan["che_do_khoan"] is True and thuong["che_do_khoan"] is False
    finally:
        db.close()


def test_KHOAN_VAN_AN_phan_them_khi_lam_NGUYEN_NGAY_chu_nhat_va_le(client):
    """Chủ chốt câu 1: làm nguyên ngày CN / lễ là CÔNG, không phải giờ tăng ca ⇒ giữ phần thêm."""
    client
    db = SessionLocal()
    try:
        svc = _svc(db)
        params = svc.get_params()
        for khoan in (False, True):
            le = _tinh(svc, params, actual_cong=27, holiday_cong=1, che_do_khoan=khoan)
            cn = _tinh(svc, params, actual_cong=27, restday_cong=1, che_do_khoan=khoan)
            assert le["ot_pay"] == 3_000_000, khoan        # lễ: trọn 300% trên 1 công
            assert cn["ot_pay"] == 1_000_000, khoan        # CN: phần thêm 100%
    finally:
        db.close()


def test_KHOAN_van_nhan_COM_TANG_CA_du_suat(client):
    """Đúng lời khách: không hệ số, nhưng tiền cơm tăng ca vẫn nhận — cùng số suất với tổ thường."""
    client
    db = SessionLocal()
    try:
        svc = _svc(db)
        params = svc.get_params()
        params.com_tang_ca_muc = 30_000
        params.com_tang_ca_nguong_phut = 180
        # Ngày làm việc TC 200' (≥ 180 ⇒ 1 suất) + ngày nghỉ TC 30' (có phút là có suất) = 2 suất.
        ot_days = {"lam": {"3": 200}, "nghi": {"7": 30}}
        thuong = _tinh(svc, params, actual_cong=26, ot_minutes=230, ot_days=ot_days,
                       che_do_khoan=False)
        khoan = _tinh(svc, params, actual_cong=26, ot_minutes=230, ot_days=ot_days,
                      che_do_khoan=True)
        assert thuong["com_tang_ca_pay"] == khoan["com_tang_ca_pay"] == 60_000
        assert khoan["ot_pay"] == 0
    finally:
        db.close()


def test_KHOAN_phu_cap_tang_ca_DEM_bang_0_nhung_gio_dem_TRONG_CA_van_tra(client):
    """Phụ cấp tăng ca đêm đi theo GIỜ tăng ca ⇒ bỏ. Giờ đêm trong ca thì không phải tăng ca."""
    client
    db = SessionLocal()
    try:
        svc = _svc(db)
        params = svc.get_params()
        dem = dict(actual_cong=26, ot_minutes=60, night_premium_minutes=60,
                   ot_night_normal_minutes=60)
        thuong = _tinh(svc, params, **dem, che_do_khoan=False)
        khoan = _tinh(svc, params, **dem, che_do_khoan=True)
        # Giờ đêm trong ca: 125.000 × 1h. Tăng ca đêm: 125.000 × 1h × (30% + 20%) = 62.500.
        assert thuong["night_premium_pay"] == GIO + 62_500
        assert khoan["night_premium_pay"] == GIO
    finally:
        db.close()


def test_KHOAN_ngay_off1x_van_tra_1x(client):
    """Ngày off1x là lương 1× của ngày đi làm, không phải hệ số ⇒ không đụng."""
    client
    db = SessionLocal()
    try:
        svc = _svc(db)
        params = svc.get_params()
        v = _tinh(svc, params, actual_cong=26, plain_cong=1, che_do_khoan=True)
        assert v["off1x_pay"] == 1_000_000 and v["ot_pay"] == 1_000_000
    finally:
        db.close()


def test_TAT_cong_tac_tang_ca_thi_KHONG_com_tang_ca_ke_ca_nguoi_co_ngay_off1x(client):
    """Lỗi soát ra 14/09 (chủ chốt sửa luôn). Luật cũ cắt cơm khi `ot_pay <= 0` VÀ công tắc tắt —
    người có ngày off1x thì `ot_pay` > 0 (tiền 1× nằm trong đó) nên tắt công tắc mà vẫn ra cơm."""
    h = _h(client)
    pb = _to("Tổ tắt tăng ca thử")
    r = client.put(f"/api/luong/dept-components/{pb}", json={"items": [
        {"component_key": "tang_ca", "is_enabled": False}]}, headers=h)
    assert r.status_code == 200, r.text
    db = SessionLocal()
    try:
        svc = _svc(db)
        params = svc.get_params()
        params.com_tang_ca_muc = 30_000
        params.com_tang_ca_nguong_phut = 180
        v = _tinh(svc, params, actual_cong=26, plain_cong=1, ot_minutes=60,
                  ot_days={"nghi": {"7": 60}}, department_id=pb, che_do_khoan=False)
        assert v["off1x_pay"] == 1_000_000            # ngày off1x vẫn trả 1×
        assert v["com_tang_ca_pay"] == 0, "tắt công tắc Tăng ca mà vẫn ra cơm tăng ca"
    finally:
        db.close()


# =============================================================================================
# Ai thuộc chế độ khoán — theo TỔ
# =============================================================================================
def test_che_do_khoan_suy_theo_TO(client):
    """Hai nguồn, mỗi nguồn là định nghĩa đang dùng ở chỗ khác: công tắc Lương khoán của tổ, và
    `dept_ids_giao_hang()` (cờ RIÊNG — tổ con không tự bật thì không tính, như §12 khoán km)."""
    client
    to_khoan = _to("Tổ khoán suy thử", khoan=True)
    to_gh = _to("Tổ giao hàng suy thử", giao_hang=True)
    to_con_gh = _to("Tổ con giao hàng chưa bật", cha=to_gh)
    to_thuong = _to("Tổ thường suy thử")
    db = SessionLocal()
    try:
        svc = _svc(db)
        assert svc._che_do_khoan(to_khoan) is True
        assert svc._che_do_khoan(to_gh) is True
        assert svc._che_do_khoan(to_con_gh) is False
        assert svc._che_do_khoan(to_thuong) is False
        assert svc._che_do_khoan(None) is False
    finally:
        db.close()


def test_cong_tac_LUONG_KHOAN_cua_to_quyet_che_do(client):
    """Tắt công tắc Lương khoán / sản lượng ở Cấu hình lương ⇒ tổ hết chế độ khoán, dù cờ cũ
    `has_piece_work` từng bật (công tắc là cửa sửa duy nhất)."""
    h = _h(client)
    pb = _to("Tổ khoán tắt công tắc", khoan=True)
    r = client.put(f"/api/luong/dept-components/{pb}", json={"items": [
        {"component_key": "luong_khoan", "is_enabled": False}]}, headers=h)
    assert r.status_code == 200, r.text
    db = SessionLocal()
    try:
        assert _svc(db)._che_do_khoan(pb) is False
    finally:
        db.close()


# =============================================================================================
# Chạy qua "Tính lại" thật — chấm công + phiếu tăng ca
# =============================================================================================
def test_TINH_LAI_to_khoan_va_to_giao_hang_khong_tien_tang_ca_van_co_com_va_co_canh_bao(client):
    """⭐ Ba người cùng làm một ngày thường + 3h tăng ca có phiếu: tổ thường · tổ khoán · tổ Giao hàng.

    Tổ khoán và tổ Giao hàng: tiền tăng ca = 0, vẫn 1 suất cơm, dòng lương chụp `che_do_khoan`.
    Cả hai chưa có đồng khoán nào trong kỳ ⇒ bảng lương phải cảnh báo trước khi chốt.
    """
    h = _h(client)
    _khai_com_tc_va_tat_khop_ca(client, h)
    to_khoan = _to("Tổ khoán tính lại", khoan=True)
    to_gh = _to("Tổ giao hàng tính lại", giao_hang=True)
    ngay = _ngay_lam_viec(client, h)[2]

    nguoi = {}
    for vai, to in (("thuong", None), ("khoan", to_khoan), ("gh", to_gh)):
        eid = _nv(client, h, ten=f"NV TC {vai}")
        if to is not None:
            _chuyen_to(eid, to)
        _ca_hanh_chinh(client, h, eid)
        _lam_ngay(client, h, eid, ngay, ot_gio=3)
        _phieu_tang_ca(client, h, eid, ngay)
        nguoi[vai] = eid

    bang = _tinh_lai(client, h)
    thuong, khoan, gh = (_dong(bang, nguoi[k]) for k in ("thuong", "khoan", "gh"))
    for d in (thuong, khoan, gh):
        assert d["ot_minutes"] == 180, d
        assert d["com_tang_ca_pay"] == MUC, d            # cơm tăng ca: ai cũng có
    assert thuong["ot_pay"] > 0 and thuong["che_do_khoan"] is False
    assert khoan["ot_pay"] == 0 and khoan["che_do_khoan"] is True
    assert gh["ot_pay"] == 0 and gh["che_do_khoan"] is True

    canh_bao = bang["canh_bao_chot"] or ""
    assert "2 người ăn khoán có giờ tăng ca nhưng tiền khoán kỳ này = 0" in canh_bao, canh_bao
    assert "NV TC khoan" in canh_bao and "NV TC gh" in canh_bao


def test_TINH_LAI_to_khoan_lam_NGUYEN_NGAY_chu_nhat_van_bang_to_thuong(client):
    """Chủ nhật đi làm trong giờ ca = CÔNG (`restday_cong`) ⇒ phần thêm giữ nguyên cho tổ khoán."""
    h = _h(client)
    _khai_com_tc_va_tat_khop_ca(client, h)
    to_khoan = _to("Tổ khoán chủ nhật", khoan=True)
    cn = _ngay_nghi(client, h)[1]

    nguoi = {}
    for vai, to in (("thuong", None), ("khoan", to_khoan)):
        eid = _nv(client, h, ten=f"NV CN {vai}")
        if to is not None:
            _chuyen_to(eid, to)
        _ca_hanh_chinh(client, h, eid)
        _lam_ngay(client, h, eid, cn)
        nguoi[vai] = eid

    bang = _tinh_lai(client, h)
    thuong, khoan = _dong(bang, nguoi["thuong"]), _dong(bang, nguoi["khoan"])
    assert thuong["ot_pay"] > 0, "đi làm CN phải có phần thêm — test dựng sai cảnh"
    assert khoan["ot_pay"] == thuong["ot_pay"]
    assert khoan["che_do_khoan"] is True


# =============================================================================================
# Cảnh báo — chỉ nói, không chặn
# =============================================================================================
def test_canh_bao_chi_voi_nguoi_KHOAN_co_gio_TC_ma_tien_khoan_bang_0(client):
    client
    from app.routers.payroll import _canh_bao_chot

    def dong(ten, **kw):
        base = dict(employee_id=1, employee_name=ten, net_pay=1, advance_total=0,
                    luong_dot_1_total=0, no_ung_ky_truoc=0, no_ung_chuyen_ky_sau=0,
                    ot_minutes=120, khoan=0, khoan_km=0, che_do_khoan=True)
        base.update(kw)
        return SimpleNamespace(**base)

    assert _canh_bao_chot([dong("Có khoán", khoan=500_000)]) is None
    assert _canh_bao_chot([dong("Có km", khoan_km=300_000)]) is None
    assert _canh_bao_chot([dong("Không giờ TC", ot_minutes=0)]) is None
    assert _canh_bao_chot([dong("Tổ thường", che_do_khoan=False)]) is None
    cb = _canh_bao_chot([dong("Thợ A")])
    assert cb is not None and "1 người ăn khoán" in cb and "Thợ A" in cb
