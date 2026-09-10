"""Bàn ĐIỂM KIỂM của tổ KCS — Giai đoạn → Công đoạn → checklist
(`docs/design-kcs-theo-cong-doan.md`, chốt 08/09/2026).

Soi tầng service `services/san_xuat/kcs.py::diem_kiem_kcs` + đường ghi `tao_kiem_dot_xuat(
loai="diem_kiem")`, không qua HTTP. Ba điều PHẢI đứng vững:

  · bộ lọc của bàn là CHECKLIST (`kcs_tieu_chi_json IS NOT NULL`), KHÔNG phải `la_kcs` — điểm kiểm
    nằm rải ở mọi công đoạn của mọi tổ, còn `la_kcs` chỉ nói thẻ việc thuộc tổ KCS;
  · phạm vi bàn là MỌI tổ người xem thấy được (tổ KCS đi kiểm việc của tổ KHÁC), không khoá theo
    một `team_id`;
  · kiểm "không đạt" ở giữa chuỗi KHÔNG chặn bước sau: không đẻ `san_xuat_batch`, không đụng
    `trang_thai` của việc, không mở cửa kho.

Tái dùng dàn cảnh của `test_san_xuat_kcs.py` (đơn → SX → phát hành vào một tổ khoán).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.models.role import SCOPE_ALL, SCOPE_OWN
from app.models.san_xuat import CV_HOAN_THANH, CV_PHAT_HANH
from app.models.san_xuat_kcs import KCS_LOAI_DIEM_KIEM, SanXuatKcsBatch
from app.models.san_xuat_san_luong import SanXuatBatch
from app.services.san_xuat import kcs

from tests.test_san_xuat_kcs import (  # noqa: F401
    _T0,
    _T1,
    _Authz,
    _anh,
    _cv_production,
    _to_kiem,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
)

_TC = [
    {"tieu_chi_id": 7, "ma": "IN-CHONG-MAU", "ten": "Chồng màu đúng", "huong_dan": None,
     "bat_buoc": True, "nguon": "danh_muc", "thu_tu": 1},
    {"tieu_chi_id": 8, "ma": "IN-LEM", "ten": "Không lem mực ở biên", "huong_dan": None,
     "bat_buoc": False, "nguon": "danh_muc", "thu_tu": 2},
]


def _diem_kiem(db, orders, lsx_svc, admin, customer, *, ma="TO-SX-DK", nhom="print"):
    """Một việc SẢN XUẤT THƯỜNG đang chạy, được gắn checklist ⇒ thành ĐIỂM KIỂM."""
    to, cv = _cv_production(db, orders, lsx_svc, admin, customer, ma=ma)
    cv.kcs_tieu_chi_json = list(_TC)
    cv.nhom_cong_doan = nhom
    cv.don_vi_ra = "cái"
    cv.don_vi_vao = "cái"
    db.commit()
    return to, cv


def _phang(ban: dict) -> list[dict]:
    return [cv for gd in ban["giai_doan"] for cv in gd["cong_viec"]]


# --- Mặt ĐỌC: bàn ba tầng -------------------------------------------------------------------
def test_ban_lay_viec_co_checklist_du_khong_phai_la_kcs(db, orders, lsx_svc, admin, customer):
    _to, cv = _diem_kiem(db, orders, lsx_svc, admin, customer)
    assert cv.la_kcs is False                              # việc SX thường, không thuộc tổ KCS

    ban = kcs.diem_kiem_kcs(db, admin, _Authz(SCOPE_ALL))
    ds = _phang(ban)
    assert [c["id"] for c in ds] == [cv.id]
    assert ban["giai_doan"][0]["nhom"] == "print"
    assert [t["ma"] for t in ds[0]["checklist"]] == ["IN-CHONG-MAU", "IN-LEM"]
    assert ds[0]["to_id"] == cv.department_id and ds[0]["to_ten"]
    assert ds[0]["batch"] == [] and ds[0]["tong_dat"] == 0 and ds[0]["tong_loi"] == 0


def test_ban_bo_qua_viec_khong_co_checklist(db, orders, lsx_svc, admin, customer):
    """`kcs_tieu_chi_json` NULL = bước không phải điểm kiểm — đây là lý do snapshot phải trả NULL
    chứ đừng ghi `[]` cho công đoạn không có tiêu chí nào."""
    _to, cv = _cv_production(db, orders, lsx_svc, admin, customer, ma="TO-SX-KHONG-TC")
    assert cv.kcs_tieu_chi_json is None
    assert _phang(kcs.diem_kiem_kcs(db, admin, _Authz(SCOPE_ALL))) == []


def test_ban_bo_qua_viec_chua_khoi_dong(db, orders, lsx_svc, admin, customer):
    """Bước mới phát hành chưa ai bấm Bắt đầu thì cổng ghi cũng từ chối — bày lên bàn chỉ để bấm
    vào rồi ăn lỗi."""
    _to, cv = _diem_kiem(db, orders, lsx_svc, admin, customer)
    cv.trang_thai = CV_PHAT_HANH
    db.commit()
    assert _phang(kcs.diem_kiem_kcs(db, admin, _Authz(SCOPE_ALL))) == []


def test_ban_gom_theo_giai_doan_dung_thu_tu(db, orders, lsx_svc, admin, customer):
    """Thứ tự giai đoạn cố định theo danh mục (`prepress → print → finishing → other`), bước không
    tra được giai đoạn xuống CUỐI dưới khoá "" — không bịa nó thành "Dịch vụ khác"."""
    _t1, _cv1 = _diem_kiem(db, orders, lsx_svc, admin, customer, ma="TO-A", nhom="finishing")
    _t2, _cv2 = _diem_kiem(db, orders, lsx_svc, admin, customer, ma="TO-B", nhom="prepress")
    _t3, cv3 = _diem_kiem(db, orders, lsx_svc, admin, customer, ma="TO-C", nhom="print")
    cv3_khac = cv3
    _t4, cv4 = _diem_kiem(db, orders, lsx_svc, admin, customer, ma="TO-D", nhom=None)
    assert cv3_khac.nhom_cong_doan == "print" and cv4.nhom_cong_doan is None

    ban = kcs.diem_kiem_kcs(db, admin, _Authz(SCOPE_ALL))
    assert [gd["nhom"] for gd in ban["giai_doan"]] == ["prepress", "print", "finishing", ""]
    assert all(gd["cong_viec"] for gd in ban["giai_doan"])   # không bày nhóm rỗng


def test_ban_theo_pham_vi_doc_cua_nguoi_xem(db, orders, lsx_svc, admin, customer):
    """Scope `own` ở một tổ khác ⇒ bàn rỗng (không phải 403): bàn là danh sách, không phải một
    tài nguyên bị từ chối."""
    _to, _cv = _diem_kiem(db, orders, lsx_svc, admin, customer)
    to_kiem, tv = _to_kiem(db)
    nguoi = SimpleNamespace(id=tv.id, department_id=to_kiem.id, role_id=1)
    assert _phang(kcs.diem_kiem_kcs(db, nguoi, _Authz(SCOPE_OWN))) == []


# --- Mặt GHI: loại `diem_kiem` --------------------------------------------------------------
def test_ghi_diem_kiem_doi_cong_doan_co_tieu_chi(db, orders, lsx_svc, admin, customer):
    _to, cv = _cv_production(db, orders, lsx_svc, admin, customer, ma="TO-SX-TRONG")
    to_kiem, tv = _to_kiem(db)
    with pytest.raises(ValueError):                        # chưa có tiêu chí nào ⇒ không phải điểm kiểm
        kcs.tao_kiem_dot_xuat(
            db, user=tv, cong_viec_id=cv.id, kcs_department_id=to_kiem.id,
            bat_dau=_T0, ket_thuc=_T1, so_luong_nhan=10, so_luong_dat=10,
            don_vi="cái", loai=KCS_LOAI_DIEM_KIEM,
        )


def test_ghi_diem_kiem_khong_de_san_luong_khong_doi_trang_thai(db, orders, lsx_svc, admin, customer):
    """"Không chặn bước sau" đúng theo CẤU TRÚC: điểm kiểm không đẻ batch sản lượng, không sửa
    `trang_thai` của việc, nên không có đường nào để một lượt "không đạt" khoá dây chuyền."""
    _to, cv = _diem_kiem(db, orders, lsx_svc, admin, customer)
    to_kiem, tv = _to_kiem(db)
    truoc_batch = db.query(SanXuatBatch).count()
    truoc_tt = cv.trang_thai

    res = kcs.tao_kiem_dot_xuat(
        db, user=tv, cong_viec_id=cv.id, kcs_department_id=to_kiem.id,
        bat_dau=_T0, ket_thuc=_T1, so_luong_nhan=10, so_luong_dat=4, so_luong_khong_dat=6,
        don_vi="cái", loai=KCS_LOAI_DIEM_KIEM,
        checklist_ket_qua=[{"thu_tu": 1, "dat": False, "ghi_chu": "Lệch 0,5mm"}],
        loi_mo_ta="Chồng màu lệch", anh=_anh(),
    )
    kb = db.get(SanXuatKcsBatch, res["kcs_batch_id"])
    assert kb.loai == KCS_LOAI_DIEM_KIEM and kb.kcs_department_id == to_kiem.id
    assert res["batch_id"] is None
    assert db.query(SanXuatBatch).count() == truoc_batch
    assert cv.trang_thai == truoc_tt


def test_ghi_diem_kiem_doi_tieu_chi_bat_buoc(db, orders, lsx_svc, admin, customer):
    """`_validate_checklist_bat_buoc` áp cho MỌI điểm kiểm, không riêng bước cuối."""
    _to, cv = _diem_kiem(db, orders, lsx_svc, admin, customer)
    to_kiem, tv = _to_kiem(db)
    with pytest.raises(ValueError):
        kcs.tao_kiem_dot_xuat(
            db, user=tv, cong_viec_id=cv.id, kcs_department_id=to_kiem.id,
            bat_dau=_T0, ket_thuc=_T1, so_luong_nhan=10, so_luong_dat=10,
            don_vi="cái", loai=KCS_LOAI_DIEM_KIEM,
        )


def test_ghi_diem_kiem_cho_ca_viec_da_hoan_thanh(db, orders, lsx_svc, admin, customer):
    """KHÁC kiểm đột xuất (chỉ đang chạy/tạm dừng): điểm kiểm còn ghi được sau khi bước đã xong —
    tổ KCS đi kiểm thường tới sau khi tổ SX chạy xong công đoạn."""
    _to, cv = _diem_kiem(db, orders, lsx_svc, admin, customer)
    cv.trang_thai = CV_HOAN_THANH
    db.commit()
    to_kiem, tv = _to_kiem(db)

    res = kcs.tao_kiem_dot_xuat(
        db, user=tv, cong_viec_id=cv.id, kcs_department_id=to_kiem.id,
        bat_dau=_T0, ket_thuc=_T1, so_luong_nhan=10, so_luong_dat=10,
        don_vi="cái", loai=KCS_LOAI_DIEM_KIEM,
        checklist_ket_qua=[{"thu_tu": 1, "dat": True, "ghi_chu": None}],
    )
    assert db.get(SanXuatKcsBatch, res["kcs_batch_id"]).loai == KCS_LOAI_DIEM_KIEM


def test_ban_tra_kem_ket_qua_da_ghi(db, orders, lsx_svc, admin, customer):
    """Bàn gói luôn kết quả đã ghi vào từng dòng — FE không phải gọi `/work-items/{id}/kcs` theo
    từng dòng (N+1) chỉ để biết công đoạn đã kiểm chưa."""
    _to, cv = _diem_kiem(db, orders, lsx_svc, admin, customer)
    to_kiem, tv = _to_kiem(db)
    kcs.tao_kiem_dot_xuat(
        db, user=tv, cong_viec_id=cv.id, kcs_department_id=to_kiem.id,
        bat_dau=_T0, ket_thuc=_T1, so_luong_nhan=10, so_luong_dat=7, so_luong_khong_dat=3,
        don_vi="cái", loai=KCS_LOAI_DIEM_KIEM,
        checklist_ket_qua=[{"thu_tu": 1, "dat": True, "ghi_chu": None}],
        loi_mo_ta="Lem biên", anh=_anh(),
    )

    dong = _phang(kcs.diem_kiem_kcs(db, admin, _Authz(SCOPE_ALL)))[0]
    assert dong["tong_dat"] == 7 and dong["tong_loi"] == 3
    assert len(dong["batch"]) == 1
    b0 = dong["batch"][0]
    assert b0["loai"] == KCS_LOAI_DIEM_KIEM
    # Không gửi kho được ⇒ trạng thái "không áp dụng", không phải "chưa gửi".
    assert b0["trang_thai_gui_kho"] == "khong_ap_dung"
    assert len(b0["loi"]) == 1 and len(b0["loi"][0]["anh"]) == 1
