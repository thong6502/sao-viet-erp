"""Danh mục Khuôn bế (khai báo lưu trữ) — CRUD nhẹ + xử lý TRÙNG MÃ do xóa mềm.

Mirror test_kho_hang: mã KB-#### sinh ngầm, xóa mềm giữ `ma` (unique) → create() tái
dùng đúng hàng khi mã trùng thay vì 409. Self-contained in-memory DB.
"""
import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401 — đăng ký metadata mọi bảng
from app.repositories.khuon_be_repo import KhuonBeRepository
from app.services.khuon_be_service import (
    KhuonBeDuplicate,
    KhuonBeService,
    KhuonBeValidationError,
)


def _svc():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    return db, KhuonBeService(KhuonBeRepository(db))


def test_create_and_validate():
    db, svc = _svc()
    k = svc.create(dict(ma="KB-0001", ten="Khuôn hộp bánh A", so_ke="Kệ B3",
                        ngay_ve_du_kien=date(2026, 1, 5)))
    assert k.id and k.ma == "KB-0001" and k.active is True
    assert k.so_ke == "Kệ B3" and k.tinh_trang == "dang_dung"
    with pytest.raises(KhuonBeValidationError):            # thiếu tên
        svc.create(dict(ma="KB-0002", ten=""))


def test_reject_bad_tinh_trang():
    db, svc = _svc()
    with pytest.raises(KhuonBeValidationError):
        svc.create(dict(ten="Khuôn X", tinh_trang="bay_hoi"))


def test_ma_auto_generated_when_blank():
    db, svc = _svc()
    a = svc.create(dict(ten="Khuôn 1"))                    # không truyền mã → tự sinh
    b = svc.create(dict(ma="", ten="Khuôn 2"))            # mã rỗng cũng tự sinh
    assert a.ma == "KB-0001" and b.ma == "KB-0002"


def test_ma_auto_skips_soft_deleted_gap():
    db, svc = _svc()
    a = svc.create(dict(ten="Khuôn 1"))                    # KB-0001
    b = svc.create(dict(ten="Khuôn 2"))                    # KB-0002
    svc.update(b.id, dict(ten="Khuôn 2", active=False))   # xóa mềm KB-0002
    c = svc.create(dict(ten="Khuôn 3"))                   # phải là KB-0003, KHÔNG tái dùng 0002
    assert a.ma == "KB-0001" and c.ma == "KB-0003"


def test_duplicate_active_blocks():
    db, svc = _svc()
    svc.create(dict(ma="KB-0001", ten="Khuôn A"))
    with pytest.raises(KhuonBeDuplicate):                  # trùng khuôn đang hoạt động → chặn
        svc.create(dict(ma="kb-0001", ten="Khuôn khác"))  # (không phân biệt hoa/thường)


def test_soft_deleted_ma_reused_not_duplicate():
    db, svc = _svc()
    a = svc.create(dict(ma="KB-0001", ten="Khuôn cũ", so_ke="Kệ 1", ghi_chu="cũ"))
    svc.update(a.id, dict(ma="KB-0001", ten="Khuôn cũ", active=False))  # xóa mềm (như UI)

    # Tạo lại đúng mã đã xóa mềm → KHÔNG 409, tái dùng chính hàng đó (cùng id).
    b = svc.create(dict(ma="KB-0001", ten="Khuôn mới", so_ke="Kệ 2", ghi_chu="mới"))
    assert b.id == a.id                                    # cùng 1 hàng, không đẻ hàng rác
    assert b.active is True
    assert b.ten == "Khuôn mới" and b.so_ke == "Kệ 2" and b.ghi_chu == "mới"

    rows, total = svc.list(active=True)                   # chỉ 1 khuôn active, không nhân đôi
    assert total == 1 and rows[0].id == a.id


def test_search_theo_ten_va_so_ke():
    """Ô tìm quét MÃ · TÊN ấn phẩm · SỐ KỆ.

    Cột `khach_hang` đã gỡ 15/08/2026 (mg `0202`) nên tìm theo tên khách KHÔNG còn ra kết quả —
    ghi thẳng vào test để lần sau không ai tưởng là hỏng rồi đi "sửa" bằng cách nối lại cột.
    Muốn biết khuôn của khách nào thì tra qua lệnh sản xuất đang dùng khuôn đó.
    """
    db, svc = _svc()
    svc.create(dict(ten="Khuôn hộp Minh Long", so_ke="Kệ A1"))
    svc.create(dict(ten="Khuôn tem", so_ke="Kệ B2"))
    rows, total = svc.list(q="minh long")
    assert total == 1 and rows[0].ten == "Khuôn hộp Minh Long"
    rows2, total2 = svc.list(q="b2")
    assert total2 == 1 and rows2[0].so_ke == "Kệ B2"
    # Chuỗi chỉ có ở tên khách cũ ⇒ không dòng nào khớp.
    assert svc.list(q="Cty")[1] == 0


def test_loc_va_dem_theo_tinh_trang():
    """Tab lọc của màn Khuôn bế chạy Ở MÁY CHỦ từ 14/08/2026.

    Trước đó màn kéo cả danh mục về rồi lọc + đếm trong JS; nay bảng chỉ cầm 20 dòng nên
    hai việc đó phải nằm đây: `list(tinh_trang=…)` lọc, `dem_theo_tinh_trang()` nuôi số
    trên tab — và số trên tab KHÔNG được đổi theo tab đang chọn.
    """
    db, svc = _svc()
    svc.create(dict(ten="Khuôn A", tinh_trang="dang_dung"))
    svc.create(dict(ten="Khuôn B", tinh_trang="dang_dung"))
    svc.create(dict(ten="Khuôn C", tinh_trang="hong"))

    rows, total = svc.list(tinh_trang="hong")
    assert total == 1 and rows[0].ten == "Khuôn C"

    assert svc.dem_theo_tinh_trang() == {"dang_dung": 2, "hong": 1}
    # Có ô tìm thì số trên tab đi theo ô tìm — tab khoe số cả danh mục là nói dối.
    assert svc.dem_theo_tinh_trang(q="khuôn c") == {"hong": 1}


# --- Nối vào bước lệnh sản xuất (mg 0205, 16/08/2026) ---------------------------


def test_ngay_ve_du_kien_THUC_SU_duoc_luu():
    """🔴 Lỗi có sẵn, sửa 16/08/2026: `ngay_ve_du_kien` KHÔNG nằm trong `KhuonBeRepository.fields`
    — danh sách cột client được phép ghi. Form có ô, service BẮT BUỘC khai khi chọn "đang đặt
    làm", người dùng gõ vào, validate qua… rồi `_gan` bỏ qua và lưu ra NULL. Hỏng câm, không lỗi.

    Mất cột này là mất luôn thứ duy nhất đáng hỏi ở nhánh "làm dao mới": chờ tới bao giờ.
    """
    db, svc = _svc()
    k = svc.create(dict(ten="Khuôn hộp mới", tinh_trang="dang_dat_lam",
                        ngay_ve_du_kien=date(2026, 8, 20)))
    db.expire_all()                                   # đọc lại từ DB, không lấy bản trong bộ nhớ
    assert svc.get(k.id).ngay_ve_du_kien == date(2026, 8, 20)


def test_khach_va_loai_duoc_luu_va_loc_duoc():
    """Hai chiều lọc của ô chọn dao ở bước lệnh. Không lưu được thì ô chọn bày cả kho."""
    db, svc = _svc()
    a = svc.create(dict(ten="Dao bế hộp A", khach_hang_id=7, loai="khuon_be"))
    svc.create(dict(ten="Dao ép nhũ hộp A", khach_hang_id=7, loai="khuon_ep"))
    svc.create(dict(ten="Dao bế hộp B", khach_hang_id=9, loai="khuon_be"))

    db.expire_all()
    assert svc.get(a.id).khach_hang_id == 7 and svc.get(a.id).loai == "khuon_be"

    # Lọc từng chiều và cả hai chiều.
    assert svc.list(khach_hang_id=7)[1] == 2
    assert svc.list(loai="khuon_be")[1] == 2
    rows, total = svc.list(khach_hang_id=7, loai="khuon_ep")
    assert total == 1 and rows[0].ten == "Dao ép nhũ hộp A"


def test_loai_khong_hop_le_bi_chan():
    db, svc = _svc()
    with pytest.raises(KhuonBeValidationError):
        svc.create(dict(ten="Khuôn lạ", loai="khuon_dap_noi"))


def test_accept_loai_khung_lua():
    """Khung lụa cũng lưu kho dùng lại như khuôn bế (chốt 04/09/2026) — kho phải nhận loại này,
    không thì bước lụa ở lệnh mở ô chọn ra rỗng và bấm 'làm mới' thì service ném 400."""
    db, svc = _svc()
    k = svc.create(dict(ten="Khung lụa hộp bánh A", loai="khung_lua", so_ke="Kệ C1"))
    assert k.loai == "khung_lua"
