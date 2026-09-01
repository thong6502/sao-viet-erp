"""Phát hành lệnh có công đoạn ĐÃ TÁCH (docs/spec-thuc-te-vs-ke-hoach.md §2.4, pha 2).

Hai tầng, hai bộ tiền đề — nên file có HAI fixture DB, cố ý:

  · `db_trong` (schema trắng, không seed) cho phần TẦNG REPO: repo phải trả MỌI phân đoạn của một
    bước, không phải một dòng bất kỳ — bước tách 6.000 máy A + 4.000 máy B mà chỉ đọc được một
    dòng thì phân đoạn còn lại biến mất khỏi bàn tổ, im lặng. Phần này chỉ đụng
    `xep_lich_cong_doan` nên kéo cả bộ danh mục vào chỉ làm chậm.
  · `db` (seed đầy, mượn của `tests/test_xep_lich_service.py`) cho phần PHÁT HÀNH: phải đi đúng
    luồng thật đơn → lệnh → routing → xếp lịch → tách → phát hành mới soi được `dung_cong_viec`.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db import Base, SessionLocal, engine
from app.models.lsx import LB_MAY, LsxCongDoan, LsxCongDoanPhuThuoc
from app.models.may_thiet_bi import MayThietBi
from app.models.order import OrderLine
from app.models.san_xuat import SanXuatCongViec, SanXuatPhuThuoc
from app.models.xep_lich import NGUON_IN_GHEP, NGUON_LSX, TT_DA_XEP, XepLichCongDoan
from app.repositories.san_xuat_repo import SanXuatRepository
from app.repositories.xep_lich_repo import XepLichRepository
from app.services.san_xuat import release
from app.services.san_xuat.release_update import _thoi_gian_nguon
from app.services.xep_lich_2.phan_doan import tach

# Fixtures + helper của luồng thật (đơn → lệnh → sẵn sàng) — cùng lối với
# `tests/test_san_xuat_release.py`, đừng dựng bộ thứ hai.
from tests.test_xep_lich_service import (  # noqa: F401
    _hai_lsx_san_sang,
    _in_step,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
    xl_svc,
)

_T0 = datetime(2026, 8, 19, 8, 0, tzinfo=timezone.utc)


@pytest.fixture
def db_trong():
    """Schema trắng, KHÔNG seed — bám precedent `test_xep_lich_phan_doan.py`."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def test_lich_lsx_step_tra_ve_du_cac_phan_doan(db_trong):
    db = db_trong
    a = XepLichCongDoan(nguon=NGUON_LSX, lsx_cong_doan_id=55, source_thu_tu=0, loai_buoc="may",
                        trang_thai=TT_DA_XEP, may_id=1, start_at=_T0,
                        finish_at=_T0 + timedelta(hours=3),
                        so_luong=6000, phan_doan_so=1, phan_doan_tong=2)
    db.add(a)
    db.flush()
    b = XepLichCongDoan(nguon=NGUON_LSX, lsx_cong_doan_id=55, source_thu_tu=0, loai_buoc="may",
                        trang_thai=TT_DA_XEP, may_id=2, start_at=_T0 + timedelta(days=1),
                        finish_at=_T0 + timedelta(days=1, hours=2),
                        so_luong=4000, phan_doan_so=2, phan_doan_tong=2, goc_dong_id=a.id)
    db.add(b)
    db.commit()

    ra = SanXuatRepository(db).lich_lsx_step(55)
    assert [r[3] for r in ra] == [1, 2]
    assert [r[0] for r in ra] == [1, 2]
    assert [float(r[4]) for r in ra] == [6000.0, 4000.0]


def test_lich_lsx_step_buoc_chua_tach_van_tra_mot_phan_tu(db_trong):
    db = db_trong
    d = XepLichCongDoan(nguon=NGUON_LSX, lsx_cong_doan_id=56, source_thu_tu=0, loai_buoc="may",
                        trang_thai=TT_DA_XEP, may_id=3, start_at=_T0,
                        finish_at=_T0 + timedelta(hours=4))
    db.add(d)
    db.commit()

    ra = SanXuatRepository(db).lich_lsx_step(56)
    assert len(ra) == 1
    # NULL = "trọn bước", KHÁC 0 — chỗ gọi phải phân biệt được để khỏi phát hành việc 0 sản lượng.
    assert ra[0][3] == 1 and ra[0][4] is None


def test_lich_lsx_step_khong_co_lich_thi_rong(db_trong):
    assert SanXuatRepository(db_trong).lich_lsx_step(999) == []


def test_lich_bg_step_tra_ve_du_cac_phan_doan(db_trong):
    db = db_trong
    a = XepLichCongDoan(nguon=NGUON_IN_GHEP, bai_ghep_id=7, bai_ghep_cong_doan_id=88,
                        source_thu_tu=0, loai_buoc="may", trang_thai=TT_DA_XEP, may_id=11,
                        start_at=_T0, finish_at=_T0 + timedelta(hours=2),
                        so_luong=1500, phan_doan_so=1, phan_doan_tong=2)
    db.add(a)
    db.flush()
    b = XepLichCongDoan(nguon=NGUON_IN_GHEP, bai_ghep_id=7, bai_ghep_cong_doan_id=88,
                        source_thu_tu=0, loai_buoc="may", trang_thai=TT_DA_XEP, may_id=12,
                        start_at=_T0 + timedelta(hours=5), finish_at=_T0 + timedelta(hours=6),
                        so_luong=500, phan_doan_so=2, phan_doan_tong=2, goc_dong_id=a.id)
    db.add(b)
    db.commit()

    ra = SanXuatRepository(db).lich_bg_step(88)
    assert [r[3] for r in ra] == [1, 2]
    assert [r[0] for r in ra] == [11, 12]
    assert [float(r[4]) for r in ra] == [1500.0, 500.0]


def test_migration_0254_co_trong_danh_sach():
    from app.db_migrations import MIGRATIONS
    assert any(ma == "0254_cong_viec_phan_doan" for ma, _fn in MIGRATIONS)


def test_phat_hanh_cap_nhat_khop_dung_lan_chay(db_trong):
    """`release_update._thoi_gian_nguon` phải trả giờ/máy của ĐÚNG lần chạy mà công việc đại diện.

    Bản cũ đọc dòng đầu tiên nên lần 2 nhận giờ + máy của lần 1; và khi lịch đã tách/gộp lại thì
    không còn phân đoạn tương ứng — lúc đó phải trả None để bên gọi giữ nguyên snapshot, chứ không
    được đoán bừa một dòng khác."""
    db = db_trong
    a = XepLichCongDoan(nguon=NGUON_LSX, lsx_cong_doan_id=60, source_thu_tu=0, loai_buoc="may",
                        trang_thai=TT_DA_XEP, may_id=1, start_at=_T0,
                        finish_at=_T0 + timedelta(hours=3),
                        so_luong=6000, phan_doan_so=1, phan_doan_tong=2)
    db.add(a)
    db.flush()
    b = XepLichCongDoan(nguon=NGUON_LSX, lsx_cong_doan_id=60, source_thu_tu=0, loai_buoc="may",
                        trang_thai=TT_DA_XEP, may_id=2, start_at=_T0 + timedelta(days=1),
                        finish_at=_T0 + timedelta(days=1, hours=2),
                        so_luong=4000, phan_doan_so=2, phan_doan_tong=2, goc_dong_id=a.id)
    db.add(b)
    db.commit()

    repo = SanXuatRepository(db)
    lan1 = SanXuatCongViec(lsx_cong_doan_id=60, phan_doan_so=1, phan_doan_tong=2)
    lan2 = SanXuatCongViec(lsx_cong_doan_id=60, phan_doan_so=2, phan_doan_tong=2)

    may_id, start, finish = _thoi_gian_nguon(repo, lan1)
    # SQLite trả datetime NAIVE dù cột khai `timezone=True` → bỏ tzinfo hai bên rồi mới so.
    assert may_id == 1
    assert start.replace(tzinfo=None) == _T0.replace(tzinfo=None)
    assert finish.replace(tzinfo=None) == (_T0 + timedelta(hours=3)).replace(tzinfo=None)

    may_id2, start2, _ = _thoi_gian_nguon(repo, lan2)
    assert may_id2 == 2, "lần 2 phải nhận máy của chính nó, không phải máy của lần 1"
    assert start2.replace(tzinfo=None) == (_T0 + timedelta(days=1)).replace(tzinfo=None)

    # Lịch đã gộp lại còn 1 lần chạy ⇒ công việc "lần 3" không còn chỗ neo.
    lan3 = SanXuatCongViec(lsx_cong_doan_id=60, phan_doan_so=3, phan_doan_tong=3)
    assert _thoi_gian_nguon(repo, lan3) is None
    # Bước chưa vào kế hoạch: không dòng lịch nào ⇒ bộ 3 rỗng (giữ hành vi cũ, KHÁC với None).
    assert _thoi_gian_nguon(repo, SanXuatCongViec(lsx_cong_doan_id=999)) == (None, None, None)


# =====================================================================================
# PHÁT HÀNH: mỗi phân đoạn một công việc cho tổ (Task 7)
# =====================================================================================
def _may_thu_hai(db) -> MayThietBi:
    """Máy thứ HAI để phân đoạn 2 chạy chỗ khác — đúng cảnh sinh ra việc tách lần chạy."""
    may = db.query(MayThietBi).filter(MayThietBi.ma == "MAY-IN-XL-2").first()
    if may is not None:
        return may
    may = MayThietBi(
        ma="MAY-IN-XL-2", ten="Máy in 2 màu", loai_may="press_offset_sheet",
        toc_do=4_000, don_vi_toc_do="to_gio", makeready_time_default=20,
        kho_max_dai=1020, kho_max_rong=720,
    )
    db.add(may)
    db.flush()
    return may


def _lsx_da_xep_va_tach(db, orders, lsx_svc, xl_svc, admin, customer):
    """Đơn → lệnh → routing → xếp lịch → TÁCH bước in 6.000 + 4.000 → xếp giờ/máy cho cả hai.

    Trả `(lsx, buoc_in, buoc_sau, may_1_id, may_2_id)`. Đi ĐÚNG luồng thật (không dựng
    `xep_lich_cong_doan` bằng tay) vì thứ đang soi là khâu phát hành ĐỌC lịch — dựng tay là tự cho
    mình dữ liệu đẹp. Routing của `_ptg_2_in` chỉ có ĐÚNG bước in, nên thêm một bước sau nó: cần
    một bước CHƯA tách để đối chứng, và cần một bước CUỐI khác bước in để soi KCS-cuối.
    """
    a, _b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    buoc = _in_step(db, a.id)
    # Số tròn để tách 6.000 + 4.000 khớp đúng tổng; năng suất khai sẵn để dòng xếp được giờ.
    buoc.so_luong_vao, buoc.so_luong_ra = 10_000, 10_000
    buoc.nang_suat, buoc.don_vi_nang_suat = 5_000, "to_gio"
    buoc.setup_phut, buoc.chay_phut, buoc.so_luot_chay = 0, None, 1
    may_2 = _may_thu_hai(db)
    sau = LsxCongDoan(
        lsx_id=a.id, thu_tu=1, ten="Xả tờ", nhom="finishing", loai_buoc=LB_MAY,
        may_id=may_2.id, so_luong_vao=10_000, so_luong_ra=10_000, nang_suat=3_000,
        don_vi_nang_suat="to_gio", don_vi_vao="to", don_vi_ra="to",
    )
    db.add(sau)
    db.commit()

    xl_svc.dua_vao_lsx(lsx_id=a.id, actor=admin)
    dong = next(
        d for d in XepLichRepository(db).by_lsx(a.id) if d.lsx_cong_doan_id == buoc.id
    )
    may_1 = buoc.may_id
    xl_svc.gan(dong_id=dong.id, patch={"may_id": may_1, "start_at": _T0}, actor=admin)

    cum = tach(db, dong_id=dong.id, cac_phan=[6000, 4000], actor=admin)
    db.commit()
    xl_svc.gan(
        dong_id=cum[1].id,
        patch={"may_id": may_2.id, "start_at": _T0 + timedelta(days=1)},
        actor=admin,
    )
    return a, buoc, sau, may_1, may_2.id


def test_phat_hanh_buoc_da_tach_de_ra_hai_cong_viec(db, orders, lsx_svc, xl_svc, admin, customer):
    """Bước in tách 6.000 + 4.000 ⇒ tổ nhận HAI công việc, mỗi cái mang đúng phần của mình."""
    a, buoc, _sau, may_1, may_2 = _lsx_da_xep_va_tach(db, orders, lsx_svc, xl_svc, admin, customer)

    goi = release.phat_hanh(db, lsx_ids={a.id}, actor=admin)
    db.commit()

    cvs = (
        db.query(SanXuatCongViec)
        .filter(SanXuatCongViec.goi_id == goi.id,
                SanXuatCongViec.lsx_cong_doan_id == buoc.id)
        .order_by(SanXuatCongViec.id)
        .all()
    )
    assert len(cvs) == 2
    # `so_luong` của dòng lịch là một phần của SL VÀO (xem `phan_doan._sl_vao_cua_buoc`) — nên
    # phần chia rơi vào `so_luong_vao`, còn `so_luong_ra` scale theo cùng tỉ lệ.
    assert sorted(float(c.so_luong_vao) for c in cvs) == [4000.0, 6000.0]
    assert sorted(float(c.so_luong_ra) for c in cvs) == [4000.0, 6000.0]
    assert {c.may_id for c in cvs} == {may_1, may_2}
    assert cvs[0].du_kien_bat_dau != cvs[1].du_kien_bat_dau
    assert [c.ten_cong_doan for c in cvs] == [
        f"{buoc.ten} (lần 1/2)", f"{buoc.ten} (lần 2/2)",
    ]
    # Bước KHÁC trong cùng lệnh (chưa tách) vẫn ĐÚNG MỘT công việc, tên không đeo hậu tố.
    khac = (
        db.query(SanXuatCongViec)
        .filter(SanXuatCongViec.goi_id == goi.id,
                SanXuatCongViec.lsx_cong_doan_id != buoc.id,
                SanXuatCongViec.lsx_id == a.id)
        .all()
    )
    assert khac and all("(lần " not in c.ten_cong_doan for c in khac)


def test_tong_san_luong_hai_phan_doan_bang_ca_buoc(db, orders, lsx_svc, xl_svc, admin, customer):
    """Bất biến: Σ phần của các phân đoạn == số của cả bước. Lệch một tờ là lệch bảng cân đối vật
    tư lẫn định mức khoán."""
    a, buoc, _sau, _m1, _m2 = _lsx_da_xep_va_tach(db, orders, lsx_svc, xl_svc, admin, customer)

    goi = release.phat_hanh(db, lsx_ids={a.id}, actor=admin)
    db.commit()

    cvs = db.query(SanXuatCongViec).filter(
        SanXuatCongViec.goi_id == goi.id, SanXuatCongViec.lsx_cong_doan_id == buoc.id
    ).all()
    assert sum(float(c.so_luong_vao) for c in cvs) == float(buoc.so_luong_vao)
    assert sum(float(c.so_luong_ra) for c in cvs) == float(buoc.so_luong_ra)


def test_phu_thuoc_noi_theo_phan_doan_cuoi(db, orders, lsx_svc, xl_svc, admin, customer):
    """Bước SAU chỉ chạy được khi phân đoạn CUỐI của bước trước xong — cạnh phụ thuộc chéo nối vào
    phân đoạn CUỐI, không nối vào phân đoạn đầu (nối đầu là cho bước sau chạy khi mới xong 60%)."""
    from app.models.lsx import Lsx

    a, buoc, _sau, _m1, _m2 = _lsx_da_xep_va_tach(db, orders, lsx_svc, xl_svc, admin, customer)
    # Hai lệnh cùng nhóm thành phẩm (cùng gói phát hành) + một cạnh CHÉO từ bước in đã tách của
    # lệnh a sang bước in của lệnh b.
    b = next(
        l for l in db.query(Lsx).filter(Lsx.order_id == a.order_id).all() if l.id != a.id
    )
    for l in (a, b):
        db.get(OrderLine, l.order_line_id).nhom = "Sách A5"
    buoc_b = _in_step(db, b.id)
    db.add(LsxCongDoanPhuThuoc(buoc_truoc_id=buoc.id, buoc_sau_id=buoc_b.id))
    db.commit()

    goi = release.phat_hanh(db, lsx_ids={a.id, b.id}, actor=admin)
    db.commit()

    cvs_a = (
        db.query(SanXuatCongViec)
        .filter(SanXuatCongViec.goi_id == goi.id,
                SanXuatCongViec.lsx_cong_doan_id == buoc.id)
        .order_by(SanXuatCongViec.id)
        .all()
    )
    cv_b = db.query(SanXuatCongViec).filter(
        SanXuatCongViec.goi_id == goi.id, SanXuatCongViec.lsx_cong_doan_id == buoc_b.id
    ).one()
    assert len(cvs_a) == 2

    canh = db.query(SanXuatPhuThuoc).filter(
        SanXuatPhuThuoc.goi_id == goi.id,
        SanXuatPhuThuoc.dich_cong_viec_id == cv_b.id,
    ).all()
    assert len(canh) == 1
    assert canh[0].nguon_cong_viec_id == cvs_a[-1].id
    assert canh[0].nguon_cong_viec_id != cvs_a[0].id


def test_kcs_cuoi_danh_dau_moi_phan_doan_cua_buoc(db, orders, lsx_svc, xl_svc, admin, customer):
    """Bước KCS cuối bị tách ⇒ MỌI phân đoạn của nó mang `la_kcs_cuoi`.

    Không phải chỉ phân đoạn cuối: `kho.tao_yeu_cau_kho_mot_nut` chặn thẳng công việc không có cờ
    này, nên bỏ cờ ở lần chạy 1 là số ĐẠT của mẻ 7.000 không có đường vào kho; và
    `dong_nhom.dieu_kien_dong_nhom` cộng mục tiêu trên đúng tập ấy — thiếu một phân đoạn là mục
    tiêu nhóm tụt còn 3.000.
    """
    from tests.test_san_xuat_release import _kcs_dept, _steps

    a, _buoc, cuoi, _m1, may_2 = _lsx_da_xep_va_tach(db, orders, lsx_svc, xl_svc, admin, customer)
    kcs = _kcs_dept(db)
    cuoi = _steps(db, a.id)[-1]
    cuoi.department_id = kcs.id
    cuoi.so_luong_vao, cuoi.so_luong_ra = 10_000, 10_000
    cuoi.nang_suat, cuoi.don_vi_nang_suat = 5_000, "to_gio"
    db.commit()

    dong_cuoi = next(
        d for d in XepLichRepository(db).by_lsx(a.id) if d.lsx_cong_doan_id == cuoi.id
    )
    xl_svc.gan(dong_id=dong_cuoi.id, patch={"may_id": may_2, "start_at": _T0}, actor=admin)
    cum = tach(db, dong_id=dong_cuoi.id, cac_phan=[7000, 3000], actor=admin)
    db.commit()
    xl_svc.gan(
        dong_id=cum[1].id, patch={"may_id": may_2, "start_at": _T0 + timedelta(days=2)},
        actor=admin,
    )

    goi = release.phat_hanh(db, lsx_ids={a.id}, actor=admin)
    db.commit()

    cvs = db.query(SanXuatCongViec).filter(
        SanXuatCongViec.goi_id == goi.id, SanXuatCongViec.lsx_cong_doan_id == cuoi.id
    ).all()
    assert len(cvs) == 2
    assert all(c.la_kcs for c in cvs)
    assert all(c.la_kcs_cuoi for c in cvs)


def test_migration_0254_backfill_so_phan_doan_tu_ten(db_trong):
    """Việc phát hành GIỮA mg 0253 và 0254 đeo `1/1` sai — backfill đọc lại số từ tên công việc.

    Không có bước này thì mọi việc cũ của một bước đã tách đều khớp về phân đoạn 1, và "Phát hành
    cập nhật" lại dập giờ của lần 1 lên cả N việc — đúng lỗi mà 0254 sinh ra để chặn."""
    from app.db_migrations import _migrate_cong_viec_phan_doan
    from app.models.san_xuat import SanXuatCongViec, SanXuatGoiPhatHanh

    db = db_trong
    goi = SanXuatGoiPhatHanh(ma="GPH-TEST-0254")
    db.add(goi)
    db.flush()
    tach_2 = SanXuatCongViec(goi_id=goi.id, ten_cong_doan="In offset (lần 2/3)")
    tron_buoc = SanXuatCongViec(goi_id=goi.id, ten_cong_doan="Cán màng mờ")
    db.add_all([tach_2, tron_buoc])
    db.commit()
    assert (tach_2.phan_doan_so, tach_2.phan_doan_tong) == (1, 1)

    _migrate_cong_viec_phan_doan(db)
    db.refresh(tach_2)
    db.refresh(tron_buoc)

    assert (tach_2.phan_doan_so, tach_2.phan_doan_tong) == (2, 3)
    # Bước KHÔNG tách phải giữ 1/1: backfill chỉ được đụng hàng có hậu tố "(lần k/n)".
    assert (tron_buoc.phan_doan_so, tron_buoc.phan_doan_tong) == (1, 1)
