"""Thực hiện sản xuất — Giai đoạn 3 mặt GHI: SẢN LƯỢNG batch + lot đầu vào (§10.3 · §11.1).

Soi tầng service `services/san_xuat/san_luong.py` (nơi chứa LUẬT), không qua HTTP:
  · `tong = tot + hong` (dung sai làm tròn), `hong > 0` bắt buộc nhóm lỗi chuẩn hoá (nhóm `loi`);
  · chỉ ghi cho công việc ĐÃ khởi động; GATE §6 chỉ tổ trưởng đúng tổ;
  · lot đầu vào từ batch công đoạn trước (§10.3) — không trỏ về chính công việc đang ghi;
  · `them_lot` bổ sung truy vết cho batch đã tạo.

Tái dùng dàn cảnh (đơn → SX → phát hành vào một tổ khoán) từ test bàn tổ / thực thi.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models.san_xuat import CV_DANG_CHAY, SanXuatCongViec
from app.models.san_xuat_san_luong import SanXuatBatch, SanXuatBatchLotVao
from app.services.san_xuat import san_luong

# Fixtures + helper luồng thật (kéo cả cây fixture xếp lịch).
from tests.test_san_xuat_thuc_thi import (  # noqa: F401
    _cvs,
    _mot_cv,
    _phat_hanh_vao_to,
    _to_khoan,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
)

_T0 = datetime(2026, 8, 19, 8, 0, tzinfo=timezone.utc)


def _cv_chay(db, orders, lsx_svc, admin, customer, ma="TO-SL"):
    """Một tổ khoán + một công việc ĐANG CHẠY, có sẵn đơn vị ra/vào để ghi batch."""
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma=ma)
    cv.trang_thai = CV_DANG_CHAY
    cv.don_vi_ra = "tờ"
    cv.don_vi_vao = "tờ"
    db.commit()
    return to, cv


def _hai_cv_chay(db, orders, lsx_svc, admin, customer):
    """Hai công việc cùng tổ khoán, cùng ĐANG CHẠY — để test lot batch→batch."""
    to = _to_khoan(db, admin, ma="TO-SL2")
    _phat_hanh_vao_to(db, orders, lsx_svc, admin, customer, to.id)
    cv1, cv2 = _cvs(db, to)[:2]
    for cv in (cv1, cv2):
        cv.trang_thai = CV_DANG_CHAY
        cv.don_vi_ra = "tờ"
        cv.don_vi_vao = "tờ"
    db.commit()
    return to, cv1, cv2


# --- Ghi batch (§11.1) ----------------------------------------------------------------------
def test_tao_batch_tot_hong_va_mo_ta_loi(db, orders, lsx_svc, admin, customer):
    to, cv = _cv_chay(db, orders, lsx_svc, admin, customer)

    res = san_luong.tao_batch(
        db, user=admin, cong_viec_id=cv.id,
        bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=1),
        tong=100, tot=90, hong=10, mo_ta_loi="Kẹt tay kê",
    )

    assert res["cong_viec_id"] == cv.id and res["batch_id"]
    b = db.get(SanXuatBatch, res["batch_id"])
    assert float(b.tong) == 100 and float(b.tot) == 90 and float(b.hong) == 10
    assert b.mo_ta_loi == "Kẹt tay kê" and b.don_vi == "tờ"
    # Tổng tốt dẫn xuất = nền trần bàn giao.
    assert san_luong.SanXuatSanLuongRepository(db).tong_tot(cv.id) == 90


def test_tong_khac_tot_cong_hong_bi_chan(db, orders, lsx_svc, admin, customer):
    to, cv = _cv_chay(db, orders, lsx_svc, admin, customer)
    with pytest.raises(ValueError):
        san_luong.tao_batch(
            db, user=admin, cong_viec_id=cv.id,
            bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=1),
            tong=100, tot=80, hong=10,   # 80 + 10 ≠ 100
        )


def test_hong_khong_con_doi_nhom_loi(db, orders, lsx_svc, admin, customer):
    """Danh mục lý do/lỗi ĐÃ GỠ (mg 0288): ghi hỏng KHÔNG còn phải nêu lý do gì."""
    to, cv = _cv_chay(db, orders, lsx_svc, admin, customer)
    r = san_luong.tao_batch(
        db, user=admin, cong_viec_id=cv.id,
        bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=1),
        tong=100, tot=90, hong=10,
    )
    assert r["batch_id"] is not None


def test_chua_bat_dau_khong_ghi_duoc(db, orders, lsx_svc, admin, customer):
    to, cv = _mot_cv(db, orders, lsx_svc, admin, customer, ma="TO-SL-CHUA")
    cv.don_vi_ra = "tờ"
    db.commit()                                          # cv vẫn 'released'
    with pytest.raises(ValueError):
        san_luong.tao_batch(
            db, user=admin, cong_viec_id=cv.id,
            bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=1), tong=10, tot=10,
        )


def test_gate_chi_to_truong(db, orders, lsx_svc, admin, customer):
    to, cv = _cv_chay(db, orders, lsx_svc, admin, customer)
    nguoi_la = SimpleNamespace(id=admin.id + 99_999)
    with pytest.raises(PermissionError):
        san_luong.tao_batch(
            db, user=nguoi_la, cong_viec_id=cv.id,
            bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=1), tong=10, tot=10,
        )


# --- Lot đầu vào (§10.3) --------------------------------------------------------------------
def test_lot_tu_batch_cong_doan_truoc(db, orders, lsx_svc, admin, customer):
    to, cv1, cv2 = _hai_cv_chay(db, orders, lsx_svc, admin, customer)
    r1 = san_luong.tao_batch(
        db, user=admin, cong_viec_id=cv1.id,
        bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=1), tong=50, tot=50,
    )
    r2 = san_luong.tao_batch(
        db, user=admin, cong_viec_id=cv2.id,
        bat_dau=_T0 + timedelta(hours=2), ket_thuc=_T0 + timedelta(hours=3),
        tong=48, tot=48,
        lot_vao=[{"nguon_batch_id": r1["batch_id"], "so_luong": 50}],
    )
    lots = (
        db.query(SanXuatBatchLotVao).filter_by(batch_id=r2["batch_id"]).all()
    )
    assert len(lots) == 1 and lots[0].nguon_batch_id == r1["batch_id"]
    assert float(lots[0].so_luong) == 50 and lots[0].don_vi == "tờ"


def test_lot_khong_tro_ve_chinh_minh(db, orders, lsx_svc, admin, customer):
    to, cv = _cv_chay(db, orders, lsx_svc, admin, customer)
    r1 = san_luong.tao_batch(
        db, user=admin, cong_viec_id=cv.id,
        bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=1), tong=50, tot=50,
    )
    with pytest.raises(ValueError):                       # lot trỏ batch của CHÍNH cv
        san_luong.tao_batch(
            db, user=admin, cong_viec_id=cv.id,
            bat_dau=_T0 + timedelta(hours=2), ket_thuc=_T0 + timedelta(hours=3),
            tong=10, tot=10,
            lot_vao=[{"nguon_batch_id": r1["batch_id"], "so_luong": 10}],
        )


def test_them_lot_bo_sung(db, orders, lsx_svc, admin, customer):
    to, cv1, cv2 = _hai_cv_chay(db, orders, lsx_svc, admin, customer)
    r1 = san_luong.tao_batch(
        db, user=admin, cong_viec_id=cv1.id,
        bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=1), tong=50, tot=50,
    )
    r2 = san_luong.tao_batch(
        db, user=admin, cong_viec_id=cv2.id,
        bat_dau=_T0 + timedelta(hours=2), ket_thuc=_T0 + timedelta(hours=3),
        tong=50, tot=50,
    )
    san_luong.them_lot(
        db, user=admin, batch_id=r2["batch_id"],
        nguon_batch_id=r1["batch_id"], so_luong=50,
    )
    lots = db.query(SanXuatBatchLotVao).filter_by(batch_id=r2["batch_id"]).all()
    assert len(lots) == 1 and lots[0].nguon_batch_id == r1["batch_id"]


def test_ket_qua_nhanh_model_tao_duoc(db):
    from app.models.san_xuat_san_luong import SanXuatKetQuaNhanh
    kq = SanXuatKetQuaNhanh(batch_id=1, lsx_id=1, so_luong=10, don_vi="con")
    db.add(kq)
    db.commit()
    db.refresh(kq)
    assert kq.id is not None
    assert kq.ban_giao_id is None


def test_toa_san_luong_hai_nhanh_dung_ty_le(db, orders, lsx_svc, admin, customer):
    from app.models.san_xuat import SanXuatPhuThuoc
    from app.models.san_xuat_san_luong import BG_XAC_NHAN, SanXuatBanGiao
    from tests.test_san_xuat_ban_giao import _hai_cv

    _to1, cv_nguon, cv_a, lsx_a = _hai_cv(db, orders, lsx_svc, admin, customer, ma="TO-TOA-1")
    _to2, cv_b, _cv_b2, lsx_b = _hai_cv(db, orders, lsx_svc, admin, customer, ma="TO-TOA-2")
    cv_a.lsx_id = lsx_a
    cv_b.lsx_id = lsx_b
    db.add(SanXuatPhuThuoc(
        goi_id=cv_nguon.goi_id, phien_ban_so=cv_nguon.phien_ban_so, nhom_id=cv_nguon.nhom_id,
        nguon_cong_viec_id=cv_nguon.id, dich_cong_viec_id=cv_a.id,
        ty_le_ghep=1.5, don_vi_nguon="tờ", don_vi_dich="con",
    ))
    db.add(SanXuatPhuThuoc(
        goi_id=cv_nguon.goi_id, phien_ban_so=cv_nguon.phien_ban_so, nhom_id=cv_nguon.nhom_id,
        nguon_cong_viec_id=cv_nguon.id, dich_cong_viec_id=cv_b.id,
        ty_le_ghep=1.0, don_vi_nguon="tờ", don_vi_dich="con",
    ))
    db.commit()

    res = san_luong.tao_batch(
        db, user=admin, cong_viec_id=cv_nguon.id,
        bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=1), tong=120, tot=120,
    )
    ket_qua = {k["lsx_id"]: k for k in res["ket_qua_lsx"]}
    assert ket_qua[lsx_a]["so_luong"] == 180.0
    assert ket_qua[lsx_b]["so_luong"] == 120.0
    bg_a = db.get(SanXuatBanGiao, ket_qua[lsx_a]["ban_giao_id"])
    assert bg_a.trang_thai == BG_XAC_NHAN
    assert bg_a.nguon_cong_viec_id == cv_nguon.id and bg_a.dich_cong_viec_id == cv_a.id


def test_chan_lsx_khac_dung_lot_diem_toa(db, orders, lsx_svc, admin, customer):
    from app.models.san_xuat import SanXuatPhuThuoc
    from tests.test_san_xuat_ban_giao import _hai_cv

    _to1, cv_nguon, cv_a, lsx_a = _hai_cv(db, orders, lsx_svc, admin, customer, ma="TO-TOA-A1")
    _to2, cv_b, _cv_b2, lsx_b = _hai_cv(db, orders, lsx_svc, admin, customer, ma="TO-TOA-A2")
    _to3, cv_c, _cv_c2, lsx_c = _hai_cv(db, orders, lsx_svc, admin, customer, ma="TO-TOA-A3")
    cv_a.lsx_id, cv_b.lsx_id, cv_c.lsx_id = lsx_a, lsx_b, lsx_c
    db.add(SanXuatPhuThuoc(
        goi_id=cv_nguon.goi_id, phien_ban_so=cv_nguon.phien_ban_so, nhom_id=cv_nguon.nhom_id,
        nguon_cong_viec_id=cv_nguon.id, dich_cong_viec_id=cv_a.id,
        ty_le_ghep=1.0, don_vi_nguon="tờ", don_vi_dich="con",
    ))
    db.commit()
    res = san_luong.tao_batch(
        db, user=admin, cong_viec_id=cv_nguon.id,
        bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=1), tong=100, tot=100,
    )
    batch_nguon_id = res["batch_id"]

    # (1) LSX B có phần (100 con) → dùng trong hạn mức là được.
    ok = san_luong.tao_batch(
        db, user=admin, cong_viec_id=cv_a.id,
        bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=1), tong=60, tot=60,
        lot_vao=[{"nguon_loai": "batch", "nguon_batch_id": batch_nguon_id, "so_luong": 60}],
    )
    assert ok["batch_id"] is not None

    # (2) Vượt phần đã toả cho lsx_a (100) — 60 đã dùng + 60 nữa = 120 > 100 → chặn.
    with pytest.raises(ValueError, match="Vượt phần đã toả"):
        san_luong.tao_batch(
            db, user=admin, cong_viec_id=cv_a.id,
            bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=1), tong=60, tot=60,
            lot_vao=[{"nguon_loai": "batch", "nguon_batch_id": batch_nguon_id, "so_luong": 60}],
        )

    # (3) LSX C không có cạnh toả nào từ batch_nguon_id → không có phần, bị chặn dù số nhỏ.
    with pytest.raises(ValueError, match="không có phần"):
        san_luong.tao_batch(
            db, user=admin, cong_viec_id=cv_c.id,
            bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=1), tong=1, tot=1,
            lot_vao=[{"nguon_loai": "batch", "nguon_batch_id": batch_nguon_id, "so_luong": 1}],
        )


def test_schema_san_luong_ket_qua_giu_ket_qua_lsx():
    from app.schemas.san_xuat import SanLuongKetQuaOut
    obj = SanLuongKetQuaOut(
        cong_viec_id=1, department_id=None, trang_thai="dang_chay", version=1, batch_id=1,
        ket_qua_lsx=[{"lsx_id": 9, "so_luong": 12.5, "don_vi": "con", "ban_giao_id": 3}],
    )
    assert obj.ket_qua_lsx[0].lsx_id == 9
    assert obj.ket_qua_lsx[0].so_luong == 12.5


# --- Chia sản lượng NHÁP hiện ngay khi ghi mẻ (spec 2026-09-11 §5.1) ------------------------
# Fixtures/helper mượn từ bài phân bổ: ở đó mới có cảnh "tổ + việc đang chạy + mẻ + chấm công".
from tests.test_san_xuat_phan_bo import (  # noqa: E402
    _canh_phan_bo,
    _cham_cong,
    _khoang,
)
from tests.test_san_xuat_thuc_thi import _emp  # noqa: E402,F401


def _authz_sl(db):
    from app.repositories.rbac_repo import RoleRepository
    from app.services.rbac_service import AuthorizationService

    return AuthorizationService(RoleRepository(db))


def test_ghi_me_xong_la_thay_ngay_ai_duoc_may_to(db, orders, lsx_svc, admin, customer):
    """Ghi mẻ xong PHẢI thấy ngay phần của từng người — không phải bấm "Chia sản lượng" mới hiện.

    Đây là yêu cầu thẳng của chủ xưởng 11/09/2026 (*"hình như thiếu sản lượng"*): tổ trưởng ghi mẻ
    là biết luôn ai được bao nhiêu, số nháp cũng được, miễn có.
    """
    from app.services.san_xuat import board

    to, cv, batch = _canh_phan_bo(db, orders, lsx_svc, admin, customer, ma="TO-CHIA-NHAP")
    e1 = _emp(db, to, "NV-CN-1", ten="Thợ Một")
    e2 = _emp(db, to, "NV-CN-2", ten="Thợ Hai")
    _cham_cong(db, e1)
    _cham_cong(db, e2)
    db.commit()
    _khoang(db, cv, e1, batch.bat_dau, batch.ket_thuc, heso=1.0)
    _khoang(db, cv, e2, batch.bat_dau, batch.ket_thuc, heso=1.0)
    db.commit()

    d = board.chi_tiet_cong_viec(db, admin, _authz_sl(db), cong_viec_id=cv.id)
    me = d["san_luong"]["batches"][0]
    chia = me["chia_du_kien"]
    assert chia is not None
    assert chia["q"] == 100.0
    assert len(chia["dong"]) == 2
    assert abs(sum(x["so_luong"] for x in chia["dong"]) - 100.0) < 1e-6, "Σ phải đúng bằng sản lượng tốt"
    for x in chia["dong"]:
        assert x["ho_ten"]
        assert x["phut_thuc_te"] > 0
        assert x["he_so_bac"] is not None
        assert "don_gia" not in x and "tien" not in x


def test_me_da_chot_thi_doc_o_ban_chot_khong_tra_nhap(db, orders, lsx_svc, admin, customer):
    """Mẻ đã có bản chia CHỐT thì `chia_du_kien` phải là None — số thật đọc ở `phan_bo`, đừng bày
    thêm một bản nháp thứ hai cạnh nó cho người ta phân vân số nào mới đúng."""
    from app.services.san_xuat import board, phan_bo

    to, cv, batch = _canh_phan_bo(db, orders, lsx_svc, admin, customer, ma="TO-CHIA-CHOT")
    e = _emp(db, to, "NV-CC-1", ten="Thợ Chốt")
    _cham_cong(db, e)
    db.commit()
    _khoang(db, cv, e, batch.bat_dau, batch.ket_thuc, heso=1.0)
    db.commit()
    kq = phan_bo.tinh_phan_bo(db, user=admin, batch_id=batch.id)
    phan_bo.chot_phan_bo(db, user=admin, phan_bo_id=kq["phan_bo_id"])
    db.commit()

    d = board.chi_tiet_cong_viec(db, admin, _authz_sl(db), cong_viec_id=cv.id)
    assert d["san_luong"]["batches"][0]["chia_du_kien"] is None
    assert d["phan_bo"][0]["trang_thai"] == "finalized"
