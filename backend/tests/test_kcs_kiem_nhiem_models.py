"""Model nền module KCS kiêm nhiệm — Task 1/12 (`.superpowers/sdd/2026-08-31-kcs-kiem-nhiem`).

Soi TẦNG MODEL (không service, không HTTP — Task 1 chỉ dựng schema):
  · cờ `la_kcs` (mặc định false) trên 3 bảng ĐANG TỒN TẠI: `cong_doan`, `lsx_cong_doan`,
    `bai_ghep_cong_doan`;
  · cột JSON checklist (nullable) trên `lsx_cong_doan`/`bai_ghep_cong_doan`
    (`kcs_tieu_chi_bo_sung_json`) và `san_xuat_cong_viec` (`kcs_tieu_chi_json`);
  · 3 cột mới trên `san_xuat_kcs_batch` (`loai` mặc định `routing`, `kcs_department_id`,
    `checklist_json`) — KHÔNG động tới cột legacy;
  · 2 bảng danh mục checklist MỚI: `san_xuat_kcs_tieu_chi` + `san_xuat_kcs_tieu_chi_cong_doan`
    (unique theo cặp tiêu_chi×công_đoạn).

Dùng `init_db()` (create_all, KHÔNG seed) trên DB in-memory của bộ test — đủ để dựng schema từ
model, không cần chạy migration (DB fresh)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal, init_db
from app.models.bai_ghep_cong_doan import BaiGhepCongDoan
from app.models.cong_doan import CongDoan
from app.models.san_xuat import SanXuatCongViec
from app.models.san_xuat_kcs import (
    KCS_LOAI_ROUTING,
    SanXuatKcsBatch,
    SanXuatKcsTieuChi,
    SanXuatKcsTieuChiCongDoan,
)
from app.models.lsx import LsxCongDoan


@pytest.fixture
def db():
    init_db()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def test_cong_doan_la_kcs_mac_dinh_false(db):
    cd = CongDoan(ma="CD-KCS-TEST-1", ten="In offset", nhom="print")
    db.add(cd)
    db.commit()
    db.refresh(cd)
    assert cd.la_kcs is False


def test_lsx_cong_doan_la_kcs_va_checklist_bo_sung(db):
    buoc = LsxCongDoan(lsx_id=1)
    db.add(buoc)
    db.commit()
    db.refresh(buoc)
    assert buoc.la_kcs is False
    assert buoc.kcs_tieu_chi_bo_sung_json is None

    buoc.la_kcs = True
    buoc.kcs_tieu_chi_bo_sung_json = [
        {"tieu_chi_id": None, "ma": None, "ten": "Đối chiếu mẫu màu khách duyệt",
         "huong_dan": None, "bat_buoc": True, "nguon": "bo_sung_lsx", "thu_tu": 1000}
    ]
    db.commit()
    db.refresh(buoc)
    assert buoc.la_kcs is True
    assert buoc.kcs_tieu_chi_bo_sung_json[0]["nguon"] == "bo_sung_lsx"


def test_bai_ghep_cong_doan_la_kcs_va_checklist_bo_sung(db):
    buoc = BaiGhepCongDoan(bai_ghep_id=1)
    db.add(buoc)
    db.commit()
    db.refresh(buoc)
    assert buoc.la_kcs is False
    assert buoc.kcs_tieu_chi_bo_sung_json is None


def test_san_xuat_cong_viec_kcs_tieu_chi_json_nullable(db):
    cv = SanXuatCongViec(goi_id=1)
    db.add(cv)
    db.commit()
    db.refresh(cv)
    assert cv.la_kcs is False
    assert cv.la_kcs_cuoi is False
    assert cv.kcs_tieu_chi_json is None

    cv.kcs_tieu_chi_json = [
        {"tieu_chi_id": 12, "ma": "IN-CHONG-MAU", "ten": "Chồng màu đúng",
         "huong_dan": "Không lệch viền nhìn thấy", "bat_buoc": True,
         "nguon": "danh_muc", "thu_tu": 10},
    ]
    db.commit()
    db.refresh(cv)
    assert cv.kcs_tieu_chi_json[0]["ma"] == "IN-CHONG-MAU"


def test_san_xuat_kcs_batch_cot_moi_khong_dung_cot_legacy(db):
    batch = SanXuatKcsBatch(
        cong_viec_id=1,
        bat_dau=datetime(2026, 8, 31, 8, 0, tzinfo=timezone.utc),
        ket_thuc=datetime(2026, 8, 31, 9, 0, tzinfo=timezone.utc),
        so_luong_nhan=100,
        so_luong_dat=95,
        don_vi="cái",
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    # Cột mới: mặc định đúng hợp đồng.
    assert batch.loai == KCS_LOAI_ROUTING == "routing"
    assert batch.kcs_department_id is None
    assert batch.checklist_json is None
    # Cột legacy KHÔNG bị đụng — vẫn ghi/đọc bình thường.
    assert batch.so_luong_nhan == 100
    assert batch.so_luong_dat == 95
    assert batch.don_vi == "cái"

    batch.loai = "dot_xuat"
    batch.kcs_department_id = None  # FK mềm SET NULL — hợp lệ dù chưa gán tổ
    db.commit()
    db.refresh(batch)
    assert batch.loai == "dot_xuat"


def test_san_xuat_kcs_tieu_chi_danh_muc(db):
    tc = SanXuatKcsTieuChi(ma="IN-CHONG-MAU", ten="Chồng màu đúng")
    db.add(tc)
    db.commit()
    db.refresh(tc)
    assert tc.bat_buoc is True
    assert tc.active is True
    assert tc.thu_tu == 0


def test_san_xuat_kcs_tieu_chi_cong_doan_gan_va_unique(db):
    cd = CongDoan(ma="CD-KCS-TEST-2", ten="In offset 2", nhom="print")
    tc = SanXuatKcsTieuChi(ma="IN-CHONG-MAU-2", ten="Chồng màu đúng 2")
    db.add_all([cd, tc])
    db.commit()

    lien_ket = SanXuatKcsTieuChiCongDoan(tieu_chi_id=tc.id, cong_doan_id=cd.id)
    db.add(lien_ket)
    db.commit()

    # Gắn TRÙNG cặp (tiêu_chi, công_đoạn) lần hai → vi phạm unique constraint.
    db.add(SanXuatKcsTieuChiCongDoan(tieu_chi_id=tc.id, cong_doan_id=cd.id))
    with pytest.raises(IntegrityError):
        db.commit()
