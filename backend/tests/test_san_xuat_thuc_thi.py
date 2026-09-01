"""Thực hiện sản xuất — Giai đoạn 2 mặt GHI: phân công · phiên chạy · khoảng tham gia (§7.1–§7.2).

Soi tầng service `services/san_xuat/thuc_thi.py` (nơi chứa LUẬT), không qua HTTP:
  · phân công snapshot cờ lương khoán từ `departments.has_piece_work`; bước nội bộ chỉ nhận khoán;
  · GATE §6: chỉ `department.head_user_id` của CHÍNH tổ mới ghi (cấp trên scope rộng KHÔNG ghi đè);
  · bắt đầu cần ≥1 thợ khoán, bắt đầu/kết thúc TRỄ cần lý do, một người không hai khoảng chồng giờ;
  · tạm dừng/kết thúc đóng phiên + mọi khoảng tham gia; version chống bấm trùng.

Một test API cuối chứng minh đường dây RBAC: admin (Giám đốc, KHÔNG có bit `can_assign_work`) → 403.

Tái dùng luồng thật (đơn → SX → sẵn sàng → phát hành vào một tổ) từ test bàn tổ.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models.department import Department
from app.models.employee import Employee
from app.models.user import User
from app.models.san_xuat import (
    BUOC_MAY,
    BUOC_TO,
    CV_DANG_CHAY,
    CV_HOAN_THANH,
    CV_TAM_DUNG,
    SanXuatCongViec,
)
from app.models.san_xuat_thuc_thi import (
    PC_DA_RUT,
    PC_HOAT_DONG,
    PHIEN_KET_THUC,
    PHIEN_TAM_DUNG,
    SanXuatKhoangThamGia,
    SanXuatPhanCong,
    SanXuatPhienChay,
)
from app.models.employee import STATUS_RESIGNED
from app.services.san_xuat import board, thuc_thi

# Fixtures luồng thật + helper phát hành vào một tổ (kéo theo cả cây fixture xếp lịch).
from tests.test_san_xuat_board import (  # noqa: F401
    _authz,
    _phat_hanh_vao_to,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
)


# --- Dàn cảnh dùng chung --------------------------------------------------------------------
def _to_khoan(db, admin, ma="TO-TT") -> Department:
    """Tổ sản xuất bật lương khoán, admin làm tổ trưởng (để qua GATE §6 khi gọi service).

    `name` khai theo `ma` — `name` UNIQUE nên test gọi hàm này NHIỀU LẦN (2 tổ khác nhau trong
    cùng một test) phải truyền `ma` khác nhau, không thì đụng UNIQUE constraint."""
    d = Department(
        name=f"Tổ Thực Thi {ma}", code=ma, la_san_xuat=True,
        has_piece_work=True, head_user_id=admin.id,
    )
    db.add(d)
    db.flush()
    return d


def _to_cong_nhat(db, ma="TO-CN") -> Department:
    d = Department(name="Tổ Công Nhật", code=ma, la_san_xuat=True, has_piece_work=False)
    db.add(d)
    db.flush()
    return d


def _emp(db, dept, ma, ten="Thợ", user_id=None) -> Employee:
    e = Employee(code=ma, full_name=ten, department_id=dept.id, user_id=user_id)
    db.add(e)
    db.flush()
    return e


def _cvs(db, to) -> list[SanXuatCongViec]:
    return (
        db.query(SanXuatCongViec)
        .filter_by(department_id=to.id)
        .order_by(SanXuatCongViec.id)
        .all()
    )


def _mot_cv(db, orders, lsx_svc, admin, customer, *, ma="TO-TT"):
    """Một tổ khoán + một công việc BUOC_MAY không hạn dự kiến (khỏi vướng luật trễ)."""
    to = _to_khoan(db, admin, ma=ma)
    _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)
    cv = _cvs(db, to)[0]
    cv.loai_buoc = BUOC_MAY
    cv.du_kien_bat_dau = None
    cv.du_kien_ket_thuc = None
    db.commit()
    return to, cv


def _mo_khoang(db, cv):
    return db.query(SanXuatKhoangThamGia).filter_by(cong_viec_id=cv.id, ket_thuc=None).all()


# --- Phân công (§7.1) -----------------------------------------------------------------------
def test_phan_cong_snapshot_co_khoan_va_tiep_nhan(db, orders, lsx_svc, admin, customer):
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer)
    e = _emp(db, to, "NV-TT-1", user_id=None)     # thợ khoán, KHÔNG tài khoản
    truoc = cv.version

    res = thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv.id, employee_id=e.id)

    assert res["cong_viec_id"] == cv.id
    assert res["version"] == truoc + 1            # version bật để chống bấm trùng
    assert res["notify_user_id"] is None          # không tài khoản → không đẩy thông báo
    pcs = db.query(SanXuatPhanCong).filter_by(cong_viec_id=cv.id, trang_thai=PC_HOAT_DONG).all()
    assert len(pcs) == 1 and pcs[0].la_luong_khoan is True


def test_phan_cong_bao_notify_khi_co_tai_khoan(db, orders, lsx_svc, admin, customer):
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer)
    u = User(username="tho_tt_2", name="Thợ Có Tài Khoản", password_hash="x")
    db.add(u)
    db.flush()
    e = _emp(db, to, "NV-TT-2", user_id=u.id)      # thợ CÓ tài khoản → phải đẩy thông báo
    res = thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv.id, employee_id=e.id)
    assert res["notify_user_id"] == u.id


def test_buoc_noi_bo_chi_nhan_tho_khoan(db, orders, lsx_svc, admin, customer):
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer)
    cv.loai_buoc = BUOC_TO
    db.commit()
    cn = _emp(db, _to_cong_nhat(db), "NV-CN-1")    # tổ không khoán
    with pytest.raises(ValueError):
        thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv.id, employee_id=cn.id)


def test_khong_giao_trung_mot_nguoi(db, orders, lsx_svc, admin, customer):
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer)
    e = _emp(db, to, "NV-TT-3")
    thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv.id, employee_id=e.id)
    with pytest.raises(ValueError):
        thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv.id, employee_id=e.id)


# --- GATE §6: chỉ tổ trưởng đúng tổ -------------------------------------------------------
def test_gate_chi_to_truong_dung_to(db, orders, lsx_svc, admin, customer):
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer)
    e = _emp(db, to, "NV-TT-4")
    nguoi_la = SimpleNamespace(id=admin.id + 99_999)   # không phải head_user_id của tổ
    with pytest.raises(PermissionError):
        thuc_thi.phan_cong(db, user=nguoi_la, cong_viec_id=cv.id, employee_id=e.id)


def test_version_lech_bi_chan(db, orders, lsx_svc, admin, customer):
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer)
    e = _emp(db, to, "NV-TT-5")
    with pytest.raises(ValueError):
        thuc_thi.phan_cong(
            db, user=admin, cong_viec_id=cv.id, employee_id=e.id,
            expected_version=cv.version + 5,
        )


# --- Phiên chạy (§7.2) ----------------------------------------------------------------------
def test_bat_dau_can_it_nhat_mot_khoan(db, orders, lsx_svc, admin, customer):
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer)
    cn = _emp(db, _to_cong_nhat(db), "NV-CN-2")             # chỉ công nhật → chưa đủ
    thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv.id, employee_id=cn.id)
    with pytest.raises(ValueError):
        thuc_thi.bat_dau(db, user=admin, cong_viec_id=cv.id)

    khoan = _emp(db, to, "NV-K-1")                          # thêm thợ khoán → mở được
    thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv.id, employee_id=khoan.id)
    # Roster 2 người > định mức seed (1) → §7.1 đòi lý do lệch số người; test này soi luật khoán.
    res = thuc_thi.bat_dau(
        db, user=admin, cong_viec_id=cv.id, ly_do_so_nguoi="Ghép thêm công nhật hỗ trợ",
    )

    assert res["trang_thai"] == CV_DANG_CHAY
    phien = db.query(SanXuatPhienChay).filter_by(cong_viec_id=cv.id).all()
    assert len(phien) == 1 and phien[0].ket_thuc is None
    assert len(_mo_khoang(db, cv)) == 2                     # mở khoảng cho cả roster


def test_bat_dau_tre_bat_buoc_ly_do(db, orders, lsx_svc, admin, customer):
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer)
    cv.du_kien_bat_dau = datetime.now(timezone.utc) - timedelta(hours=2)
    db.commit()
    thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv.id, employee_id=_emp(db, to, "NV-K-2").id)

    with pytest.raises(ValueError):
        thuc_thi.bat_dau(db, user=admin, cong_viec_id=cv.id)          # trễ, thiếu lý do
    res = thuc_thi.bat_dau(db, user=admin, cong_viec_id=cv.id, ly_do_tre="Máy hỏng chờ sửa")
    assert res["trang_thai"] == CV_DANG_CHAY


def _dat_dinh_muc_so_nguoi(db, cv, n: int) -> None:
    """Gán số người dự kiến (chốt lúc phát hành) vào dinh_muc_json — gán lại cả dict để SA bắt dirty."""
    cv.dinh_muc_json = {**(cv.dinh_muc_json or {}), "so_nhan_cong_tieu_chuan": n}
    db.commit()


def test_bat_dau_lech_so_nguoi_bat_buoc_ly_do(db, orders, lsx_svc, admin, customer):
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer)
    _dat_dinh_muc_so_nguoi(db, cv, 2)                     # dự kiến 2 người
    thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv.id, employee_id=_emp(db, to, "NV-LSN-1").id)

    with pytest.raises(ValueError):                       # thực tế 1 ≠ dự kiến 2, thiếu lý do → chặn
        thuc_thi.bat_dau(db, user=admin, cong_viec_id=cv.id)
    res = thuc_thi.bat_dau(
        db, user=admin, cong_viec_id=cv.id, ly_do_so_nguoi="Một thợ nghỉ đột xuất",
    )
    assert res["trang_thai"] == CV_DANG_CHAY
    phien = db.query(SanXuatPhienChay).filter_by(cong_viec_id=cv.id).first()
    assert phien.ly_do_so_nguoi == "Một thợ nghỉ đột xuất"


def test_bat_dau_khop_so_nguoi_khong_can_ly_do(db, orders, lsx_svc, admin, customer):
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer)
    _dat_dinh_muc_so_nguoi(db, cv, 1)                     # dự kiến 1 người
    thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv.id, employee_id=_emp(db, to, "NV-LSN-2").id)

    # Khớp số người: khỏi lý do; lý do thừa (nếu có) KHÔNG được ghi lại.
    res = thuc_thi.bat_dau(db, user=admin, cong_viec_id=cv.id, ly_do_so_nguoi="thừa")
    assert res["trang_thai"] == CV_DANG_CHAY
    phien = db.query(SanXuatPhienChay).filter_by(cong_viec_id=cv.id).first()
    assert phien.ly_do_so_nguoi is None


def test_mot_nguoi_khong_hai_khoang_chong_gio(db, orders, lsx_svc, admin, customer):
    to = _to_khoan(db, admin)
    _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)
    cvs = _cvs(db, to)
    cv1, cv2 = cvs[0], cvs[1]
    for cv in (cv1, cv2):
        cv.loai_buoc = BUOC_MAY
        cv.du_kien_bat_dau = None
    db.commit()
    e = _emp(db, to, "NV-DUP")

    thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv1.id, employee_id=e.id)
    thuc_thi.bat_dau(db, user=admin, cong_viec_id=cv1.id)             # e có khoảng mở ở cv1
    thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv2.id, employee_id=e.id)  # cv2 chưa chạy → ok
    with pytest.raises(ValueError):
        thuc_thi.bat_dau(db, user=admin, cong_viec_id=cv2.id)         # chồng giờ → chặn


def test_tam_dung_dong_phien_va_khoang(db, orders, lsx_svc, admin, customer):
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer)
    thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv.id, employee_id=_emp(db, to, "NV-K-3").id)
    thuc_thi.bat_dau(db, user=admin, cong_viec_id=cv.id)

    with pytest.raises(ValueError):
        thuc_thi.tam_dung(db, user=admin, cong_viec_id=cv.id, ly_do="")   # thiếu lý do
    res = thuc_thi.tam_dung(db, user=admin, cong_viec_id=cv.id, ly_do="Hết giấy")

    assert res["trang_thai"] == CV_TAM_DUNG
    phien = db.query(SanXuatPhienChay).filter_by(cong_viec_id=cv.id).first()
    assert phien.ket_thuc is not None
    assert phien.loai_dong == PHIEN_TAM_DUNG and phien.ly_do == "Hết giấy"
    assert len(_mo_khoang(db, cv)) == 0                                # khoảng đóng theo


def test_ket_thuc_hoan_thanh_dong_phien(db, orders, lsx_svc, admin, customer):
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer)
    thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv.id, employee_id=_emp(db, to, "NV-K-4").id)
    thuc_thi.bat_dau(db, user=admin, cong_viec_id=cv.id)

    res = thuc_thi.ket_thuc(db, user=admin, cong_viec_id=cv.id)
    assert res["trang_thai"] == CV_HOAN_THANH
    phien = db.query(SanXuatPhienChay).filter_by(cong_viec_id=cv.id).first()
    assert phien.loai_dong == PHIEN_KET_THUC and phien.ket_thuc is not None
    assert len(_mo_khoang(db, cv)) == 0


def test_ket_thuc_tre_bat_buoc_ly_do(db, orders, lsx_svc, admin, customer):
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer)
    thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv.id, employee_id=_emp(db, to, "NV-K-5").id)
    thuc_thi.bat_dau(db, user=admin, cong_viec_id=cv.id)
    cv.du_kien_ket_thuc = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()

    with pytest.raises(ValueError):
        thuc_thi.ket_thuc(db, user=admin, cong_viec_id=cv.id)          # trễ, chưa có lý do nào
    res = thuc_thi.ket_thuc(db, user=admin, cong_viec_id=cv.id, ly_do_tre="Sự cố điện")
    assert res["trang_thai"] == CV_HOAN_THANH


def test_ket_thuc_tre_mien_ly_do_khi_da_tam_dung_co_ly_do(db, orders, lsx_svc, admin, customer):
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer)
    thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv.id, employee_id=_emp(db, to, "NV-K-6").id)
    thuc_thi.bat_dau(db, user=admin, cong_viec_id=cv.id)
    cv.du_kien_ket_thuc = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()
    thuc_thi.tam_dung(db, user=admin, cong_viec_id=cv.id, ly_do="Kẹt giấy")  # lý do đã giải thích

    res = thuc_thi.ket_thuc(db, user=admin, cong_viec_id=cv.id)              # trễ nhưng khỏi lý do
    assert res["trang_thai"] == CV_HOAN_THANH


def test_go_phan_cong_dong_khoang_dang_mo(db, orders, lsx_svc, admin, customer):
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer)
    e = _emp(db, to, "NV-K-7")
    thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv.id, employee_id=e.id)
    thuc_thi.bat_dau(db, user=admin, cong_viec_id=cv.id)
    pc = db.query(SanXuatPhanCong).filter_by(cong_viec_id=cv.id, employee_id=e.id).first()

    thuc_thi.go_phan_cong(db, user=admin, phan_cong_id=pc.id, ly_do="Đổi người")

    db.refresh(pc)
    assert pc.trang_thai == PC_DA_RUT and pc.ly_do_rut == "Đổi người"
    con_mo = db.query(SanXuatKhoangThamGia).filter_by(
        cong_viec_id=cv.id, employee_id=e.id, ket_thuc=None
    ).count()
    assert con_mo == 0


# --- Nguồn danh cho ô "Giao người" (board.nhan_vien_chon) -----------------------------------
def test_nhan_vien_chon_liet_ke_to_khoan_bo_nghi(db, orders, lsx_svc, admin, customer):
    to, _cv = _mot_cv(db, orders, lsx_svc, admin, customer)
    con = _emp(db, to, "NV-CH-1", ten="Còn Làm")
    _emp(db, to, "NV-CH-9", ten="Đã Nghỉ").status = STATUS_RESIGNED
    _emp(db, _to_cong_nhat(db, ma="TO-CN-X"), "NV-KHAC-1")  # tổ khác → không lọt
    db.commit()

    res = board.nhan_vien_chon(db, admin, _authz(db), team_id=to.id)
    assert res["team_id"] == to.id
    ids = [r["id"] for r in res["nhan_vien"]]
    assert con.id in ids                                   # người còn làm có mặt
    assert all(r["full_name"] != "Đã Nghỉ" for r in res["nhan_vien"])  # đã nghỉ bị loại
    assert all(r["la_luong_khoan"] is True for r in res["nhan_vien"])  # tổ khoán → cả tổ khoán
    assert res["nhan_vien"][0]["co_tai_khoan"] is False    # thợ không tài khoản


def test_nhan_vien_chon_to_cong_nhat_khong_khoan(db, orders, lsx_svc, admin, customer):
    to, _cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-TT-CN")
    to.has_piece_work = False                              # biến tổ này thành công nhật
    _emp(db, to, "NV-CN-2")
    db.commit()
    res = board.nhan_vien_chon(db, admin, _authz(db), team_id=to.id)
    assert res["nhan_vien"] and all(r["la_luong_khoan"] is False for r in res["nhan_vien"])


def test_nhan_vien_chon_ngoai_pham_vi_bi_chan(db, orders, lsx_svc, admin, customer):
    to, _cv = _mot_cv(db, orders, lsx_svc, admin, customer)
    from app.models.role import SCOPE_OWN
    from tests.test_san_xuat_board import _FakeAuthz, _to_moi
    ngoai = _to_moi(db, "Tổ Ngoài TT", "TO-NG-TT")
    # KHÔNG dùng `admin.id`: `_to_khoan` đặt admin làm tổ trưởng của `to`, mà từ mg `0250`
    # (KCS kiêm nhiệm) `_to_thay_duoc` cho user thấy MỌI tổ mình đứng `head_user_id` kể cả ngoài
    # phòng — tổ trưởng kiêm nhiệm được `_gate` cho GHI thì cũng phải có lối vào để XEM. Muốn thử
    # đúng vế "ngoài phạm vi" thì người gọi phải KHÔNG phải tổ trưởng của tổ đích.
    nguoi_la = admin.id + 9_999
    assert to.head_user_id != nguoi_la
    user = SimpleNamespace(id=nguoi_la, department_id=ngoai.id, role_id=admin.role_id)
    with pytest.raises(PermissionError):
        board.nhan_vien_chon(db, user, _FakeAuthz(SCOPE_OWN), team_id=to.id)


# --- Đường dây RBAC: admin KHÔNG có bit can_assign_work → 403 --------------------------------
def test_api_admin_thieu_bit_assign_work_403(client):
    tok = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin123"}
    ).json()["access_token"]
    resp = client.post(
        "/api/san-xuat/work-items/1/phan-cong",
        json={"employee_id": 1},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert resp.status_code == 403
