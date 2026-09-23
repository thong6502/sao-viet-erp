"""Dải routing trên bàn tổ (docs/design-dai-routing-tren-ban-to.md).

Bàn tổ chỉ lọc bước CỦA TỔ mình, nên thẻ lệnh hiện đúng một dòng. Dải cần bước của MỌI tổ trong
cùng gói phát hành, sắp theo thứ tự routing của lệnh.

Dựng cảnh bằng `lenh_that` của `lenh_sx_fixtures` (lệnh THẬT đã phát hành, routing CTP → In →
Đóng gói): fixture `_hai_cv` của `test_san_xuat_ban_giao` chỉ cho MỘT bước mỗi lệnh — không thử
được cái mà module này sinh ra để làm.
"""
from __future__ import annotations

from app.models.department import Department
from app.repositories.san_xuat_repo import SanXuatRepository

from tests.lenh_sx_fixtures import (  # noqa: F401
    _cvs,
    admin,
    customer,
    lenh_that,
    lsx_svc,
    orders,
    sess,
)


def _to_moi(sess, ten: str, ma: str) -> Department:
    d = Department(name=ten, code=ma, la_san_xuat=True)
    sess.add(d)
    sess.flush()
    return d


def test_lay_buoc_cua_moi_to_trong_goi(sess, lenh_that):
    """Đẩy bước ĐẦU sang tổ khác — hàm vẫn phải trả đủ cả ba bước của lệnh."""
    cvs = _cvs(sess, lenh_that)
    assert len(cvs) == 3
    to_khac = _to_moi(sess, "Tổ CTP dải", "TO-DAI-CTP")
    cvs[0].department_id = to_khac.id
    sess.commit()

    repo = SanXuatRepository(sess)
    rows = repo.cong_viec_cua_goi_cho_lenh({cvs[0].goi_id}, {lenh_that})
    assert {cv.id for cv in rows} == {cv.id for cv in cvs}


def test_thu_tu_theo_step_key(sess, lenh_that):
    """Map step_key → (lsx_id, thu_tu) để sắp dải; `san_xuat_cong_viec` không có cột thứ tự."""
    cvs = _cvs(sess, lenh_that)
    m = SanXuatRepository(sess).thu_tu_theo_step_key({lenh_that})
    for cv in cvs:
        assert cv.step_key in m
        assert m[cv.step_key][0] == lenh_that
    assert m[cvs[0].step_key][1] < m[cvs[1].step_key][1] < m[cvs[2].step_key][1]


def test_ban_giao_toi_nhieu_dich_gop_mot_truy_van(sess, lenh_that):
    """Bản GỘP của `ban_giao_toi_dich` — trang bàn tổ có 20 lệnh, gọi từng cái là N+1."""
    from app.repositories.san_xuat_san_luong_repo import SanXuatSanLuongRepository
    from tests.lenh_sx_fixtures import _da_nhan_tu

    cvs = _cvs(sess, lenh_that)
    _da_nhan_tu(sess, cvs[0], cvs[1], so_luong=120)

    sl = SanXuatSanLuongRepository(sess)
    m = sl.ban_giao_toi_nhieu_dich([cv.id for cv in cvs])
    assert cvs[0].id not in m
    assert len(m[cvs[1].id]) == 1
    assert float(m[cvs[1].id][0].so_luong) == 120.0


def test_dung_routing_danh_dau_buoc_cua_toi(sess, lenh_that):
    """Dải có đủ 3 bước; chỉ bước của tổ mình mang `la_cua_toi` và `cong_viec_id`."""
    from app.services.san_xuat.routing_dai import dung_routing

    cvs = _cvs(sess, lenh_that)
    to_khac = _to_moi(sess, "Tổ CTP dải 2", "TO-DAI-CTP2")
    cvs[0].department_id = to_khac.id
    sess.commit()

    repo = SanXuatRepository(sess)
    ra = dung_routing(sess, repo, khoa=[("lsx", lenh_that)], cv_cua_toi=cvs[1:])
    dai = ra[("lsx", lenh_that)]
    assert [o["ten_cong_doan"] for o in dai] == [cv.ten_cong_doan for cv in cvs]
    assert [o["la_cua_toi"] for o in dai] == [False, True, True]
    assert dai[0]["cong_viec_id"] is None
    assert dai[0]["to_ten"] == to_khac.name
    assert dai[1]["cong_viec_id"] == cvs[1].id


def test_o_nguon_noi_da_giao_sang_to_toi(sess, lenh_that):
    """Bước trước ghi "đã giao sang" — khác hẳn với "bước trước đã xong"."""
    from app.services.san_xuat.routing_dai import dung_routing
    from tests.lenh_sx_fixtures import _da_nhan_tu

    cvs = _cvs(sess, lenh_that)
    to_khac = _to_moi(sess, "Tổ CTP dải 3", "TO-DAI-CTP3")
    cvs[0].department_id = to_khac.id
    sess.commit()
    _da_nhan_tu(sess, cvs[0], cvs[1], so_luong=480)

    ra = dung_routing(sess, SanXuatRepository(sess),
                      khoa=[("lsx", lenh_that)], cv_cua_toi=cvs[1:])
    dai = ra[("lsx", lenh_that)]
    assert dai[0]["da_giao_sang_toi"] == 480.0
    assert dai[1]["da_giao_sang_toi"] is None
    assert dai[2]["da_giao_sang_toi"] is None


def test_gop_trang_thai_lay_yeu_nhat(sess):
    """Một bước tách N lần chạy = MỘT ô; trạng thái lấy yếu nhất."""
    from app.services.san_xuat.routing_dai import _gop_trang_thai

    assert _gop_trang_thai(["completed", "released"]) == "released"
    assert _gop_trang_thai(["completed", "running"]) == "running"
    assert _gop_trang_thai(["completed", "completed"]) == "completed"
    assert _gop_trang_thai(["paused", "completed"]) == "paused"
    assert _gop_trang_thai([]) == "released"
