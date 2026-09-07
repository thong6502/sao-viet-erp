"""Model sổ tài sản — dựng bảng + ràng buộc. DB in-memory riêng, không đụng DB dev."""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401 — đăng ký metadata
from app.models.tai_san import LOAI_TSCD, TT_DANG_DUNG, TaiSan, TaiSanKhauHao, TaiSanKy


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


def test_tao_tai_san_va_mac_dinh():
    db = _db()
    db.add(_ts())
    db.commit()
    t = db.query(TaiSan).one()
    assert t.trang_thai == TT_DANG_DUNG
    assert t.so_luong == 1
    assert t.hao_mon_luy_ke == 0
    assert t.ghi_chu_hach_toan is None


def test_ma_tai_san_khong_trung():
    db = _db()
    db.add(_ts())
    db.commit()
    db.add(_ts(ten="May khac"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_mot_ky_mot_dong_khau_hao_cho_moi_tai_san():
    db = _db()
    t = _ts()
    db.add(t)
    db.commit()
    db.add(TaiSanKhauHao(tai_san_id=t.id, ky_nam=2026, ky_thang=8,
                         muc_trich=27_500_000, luy_ke=157_016_129, con_lai=3_142_983_871))
    db.commit()
    db.add(TaiSanKhauHao(tai_san_id=t.id, ky_nam=2026, ky_thang=8,
                         muc_trich=1, luy_ke=1, con_lai=1))
    with pytest.raises(IntegrityError):
        db.commit()


def test_ky_ke_toan_khong_trung_thang():
    db = _db()
    db.add(TaiSanKy(ky_nam=2026, ky_thang=8))
    db.commit()
    assert db.query(TaiSanKy).one().trang_thai == "mo"
    db.add(TaiSanKy(ky_nam=2026, ky_thang=8))
    with pytest.raises(IntegrityError):
        db.commit()
