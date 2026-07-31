"""Danh mục Đơn vị + CẶP quy đổi — service có chạm DB (SQLite in-memory của conftest).

Trọng tâm là thứ KHÔNG test được bằng hàm thuần:
  · khai cặp làm LỆCH đường đã có thì CHẶN (chủ chốt 2026-07-30) — số quy đổi chảy vào tiền khoán
    và tồn kho, lệch mà im lặng thì phát hiện ra đã trả lương sai mấy tháng;
  · câu hiển thị đọc TỪ CHÍNH dòng đang xem, vế trái luôn là số nguyên;
  · xoá đơn vị thì cặp của nó đi theo (cặp mồ côi là đường đi ma).
"""
from __future__ import annotations

import pytest

from app.db import Base, SessionLocal, engine
from app.repositories.don_vi_do_repo import DonViDoRepository
from app.services.don_vi_do_service import DonViDoService, DonViDoValidationError


@pytest.fixture
def svc():
    """DB trắng cho mỗi test: danh mục đơn vị là bảng NHỎ, dựng lại rẻ hơn dọn dẹp."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        yield DonViDoService(DonViDoRepository(db))
    finally:
        db.close()


def _bo_ba(svc):
    """Đúng ba bước chủ mô tả: tạo `tấn`, tạo `kg`, khai 1 tấn = 1.000 kg."""
    tan = svc.create({"ma": "tan", "ten": "tấn"})
    kg = svc.create({"ma": "kg", "ten": "kg"})
    svc.create_cap({"tu_id": tan.id, "den_id": kg.id, "he_so": 1000})
    return tan, kg


# --- chặn mâu thuẫn -----------------------------------------------------------


def test_chan_cap_lam_lech_duong_da_co(svc):
    tan, kg = _bo_ba(svc)
    g = svc.create({"ma": "g", "ten": "g"})
    svc.create_cap({"tu_id": kg.id, "den_id": g.id, "he_so": 1000})

    with pytest.raises(DonViDoValidationError) as e:
        svc.create_cap({"tu_id": tan.id, "den_id": g.id, "he_so": 999_000})
    # Thông điệp phải CHỈ RA đường đang mâu thuẫn, không chỉ nói "sai".
    assert "tan" in str(e.value) and "kg" in str(e.value) and "g" in str(e.value)


def test_cho_luu_cap_khop_voi_duong_da_co(svc):
    tan, kg = _bo_ba(svc)
    g = svc.create({"ma": "g", "ten": "g"})
    svc.create_cap({"tu_id": kg.id, "den_id": g.id, "he_so": 1000})
    # 1 tấn = 1.000.000 g khớp đường tấn → kg → g nên phải cho lưu (dư thừa nhưng không sai).
    cap = svc.create_cap({"tu_id": tan.id, "den_id": g.id, "he_so": 1_000_000})
    assert float(cap.he_so) == 1_000_000


def test_sua_cap_khong_tu_mau_thuan_voi_chinh_no(svc):
    """Sửa hệ số của một cặp phải bỏ qua CHÍNH nó khi dò đường, không thì không sửa nổi."""
    tan, kg = _bo_ba(svc)
    cap = svc.repo.find_cap(tan.id, kg.id)
    svc.update_cap(cap.id, {"he_so": 1200})
    assert float(svc.repo.get_cap(cap.id).he_so) == 1200


@pytest.mark.parametrize("he_so", [0, -5])
def test_chan_he_so_khong_duong(svc, he_so):
    tan, kg = _bo_ba(svc)
    m = svc.create({"ma": "m", "ten": "mét"})
    with pytest.raises(DonViDoValidationError):
        svc.create_cap({"tu_id": m.id, "den_id": kg.id, "he_so": he_so})


def test_chan_cap_tu_tro_chinh_no(svc):
    tan, _kg = _bo_ba(svc)
    with pytest.raises(DonViDoValidationError):
        svc.create_cap({"tu_id": tan.id, "den_id": tan.id, "he_so": 1})


def test_khong_cho_khai_hai_dong_cho_cung_mot_cap(svc):
    """Khai `tấn → kg` rồi khai tiếp `kg → tấn` là hai dòng nói cùng chuyện — sớm muộn lệch nhau."""
    tan, kg = _bo_ba(svc)
    from app.services.don_vi_do_service import DonViDoDuplicate

    with pytest.raises(DonViDoDuplicate):
        svc.create_cap({"tu_id": kg.id, "den_id": tan.id, "he_so": 0.001})


# --- câu hiển thị -------------------------------------------------------------


def test_cau_doc_tu_chinh_dong_va_ve_trai_la_so_nguyen(svc):
    tan, kg = _bo_ba(svc)
    # Dòng tấn đọc xuôi; dòng kg KHÔNG được hiện "0,001 kg = 1 tấn" mà phải lật cho dễ đọc.
    assert svc.quy_doi_text(tan) == "1 tấn = 1.000 kg"
    assert svc.quy_doi_text(kg) == "1.000 kg = 1 tấn"


def test_don_vi_chua_khai_cap_noi_thang(svc):
    thung = svc.create({"ma": "thung", "ten": "thùng"})
    assert svc.quy_doi_text(thung) == "Chưa khai quy đổi"
    assert svc.canh_bao(thung), "phải nhắc là chưa dùng quy đổi được"


# --- quy đổi động (hệ số là công thức) ----------------------------------------


def test_luu_duoc_dong_cong_thuc(svc):
    """"1 tờ bằng mấy kg" tuỳ giấy — khai bằng CÔNG THỨC, `he_so` để 0."""
    to = svc.create({"ma": "to", "ten": "tờ"})
    kg = svc.create({"ma": "kg", "ten": "kg"})
    cap = svc.create_cap({"tu_id": to.id, "den_id": kg.id,
                          "cong_thuc": "dinh_luong * dai * rong"})
    assert float(cap.he_so) == 0          # số chỉ có lúc chạy, để 0 cho hỏng lộ ra ngay
    assert svc.quy_doi_text(to) == "1 tờ = định lượng × dài × rộng kg"


def test_chan_bien_la_trong_cong_thuc(svc):
    """Biến hệ thống không bơm được thì dòng đó nằm chết trong bảng — chặn ngay lúc khai."""
    to = svc.create({"ma": "to", "ten": "tờ"})
    kg = svc.create({"ma": "kg", "ten": "kg"})
    with pytest.raises(DonViDoValidationError) as e:
        svc.create_cap({"tu_id": to.id, "den_id": kg.id, "cong_thuc": "do_day * dai"})
    assert "do_day" in str(e.value)


def test_dong_cong_thuc_khong_bi_chan_mau_thuan(svc):
    """Dòng động chưa có giấy nào để thay biến nên KHÔNG so được với đường hằng — đừng chặn oan."""
    tan, kg = _bo_ba(svc)
    to = svc.create({"ma": "to", "ten": "tờ"})
    svc.create_cap({"tu_id": to.id, "den_id": kg.id, "cong_thuc": "dinh_luong * dai * rong"})
    # Cặp HẰNG vẫn bị chặn như cũ (tấn → g lệch với đường tấn → kg → g).
    g = svc.create({"ma": "g", "ten": "g"})
    svc.create_cap({"tu_id": kg.id, "den_id": g.id, "he_so": 1000})
    with pytest.raises(DonViDoValidationError):
        svc.create_cap({"tu_id": tan.id, "den_id": g.id, "he_so": 999_000})


# --- vòng đời -----------------------------------------------------------------


def test_xoa_don_vi_thi_cap_cua_no_di_theo(svc):
    """Cặp mồ côi trỏ vào đơn vị đã xoá là đường đi MA — máy vẫn tính ra số mà không ai hiểu."""
    tan, kg = _bo_ba(svc)
    svc.delete(tan.id)
    assert svc.repo.cap_rows() == []
