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


# --- module này CHỈ còn: khai đơn vị + quy đổi giữa các đơn vị ------------------
#
# Hai đợt gỡ, cùng một lý do — công thức KHÔNG thuộc về đơn vị:
#
#   14/08/2026 (mg `0198`) — CẶP mang công thức ("1 tờ = f(quy cách) kg"), bảy ca test đi cùng:
#     `test_luu_duoc_dong_cong_thuc` · `test_chan_bien_la_trong_cong_thuc`
#     `test_dong_cong_thuc_khong_bi_chan_mau_thuan` · `test_moi_don_vi_chi_mot_cong_thuc_ra_no`
#     `test_sua_chinh_dong_cong_thuc_khong_tu_chan`
#     `test_canh_bao_hai_cong_thuc_cung_dich_cho_du_lieu_cu`
#     `test_canh_bao_cap_so_co_dinh_de_len_duong_cong_thuc` · `test_khong_canh_bao_cap_cung_loai_do`
#
#   17/08/2026 (mg `0215`) — CÁCH ĐO của chính đơn vị (`don_vi_do.cong_thuc`), tám ca test đi cùng:
#     `test_chips_noi_ro_manh_nao_la_cong_thuc`
#     `test_chips_cua_don_vi_MUON_cong_thuc_cung_la_cong_thuc`
#     `test_don_vi_mang_cach_do_cua_chinh_no`
#     `test_don_vi_co_cong_thuc_hien_cong_thuc_va_KHONG_bao_chua_khai`
#     `test_mot_CUM_TINH_chi_mot_cong_thuc_luong`
#     `test_khong_co_cap_noi_thi_to_va_kg_deu_duoc_co_cong_thuc`
#     `test_noi_cau_TINH_gop_hai_cong_thuc_thi_CHAN`
#     `test_chan_chip_sl_vao_khi_don_vi_dang_la_dau_ra_cua_buoc_ngoai_dong`
#
# Cách đo treo ở đơn vị là câu trả lời DÙNG CHUNG cho mọi ai đếm bằng đơn vị đó, trong khi câu hỏi
# thật luôn thuộc về một cái CỤ THỂ: keo và mực cùng đo `kg` mà ăn khác nhau. Nay mỗi nơi có ô
# riêng — `cong_thuc_luong` ở Giấy · Vật tư · Máy · Công việc khoán, `cong_thuc_san_luong` ở Công
# đoạn (luật vòng-tròn `sl_vao`/`sl_ra` theo về đó, xem `test_cong_doan.py`).


def test_cap_khong_nhan_cong_thuc_nua(svc):
    """Cửa TẠO/SỬA cặp phải CHẶN `cong_thuc`, không nuốt im lặng.

    Client cũ (hoặc script cũ) còn gửi field này; nuốt rồi bỏ qua là lưu một cặp `he_so = 0` — cặp
    chết mà người khai tưởng đã lưu xong.
    """
    to = svc.create({"ma": "to", "ten": "tờ"})
    kg = svc.create({"ma": "kg", "ten": "kg"})
    with pytest.raises(DonViDoValidationError, match="E-DV-CAP-CONGTHUC"):
        svc.create_cap({"tu_id": to.id, "den_id": kg.id,
                        "cong_thuc": "dinh_luong * dai_in * rong_in"})
    # Cặp SỐ vẫn khai bình thường, và sửa cũng không cho lén nhét công thức vào.
    cap = svc.create_cap({"tu_id": to.id, "den_id": kg.id, "he_so": 0.039})
    with pytest.raises(DonViDoValidationError, match="E-DV-CAP-CONGTHUC"):
        svc.update_cap(cap.id, {"tu_id": to.id, "den_id": kg.id, "he_so": 0.039,
                                "cong_thuc": "dinh_luong * dai_in * rong_in"})


def test_xoa_don_vi_thi_cap_cua_no_di_theo(svc):
    """Cặp mồ côi trỏ vào đơn vị đã xoá là đường đi MA — máy vẫn tính ra số mà không ai hiểu."""
    tan, kg = _bo_ba(svc)
    svc.delete(tan.id)
    assert svc.repo.cap_rows() == []


# --- Cờ "dùng làm đơn vị tốc độ" --------------------------------------------
#
# Ô "Đơn vị tốc độ" bên màn Máy lọc theo cờ này. Trước 03/08/2026 nó đổ CẢ danh mục ra — 17 dòng,
# quá nửa vô nghĩa với máy (g/giờ, thùng/giờ, tấn/giờ…), chủ soi ra ngay.


def test_don_vi_moi_mac_dinh_KHONG_phai_don_vi_toc_do(svc):
    """Bảng dùng chung kho/khoán/mua hàng ⇒ đơn vị mới thêm chưa chắc là tốc độ máy. Mặc định TẮT,
    người dùng tự bật — bật sẵn là danh sách lại rác dần theo thời gian."""
    dv = svc.create({"ma": "thung_go", "ten": "thùng gỗ"})
    assert dv.dung_lam_toc_do is False


def test_bat_va_go_co_toc_do(svc):
    dv = svc.create({"ma": "cuon", "ten": "cuộn", "dung_lam_toc_do": True})
    assert dv.dung_lam_toc_do is True
    dv = svc.update(dv.id, {"ma": "cuon", "ten": "cuộn", "dung_lam_toc_do": False})
    assert dv.dung_lam_toc_do is False


def test_GO_khoi_danh_sach_toc_do_KHONG_xoa_don_vi(svc):
    """⭐ Chốt quan trọng nhất của tính năng này.

    Nút "×" bên màn Máy chỉ BỎ CỜ. Nếu một ngày ai đó đấu nó vào `delete` cho "gọn", xoá `kg` để
    khuất mắt "kg/giờ" sẽ kéo theo mọi cặp quy đổi của kg ⇒ gãy tồn kho và TIỀN KHOÁN. Test này
    canh đúng việc đơn vị phải SỐNG SÓT sau khi gỡ."""
    kg = svc.create({"ma": "kg", "ten": "kg", "ho": "khoi_luong", "dung_lam_toc_do": True})
    tan = svc.create({"ma": "tan", "ten": "tấn", "ho": "khoi_luong"})
    svc.create_cap({"tu_id": tan.id, "den_id": kg.id, "he_so": 1000})

    svc.update(kg.id, {"ma": "kg", "ten": "kg", "ho": "khoi_luong", "dung_lam_toc_do": False})

    con_lai = svc.get(kg.id)
    assert con_lai is not None and con_lai.active is True, "go co ma mat don vi"
    assert con_lai.dung_lam_toc_do is False
    caps, _tong = svc.list_cap()
    assert any(c.tu_ma == "tan" and c.den_ma == "kg" for c in caps), "go co ma mat cap quy doi"
