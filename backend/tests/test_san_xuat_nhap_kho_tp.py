"""Nhập kho THÀNH PHẨM qua "Yêu cầu nhập xuất" (`docs/design-nhap-kho-thanh-pham-qua-yeu-cau-nhap-xuat.md`).

Soi `services/san_xuat/kho.py` cùng đường kho THẬT (phiếu nhập → ghi sổ → lô), không qua HTTP:
  · KCS bấm một lần = MỘT yêu cầu NHẬP thật, tự duyệt, kho để trống, nguồn = công đoạn; giá gốc 0,
    giá bán lấy từ đơn; `lsx_id` = lệnh thân chính; bấm lại khi hết số → `KhongConSoDuGuiKho` (409);
  · mặt hàng = mã Thành phẩm của CỤM BÁN: nhãn chung ⇒ một dòng giá cụm; nhóm chứa hai cụm ⇒ chia
    theo SL cụm; hai cụm ra cùng một mã ⇒ gộp một dòng, giá bình quân theo số;
  · đơn vị: quy đổi được thì nhân hệ số; không đổi được / món chưa khai đơn vị ⇒ lỗi nghiệp vụ;
  · kho nhận một phần rồi huỷ ⇒ phần chưa nhận quay về cho KCS gửi lại; đọc ngược "kho đã nhận";
  · sự kiện real-time; tồn thành phẩm của nhóm cho khối Giao hàng.
"""
from __future__ import annotations

import pytest

from app.models.don_vi_do import DonViDo, DonViQuyDoi
from app.models.kho_hang import KhoHang
from app.models.lsx import Lsx
from app.models.order import OrderLine
from app.models.san_xuat import SanXuatNhomLsx
from app.models.stock_request import REQ_APPROVED, REQ_NHAP, StockRequest
from app.models.vat_lieu_kho import VatTuInAn
from app.repositories.audit_repo import AuditLogRepository
from app.routers.kho_voucher import get_service as voucher_service
from app.services.san_xuat import kcs, kho
from app.services.san_xuat.vat_tu_de_nghi import _hang_service, _req_service
from app.services.thanh_pham_khai_bao import cum_ban, khai_cum
from tests.test_san_xuat_kcs import (  # noqa: F401
    _batch,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
)


def _gui(db, cv, rb) -> dict:
    return kho.tao_yeu_cau_nhap_kho_cong_doan(db, user=rb["nguoi_kcs"], cong_viec_id=cv.id)


def _dong_don(db, cv) -> list[OrderLine]:
    lenh = db.get(Lsx, cv.lsx_id)
    return sorted(db.query(OrderLine).filter_by(order_id=lenh.order_id).all(), key=lambda x: x.id)


def _nhan(db, admin, request_id: int, so_luong: float, *, kho_ma="KHO-TP") -> None:
    """Thủ kho lập phiếu nhập từ Hộp yêu cầu (chọn kho) rồi ghi sổ — đúng hai hàm router kho gọi."""
    k = db.query(KhoHang).filter_by(ma=kho_ma).one_or_none()
    if k is None:
        k = KhoHang(ma=kho_ma, ten="Kho thành phẩm")
        db.add(k)
        db.commit()
    req = db.get(StockRequest, request_id)
    [ln] = req.lines
    con = float(ln.sl_duyet or ln.sl_de_nghi) - float(ln.sl_da_ung or 0)
    svc = voucher_service(db)
    v = svc.create(user=admin, request_id=request_id, kho_id=k.id, lines=[{
        "request_line_id": ln.id, "so_luong": so_luong,
        "ly_do": "Nhận trước một phần" if so_luong < con else None,
    }])
    svc.post(v.id, admin)


def _huy_boi_kho(db, request_id: int) -> None:
    _req_service(db, _hang_service(db)).cancel_by_kho(db.get(StockRequest, request_id), "Không nhận")


# --- Một cụm, một dòng ------------------------------------------------------------------------
def test_bam_gui_kho_lap_yeu_cau_nhap_that_tu_duyet(db, orders, lsx_svc, admin, customer, monkeypatch):
    phat: list[dict] = []
    monkeypatch.setattr(kho.hub, "broadcast", lambda ev: phat.append(ev))
    _to, cv, rb = _batch(db, orders, lsx_svc, admin, customer, dat=90, khong_dat=10, cuoi=True)

    res = _gui(db, cv, rb)

    req = db.get(StockRequest, res["request_id"])
    assert req.loai == REQ_NHAP and req.trang_thai == REQ_APPROVED and req.kho_id is None
    assert req.san_xuat_cong_viec_id == cv.id and req.bo_phan_id == cv.department_id
    assert req.nguoi_tao_id == rb["nguoi_kcs"].id
    [ln] = req.lines
    tp = db.get(VatTuInAn, ln.hang_id)
    assert tp.la_thanh_pham and tp.ten == "Hộp A" and ln.dvt == tp.don_vi_gia
    assert float(ln.sl_de_nghi) == 90 and float(ln.sl_duyet) == 90
    assert int(ln.don_gia or 0) == 0                      # giá gốc: kế toán kho nhập sau
    assert ln.don_gia_ban == 500                          # 10.000.000 ÷ 20.000 cái
    assert ln.lsx_id == cv.lsx_id                         # lệnh thân chính của nhóm
    assert res["so_luong"] == 90 and res["dong"][0]["ma_hang"] == tp.ma
    [ev] = [e for e in phat if e["type"] == "san_xuat_kho_changed"]
    assert ev["cong_viec_id"] == cv.id and ev["request_id"] == req.id
    log = AuditLogRepository(db).list_for_target(f"san_xuat_cong_viec:{cv.id}")
    assert any(r.action == "san_xuat_kho_yeu_cau_nhap" for r in log)

    with pytest.raises(kho.KhongConSoDuGuiKho):
        _gui(db, cv, rb)
    assert db.query(StockRequest).filter_by(san_xuat_cong_viec_id=cv.id).count() == 1


def test_chua_co_thanh_tien_thi_gia_ban_trong(db, orders, lsx_svc, admin, customer):
    _to, cv, rb = _batch(db, orders, lsx_svc, admin, customer, dat=50, khong_dat=0, cuoi=True)
    for ln in _dong_don(db, cv):
        ln.line_total = None
    db.commit()
    res = _gui(db, cv, rb)
    assert res["dong"][0]["don_gia_ban"] is None
    assert db.get(StockRequest, res["request_id"]).lines[0].don_gia_ban is None


# --- Cụm bán ----------------------------------------------------------------------------------
def test_ruot_bia_cung_nhan_la_mot_dong_gia_cum(db, orders, lsx_svc, admin, customer):
    _to, cv, rb = _batch(db, orders, lsx_svc, admin, customer, dat=90, khong_dat=0, cuoi=True)
    a, b = _dong_don(db, cv)
    for ln in (a, b):
        ln.nhom, ln.dvt_nhom, ln.qty = "Kỷ yếu", "cuốn", 20_000
    cv.don_vi_ra = "cuốn"                                # KCS đếm quyển — cùng đơn vị cụm
    db.commit()

    res = _gui(db, cv, rb)
    [d] = res["dong"]
    assert d["ten_hang"] == "Kỷ yếu" and d["sl_de_nghi"] == 90
    assert d["don_gia_ban"] == 1_000                     # (10tr + 10tr) ÷ 20.000


def _gop_lenh_thu_hai_vao_nhom(db, cv) -> None:
    """Đưa lệnh còn lại của đơn vào CÙNG nhóm với công đoạn cuối — nhóm chứa hai dòng đơn."""
    lenh = db.get(Lsx, cv.lsx_id)
    khac = db.query(Lsx).filter(Lsx.order_id == lenh.order_id, Lsx.id != lenh.id).one()
    tv = db.query(SanXuatNhomLsx).filter_by(lsx_id=khac.id).one_or_none()
    if tv is None:
        db.add(SanXuatNhomLsx(nhom_id=cv.nhom_id, lsx_id=khac.id, order_line_id=khac.order_line_id))
    else:
        tv.nhom_id, tv.la_than_chinh = cv.nhom_id, False
    db.commit()


def test_nhom_hai_cum_chia_theo_so_luong_cum(db, orders, lsx_svc, admin, customer):
    _to, cv, rb = _batch(db, orders, lsx_svc, admin, customer, dat=90, khong_dat=0, cuoi=True)
    _gop_lenh_thu_hai_vao_nhom(db, cv)

    res = _gui(db, cv, rb)
    theo_ten = {d["ten_hang"]: d for d in res["dong"]}
    assert set(theo_ten) == {"Hộp A", "Hộp B"}
    assert theo_ten["Hộp A"]["sl_de_nghi"] == pytest.approx(64.29)     # 90 × 20.000 / 28.000
    assert theo_ten["Hộp B"]["sl_de_nghi"] == pytest.approx(25.71)     # phần dư, tổng khớp 90
    assert theo_ten["Hộp A"]["don_gia_ban"] == 500 and theo_ten["Hộp B"]["don_gia_ban"] == 1_250
    req = db.get(StockRequest, res["request_id"])
    assert {ln.lsx_id for ln in req.lines} == {cv.lsx_id}               # cùng neo thân chính
    # Đọc ngược đủ 90 theo đơn vị KCS ⇒ hết số.
    with pytest.raises(kho.KhongConSoDuGuiKho):
        _gui(db, cv, rb)


def test_hai_cum_cung_ten_ra_cung_ma_thi_gop_mot_dong(db, orders, lsx_svc, admin, customer):
    _to, cv, rb = _batch(db, orders, lsx_svc, admin, customer, dat=90, khong_dat=0, cuoi=True)
    _gop_lenh_thu_hai_vao_nhom(db, cv)
    for ln in _dong_don(db, cv):
        ln.nhom = "Hộp quà"                              # cùng nhãn, khác SL ⇒ hai cụm, một mã
    db.commit()

    res = _gui(db, cv, rb)
    [d] = res["dong"]
    assert d["ten_hang"] == "Hộp quà" and d["sl_de_nghi"] == pytest.approx(90)
    # Bình quân theo số: (64,29 × 500 + 25,71 × 1.250) ÷ 90.
    assert d["don_gia_ban"] == round((64.29 * 500 + 25.71 * 1_250) / 90)


# --- Đơn vị -----------------------------------------------------------------------------------
def _tp_cua_cv(db, cv) -> VatTuInAn:
    lenh = db.get(Lsx, cv.lsx_id)
    order = lenh.order if hasattr(lenh, "order") and lenh.order else None
    from app.models.order import Order
    order = order or db.get(Order, lenh.order_id)
    cum = next(c for c in cum_ban(order) if any(ln.id == lenh.order_line_id for ln in c.dong))
    tp = khai_cum(db, order, cum)
    db.commit()
    return tp


def test_mon_chua_khai_don_vi_bao_loi(db, orders, lsx_svc, admin, customer):
    _to, cv, rb = _batch(db, orders, lsx_svc, admin, customer, dat=90, khong_dat=0, cuoi=True)
    tp = _tp_cua_cv(db, cv)
    tp.don_vi_gia = None
    db.commit()
    with pytest.raises(ValueError, match=f"Thành phẩm {tp.ma} chưa khai đơn vị"):
        _gui(db, cv, rb)
    assert db.query(StockRequest).filter_by(san_xuat_cong_viec_id=cv.id).count() == 0


def test_don_vi_khong_quy_doi_duoc_bao_loi(db, orders, lsx_svc, admin, customer):
    _to, cv, rb = _batch(db, orders, lsx_svc, admin, customer, dat=90, khong_dat=0, cuoi=True)
    tp = _tp_cua_cv(db, cv)
    kien = DonViDo(ma="kien_tp", ten="kiện TP", ho="khac")
    db.add(kien)
    db.flush()
    tp.don_vi_gia = kien.ma
    db.commit()
    with pytest.raises(ValueError, match="Không quy đổi được từ «cái» sang «kiện TP»"):
        _gui(db, cv, rb)


def test_don_vi_quy_doi_duoc_nhan_he_so(db, orders, lsx_svc, admin, customer):
    _to, cv, rb = _batch(db, orders, lsx_svc, admin, customer, dat=90, khong_dat=0, cuoi=True)
    tp = _tp_cua_cv(db, cv)
    cai = db.query(DonViDo).filter(DonViDo.ma == "cai").one()
    chuc = DonViDo(ma="chuc_tp", ten="chục TP", ho="khac")
    db.add(chuc)
    db.flush()
    db.add(DonViQuyDoi(tu_id=chuc.id, den_id=cai.id, he_so=10))
    tp.don_vi_gia = chuc.ma
    db.commit()

    res = _gui(db, cv, rb)
    assert res["dong"][0]["dvt"] == "chuc_tp" and res["dong"][0]["sl_de_nghi"] == 9   # 90 cái = 9 chục
    [d] = kho.dong_nhap_kho_cua_cong_viec(db, [cv.id])[cv.id]
    assert d.sl_da_de_nghi_kcs == pytest.approx(90)     # quy ngược về cái khi tính trần
    with pytest.raises(kho.KhongConSoDuGuiKho):
        _gui(db, cv, rb)


# --- Kho nhận / huỷ ----------------------------------------------------------------------------
def test_kho_nhan_mot_phan_roi_huy_tra_phan_chua_nhan(db, orders, lsx_svc, admin, customer):
    _to, cv, rb = _batch(db, orders, lsx_svc, admin, customer, dat=90, khong_dat=0, cuoi=True)
    r1 = _gui(db, cv, rb)

    _nhan(db, admin, r1["request_id"], 40)
    [d] = kho.dong_nhap_kho_cua_cong_viec(db, [cv.id])[cv.id]
    assert d.sl_da_nhan == 40 and d.cho_kho and d.sl_cho_kho_kcs == pytest.approx(50)
    assert d.nhan_luc is not None and d.nhan_boi == admin.id
    with pytest.raises(kho.KhongConSoDuGuiKho):          # 50 còn đang chờ kho — chưa gửi lại được
        _gui(db, cv, rb)

    _huy_boi_kho(db, r1["request_id"])
    [d] = kho.dong_nhap_kho_cua_cong_viec(db, [cv.id])[cv.id]
    assert not d.con_hieu_luc and d.sl_da_de_nghi == 40 and not d.cho_kho
    r2 = _gui(db, cv, rb)
    assert r2["so_luong"] == 50 and r2["request_id"] != r1["request_id"]


def test_kho_huy_khi_chua_nhan_tra_ca(db, orders, lsx_svc, admin, customer):
    _to, cv, rb = _batch(db, orders, lsx_svc, admin, customer, dat=30, khong_dat=0, cuoi=True)
    r1 = _gui(db, cv, rb)
    _huy_boi_kho(db, r1["request_id"])
    assert _gui(db, cv, rb)["so_luong"] == 30


def test_dieu_chinh_khong_ha_duoi_so_da_gui(db, orders, lsx_svc, admin, customer):
    _to, cv, rb = _batch(db, orders, lsx_svc, admin, customer, dat=80, khong_dat=20, cuoi=True)
    _gui(db, cv, rb)
    with pytest.raises(ValueError, match="không được thấp hơn"):
        kcs.dieu_chinh_ket_qua(db, user=rb["nguoi_kcs"], kcs_batch_id=rb["kcs_batch_id"],
                               so_luong_dat=70, so_luong_khong_dat=30, expected_version=1)
    # Tăng đạt thì luôn được — chỉ chặn hạ dưới số kho đang giữ.
    kcs.dieu_chinh_ket_qua(db, user=rb["nguoi_kcs"], kcs_batch_id=rb["kcs_batch_id"],
                           so_luong_dat=90, so_luong_khong_dat=10, expected_version=1)
    assert _gui(db, cv, rb)["so_luong"] == 10


# --- Real-time + đọc cho Giao hàng -----------------------------------------------------------
def test_phat_su_kien_kho_bao_nguoi_tao(monkeypatch):
    phat, rieng = [], []
    monkeypatch.setattr(kho.hub, "broadcast", lambda ev: phat.append(ev))
    monkeypatch.setattr(kho.hub, "publish", lambda uid, ev: rieng.append((uid, ev)))

    class _Req:
        id, ma, trang_thai, nguoi_tao_id, san_xuat_cong_viec_id = 7, "DNN00007", "partial", 3, 11

    kho.phat_su_kien_kho(_Req(), bao_nguoi_tao=True)
    assert phat == [{"type": "san_xuat_kho_changed", "cong_viec_id": 11, "request_id": 7,
                     "ma": "DNN00007", "trang_thai": "partial"}]
    assert rieng == [(3, {"type": "san_xuat_kho", "cong_viec_id": 11, "request_id": 7,
                          "ma": "DNN00007", "trang_thai": "partial"})]

    class _Khac(_Req):
        san_xuat_cong_viec_id = None

    phat.clear()
    kho.phat_su_kien_kho(_Khac(), bao_nguoi_tao=True)
    assert phat == []                                    # yêu cầu không từ KCS thì im lặng


def test_ton_thanh_pham_cua_nhom_theo_kho(db, orders, lsx_svc, admin, customer):
    _to, cv, rb = _batch(db, orders, lsx_svc, admin, customer, dat=90, khong_dat=0, cuoi=True)
    r = _gui(db, cv, rb)
    o_kho_tp = lambda out: [h for h in out["hang"] if h["kho_ten"] == "Kho thành phẩm"]  # noqa: E731
    assert o_kho_tp(kho.ton_thanh_pham_cua_nhom(db, cv.nhom_id)) == []

    _nhan(db, admin, r["request_id"], 40)
    out = kho.ton_thanh_pham_cua_nhom(db, cv.nhom_id)
    [h] = o_kho_tp(out)
    assert h["ten"] == "Hộp A"
    assert h["so_luong"] == 40 and h["so_toi_da"] == 40
    assert out["da_nhap_kho"] == 40 and out["co_the_giao"] is True and out["da_giao"] == 0
