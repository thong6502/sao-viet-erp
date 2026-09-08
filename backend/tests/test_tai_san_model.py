"""Model sổ tài sản — dựng bảng + ràng buộc. DB in-memory riêng, không đụng DB dev."""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401 — đăng ký metadata
from app.models.tai_san import LOAI_TSCD, MOC_GHI_TANG, MOC_NANG_CAP, TT_DANG_DUNG, TaiSan, TaiSanMoc


def _db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def _ts(**over):
    base = dict(
        ma="TS-0001", ten="May in Komori 4 mau", loai=LOAI_TSCD,
        nguyen_gia=3_300_000_000, so_thang=120, ngay_su_dung=date(2026, 3, 10),
        co_so_trich=3_300_000_000, so_thang_con=120, moc_tu_ngay=date(2026, 3, 10),
    )
    base.update(over)
    return TaiSan(**base)


def _moc(**over):
    base = dict(
        tu_ngay=date(2026, 3, 10), nguyen_gia=3_300_000_000, co_so_trich=3_300_000_000,
        so_thang_con=120, luy_ke_dau=0, nguon=MOC_GHI_TANG,
    )
    base.update(over)
    return TaiSanMoc(**base)


def test_tao_tai_san_va_mac_dinh():
    db = _db()
    db.add(_ts())
    db.commit()
    t = db.query(TaiSan).one()
    assert t.trang_thai == TT_DANG_DUNG
    assert t.so_luong == 1
    assert t.hao_mon_dau_ky == 0
    assert t.ghi_chu is None


def test_khong_con_cot_hao_mon_luy_ke():
    """Lũy kế là số TÍNH từ mốc (08/09/2026) — không có cột nào để ai cộng dồn hay chốt."""
    assert "hao_mon_luy_ke" not in TaiSan.__table__.columns
    assert "tai_san_khau_hao" not in Base.metadata.tables
    assert "tai_san_ky" not in Base.metadata.tables
    assert "tai_san_ky_log" not in Base.metadata.tables
    assert "tai_san_moc" in Base.metadata.tables


def test_ma_tai_san_khong_trung():
    db = _db()
    db.add(_ts())
    db.commit()
    db.add(_ts(ten="May khac"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_moc_di_theo_tai_san_va_xoa_theo():
    db = _db()
    t = _ts()
    t.moc.append(_moc())
    db.add(t)
    db.commit()
    assert db.query(TaiSanMoc).count() == 1
    db.delete(t)
    db.commit()
    assert db.query(TaiSanMoc).count() == 0


def test_moc_doc_ra_theo_thu_tu_ngay():
    """Thêm mốc sau trước, mốc trước sau — đọc lại vẫn theo `tu_ngay` rồi `id`."""
    db = _db()
    t = _ts()
    t.moc.append(_moc(tu_ngay=date(2026, 9, 1), nguon=MOC_NANG_CAP, luy_ke_dau=157_016_129))
    t.moc.append(_moc())
    db.add(t)
    db.commit()
    db.expire_all()
    t = db.query(TaiSan).one()
    assert [m.tu_ngay for m in t.moc] == [date(2026, 3, 10), date(2026, 9, 1)]
    assert [m.nguon for m in t.moc] == [MOC_GHI_TANG, MOC_NANG_CAP]
