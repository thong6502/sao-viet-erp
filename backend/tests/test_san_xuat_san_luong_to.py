"""Tab SẢN LƯỢNG của Bàn tổ — `services/san_xuat/san_luong_to.py` (spec 2026-09-14 §6, sửa
2026-09-18 §7.3b).

Soi luật:
  · mẻ có đúng MỘT chủ (tổ của bước). Tổ khác có người trong mẻ thấy mẻ đó ở mục KHÁCH — cùng một
    con số, KHÔNG cộng vào tổng của mình ⇒ cộng tổng các tổ ra đúng sản lượng xưởng;
  · mỗi mẻ mang danh sách người tham gia; "người ngoài" mang nhãn tổ gốc (mẻ của tổ: ngoài tổ chủ;
    mục khách: ngoài vùng đang xem); không số phút, không phần chia, không tiền;
  · phạm vi TRỌN thấy mọi mẻ của tổ + dòng tổng; chỉ CỦA TÔI thấy đúng mẻ mình có mặt, không tổng;
  · ngày = ngày BẮT ĐẦU mẻ theo giờ xưởng; không cộng lẫn đơn vị;
  · lọc đơn vị (cây con), tìm mã lệnh, phân trang + tổng trên cả bộ lọc ở máy chủ.

Bản trước 18/09/2026 soi tầng "đã chốt / tạm tính" của engine chia sản lượng — gỡ hẳn (mg 0322).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.employee import Employee
from app.models.role import SCOPE_OWN
from app.models.san_xuat import SanXuatCongViec
from app.models.san_xuat_phan_bo import HT_CHO_HAI_BEN, HT_XAC_NHAN, SanXuatHoTro
from app.models.san_xuat_san_luong import SanXuatBatch
from app.models.user import User
from app.services.gio_xuong import ve_utc_that
from app.services.san_xuat import san_luong_to
from tests.quyen_to_fixtures import cap_quyen_to
from tests.san_xuat_me_fixtures import khoang
from tests.test_san_xuat_thuc_thi import (  # noqa: F401
    _cvs,
    _phat_hanh_vao_to,
    _to_cong_nhat,
    _to_khoan,
    _xuong_cha,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
)

_UTC = timezone.utc


def _gio_xuong(y, m, d, h=8, mi=0) -> datetime:
    """Giờ tường ở xưởng → UTC thật (thang của `san_xuat_batch.bat_dau`)."""
    return ve_utc_that(datetime(y, m, d, h, mi, tzinfo=_UTC))


def _me(db, cv, bat_dau, tot, hong=0, don_vi="tờ", viec=None, *co_mat) -> SanXuatBatch:
    """`co_mat` = người có khoảng tham gia phủ trọn mẻ."""
    b = SanXuatBatch(cong_viec_id=cv.id, bat_dau=bat_dau, ket_thuc=bat_dau + timedelta(hours=1),
                     tong=tot + hong, tot=tot, hong=hong, don_vi=don_vi, ten_khoan_snapshot=viec)
    db.add(b)
    db.flush()
    for e in co_mat:
        khoang(db, cv, e, b.bat_dau, b.ket_thuc)
    return b


def _nguoi(db, dept, username, ma) -> tuple[User, Employee]:
    u = User(username=username, name=f"Người {ma}", password_hash="x", department_id=dept.id)
    db.add(u)
    db.flush()
    e = Employee(code=ma, full_name=u.name, department_id=dept.id, user_id=u.id)
    db.add(e)
    db.flush()
    return u, e


@pytest.fixture
def xuong(db, orders, lsx_svc, admin, customer):
    """Xưởng → Tổ in (lệnh A) + Tổ cắt (lệnh B). Mẻ tháng 9/2026:
      · A · Tổ in: m1 90 tốt/10 hỏng tờ (hai thợ in) · m2 50 tờ (một thợ in) · m3 7 cái (không ai);
      · B · Tổ cắt: m4 200 tốt/5 hỏng tờ — thợ cắt + MỘT thợ Tổ in sang giúp;
      · A · Tổ in: một mẻ tháng 8 (ngoài khoảng mặc định)."""
    to_in = _to_khoan(db, admin, ma="TO-SL-IN")
    a, b, _ = _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to_in.id)
    to_cat = _to_cong_nhat(db, ma="TO-SL-CAT")
    x = _xuong_cha(db, "XUONG-SL", to_in, to_cat)
    cvs = _cvs(db, to_in)
    cv_a = next(cv for cv in cvs if cv.lsx_id == a.id)
    cv_b = next(cv for cv in cvs if cv.lsx_id == b.id)
    cv_b.department_id = to_cat.id

    _, tho_in = _nguoi(db, to_in, "tho_sl_in", "NV-SL-IN")
    u_tho2, tho_in2 = _nguoi(db, to_in, "tho_sl_in2", "NV-SL-IN2")
    _, tho_cat = _nguoi(db, to_cat, "tho_sl_cat", "NV-SL-CAT")

    m1 = _me(db, cv_a, _gio_xuong(2026, 9, 3), 90, 10, "tờ", "In 4 màu", tho_in, tho_in2)
    m2 = _me(db, cv_a, _gio_xuong(2026, 9, 5), 50, 0, "tờ", None, tho_in)
    m3 = _me(db, cv_a, _gio_xuong(2026, 9, 6), tot=7, hong=1, don_vi="cái")
    m4 = _me(db, cv_b, _gio_xuong(2026, 9, 4), 200, 5, "tờ", "Cắt thành phẩm", tho_cat, tho_in2)
    _me(db, cv_a, _gio_xuong(2026, 8, 20), tot=999)

    cap_quyen_to(db, admin, x)
    cap_quyen_to(db, u_tho2, to_in, scope=SCOPE_OWN, viec=())
    db.commit()
    return {"x": x, "to_in": to_in, "to_cat": to_cat, "a": a, "b": b, "tho2": u_tho2,
            "tho_in": tho_in, "tho_in2": tho_in2, "tho_cat": tho_cat,
            "m1": m1, "m2": m2, "m3": m3, "m4": m4}


def _lenh(res, lsx):
    return next(l for l in res["lenh"] if l["nguon_loai"] == "lsx" and l["nguon_id"] == lsx.id)


def _xem(db, user, team_id, **kw):
    kw.setdefault("tu", date(2026, 9, 1))
    kw.setdefault("den", date(2026, 9, 30))
    return san_luong_to.san_luong(db, user, team_id=team_id, **kw)


def test_quan_doc_thay_tron_lenh_cong_doan_me_va_nguoi(db, admin, xuong):
    res = _xem(db, admin, xuong["x"].id)

    assert res["tong_lenh"] == 2 and res["co_pham_vi_tron"]
    # Không cộng lẫn đơn vị: tờ và cái là hai dòng tổng riêng; mẻ tháng 8 nằm ngoài.
    tong = {t["don_vi"]: t for t in res["tong"]}
    assert tong["tờ"]["tot"] == 340 and tong["tờ"]["hong"] == 15 and tong["tờ"]["so_me"] == 3
    assert tong["cái"]["tot"] == 7 and tong["cái"]["so_me"] == 1

    la = _lenh(res, xuong["a"])
    assert {s["don_vi"]: s["tot"] for s in la["san_luong"]} == {"tờ": 140, "cái": 7}
    cd = la["cong_doan"][0]
    assert cd["to_id"] == xuong["to_in"].id and cd["la_khach"] is False and cd["so_me"] == 3
    me = {m["batch_id"]: m for m in cd["me"]}
    assert me[xuong["m1"].id]["viec_khoan_ten"] == "In 4 màu"
    assert me[xuong["m2"].id]["viec_khoan_ten"] is None           # mẻ chưa khai việc khoán
    assert {n["employee_id"] for n in me[xuong["m1"].id]["nguoi"]} == {
        xuong["tho_in"].id, xuong["tho_in2"].id}
    assert me[xuong["m3"].id]["nguoi"] == []
    # Người nhà thì không dán nhãn tổ; không ai có số phút hay phần chia.
    assert all(n["to_ten"] is None for n in me[xuong["m1"].id]["nguoi"])
    assert all(set(n) == {"employee_id", "ho_ten", "to_ten"} for m in cd["me"] for n in m["nguoi"])
    assert "tien" not in str(res) and "don_gia" not in str(res) and "phut" not in str(res)


def test_nguoi_sang_giup_mang_nhan_to_goc(db, admin, xuong):
    res = _xem(db, admin, xuong["x"].id)
    m4 = next(m for m in _lenh(res, xuong["b"])["cong_doan"][0]["me"]
              if m["batch_id"] == xuong["m4"].id)
    nhan = {n["employee_id"]: n["to_ten"] for n in m4["nguoi"]}
    assert nhan == {xuong["tho_cat"].id: None, xuong["tho_in2"].id: xuong["to_in"].name}


def test_me_mot_chu_to_khach_thay_cung_so_nhung_khong_cong_vao_tong(db, admin, xuong):
    """Ví dụ của chủ xưởng: a, b tổ bế + c tổ cán cùng làm một mẻ ⇒ tab của CẢ HAI tổ đều ghi nhận
    mẻ đó với cùng thông tin; chỉ tổ chủ cộng vào tổng."""
    to_in = _xem(db, admin, xuong["x"].id, to_id=xuong["to_in"].id)
    to_cat = _xem(db, admin, xuong["x"].id, to_id=xuong["to_cat"].id)

    # Tổ in thấy mẻ của Tổ cắt ở mục khách — đủ 200, không 50 hay phần nào khác.
    cd_khach = _lenh(to_in, xuong["b"])["cong_doan"][0]
    assert cd_khach["la_khach"] is True and cd_khach["to_id"] == xuong["to_cat"].id
    assert [(m["batch_id"], m["tot"]) for m in cd_khach["me"]] == [(xuong["m4"].id, 200.0)]
    assert _lenh(to_in, xuong["b"])["san_luong"] == []            # khách không vào dòng tổng lệnh
    # Mục khách dán nhãn theo tổ ĐANG XEM: người tổ chủ mang "Tổ cắt", người của mình để trơn.
    nhan = {n["employee_id"]: n["to_ten"] for n in cd_khach["me"][0]["nguoi"]}
    assert nhan == {xuong["tho_cat"].id: xuong["to_cat"].name, xuong["tho_in2"].id: None}
    assert {t["don_vi"]: t["tot"] for t in to_in["tong"]} == {"tờ": 140, "cái": 7}

    # Tổ cắt là chủ: cùng mẻ, cùng số, vào tổng.
    cd_chu = _lenh(to_cat, xuong["b"])["cong_doan"][0]
    assert cd_chu["la_khach"] is False
    assert [(m["batch_id"], m["tot"]) for m in cd_chu["me"]] == [(xuong["m4"].id, 200.0)]
    assert {t["don_vi"]: t["tot"] for t in to_cat["tong"]} == {"tờ": 200}

    # Cộng tổng hai tổ ra đúng tổng xưởng — không mẻ nào đếm hai lượt.
    xuong_tong = {t["don_vi"]: t["tot"] for t in _xem(db, admin, xuong["x"].id)["tong"]}
    assert 140 + 200 == xuong_tong["tờ"]


def _ho_tro(db, cv, emp, ngay, trang_thai=HT_XAC_NHAN) -> SanXuatHoTro:
    h = SanXuatHoTro(cong_viec_id=cv.id, employee_id=emp.id, to_goc_id=emp.department_id,
                     to_thuc_hien_id=cv.department_id, ngay_lam_viec=ngay, trang_thai=trang_thai)
    db.add(h)
    db.flush()
    return h


def test_nguoi_sang_giup_qua_ho_tro_cheo_khong_co_khoang_van_co_mat(db, admin, xuong):
    """Ô "Giao người" chỉ bày người trong tổ ⇒ người tổ khác vào mẻ bằng HỖ TRỢ CHÉO, không có
    khoảng tham gia. Thỏa thuận đủ hai bên xác nhận, đúng công việc + đúng NGÀY xưởng của mẻ ⇒ có
    mặt: tổ chủ thấy tên kèm nhãn tổ gốc, tổ của người đi giúp thấy mẻ ở mục khách (cùng số, không
    cộng tổng). Lệch ngày hoặc chưa đủ hai bên thì không."""
    cv_b = db.get(SanXuatCongViec, xuong["m4"].cong_viec_id)
    tho_in, tho_in2, tho_cat = xuong["tho_in"], xuong["tho_in2"], xuong["tho_cat"]
    m5 = _me(db, cv_b, _gio_xuong(2026, 9, 10), 300, 0, "tờ", "Cắt thành phẩm", tho_cat)
    m6 = _me(db, cv_b, _gio_xuong(2026, 9, 11), 40, 0, "tờ", "Cắt thành phẩm", tho_cat)
    _ho_tro(db, cv_b, tho_in2, date(2026, 9, 10))                       # đúng ngày m5
    _ho_tro(db, cv_b, tho_in, date(2026, 9, 12))                        # lệch ngày m6
    _ho_tro(db, cv_b, tho_in, date(2026, 9, 11), HT_CHO_HAI_BEN)        # chưa đủ hai bên
    db.commit()

    to_cat = _xem(db, admin, xuong["x"].id, to_id=xuong["to_cat"].id)
    me_cat = {m["batch_id"]: m for m in _lenh(to_cat, xuong["b"])["cong_doan"][0]["me"]}
    assert {n["employee_id"]: n["to_ten"] for n in me_cat[m5.id]["nguoi"]} == {
        tho_cat.id: None, tho_in2.id: xuong["to_in"].name}
    assert [n["employee_id"] for n in me_cat[m6.id]["nguoi"]] == [tho_cat.id]

    to_in = _xem(db, admin, xuong["x"].id, to_id=xuong["to_in"].id)
    cd_khach = _lenh(to_in, xuong["b"])["cong_doan"][0]
    assert cd_khach["la_khach"] is True
    assert sorted((m["batch_id"], m["tot"]) for m in cd_khach["me"]) == sorted(
        [(xuong["m4"].id, 200.0), (m5.id, 300.0)])
    assert {t["don_vi"]: t["tot"] for t in to_in["tong"]} == {"tờ": 140, "cái": 7}

    # Thợ chỉ "Của tôi" cũng thấy mẻ mình sang giúp — và chỉ mẻ đó.
    rieng = _xem(db, xuong["tho2"], xuong["to_in"].id)
    ids = {m["batch_id"] for l in rieng["lenh"] for c in l["cong_doan"] for m in c["me"]}
    assert m5.id in ids and m6.id not in ids


def test_ngay_la_ngay_bat_dau_me_theo_gio_xuong(db, admin, xuong):
    """Mẻ 01:30 sáng 7/9 giờ xưởng là 6/9 theo UTC — vẫn phải rơi vào ngày 7/9."""
    cv = _cvs(db, xuong["to_in"])[0]
    _me(db, cv, _gio_xuong(2026, 9, 7, 1, 30), tot=11, don_vi="bộ")
    db.commit()

    ngay_7 = _xem(db, admin, xuong["x"].id, tu=date(2026, 9, 7), den=date(2026, 9, 7))
    ngay_6 = _xem(db, admin, xuong["x"].id, tu=date(2026, 9, 6), den=date(2026, 9, 6))
    assert [t["don_vi"] for t in ngay_7["tong"]] == ["bộ"]
    assert "bộ" not in [t["don_vi"] for t in ngay_6["tong"]]


def test_tho_cua_toi_chi_thay_me_minh_co_mat_khong_tong(db, xuong):
    res = _xem(db, xuong["tho2"], xuong["to_in"].id)

    assert not res["co_pham_vi_tron"] and res["co_pham_vi_rieng"]
    assert res["tong"] == []
    assert res["tong_lenh"] == 2
    me = sorted((m["batch_id"], c["la_khach"])
                for l in res["lenh"] for c in l["cong_doan"] for m in c["me"])
    # m1 ở tổ mình + m4 sang giúp Tổ cắt; m2 (không có mặt) và m3 thì không lộ.
    assert me == sorted([(xuong["m1"].id, False), (xuong["m4"].id, True)])


def test_loc_don_vi_thu_ve_cay_con_va_chan_ngoai_vung(db, admin, xuong):
    res = _xem(db, admin, xuong["x"].id, to_id=xuong["to_cat"].id)
    assert res["tong_lenh"] == 1 and _lenh(res, xuong["b"])
    assert {t["don_vi"]: t["tot"] for t in res["tong"]} == {"tờ": 200}
    assert [d["id"] for d in res["cac_to"]] == [xuong["x"].id, xuong["to_in"].id, xuong["to_cat"].id]

    with pytest.raises(PermissionError):
        san_luong_to.san_luong(db, xuong["tho2"], team_id=xuong["to_in"].id,
                               to_id=xuong["to_cat"].id)


def test_tim_ma_lenh_va_phan_trang(db, admin, xuong):
    res = _xem(db, admin, xuong["x"].id, tim=xuong["b"].ma)
    assert [l["nguon_id"] for l in res["lenh"]] == [xuong["b"].id]
    assert {t["don_vi"]: t["tot"] for t in res["tong"]} == {"tờ": 200}

    p1 = _xem(db, admin, xuong["x"].id, co_trang=1)
    p2 = _xem(db, admin, xuong["x"].id, co_trang=1, trang=2)
    assert p1["tong_lenh"] == p2["tong_lenh"] == 2
    # Lệnh có mẻ mới nhất lên đầu; tổng vẫn tính trên cả bộ lọc.
    assert [l["nguon_id"] for l in p1["lenh"]] == [xuong["a"].id]
    assert [l["nguon_id"] for l in p2["lenh"]] == [xuong["b"].id]
    assert p1["tong"] == p2["tong"]


def test_ngoai_pham_vi_va_khoang_ngay_sai(db, admin, xuong):
    with pytest.raises(PermissionError):
        san_luong_to.san_luong(db, xuong["tho2"], team_id=xuong["to_cat"].id)
    with pytest.raises(ValueError):
        san_luong_to.san_luong(db, admin, team_id=xuong["x"].id,
                               tu=date(2026, 9, 10), den=date(2026, 9, 1))
