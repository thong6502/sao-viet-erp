"""Danh mục HẠNG MỤC KIỂM KCS — repo/service sau mg `0285` (thuộc ĐÚNG MỘT công đoạn).

Ba điểm soi ở đây (snapshot khi phát hành soi riêng ở `test_san_xuat_release.py`):
  · `SanXuatRepository.checklist_theo_cong_doan()` — gom theo công đoạn, đúng lọc `active` +
    đúng thứ tự `thu_tu` rồi `id`.
  · CRUD `san_xuat_kcs_tieu_chi` qua `SanXuatKcsTieuChiService` — mã sinh ngầm `KM####`, chặn
    công đoạn ma, chặn trùng câu chữ trong CÙNG công đoạn (khác công đoạn thì cho).
  · `hang_muc_theo_cong_doan()` — nguồn của màn khai báo ba tầng.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401 — đăng ký toàn bộ metadata (kể cả san_xuat_kcs)
from app.repositories.cong_doan_repo import CongDoanRepository
from app.repositories.san_xuat_kcs_tieu_chi_repo import (
    SanXuatKcsTieuChiRepository, hang_muc_theo_cong_doan,
)
from app.repositories.san_xuat_repo import SanXuatRepository
from app.services.cong_doan_service import CongDoanService
from app.services.san_xuat_kcs_tieu_chi_service import (
    SanXuatKcsTieuChiService,
    SanXuatKcsTieuChiValidationError,
)


def _db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def _svc():
    db = _db()
    return db, SanXuatKcsTieuChiService(SanXuatKcsTieuChiRepository(db))


def _cong_doan(db, ma: str, nhom: str = "print"):
    """Công đoạn tối thiểu — mượn CongDoanService cho đúng validate (basis/nhóm) thay vì tạo ORM
    trần, tránh cấu hình sai lặng lẽ lọt qua test."""
    cd_svc = CongDoanService(CongDoanRepository(db))
    return cd_svc.create(dict(
        ma=ma, ten=ma, nhom=nhom,
        che_do_tinh="theo_san_luong", pricing_basis="per_finished_qty", first_unit_floor=0,
    ))


# ---- checklist_theo_cong_doan() -------------------------------------------------------------
def test_checklist_theo_cong_doan_gom_dung_va_sap_theo_thu_tu():
    db = _db()
    cd1 = _cong_doan(db, "CD-KCS-1")
    cd2 = _cong_doan(db, "CD-KCS-2")
    svc = SanXuatKcsTieuChiService(SanXuatKcsTieuChiRepository(db))

    # Cùng CÂU CHỮ khai cho hai công đoạn = HAI dòng (mô hình mới không dùng chung một dòng).
    chung_1 = svc.create(dict(ten="Chồng màu đúng", thu_tu=10, cong_doan_id=cd1.id))
    chung_2 = svc.create(dict(ten="Chồng màu đúng", thu_tu=10, cong_doan_id=cd2.id))
    rieng = svc.create(dict(ten="Kiểm biên dạng bế", thu_tu=5, cong_doan_id=cd1.id))

    out = SanXuatRepository(db).checklist_theo_cong_doan({cd1.id, cd2.id})

    assert [t.id for t in out[cd1.id]] == [rieng.id, chung_1.id]   # sort thu_tu rồi id: 5 < 10
    assert [t.id for t in out[cd2.id]] == [chung_2.id]


def test_checklist_theo_cong_doan_chi_lay_active():
    db = _db()
    cd = _cong_doan(db, "CD-KCS-3")
    svc = SanXuatKcsTieuChiService(SanXuatKcsTieuChiRepository(db))
    tc_on = svc.create(dict(ten="Còn hiệu lực", active=True, cong_doan_id=cd.id))
    svc.create(dict(ten="Đã ngừng", active=False, cong_doan_id=cd.id))

    out = SanXuatRepository(db).checklist_theo_cong_doan({cd.id})
    assert [t.id for t in out[cd.id]] == [tc_on.id]


def test_checklist_theo_cong_doan_rong_khi_khong_co_id():
    db = _db()
    assert SanXuatRepository(db).checklist_theo_cong_doan(set()) == {}


# ---- CRUD ------------------------------------------------------------------------------------
def test_ma_sinh_ngam_nguoi_khai_chi_go_cau_chu():
    """Người khai chỉ gõ câu chữ hạng mục — mã `KM####` do server cấp (UI không có ô nhập mã)."""
    db, svc = _svc()
    cd = _cong_doan(db, "CD-MA")
    a = svc.create(dict(ten="Kiểm màu", cong_doan_id=cd.id))
    b = svc.create(dict(ten="Kiểm bế", cong_doan_id=cd.id))
    assert a.ma == "KM0001" and b.ma == "KM0002"


def test_doi_cong_doan_cua_hang_muc():
    db, svc = _svc()
    cd1 = _cong_doan(db, "CD-A")
    cd2 = _cong_doan(db, "CD-B")
    tc = svc.create(dict(ten="Kiểm màu", cong_doan_id=cd1.id))
    assert tc.cong_doan_id == cd1.id

    tc = svc.update(tc.id, dict(ten="Kiểm màu", cong_doan_id=cd2.id))
    assert svc.get(tc.id).cong_doan_id == cd2.id


def test_validate_ten_khong_duoc_trong():
    db, svc = _svc()
    cd = _cong_doan(db, "CD-TRONG")
    with pytest.raises(SanXuatKcsTieuChiValidationError):
        svc.create(dict(ten="", cong_doan_id=cd.id))


def test_validate_cong_doan_id_khong_ton_tai_bi_chan():
    db, svc = _svc()
    with pytest.raises(SanXuatKcsTieuChiValidationError):
        svc.create(dict(ten="X", cong_doan_id=999))
    with pytest.raises(SanXuatKcsTieuChiValidationError):
        svc.create(dict(ten="X", cong_doan_id=None))


def test_trung_cau_chu_trong_cung_cong_doan_bi_chan_khac_cong_doan_thi_duoc():
    db, svc = _svc()
    cd1 = _cong_doan(db, "CD-T1")
    cd2 = _cong_doan(db, "CD-T2")
    svc.create(dict(ten="Chồng màu đúng", cong_doan_id=cd1.id))
    svc.create(dict(ten="Chồng màu đúng", cong_doan_id=cd2.id))   # công đoạn khác: OK
    with pytest.raises(SanXuatKcsTieuChiValidationError):
        svc.create(dict(ten="Chồng màu đúng", cong_doan_id=cd1.id))


def test_dat_active_khong_lam_mat_cong_doan():
    """Regression giữ từ bản nhiều-nhiều: PATCH .../active chỉ gửi `{"active": bool}` một khoá,
    `_validate` phải lấy công đoạn từ bản ghi hiện có chứ không đọc thành "chưa chọn công đoạn"."""
    db, svc = _svc()
    cd = _cong_doan(db, "CD-ACT")
    tc = svc.create(dict(ten="Kiểm độ bám mực", cong_doan_id=cd.id))

    tc = svc.dat_active(tc.id, False)
    assert tc.active is False and tc.cong_doan_id == cd.id
    tc = svc.dat_active(tc.id, True)
    assert tc.active is True and svc.get(tc.id).cong_doan_id == cd.id


# ---- Nguồn của màn khai báo ba tầng ----------------------------------------------------------
def test_hang_muc_theo_cong_doan_gom_ca_dong_ngung_dung():
    """Màn khai báo phải THẤY dòng đang ngừng dùng (để bật lại) — khác đường phát hành."""
    db, svc = _svc()
    cd = _cong_doan(db, "CD-KB")
    a = svc.create(dict(ten="Mục 1", thu_tu=2, cong_doan_id=cd.id))
    b = svc.create(dict(ten="Mục 2", thu_tu=1, cong_doan_id=cd.id, active=False))

    out = hang_muc_theo_cong_doan(db)
    assert [h.id for h in out[cd.id]] == [b.id, a.id]   # sort thu_tu rồi id


def _khai_bao(db):
    from app.routers.san_xuat_kcs_tieu_chi import khai_bao
    return khai_bao(db, None)


def test_khai_bao_tra_kem_o_chon_cong_doan_dang_dung_chua_khai():
    """Ô chọn "Khai báo công đoạn kiểm tra mới" đi CHUNG cửa khai-bao (màn thôi gọi `/api/cong-doan`):
    chỉ công đoạn ĐANG DÙNG mà CHƯA khai, xếp theo mã, có cả khi chưa khai hạng mục nào."""
    from app.models.cong_doan import CongDoan

    db, svc = _svc()
    da_khai = _cong_doan(db, "CD-B", nhom="finishing")
    chua_2 = _cong_doan(db, "CD-C", nhom="print")
    chua_1 = _cong_doan(db, "CD-A", nhom="prepress")
    ngung = _cong_doan(db, "CD-D", nhom="print")
    db.get(CongDoan, ngung.id).active = False
    db.commit()

    rong = _khai_bao(db)
    assert rong.giai_doan == []
    assert [c.ma for c in rong.cong_doan_chon] == ["CD-A", "CD-B", "CD-C"]

    svc.create(dict(ten="Mục 1", cong_doan_id=da_khai.id))
    out = _khai_bao(db)
    assert [(g.nhom, [c.cong_doan_id for c in g.cong_doan]) for g in out.giai_doan] == [
        ("finishing", [da_khai.id]),
    ]
    assert [(c.id, c.nhom) for c in out.cong_doan_chon] == [
        (chua_1.id, "prepress"), (chua_2.id, "print"),
    ]


def test_khai_bao_khong_chay_theo_so_cong_doan_va_hang_muc():
    """Cả cây lẫn ô chọn = số truy vấn CỐ ĐỊNH, thêm công đoạn/hạng mục không làm nhảy (N+1)."""
    from sqlalchemy import event

    db, svc = _svc()
    eng = db.get_bind()

    def dem() -> int:
        n = {"n": 0}

        def _ghi(*_a):
            n["n"] += 1

        event.listen(eng, "before_cursor_execute", _ghi)
        try:
            _khai_bao(db)
        finally:
            event.remove(eng, "before_cursor_execute", _ghi)
        return n["n"]

    def dung(dot: int, so: int) -> None:
        for i in range(so):
            cd = _cong_doan(db, f"CD-N{dot}-{i}")
            for j in range(3):
                svc.create(dict(ten=f"Mục {j}", cong_doan_id=cd.id))
            _cong_doan(db, f"CD-M{dot}-{i}")      # công đoạn chưa khai → vào ô chọn

    dung(1, 3)
    db.expire_all()
    nho = dem()
    dung(2, 12)
    db.expire_all()
    assert dem() == nho <= 2
