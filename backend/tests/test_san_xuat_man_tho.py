"""Màn của THỢ (spec 2026-09-18 §7.5): "Các mẻ tôi tham gia" — sản lượng CẢ MẺ + danh sách người.

Trước 18/09/2026 thợ đọc "phần của tôi" từ dòng chia sản lượng đã chốt. Tầng chia gỡ hẳn (mg 0322,
chủ xưởng: *"ghi nhận thế thôi, đừng có chia bất cứ gì"*), nên thợ thấy con số của cả mẻ kèm tên
những người cùng làm — không số phút của ai, không tiền.

Phần drawer soi ở tầng SERVICE (`board.chi_tiet_cong_viec`) vì dàn cảnh cần hai người cùng một mẻ có
chấm công thật. "Thợ" là tài khoản thật được cấp dòng quyền của tổ theo vai mẫu Công nhân (Xem +
phạm vi Của tôi, mg 0302).
"""
from __future__ import annotations

from datetime import timedelta

from app.models.role import SCOPE_OWN
from app.models.san_xuat_phan_bo import HT_XAC_NHAN, SanXuatHoTro
from app.models.user import User
from app.services.san_xuat import board
from app.services.san_xuat.nguoi_trong_me import ngay_cua_me
from app.services.san_xuat.san_luong_cua_toi import san_luong_cua_toi
from tests.quyen_to_fixtures import cap_quyen_to
from tests.san_xuat_me_fixtures import T0, canh_me, cham_cong, khoang, tao_me
from tests.test_san_xuat_board import _giao

# Fixtures + helper luồng thật.
from tests.test_san_xuat_thuc_thi import (  # noqa: F401
    _emp,
    _to_cong_nhat,
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


def _canh_2_nguoi(db, orders, lsx_svc, admin, customer, *, ma):
    """Tổ (admin giữ dòng quyền Tất cả của tổ) + MỘT mẻ + hai người A/B cùng làm, cùng có chấm
    công hợp lệ. A có tài khoản riêng thuộc tổ (đóng vai THỢ mở bàn), B thì không.

    Cả hai đều phải có PHÂN CÔNG còn hiệu lực: thợ chưa được giao việc thì bị chặn ngay ở cửa
    drawer (§7.1), bài sẽ đỏ vì lý do khác hẳn điều nó muốn soi."""
    to, cv, batch = canh_me(db, orders, lsx_svc, admin, customer, ma=ma)
    u_a = User(username=f"tho_a_{ma.lower()}", name="Thợ A", password_hash="x",
               department_id=to.id)
    db.add(u_a)
    db.flush()
    cap_quyen_to(db, u_a, to, scope=SCOPE_OWN, viec=())
    a = _emp(db, to, f"NV-A-{ma}", ten="Thợ A Tên", user_id=u_a.id)
    b = _emp(db, to, f"NV-B-{ma}", ten="Thợ B Tên")
    cham_cong(db, a)
    cham_cong(db, b)
    db.commit()
    _giao(db, cv.id, a.id)
    _giao(db, cv.id, b.id)
    khoang(db, cv, a, batch.bat_dau, batch.ket_thuc)
    khoang(db, cv, b, batch.bat_dau, batch.ket_thuc)
    db.commit()
    return to, cv, batch, u_a, a, b


def test_tho_thay_ca_danh_sach_nguoi_trong_me_khong_so_phut(db, orders, lsx_svc, admin, customer):
    _to, cv, batch, tho, a, b = _canh_2_nguoi(
        db, orders, lsx_svc, admin, customer, ma="TO-THO-1")

    d = board.chi_tiet_cong_viec(db, tho, _authz(db), cong_viec_id=cv.id)
    assert "phan_bo" not in d
    me = next(m for m in d["san_luong"]["batches"] if m["id"] == batch.id)
    assert {n["ho_ten"] for n in me["nguoi_tham_gia"]} == {a.full_name, b.full_name}
    assert me["so_nguoi"] == 2
    assert "chia_du_kien" not in me
    # Không phút, không phần chia — chỉ tên + nhãn tổ gốc (người cùng tổ ⇒ trơn).
    assert all(set(n) == {"employee_id", "ho_ten", "to_ten"} for n in me["nguoi_tham_gia"])
    assert all(n["to_ten"] is None for n in me["nguoi_tham_gia"])


def test_cham_dung_moc_dau_me_khong_tinh_la_co_mat(db, orders, lsx_svc, admin, customer):
    """Drawer và tab Sản lượng dùng CHUNG một luật: khoảng chỉ chạm mốc bắt đầu mẻ thì KHÔNG có mặt."""
    to, cv, batch, _tho, a, b = _canh_2_nguoi(
        db, orders, lsx_svc, admin, customer, ma="TO-THO-MOC")
    c = _emp(db, to, "NV-C-MOC", ten="Thợ Vừa Rời")
    khoang(db, cv, c, batch.bat_dau - timedelta(hours=1), batch.bat_dau)
    db.commit()

    d = board.chi_tiet_cong_viec(db, admin, _authz(db), cong_viec_id=cv.id)
    me = next(m for m in d["san_luong"]["batches"] if m["id"] == batch.id)
    assert {n["ho_ten"] for n in me["nguoi_tham_gia"]} == {a.full_name, b.full_name}


def test_cac_me_toi_tham_gia_tra_ca_me_va_nguoi_cung_lam(db, orders, lsx_svc, admin, customer):
    _to, cv, batch, tho, a, b = _canh_2_nguoi(
        db, orders, lsx_svc, admin, customer, ma="TO-THO-3")
    # Mẻ thứ hai chỉ có B ⇒ không thuộc "của tôi" của A.
    b2 = tao_me(db, user=admin, cong_viec_id=cv.id, bat_dau=T0 + timedelta(hours=3),
                ket_thuc=T0 + timedelta(hours=4), tong=40, tot=40)["batch_id"]
    khoang(db, cv, b, T0 + timedelta(hours=3), T0 + timedelta(hours=4))
    db.commit()

    d = san_luong_cua_toi(db, tho, nam=T0.year, thang=T0.month)
    assert d["employee_id"] == a.id
    assert d["so_me"] == 1 and [m["batch_id"] for m in d["me"]] == [batch.id]
    assert b2 not in [m["batch_id"] for m in d["me"]]
    m = d["me"][0]
    assert m["tot"] == 100.0                                   # số của CẢ mẻ, không "phần của tôi"
    assert m["viec_khoan_ten"] == "Việc khoán test"
    assert {n["ho_ten"] for n in m["nguoi_tham_gia"]} == {"tôi", b.full_name}
    assert "tien" not in str(d) and "don_gia" not in str(d) and "phut" not in str(d)


def test_tho_sang_giup_to_khac_thay_nhan_to_theo_to_cua_minh(db, orders, lsx_svc, admin, customer):
    """§7.3b luật 2 ở màn thợ: "tổ đang xem" là tổ của CHÍNH thợ. Thợ tổ khác sang giúp thì người
    của tổ chủ mẻ mang nhãn tổ gốc, còn "tôi" để trơn — không dán nhãn lên chính mình."""
    to, cv, batch, _tho, a, b = _canh_2_nguoi(
        db, orders, lsx_svc, admin, customer, ma="TO-THO-GIUP")
    to2 = _to_cong_nhat(db, ma="TO-THO-GIUP2")
    u_c = User(username="tho_c_giup", name="Thợ C", password_hash="x", department_id=to2.id)
    db.add(u_c)
    db.flush()
    c = _emp(db, to2, "NV-C-GIUP", ten="Thợ C Tên", user_id=u_c.id)
    khoang(db, cv, c, batch.bat_dau, batch.ket_thuc)
    db.commit()

    m = san_luong_cua_toi(db, u_c, nam=T0.year, thang=T0.month)["me"][0]
    nhan = {n["ho_ten"]: n["to_ten"] for n in m["nguoi_tham_gia"]}
    assert nhan == {"tôi": None, a.full_name: to.name, b.full_name: to.name}


def test_nguoi_to_khac_sang_giup_qua_ho_tro_cheo_hien_o_drawer_va_man_tho(
    db, orders, lsx_svc, admin, customer,
):
    """Ô "Giao người" chỉ bày người trong tổ ⇒ người tổ khác vào mẻ bằng HỖ TRỢ CHÉO đã xác nhận
    (đúng công việc, đúng ngày xưởng của mẻ), không có khoảng tham gia. Drawer phải liệt kê họ kèm
    nhãn tổ gốc, và "Các mẻ tôi tham gia" của chính họ phải có mẻ đó (spec 18/09/2026 §13 bước 5-9)."""
    to, cv, batch, _tho, a, b = _canh_2_nguoi(
        db, orders, lsx_svc, admin, customer, ma="TO-THO-HT")
    to2 = _to_cong_nhat(db, ma="TO-THO-HT2")
    u_c = User(username="tho_c_ht", name="Thợ C", password_hash="x", department_id=to2.id)
    db.add(u_c)
    db.flush()
    c = _emp(db, to2, "NV-C-HT", ten="Thợ C Giúp", user_id=u_c.id)
    db.add(SanXuatHoTro(cong_viec_id=cv.id, employee_id=c.id, to_goc_id=to2.id,
                        to_thuc_hien_id=to.id, ngay_lam_viec=ngay_cua_me(batch.bat_dau),
                        trang_thai=HT_XAC_NHAN))
    db.commit()

    d = board.chi_tiet_cong_viec(db, admin, _authz(db), cong_viec_id=cv.id)
    me = next(m for m in d["san_luong"]["batches"] if m["id"] == batch.id)
    assert {n["ho_ten"]: n["to_ten"] for n in me["nguoi_tham_gia"]} == {
        a.full_name: None, b.full_name: None, c.full_name: to2.name}
    assert me["so_nguoi"] == 3

    ds = san_luong_cua_toi(db, u_c, nam=T0.year, thang=T0.month)["me"]
    assert [m["batch_id"] for m in ds] == [batch.id]
    assert {n["ho_ten"]: n["to_ten"] for n in ds[0]["nguoi_tham_gia"]} == {
        "tôi": None, a.full_name: to.name, b.full_name: to.name}


def test_tai_khoan_chua_noi_ho_so_thi_rong(db, admin):
    u = User(username="chua_noi_ho_so", name="Chưa Nối", password_hash="x")
    db.add(u)
    db.commit()
    d = san_luong_cua_toi(db, u, nam=2026, thang=9)
    assert d == {"nam": 2026, "thang": 9, "employee_id": None, "me": [], "so_me": 0}
