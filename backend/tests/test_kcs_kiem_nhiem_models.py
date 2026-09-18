"""Model nền KCS — checklist + lần kiểm + danh mục tiêu chí.

Soi TẦNG MODEL (không service, không HTTP):
  · cột JSON checklist (nullable) `san_xuat_cong_viec.kcs_tieu_chi_json` — ảnh chụp lúc phát hành;
    ô "bổ sung" trên bước lệnh/bài ghép ĐÃ GỠ (mg `0283`), xem test cùng tên bên dưới;
  · `san_xuat_kcs_batch.checklist_json` (nullable). Hai cột `loai` / `kcs_department_id` ĐÃ GỠ
    (KCS theo lệnh, mg `0306`): chỉ còn MỘT kiểu kiểm, người kiểm lấy từ tài khoản;
  · danh mục tiêu chí `san_xuat_kcs_tieu_chi` thuộc MỘT công đoạn (mg `0285`).

Cờ `la_kcs` trên công việc đã phát hành ĐÃ GỠ (mg `0306`) — KCS không còn là một bước trong routing;
`la_kcs_cuoi` = công đoạn cuối của nhóm thành phẩm, suy lúc phát hành.

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
from app.models.san_xuat_kcs import SanXuatKcsBatch, SanXuatKcsTieuChi
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


def test_buoc_lenh_khong_con_o_tieu_chi_bo_sung(db):
    """Ô "Tiêu chí KCS bổ sung" ĐÃ GỠ khỏi bước lệnh và bước bài ghép (mg `0283`, 08/09/2026):
    tiêu chí KCS chỉ còn MỘT nguồn là danh mục gắn theo công đoạn
    (`docs/design-kcs-theo-cong-doan.md` mục 5). Chốt bằng test để không ai lặng lẽ khai lại cột
    thứ hai rồi hai nguồn lại lệch nhau."""
    for buoc in (LsxCongDoan(lsx_id=1), BaiGhepCongDoan(bai_ghep_id=1)):
        db.add(buoc)
        db.commit()
        db.refresh(buoc)
        assert not hasattr(buoc, "kcs_tieu_chi_bo_sung_json")
        assert "kcs_tieu_chi_bo_sung_json" not in buoc.__table__.columns


def test_san_xuat_cong_viec_kcs_tieu_chi_json_nullable(db):
    cv = SanXuatCongViec(goi_id=1)
    db.add(cv)
    db.commit()
    db.refresh(cv)
    assert "la_kcs" not in cv.__table__.columns        # gỡ ở mg 0306
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


def test_san_xuat_kcs_batch_mot_kieu_kiem(db):
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

    assert batch.checklist_json is None
    assert batch.so_luong_nhan == 100 and batch.so_luong_dat == 95 and batch.don_vi == "cái"
    # KCS theo lệnh (mg 0306): không còn phân loại lần kiểm, không còn "tổ KCS đi kiểm".
    for cot in ("loai", "kcs_department_id"):
        assert cot not in SanXuatKcsBatch.__table__.columns


def test_san_xuat_kcs_tieu_chi_danh_muc(db):
    cd = CongDoan(ma="CD-KCS-TEST-1", ten="In offset", nhom="print")
    db.add(cd)
    db.commit()
    tc = SanXuatKcsTieuChi(ma="IN-CHONG-MAU", ten="Chồng màu đúng", cong_doan_id=cd.id)
    db.add(tc)
    db.commit()
    db.refresh(tc)
    assert tc.bat_buoc is True
    assert tc.active is True
    assert tc.thu_tu == 0
    assert tc.cong_doan_id == cd.id


def test_hang_muc_kiem_khong_trung_ten_trong_mot_cong_doan(db):
    """Hạng mục THUỘC một công đoạn (mg `0285`) — cùng công đoạn cấm trùng câu chữ, khác công
    đoạn thì được (hai tờ ISO khác nhau vẫn có dòng "Chồng màu đúng")."""
    cd1 = CongDoan(ma="CD-KCS-TEST-2", ten="In offset 2", nhom="print")
    cd2 = CongDoan(ma="CD-KCS-TEST-3", ten="In lụa", nhom="print")
    db.add_all([cd1, cd2])
    db.commit()

    db.add(SanXuatKcsTieuChi(ma="KM0001", ten="Chồng màu đúng", cong_doan_id=cd1.id))
    db.commit()
    # Cùng câu chữ ở CÔNG ĐOẠN KHÁC → hợp lệ.
    db.add(SanXuatKcsTieuChi(ma="KM0002", ten="Chồng màu đúng", cong_doan_id=cd2.id))
    db.commit()

    db.add(SanXuatKcsTieuChi(ma="KM0003", ten="Chồng màu đúng", cong_doan_id=cd1.id))
    with pytest.raises(IntegrityError):
        db.commit()
