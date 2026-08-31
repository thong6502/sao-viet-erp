"""Thực hiện sản xuất — Giai đoạn 5 (đóng nhóm §16 + đóng thiếu §13.3).

Soi tầng service `services/san_xuat/dong_nhom.py` (nơi chứa LUẬT), không qua HTTP:
  · cổng đóng ĐỦ tính-lúc-đọc: mọi việc xong · không lệch bàn giao · KCS cuối phân loại hết số
    NHẬN (KHÔNG so mục tiêu đơn) · phân bổ đã chốt · hết lỗi KCS chờ · hết BTP chờ kho;
  · `tu_dong_dong_neu_du` chỉ đóng khi HỘI ĐỦ, idempotent (đã đóng ⇒ no-op);
  · đóng THIẾU: chỉ trưởng KCS, bắt buộc lý do nhóm `dong_thieu`, vẫn phải sạch điều kiện toàn vẹn
    (mọi điều kiện TRỪ "mọi việc xong"); version chống bấm trùng.

Tái dùng dàn cảnh KCS (đơn → SX → phát hành → batch KCS) để có nhóm thật + tổ trưởng = admin.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.models.san_xuat import (
    CV_HOAN_THANH,
    NHOM_DONG_DU,
    NHOM_DONG_THIEU,
)
from app.models.san_xuat_kcs import SanXuatKcsBatch, SanXuatKcsLoi, TN_CHO
from app.models.san_xuat_kho import PL_NHAP_BTP
from app.models.san_xuat_ly_do import (
    NHOM_DONG_THIEU as LY_DO_DONG_THIEU,
    SanXuatLyDo,
)
from app.repositories.san_xuat_repo import SanXuatRepository
from app.schemas.san_xuat import DongNhomDieuKienOut, DongNhomKetQuaOut
from app.services.san_xuat import dong_nhom, kcs, kho

# Dàn cảnh + fixtures luồng thật từ test KCS (kéo cả cây fixture xếp lịch).
from tests.test_san_xuat_kcs import (  # noqa: F401
    _batch,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
)

_T0 = datetime(2026, 8, 20, 8, 0, tzinfo=timezone.utc)
_T1 = datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc)


def _cvs_nhom(db, nhom_id):
    return SanXuatRepository(db).cong_viec_hien_tai_cua_nhom(nhom_id)


def _hoan_thanh_het(db, nhom_id):
    for cv in _cvs_nhom(db, nhom_id):
        cv.trang_thai = CV_HOAN_THANH
    db.commit()


def _ly_do_dt(db, ma="DT-1", ten="Khách chốt nhận thiếu"):
    ld = SanXuatLyDo(ma=ma, nhom=LY_DO_DONG_THIEU, ten=ten)
    db.add(ld)
    db.flush()
    return ld


# --- Cổng đóng ĐỦ (§16) ---------------------------------------------------------------------
def test_du_dieu_kien_thi_tu_dong_dong_du(db, orders, lsx_svc, admin, customer):
    _to, cv, _res = _batch(db, orders, lsx_svc, admin, customer)
    assert cv.nhom_id is not None
    _hoan_thanh_het(db, cv.nhom_id)

    ket = dong_nhom.tu_dong_dong_neu_du(db, nhom_id=cv.nhom_id, actor=admin, su_kien="test")
    assert ket is not None and ket["kieu"] == "du"
    assert ket["trang_thai"] == NHOM_DONG_DU
    assert SanXuatRepository(db).nhom(cv.nhom_id).trang_thai == NHOM_DONG_DU
    # response_model không được nuốt field: dict service phải khớp schema ra FE.
    assert DongNhomKetQuaOut.model_validate(ket).kieu == "du"


def test_con_viec_chua_xong_thi_khong_dong(db, orders, lsx_svc, admin, customer):
    _to, cv, _res = _batch(db, orders, lsx_svc, admin, customer)
    cvs = _cvs_nhom(db, cv.nhom_id)
    for c in cvs[1:]:
        c.trang_thai = CV_HOAN_THANH       # để sót ĐÚNG một việc chưa xong
    db.commit()

    assert dong_nhom.tu_dong_dong_neu_du(db, nhom_id=cv.nhom_id) is None
    dk = dong_nhom.dieu_kien_dong_nhom(db, cv.nhom_id)
    assert dk["du_dong_du"] is False
    hoan_thanh = next(d for d in dk["dieu_kien"] if d["ma"] == "moi_viec_xong")
    assert hoan_thanh["dat"] is False and "chưa xong" in hoan_thanh["chi_tiet"]


def test_loi_kcs_cho_chan_dong_du(db, orders, lsx_svc, admin, customer):
    _to, cv, res = _batch(db, orders, lsx_svc, admin, customer)
    _hoan_thanh_het(db, cv.nhom_id)
    db.add(SanXuatKcsLoi(kcs_batch_id=res["kcs_batch_id"], trang_thai=TN_CHO, so_luong=3))
    db.commit()

    assert dong_nhom.tu_dong_dong_neu_du(db, nhom_id=cv.nhom_id) is None
    dk = dong_nhom.dieu_kien_dong_nhom(db, cv.nhom_id)
    assert dk["du_dong_du"] is False
    loi = next(d for d in dk["dieu_kien"] if d["ma"] == "het_loi_kcs_cho")
    assert loi["dat"] is False


def test_loi_ghi_qua_kcs_kiem_nhiem_khong_chan_dong_du(db, orders, lsx_svc, admin, customer):
    """Task 11.5: lỗi MỚI ghi qua `kcs.ghi_loi()` (kiêm nhiệm, mg 0250) có trang_thai="recorded",
    KHÔNG còn là `pending` nên KHÔNG chặn đóng nhóm — khác lỗi kiểu CŨ ở test bên trên. Đây là test
    tái hiện đúng bug đã báo cáo: trước bản vá, dòng `assert loi["dat"] is True` bên dưới FAIL vì
    `ghi_loi()` từng hardcode `trang_thai=TN_CHO`."""
    _to, cv, res = _batch(db, orders, lsx_svc, admin, customer)
    ld = SanXuatLyDo(ma="LOI-FIX-115", nhom="loi", ten="Lem mực")
    db.add(ld)
    db.flush()
    kcs.ghi_loi(
        db, user=admin, kcs_batch_id=res["kcs_batch_id"], nhom_loi_id=ld.id,
        so_luong=3, anh=[{"file_name": "loi.jpg",
                          "file_url": "/api/files/san-xuat/kcs-loi/1/x.jpg",
                          "file_type": "image/jpeg"}],
    )
    _hoan_thanh_het(db, cv.nhom_id)

    dk = dong_nhom.dieu_kien_dong_nhom(db, cv.nhom_id)
    loi = next(d for d in dk["dieu_kien"] if d["ma"] == "het_loi_kcs_cho")
    assert loi["dat"] is True                              # KHÔNG còn bị chặn bởi lỗi mới
    assert dong_nhom.tu_dong_dong_neu_du(db, nhom_id=cv.nhom_id) is not None


def test_btp_cho_kho_chan_dong_du(db, orders, lsx_svc, admin, customer):
    _to, cv, _res = _batch(db, orders, lsx_svc, admin, customer)
    _hoan_thanh_het(db, cv.nhom_id)
    kho.phan_loai_btp_du(
        db, user=admin, cong_viec_id=cv.id, so_luong=5, phan_loai=PL_NHAP_BTP
    )

    assert dong_nhom.tu_dong_dong_neu_du(db, nhom_id=cv.nhom_id) is None
    dk = dong_nhom.dieu_kien_dong_nhom(db, cv.nhom_id)
    btp = next(d for d in dk["dieu_kien"] if d["ma"] == "het_btp_cho_kho")
    assert btp["dat"] is False


def test_kcs_cuoi_batch_do_dang_chan_dong_du(db, orders, lsx_svc, admin, customer):
    """Điều kiện 3 đo classified/received: batch dở (phân loại < nhận) ⇒ chưa đủ."""
    _to, cv, _res = _batch(db, orders, lsx_svc, admin, customer)
    cv.la_kcs_cuoi = True
    db.add(
        SanXuatKcsBatch(
            cong_viec_id=cv.id, nhom_id=cv.nhom_id, bat_dau=_T0, ket_thuc=_T1,
            so_luong_nhan=10, so_luong_dat=3, so_luong_khong_dat=2, don_vi="cái",
        )
    )
    _hoan_thanh_het(db, cv.nhom_id)

    dk = dong_nhom.dieu_kien_dong_nhom(db, cv.nhom_id)
    kcs = next(d for d in dk["dieu_kien"] if d["ma"] == "kcs_cuoi_phan_loai_du")
    # _batch đã đẻ batch đủ (100/100) trên cv; batch dở của test thêm 5/10 ⇒ tổng 105/110 < 1.
    assert kcs["dat"] is False and "105/110" in kcs["chi_tiet"]
    assert dong_nhom.tu_dong_dong_neu_du(db, nhom_id=cv.nhom_id) is None


def test_dong_du_idempotent(db, orders, lsx_svc, admin, customer):
    _to, cv, _res = _batch(db, orders, lsx_svc, admin, customer)
    _hoan_thanh_het(db, cv.nhom_id)
    assert dong_nhom.tu_dong_dong_neu_du(db, nhom_id=cv.nhom_id) is not None
    # Đã đóng ⇒ gọi lại không đổi trạng thái, không bump version.
    v = SanXuatRepository(db).nhom(cv.nhom_id).version
    assert dong_nhom.tu_dong_dong_neu_du(db, nhom_id=cv.nhom_id) is None
    assert SanXuatRepository(db).nhom(cv.nhom_id).version == v


# --- Đóng THIẾU (§13.3) ---------------------------------------------------------------------
def test_dong_thieu_khi_con_do_nhung_toan_ven_sach(db, orders, lsx_svc, admin, customer):
    _to, cv, _res = _batch(db, orders, lsx_svc, admin, customer)
    # KHÔNG hoàn thành hết (còn dở) nhưng các điều kiện toàn vẹn khác đều sạch.
    ld = _ly_do_dt(db)

    ket = dong_nhom.dong_thieu(db, user=admin, nhom_id=cv.nhom_id, ly_do_id=ld.id)
    assert ket["kieu"] == "thieu" and ket["trang_thai"] == NHOM_DONG_THIEU
    assert ket["ly_do_id"] == ld.id
    assert SanXuatRepository(db).nhom(cv.nhom_id).trang_thai == NHOM_DONG_THIEU
    assert DongNhomKetQuaOut.model_validate(ket).ly_do_id == ld.id


def test_dong_thieu_van_chan_khi_con_loi_kcs(db, orders, lsx_svc, admin, customer):
    _to, cv, res = _batch(db, orders, lsx_svc, admin, customer)
    db.add(SanXuatKcsLoi(kcs_batch_id=res["kcs_batch_id"], trang_thai=TN_CHO, so_luong=1))
    ld = _ly_do_dt(db)
    db.commit()

    with pytest.raises(ValueError, match="đóng thiếu"):
        dong_nhom.dong_thieu(db, user=admin, nhom_id=cv.nhom_id, ly_do_id=ld.id)


def test_dong_thieu_ly_do_sai_nhom_bi_chan(db, orders, lsx_svc, admin, customer):
    _to, cv, _res = _batch(db, orders, lsx_svc, admin, customer)
    sai = SanXuatLyDo(ma="TD-X", nhom="tam_dung", ten="Chờ mực")
    db.add(sai)
    db.flush()
    with pytest.raises(ValueError, match="Lý do"):
        dong_nhom.dong_thieu(db, user=admin, nhom_id=cv.nhom_id, ly_do_id=sai.id)


def test_dong_thieu_gate_chi_truong_kcs(db, orders, lsx_svc, admin, customer):
    _to, cv, _res = _batch(db, orders, lsx_svc, admin, customer)
    ld = _ly_do_dt(db)
    nguoi_la = SimpleNamespace(id=admin.id + 99_999)
    with pytest.raises(PermissionError):
        dong_nhom.dong_thieu(db, user=nguoi_la, nhom_id=cv.nhom_id, ly_do_id=ld.id)


def test_dong_thieu_version_lech_bi_chan(db, orders, lsx_svc, admin, customer):
    _to, cv, _res = _batch(db, orders, lsx_svc, admin, customer)
    ld = _ly_do_dt(db)
    v = SanXuatRepository(db).nhom(cv.nhom_id).version
    with pytest.raises(ValueError, match="cập nhật"):
        dong_nhom.dong_thieu(
            db, user=admin, nhom_id=cv.nhom_id, ly_do_id=ld.id, expected_version=v + 5
        )


def test_khong_the_dong_thieu_nhom_da_dong(db, orders, lsx_svc, admin, customer):
    _to, cv, _res = _batch(db, orders, lsx_svc, admin, customer)
    _hoan_thanh_het(db, cv.nhom_id)
    dong_nhom.tu_dong_dong_neu_du(db, nhom_id=cv.nhom_id, actor=admin)
    ld = _ly_do_dt(db)
    with pytest.raises(ValueError, match="đã đóng"):
        dong_nhom.dong_thieu(db, user=admin, nhom_id=cv.nhom_id, ly_do_id=ld.id)


def test_dieu_kien_shape_va_du_dong_thieu(db, orders, lsx_svc, admin, customer):
    _to, cv, _res = _batch(db, orders, lsx_svc, admin, customer)
    dk = dong_nhom.dieu_kien_dong_nhom(db, cv.nhom_id)
    assert set(dk) == {
        "nhom_id", "order_id", "trang_thai", "version",
        "du_dong_du", "du_dong_thieu", "dieu_kien",
    }
    mas = {d["ma"] for d in dk["dieu_kien"]}
    assert mas == {
        "moi_viec_xong", "khong_lech_ban_giao", "kcs_cuoi_phan_loai_du",
        "phan_bo_da_chot", "het_loi_kcs_cho", "het_btp_cho_kho",
    }
    # Còn dở (chưa xong hết) nhưng sạch điều kiện toàn vẹn ⇒ chưa đóng đủ nhưng đủ đóng thiếu.
    assert dk["du_dong_du"] is False and dk["du_dong_thieu"] is True
    # response_model của GET /dieu-kien-dong phải nhận trọn dict (kể cả list điều kiện lồng).
    val = DongNhomDieuKienOut.model_validate(dk)
    assert len(val.dieu_kien) == 6 and val.du_dong_thieu is True
