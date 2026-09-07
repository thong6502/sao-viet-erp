"""Kỳ khấu hao: tính lại được khi chưa chốt, khoá cứng khi đã chốt."""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401
from app.models.department import Department
from app.models.tai_san import LOAI_CCDC, LOAI_TSCD
from app.models.user import User
from app.repositories.tai_san_repo import TaiSanRepository
from app.services.tai_san.ky_service import (
    KyCoChungTuSau,
    KyDaChot,
    KyService,
    KyTruocChuaChot,
)
from app.services.tai_san.service import TaiSanService


def _moi_truong():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    return db, TaiSanService(TaiSanRepository(db)), KyService(db)


def _komori(svc):
    return svc.ghi_tang(dict(
        ten="May in Komori 4 mau", loai=LOAI_TSCD, so_thang=120,
        ngay_su_dung=date(2026, 3, 10),
        chi_phi=[{"dien_giai": "Nguyen gia", "so_tien": 3_300_000_000}],
    ))


def test_tinh_ky_dau_tien_theo_ngay():
    db, svc, ky = _moi_truong()
    _komori(svc)
    dong = ky.tinh(2026, 3)
    assert len(dong) == 1
    assert dong[0].muc_trich == 19_516_129
    assert dong[0].luy_ke == 19_516_129
    assert dong[0].con_lai == 3_280_483_871


def test_tinh_lai_ky_chua_chot_thi_ghi_de_khong_cong_don():
    db, svc, ky = _moi_truong()
    _komori(svc)
    ky.tinh(2026, 3)
    dong = ky.tinh(2026, 3)
    assert len(dong) == 1
    assert dong[0].luy_ke == 19_516_129


def test_luy_ke_cong_don_qua_cac_ky():
    db, svc, ky = _moi_truong()
    t = _komori(svc)
    ky.tinh(2026, 3)
    ky.chot(2026, 3)
    dong = ky.tinh(2026, 4)
    assert dong[0].muc_trich == 27_500_000
    assert dong[0].luy_ke == 47_016_129
    # Tính THỬ không đụng sổ: hao mòn lũy kế chỉ nhích khi CHỐT.
    db.refresh(t)
    assert t.hao_mon_luy_ke == 19_516_129
    ky.chot(2026, 4)
    db.refresh(t)
    assert t.hao_mon_luy_ke == 47_016_129


def test_ky_truoc_chua_chot_van_cong_dung_luy_ke_khi_xem_ky_sau():
    """Xem trước tháng 4 lúc tháng 3 còn mở: lũy kế phải đã gồm tháng 3."""
    db, svc, ky = _moi_truong()
    _komori(svc)
    ky.tinh(2026, 3)
    dong = ky.tinh(2026, 4)
    assert dong[0].luy_ke == 47_016_129


def test_chot_roi_thi_khong_tinh_lai_duoc():
    db, svc, ky = _moi_truong()
    _komori(svc)
    ky.tinh(2026, 3)
    ky.chot(2026, 3)
    with pytest.raises(KyDaChot):
        ky.tinh(2026, 3)


def test_chot_hai_lan_bi_chan():
    db, svc, ky = _moi_truong()
    _komori(svc)
    ky.tinh(2026, 3)
    ky.chot(2026, 3)
    with pytest.raises(KyDaChot):
        ky.chot(2026, 3)


def test_khong_duoc_nhay_coc_khi_ky_truoc_con_mo():
    db, svc, ky = _moi_truong()
    _komori(svc)
    ky.tinh(2026, 3)
    ky.tinh(2026, 4)
    with pytest.raises(KyTruocChuaChot):
        ky.chot(2026, 4)


def test_mo_lai_ky_da_chot():
    db, svc, ky = _moi_truong()
    t = _komori(svc)
    ky.tinh(2026, 3)
    ky.chot(2026, 3)
    k = ky.mo(2026, 3)
    assert k.trang_thai == "mo"
    db.refresh(t)
    assert t.hao_mon_luy_ke == 0
    assert ky.tinh(2026, 3)[0].muc_trich == 19_516_129


def test_khong_mo_lai_ky_cu_khi_ky_sau_da_chot():
    db, svc, ky = _moi_truong()
    _komori(svc)
    ky.tinh(2026, 3)
    ky.chot(2026, 3)
    ky.tinh(2026, 4)
    ky.chot(2026, 4)
    with pytest.raises(KyDaChot):
        ky.mo(2026, 3)


def test_bang_ky_co_du_cot_man_hinh_can():
    db, svc, ky = _moi_truong()
    t = _komori(svc)
    ky.tinh(2026, 3)
    hang = ky.bang(2026, 3)[0]
    assert set(hang) == {
        "tai_san_id", "ma", "ten", "loai", "bo_phan_ten",
        "nguyen_gia", "muc_trich", "luy_ke", "con_lai",
    }
    assert hang["ma"] == t.ma
    assert hang["ten"] == "May in Komori 4 mau"


def test_khong_mo_lai_ky_khi_da_co_ghi_giam_mot_phan_sau_do():
    """Bo 2 trong 4 cai o thang 5 thi thang 3 dong cua roi: tru muc trich cu se ra luy ke AM."""
    db, svc, ky = _moi_truong()
    t = svc.ghi_tang(dict(
        ten="Dao xen giay", loai=LOAI_CCDC, so_luong=4, don_gia=2_500_000,
        so_thang=24, ngay_su_dung=date(2026, 3, 5),
    ))
    ky.tinh(2026, 3)
    ky.chot(2026, 3)
    db.refresh(t)
    luy_ke_sau_chot = t.hao_mon_luy_ke
    assert luy_ke_sau_chot > 0

    svc.ghi_giam(t.id, ngay=date(2026, 5, 10), ly_do="Gay 2 cai", so_luong_giam=2)
    db.refresh(t)
    assert t.hao_mon_luy_ke < luy_ke_sau_chot     # da rut theo ty le

    with pytest.raises(KyCoChungTuSau):
        ky.mo(2026, 3)
    db.refresh(t)
    assert t.hao_mon_luy_ke > 0                   # khong ai tru vao luy ke ca


def test_khong_mo_lai_ky_khi_da_co_nang_cap_sau_do():
    db, svc, ky = _moi_truong()
    t = _komori(svc)
    ky.tinh(2026, 3)
    ky.chot(2026, 3)
    svc.nang_cap(t.id, ngay=date(2026, 6, 1), so_tien=180_000_000, so_thang_con_lai=117)
    with pytest.raises(KyCoChungTuSau):
        ky.mo(2026, 3)


def test_dieu_chuyen_sau_ky_van_mo_lai_duoc():
    """Doi bo phan khong dung toi mot con so nao — chan luon la chan oan."""
    db, svc, ky = _moi_truong()
    to_be = Department(name="To Be", code="PB902")
    db.add(to_be)
    db.commit()
    t = _komori(svc)
    ky.tinh(2026, 3)
    ky.chot(2026, 3)
    svc.dieu_chuyen(t.id, ngay=date(2026, 6, 1), bo_phan_moi_id=to_be.id, ly_do="Chuyen to")
    assert ky.mo(2026, 3).trang_thai == "mo"
    db.refresh(t)
    assert t.hao_mon_luy_ke == 0


# --- Vet chot / mo ---------------------------------------------------------------------------


def _nguoi(db, ten="Nguyen Van Giam"):
    u = User(username="ketoan1", name=ten, password_hash="x")
    db.add(u)
    db.commit()
    return u


def test_tinh_khong_de_lai_vet():
    """Bam Tinh la chuyen thuong ngay va khong dung toi luy ke — ghi vet thi vet chot chim nghim."""
    db, svc, ky = _moi_truong()
    _komori(svc)
    ky.tinh(2026, 3)
    assert ky.lich_su(2026, 3) == []


def test_chot_ghi_vet_kem_so_tien_va_nguoi():
    db, svc, ky = _moi_truong()
    u = _nguoi(db)
    _komori(svc)
    ky.tinh(2026, 3)
    ky.chot(2026, 3, user_id=u.id)
    vet = ky.lich_su(2026, 3)
    assert len(vet) == 1
    assert vet[0]["hanh_dong"] == "chot"
    assert vet[0]["so_tien"] == 19_516_129        # dung bang so vua cong vao hao mon luy ke
    assert vet[0]["so_mon"] == 1
    assert vet[0]["nguoi_ten"] == "Nguyen Van Giam"


def test_mo_lai_ky_van_giu_vet_lan_chot_truoc():
    """`tai_san_ky` xoa sach nguoi/ngay chot khi mo lai — vet la cho DUY NHAT con lai."""
    db, svc, ky = _moi_truong()
    u = _nguoi(db)
    _komori(svc)
    ky.tinh(2026, 3)
    ky.chot(2026, 3, user_id=u.id)
    k = ky.mo(2026, 3, user_id=u.id)
    assert k.ngay_chot is None and k.nguoi_chot_id is None
    vet = ky.lich_su(2026, 3)
    assert [v["hanh_dong"] for v in vet] == ["mo", "chot"]      # moi nhat truoc
    assert vet[0]["so_tien"] == vet[1]["so_tien"] == 19_516_129
    assert vet[0]["so_mon"] == 1


def test_chot_mo_chot_lai_de_lai_ba_vet():
    db, svc, ky = _moi_truong()
    _komori(svc)
    ky.tinh(2026, 3)
    ky.chot(2026, 3)
    ky.mo(2026, 3)
    ky.chot(2026, 3)
    assert [v["hanh_dong"] for v in ky.lich_su(2026, 3)] == ["chot", "mo", "chot"]


def test_vet_khong_lan_giua_cac_ky():
    db, svc, ky = _moi_truong()
    _komori(svc)
    ky.tinh(2026, 3)
    ky.chot(2026, 3)
    ky.tinh(2026, 4)
    ky.chot(2026, 4)
    assert len(ky.lich_su(2026, 3)) == 1
    thang_tu = ky.lich_su(2026, 4)
    assert len(thang_tu) == 1
    assert thang_tu[0]["so_tien"] == 27_500_000
