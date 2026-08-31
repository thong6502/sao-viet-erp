"""Danh mục Tiêu chí KCS — repo/service (Task 3/12 `.superpowers/sdd/2026-08-31-kcs-kiem-nhiem`).

Hai điểm soi ở đây (snapshot khi phát hành soi riêng ở `test_san_xuat_release.py`):
  · `SanXuatRepository.checklist_theo_cong_doan()` — batch fetch nhiều-nhiều, đúng lọc `active` +
    đúng thứ tự `thu_tu` rồi `id`.
  · CRUD `san_xuat_kcs_tieu_chi` qua `SanXuatKcsTieuChiService` — `cong_doan_ids` thêm/bớt phản
    ánh đúng vào bảng nối, validate id công đoạn phải có thật.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401 — đăng ký toàn bộ metadata (kể cả san_xuat_kcs)
from app.repositories.cong_doan_repo import CongDoanRepository
from app.repositories.san_xuat_kcs_tieu_chi_repo import SanXuatKcsTieuChiRepository
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


def _cong_doan(db, ma: str):
    """Công đoạn tối thiểu — mượn CongDoanService cho đúng validate (basis/nhóm) thay vì tạo ORM
    trần, tránh cấu hình sai lặng lẽ lọt qua test."""
    cd_svc = CongDoanService(CongDoanRepository(db))
    return cd_svc.create(dict(
        ma=ma, ten=ma, nhom="print",
        che_do_tinh="theo_san_luong", pricing_basis="per_finished_qty", first_unit_floor=0,
    ))


# ---- Scenario 1: checklist_theo_cong_doan() — nhiều tiêu chí/một công đoạn, một tiêu chí/nhiều
# công đoạn ----
def test_checklist_theo_cong_doan_nhieu_tieu_chi_nhieu_cong_doan():
    db = _db()
    cd1 = _cong_doan(db, "CD-KCS-1")
    cd2 = _cong_doan(db, "CD-KCS-2")
    tc_svc = SanXuatKcsTieuChiService(SanXuatKcsTieuChiRepository(db))

    # Tiêu chí "chung" gắn CẢ hai công đoạn.
    tc_chung = tc_svc.create(dict(
        ma="TC-CHUNG", ten="Chồng màu đúng", thu_tu=10, cong_doan_ids=[cd1.id, cd2.id],
    ))
    # Tiêu chí RIÊNG chỉ gắn cd1.
    tc_rieng = tc_svc.create(dict(
        ma="TC-RIENG", ten="Kiểm biên dạng bế", thu_tu=5, cong_doan_ids=[cd1.id],
    ))

    repo = SanXuatRepository(db)
    out = repo.checklist_theo_cong_doan({cd1.id, cd2.id})

    assert {t.id for t in out[cd1.id]} == {tc_chung.id, tc_rieng.id}
    assert [t.id for t in out[cd1.id]] == [tc_rieng.id, tc_chung.id]   # sort thu_tu rồi id: 5 < 10
    assert [t.id for t in out[cd2.id]] == [tc_chung.id]


def test_checklist_theo_cong_doan_chi_lay_active():
    db = _db()
    cd = _cong_doan(db, "CD-KCS-3")
    tc_svc = SanXuatKcsTieuChiService(SanXuatKcsTieuChiRepository(db))
    tc_on = tc_svc.create(dict(ma="TC-ON", ten="Còn hiệu lực", active=True, cong_doan_ids=[cd.id]))
    tc_svc.create(dict(ma="TC-OFF", ten="Đã ngừng", active=False, cong_doan_ids=[cd.id]))

    repo = SanXuatRepository(db)
    out = repo.checklist_theo_cong_doan({cd.id})
    assert [t.id for t in out[cd.id]] == [tc_on.id]


def test_checklist_theo_cong_doan_rong_khi_khong_co_id():
    db = _db()
    repo = SanXuatRepository(db)
    assert repo.checklist_theo_cong_doan(set()) == {}


# ---- Scenario 5: CRUD cơ bản, cong_doan_ids thêm/bớt phản ánh đúng vào bảng nối ----
def test_crud_gan_va_doi_cong_doan_ids():
    db, svc = _svc()
    cd1 = _cong_doan(db, "CD-A")
    cd2 = _cong_doan(db, "CD-B")
    cd3 = _cong_doan(db, "CD-C")

    tc = svc.create(dict(ma="TC-01", ten="Kiểm màu", cong_doan_ids=[cd1.id, cd2.id]))
    assert sorted(tc.cong_doan_ids) == sorted([cd1.id, cd2.id])

    # `update()` ở CatalogService là PUT thay-toàn-bộ (như `bu_hao`), KHÔNG merge với dữ liệu cũ —
    # `_validate` soi đúng dict truyền vào nên phải gửi lại đủ ma/ten như form thật sự gửi.
    # Sửa: bớt cd1, giữ cd2, thêm cd3 — bảng nối phải phản ánh ĐÚNG tập mới, không còn dòng cũ
    # ngoài tập mới (repo `_replace_cong_doan_links` clear() + flush() rồi ghi lại).
    tc = svc.update(tc.id, dict(ma="TC-01", ten="Kiểm màu", cong_doan_ids=[cd2.id, cd3.id]))
    assert sorted(tc.cong_doan_ids) == sorted([cd2.id, cd3.id])

    # Đọc lại từ DB (không phải object đang cache) để chắc bảng nối thật sự đổi, không phải chỉ
    # đổi trên instance Python đang giữ.
    lai = svc.get(tc.id)
    assert sorted(lai.cong_doan_ids) == sorted([cd2.id, cd3.id])


def test_crud_dedup_cong_doan_id_trung():
    db, svc = _svc()
    cd = _cong_doan(db, "CD-DUP")
    tc = svc.create(dict(ma="TC-DUP", ten="X", cong_doan_ids=[cd.id, cd.id, cd.id]))
    assert tc.cong_doan_ids == [cd.id]


def test_validate_ma_ten_khong_duoc_trong():
    db, svc = _svc()
    with pytest.raises(SanXuatKcsTieuChiValidationError):
        svc.create(dict(ma="", ten="X"))
    with pytest.raises(SanXuatKcsTieuChiValidationError):
        svc.create(dict(ma="TC-X", ten=""))


def test_validate_cong_doan_id_khong_ton_tai_bi_chan():
    db, svc = _svc()
    with pytest.raises(SanXuatKcsTieuChiValidationError):
        svc.create(dict(ma="TC-SAI", ten="X", cong_doan_ids=[999]))


def test_dat_active_khong_xoa_cong_doan_ids():
    """Regression — Fix round 1 (xác minh UI thật, xem task-3-report.md): PATCH .../active (nút
    "Ngừng dùng"/"Bật lại") chỉ gửi `{"active": bool}` một khoá, KHÔNG đụng `cong_doan_ids`.
    Trước bản vá, `_sau_gan` đọc khoá vắng mặt thành "xoá trọn" (`data.get(...) or []`) nên bấm
    Ngừng dùng/Bật lại xoá sạch công đoạn đang gắn."""
    db, svc = _svc()
    cd1 = _cong_doan(db, "CD-ACT-1")
    cd2 = _cong_doan(db, "CD-ACT-2")
    tc = svc.create(dict(ma="TC-ACT", ten="Kiểm độ bám mực", cong_doan_ids=[cd1.id, cd2.id]))
    assert sorted(tc.cong_doan_ids) == sorted([cd1.id, cd2.id])

    tc = svc.dat_active(tc.id, False)
    assert tc.active is False
    assert sorted(tc.cong_doan_ids) == sorted([cd1.id, cd2.id])

    tc = svc.dat_active(tc.id, True)
    assert tc.active is True
    assert sorted(tc.cong_doan_ids) == sorted([cd1.id, cd2.id])

    # Đọc lại từ DB — chắc bảng nối THẬT sự còn nguyên, không phải chỉ còn trên instance cache.
    lai = svc.get(tc.id)
    assert sorted(lai.cong_doan_ids) == sorted([cd1.id, cd2.id])
