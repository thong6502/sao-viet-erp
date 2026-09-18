"""Thực hiện sản xuất — Giai đoạn 5/6: TÍCH HỢP tầng router (§16 chốt chặn · §17 · nghiệm thu §21).

Các test service lẻ (test_san_xuat_kcs / _kho / _dong_nhom) đã soi TỪNG luật. File này soi cái
service-lẻ KHÔNG chạm tới: **đường dây hội tụ ở router** — sau một thao tác gỡ điều kiện CUỐI (KCS
kiểm nốt công đoạn cuối / kiểm tới đủ mục tiêu), chốt chặn `_thu_dong_nhom` tự đóng ĐỦ nhóm. Đây
đúng seam mà endpoint gọi (`kiem_cong_doan` → `_thu_dong_nhom`).

Nghiệm thu §21 theo KCS theo lệnh (mg 0306): lỗi KCS tổ chưa bấm "Đã xem" KHÔNG chặn nhập kho phần
ĐẠT, và cũng KHÔNG chặn đóng nhóm — lỗi là thông báo một chiều cho tổ.

Tái dùng NGUYÊN dàn cảnh + helper từ các test G5: `_batch` (một lần kiểm của KCS), `_hoan_thanh_het`
(đánh dấu mọi việc của nhóm xong).
"""
from __future__ import annotations

from app.models.san_xuat import NHOM_DONG_DU
from app.models.stock_request import REQ_APPROVED, StockRequest
from app.repositories.san_xuat_repo import SanXuatRepository
from app.routers.san_xuat import _thu_dong_nhom
from app.services.san_xuat import dong_nhom, kcs, kho

# Fixtures + helper dàn cảnh từ các test G5 (kéo cả cây fixture xếp lịch).
from tests.test_san_xuat_dong_nhom import _hoan_thanh_het, _muc_tieu
from tests.test_san_xuat_kcs import (  # noqa: F401
    _batch,
    _ghi_tot,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
)


def _trang_thai_nhom(db, nhom_id):
    return SanXuatRepository(db).nhom(nhom_id).trang_thai


# --- §16 + §17: chốt chặn router hội tụ khi gỡ điều kiện CUỐI --------------------------------
def test_kcs_kiem_not_cong_doan_cuoi_thi_router_tu_dong_dong_du(db, orders, lsx_svc, admin, customer):
    """Công đoạn cuối chưa kiểm hết là chốt DUY NHẤT còn treo; KCS kiểm nốt phần còn lại → endpoint
    gọi `_thu_dong_nhom` → nhóm tự đóng ĐỦ (không cần ai đóng thiếu bằng tay)."""
    _to, cv, rb = _batch(db, orders, lsx_svc, admin, customer, dat=60, khong_dat=0, cuoi=True, tot=100)
    _muc_tieu(db, cv.nhom_id, 100)
    _hoan_thanh_het(db, cv.nhom_id)
    assert dong_nhom.tu_dong_dong_neu_du(db, nhom_id=cv.nhom_id) is None

    res = kcs.kiem_cong_doan(db, user=rb["nguoi_kcs"], cong_viec_id=cv.id, so_dat=40)
    _thu_dong_nhom(db, res, user=rb["nguoi_kcs"], su_kien="kcs_kiem")
    assert _trang_thai_nhom(db, cv.nhom_id) == NHOM_DONG_DU


def test_kcs_kiem_not_toi_muc_tieu_thi_router_tu_dong_dong_du(db, orders, lsx_svc, admin, customer):
    """Hụt mục tiêu là chốt DUY NHẤT còn treo (việc đã xong, KCS đã kiểm hết số tốt đang có): tổ ghi
    thêm mẻ, KCS kiểm nốt tới mục tiêu → endpoint gọi `_thu_dong_nhom` → nhóm tự đóng ĐỦ."""
    _to, cv, rb = _batch(db, orders, lsx_svc, admin, customer, dat=60, khong_dat=0, cuoi=True)
    _muc_tieu(db, cv.nhom_id, 100)
    _hoan_thanh_het(db, cv.nhom_id)
    _thu_dong_nhom(db, {"nhom_id": cv.nhom_id}, user=rb["nguoi_kcs"], su_kien="kcs_kiem")
    assert _trang_thai_nhom(db, cv.nhom_id) != NHOM_DONG_DU           # đạt 60/100 → chưa đủ

    _ghi_tot(db, cv, 40)
    res = kcs.kiem_cong_doan(db, user=rb["nguoi_kcs"], cong_viec_id=cv.id, so_dat=40)
    _thu_dong_nhom(db, res, user=rb["nguoi_kcs"], su_kien="kcs_kiem")
    assert _trang_thai_nhom(db, cv.nhom_id) == NHOM_DONG_DU


# --- Nghiệm thu §21: lỗi chưa xem không chặn nhập kho lẫn đóng nhóm ---------------------------
def test_loi_chua_xem_khong_chan_nhap_kho_phan_dat_va_dong_nhom(db, orders, lsx_svc, admin, customer):
    _to, cv, rb = _batch(db, orders, lsx_svc, admin, customer, cuoi=True)  # đạt 90, lỗi 10
    assert kcs.loi_cho_xem(db, [cv.department_id])
    _muc_tieu(db, cv.nhom_id, 90)
    _hoan_thanh_het(db, cv.nhom_id)

    yc = kho.tao_yeu_cau_nhap_kho_cong_doan(db, user=rb["nguoi_kcs"], cong_viec_id=cv.id)
    assert yc["so_luong"] == 90
    assert db.get(StockRequest, yc["request_id"]).trang_thai == REQ_APPROVED

    assert dong_nhom.tu_dong_dong_neu_du(db, nhom_id=cv.nhom_id) is not None
    assert _trang_thai_nhom(db, cv.nhom_id) == NHOM_DONG_DU
