"""Lô GỐC qua điều chuyển (design nhập kho thành phẩm §5).

Lô nhập từ yêu cầu là gốc của chính nó (`lo_goc_id` trống). Điều chuyển ghi lô gốc của lô nguồn lên dòng
phiếu nhập đích, ghi sổ chép sang lô mới — A → B → C vẫn trỏ về MỘT lô gốc, nên lô ở kho cuối vẫn đọc
được lệnh / đơn / khách / giá bán mà không chép hai thứ đó qua mỗi lần chuyển.
"""
from __future__ import annotations

from app.models.kho_hang import KhoHang
from app.models.lsx import Lsx
from app.models.order import Order
from app.models.stock_lot import StockLot
from app.models.stock_request import StockRequest
from app.models.stock_voucher import StockVoucherLine
from app.repositories.stock_lot_repo import StockLotRepository, goc_cua
from app.routers.kho_voucher import get_service as voucher_service
from tests.test_san_xuat_kcs import (  # noqa: F401
    _batch,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
)
from tests.test_san_xuat_nhap_kho_tp import _gui, _nhan


def _kho(db, ma: str) -> KhoHang:
    k = db.query(KhoHang).filter_by(ma=ma).one_or_none()
    if k is None:
        k = KhoHang(ma=ma, ten=f"Kho {ma}")
        db.add(k)
        db.commit()
    return k


def _chuyen(db, admin, tp_id: int, tu: KhoHang, den: KhoHang, so_luong: float) -> list[StockLot]:
    """Ấn điều chuyển rồi kho đích ghi sổ phiếu nhập dựng sẵn — trả các lô mới ở kho đích."""
    svc = voucher_service(db)
    res = svc.dieu_chuyen(user=admin, kho_nguon_id=tu.id, kho_den_id=den.id,
                          items=[{"hang_loai": "vat_tu", "hang_id": tp_id, "so_luong": so_luong}])
    svc.post(res["phieu_nhap"].id, admin)
    ids = [ln.lot_id for ln in db.query(StockVoucherLine).filter_by(voucher_id=res["phieu_nhap"].id)]
    return [db.get(StockLot, i) for i in ids]


def test_dieu_chuyen_a_b_c_tro_ve_mot_lo_goc_va_doc_dung_nguon(db, orders, lsx_svc, admin, customer):
    _to, cv, rb = _batch(db, orders, lsx_svc, admin, customer, dat=90, khong_dat=0, cuoi=True)
    r = _gui(db, cv, rb)
    a, b, c = _kho(db, "KHO-TP"), _kho(db, "KHO-B"), _kho(db, "KHO-C")
    _nhan(db, admin, r["request_id"], 90)

    tp_id = db.get(StockRequest, r["request_id"]).lines[0].hang_id
    [goc] = db.query(StockLot).filter_by(kho_id=a.id, hang_loai="vat_tu", hang_id=tp_id).all()
    assert goc.lo_goc_id is None and goc_cua(goc) == goc.id

    [o_b] = _chuyen(db, admin, tp_id, a, b, 30)
    [o_c] = _chuyen(db, admin, tp_id, b, c, 10)
    assert o_b.lo_goc_id == goc.id
    assert o_c.lo_goc_id == goc.id                        # không trỏ về lô trung gian ở B
    assert float(o_c.sl_con_lai) == 10 and float(o_b.sl_con_lai) == 20 and float(goc.sl_con_lai) == 60

    lenh = db.get(Lsx, cv.lsx_id)
    don = db.get(Order, lenh.order_id)
    nguon = StockLotRepository(db).nguon_lo([goc.id, o_b.id, o_c.id])
    for lot_id in (goc.id, o_b.id, o_c.id):
        n = nguon[lot_id]
        assert n["lo_goc_id"] == goc.id and n["tu_kcs"] is True
        assert n["lsx_id"] == lenh.id and n["lsx_ma"] == lenh.ma
        assert n["order_id"] == don.id and n["order_ma"] == don.order_no
        assert n["customer_id"] == customer.id and n["khach_hang"] == customer.name
        assert n["don_gia_ban"] == 500


def test_lo_khong_tu_kcs_thi_nguon_trong(db, orders, lsx_svc, admin, customer):
    # Lô dựng sẵn của fixture xếp lịch không có phiếu nhập nào ⇒ không truy được nguồn.
    _batch(db, orders, lsx_svc, admin, customer, dat=10, khong_dat=0, cuoi=True)
    lot = db.query(StockLot).filter(StockLot.ma_lo.like("LOT-XL-%")).first()
    assert lot is not None
    n = StockLotRepository(db).nguon_lo([lot.id])[lot.id]
    assert n == {"lo_goc_id": lot.id, "lsx_id": None, "lsx_ma": None, "order_id": None, "order_ma": None,
                 "customer_id": None, "khach_hang": None, "don_gia_ban": None, "tu_kcs": False}
    assert StockLotRepository(db).nguon_lo([]) == {}
