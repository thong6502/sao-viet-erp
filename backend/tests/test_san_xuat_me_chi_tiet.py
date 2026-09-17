"""Mẻ phải đọc được trọn vẹn (spec 2026-09-11 §5.2) — không cột mới, mọi số đã có trong DB.

Chủ xưởng: *"tổ trưởng phải thấy được thông tin của từng mẻ và sản lượng các thứ, nói chung đầy đủ
và chi tiết để sau này hỗ trợ kế toán lương"*.

Bài viết ở tầng SERVICE (`board.chi_tiet_cong_viec`) chứ không qua HTTP: dàn cảnh "việc đang chạy
+ phiên đổi máy + mẻ + chấm công" chỉ dựng được bằng các helper của `test_san_xuat_phan_bo` /
`test_san_xuat_thuc_thi`, và đường HTTP của drawer đã có bài riêng ở `test_san_xuat_board_api.py`.
"""
from __future__ import annotations

from datetime import timedelta

from app.models.attendance import WorkShift
from app.models.may_thiet_bi import MayThietBi
from app.models.san_xuat import CV_TAM_DUNG
from app.models.san_xuat_thuc_thi import SanXuatPhienChay
from app.services.gio_xuong import thuc_te_hien_thi, ve_gio_xuong
from app.services.san_xuat import board
from app.services.san_xuat.thuc_thi import _aware

# Fixtures + helper luồng thật.
from tests.test_san_xuat_phan_bo import (  # noqa: F401
    _T0,
    _canh_phan_bo,
    _cham_cong,
    _khoang,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
)
from tests.test_san_xuat_thuc_thi import _emp


def _authz(db):
    from app.repositories.rbac_repo import RoleRepository
    from app.services.rbac_service import AuthorizationService

    return AuthorizationService(RoleRepository(db))


def _may(db, ma) -> MayThietBi:
    m = MayThietBi(ma=ma, ten=f"Máy {ma}", loai_may="press_offset_sheet")
    db.add(m)
    db.flush()
    return m


def _phien(db, cv, *, bat_dau, ket_thuc, may_id=None, loai_dong="ket_thuc", ly_do=None, stt=1):
    p = SanXuatPhienChay(
        cong_viec_id=cv.id, so_thu_tu=stt, may_id=may_id,
        bat_dau=bat_dau, ket_thuc=ket_thuc, loai_dong=loai_dong, ly_do=ly_do,
    )
    db.add(p)
    db.flush()
    return p


def _me(db, cv, *, bat_dau, ket_thuc, tot=50.0, admin=None):
    from app.services.san_xuat import san_luong

    r = san_luong.tao_batch(db, user=admin, cong_viec_id=cv.id,
                            bat_dau=bat_dau, ket_thuc=ket_thuc, tong=tot, tot=tot)
    return r["batch_id"]


def _mes(db, admin, cv):
    return board.chi_tiet_cong_viec(
        db, admin, _authz(db), cong_viec_id=cv.id)["san_luong"]["batches"]


def test_me_mang_theo_may_da_chay_no(db, orders, lsx_svc, admin, customer):
    """Máy đứng trên PHIÊN, không trên công việc: đổi máy giữa chừng thì mỗi mẻ một máy khác nhau.
    Đọc `cv.may_id` là luôn ra máy HIỆN TẠI — sai cho mẻ chạy trước lúc đổi."""
    _to, cv, batch = _canh_phan_bo(db, orders, lsx_svc, admin, customer, ma="TO-ME-MAY")
    m1, m2 = _may(db, "MAY-ME-1"), _may(db, "MAY-ME-2")
    db.commit()
    # Mẻ 1 = chính `batch` của dàn cảnh (T0 → T0+1h); mẻ 2 chạy sau, trên máy khác.
    b2_bd = _T0 + timedelta(hours=2)
    _me(db, cv, bat_dau=b2_bd, ket_thuc=b2_bd + timedelta(hours=1), admin=admin)
    _phien(db, cv, bat_dau=batch.bat_dau, ket_thuc=batch.ket_thuc, may_id=m1.id,
           loai_dong="doi_may", stt=1)
    _phien(db, cv, bat_dau=b2_bd, ket_thuc=b2_bd + timedelta(hours=1), may_id=m2.id, stt=2)
    db.commit()

    assert [m["may_ten"] for m in _mes(db, admin, cv)] == [m1.ten, m2.ten]


def test_me_mang_theo_ca_va_su_co_dung_may(db, orders, lsx_svc, admin, customer):
    _to, cv, batch = _canh_phan_bo(db, orders, lsx_svc, admin, customer, ma="TO-ME-CA")
    # `start_minute` là phút-trong-ngày theo GIỜ TƯỜNG xưởng, còn cửa sổ mẻ là UTC THẬT (mg 0298),
    # nên ca phải neo vào giờ tường CỦA CHÍNH mốc mẻ — ghim cứng 06:00–14:00 là bài chỉ xanh trên
    # máy đặt múi UTC. Kẹp hai đầu để ca 8 tiếng luôn ôm trọn mốc ở mọi múi giờ máy chủ.
    tuong = ve_gio_xuong(batch.bat_dau)
    dau_ca = max(0, min(tuong.hour * 60 + tuong.minute - 120, 24 * 60 - 480))
    db.add(WorkShift(name="Ca 1 xưởng", start_minute=dau_ca, end_minute=dau_ca + 480))
    db.flush()
    _phien(db, cv, bat_dau=batch.bat_dau, ket_thuc=batch.bat_dau + timedelta(minutes=20),
           loai_dong="tam_dung", ly_do="kẹt giấy", stt=1)
    db.commit()

    me = _mes(db, admin, cv)[0]
    assert me["ca_ten"], "ca phải suy được từ giờ bắt đầu mẻ"
    assert [s["ly_do"] for s in me["su_co"]] == ["kẹt giấy"]


def test_dung_may_tinh_tu_luc_tam_dung_toi_luc_chay_lai(db, orders, lsx_svc, admin, customer):
    """Khoảng [bat_dau, ket_thuc] của phiên đóng bằng Tạm dừng là lúc máy CHẠY. Máy DỪNG từ
    `ket_thuc` của phiên đó tới lúc phiên kế mở. Lấy nhầm khoảng chạy thì mẻ 09:09–09:11 hiện
    "Dừng máy 09:09–00:21" cho lần hết giấy lúc nửa đêm (DB dev 17/09/2026)."""
    _to, cv, batch = _canh_phan_bo(db, orders, lsx_svc, admin, customer, ma="TO-ME-DUNG")
    bd = _aware(batch.bat_dau)
    dung_tu, chay_lai = bd + timedelta(minutes=20), bd + timedelta(minutes=35)
    _phien(db, cv, bat_dau=bd, ket_thuc=dung_tu, loai_dong="tam_dung", ly_do="kẹt giấy", stt=1)
    _phien(db, cv, bat_dau=chay_lai, ket_thuc=None, loai_dong=None, stt=2)
    db.commit()

    su_co = _mes(db, admin, cv)[0]["su_co"]
    assert [(s["bat_dau"], s["ket_thuc"]) for s in su_co] == [
        (thuc_te_hien_thi(dung_tu), thuc_te_hien_thi(chay_lai))]


def test_dung_may_ngoai_cua_so_me_khong_gan_vao_me(db, orders, lsx_svc, admin, customer):
    """Phiên chạy phủ qua mẻ nhưng lúc DỪNG rơi sau mẻ ⇒ mẻ không có lần dừng nào."""
    _to, cv, batch = _canh_phan_bo(db, orders, lsx_svc, admin, customer, ma="TO-ME-DUNG-SAU")
    bd = _aware(batch.bat_dau)
    dung_tu = _aware(batch.ket_thuc) + timedelta(hours=10)
    _phien(db, cv, bat_dau=bd, ket_thuc=dung_tu, loai_dong="tam_dung", ly_do="hết giấy", stt=1)
    _phien(db, cv, bat_dau=dung_tu + timedelta(minutes=1), ket_thuc=dung_tu + timedelta(minutes=3),
           stt=2)
    db.commit()

    assert _mes(db, admin, cv)[0]["su_co"] == []


def test_dung_may_chua_chay_lai_de_trong_gio_het(db, orders, lsx_svc, admin, customer):
    """Việc còn đang tạm dừng, chưa có phiên kế ⇒ lần dừng chưa hết: `ket_thuc` trống."""
    _to, cv, batch = _canh_phan_bo(db, orders, lsx_svc, admin, customer, ma="TO-ME-DUNG-MO")
    bd = _aware(batch.bat_dau)
    _phien(db, cv, bat_dau=bd, ket_thuc=bd + timedelta(minutes=20), loai_dong="tam_dung",
           ly_do="mất điện", stt=1)
    cv.trang_thai = CV_TAM_DUNG
    db.commit()

    su_co = _mes(db, admin, cv)[0]["su_co"]
    assert [(s["ly_do"], s["ket_thuc"]) for s in su_co] == [("mất điện", None)]


def test_me_mang_ten_dau_viec_ke_hoach_da_chon_nhung_khong_mang_gia(
    db, orders, lsx_svc, admin, customer,
):
    _to, cv, batch = _canh_phan_bo(db, orders, lsx_svc, admin, customer, ma="TO-ME-DV")
    cv.khoan_json = {"ten": "Bế hộp bánh · 1050"}
    e = _emp(db, cv_to(db, cv), "NV-ME-1", ten="Thợ Mẻ")
    db.commit()
    _khoang(db, cv, e, batch.bat_dau, batch.ket_thuc)
    db.commit()

    me = _mes(db, admin, cv)[0]
    assert me["dau_viec_ten"] == "Bế hộp bánh · 1050"
    assert me["so_nguoi"] >= 1
    assert "don_gia" not in me and "tien" not in me


def cv_to(db, cv):
    from app.models.department import Department

    return db.get(Department, cv.department_id)
