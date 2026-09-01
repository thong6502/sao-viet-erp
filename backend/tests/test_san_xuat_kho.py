"""Thực hiện sản xuất — Giai đoạn 5 (KHO): yêu cầu nhập kho thành phẩm · xác nhận kho · phân loại BTP dư (§14).

Soi tầng service `services/san_xuat/kho.py` (nơi chứa LUẬT), không qua HTTP:
  · §14.1 KCS tạo nhiều yêu cầu nhập kho MỘT PHẦN từ một batch ĐẠT; TỔNG yêu cầu của một batch ≤
    `so_luong_dat`; kho xác nhận từng phần (cộng dồn) → mỗi lần đẻ MỘT lot thành phẩm (khoá); trạng
    thái suy theo số (chờ → một phần → đủ); KCS huỷ phần chưa nhận (giữ phần đã khoá);
  · §14.2 BTP dư phân loại `nhập kho BTP` / `mẫu lưu` / `phế`; riêng `nhập kho BTP` chờ kho xác nhận
    nhận (chặn đóng nhóm §16); mẫu lưu / phế là chung cục ngay;
  · registry hàng get-or-create theo danh tính → hai yêu cầu cùng một batch dùng CHUNG một hàng;
  · GATE §6: bên KCS/tổ (tạo yêu cầu, huỷ, phân loại BTP) gate tổ trưởng đúng tổ; một test API cuối:
    hộp thư kho chưa đăng nhập → 401.

Tái dùng dàn cảnh (đơn → SX → phát hành) + helper `_batch` (batch KCS đạt một phần) từ test KCS.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.models.kho_hang import KhoHang
from app.models.san_xuat_kho import (
    HANG_THANH_PHAM,
    PL_MAU_LUU,
    PL_NHAP_BTP,
    PL_PHE,
    YC_CHO_KHO,
    YC_DA_NHAP,
    YC_HUY,
    YC_MOT_PHAN,
)
from app.repositories.san_xuat_kho_repo import SanXuatKhoRepository
from app.services.san_xuat import kho

# Fixtures + helper batch KCS đạt một phần (nhan=100, dat=90, khong_dat=10).
from tests.test_san_xuat_kcs import (  # noqa: F401
    _batch,
    _cv_kcs,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
)


def _kho_tp(db, ma="KHO-TP", ten="Kho thành phẩm") -> KhoHang:
    """Kho ĐÍCH để kho xác nhận nhập vào — `kho_xac_nhan_nhap` bắt buộc chọn kho (31/08/2026).
    Luật kho đích soi riêng ở `test_san_xuat_kho_dich.py`; ở đây chỉ là dàn cảnh."""
    k = KhoHang(ma=ma, ten=ten)
    db.add(k)
    db.flush()
    return k


# --- §14.1 Yêu cầu nhập kho thành phẩm ------------------------------------------------------
def test_tong_yeu_cau_khong_vuot_so_dat(db, orders, lsx_svc, admin, customer):
    to, cv, rb = _batch(db, orders, lsx_svc, admin, customer)          # dat = 90
    r1 = kho.tao_yeu_cau_nhap_thanh_pham(
        db, user=admin, kcs_batch_id=rb["kcs_batch_id"], so_luong=50)
    assert r1["trang_thai"] == YC_CHO_KHO
    r2 = kho.tao_yeu_cau_nhap_thanh_pham(
        db, user=admin, kcs_batch_id=rb["kcs_batch_id"], so_luong=40)  # 50 + 40 = 90 vừa đủ
    assert r2["nhom_id"] == r1["nhom_id"]
    with pytest.raises(ValueError):                                    # 90 + 1 > 90
        kho.tao_yeu_cau_nhap_thanh_pham(
            db, user=admin, kcs_batch_id=rb["kcs_batch_id"], so_luong=1)


def test_batch_khong_dat_khong_nhap_kho(db, orders, lsx_svc, admin, customer):
    to, cv, rb = _batch(db, orders, lsx_svc, admin, customer, nhan=40, dat=0, khong_dat=40)
    with pytest.raises(ValueError):                                    # không có số đạt
        kho.tao_yeu_cau_nhap_thanh_pham(
            db, user=admin, kcs_batch_id=rb["kcs_batch_id"], so_luong=5)


def test_hai_yeu_cau_mot_batch_dung_chung_registry(db, orders, lsx_svc, admin, customer):
    to, cv, rb = _batch(db, orders, lsx_svc, admin, customer)
    r1 = kho.tao_yeu_cau_nhap_thanh_pham(
        db, user=admin, kcs_batch_id=rb["kcs_batch_id"], so_luong=10)
    r2 = kho.tao_yeu_cau_nhap_thanh_pham(
        db, user=admin, kcs_batch_id=rb["kcs_batch_id"], so_luong=20)
    assert r1["hang_id"] == r2["hang_id"]                              # cùng danh tính → chung hàng
    repo = SanXuatKhoRepository(db)
    assert repo.dem_hang() == 1
    assert repo.hang(r1["hang_id"]).loai_hang == HANG_THANH_PHAM


def test_gate_chi_to_truong_kcs_tao_yeu_cau(db, orders, lsx_svc, admin, customer):
    to, cv, rb = _batch(db, orders, lsx_svc, admin, customer)
    nguoi_la = SimpleNamespace(id=admin.id + 99_999)
    with pytest.raises(PermissionError):
        kho.tao_yeu_cau_nhap_thanh_pham(
            db, user=nguoi_la, kcs_batch_id=rb["kcs_batch_id"], so_luong=10)


# --- §14.1 Kho xác nhận từng phần -----------------------------------------------------------
def test_xac_nhan_tung_phan_de_lot_va_chuyen_trang_thai(db, orders, lsx_svc, admin, customer):
    to, cv, rb = _batch(db, orders, lsx_svc, admin, customer)
    yc = kho.tao_yeu_cau_nhap_thanh_pham(
        db, user=admin, kcs_batch_id=rb["kcs_batch_id"], so_luong=60)
    repo = SanXuatKhoRepository(db)
    k = _kho_tp(db)

    x1 = kho.kho_xac_nhan_nhap(db, user=admin, yc_id=yc["yc_id"], so_luong=20, kho_id=k.id)
    assert x1["trang_thai"] == YC_MOT_PHAN and x1["so_luong_xac_nhan"] == 20
    lot1 = repo.lot(x1["lot_id"])                                      # mỗi lần xác nhận đẻ một lot
    assert lot1.loai_hang == HANG_THANH_PHAM and float(lot1.so_luong) == 20
    assert lot1.kho_xac_nhan is True and lot1.nhap_kho_yc_id == yc["yc_id"]
    assert lot1.kho_id == k.id                                         # lot mang kho đã nhận nó

    x2 = kho.kho_xac_nhan_nhap(db, user=admin, yc_id=yc["yc_id"], so_luong=40, kho_id=k.id)  # đủ 60
    assert x2["trang_thai"] == YC_DA_NHAP and x2["so_luong_xac_nhan"] == 60

    with pytest.raises(ValueError):                                    # đã đủ → không xác nhận thêm
        kho.kho_xac_nhan_nhap(db, user=admin, yc_id=yc["yc_id"], so_luong=1, kho_id=k.id)


def test_xac_nhan_khong_vuot_phan_con_lai(db, orders, lsx_svc, admin, customer):
    to, cv, rb = _batch(db, orders, lsx_svc, admin, customer)
    yc = kho.tao_yeu_cau_nhap_thanh_pham(
        db, user=admin, kcs_batch_id=rb["kcs_batch_id"], so_luong=30)
    k = _kho_tp(db)
    with pytest.raises(ValueError):
        kho.kho_xac_nhan_nhap(db, user=admin, yc_id=yc["yc_id"], so_luong=31, kho_id=k.id)


def test_xac_nhan_version_lech_bi_chan(db, orders, lsx_svc, admin, customer):
    to, cv, rb = _batch(db, orders, lsx_svc, admin, customer)
    yc = kho.tao_yeu_cau_nhap_thanh_pham(
        db, user=admin, kcs_batch_id=rb["kcs_batch_id"], so_luong=30)
    k = _kho_tp(db)
    with pytest.raises(ValueError):
        kho.kho_xac_nhan_nhap(
            db, user=admin, yc_id=yc["yc_id"], so_luong=10, kho_id=k.id,
            expected_version=yc["version"] + 5)


# --- §14.1 KCS huỷ phần chưa nhận (giữ phần đã khoá) ----------------------------------------
def test_huy_phan_chua_nhan_giu_phan_da_khoa(db, orders, lsx_svc, admin, customer):
    to, cv, rb = _batch(db, orders, lsx_svc, admin, customer)
    yc = kho.tao_yeu_cau_nhap_thanh_pham(
        db, user=admin, kcs_batch_id=rb["kcs_batch_id"], so_luong=50)
    k = _kho_tp(db)
    kho.kho_xac_nhan_nhap(db, user=admin, yc_id=yc["yc_id"], so_luong=20, kho_id=k.id)  # khoá 20

    res = kho.huy_phan_chua_nhan(db, user=admin, yc_id=yc["yc_id"])
    assert res["trang_thai"] == YC_DA_NHAP                             # còn phần đã nhận → chốt đủ
    y = SanXuatKhoRepository(db).yc(yc["yc_id"])
    assert float(y.so_luong_yeu_cau) == 20                            # trần chốt về phần đã nhận


def test_huy_khi_chua_nhan_gi_thi_huy_han(db, orders, lsx_svc, admin, customer):
    to, cv, rb = _batch(db, orders, lsx_svc, admin, customer)
    yc = kho.tao_yeu_cau_nhap_thanh_pham(
        db, user=admin, kcs_batch_id=rb["kcs_batch_id"], so_luong=30)
    res = kho.huy_phan_chua_nhan(db, user=admin, yc_id=yc["yc_id"])
    assert res["trang_thai"] == YC_HUY
    # đã huỷ hết → giải phóng trần: yêu cầu lại đủ 90 được
    r2 = kho.tao_yeu_cau_nhap_thanh_pham(
        db, user=admin, kcs_batch_id=rb["kcs_batch_id"], so_luong=90)
    assert r2["trang_thai"] == YC_CHO_KHO


# --- §14.2 Phân loại BTP dư -----------------------------------------------------------------
def test_phan_loai_btp_nhap_cho_kho_con_mau_phe_chung_cuc(db, orders, lsx_svc, admin, customer):
    to, cv, rb = _batch(db, orders, lsx_svc, admin, customer)
    repo = SanXuatKhoRepository(db)

    l_nhap = kho.phan_loai_btp_du(
        db, user=admin, cong_viec_id=cv.id, so_luong=5, phan_loai=PL_NHAP_BTP)
    assert l_nhap["cho_kho"] is True                                  # nhập kho BTP → chờ kho
    assert repo.lot(l_nhap["lot_id"]).kho_xac_nhan is False

    l_mau = kho.phan_loai_btp_du(
        db, user=admin, cong_viec_id=cv.id, so_luong=2, phan_loai=PL_MAU_LUU)
    assert l_mau["cho_kho"] is False                                  # mẫu lưu → chung cục ngay
    assert repo.lot(l_mau["lot_id"]).kho_xac_nhan is True

    l_phe = kho.phan_loai_btp_du(
        db, user=admin, cong_viec_id=cv.id, so_luong=3, phan_loai=PL_PHE)
    assert repo.lot(l_phe["lot_id"]).kho_xac_nhan is True             # phế → chung cục ngay

    # ba lot BTP cùng danh tính (đơn+nhóm+LSX+công đoạn+quy cách) → chung một registry.
    assert l_nhap["hang_id"] == l_mau["hang_id"] == l_phe["hang_id"]


def test_phan_loai_btp_sai_loai_bi_chan(db, orders, lsx_svc, admin, customer):
    to, cv, rb = _batch(db, orders, lsx_svc, admin, customer)
    with pytest.raises(ValueError):
        kho.phan_loai_btp_du(
            db, user=admin, cong_viec_id=cv.id, so_luong=5, phan_loai="linh_tinh")


def test_gate_phan_loai_btp(db, orders, lsx_svc, admin, customer):
    to, cv, rb = _batch(db, orders, lsx_svc, admin, customer)
    nguoi_la = SimpleNamespace(id=admin.id + 99_999)
    with pytest.raises(PermissionError):
        kho.phan_loai_btp_du(
            db, user=nguoi_la, cong_viec_id=cv.id, so_luong=5, phan_loai=PL_NHAP_BTP)


# --- §14.2 Kho xác nhận BTP + trần đóng nhóm (§16) ------------------------------------------
def test_kho_xac_nhan_btp_mo_tran_dong_nhom(db, orders, lsx_svc, admin, customer):
    to, cv, rb = _batch(db, orders, lsx_svc, admin, customer)
    repo = SanXuatKhoRepository(db)
    l = kho.phan_loai_btp_du(
        db, user=admin, cong_viec_id=cv.id, so_luong=5, phan_loai=PL_NHAP_BTP)
    assert repo.co_btp_tra_cho_kho(cv.nhom_id) is True                # còn BTP chờ kho → chặn (§16)

    out = kho.kho_xac_nhan_btp(db, user=admin, lot_id=l["lot_id"])
    assert out["nhom_id"] == cv.nhom_id and out["cong_viec_id"] == cv.id
    assert repo.lot(l["lot_id"]).kho_xac_nhan is True
    assert repo.co_btp_tra_cho_kho(cv.nhom_id) is False               # hết chờ → mở

    with pytest.raises(ValueError):                                    # đã xác nhận → không lặp
        kho.kho_xac_nhan_btp(db, user=admin, lot_id=l["lot_id"])


def test_kho_xac_nhan_btp_tu_choi_mau_luu(db, orders, lsx_svc, admin, customer):
    to, cv, rb = _batch(db, orders, lsx_svc, admin, customer)
    l = kho.phan_loai_btp_du(
        db, user=admin, cong_viec_id=cv.id, so_luong=2, phan_loai=PL_MAU_LUU)
    with pytest.raises(ValueError):                                    # mẫu lưu không qua kho
        kho.kho_xac_nhan_btp(db, user=admin, lot_id=l["lot_id"])


# --- Đọc: hộp thư kho + chi tiết nhóm -------------------------------------------------------
def test_hop_thu_kho_gom_yc_va_btp_cho_nhan(db, orders, lsx_svc, admin, customer):
    to, cv, rb = _batch(db, orders, lsx_svc, admin, customer)
    yc = kho.tao_yeu_cau_nhap_thanh_pham(
        db, user=admin, kcs_batch_id=rb["kcs_batch_id"], so_luong=30)
    lb = kho.phan_loai_btp_du(
        db, user=admin, cong_viec_id=cv.id, so_luong=5, phan_loai=PL_NHAP_BTP)

    hop = kho.hop_thu_kho(db)
    assert [y["id"] for y in hop["yeu_cau_nhap"]] == [yc["yc_id"]]
    assert [l["id"] for l in hop["btp_cho_nhan"]] == [lb["lot_id"]]

    k = _kho_tp(db)
    kho.kho_xac_nhan_nhap(db, user=admin, yc_id=yc["yc_id"], so_luong=30, kho_id=k.id)  # đủ → rời hộp thư
    kho.kho_xac_nhan_btp(db, user=admin, lot_id=lb["lot_id"])
    hop2 = kho.hop_thu_kho(db)
    assert hop2["yeu_cau_nhap"] == [] and hop2["btp_cho_nhan"] == []


def test_chi_tiet_kho_nhom(db, orders, lsx_svc, admin, customer):
    to, cv, rb = _batch(db, orders, lsx_svc, admin, customer)
    yc = kho.tao_yeu_cau_nhap_thanh_pham(
        db, user=admin, kcs_batch_id=rb["kcs_batch_id"], so_luong=30)
    k = _kho_tp(db)
    kho.kho_xac_nhan_nhap(db, user=admin, yc_id=yc["yc_id"], so_luong=10, kho_id=k.id)
    lb = kho.phan_loai_btp_du(
        db, user=admin, cong_viec_id=cv.id, so_luong=5, phan_loai=PL_NHAP_BTP)

    ct = kho.chi_tiet_kho_nhom(db, cv.nhom_id)
    assert ct["nhom_id"] == cv.nhom_id
    assert [y["id"] for y in ct["yeu_cau"]] == [yc["yc_id"]]
    assert len(ct["lot"]) == 2                                         # 1 thành phẩm + 1 BTP
    assert [l["id"] for l in ct["btp_tra_cho_kho"]] == [lb["lot_id"]]


# --- Đường dây HTTP -------------------------------------------------------------------------
def test_api_hop_thu_kho_can_dang_nhap(client):
    assert client.get("/api/san-xuat/kho/hop-thu").status_code == 401
