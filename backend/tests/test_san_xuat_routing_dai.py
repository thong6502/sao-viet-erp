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
