"""Đầu vào theo routing lệnh (19/09/2026, `services/san_xuat/dau_vao.py`).

  · chặng trước là chiều ngược đúng của chặng sau (cạnh thắng thứ tự bảng);
  · bắt đầu phải đã NHẬN (bàn giao đã xác nhận) từ công đoạn trước;
  · Σ số làm được các mẻ ≤ số đã nhận × hệ số quy đổi — cùng đơn vị hệ số 1, tờ → con nhân hệ số;
    nguồn giao khác đơn vị vào (bản kẽm vào bước in tờ) thì không làm trần;
  · điều chỉnh giảm bàn giao không được kéo trần xuống dưới số đã ghi;
  · drawer bày công đoạn trước + trần bằng đúng các hàm đó.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.models.lsx import LsxCongDoanPhuThuoc
from app.models.san_xuat import CV_DANG_CHAY, CV_PHAT_HANH
from app.models.san_xuat_san_luong import BG_DE_XUAT, BG_XAC_NHAN
from app.repositories.rbac_repo import RoleRepository
from app.repositories.san_xuat_san_luong_repo import SanXuatSanLuongRepository
from app.services.rbac_service import AuthorizationService
from app.services.san_xuat import ban_giao, board, thuc_thi

from tests.test_san_xuat_ban_giao import (  # noqa: F401
    _T0,
    _batch,
    _buoc,
    _hai_cv,
    _to_dich,
    _viec,
)
from tests.test_san_xuat_thuc_thi import (  # noqa: F401
    _emp,
    _phat_hanh_vao_to,
    _to_khoan,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
)


def _cung_lenh(db, orders, lsx_svc, admin, customer, *, he_so=1.0, dv_ra="tờ", ma="TO-DV"):
    """cv1 → cv2 cùng tổ, cùng lệnh (bàn giao tự xác nhận). cv2 nhận "tờ", ra `dv_ra`."""
    to, cv1, cv2, lsx = _hai_cv(db, orders, lsx_svc, admin, customer, ma=ma)
    cv1.lsx_id = cv2.lsx_id = lsx
    cv2.don_vi_ra = dv_ra
    cv2.he_so_quy_doi = he_so
    db.commit()
    return to, cv1, cv2


def _giao(db, admin, cv1, cv2, tot, t0=_T0):
    b = _batch(db, admin, cv1, tot=tot, t0=t0)
    return ban_giao.de_xuat(db, user=admin, nguon_cong_viec_id=cv1.id,
                            dich_cong_viec_id=cv2.id, batch_ids=[b])


def test_chang_truoc_la_chieu_nguoc_chang_sau(db, orders, lsx_svc, admin, customer):
    to = _to_khoan(db, admin, ma="TO-CT")
    a, _b, goi = _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)
    x, y, z = (_buoc(db, a.id, 900 + i, t) for i, t in enumerate(("X", "Y", "Z")))
    cvx, cvy = _viec(db, goi.id, a.id, x), _viec(db, goi.id, a.id, y)
    z1, z2 = _viec(db, goi.id, a.id, z, 1, 2), _viec(db, goi.id, a.id, z, 2, 2)
    db.commit()
    repo = SanXuatSanLuongRepository(db)

    assert [c.id for c in repo.cong_viec_chang_truoc(cvy)] == [cvx.id]          # thu_tu
    assert [c.id for c in repo.cong_viec_chang_truoc(z1)] == [cvy.id]
    assert [c.id for c in repo.cong_viec_chang_truoc(z2)] == [cvy.id]           # mọi lần chạy

    # X khai cạnh X → Z: chặng sau của X chỉ còn Z, nên X thôi là chặng trước của Y.
    db.add(LsxCongDoanPhuThuoc(buoc_truoc_id=x.id, buoc_sau_id=z.id))
    db.commit()
    assert repo.cong_viec_chang_truoc(cvy) == []
    assert {c.id for c in repo.cong_viec_chang_truoc(z1)} == {cvx.id, cvy.id}
    for truoc in (cvx, cvy):                                                     # đối xứng
        assert z1.id in {c.id for c in repo.cong_viec_chang_sau(truoc)}


def test_bat_dau_phai_da_nhan_tu_cong_doan_truoc(db, orders, lsx_svc, admin, customer):
    to, cv1, cv2 = _cung_lenh(db, orders, lsx_svc, admin, customer, ma="TO-BD")
    cv2.trang_thai = CV_PHAT_HANH
    db.commit()
    thuc_thi.phan_cong(db, user=admin, cong_viec_id=cv2.id, employee_id=_emp(db, to, "NV-DV-1").id)

    with pytest.raises(ValueError, match=rf"^Chưa nhận hàng từ công đoạn trước \({cv1.ten_cong_doan}\)"):
        thuc_thi.bat_dau(db, user=admin, cong_viec_id=cv2.id)

    _giao(db, admin, cv1, cv2, 100)
    assert thuc_thi.bat_dau(db, user=admin, cong_viec_id=cv2.id)["trang_thai"] == CV_DANG_CHAY


def test_de_xuat_chua_xac_nhan_chua_tinh_la_da_nhan(db, orders, lsx_svc, admin, customer):
    to, cv1, cv2 = _cung_lenh(db, orders, lsx_svc, admin, customer, ma="TO-DX")
    to_b, ub = _to_dich(db, ma="TO-DX-DICH")
    cv2.department_id = to_b.id                          # khác tổ ⇒ chờ bên nhận xác nhận
    db.commit()
    r = _giao(db, admin, cv1, cv2, 100)
    assert r["trang_thai_ban_giao"] == BG_DE_XUAT
    with pytest.raises(ValueError, match="chờ công đoạn trước giao thêm"):
        _batch(db, ub, cv2, tot=10, t0=_T0 + timedelta(hours=2))

    ban_giao.xac_nhan(db, user=ub, ban_giao_id=r["ban_giao_id"])
    _batch(db, ub, cv2, tot=100, t0=_T0 + timedelta(hours=2))


def test_cung_don_vi_ghi_toi_da_bang_so_da_nhan(db, orders, lsx_svc, admin, customer):
    to, cv1, cv2 = _cung_lenh(db, orders, lsx_svc, admin, customer, ma="TO-TR")
    with pytest.raises(ValueError, match="chờ công đoạn trước giao thêm"):      # chưa nhận gì
        _batch(db, admin, cv2, tot=10, t0=_T0 + timedelta(hours=2))

    assert _giao(db, admin, cv1, cv2, 100)["trang_thai_ban_giao"] == BG_XAC_NHAN
    _batch(db, admin, cv2, tot=60, t0=_T0 + timedelta(hours=2))
    with pytest.raises(ValueError) as loi:
        _batch(db, admin, cv2, tot=50, t0=_T0 + timedelta(hours=3))
    assert str(loi.value) == (
        f"Vượt số nhận từ công đoạn trước: đã nhận từ {cv1.ten_cong_doan} 100 tờ, "
        f"đã ghi 60 tờ — mẻ này ghi tối đa 40 tờ."
    )
    _batch(db, admin, cv2, tot=40, t0=_T0 + timedelta(hours=3))                  # chạm trần: được


def test_doi_don_vi_nhan_he_so(db, orders, lsx_svc, admin, customer):
    """Bế 1 tờ → 2 con: nhận 1.000 tờ thì ghi tối đa 2.000 con."""
    to, cv1, cv2 = _cung_lenh(db, orders, lsx_svc, admin, customer, he_so=2, dv_ra="con", ma="TO-HS")
    _giao(db, admin, cv1, cv2, 1000)
    _batch(db, admin, cv2, tot=1500, t0=_T0 + timedelta(hours=2))
    with pytest.raises(ValueError) as loi:
        _batch(db, admin, cv2, tot=600, t0=_T0 + timedelta(hours=3))
    assert str(loi.value) == (
        f"Vượt số nhận từ công đoạn trước: đã nhận từ {cv1.ten_cong_doan} 1.000 tờ × 2 = tối đa "
        f"2.000 con, đã ghi 1.500 con — mẻ này ghi tối đa 500 con."
    )
    _batch(db, admin, cv2, tot=500, t0=_T0 + timedelta(hours=3))


def test_he_so_khong_thi_khong_tran(db, orders, lsx_svc, admin, customer):
    """Hệ số 0 = số vào/ra gõ tay (Cắt tờ cuộn → tờ in), máy không suy được ⇒ không trần."""
    to, cv1, cv2 = _cung_lenh(db, orders, lsx_svc, admin, customer, he_so=0, ma="TO-H0")
    _giao(db, admin, cv1, cv2, 10)
    _batch(db, admin, cv2, tot=500, t0=_T0 + timedelta(hours=2))


def test_nguon_khac_don_vi_vao_thi_khong_tran(db, orders, lsx_svc, admin, customer):
    """Ghi kẽm đứng trước In: In nhận BẢN KẼM, lấy số bản kẽm làm trần số tờ in là vô nghĩa."""
    to, k1, k2 = _cung_lenh(db, orders, lsx_svc, admin, customer, ma="TO-KEM")
    k1.don_vi_ra = k1.don_vi_vao = "kem"
    db.commit()
    _giao(db, admin, k1, k2, 4)
    _batch(db, admin, k2, tot=5000, t0=_T0 + timedelta(hours=2))


def test_dieu_chinh_giam_khong_duoc_duoi_so_da_ghi(db, orders, lsx_svc, admin, customer):
    to, cv1, cv2 = _cung_lenh(db, orders, lsx_svc, admin, customer, ma="TO-DC")
    r = _giao(db, admin, cv1, cv2, 100)
    _batch(db, admin, cv2, tot=80, t0=_T0 + timedelta(hours=2))

    with pytest.raises(ValueError) as loi:
        ban_giao.dieu_chinh(db, user=admin, ban_giao_id=r["ban_giao_id"], so_luong_sau=70)
    assert str(loi.value) == (
        f"Không giảm xuống 70 được: {cv2.ten_cong_doan} đã ghi mẻ 80 tờ, "
        f"giảm thế thì số nhận chỉ đủ cho 70 tờ."
    )
    assert ban_giao.dieu_chinh(db, user=admin, ban_giao_id=r["ban_giao_id"],
                               so_luong_sau=80)["so_luong"] == 80


def test_drawer_bay_cong_doan_truoc_va_tran(db, orders, lsx_svc, admin, customer):
    from app.schemas.san_xuat import WorkItemChiTietOut

    to, cv1, cv2 = _cung_lenh(db, orders, lsx_svc, admin, customer, he_so=2, dv_ra="con", ma="TO-DR")
    cv1.so_luong_ra = 1200
    db.commit()
    az = AuthorizationService(RoleRepository(db))

    def ct():
        return WorkItemChiTietOut.model_validate(
            board.chi_tiet_cong_viec(db, admin, az, cong_viec_id=cv2.id)).model_dump()

    truoc = ct()
    assert truoc["thieu_dau_vao"] == [cv1.ten_cong_doan]
    assert truoc["tran_ghi"]["toi_da"] == 0

    _giao(db, admin, cv1, cv2, 1000)
    _batch(db, admin, cv1, tot=150, t0=_T0 + timedelta(hours=1, minutes=30))   # làm thêm, chưa giao
    _batch(db, admin, cv2, tot=300, t0=_T0 + timedelta(hours=2))
    sau = ct()
    assert sau["thieu_dau_vao"] == []
    [dong] = sau["cong_doan_truoc"]
    assert (dong["cong_viec_id"], dong["ke_hoach"], dong["don_vi"], dong["thuc_te"],
            dong["da_giao"], dong["da_xac_nhan"], dong["cho_xac_nhan"]) == (
        cv1.id, 1200, "tờ", 1150, 1000, 1000, 0)
    assert {k: sau["tran_ghi"][k] for k in ("toi_da", "da_nhan", "he_so", "da_ghi", "con_ghi_duoc")} == {
        "toi_da": 2000, "da_nhan": 1000, "he_so": 2, "da_ghi": 300, "con_ghi_duoc": 1700}
