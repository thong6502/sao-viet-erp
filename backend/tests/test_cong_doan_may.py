"""Bảng nối công đoạn × máy — nơi khai công thức giờ chạy và công thức giá theo từng máy.

Vì sao có bảng này (06/09/2026): "một bước chạy trên máy này bằng bao nhiêu <đơn vị tốc độ>" và
"máy này tính tiền thế nào" đều là giao của VIỆC và MÁY. Treo ở máy thì mọi công đoạn dùng chung;
treo ở công đoạn thì mọi máy dùng chung — cả hai cách cũ đều sai một nửa.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — đăng ký metadata
from app.db import Base
from app.models.cong_doan import CongDoan, CongDoanDauViec, CongDoanDauViecVatTu, CongDoanMay
from app.models.may_thiet_bi import MayThietBi


@pytest.fixture()
def db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng)()
    yield s
    s.close()


def _cd(db, ma="CD-M1") -> CongDoan:
    cd = CongDoan(ma=ma, ten="In AB", nhom="print")
    db.add(cd)
    db.flush()
    return cd


def _may(db, ma="MAY-1") -> MayThietBi:
    m = MayThietBi(ma=ma, ten="Komori 5 màu", loai_may="Máy in")
    db.add(m)
    db.flush()
    return m


def test_mot_cong_doan_giu_nhieu_may_moi_may_mot_cap_cong_thuc(db):
    cd, m1, m2 = _cd(db), _may(db, "MAY-1"), _may(db, "MAY-2")
    cd.may_lam_duoc.append(CongDoanMay(
        may_id=m1.id, cong_thuc_gio="sl_vao * so_mau / 5", cong_thuc_gia="sl_vao * 180", thu_tu=0))
    cd.may_lam_duoc.append(CongDoanMay(
        may_id=m2.id, cong_thuc_gio="sl_vao * so_mau / 2", cong_thuc_gia="sl_vao * 90", thu_tu=1))
    db.commit()
    db.refresh(cd)
    assert [r.may_id for r in cd.may_lam_duoc] == [m1.id, m2.id]
    assert cd.may_lam_duoc[0].cong_thuc_gio == "sl_vao * so_mau / 5"
    assert cd.may_lam_duoc[1].cong_thuc_gia == "sl_vao * 90"


def test_mot_may_khong_khai_hai_lan_trong_cung_cong_doan(db):
    cd, m = _cd(db), _may(db)
    cd.may_lam_duoc.append(CongDoanMay(may_id=m.id, thu_tu=0))
    db.commit()
    cd.may_lam_duoc.append(CongDoanMay(may_id=m.id, thu_tu=1))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_xoa_cong_doan_keo_theo_dong_may(db):
    cd, m = _cd(db), _may(db)
    cd.may_lam_duoc.append(CongDoanMay(may_id=m.id, thu_tu=0))
    db.commit()
    db.delete(cd)
    db.commit()
    assert db.query(CongDoanMay).count() == 0
