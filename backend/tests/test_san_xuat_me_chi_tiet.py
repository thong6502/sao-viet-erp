"""Mẻ phải đọc được trọn vẹn (spec 2026-09-11 §5.2) — không cột mới, mọi số đã có trong DB.

Chủ xưởng: *"tổ trưởng phải thấy được thông tin của từng mẻ và sản lượng các thứ, nói chung đầy đủ
và chi tiết để sau này hỗ trợ kế toán lương"*.

Bài viết ở tầng SERVICE (`board.chi_tiet_cong_viec`) chứ không qua HTTP: dàn cảnh "việc đang chạy
+ phiên đổi máy + mẻ + chấm công" chỉ dựng được bằng các helper của `san_xuat_me_fixtures` /
`test_san_xuat_thuc_thi`, và đường HTTP của drawer đã có bài riêng ở `test_san_xuat_board_api.py`.
"""
from __future__ import annotations

from datetime import timedelta

from app.models.attendance import WorkShift
from app.models.cong_doan import CongDoanKhoan, CongDoanKhoanPhatSinh
from app.models.lsx import LsxCongDoan
from app.models.may_thiet_bi import MayThietBi
from app.models.san_xuat import CV_TAM_DUNG
from app.models.san_xuat_thuc_thi import SanXuatPhienChay
from app.services.gio_xuong import thuc_te_hien_thi, ve_gio_xuong
from app.services.san_xuat import board
from app.services.san_xuat.thuc_thi import _aware

# Fixtures + helper luồng thật.
from tests.san_xuat_me_fixtures import T0 as _T0
from tests.san_xuat_me_fixtures import canh_me, khoang, tao_me
from tests.test_san_xuat_thuc_thi import (  # noqa: F401
    _emp,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
)


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
    r = tao_me(db, user=admin, cong_viec_id=cv.id,
               bat_dau=bat_dau, ket_thuc=ket_thuc, tong=tot, tot=tot)
    return r["batch_id"]


def _mes(db, admin, cv):
    return board.chi_tiet_cong_viec(
        db, admin, _authz(db), cong_viec_id=cv.id)["san_luong"]["batches"]


def test_me_mang_theo_may_da_chay_no(db, orders, lsx_svc, admin, customer):
    """Máy đứng trên PHIÊN, không trên công việc: đổi máy giữa chừng thì mỗi mẻ một máy khác nhau.
    Đọc `cv.may_id` là luôn ra máy HIỆN TẠI — sai cho mẻ chạy trước lúc đổi."""
    _to, cv, batch = canh_me(db, orders, lsx_svc, admin, customer, ma="TO-ME-MAY")
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
    _to, cv, batch = canh_me(db, orders, lsx_svc, admin, customer, ma="TO-ME-CA")
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
    _to, cv, batch = canh_me(db, orders, lsx_svc, admin, customer, ma="TO-ME-DUNG")
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
    _to, cv, batch = canh_me(db, orders, lsx_svc, admin, customer, ma="TO-ME-DUNG-SAU")
    bd = _aware(batch.bat_dau)
    dung_tu = _aware(batch.ket_thuc) + timedelta(hours=10)
    _phien(db, cv, bat_dau=bd, ket_thuc=dung_tu, loai_dong="tam_dung", ly_do="hết giấy", stt=1)
    _phien(db, cv, bat_dau=dung_tu + timedelta(minutes=1), ket_thuc=dung_tu + timedelta(minutes=3),
           stt=2)
    db.commit()

    assert _mes(db, admin, cv)[0]["su_co"] == []


def test_dung_may_chua_chay_lai_de_trong_gio_het(db, orders, lsx_svc, admin, customer):
    """Việc còn đang tạm dừng, chưa có phiên kế ⇒ lần dừng chưa hết: `ket_thuc` trống."""
    _to, cv, batch = canh_me(db, orders, lsx_svc, admin, customer, ma="TO-ME-DUNG-MO")
    bd = _aware(batch.bat_dau)
    _phien(db, cv, bat_dau=bd, ket_thuc=bd + timedelta(minutes=20), loai_dong="tam_dung",
           ly_do="mất điện", stt=1)
    cv.trang_thai = CV_TAM_DUNG
    db.commit()

    su_co = _mes(db, admin, cv)[0]["su_co"]
    assert [(s["ly_do"], s["ket_thuc"]) for s in su_co] == [("mất điện", None)]


def test_me_mang_viec_khoan_va_phat_sinh_da_chup_khong_co_thanh_tien(
    db, orders, lsx_svc, admin, customer,
):
    """Mẻ tự lấy KHOÁN CÔNG ĐOẠN: drawer đọc ẢNH CHỤP tên · ĐVT · đơn giá lúc ghi, kèm
    việc phát sinh đã tích. Không có ô THÀNH TIỀN nào — sản xuất chỉ ghi nhận số lượng (chốt ý 4)."""
    _to, cv, batch = canh_me(db, orders, lsx_svc, admin, customer, ma="TO-ME-DV")
    buoc = db.get(LsxCongDoan, cv.lsx_cong_doan_id)
    khoan_cfg = CongDoanKhoan(cong_doan_id=buoc.cong_doan_id, unit="to", unit_price=100)
    khoan_cfg.viec_phat_sinh.append(CongDoanKhoanPhatSinh(
        ten="Thay bản kẽm", don_gia=15000, don_vi="ban", thu_tu=0,
    ))
    db.add(khoan_cfg)
    db.flush()
    ps = khoan_cfg.viec_phat_sinh[0]
    e = _emp(db, cv_to(db, cv), "NV-ME-1", ten="Thợ Mẻ")
    db.commit()
    b2 = tao_me(
        db, user=admin, cong_viec_id=cv.id,
        bat_dau=_T0 + timedelta(hours=2), ket_thuc=_T0 + timedelta(hours=3), tong=30, tot=30,
        phat_sinh=[{"phat_sinh_id": ps.id, "so_luong": 2}],
    )["batch_id"]
    khoang(db, cv, e, batch.bat_dau, batch.ket_thuc)
    db.commit()

    mes = {m["id"]: m for m in _mes(db, admin, cv)}
    m1, m2 = mes[batch.id], mes[b2]
    assert (m1["viec_khoan_id"], m1["viec_khoan_ten"], m1["viec_khoan_don_gia"]) == (
        None, None, None)
    assert (m2["viec_khoan_id"], m2["viec_khoan_don_gia"]) == (khoan_cfg.id, 100.0)
    assert m1["phat_sinh"] == [] and m1["so_nguoi"] == 1
    assert [(p["ten"], p["so_luong"], p["don_gia"]) for p in m2["phat_sinh"]] == [
        ("Thay bản kẽm", 2.0, 15000.0)]
    # Việc phát sinh KHÔNG cộng vào sản lượng: mẻ 2 vẫn đúng 30 tốt.
    assert m2["tot"] == 30.0
    for m in (m1, m2):
        assert "tien" not in m and "thanh_tien" not in m
        assert all("thanh_tien" not in p for p in m["phat_sinh"])


def cv_to(db, cv):
    from app.models.department import Department

    return db.get(Department, cv.department_id)
