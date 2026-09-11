"""Bốn chỗ TIÊU THỤ lịch phải đọc được lệnh xếp ở màn 3.

Màn 3 lưu MỘT mốc cho cả lệnh và không đẻ dòng `xep_lich_cong_doan` nào. Bốn nơi dưới đây trước
giờ chỉ biết bảng lịch cũ, nên nếu không nối thì mỗi nơi hỏng một kiểu ÂM THẦM:

- giữ chỗ vật tư: lệnh bị coi là chưa qua cửa kế hoạch → nhả chỗ đã giữ;
- kế hoạch vật tư: "ngày cần" rơi về suy đoán từ hạn SX thay vì giờ bước thật;
- màn Máy: máy đang chạy hiện "rảnh" — sai theo hướng nguy hiểm nhất, người ta đẩy thêm việc vào;
- bàn tổ: thẻ việc ra TRỐNG GIỜ, tổ không xếp được thứ tự làm.

Không cái nào trong bốn cái đó làm test khác đỏ, nên phải có bộ riêng chốt lại.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.repositories.xep_lich_lenh_repo import XepLichLenhRepository
from app.services.xep_lich_3 import XepLich3Service
from app.services.xep_lich_3.moc import lsx_da_xep, moc_theo_buoc
from tests.test_xep_lich_service import (  # noqa: F401
    _hai_lsx_san_sang,
    _khai_giay_len_buoc_in,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
)

MOC = datetime(2026, 9, 11, 8, 0)


@pytest.fixture
def svc3(db):
    return XepLich3Service(db, XepLichLenhRepository(db))


@pytest.fixture
def lenh(db, orders, lsx_svc, admin, customer):
    ds = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    _khai_giay_len_buoc_in(db, ds[0].id)
    db.commit()
    return ds[0]


def test_cau_moc_tra_ve_tung_buoc(db, svc3, lenh):
    svc3.dat_moc(lenh.id, MOC)
    assert lsx_da_xep(db) == {lenh.id}
    moc = moc_theo_buoc(db, [lenh.id])
    assert moc, "lệnh đã xếp mà cầu không trả mốc bước nào"
    assert all(kt >= bd for bd, kt in moc.values())


def test_lenh_chua_xep_thi_cau_im_lang(db, lenh):
    """Không có dòng ⇒ không có mốc: chỗ gọi rơi về đường cũ, không phải nhận số bịa."""
    assert lsx_da_xep(db) == set()
    assert moc_theo_buoc(db, [lenh.id]) == {}


def test_giu_cho_khong_nha_lenh_xep_o_man_3(db, svc3, lenh):
    from app.repositories.giu_cho_repo import GiuChoRepository

    assert lenh.id not in GiuChoRepository(db).chu_the_da_xep_lich()[0]
    svc3.dat_moc(lenh.id, MOC)
    assert lenh.id in GiuChoRepository(db).chu_the_da_xep_lich()[0]


def test_ke_hoach_vat_tu_lay_gio_buoc_tu_man_3(db, svc3, lenh):
    from app.routers.ke_hoach_vat_tu import get_service

    svc3.dat_moc(lenh.id, MOC)
    kh = get_service(db)               # dựng đúng bộ phụ thuộc của màn thật, không bịa bản giả
    kh._nap_lich({lenh.id}, set())
    assert kh._start_buoc, "lệnh đã xếp ở màn 3 mà bảng cân đối không thấy giờ bước nào"
    buoc_ids = set(moc_theo_buoc(db, [lenh.id]))
    assert buoc_ids <= set(kh._start_buoc)


def test_man_may_thay_may_dang_ban(db, svc3, lenh):
    """Bước IN có máy — giữa khoảng chạy của nó, cột Trạng thái phải nói máy đang bận."""
    from app.services.may_trang_thai import lenh_dang_chay

    svc3.dat_moc(lenh.id, MOC)
    moc = moc_theo_buoc(db, [lenh.id])
    may_ids = [c.may_id for c in lenh.cong_doans if c.may_id]
    assert may_ids, "lệnh mẫu không có bước nào gán máy — test mất ý nghĩa"

    trong = None
    for c in lenh.cong_doans:
        if c.may_id and c.id in moc:
            bd, kt = moc[c.id]
            if kt > bd:
                trong = (c.may_id, bd + (kt - bd) / 2)
                break
    assert trong, "không bước máy nào có khoảng chạy > 0"
    may_id, giua = trong
    dang = lenh_dang_chay(db, may_ids, giua)
    assert may_id in dang and dang[may_id]["ma"] == lenh.ma

    # Trước mốc bắt đầu thì máy phải rảnh — nếu không là cầu đang trả khoảng vô hạn.
    assert lenh_dang_chay(db, may_ids, MOC - timedelta(days=30)) == {}


def test_the_viec_duoi_xuong_co_gio_du_kien(db, svc3, lenh, admin):
    """Chốt cuối: phát hành từ màn 3 xong, bàn tổ phải thấy giờ chứ không phải ô trống."""
    from app.models.san_xuat import SanXuatCongViec

    svc3.dat_moc(lenh.id, MOC)
    svc3.phat_hanh(lenh.id, actor=admin)
    cvs = db.query(SanXuatCongViec).filter(SanXuatCongViec.lsx_id == lenh.id).all()
    assert cvs, "phát hành xong mà không đẻ công việc nào"
    co_gio = [c for c in cvs if c.du_kien_bat_dau is not None]
    assert co_gio, "mọi thẻ việc đều trống giờ — cầu mốc chưa vào tới snapshot"
    assert all(c.du_kien_ket_thuc >= c.du_kien_bat_dau for c in co_gio)
