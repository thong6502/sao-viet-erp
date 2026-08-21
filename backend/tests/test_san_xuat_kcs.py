"""Thực hiện sản xuất — Giai đoạn 5 (KCS): batch kiểm tra · lỗi · phản hồi trách nhiệm (§13).

Soi tầng service `services/san_xuat/kcs.py` (nơi chứa LUẬT), không qua HTTP:
  · §13.1 `so_luong_nhan = dat + khong_dat`; NĂNG SUẤT KCS lấy nền theo `so_luong_nhan` → đẻ kèm
    một `san_xuat_batch` (`tot = nhan`, `hong = 0`) để tái dùng NGUYÊN pipeline phân bổ; kết luận
    suy từ số (đạt / đạt một phần / không đạt);
  · chỉ ghi cho công việc KCS (`la_kcs`) đã khởi động; GATE §6 chỉ tổ trưởng đúng tổ KCS;
  · §13.2 mỗi lỗi ≥1 ảnh, nhóm lỗi phải thuộc nhóm `loi`; tổ trưởng tổ BỊ yêu cầu (KHÁC tổ KCS)
    CHẤP NHẬN / TỪ CHỐI-kèm-lý-do — chung thẩm; lỗi chờ CHẶN đóng đủ nhóm (§16);
  · hai test API cuối chứng minh đường dây HTTP: chưa đăng nhập → 401; multipart ảnh + admin
    (thiếu bit `assign_work`) → 403.

Tái dùng dàn cảnh (đơn → SX → phát hành vào một tổ khoán) từ test sản lượng / thực thi.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models.department import Department
from app.models.san_xuat import CV_DANG_CHAY, CV_PHAT_HANH
from app.models.san_xuat_kcs import (
    KCS_DAT,
    KCS_DAT_MOT_PHAN,
    KCS_KHONG_DAT,
    TN_CHAP_NHAN,
    TN_CHO,
    TN_TU_CHOI,
    SanXuatKcsBatch,
    SanXuatKcsLoi,
    SanXuatKcsLoiAnh,
)
from app.models.san_xuat_ly_do import NHOM_LOI, NHOM_TAM_DUNG, SanXuatLyDo
from app.models.san_xuat_san_luong import SanXuatBatch
from app.models.user import User
from app.repositories.san_xuat_kcs_repo import SanXuatKcsRepository
from app.services.san_xuat import kcs

# Fixtures + helper luồng thật (kéo cả cây fixture xếp lịch).
from tests.test_san_xuat_thuc_thi import (  # noqa: F401
    _emp,
    _mot_cv,
    _phat_hanh_vao_to,
    _to_khoan,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
)

_T0 = datetime(2026, 8, 20, 8, 0, tzinfo=timezone.utc)
_T1 = _T0 + timedelta(hours=1)


def _ly_do(db, nhom=NHOM_LOI, ma="LOI-BONG", ten="Bong tróc mực") -> SanXuatLyDo:
    ld = SanXuatLyDo(ma=ma, nhom=nhom, ten=ten)
    db.add(ld)
    db.flush()
    return ld


def _cv_kcs(db, orders, lsx_svc, admin, customer, ma="TO-KCS"):
    """Một tổ khoán + một công việc KCS ĐANG CHẠY, có đơn vị ra để ghi batch kiểm tra."""
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma=ma)
    cv.la_kcs = True
    cv.trang_thai = CV_DANG_CHAY
    cv.don_vi_ra = "cái"
    cv.don_vi_vao = "cái"
    db.commit()
    return to, cv


def _to_chiu(db, ten="Tổ Bế Bị Đổ", ma="TO-CHIU") -> tuple[Department, User]:
    """Một tổ SX khác + tổ trưởng riêng (để soi gate phản hồi = tổ trưởng tổ BỊ yêu cầu)."""
    u = User(username=f"tt_{ma.lower()}", name="Tổ Trưởng Bế", password_hash="x")
    db.add(u)
    db.flush()
    d = Department(name=ten, code=ma, la_san_xuat=True, head_user_id=u.id)
    db.add(d)
    db.flush()
    return d, u


def _anh() -> list[dict]:
    return [{"file_name": "loi.jpg", "file_url": "/api/files/san-xuat/kcs-loi/1/x_loi.jpg",
             "file_type": "image/jpeg"}]


def _batch(db, orders, lsx_svc, admin, customer, *, nhan=100, dat=90, khong_dat=10, ma="TO-KCS"):
    to, cv = _cv_kcs(db, orders, lsx_svc, admin, customer, ma=ma)
    res = kcs.tao_batch_kcs(
        db, user=admin, cong_viec_id=cv.id, bat_dau=_T0, ket_thuc=_T1,
        so_luong_nhan=nhan, so_luong_dat=dat, so_luong_khong_dat=khong_dat,
    )
    return to, cv, res


# --- Batch kiểm tra (§13.1) -----------------------------------------------------------------
def test_tao_batch_de_kem_batch_san_luong_nen(db, orders, lsx_svc, admin, customer):
    to, cv, res = _batch(db, orders, lsx_svc, admin, customer)

    kb = db.get(SanXuatKcsBatch, res["kcs_batch_id"])
    assert kb is not None and float(kb.so_luong_nhan) == 100
    assert float(kb.so_luong_dat) == 90 and float(kb.so_luong_khong_dat) == 10
    assert kb.ket_luan == KCS_DAT_MOT_PHAN and kb.don_vi == "cái"

    # Batch sản lượng nền: tot = số NHẬN (nền năng suất KCS §13.1), hong = 0 (không đạt là lỗi
    # SẢN PHẨM, không phải hỏng do KCS). Pipeline phân bổ đọc batch.tot → chạy nguyên.
    assert res["batch_id"] and kb.batch_id == res["batch_id"]
    b = db.get(SanXuatBatch, res["batch_id"])
    assert float(b.tong) == 100 and float(b.tot) == 100 and float(b.hong) == 0
    assert b.ghi_chu == "KCS" and b.cong_viec_id == cv.id


def test_ket_luan_dat_khi_khong_co_khong_dat(db, orders, lsx_svc, admin, customer):
    _to, _cv, r = _batch(db, orders, lsx_svc, admin, customer, nhan=50, dat=50, khong_dat=0)
    assert db.get(SanXuatKcsBatch, r["kcs_batch_id"]).ket_luan == KCS_DAT


def test_ket_luan_khong_dat_khi_khong_co_dat(db, orders, lsx_svc, admin, customer):
    _to, _cv, r = _batch(db, orders, lsx_svc, admin, customer, nhan=40, dat=0, khong_dat=40)
    assert db.get(SanXuatKcsBatch, r["kcs_batch_id"]).ket_luan == KCS_KHONG_DAT


def test_nhan_khac_dat_cong_khong_dat_bi_chan(db, orders, lsx_svc, admin, customer):
    to, cv = _cv_kcs(db, orders, lsx_svc, admin, customer)
    with pytest.raises(ValueError):
        kcs.tao_batch_kcs(
            db, user=admin, cong_viec_id=cv.id, bat_dau=_T0, ket_thuc=_T1,
            so_luong_nhan=100, so_luong_dat=80, so_luong_khong_dat=10,   # 80 + 10 ≠ 100
        )


def test_co_mau_khong_vuot_so_nhan(db, orders, lsx_svc, admin, customer):
    to, cv = _cv_kcs(db, orders, lsx_svc, admin, customer)
    with pytest.raises(ValueError):
        kcs.tao_batch_kcs(
            db, user=admin, cong_viec_id=cv.id, bat_dau=_T0, ket_thuc=_T1,
            so_luong_nhan=100, so_luong_dat=100, so_luong_khong_dat=0, co_mau=120,
        )


def test_chi_cong_viec_kcs_moi_ghi_duoc(db, orders, lsx_svc, admin, customer):
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-NOT-KCS")
    cv.la_kcs = False                                    # công việc thường, không KCS
    cv.trang_thai = CV_DANG_CHAY
    cv.don_vi_ra = "cái"
    db.commit()
    with pytest.raises(ValueError):
        kcs.tao_batch_kcs(
            db, user=admin, cong_viec_id=cv.id, bat_dau=_T0, ket_thuc=_T1,
            so_luong_nhan=10, so_luong_dat=10, so_luong_khong_dat=0,
        )


def test_chua_bat_dau_khong_ghi_duoc(db, orders, lsx_svc, admin, customer):
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-KCS-CHUA")
    cv.la_kcs = True
    cv.don_vi_ra = "cái"
    db.commit()                                          # vẫn 'released'
    assert cv.trang_thai == CV_PHAT_HANH
    with pytest.raises(ValueError):
        kcs.tao_batch_kcs(
            db, user=admin, cong_viec_id=cv.id, bat_dau=_T0, ket_thuc=_T1,
            so_luong_nhan=10, so_luong_dat=10, so_luong_khong_dat=0,
        )


def test_gate_chi_to_truong_kcs(db, orders, lsx_svc, admin, customer):
    to, cv = _cv_kcs(db, orders, lsx_svc, admin, customer)
    nguoi_la = SimpleNamespace(id=admin.id + 99_999)
    with pytest.raises(PermissionError):
        kcs.tao_batch_kcs(
            db, user=nguoi_la, cong_viec_id=cv.id, bat_dau=_T0, ket_thuc=_T1,
            so_luong_nhan=10, so_luong_dat=10, so_luong_khong_dat=0,
        )


# --- Lỗi + ảnh (§13.2) ----------------------------------------------------------------------
def test_ghi_loi_kem_anh_va_neo_to_chiu(db, orders, lsx_svc, admin, customer):
    to, cv, rb = _batch(db, orders, lsx_svc, admin, customer)
    ld = _ly_do(db)
    to2, tt2 = _to_chiu(db)

    res = kcs.ghi_loi(
        db, user=admin, kcs_batch_id=rb["kcs_batch_id"], nhom_loi_id=ld.id,
        mo_ta="Lem mực mép trái", to_chiu_id=to2.id, so_luong=6, anh=_anh(),
    )

    loi = db.get(SanXuatKcsLoi, res["loi_id"])
    assert loi.trang_thai == TN_CHO and loi.to_chiu_id == to2.id
    assert loi.nhom_loi_id == ld.id and float(loi.so_luong) == 6
    # Đẩy SSE tới tổ trưởng tổ BỊ yêu cầu.
    assert res["to_chiu_head_user_id"] == tt2.id
    anh = db.query(SanXuatKcsLoiAnh).filter_by(loi_id=loi.id).all()
    assert len(anh) == 1 and anh[0].file_name == "loi.jpg"


def test_ghi_loi_bat_buoc_it_nhat_mot_anh(db, orders, lsx_svc, admin, customer):
    to, cv, rb = _batch(db, orders, lsx_svc, admin, customer)
    ld = _ly_do(db)
    with pytest.raises(ValueError):
        kcs.ghi_loi(db, user=admin, kcs_batch_id=rb["kcs_batch_id"],
                    nhom_loi_id=ld.id, anh=[])


def test_ghi_loi_nhom_phai_la_loi(db, orders, lsx_svc, admin, customer):
    to, cv, rb = _batch(db, orders, lsx_svc, admin, customer)
    sai = _ly_do(db, nhom=NHOM_TAM_DUNG, ma="TD-KCS", ten="Chờ mực")   # không phải nhóm `loi`
    with pytest.raises(ValueError):
        kcs.ghi_loi(db, user=admin, kcs_batch_id=rb["kcs_batch_id"],
                    nhom_loi_id=sai.id, anh=_anh())


def test_xoa_anh_giu_it_nhat_mot(db, orders, lsx_svc, admin, customer):
    to, cv, rb = _batch(db, orders, lsx_svc, admin, customer)
    ld = _ly_do(db)
    res = kcs.ghi_loi(db, user=admin, kcs_batch_id=rb["kcs_batch_id"],
                      nhom_loi_id=ld.id, anh=_anh())      # đúng 1 ảnh
    anh = db.query(SanXuatKcsLoiAnh).filter_by(loi_id=res["loi_id"]).first()
    with pytest.raises(ValueError):                        # xoá ảnh cuối → chặn
        kcs.xoa_anh_loi(db, user=admin, anh_id=anh.id)


def test_them_roi_xoa_anh(db, orders, lsx_svc, admin, customer):
    to, cv, rb = _batch(db, orders, lsx_svc, admin, customer)
    ld = _ly_do(db)
    res = kcs.ghi_loi(db, user=admin, kcs_batch_id=rb["kcs_batch_id"],
                      nhom_loi_id=ld.id, anh=_anh())
    them = kcs.them_anh_loi(db, user=admin, loi_id=res["loi_id"], anh=[
        {"file_name": "loi2.jpg", "file_url": "/api/files/san-xuat/kcs-loi/1/y.jpg",
         "file_type": "image/jpeg"}])
    assert them["so_anh"] == 2
    anh0 = db.query(SanXuatKcsLoiAnh).filter_by(loi_id=res["loi_id"]).first()
    out = kcs.xoa_anh_loi(db, user=admin, anh_id=anh0.id)   # còn 2 → xoá được
    assert out["file_url"] == anh0.file_url
    assert db.query(SanXuatKcsLoiAnh).filter_by(loi_id=res["loi_id"]).count() == 1


# --- Phản hồi trách nhiệm (§13.2) -----------------------------------------------------------
def _mot_loi(db, orders, lsx_svc, admin, customer):
    to, cv, rb = _batch(db, orders, lsx_svc, admin, customer)
    ld = _ly_do(db)
    to2, tt2 = _to_chiu(db)
    res = kcs.ghi_loi(db, user=admin, kcs_batch_id=rb["kcs_batch_id"],
                      nhom_loi_id=ld.id, to_chiu_id=to2.id, anh=_anh())
    return cv, res["loi_id"], to2, tt2


def test_phan_hoi_chap_nhan(db, orders, lsx_svc, admin, customer):
    cv, loi_id, to2, tt2 = _mot_loi(db, orders, lsx_svc, admin, customer)
    res = kcs.phan_hoi_loi(db, user=tt2, loi_id=loi_id, chap_nhan=True)
    assert res["trang_thai"] == TN_CHAP_NHAN
    loi = db.get(SanXuatKcsLoi, loi_id)
    assert loi.phan_hoi_by_id == tt2.id and loi.ly_do_tu_choi is None


def test_phan_hoi_tu_choi_bat_buoc_ly_do(db, orders, lsx_svc, admin, customer):
    cv, loi_id, to2, tt2 = _mot_loi(db, orders, lsx_svc, admin, customer)
    with pytest.raises(ValueError):                        # từ chối mà không nêu lý do
        kcs.phan_hoi_loi(db, user=tt2, loi_id=loi_id, chap_nhan=False, ly_do_tu_choi="")
    res = kcs.phan_hoi_loi(db, user=tt2, loi_id=loi_id, chap_nhan=False,
                           ly_do_tu_choi="Do khâu in, không phải tổ tôi")
    assert res["trang_thai"] == TN_TU_CHOI
    assert db.get(SanXuatKcsLoi, loi_id).ly_do_tu_choi == "Do khâu in, không phải tổ tôi"


def test_phan_hoi_gate_dung_to_bi_yeu_cau(db, orders, lsx_svc, admin, customer):
    cv, loi_id, to2, tt2 = _mot_loi(db, orders, lsx_svc, admin, customer)
    # admin là tổ trưởng tổ KCS, KHÔNG phải tổ bị yêu cầu → không được phản hồi.
    with pytest.raises(PermissionError):
        kcs.phan_hoi_loi(db, user=admin, loi_id=loi_id, chap_nhan=True)


def test_phan_hoi_chung_tham(db, orders, lsx_svc, admin, customer):
    cv, loi_id, to2, tt2 = _mot_loi(db, orders, lsx_svc, admin, customer)
    kcs.phan_hoi_loi(db, user=tt2, loi_id=loi_id, chap_nhan=True)
    with pytest.raises(ValueError):                        # đã phản hồi → chung thẩm
        kcs.phan_hoi_loi(db, user=tt2, loi_id=loi_id, chap_nhan=False,
                         ly_do_tu_choi="đổi ý")


# --- Đọc: chi tiết + hộp thư + trần đóng nhóm (§13, §16) -------------------------------------
def test_chi_tiet_kcs_gom_batch_loi_anh(db, orders, lsx_svc, admin, customer):
    cv, loi_id, to2, tt2 = _mot_loi(db, orders, lsx_svc, admin, customer)
    ct = kcs.chi_tiet_kcs(db, admin, cv.id)
    assert ct["la_kcs"] is True and len(ct["batch"]) == 1
    b0 = ct["batch"][0]
    assert b0["so_luong_nhan"] == 100 and len(b0["loi"]) == 1
    assert b0["loi"][0]["trang_thai"] == TN_CHO and len(b0["loi"][0]["anh"]) == 1
    assert b0["loi"][0]["nhom_loi_ten"] == "Bong tróc mực"


def test_hop_thu_loi_theo_to_truong(db, orders, lsx_svc, admin, customer):
    cv, loi_id, to2, tt2 = _mot_loi(db, orders, lsx_svc, admin, customer)
    hop = kcs.hop_thu_loi(db, tt2)                         # tổ trưởng tổ bị yêu cầu
    assert [l["id"] for l in hop] == [loi_id]
    assert kcs.hop_thu_loi(db, admin) == []                # admin không phải tổ bị yêu cầu
    kcs.phan_hoi_loi(db, user=tt2, loi_id=loi_id, chap_nhan=True)
    assert kcs.hop_thu_loi(db, tt2) == []                  # đã phản hồi → rời hộp thư


def test_loi_cho_chan_dong_du_nhom(db, orders, lsx_svc, admin, customer):
    cv, loi_id, to2, tt2 = _mot_loi(db, orders, lsx_svc, admin, customer)
    repo = SanXuatKcsRepository(db)
    assert repo.co_loi_chua_tra_loi(cv.nhom_id) is True    # còn lỗi chờ → chặn (§16)
    kcs.phan_hoi_loi(db, user=tt2, loi_id=loi_id, chap_nhan=True)
    assert repo.co_loi_chua_tra_loi(cv.nhom_id) is False   # hết chờ → mở


# --- Đường dây HTTP ---------------------------------------------------------------------------
def test_api_hop_thu_can_dang_nhap(client):
    assert client.get("/api/san-xuat/kcs/hop-thu").status_code == 401


def test_api_ghi_loi_multipart_admin_thieu_bit_403(client):
    tok = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin123"}
    ).json()["access_token"]
    resp = client.post(
        "/api/san-xuat/kcs/1/loi",
        data={"nhom_loi_id": 1},
        files={"files": ("loi.png", b"\x89PNG\r\n\x1a\n", "image/png")},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert resp.status_code == 403
