"""Thực hiện sản xuất — Giai đoạn 5/6: TÍCH HỢP tầng router (§16 chốt chặn · §17 · nghiệm thu §21).

Các test service lẻ (test_san_xuat_kcs / _kho / _dong_nhom) đã soi TỪNG luật. File này soi cái
service-lẻ KHÔNG chạm tới: **đường dây hội tụ ở router** — sau một thao tác gỡ điều kiện CUỐI
(phản hồi lỗi KCS, kho xác nhận BTP), chốt chặn `_thu_dong_nhom` tự đóng ĐỦ nhóm. Đây đúng seam mà
endpoint gọi (`phan_hoi_loi` → `_thu_dong_nhom`; `kho_xac_nhan_btp` → `_thu_dong_nhom`).

Nghiệm thu §21 (dòng khó nhất): "lỗi KCS chờ phản hồi KHÔNG chặn nhập kho phần ĐẠT, NHƯNG vẫn
chặn đóng nhóm" — hai đường (nhập kho thành phẩm vs cổng đóng nhóm) độc lập nhau.

Tái dùng NGUYÊN dàn cảnh + helper từ các test G5 (không dựng cảnh mới): `_batch` (batch KCS đạt một
phần 100/90/10), `_hoan_thanh_het` (đánh dấu mọi việc của nhóm xong), `_ly_do`/`_to_chiu`/`_anh`.
"""
from __future__ import annotations

from app.models.san_xuat import NHOM_DONG_DU
from app.models.san_xuat_kcs import TN_CHAP_NHAN
from app.models.san_xuat_kho import PL_NHAP_BTP, YC_CHO_KHO
from app.repositories.san_xuat_repo import SanXuatRepository
from app.routers.san_xuat import _thu_dong_nhom
from app.services.san_xuat import dong_nhom, kcs, kho

# Fixtures + helper dàn cảnh từ các test G5 (kéo cả cây fixture xếp lịch).
from tests.test_san_xuat_dong_nhom import _hoan_thanh_het
from tests.test_san_xuat_kcs import (  # noqa: F401
    _anh,
    _batch,
    _ly_do,
    _to_chiu,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
)


def _trang_thai_nhom(db, nhom_id):
    return SanXuatRepository(db).nhom(nhom_id).trang_thai


# --- §16 + §17: chốt chặn router hội tụ khi gỡ điều kiện CUỐI --------------------------------
def test_phan_hoi_loi_la_chot_cuoi_thi_router_tu_dong_dong_du(db, orders, lsx_svc, admin, customer):
    """Lỗi KCS chờ là chốt DUY NHẤT còn treo; tổ bị yêu cầu phản hồi CHẤP NHẬN → endpoint gọi
    `_thu_dong_nhom` → nhóm tự đóng ĐỦ (không cần trưởng KCS đóng tay)."""
    _to, cv, rb = _batch(db, orders, lsx_svc, admin, customer)
    _hoan_thanh_het(db, cv.nhom_id)
    ld = _ly_do(db)
    to2, tt2 = _to_chiu(db)
    loi = kcs.ghi_loi(
        db, user=admin, kcs_batch_id=rb["kcs_batch_id"], nhom_loi_id=ld.id,
        to_chiu_id=to2.id, anh=_anh(),
    )

    # Còn lỗi chờ → chưa hội đủ, chốt chặn không đóng.
    assert dong_nhom.tu_dong_dong_neu_du(db, nhom_id=cv.nhom_id) is None

    ph = kcs.phan_hoi_loi(db, user=tt2, loi_id=loi["loi_id"], chap_nhan=True)
    assert ph["trang_thai"] == TN_CHAP_NHAN
    # Router chốt chặn (đúng nơi endpoint phan_hoi_loi gọi) lần ra nhóm qua cong_viec_id.
    _thu_dong_nhom(db, ph, user=tt2, su_kien="phan_hoi_loi_kcs")
    assert _trang_thai_nhom(db, cv.nhom_id) == NHOM_DONG_DU


def test_kho_xac_nhan_btp_la_chot_cuoi_thi_router_tu_dong_dong_du(db, orders, lsx_svc, admin, customer):
    """BTP dư chờ kho là chốt DUY NHẤT còn treo; kho xác nhận nhận → endpoint gọi `_thu_dong_nhom`
    → nhóm tự đóng ĐỦ."""
    _to, cv, rb = _batch(db, orders, lsx_svc, admin, customer)
    _hoan_thanh_het(db, cv.nhom_id)
    lb = kho.phan_loai_btp_du(
        db, user=admin, cong_viec_id=cv.id, so_luong=5, phan_loai=PL_NHAP_BTP
    )
    assert lb["cho_kho"] is True

    assert dong_nhom.tu_dong_dong_neu_du(db, nhom_id=cv.nhom_id) is None  # BTP chờ kho → chặn

    xn = kho.kho_xac_nhan_btp(db, user=admin, lot_id=lb["lot_id"])
    assert xn["nhom_id"] == cv.nhom_id
    _thu_dong_nhom(db, xn, user=admin, su_kien="kho_xac_nhan_btp")
    assert _trang_thai_nhom(db, cv.nhom_id) == NHOM_DONG_DU


def test_chot_chan_la_cong_VA_go_mot_chot_chua_du(db, orders, lsx_svc, admin, customer):
    """Hai chốt cùng treo (lỗi KCS + BTP chờ kho): gỡ MỘT cái, `_thu_dong_nhom` KHÔNG được đóng non;
    chỉ khi gỡ NỐT cái còn lại lần chốt chặn kế mới đóng ĐỦ."""
    _to, cv, rb = _batch(db, orders, lsx_svc, admin, customer)
    _hoan_thanh_het(db, cv.nhom_id)
    ld = _ly_do(db)
    to2, tt2 = _to_chiu(db)
    loi = kcs.ghi_loi(
        db, user=admin, kcs_batch_id=rb["kcs_batch_id"], nhom_loi_id=ld.id,
        to_chiu_id=to2.id, anh=_anh(),
    )
    lb = kho.phan_loai_btp_du(
        db, user=admin, cong_viec_id=cv.id, so_luong=5, phan_loai=PL_NHAP_BTP
    )

    # Gỡ chốt lỗi trước; BTP vẫn treo → chốt chặn KHÔNG đóng non.
    ph = kcs.phan_hoi_loi(db, user=tt2, loi_id=loi["loi_id"], chap_nhan=True)
    _thu_dong_nhom(db, ph, user=tt2, su_kien="phan_hoi_loi_kcs")
    assert _trang_thai_nhom(db, cv.nhom_id) != NHOM_DONG_DU

    # Gỡ nốt BTP → lần chốt chặn kế đóng ĐỦ.
    xn = kho.kho_xac_nhan_btp(db, user=admin, lot_id=lb["lot_id"])
    _thu_dong_nhom(db, xn, user=admin, su_kien="kho_xac_nhan_btp")
    assert _trang_thai_nhom(db, cv.nhom_id) == NHOM_DONG_DU


# --- Nghiệm thu §21: hai đường (nhập kho vs đóng nhóm) độc lập -------------------------------
def test_loi_kcs_cho_khong_chan_nhap_kho_phan_dat_nhung_chan_dong_nhom(db, orders, lsx_svc, admin, customer):
    """§21: lỗi KCS chờ phản hồi KHÔNG chặn KCS tạo yêu cầu nhập kho phần ĐẠT (90), NHƯNG vẫn chặn
    cổng đóng nhóm — điều kiện `het_loi_kcs_cho` chưa đạt."""
    _to, cv, rb = _batch(db, orders, lsx_svc, admin, customer)  # dat = 90
    _hoan_thanh_het(db, cv.nhom_id)
    ld = _ly_do(db)
    to2, tt2 = _to_chiu(db)
    kcs.ghi_loi(
        db, user=admin, kcs_batch_id=rb["kcs_batch_id"], nhom_loi_id=ld.id,
        to_chiu_id=to2.id, anh=_anh(),
    )

    # Đường nhập kho phần ĐẠT vẫn chạy: lỗi (số không đạt) không liên quan số đạt.
    yc = kho.tao_yeu_cau_nhap_thanh_pham(
        db, user=admin, kcs_batch_id=rb["kcs_batch_id"], so_luong=90
    )
    assert yc["trang_thai"] == YC_CHO_KHO

    # Nhưng cổng đóng nhóm vẫn đóng: còn lỗi KCS chờ.
    assert dong_nhom.tu_dong_dong_neu_du(db, nhom_id=cv.nhom_id) is None
    dk = dong_nhom.dieu_kien_dong_nhom(db, cv.nhom_id)
    het_loi = next(d for d in dk["dieu_kien"] if d["ma"] == "het_loi_kcs_cho")
    assert het_loi["dat"] is False and dk["du_dong_du"] is False
