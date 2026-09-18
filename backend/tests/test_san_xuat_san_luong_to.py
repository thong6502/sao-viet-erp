"""Tab SẢN LƯỢNG của Bàn tổ (spec 2026-09-14 §6) — `services/san_xuat/san_luong_to.py`.

Soi luật:
  · phạm vi theo dòng quyền tổ: thấy TRỌN → số mẻ + tầng người (đã chốt / tạm tính / hỗ trợ chéo);
    chỉ CỦA TÔI → không tầng người, số là phần ĐÃ CHỐT của mình (nháp không lộ);
  · ngày = ngày BẮT ĐẦU mẻ theo giờ xưởng; không cộng lẫn đơn vị;
  · lọc đơn vị (cây con), tìm mã lệnh, phân trang + tổng trên cả bộ lọc ở máy chủ.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.employee import Employee
from app.models.role import SCOPE_OWN
from app.models.san_xuat_phan_bo import PB_DA_CHOT, PB_NHAP, SanXuatPhanBo, SanXuatPhanBoDong
from app.models.san_xuat_san_luong import SanXuatBatch
from app.models.user import User
from app.services.gio_xuong import ve_utc_that
from app.services.san_xuat import san_luong_to
from tests.quyen_to_fixtures import cap_quyen_to
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


def _me(db, cv, bat_dau, *, tot, hong=0, don_vi="tờ") -> SanXuatBatch:
    b = SanXuatBatch(cong_viec_id=cv.id, bat_dau=bat_dau, ket_thuc=bat_dau + timedelta(hours=1),
                     tong=tot + hong, tot=tot, hong=hong, don_vi=don_vi)
    db.add(b)
    db.flush()
    return b


def _chia(db, b, cv, trang_thai, don_vi, *dong) -> SanXuatPhanBo:
    """`dong` = (employee, so_luong, department_id, la_ho_tro)."""
    pb = SanXuatPhanBo(batch_id=b.id, cong_viec_id=cv.id, ngay=b.bat_dau.date(),
                       ky_nam=b.bat_dau.year, ky_thang=b.bat_dau.month, trang_thai=trang_thai,
                       q_tra_luong=sum(x[1] for x in dong), don_vi_tra_luong=don_vi)
    db.add(pb)
    db.flush()
    for e, sl, dept_id, ho_tro in dong:
        db.add(SanXuatPhanBoDong(phan_bo_id=pb.id, employee_id=e.id, department_id=dept_id,
                                 la_ho_tro=ho_tro, ngay=pb.ngay, so_luong_tra_luong=sl))
    db.flush()
    return pb


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
      · A · Tổ in: 2 mẻ đơn vị tờ (một đã chốt, một nháp) + 1 mẻ đơn vị cái chưa chia;
      · B · Tổ cắt: 1 mẻ đã chốt, có thợ Tổ in đi hỗ trợ;
      · A · Tổ in: 1 mẻ tháng 8 (ngoài khoảng mặc định)."""
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

    m1 = _me(db, cv_a, _gio_xuong(2026, 9, 3), tot=90, hong=10)
    _chia(db, m1, cv_a, PB_DA_CHOT, "tờ", (tho_in, 60, to_in.id, False), (tho_in2, 30, to_in.id, False))
    m2 = _me(db, cv_a, _gio_xuong(2026, 9, 5), tot=50, hong=0)
    _chia(db, m2, cv_a, PB_NHAP, "tờ", (tho_in, 20, to_in.id, False), (tho_in2, 30, to_in.id, False))
    _me(db, cv_a, _gio_xuong(2026, 9, 6), tot=7, hong=1, don_vi="cái")
    m4 = _me(db, cv_b, _gio_xuong(2026, 9, 4), tot=200, hong=5)
    _chia(db, m4, cv_b, PB_DA_CHOT, "tờ", (tho_cat, 150, to_cat.id, False), (tho_in2, 50, to_in.id, True))
    _me(db, cv_a, _gio_xuong(2026, 8, 20), tot=999)

    cap_quyen_to(db, admin, x)
    cap_quyen_to(db, u_tho2, to_in, scope=SCOPE_OWN, viec=())
    db.commit()
    return {"x": x, "to_in": to_in, "to_cat": to_cat, "a": a, "b": b, "tho2": u_tho2,
            "tho_in": tho_in, "tho_in2": tho_in2, "tho_cat": tho_cat}


def _lenh(res, lsx):
    return next(l for l in res["lenh"] if l["nguon_loai"] == "lsx" and l["nguon_id"] == lsx.id)


def test_quan_doc_thay_tron_lenh_cong_doan_nguoi(db, admin, xuong):
    res = san_luong_to.san_luong(db, admin, team_id=xuong["x"].id,
                                 tu=date(2026, 9, 1), den=date(2026, 9, 30))

    assert res["tong_lenh"] == 2 and res["co_pham_vi_tron"]
    # Không cộng lẫn đơn vị: tờ và cái là hai dòng tổng riêng; mẻ tháng 8 nằm ngoài.
    tong = {t["don_vi"]: t for t in res["tong"]}
    assert tong["tờ"]["tot"] == 340 and tong["tờ"]["hong"] == 15 and tong["tờ"]["so_me"] == 3
    assert tong["cái"]["tot"] == 7 and tong["cái"]["so_me"] == 1

    la = _lenh(res, xuong["a"])
    assert {s["don_vi"]: s["tot"] for s in la["san_luong"]} == {"tờ": 140, "cái": 7}
    cd = la["cong_doan"][0]
    assert cd["to_id"] == xuong["to_in"].id and not cd["cua_toi"]
    assert cd["so_me"] == 3 and cd["chua_chia"] == 1
    nguoi = {n["employee_id"]: n for n in cd["nguoi"]}
    # Đã chốt tách riêng tạm tính (bản chia nháp).
    assert nguoi[xuong["tho_in"].id]["da_chot"] == 60 and nguoi[xuong["tho_in"].id]["tam_tinh"] == 20
    assert nguoi[xuong["tho_in2"].id]["da_chot"] == 30 and nguoi[xuong["tho_in2"].id]["tam_tinh"] == 30

    lb = _lenh(res, xuong["b"])
    cd_b = lb["cong_doan"][0]
    ho_tro = [n for n in cd_b["nguoi"] if n["la_ho_tro"]]
    assert [(n["employee_id"], n["da_chot"]) for n in ho_tro] == [(xuong["tho_in2"].id, 50)]
    assert "tien" not in str(res) and "don_gia" not in str(res)


def test_ngay_la_ngay_bat_dau_me_theo_gio_xuong(db, admin, xuong):
    """Mẻ 01:30 sáng 7/9 giờ xưởng là 6/9 theo UTC — vẫn phải rơi vào ngày 7/9."""
    cv = _cvs(db, xuong["to_in"])[0]
    _me(db, cv, _gio_xuong(2026, 9, 7, 1, 30), tot=11, don_vi="bộ")
    db.commit()

    ngay_7 = san_luong_to.san_luong(db, admin, team_id=xuong["x"].id,
                                    tu=date(2026, 9, 7), den=date(2026, 9, 7))
    ngay_6 = san_luong_to.san_luong(db, admin, team_id=xuong["x"].id,
                                    tu=date(2026, 9, 6), den=date(2026, 9, 6))
    assert [t["don_vi"] for t in ngay_7["tong"]] == ["bộ"]
    assert "bộ" not in [t["don_vi"] for t in ngay_6["tong"]]


def test_tho_cua_toi_chi_thay_phan_da_chot_cua_minh(db, xuong):
    tho2 = xuong["tho2"]
    res = san_luong_to.san_luong(db, tho2, team_id=xuong["to_in"].id,
                                 tu=date(2026, 9, 1), den=date(2026, 9, 30))

    assert not res["co_pham_vi_tron"] and res["co_pham_vi_rieng"]
    assert res["tong"] == []
    # 30 đã chốt ở Tổ in + 50 hỗ trợ Tổ cắt; 30 nháp không lộ.
    assert res["tong_cua_toi"] == [{"don_vi": "tờ", "da_chot": 80}]
    assert res["tong_lenh"] == 2
    for l in res["lenh"]:
        assert l["san_luong"] == []
        for cd in l["cong_doan"]:
            assert cd["cua_toi"] and cd["nguoi"] == [] and cd["san_luong"] == []
    assert _lenh(res, xuong["b"])["phan_cua_toi"] == [{"don_vi": "tờ", "da_chot": 50}]


def test_loc_don_vi_thu_ve_cay_con_va_chan_ngoai_vung(db, admin, xuong):
    res = san_luong_to.san_luong(db, admin, team_id=xuong["x"].id, to_id=xuong["to_cat"].id,
                                 tu=date(2026, 9, 1), den=date(2026, 9, 30))
    assert res["tong_lenh"] == 1 and _lenh(res, xuong["b"])
    assert {t["don_vi"]: t["tot"] for t in res["tong"]} == {"tờ": 200}
    assert [d["id"] for d in res["cac_to"]] == [xuong["x"].id, xuong["to_in"].id, xuong["to_cat"].id]

    with pytest.raises(PermissionError):
        san_luong_to.san_luong(db, xuong["tho2"], team_id=xuong["to_in"].id,
                               to_id=xuong["to_cat"].id)


def test_tim_ma_lenh_va_phan_trang(db, admin, xuong):
    res = san_luong_to.san_luong(db, admin, team_id=xuong["x"].id, tim=xuong["b"].ma,
                                 tu=date(2026, 9, 1), den=date(2026, 9, 30))
    assert [l["nguon_id"] for l in res["lenh"]] == [xuong["b"].id]
    assert {t["don_vi"]: t["tot"] for t in res["tong"]} == {"tờ": 200}

    p1 = san_luong_to.san_luong(db, admin, team_id=xuong["x"].id, co_trang=1,
                                tu=date(2026, 9, 1), den=date(2026, 9, 30))
    p2 = san_luong_to.san_luong(db, admin, team_id=xuong["x"].id, co_trang=1, trang=2,
                                tu=date(2026, 9, 1), den=date(2026, 9, 30))
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
