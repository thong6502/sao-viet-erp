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


def test_chips_noi_ro_manh_nao_la_cong_thuc(svc):
    """Màn danh sách tô màu theo `loai` server trả, KHÔNG tự đoán từ chữ.

    Ca thật 14/08/2026: "bài in = Tờ vào máy + 2000" hiện xám y như một hệ số cố định, vì màn hình
    đoán "đây là công thức" bằng cách dò tên biến (`dinh_luong`, `dai`…) và dấu `×` — mà tên biến
    đã được server đổi sang nhãn tiếng Việt, còn công thức này thì chỉ có dấu `+`.
    """
    bai = svc.create({"ma": "bai", "ten": "bài in", "cong_thuc": "to_dau_vao + 2000"})
    met = svc.create({"ma": "m", "ten": "mét"})
    svc.create_cap({"tu_id": bai.id, "den_id": met.id, "he_so": 65})

    chips = svc.quy_doi_chips(bai)
    assert [c["loai"] for c in chips] == ["cong_thuc", "co_dinh"]
    assert chips[0]["text"] == "bài in = Tờ vào máy + 2000"
    assert chips[1]["text"] == "1 bài in = 65 mét"
    # Chuỗi phẳng giữ nguyên hình dạng cũ — nhật ký và tooltip vẫn đọc nó.
    assert svc.quy_doi_text(bai) == "bài in = Tờ vào máy + 2000 · 1 bài in = 65 mét"


def test_chips_cua_don_vi_MUON_cong_thuc_cung_la_cong_thuc(svc):
    """`g` mượn công thức của `kg` qua cầu tĩnh — mảnh đó vẫn phải là `cong_thuc`, không phải hệ số."""
    kg = svc.create({"ma": "kg", "ten": "kg", "cong_thuc": "sl_ra * 200"})
    g = svc.create({"ma": "g", "ten": "g"})
    svc.create_cap({"tu_id": kg.id, "den_id": g.id, "he_so": 1000})

    chips = svc.quy_doi_chips(g)
    assert chips[0]["loai"] == "cong_thuc"
    assert "theo kg" in chips[0]["text"]


# --- cách đo của chính đơn vị (thay chỗ quy đổi động đã gỡ) ---------------------
#
# 🔴 Bảy ca test của QUY ĐỔI ĐỘNG gỡ 14/08/2026 cùng cơ chế (mg `0198`):
#     `test_luu_duoc_dong_cong_thuc` · `test_chan_bien_la_trong_cong_thuc`
#     `test_dong_cong_thuc_khong_bi_chan_mau_thuan` · `test_moi_don_vi_chi_mot_cong_thuc_ra_no`
#     `test_sua_chinh_dong_cong_thuc_khong_tu_chan`
#     `test_canh_bao_hai_cong_thuc_cung_dich_cho_du_lieu_cu`
#     `test_canh_bao_cap_so_co_dinh_de_len_duong_cong_thuc` · `test_khong_canh_bao_cap_cung_loai_do`
#
# Chúng kiểm cặp-mang-công-thức và hai cảnh báo chỉ tồn tại vì cặp đó. Cửa vào nay CHẶN
# (`test_cap_khong_nhan_cong_thuc_nua` ngay dưới), nên giữ chúng là test một tính năng không còn.
# Luật "một phép đo một công thức" KHÔNG mất — nó chuyển sang cụm đơn vị, xem
# `test_mot_CUM_TINH_chi_mot_cong_thuc_luong`.


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


def test_don_vi_mang_cach_do_cua_chinh_no(svc):
    """CÁCH ĐO (mg 0192): công thức ĐỊNH NGHĨA chính đơn vị, KHÔNG nối với đơn vị nào.

    Đây là nguồn số lượng của BOM, và từ 14/08/2026 là cách DUY NHẤT khai công thức cho đơn vị.
    Khác ô công thức ở Giấy · Vật tư khác · Công đoạn (`cong_thuc_gia`) — ô đó ra TIỀN.
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


# --- vòng đời -----------------------------------------------------------------


def test_don_vi_co_cong_thuc_hien_cong_thuc_va_KHONG_bao_chua_khai(svc):
    """Đơn vị TỰ TÍNH không cần cặp nào — cột "Quy đổi" phải in công thức, đừng bảo "chưa khai".

    Dính 13/08/2026: `kg_giay_to_in` khai công thức tử tế mà màn danh sách vẫn hiện "Chưa khai quy
    đổi" + cảnh báo vàng, vì cả hai chỗ chỉ nhìn bảng CẶP. Người khai nhìn vào tưởng chưa lưu được,
    rồi đi khai thêm một cặp không ai dùng cho hết cảnh báo.
    """
    dv = svc.create({"ma": "kg_giay_to_in", "ten": "kg giấy (theo tờ in)",
                     "ho": "khoi_luong",
                     "cong_thuc": "dinh_luong * dai_in * rong_in * to_dau_vao"})
    # Câu hiển thị đọc được bằng chữ, không phải mã biến trần.
    cau = svc.quy_doi_text(dv)
    # KHÔNG có "1 " — câu định nghĩa, không phải tỉ số.
    assert cau.startswith("kg giấy (theo tờ in) = ")
    assert "Định lượng giấy" in cau and "Tờ vào máy" in cau
    assert svc.canh_bao(dv) == [], "đơn vị tự tính không cần cặp — đừng báo chưa khai quy đổi"

    # Đơn vị THƯỜNG chưa khai gì thì vẫn phải nhắc như cũ.
    thung = svc.create({"ma": "thung_x", "ten": "thùng X"})
    assert svc.quy_doi_text(thung) == "Chưa khai quy đổi"
    assert svc.canh_bao(thung)


def test_mot_CUM_TINH_chi_mot_cong_thuc_luong(svc):
    """`kg · tấn · g` nối nhau bằng hằng số ⇒ MỘT phép đo ⇒ chỉ được MỘT công thức lượng.

    Hai công thức trong cùng cụm là hai số cho cùng một câu hỏi, và `_cach_do_lan` bên lệnh sẽ
    phải chọn bừa.
    """
    kg = svc.create({"ma": "kg", "ten": "kg", "ho": "khoi_luong",
                     "cong_thuc": "dinh_luong * dai_in * rong_in * to_dau_vao"})
    tan = svc.create({"ma": "tan", "ten": "tấn", "ho": "khoi_luong"})
    svc.create_cap({"tu_id": tan.id, "den_id": kg.id, "he_so": 1000})

    with pytest.raises(DonViDoValidationError, match="E-DV-BOM-TRUNG"):
        svc.update(tan.id, {"ma": "tan", "ten": "tấn", "ho": "khoi_luong",
                            "cong_thuc": "so_luong * 2"})
    # Sửa ở chính đơn vị đang giữ công thức thì KHÔNG bị chặn.
    svc.update(kg.id, {"ma": "kg", "ten": "kg", "ho": "khoi_luong", "cong_thuc": "so_luong * 3"})


def test_khong_co_cap_noi_thi_to_va_kg_deu_duoc_co_cong_thuc(svc):
    """`tờ` đếm tờ giấy, `kg` cân khối lượng — hai PHÉP ĐO khác nhau, mỗi cái một công thức.

    Luật "một cụm một công thức" chỉ bó trong CỤM (đơn vị nối nhau bằng hệ số cố định). Trước
    14/08/2026 hai đơn vị này nối bằng cạnh ĐỘNG và test kiểm rằng cạnh động không gộp cụm; nay
    không có cạnh nào nối chúng nữa, nhưng kết luận phải giữ y nguyên — gộp là chặn oan.
    """
    to = svc.create({"ma": "to", "ten": "tờ", "ho": "to", "cong_thuc": "to_dau_vao"})
    kg = svc.create({"ma": "kg", "ten": "kg", "ho": "khoi_luong"})
    svc.update(kg.id, {"ma": "kg", "ten": "kg", "ho": "khoi_luong",
                       "cong_thuc": "dinh_luong * dai_in * rong_in * to_dau_vao"})
    assert svc.get(kg.id).cong_thuc and svc.get(to.id).cong_thuc


def test_noi_cau_TINH_gop_hai_cong_thuc_thi_CHAN(svc):
    """Chiều NGƯỢC: hai đơn vị đã có công thức rồi mới nối cầu tĩnh ⇒ cụm mới có hai ⇒ chặn.

    Không có luật này thì chỉ cần khai ngược thứ tự là lọt.
    """
    kg = svc.create({"ma": "kg", "ten": "kg", "ho": "khoi_luong", "cong_thuc": "so_luong"})
    ta = svc.create({"ma": "ta", "ten": "tạ", "ho": "khoi_luong", "cong_thuc": "so_luong * 2"})
    with pytest.raises(DonViDoValidationError, match="E-DV-BOM-TRUNG"):
        svc.create_cap({"tu_id": ta.id, "den_id": kg.id, "he_so": 100})


def test_chan_chip_sl_vao_khi_don_vi_dang_la_dau_ra_cua_buoc_ngoai_dong(svc):
    """Chiều NGƯỢC của luật vòng tròn: sửa công thức đơn vị thêm `sl_vao` sau khi đã khai công đoạn.

    Không có nó thì khai ngược thứ tự là lọt — khai công đoạn trước, rồi mới thêm chip.
    """
    from app.models.cong_doan import CongDoan

    kem = svc.create({"ma": "kem", "ten": "bản kẽm", "ho": "kem", "cong_thuc": "so_kem"})
    svc.repo.db.add(CongDoan(ma="CD-CTP", ten="Ghi kẽm CTP", nhom="prepress",
                             don_vi_vao="kem", don_vi_ra="kem"))
    svc.repo.db.commit()

    with pytest.raises(DonViDoValidationError, match="E-DV-VONG-TRON"):
        svc.update(kem.id, {"ma": "kem", "ten": "bản kẽm", "ho": "kem",
                            "cong_thuc": "sl_vao * 2"})


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
