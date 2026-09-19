"""Thực hiện sản xuất — Giai đoạn 5 (đóng nhóm §16 + đóng thiếu §13.3).

Soi tầng service `services/san_xuat/dong_nhom.py` (nơi chứa LUẬT), không qua HTTP:
  · cổng đóng ĐỦ tính-lúc-đọc: mọi việc xong · không lệch bàn giao · KCS đã kiểm hết công đoạn cuối
    (Σ đạt + lỗi ≥ Σ tốt) · KCS ĐẠT đủ mục tiêu (Σ đạt ≥ Σ `so_luong_ra` công đoạn cuối, 17/09/2026)
    · phân bổ đã chốt. Lỗi KCS tổ chưa bấm "Đã xem" KHÔNG chặn (KCS theo lệnh, mg 0306);
  · `tu_dong_dong_neu_du` chỉ đóng khi HỘI ĐỦ, idempotent (đã đóng ⇒ no-op);
  · đóng THIẾU: chỉ TRƯỞNG phòng ban `is_kcs` (`head_user_id`); thành viên tổ KCS hay người đủ quyền
    theo tổ đều bị chặn; vẫn phải sạch điều kiện toàn vẹn (mọi điều kiện TRỪ "mọi việc xong" và
    "đạt đủ mục tiêu");
    version chống bấm trùng.

Tái dùng dàn cảnh KCS (đơn → SX → phát hành → một lần kiểm ở công đoạn cuối) để có nhóm thật.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.models.san_xuat import (
    CV_HOAN_THANH,
    NHOM_DONG_DU,
    NHOM_DONG_THIEU,
    SanXuatCongViec,
)
from app.models.san_xuat_san_luong import SanXuatBatch
from app.repositories.san_xuat_repo import SanXuatRepository
from app.schemas.san_xuat import DongNhomDieuKienOut, DongNhomKetQuaOut
from app.services.san_xuat import dong_nhom, kcs

# Dàn cảnh + fixtures luồng thật từ test KCS (kéo cả cây fixture xếp lịch).
from tests.test_san_xuat_kcs import (  # noqa: F401
    _batch,
    _emp,
    _nguoi_o_to,
    _ghi_tot,
    _to_kiem,
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


def _muc_tieu(db, nhom_id, so):
    """Đặt mục tiêu (`so_luong_ra`) cho công đoạn cuối của nhóm — cổng đóng ĐỦ so số KCS đạt với nó."""
    for cv in _cvs_nhom(db, nhom_id):
        if cv.la_kcs_cuoi:
            cv.so_luong_ra = so
    db.commit()


def _hoan_thanh_het(db, nhom_id):
    for cv in _cvs_nhom(db, nhom_id):
        cv.trang_thai = CV_HOAN_THANH
    db.commit()


def _truong_kcs(db):
    return _to_kiem(db, ten="Tổ KCS Trưởng", ma="KCS-TRUONG", truong=True)[1]


def _dk(db, nhom_id, ma):
    return next(d for d in dong_nhom.dieu_kien_dong_nhom(db, nhom_id)["dieu_kien"] if d["ma"] == ma)


# --- Cổng đóng ĐỦ (§16) ---------------------------------------------------------------------
def test_du_dieu_kien_thi_tu_dong_dong_du(db, orders, lsx_svc, admin, customer):
    _to, cv, _res = _batch(db, orders, lsx_svc, admin, customer, cuoi=True)
    assert cv.nhom_id is not None
    _muc_tieu(db, cv.nhom_id, 90)                  # đạt 90 = mục tiêu
    _hoan_thanh_het(db, cv.nhom_id)

    ket = dong_nhom.tu_dong_dong_neu_du(db, nhom_id=cv.nhom_id, actor=admin, su_kien="test")
    assert ket is not None and ket["kieu"] == "du"
    assert ket["trang_thai"] == NHOM_DONG_DU
    assert SanXuatRepository(db).nhom(cv.nhom_id).trang_thai == NHOM_DONG_DU
    # response_model không được nuốt field: dict service phải khớp schema ra FE.
    assert DongNhomKetQuaOut.model_validate(ket).kieu == "du"


def test_con_viec_chua_xong_thi_khong_dong(db, orders, lsx_svc, admin, customer):
    _to, cv, _res = _batch(db, orders, lsx_svc, admin, customer, cuoi=True)
    cvs = _cvs_nhom(db, cv.nhom_id)
    for c in cvs[1:]:
        c.trang_thai = CV_HOAN_THANH       # để sót ĐÚNG một việc chưa xong
    db.commit()

    assert dong_nhom.tu_dong_dong_neu_du(db, nhom_id=cv.nhom_id) is None
    dk = dong_nhom.dieu_kien_dong_nhom(db, cv.nhom_id)
    assert dk["du_dong_du"] is False
    hoan_thanh = next(d for d in dk["dieu_kien"] if d["ma"] == "moi_viec_xong")
    assert hoan_thanh["dat"] is False and "chưa xong" in hoan_thanh["chi_tiet"]


def test_loi_kcs_chua_xem_khong_chan_dong_du(db, orders, lsx_svc, admin, customer):
    """Lỗi KCS chỉ là thông báo một chiều cho tổ — tổ chưa bấm "Đã xem" nhóm vẫn đóng đủ."""
    _to, cv, res = _batch(db, orders, lsx_svc, admin, customer, cuoi=True)
    assert res["loi_id"] and kcs.loi_cho_xem(db, [cv.department_id])
    _muc_tieu(db, cv.nhom_id, 90)
    _hoan_thanh_het(db, cv.nhom_id)
    assert dong_nhom.tu_dong_dong_neu_du(db, nhom_id=cv.nhom_id) is not None


def test_hut_muc_tieu_thi_khong_dong_du_nhung_dong_thieu_duoc(db, orders, lsx_svc, admin, customer):
    """Làm xong hết, KCS kiểm hết số tốt, nhưng đạt 90 trên mục tiêu 10.000: KHÔNG được tự đóng ĐỦ
    (trước 17/09/2026 nhóm này tự đóng đủ và báo Sale "đơn có thể giao"). Hụt mục tiêu không phải
    lỗi toàn vẹn ⇒ trưởng KCS đóng THIẾU được."""
    _to, cv, _res = _batch(db, orders, lsx_svc, admin, customer, cuoi=True)
    _muc_tieu(db, cv.nhom_id, 10000)
    _hoan_thanh_het(db, cv.nhom_id)

    assert dong_nhom.tu_dong_dong_neu_du(db, nhom_id=cv.nhom_id) is None
    dk = dong_nhom.dieu_kien_dong_nhom(db, cv.nhom_id)
    muc = next(d for d in dk["dieu_kien"] if d["ma"] == "dat_muc_tieu")
    assert muc["dat"] is False and muc["chi_tiet"] == "mới đạt 90/10.000"
    assert dk["du_dong_du"] is False and dk["du_dong_thieu"] is True
    assert (dk["muc_tieu"], dk["da_dat"], dk["con_thieu"]) == (10000.0, 90.0, 9910.0)

    ket = dong_nhom.dong_thieu(db, user=_truong_kcs(db), nhom_id=cv.nhom_id)
    assert ket["trang_thai"] == NHOM_DONG_THIEU


def test_muc_tieu_so_so_dat_khong_so_so_tot(db, orders, lsx_svc, admin, customer):
    """So với số KCS ĐẠT: tốt 100 = mục tiêu, nhưng KCS đạt 90 lỗi 10 ⇒ vẫn hụt 10."""
    _to, cv, _res = _batch(db, orders, lsx_svc, admin, customer, cuoi=True)   # tốt 100 · đạt 90
    _muc_tieu(db, cv.nhom_id, 100)
    _hoan_thanh_het(db, cv.nhom_id)
    assert _dk(db, cv.nhom_id, "kcs_cuoi_kiem_het")["dat"] is True
    assert _dk(db, cv.nhom_id, "dat_muc_tieu")["chi_tiet"] == "mới đạt 90/100"
    assert dong_nhom.tu_dong_dong_neu_du(db, nhom_id=cv.nhom_id) is None


def test_muc_tieu_cong_moi_cong_viec_cuoi(db, orders, lsx_svc, admin, customer):
    """Công đoạn cuối bị TÁCH lần chạy thì mọi phân đoạn đều mang `la_kcs_cuoi`: mục tiêu và số đạt
    là TỔNG qua các phân đoạn, không lấy riêng phân đoạn nào."""
    _to, cv, res = _batch(db, orders, lsx_svc, admin, customer, dat=90, khong_dat=0, cuoi=True)
    # Lần chạy 2/2 — đúng hình dạng `snapshot._dung_cong_viec` ghi ra khi tách: cùng gói/lệnh/bước,
    # chỉ khác cặp số phân đoạn; `danh_dau_kcs_cuoi` đánh cờ cuối lên MỌI phân đoạn.
    cv.phan_doan_so, cv.phan_doan_tong, cv.so_luong_ra = 1, 2, 90
    cv2 = SanXuatCongViec(
        goi_id=cv.goi_id, lsx_id=cv.lsx_id, nhom_id=cv.nhom_id, lsx_cong_doan_id=cv.lsx_cong_doan_id,
        step_key=cv.step_key, phan_doan_so=2, phan_doan_tong=2, ten_cong_doan=cv.ten_cong_doan,
        department_id=cv.department_id, trang_thai=cv.trang_thai, la_kcs_cuoi=True,
        don_vi_vao=cv.don_vi_vao, don_vi_ra=cv.don_vi_ra, so_luong_ra=60,
    )
    db.add(cv2)
    db.commit()
    _hoan_thanh_het(db, cv.nhom_id)
    assert _dk(db, cv.nhom_id, "dat_muc_tieu")["chi_tiet"] == "mới đạt 90/150"

    _ghi_tot(db, cv2, 60)
    kcs.kiem_cong_doan(db, user=res["nguoi_kcs"], cong_viec_id=cv2.id, so_dat=60)
    assert _dk(db, cv.nhom_id, "dat_muc_tieu")["dat"] is True
    assert dong_nhom.tu_dong_dong_neu_du(db, nhom_id=cv.nhom_id) is not None


def test_khong_co_muc_tieu_thi_khong_tu_nhan_la_du(db, orders, lsx_svc, admin, customer):
    """Công đoạn cuối không có `so_luong_ra` thì không có gì để so ⇒ chưa đạt, chỉ đóng thiếu được."""
    _to, cv, _res = _batch(db, orders, lsx_svc, admin, customer, cuoi=True)
    _muc_tieu(db, cv.nhom_id, None)
    _hoan_thanh_het(db, cv.nhom_id)
    dk = _dk(db, cv.nhom_id, "dat_muc_tieu")
    assert dk["dat"] is False and dk["chi_tiet"] == "công đoạn cuối chưa có số mục tiêu"
    assert dong_nhom.tu_dong_dong_neu_du(db, nhom_id=cv.nhom_id) is None
    assert dong_nhom.dieu_kien_dong_nhom(db, cv.nhom_id)["du_dong_thieu"] is True


def test_so_chi_tiet_viet_kieu_viet():
    assert dong_nhom._so(1_000_000) == "1.000.000"
    assert dong_nhom._so(12.5) == "12,5"
    assert dong_nhom._so(90) == "90"


def test_cong_doan_cuoi_chua_kiem_het_chan_dong_du(db, orders, lsx_svc, admin, customer):
    """Điều kiện 3: Σ(đạt + lỗi) KCS đã kiểm ở công đoạn cuối phải phủ Σ tốt tổ đã ghi."""
    _to, cv, res = _batch(db, orders, lsx_svc, admin, customer, dat=60, khong_dat=10, cuoi=True,
                          tot=100)
    _muc_tieu(db, cv.nhom_id, 90)
    _hoan_thanh_het(db, cv.nhom_id)
    dk = _dk(db, cv.nhom_id, "kcs_cuoi_kiem_het")
    assert dk["dat"] is False and "70/100" in dk["chi_tiet"]
    assert dong_nhom.tu_dong_dong_neu_du(db, nhom_id=cv.nhom_id) is None

    kcs.kiem_cong_doan(db, user=res["nguoi_kcs"], cong_viec_id=cv.id, so_dat=30)
    assert _dk(db, cv.nhom_id, "kcs_cuoi_kiem_het")["dat"] is True
    assert dong_nhom.tu_dong_dong_neu_du(db, nhom_id=cv.nhom_id) is not None


def test_cong_doan_cuoi_chua_co_so_tot_hoac_khong_xac_dinh(db, orders, lsx_svc, admin, customer):
    _to, cv, _res = _batch(db, orders, lsx_svc, admin, customer, dat=5, khong_dat=0, cuoi=True)
    for c in _cvs_nhom(db, cv.nhom_id):
        c.la_kcs_cuoi = False
    db.commit()
    dk = _dk(db, cv.nhom_id, "kcs_cuoi_kiem_het")
    assert dk["dat"] is False and "chưa xác định công đoạn cuối" in dk["chi_tiet"]

    # Tổ xoá mẻ SAU khi KCS đã kiểm (hoặc dữ liệu cũ trước khi KCS phải có mẻ mới kiểm được).
    cv.la_kcs_cuoi = True
    db.query(SanXuatBatch).filter_by(cong_viec_id=cv.id).delete()
    db.commit()
    dk = _dk(db, cv.nhom_id, "kcs_cuoi_kiem_het")
    assert dk["dat"] is False and "chưa ghi số tốt" in dk["chi_tiet"]


def test_dong_du_idempotent(db, orders, lsx_svc, admin, customer):
    _to, cv, _res = _batch(db, orders, lsx_svc, admin, customer, cuoi=True)
    _muc_tieu(db, cv.nhom_id, 90)
    _hoan_thanh_het(db, cv.nhom_id)
    assert dong_nhom.tu_dong_dong_neu_du(db, nhom_id=cv.nhom_id) is not None
    # Đã đóng ⇒ gọi lại không đổi trạng thái, không bump version.
    v = SanXuatRepository(db).nhom(cv.nhom_id).version
    assert dong_nhom.tu_dong_dong_neu_du(db, nhom_id=cv.nhom_id) is None
    assert SanXuatRepository(db).nhom(cv.nhom_id).version == v


# --- Đóng THIẾU (§13.3) ---------------------------------------------------------------------
def test_dong_thieu_khi_con_do_nhung_toan_ven_sach(db, orders, lsx_svc, admin, customer):
    _to, cv, _res = _batch(db, orders, lsx_svc, admin, customer, cuoi=True)
    # KHÔNG hoàn thành hết (còn dở) nhưng các điều kiện toàn vẹn khác đều sạch.
    ket = dong_nhom.dong_thieu(db, user=_truong_kcs(db), nhom_id=cv.nhom_id)
    assert ket["kieu"] == "thieu" and ket["trang_thai"] == NHOM_DONG_THIEU
    assert SanXuatRepository(db).nhom(cv.nhom_id).trang_thai == NHOM_DONG_THIEU
    assert DongNhomKetQuaOut.model_validate(ket).trang_thai == NHOM_DONG_THIEU


def test_dong_thieu_van_chan_khi_cong_doan_cuoi_chua_kiem_het(db, orders, lsx_svc, admin, customer):
    _to, cv, _res = _batch(db, orders, lsx_svc, admin, customer, dat=50, khong_dat=0, cuoi=True,
                           tot=100)
    with pytest.raises(ValueError, match="đóng thiếu"):
        dong_nhom.dong_thieu(db, user=_truong_kcs(db), nhom_id=cv.nhom_id)


def test_dong_thieu_chi_truong_to_kcs(db, orders, lsx_svc, admin, customer):
    """Đóng thiếu là quyết định cấp nhóm của trưởng tổ KCS: người lạ, admin, người đủ mọi quyền
    theo tổ, thành viên tổ KCS (chính người vừa kiểm) đều bị chặn."""
    to, cv, res = _batch(db, orders, lsx_svc, admin, customer, cuoi=True)
    nguoi_la = SimpleNamespace(id=admin.id + 99_999)
    du_quyen_to = _nguoi_o_to(db, to, "dong_thieu_du_quyen_to",
                              viec=("run_order", "confirm_output", "warehouse"))
    for u in (nguoi_la, admin, du_quyen_to, res["nguoi_kcs"]):
        with pytest.raises(PermissionError):
            dong_nhom.dong_thieu(db, user=u, nhom_id=cv.nhom_id)
    assert SanXuatRepository(db).nhom(cv.nhom_id).trang_thai != NHOM_DONG_THIEU

    ket = dong_nhom.dong_thieu(db, user=_truong_kcs(db), nhom_id=cv.nhom_id)
    assert ket["trang_thai"] == NHOM_DONG_THIEU


def test_dong_thieu_version_lech_bi_chan(db, orders, lsx_svc, admin, customer):
    _to, cv, _res = _batch(db, orders, lsx_svc, admin, customer, cuoi=True)
    v = SanXuatRepository(db).nhom(cv.nhom_id).version
    with pytest.raises(ValueError, match="cập nhật"):
        dong_nhom.dong_thieu(
            db, user=_truong_kcs(db), nhom_id=cv.nhom_id, expected_version=v + 5
        )


def test_khong_the_dong_thieu_nhom_da_dong(db, orders, lsx_svc, admin, customer):
    _to, cv, _res = _batch(db, orders, lsx_svc, admin, customer, cuoi=True)
    _muc_tieu(db, cv.nhom_id, 90)
    _hoan_thanh_het(db, cv.nhom_id)
    dong_nhom.tu_dong_dong_neu_du(db, nhom_id=cv.nhom_id, actor=admin)
    with pytest.raises(ValueError, match="đã đóng"):
        dong_nhom.dong_thieu(db, user=_truong_kcs(db), nhom_id=cv.nhom_id)


def test_dieu_kien_shape_va_du_dong_thieu(db, orders, lsx_svc, admin, customer):
    _to, cv, _res = _batch(db, orders, lsx_svc, admin, customer, cuoi=True)
    dk = dong_nhom.dieu_kien_dong_nhom(db, cv.nhom_id)
    assert set(dk) == {
        "nhom_id", "order_id", "trang_thai", "version",
        "du_dong_du", "du_dong_thieu", "dieu_kien",
        # Số mục tiêu / đã đạt / còn thiếu của nhóm — cùng số mà điều kiện "dat_muc_tieu" so.
        "muc_tieu", "da_dat", "con_thieu",
    }
    mas = {d["ma"] for d in dk["dieu_kien"]}
    assert mas == {
        "moi_viec_xong", "khong_lech_ban_giao", "kcs_cuoi_kiem_het", "dat_muc_tieu",
        # "phan_bo_da_chot" GỠ 18/09/2026 cùng tầng chia sản lượng (mg `0322`).
    }
    # Còn dở (chưa xong hết) nhưng sạch điều kiện toàn vẹn ⇒ chưa đóng đủ nhưng đủ đóng thiếu.
    assert dk["du_dong_du"] is False and dk["du_dong_thieu"] is True
    # response_model của GET /dieu-kien-dong phải nhận trọn dict (kể cả list điều kiện lồng).
    val = DongNhomDieuKienOut.model_validate(dk)
    assert len(val.dieu_kien) == 4 and val.du_dong_thieu is True
