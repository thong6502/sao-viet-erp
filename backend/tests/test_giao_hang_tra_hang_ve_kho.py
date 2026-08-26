"""Trả hàng về kho phải VÀO SỔ (PRD `prd-giao-hang-mot-yeu-cau-mot-chuyen.md` §3).

Trước 22/08/2026 `kho_nhan_lai_hang` chỉ đổi nhãn trạng thái, KHÔNG lập phiếu nhập — hàng đã xuất
cho chuyến hỏng thì sổ kho vĩnh viễn coi là đã xuất, dù xe chở về và thủ kho đã cầm hàng.

Lỗi đó chưa lộ vì đường "chờ giao lại" giữ hàng trên xe rồi giao tiếp bằng chuyến mới, không xuất
kho lần hai. Bỏ đường đó (mô hình một-yêu-cầu-một-chuyến) là lộ ngay: mỗi lần giao lại trừ kho
thêm một lần nữa cho cùng một lô hàng.

Bộ này khoá bốn thứ, đúng nghiệm thu #19–#22 của PRD.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.models.stock_request import REQ_NHAP, REQ_XUAT, StockRequest
from tests.test_giao_hang_api import (
    _admin,
    _di_toi_dang_giao,
    _don_da_chot,
    _len_kh,
    _tai_xe,
    _tao_yc,
)


def _chuyen(client, h, *, suffix: str, qty: int = 100):
    """Đơn → yêu cầu giao → kế hoạch → xuất kho → tài xế đang giao. Trả `(trip_id, order_line_id)`."""
    oid, lid = _don_da_chot(suffix=suffix, qty=qty)
    yc = _tao_yc(client, h, oid, lid, qty=qty)
    r = _len_kh(client, h, yc["id"], _tai_xe(f"TX-{suffix}"))
    assert r.status_code == 201, r.text
    trip = r.json()["trip"]["id"]
    _di_toi_dang_giao(client, h, trip)
    return trip, lid


def _ket_qua(client, h, trip, **body):
    r = client.post(f"/api/giao-hang/trips/{trip}/ket-qua",
                    json={"km": 12, **body}, headers=h)
    assert r.status_code == 200, r.text
    return r


def _yc_kho(trip_id: int, loai: str) -> StockRequest | None:
    db = SessionLocal()
    try:
        return (db.query(StockRequest)
                .filter(StockRequest.delivery_trip_id == trip_id, StockRequest.loai == loai)
                .order_by(StockRequest.id.desc()).first())
    finally:
        db.close()


def _so_tra_ve(trip_id: int) -> dict[tuple[str, int], float]:
    yc = _yc_kho(trip_id, REQ_NHAP)
    if yc is None:
        return {}
    db = SessionLocal()
    try:
        yc = db.query(StockRequest).filter(StockRequest.id == yc.id).one()
        return {(l.hang_loai, l.hang_id): float(l.sl_de_nghi) for l in yc.lines}
    finally:
        db.close()


# =============================================================================================
# #19 — thất bại: trả TOÀN BỘ
# =============================================================================================
def test_19_GIAO_THAT_BAI_tra_lai_TOAN_BO_vao_so_kho(client):
    """⭐ Lý do tồn tại của cả bước này: hàng chở về mà sổ kho vẫn ghi đã xuất là kho sai vĩnh viễn."""
    h = _admin(client)
    trip, _lid = _chuyen(client, h, suffix="tv1", qty=100)
    _ket_qua(client, h, trip, ket_qua="that_bai",
             ly_do_that_bai="Khach dong cua", huong_xu_ly="tra_ve")

    assert _yc_kho(trip, REQ_NHAP) is None, "chưa nhận lại mà đã đẻ phiếu nhập"
    r = client.post(f"/api/giao-hang/trips/{trip}/da-tra-hang", headers=h)
    assert r.status_code == 200, r.text

    yc_xuat = _yc_kho(trip, REQ_XUAT)
    assert _so_tra_ve(trip) == {("vat_tu", _hang_id(yc_xuat)): 100.0}


def _hang_id(yc: StockRequest) -> int:
    db = SessionLocal()
    try:
        return db.query(StockRequest).filter(StockRequest.id == yc.id).one().lines[0].hang_id
    finally:
        db.close()


# =============================================================================================
# #20 — giao thiếu: chỉ trả PHẦN THỪA
# =============================================================================================
def test_20_GIAO_THIEU_chi_tra_lai_PHAN_THUA(client):
    """⭐ Giao 80/100 thì chỉ 20 quay về. Trả nguyên 100 là thổi phồng tồn kho — kho có 20 trên
    giấy mà thực tế 80 đã ở chỗ khách."""
    h = _admin(client)
    trip, lid = _chuyen(client, h, suffix="tv2", qty=100)
    _ket_qua(client, h, trip, ket_qua="giao_thieu", nguoi_nhan_thuc_te="Chi Lan",
             so_thuc_nhan=[{"order_line_id": lid, "qty": 80}])

    r = client.post(f"/api/giao-hang/trips/{trip}/da-tra-hang", headers=h)
    assert r.status_code == 200, r.text
    assert list(_so_tra_ve(trip).values()) == [20.0], _so_tra_ve(trip)


# =============================================================================================
# #21 — không lập được phiếu thì KHÔNG đổi trạng thái
# =============================================================================================
def test_21_GIAO_DU_thi_khong_co_gi_de_tra(client):
    """Giao đủ ⇒ không đi qua bước trả hàng, và cũng không đẻ phiếu nhập rỗng."""
    h = _admin(client)
    trip, _lid = _chuyen(client, h, suffix="tv3", qty=100)
    _ket_qua(client, h, trip, ket_qua="thanh_cong", nguoi_nhan_thuc_te="Chi Lan")

    r = client.post(f"/api/giao-hang/trips/{trip}/da-tra-hang", headers=h)
    assert r.status_code == 400, r.text        # chuyến không ở trạng thái đang trả hàng
    assert _yc_kho(trip, REQ_NHAP) is None


# =============================================================================================
# #22 — bấm hai lần không nhập kho hai lần
# =============================================================================================
def test_22_BAM_HAI_LAN_khong_nhap_kho_hai_lan(client):
    """⭐ Bấm nhầm hai lần là tồn kho tự nhân đôi — và không ai thấy, vì phiếu nào cũng hợp lệ."""
    h = _admin(client)
    trip, _lid = _chuyen(client, h, suffix="tv4", qty=100)
    _ket_qua(client, h, trip, ket_qua="that_bai",
             ly_do_that_bai="Khach doi hang", huong_xu_ly="tra_ve")

    assert client.post(f"/api/giao-hang/trips/{trip}/da-tra-hang", headers=h).status_code == 200
    lan_hai = client.post(f"/api/giao-hang/trips/{trip}/da-tra-hang", headers=h)
    assert lan_hai.status_code == 400, lan_hai.text

    # Bất biến thật sự cần khoá là SỐ PHIẾU, không phải câu báo: chặn bằng cổng nào cũng được,
    # miễn là kho không bị cộng hàng hai lần.
    db = SessionLocal()
    try:
        n = (db.query(StockRequest)
             .filter(StockRequest.delivery_trip_id == trip, StockRequest.loai == REQ_NHAP)
             .count())
    finally:
        db.close()
    assert n == 1, f"đẻ ra {n} phiếu nhập trả hàng cho một chuyến"


def test_yeu_cau_XUAT_cua_chuyen_khong_bi_lan_sang_phieu_NHAP(client):
    """⭐ Một chuyến nay treo HAI yêu cầu cùng `delivery_trip_id`. Hàm tra "yêu cầu xuất của
    chuyến" mà không lọc loại thì sau khi trả hàng nó trả nhầm phiếu nhập — mọi chỗ hỏi "chuyến
    này đã gửi kho chưa" đều nhận sai mã."""
    h = _admin(client)
    trip, _lid = _chuyen(client, h, suffix="tv5", qty=100)
    ma_xuat = _yc_kho(trip, REQ_XUAT).ma
    _ket_qua(client, h, trip, ket_qua="that_bai",
             ly_do_that_bai="Khach tu choi", huong_xu_ly="tra_ve")
    client.post(f"/api/giao-hang/trips/{trip}/da-tra-hang", headers=h)

    db = SessionLocal()
    try:
        from app.repositories.stock_request_repo import StockRequestRepository
        repo = StockRequestRepository(db)
        assert repo.tim_theo_delivery_trip(trip, loai=REQ_XUAT).ma == ma_xuat
        assert repo.tim_theo_delivery_trip(trip, loai=REQ_NHAP).ma != ma_xuat
    finally:
        db.close()
