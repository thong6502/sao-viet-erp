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
                          "cong_thuc": "dinh_luong * dai_in * rong_in"})
    assert float(cap.he_so) == 0          # số chỉ có lúc chạy, để 0 cho hỏng lộ ra ngay
    assert svc.quy_doi_text(to) == "1 tờ = Định lượng giấy × Dài tờ in × Rộng tờ in kg"


def test_chan_bien_la_trong_cong_thuc(svc):
    """Biến hệ thống không bơm được thì dòng đó nằm chết trong bảng — chặn ngay lúc khai."""
    to = svc.create({"ma": "to", "ten": "tờ"})
    kg = svc.create({"ma": "kg", "ten": "kg"})
    with pytest.raises(DonViDoValidationError) as e:
        svc.create_cap({"tu_id": to.id, "den_id": kg.id, "cong_thuc": "do_day * dai_in"})
    assert "do_day" in str(e.value)


def test_dong_cong_thuc_khong_bi_chan_mau_thuan(svc):
    """Dòng động chưa có giấy nào để thay biến nên KHÔNG so được với đường hằng — đừng chặn oan."""
    tan, kg = _bo_ba(svc)
    to = svc.create({"ma": "to", "ten": "tờ"})
    svc.create_cap({"tu_id": to.id, "den_id": kg.id, "cong_thuc": "dinh_luong * dai_in * rong_in"})
    # Cặp HẰNG vẫn bị chặn như cũ (tấn → g lệch với đường tấn → kg → g).
    g = svc.create({"ma": "g", "ten": "g"})
    svc.create_cap({"tu_id": kg.id, "den_id": g.id, "he_so": 1000})
    with pytest.raises(DonViDoValidationError):
        svc.create_cap({"tu_id": tan.id, "den_id": g.id, "he_so": 999_000})


def test_don_vi_mang_cach_do_cua_chinh_no(svc):
    """CÁCH ĐO (mg 0192): công thức ĐỊNH NGHĨA chính đơn vị, KHÔNG nối với đơn vị nào.

    Đây là nguồn số lượng của BOM. Khác hai thứ dễ nhầm: `don_vi_quy_doi.cong_thuc` nối HAI đơn vị,
    còn ô công thức ở Giấy · Vật tư khác · Công đoạn ra TIỀN. Ô này ra LƯỢNG và đứng một mình.
    """
    dv = svc.create({"ma": "m2_to_in", "ten": "m² tờ in",
                     "cong_thuc": "dai_in * rong_in * to_sau_in"})
    assert dv.cong_thuc == "dai_in * rong_in * to_sau_in"
    # Đơn vị thường không bắt buộc có cách đo.
    assert svc.create({"ma": "thung", "ten": "thùng"}).cong_thuc is None
    # Sửa được, và xoá trắng thì về None chứ không giữ chuỗi rỗng.
    assert svc.update(dv.id, {"ma": dv.ma, "ten": dv.ten, "cong_thuc": "  "}).cong_thuc is None
    # Biến lạ bị chặn ngay — để lọt thì cách đo nằm chết, mọi vật tư dùng đơn vị này im lặng ra 0.
    with pytest.raises(DonViDoValidationError, match="do_day"):
        svc.create({"ma": "hop_x", "ten": "hộp X", "cong_thuc": "do_day * dai_in"})


def test_moi_don_vi_chi_mot_cong_thuc_ra_no(svc):
    """MỖI ĐƠN VỊ CHỈ TÍNH RA BẰNG MỘT CÔNG THỨC — luật sinh ra cho BOM (12/08/2026).

    Vật tư khai ĐVT là kg thì lúc bung ở bước lệnh máy phải đổi số lượng bước sang kg. Hai công thức
    cùng ra kg là không có cách nào chọn, và chọn bừa nghĩa là số vật tư sai mà nhìn vẫn hợp lý.
    """
    to = svc.create({"ma": "to", "ten": "tờ"})
    to_ng = svc.create({"ma": "to_nguyen", "ten": "tờ nguyên"})
    kg = svc.create({"ma": "kg", "ten": "kg"})
    m2 = svc.create({"ma": "m2", "ten": "m²"})
    svc.create_cap({"tu_id": to.id, "den_id": kg.id,
                    "cong_thuc": "dinh_luong * dai_in * rong_in"})

    # Công thức thứ hai cùng ra kg → chặn, và nói rõ dòng nào đang chiếm chỗ.
    with pytest.raises(DonViDoValidationError) as e:
        svc.create_cap({"tu_id": to_ng.id, "den_id": kg.id,
                        "cong_thuc": "dinh_luong * dai_nguyen * rong_nguyen"})
    assert "kg" in str(e.value) and "tờ" in str(e.value)

    # Khác ĐÍCH thì vẫn khai được — `tờ` đi ra nhiều đường là chuyện bình thường.
    svc.create_cap({"tu_id": to.id, "den_id": m2.id, "cong_thuc": "dai_in * rong_in"})


def test_sua_chinh_dong_cong_thuc_khong_tu_chan(svc):
    """Sửa công thức của chính dòng đang có không được coi nó là 'dòng thứ hai'."""
    to = svc.create({"ma": "to", "ten": "tờ"})
    kg = svc.create({"ma": "kg", "ten": "kg"})
    cap = svc.create_cap({"tu_id": to.id, "den_id": kg.id,
                          "cong_thuc": "dinh_luong * dai_in * rong_in"})
    sua = svc.update_cap(cap.id, {"tu_id": to.id, "den_id": kg.id,
                                  "cong_thuc": "dinh_luong * dai_nguyen * rong_nguyen"})
    assert sua.cong_thuc == "dinh_luong * dai_nguyen * rong_nguyen"


def test_canh_bao_hai_cong_thuc_cung_dich_cho_du_lieu_cu(svc):
    """Dòng khai TRƯỚC luật vẫn nằm nguyên — chỉ nhắc, không tự dọn hộ."""
    from app.models.don_vi_do import DonViQuyDoi

    to = svc.create({"ma": "to", "ten": "tờ"})
    to_ng = svc.create({"ma": "to_nguyen", "ten": "tờ nguyên"})
    kg = svc.create({"ma": "kg", "ten": "kg"})
    svc.create_cap({"tu_id": to.id, "den_id": kg.id,
                    "cong_thuc": "dinh_luong * dai_in * rong_in"})
    # Ghi thẳng ORM = đúng cách seed/dữ liệu cũ vào DB, không qua cửa validate.
    svc.repo.db.add(DonViQuyDoi(tu_id=to_ng.id, den_id=kg.id, he_so=0,
                                cong_thuc="dinh_luong * dai_nguyen * rong_nguyen"))
    svc.repo.db.commit()
    svc._quen_cache()

    cb = " ".join(svc.canh_bao(kg))
    assert "2 công thức động cùng ra kg" in cb
    assert not any("công thức động cùng ra" in c for c in svc.canh_bao(to)), \
        "cảnh báo phải bám đơn vị ĐÍCH, không bám đơn vị nguồn"


def test_canh_bao_cap_so_co_dinh_de_len_duong_cong_thuc(svc):
    """`1 tờ = 1.000 g` (⇒ mọi tờ nặng 1 kg) là dữ liệu SAI đã lọt vào DB thật.

    `_kiem_mau_thuan` không bắt được vì nó chỉ so với đường HẰNG, mà tờ → kg là đường ĐỘNG. Không
    chặn (cạnh động có thể thiếu biến) nhưng PHẢI nhắc, không thì BFS chọn đường ngắn hơn là số cố
    định và mọi phép đổi tờ ↔ cân đều sai mà im lặng.
    """
    to = svc.create({"ma": "to", "ten": "tờ", "ho": "to"})
    kg = svc.create({"ma": "kg", "ten": "kg", "ho": "khoi_luong"})
    g = svc.create({"ma": "g", "ten": "g", "ho": "khoi_luong"})
    svc.create_cap({"tu_id": to.id, "den_id": kg.id, "cong_thuc": "dinh_luong * dai_in * rong_in"})
    svc.create_cap({"tu_id": kg.id, "den_id": g.id, "he_so": 1000})

    svc.create_cap({"tu_id": to.id, "den_id": g.id, "he_so": 1000})   # cặp rác — vẫn lưu được
    assert any("số cố định" in c for c in svc.canh_bao(to))


def test_khong_canh_bao_cap_cung_loai_do(svc):
    """"1 tấn = 1.000 kg" đúng với MỌI mặt hàng — cùng loại đo thì không bao giờ báo, kẻo cảnh báo
    nhiều tới mức không ai đọc nữa."""
    tan = svc.create({"ma": "tan", "ten": "tấn", "ho": "khoi_luong"})
    kg = svc.create({"ma": "kg", "ten": "kg", "ho": "khoi_luong"})
    to = svc.create({"ma": "to", "ten": "tờ", "ho": "to"})
    svc.create_cap({"tu_id": tan.id, "den_id": kg.id, "he_so": 1000})
    svc.create_cap({"tu_id": to.id, "den_id": kg.id, "cong_thuc": "dinh_luong * dai_in * rong_in"})
    assert not [c for c in svc.canh_bao(tan) if "số cố định" in c]
    assert not [c for c in svc.canh_bao(kg) if "số cố định" in c]


# --- vòng đời -----------------------------------------------------------------


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
