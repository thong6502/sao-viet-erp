"""Nhập kho thành phẩm phải chọn KHO ĐÍCH (31/08/2026).

Không có kho đích thì lot thành phẩm là một con số lơ lửng: không tra được tồn theo kho, không lập
được phiếu xuất giao. Ba luật soi ở đây:
  · BẮT BUỘC chọn — gọi `kho_xac_nhan_nhap` mà không truyền `kho_id` là hỏng ngay ở cổng;
  · kho phải CÓ THẬT — id lạ bị chặn bằng lỗi nghiệp vụ, không đẻ lot mồ côi;
  · lot GHI LẠI kho đã nhận nó — nhập nhiều lần vào nhiều kho thì mỗi lot mang kho của nó
    (bảng lot là CHỈ-THÊM nên đây là chỗ duy nhất giữ được sự thật đó).

Dàn cảnh (đơn → SX → phát hành → batch KCS đạt một phần) tái dùng `_batch` của test KCS — đúng khuôn
`tests/test_san_xuat_kho.py`. Gate quyền `kho` nằm ở ROUTER, nên ở tầng service người xác nhận là
`admin` như mọi test cùng lát.
"""
from __future__ import annotations

import pytest

from app.models.kho_hang import KhoHang
from app.models.san_xuat_kho import SanXuatKhoLot
from app.services.san_xuat import kho

# Fixtures + helper batch KCS đạt một phần (nhan=100, dat=90, khong_dat=10).
from tests.test_san_xuat_kcs import (  # noqa: F401
    _batch,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
)


def _kho(db, ma: str, ten: str) -> KhoHang:
    k = KhoHang(ma=ma, ten=ten)
    db.add(k)
    db.commit()
    return k


@pytest.fixture()
def kho_a(db):                                    # noqa: F811 — fixture `db` nhận qua import
    return _kho(db, "KHO-TPA", "Kho thành phẩm A")


@pytest.fixture()
def kho_b(db):                                    # noqa: F811
    return _kho(db, "KHO-TPB", "Kho thành phẩm B")


@pytest.fixture()
def yc_nhap_kho(db, orders, lsx_svc, admin, customer):   # noqa: F811
    """Một yêu cầu nhập kho thành phẩm 10 đơn vị, đang chờ kho nhận."""
    _to, _cv, rb = _batch(db, orders, lsx_svc, admin, customer)
    return kho.tao_yeu_cau_nhap_thanh_pham(
        db, user=admin, kcs_batch_id=rb["kcs_batch_id"], so_luong=10)


def test_thieu_kho_dich_bi_chan(db, yc_nhap_kho, admin):   # noqa: F811
    """Không truyền kho đích ⇒ chặn ngay, KHÔNG âm thầm đẻ lot không kho."""
    with pytest.raises((ValueError, TypeError)):
        kho.kho_xac_nhan_nhap(db, user=admin, yc_id=yc_nhap_kho["yc_id"], so_luong=10)


def test_kho_khong_ton_tai_bi_chan(db, yc_nhap_kho, admin):   # noqa: F811
    with pytest.raises(ValueError, match="[Kk]ho"):
        kho.kho_xac_nhan_nhap(
            db, user=admin, yc_id=yc_nhap_kho["yc_id"], so_luong=10, kho_id=999_999)


def test_lot_mang_kho_da_nhan(db, yc_nhap_kho, admin, kho_a, kho_b):   # noqa: F811
    """Nhận hai lần vào hai kho khác nhau ⇒ hai lot, mỗi lot mang đúng kho đã nhận nó."""
    kho.kho_xac_nhan_nhap(
        db, user=admin, yc_id=yc_nhap_kho["yc_id"], so_luong=6, kho_id=kho_a.id)
    kho.kho_xac_nhan_nhap(
        db, user=admin, yc_id=yc_nhap_kho["yc_id"], so_luong=4, kho_id=kho_b.id)

    lots = (
        db.query(SanXuatKhoLot)
        .filter_by(nhap_kho_yc_id=yc_nhap_kho["yc_id"])
        .order_by(SanXuatKhoLot.id)
        .all()
    )
    assert [l.kho_id for l in lots] == [kho_a.id, kho_b.id]
    assert [float(l.so_luong) for l in lots] == [6.0, 4.0]


def test_mat_doc_phoi_kho_cua_tung_lot(db, yc_nhap_kho, admin, kho_a, kho_b):   # noqa: F811
    """Panel §14 phải đọc được kho của từng lot — không thì UI vẫn là con số lơ lửng."""
    r1 = kho.kho_xac_nhan_nhap(
        db, user=admin, yc_id=yc_nhap_kho["yc_id"], so_luong=6, kho_id=kho_a.id)
    kho.kho_xac_nhan_nhap(
        db, user=admin, yc_id=yc_nhap_kho["yc_id"], so_luong=4, kho_id=kho_b.id)

    nhom_id = r1["nhom_id"]
    ct = kho.chi_tiet_kho_nhom(db, nhom_id)
    lots = sorted((l for l in ct["lot"] if l["loai_hang"] == "thanh_pham"), key=lambda l: l["id"])
    assert [l["kho_id"] for l in lots] == [kho_a.id, kho_b.id]
    assert [l["kho_ten"] for l in lots] == ["Kho thành phẩm A", "Kho thành phẩm B"]


def test_kho_ngung_dung_bi_chan(db, yc_nhap_kho, admin, kho_a):   # noqa: F811
    """Kho ngừng dùng là xoá MỀM — bản ghi vẫn nằm đó. Chỉ soi "có tồn tại" thì hàng chui vào kho
    đã ngừng dùng rồi biến mất khỏi mọi màn kho có lọc `active`.

    Ca thật: 8h thủ kho mở màn (ô chọn kho nạp MỘT lần), 9h admin bấm Ngừng dùng kho đó, 9h30 thủ
    kho vẫn thấy nó trong ô chọn cũ và bấm xác nhận."""
    kho_a.active = False
    db.commit()
    with pytest.raises(ValueError, match="ngừng dùng"):
        kho.kho_xac_nhan_nhap(
            db, user=admin, yc_id=yc_nhap_kho["yc_id"], so_luong=10, kho_id=kho_a.id)


def test_ten_kho_van_doc_duoc_sau_khi_kho_ngung_dung(db, yc_nhap_kho, admin, kho_a):   # noqa: F811
    """Mặt ĐỌC thì NGƯỢC LẠI: kho xoá mềm vẫn phải trả tên, không thì lot cũ mất tên chỗ cất.

    Chốt chặn `active` chỉ nằm ở đường GHI (`kho_nhan_duoc`) — đừng "sửa cho nhất quán" bằng cách
    lọc `active` trong `ten_kho_theo_ids`."""
    r = kho.kho_xac_nhan_nhap(
        db, user=admin, yc_id=yc_nhap_kho["yc_id"], so_luong=10, kho_id=kho_a.id)
    kho_a.active = False
    db.commit()

    ct = kho.chi_tiet_kho_nhom(db, r["nhom_id"])
    lot = next(l for l in ct["lot"] if l["id"] == r["lot_id"])
    assert lot["kho_ten"] == "Kho thành phẩm A"


# --- Đường dây HTTP (§14.1) --------------------------------------------------------------------
# Tầng service đã có 6 test ở trên; ở đây soi đúng phần router: `kho_id` có đi từ thân yêu cầu vào
# service không, và schema có thật sự BẮT BUỘC nó không. Không có bài này thì ai nới
# `KhoXacNhanNhapIn.kho_id` thành `int | None = None` cả bộ vẫn xanh.
# `admin` (Giám đốc) có `kho:create` nên qua được cổng RBAC — bit `san_xuat:assign_work` mà vai này
# THIẾU không liên quan tới endpoint này.
def _dang_nhap(c) -> dict[str, str]:
    tok = c.post("/api/auth/login",
                 json={"username": "admin", "password": "admin123"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_route_thieu_kho_id_tra_422(db, yc_nhap_kho, admin):   # noqa: F811
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        r = c.post(f"/api/san-xuat/kho/yeu-cau/{yc_nhap_kho['yc_id']}/xac-nhan",
                   json={"so_luong": 10}, headers=_dang_nhap(c))
    assert r.status_code == 422


def test_route_co_kho_id_tra_200_va_lot_mang_kho(db, yc_nhap_kho, admin, kho_a):   # noqa: F811
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        r = c.post(f"/api/san-xuat/kho/yeu-cau/{yc_nhap_kho['yc_id']}/xac-nhan",
                   json={"so_luong": 10, "kho_id": kho_a.id}, headers=_dang_nhap(c))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kho_id"] == kho_a.id          # schema Out không nuốt field

    db.expire_all()
    lot = db.get(SanXuatKhoLot, body["lot_id"])
    assert lot is not None and lot.kho_id == kho_a.id
