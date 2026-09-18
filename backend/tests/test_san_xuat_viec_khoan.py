"""Ghi mẻ theo CÔNG VIỆC KHOÁN (spec 2026-09-18 §7.1 · §7.2 · §7.2b).

Soi `services/san_xuat/viec_khoan.py` + đường ghi `san_luong.tao_batch`:
  · danh sách việc của tổ: đơn giá · ĐVT · ghi chú + việc phát sinh (tên · đơn giá · ĐVT); ô tìm
    TƯƠNG ĐỐI (bỏ dấu, khớp một phần, cả mã lẫn tên);
  · mẻ BẮT BUỘC một việc khoán của đúng tổ, còn dùng — trừ bước THUÊ NGOÀI;
  · việc phát sinh phải thuộc chính việc đã chọn, số lượng > 0, và KHÔNG cộng vào sản lượng;
  · mẻ CHỤP đơn giá lúc ghi; danh mục đổi thì băng nói, chỉ đổi số khi người bấm.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.models.san_xuat import BUOC_THUE_NGOAI, CV_DANG_CHAY
from app.models.san_xuat_san_luong import SanXuatBatch
from app.services.danh_muc_tham_chieu import tham_chieu
from app.services.san_xuat import board, san_luong, viec_khoan
from tests.san_xuat_me_fixtures import T0, viec_khoan_cua_to, viec_phat_sinh
from tests.test_san_xuat_thuc_thi import (  # noqa: F401
    _mot_cv,
    _to_khoan,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
)


def _cv_chay(db, orders, lsx_svc, admin, customer, ma="TO-VK"):
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma=ma)
    cv.trang_thai = CV_DANG_CHAY
    cv.don_vi_ra = "tờ"
    cv.don_vi_vao = "tờ"
    db.commit()
    return to, cv


def _ghi(db, admin, cv, **kw):
    kw.setdefault("bat_dau", T0)
    kw.setdefault("ket_thuc", T0 + timedelta(hours=1))
    kw.setdefault("tong", 100)
    kw.setdefault("tot", 100)
    return san_luong.tao_batch(db, user=admin, cong_viec_id=cv.id, **kw)


def _bo_viec_nen(ds):
    """Bỏ việc khoán NỀN (`VK-T<tổ>`) mà fixture lập lệnh tự khai để qua cổng Sẵn sàng."""
    return [d for d in ds if not (d["ma"] or "").startswith("VK-T")]


def _authz(db):
    from app.repositories.rbac_repo import RoleRepository
    from app.services.rbac_service import AuthorizationService

    return AuthorizationService(RoleRepository(db))


# --- Danh sách việc của tổ (§7.1) -----------------------------------------------------------
def test_danh_sach_viec_cua_to_mang_du_gia_dvt_ghi_chu_va_phat_sinh(db, orders, lsx_svc, admin, customer):
    to, _cv = _cv_chay(db, orders, lsx_svc, admin, customer)
    vk = viec_khoan_cua_to(db, to.id, ma="KH-0013", ten="Bình bài & ra kẽm", don_gia=15000,
                           unit="kem", note="Tính theo bản")
    viec_phat_sinh(db, vk, ten="Thay bản kẽm", don_gia=15000, don_vi="kem")
    khac = _to_khoan(db, admin, ma="TO-VK-KHAC")
    viec_khoan_cua_to(db, khac.id, ma="KH-0099", ten="Việc tổ khác")
    db.commit()

    ds = _bo_viec_nen(viec_khoan.danh_sach_cua_to(db, department_id=to.id))
    assert [d["ma"] for d in ds] == ["KH-0013"]                  # chỉ việc của ĐÚNG tổ
    d = ds[0]
    assert (d["ten"], d["don_gia"], d["don_vi"], d["ghi_chu"]) == (
        "Bình bài & ra kẽm", 15000.0, "kem", "Tính theo bản")
    assert [(p["ten"], p["don_gia"], p["don_vi"]) for p in d["phat_sinh"]] == [
        ("Thay bản kẽm", 15000.0, "kem")]


def test_o_tim_tuong_doi_bo_dau_khop_mot_phan_ca_ma_lan_ten(db, orders, lsx_svc, admin, customer):
    to, _cv = _cv_chay(db, orders, lsx_svc, admin, customer)
    viec_khoan_cua_to(db, to.id, ma="KH-0013", ten="Bình bài & ra kẽm")
    viec_khoan_cua_to(db, to.id, ma="KH-0020", ten="Cán màng mờ")
    db.commit()

    def _ma(tim):
        return [d["ma"] for d in _bo_viec_nen(
            viec_khoan.danh_sach_cua_to(db, department_id=to.id, tim=tim))]

    assert _ma("ra kem") == ["KH-0013"]          # không dấu vẫn khớp
    assert _ma("MÀNG") == ["KH-0020"]            # hoa/thường, một phần của tên
    assert _ma("0020") == ["KH-0020"]            # khớp theo mã
    assert _ma("") == ["KH-0013", "KH-0020"]
    assert _ma("không có") == []


def test_viec_ngung_dung_khong_hien_trong_danh_sach(db, orders, lsx_svc, admin, customer):
    to, _cv = _cv_chay(db, orders, lsx_svc, admin, customer)
    vk = viec_khoan_cua_to(db, to.id, ma="KH-0050")
    vk.active = False
    db.commit()
    assert _bo_viec_nen(viec_khoan.danh_sach_cua_to(db, department_id=to.id)) == []


# --- Ghi mẻ: bắt buộc việc khoán (§7.2) -----------------------------------------------------
def test_me_bat_buoc_chon_viec_khoan(db, orders, lsx_svc, admin, customer):
    _to, cv = _cv_chay(db, orders, lsx_svc, admin, customer)
    with pytest.raises(ValueError, match="phải chọn một công việc khoán"):
        _ghi(db, admin, cv)


def test_viec_khoan_cua_to_khac_hoac_ngung_dung_bi_chan(db, orders, lsx_svc, admin, customer):
    to, cv = _cv_chay(db, orders, lsx_svc, admin, customer)
    khac = _to_khoan(db, admin, ma="TO-VK-K2")
    cua_khac = viec_khoan_cua_to(db, khac.id, ma="KH-0101")
    ngung = viec_khoan_cua_to(db, to.id, ma="KH-0102")
    ngung.active = False
    db.commit()
    for vk in (cua_khac, ngung):
        with pytest.raises(ValueError, match="không thuộc tổ của bước này"):
            _ghi(db, admin, cv, piece_rate_id=vk.id)
        db.rollback()


def test_me_chup_ten_dvt_don_gia_luc_ghi(db, orders, lsx_svc, admin, customer):
    to, cv = _cv_chay(db, orders, lsx_svc, admin, customer)
    vk = viec_khoan_cua_to(db, to.id, ma="KH-0200", ten="Bế hộp", don_gia=120, unit="to")
    db.commit()
    b = db.get(SanXuatBatch, _ghi(db, admin, cv, piece_rate_id=vk.id)["batch_id"])
    assert (b.piece_rate_id, b.ten_khoan_snapshot, b.don_vi_khoan_snapshot) == (vk.id, "Bế hộp", "to")
    assert float(b.don_gia_khoan_snapshot) == 120


def test_viec_khoan_da_co_me_ghi_thi_chan_xoa_han(db, orders, lsx_svc, admin, customer):
    """Tham chiếu DUY NHẤT còn lại tới công việc khoán là ID THẬT trên mẻ (`piece_rate_id`). Mẻ có
    ảnh chụp nên số không xê dịch, nhưng xoá hẳn thì hết đường tra "đơn giá này ở đâu ra" — chỉ
    cho ngừng dùng. Việc chưa ai ghi thì xoá được."""
    to, cv = _cv_chay(db, orders, lsx_svc, admin, customer)
    vk = viec_khoan_cua_to(db, to.id, ma="KH-0250", ten="Bế hộp")
    trong = viec_khoan_cua_to(db, to.id, ma="KH-0251", ten="Chưa ai ghi")
    db.commit()
    _ghi(db, admin, cv, piece_rate_id=vk.id)

    tc = tham_chieu(db, "cong_viec_khoan", vk)
    assert not tc.xoa_han_duoc
    assert tc.chan == ["1 mẻ sản lượng đã ghi"], tc.chan
    assert tham_chieu(db, "cong_viec_khoan", trong).xoa_han_duoc


def test_buoc_thue_ngoai_khong_bat_buoc_viec_khoan(db, orders, lsx_svc, admin, customer):
    """Thuê ngoài làm ở xưởng người ta — thợ của tổ không ăn khoán trên đó; cổng lập kế hoạch cũng
    miễn loại bước này. Nhưng đã tích việc phát sinh thì phải có việc khoán đi kèm."""
    _to, cv = _cv_chay(db, orders, lsx_svc, admin, customer)
    cv.loai_buoc = BUOC_THUE_NGOAI
    db.commit()
    b = db.get(SanXuatBatch, _ghi(db, admin, cv)["batch_id"])
    assert b.piece_rate_id is None and b.ten_khoan_snapshot is None
    with pytest.raises(ValueError, match="chọn việc khoán trước"):
        _ghi(db, admin, cv, bat_dau=T0 + timedelta(hours=2), ket_thuc=T0 + timedelta(hours=3),
             phat_sinh=[{"phat_sinh_id": 1, "so_luong": 1}])


# --- Việc phát sinh ---------------------------------------------------------------------------
def test_phat_sinh_phai_thuoc_viec_da_chon_va_so_luong_duong(db, orders, lsx_svc, admin, customer):
    to, cv = _cv_chay(db, orders, lsx_svc, admin, customer)
    vk = viec_khoan_cua_to(db, to.id, ma="KH-0300")
    vk2 = viec_khoan_cua_to(db, to.id, ma="KH-0301")
    ps = viec_phat_sinh(db, vk)
    ps_la = viec_phat_sinh(db, vk2, ten="Của việc khác")
    db.commit()
    cac_loi = [
        ([{"phat_sinh_id": ps_la.id, "so_luong": 1}], "không thuộc công việc khoán"),
        ([{"phat_sinh_id": ps.id, "so_luong": 0}], "phải lớn hơn 0"),
        ([{"phat_sinh_id": ps.id, "so_luong": "abc"}], "không hợp lệ"),
        ([{"phat_sinh_id": ps.id, "so_luong": 1}, {"phat_sinh_id": ps.id, "so_luong": 2}],
         "bị chọn hai lần"),
    ]
    for phat_sinh, loi in cac_loi:
        with pytest.raises(ValueError, match=loi):
            _ghi(db, admin, cv, piece_rate_id=vk.id, phat_sinh=phat_sinh)
        db.rollback()


def test_phat_sinh_khong_cong_vao_san_luong(db, orders, lsx_svc, admin, customer):
    """Chủ xưởng: *"chỗ việc phát sinh như lên khuôn không cộng vào sản lượng"*."""
    to, cv = _cv_chay(db, orders, lsx_svc, admin, customer)
    vk = viec_khoan_cua_to(db, to.id, ma="KH-0400")
    ps1 = viec_phat_sinh(db, vk, ten="Lên khuôn", don_vi="lan")
    ps2 = viec_phat_sinh(db, vk, ten="Thay bản kẽm", don_vi="kem")
    db.commit()
    _ghi(db, admin, cv, piece_rate_id=vk.id, tong=1000, tot=1000,
         phat_sinh=[{"phat_sinh_id": ps1.id, "so_luong": 3}, {"phat_sinh_id": ps2.id, "so_luong": 2}])

    assert san_luong.SanXuatSanLuongRepository(db).tong_tot(cv.id) == 1000
    d = board.chi_tiet_cong_viec(db, admin, _authz(db), cong_viec_id=cv.id)
    me = d["san_luong"]["batches"][0]
    assert me["tot"] == 1000.0
    assert sorted((p["ten"], p["so_luong"]) for p in me["phat_sinh"]) == [
        ("Lên khuôn", 3.0), ("Thay bản kẽm", 2.0)]


# --- Băng "Danh mục đã đổi" + cập nhật theo danh mục (§7.2b) ---------------------------------
def test_danh_muc_doi_bao_lech_va_chi_doi_khi_nguoi_bam(db, orders, lsx_svc, admin, customer):
    to, cv = _cv_chay(db, orders, lsx_svc, admin, customer)
    vk = viec_khoan_cua_to(db, to.id, ma="KH-0500", ten="Cán màng", don_gia=100)
    ps = viec_phat_sinh(db, vk, ten="Lên khuôn", don_gia=5000)
    db.commit()
    bid = _ghi(db, admin, cv, piece_rate_id=vk.id,
               phat_sinh=[{"phat_sinh_id": ps.id, "so_luong": 1}])["batch_id"]

    def _me():
        d = board.chi_tiet_cong_viec(db, admin, _authz(db), cong_viec_id=cv.id)
        return next(m for m in d["san_luong"]["batches"] if m["id"] == bid)

    assert _me()["danh_muc_doi"] == []                         # vừa ghi ⇒ khớp danh mục

    vk.unit_price = 120                                         # danh mục đổi giá
    ps.ten = "Lên khuôn bế"
    db.commit()
    doi = _me()["danh_muc_doi"]
    assert sorted(o["truong"] for o in doi) == ["don_gia", "ten"]
    assert "Lên khuôn bế" in str(doi) and "120" in str(doi)
    # Không bấm thì mẻ giữ số cũ.
    assert _me()["viec_khoan_don_gia"] == 100.0

    viec_khoan.cap_nhat_theo_danh_muc(db, user=admin, batch_id=bid)
    me = _me()
    assert me["danh_muc_doi"] == []
    assert me["viec_khoan_don_gia"] == 120.0
    assert [p["ten"] for p in me["phat_sinh"]] == ["Lên khuôn bế"]


def test_so_noi_dung_khong_so_moc_sua(db, orders, lsx_svc, admin, customer):
    """Lưu lại danh mục mà KHÔNG đổi số (chỉ chạm `updated_at`) thì băng không được bật."""
    to, cv = _cv_chay(db, orders, lsx_svc, admin, customer)
    vk = viec_khoan_cua_to(db, to.id, ma="KH-0600", don_gia=100)
    db.commit()
    bid = _ghi(db, admin, cv, piece_rate_id=vk.id)["batch_id"]
    vk.unit_price = 100.0
    vk.ten = "Việc khoán test "                                 # khoảng trắng thừa ⇒ cùng nội dung
    db.commit()
    b = db.get(SanXuatBatch, bid)
    assert viec_khoan.danh_muc_doi(db, b, [], department_id=to.id) == []


def test_viec_da_xoa_khoi_to_thi_bao_mat_khong_tu_go(db, orders, lsx_svc, admin, customer):
    to, cv = _cv_chay(db, orders, lsx_svc, admin, customer)
    vk = viec_khoan_cua_to(db, to.id, ma="KH-0700", ten="Việc sẽ gỡ")
    db.commit()
    bid = _ghi(db, admin, cv, piece_rate_id=vk.id)["batch_id"]
    vk.department_ids = []                                      # gỡ tổ khỏi việc
    db.commit()
    b = db.get(SanXuatBatch, bid)
    doi = viec_khoan.danh_muc_doi(db, b, [], department_id=to.id)
    assert [o["mat"] for o in doi] == [True]
    assert b.ten_khoan_snapshot == "Việc sẽ gỡ"                 # mẻ vẫn giữ ảnh chụp


def test_drawer_nap_doi_chieu_mot_lan_cho_nhieu_me(db, orders, lsx_svc, admin, customer):
    """Băng của N mẻ đọc chung một bản nạp — số truy vấn KHÔNG tăng theo số mẻ."""
    from sqlalchemy import event

    to, cv = _cv_chay(db, orders, lsx_svc, admin, customer)
    vk = viec_khoan_cua_to(db, to.id, ma="KH-0800")
    ps = viec_phat_sinh(db, vk)
    db.commit()

    def _dem_khi_mo():
        so: list[str] = []

        def _dem(conn, cursor, statement, *_a):
            so.append(statement)

        eng = db.get_bind()
        event.listen(eng, "before_cursor_execute", _dem)
        try:
            board.chi_tiet_cong_viec(db, admin, _authz(db), cong_viec_id=cv.id)
        finally:
            event.remove(eng, "before_cursor_execute", _dem)
        return len(so)

    for i in range(2):
        _ghi(db, admin, cv, piece_rate_id=vk.id, bat_dau=T0 + timedelta(hours=2 * i),
             ket_thuc=T0 + timedelta(hours=2 * i + 1),
             phat_sinh=[{"phat_sinh_id": ps.id, "so_luong": 1}])
    db.expire_all()
    hai = _dem_khi_mo()
    for i in range(2, 6):
        _ghi(db, admin, cv, piece_rate_id=vk.id, bat_dau=T0 + timedelta(hours=2 * i),
             ket_thuc=T0 + timedelta(hours=2 * i + 1),
             phat_sinh=[{"phat_sinh_id": ps.id, "so_luong": 1}])
    db.expire_all()
    assert _dem_khi_mo() == hai
