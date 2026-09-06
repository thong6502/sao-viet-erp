"""Bốn công thức mới đọc ĐÚNG chỗ mới (06/09/2026).

Xem plan `docs/superpowers/plans/2026-09-06-doi-cong-thuc-ve-cong-doan.md`: cách đo lượng của bước
chuyển từ MÁY / ĐẦU VIỆC KHOÁN / VẬT TƯ về màn CÔNG ĐOẠN, vì cả ba câu hỏi ("chạy trên máy này
bằng bao nhiêu", "việc này khoán theo lượng nào", "món này ăn bao nhiêu") đều đổi theo công đoạn.
"""
from __future__ import annotations

from app.models.cong_doan import CongDoan, CongDoanMay
from app.models.may_thiet_bi import MayThietBi

from tests.test_lsx_service import (  # noqa: F401 — fixture dùng chung
    admin, customer, db, lsx_svc, orders,
)


def test_gio_chay_doc_cong_thuc_cua_cap_cong_doan_va_may(db, orders, lsx_svc, admin, customer):
    """Cùng một máy, hai công đoạn ⇒ hai cách đo khác nhau. Đó là lý do bảng nối ra đời."""
    cd = CongDoan(ma="CD-G1", ten="In khổ nhỏ", nhom="print", don_vi_vao="to", don_vi_ra="to")
    may = MayThietBi(ma="MAY-G1", ten="Komori 5 màu", loai_may="Máy in",
                     toc_do=6000, don_vi_toc_do="to_gio")
    db.add_all([cd, may])
    db.flush()
    cd.may_lam_duoc.append(CongDoanMay(may_id=may.id, cong_thuc_gio="sl_vao * so_mau / 2",
                                       thu_tu=0))
    db.commit()

    class _Buoc:
        loai_buoc = "may"
        cong_doan_id = cd.id
        may_id = may.id
        so_luong_vao = 1000
        so_luong_ra = 1000
        don_vi_vao = "to"
        don_vi_ra = "to"
        so_luot_chay = 1
        khoan_json = None

    got = lsx_svc.sl_tinh_cua_buoc(_Buoc(), may, {"so_mau": 5})
    assert got is not None
    assert round(got[0]) == 2500, "1000 tờ × 5 màu ÷ 2 = 2500 lượt"


def test_may_khong_nam_trong_danh_sach_cong_doan_thi_lui_ve_cau_quy_doi(
        db, orders, lsx_svc, admin, customer):
    """Không khai cặp ⇒ không có công thức riêng ⇒ hành vi y như ô để trống hôm nay."""
    cd = CongDoan(ma="CD-G2", ten="Bế", nhom="finishing", don_vi_vao="to", don_vi_ra="to")
    may = MayThietBi(ma="MAY-G2", ten="Yawa 1050", loai_may="Bế",
                     toc_do=4000, don_vi_toc_do="to_gio")
    db.add_all([cd, may])
    db.commit()

    class _Buoc:
        loai_buoc = "may"
        cong_doan_id = cd.id
        may_id = may.id
        so_luong_vao = 800
        so_luong_ra = 800
        don_vi_vao = "to"
        don_vi_ra = "to"
        so_luot_chay = 1
        khoan_json = None

    got = lsx_svc.sl_tinh_cua_buoc(_Buoc(), may, {})
    assert got is not None and round(got[0]) == 800, "cùng đơn vị ⇒ cầu quy đổi trả nguyên số"


def test_anh_chup_dau_viec_lay_cong_thuc_tu_dinh_muc_cua_cong_doan():
    """Ảnh chụp ghim CÔNG THỨC CỦA CÔNG ĐOẠN, không phải của bảng đơn giá khoán."""
    from types import SimpleNamespace

    from app.services.piece_work_service import khoan_snapshot

    rate = SimpleNamespace(id=7, ten="In offset", unit="to", unit_price=120)
    dm = SimpleNamespace(cong_thuc_khoan="sl_vao * so_luot_chay")

    assert "cong_thuc" not in khoan_snapshot(rate)
    assert khoan_snapshot(rate, dm)["cong_thuc"] == "sl_vao * so_luot_chay"


def test_hai_vat_tu_cung_kg_trong_mot_dau_viec_an_theo_hai_cach(db, orders, lsx_svc, admin,
                                                                customer):
    """Mực ăn theo SỐ TỜ, dung môi rửa máy ăn theo SỐ MÀU — đúng ca đã bàn với chủ dự án."""
    from types import SimpleNamespace

    from app.models.cong_doan import CongDoanDauViec, CongDoanDauViecVatTu
    from app.models.vat_lieu_kho import VatTuInAn

    cd = CongDoan(ma="CD-G5", ten="In offset khổ nhỏ", nhom="print",
                  don_vi_vao="to", don_vi_ra="to")
    muc = VatTuInAn(ma="VT-MUC-C", ten="Mực offset Cyan", don_vi_gia="kg", active=True)
    dm_moi = VatTuInAn(ma="VT-DM-01", ten="Dung môi rửa máy in", don_vi_gia="kg", active=True)
    db.add_all([cd, muc, dm_moi])
    db.flush()

    dv = CongDoanDauViec(cong_doan_id=cd.id, piece_rate_id=1,
                         nang_suat_nguoi_gio=100, so_nguoi_tieu_chuan=2)
    dv.vat_tus.append(CongDoanDauViecVatTu(
        vat_tu_id=muc.id, thu_tu=0, cong_thuc_luong="sl_vao / 40000"))
    dv.vat_tus.append(CongDoanDauViecVatTu(
        vat_tu_id=dm_moi.id, thu_tu=1, cong_thuc_luong="so_mau * 0.3"))
    db.add(dv)
    db.commit()

    buoc = SimpleNamespace(so_luong_vao=5000, so_luong_ra=5000, so_luot_chay=1)
    ra, canh_bao = lsx_svc._vat_tu_bung(dv, buoc, {"so_mau": 4})

    theo_ma = {r["ma"]: r["so_luong"] for r in ra}
    assert theo_ma["VT-MUC-C"] == 0.125, "5.000 tờ ÷ 40.000 = 0,125 kg"
    assert theo_ma["VT-DM-01"] == 1.2, "4 màu × 0,3 = 1,2 kg — KHÔNG dính số tờ"
    assert canh_bao == []


def test_dong_vat_tu_chua_khai_cong_thuc_thi_bo_ra_kem_ly_do(db, orders, lsx_svc, admin, customer):
    """KHÔNG ĐOÁN: thà người kế hoạch tự thêm còn hơn bung một con số sai trông như thật."""
    from types import SimpleNamespace

    from app.models.cong_doan import CongDoanDauViec, CongDoanDauViecVatTu
    from app.models.vat_lieu_kho import VatTuInAn

    cd = CongDoan(ma="CD-G6", ten="Vào gáy", nhom="finishing",
                  don_vi_vao="to", don_vi_ra="cai")
    keo = VatTuInAn(ma="VT-KEO-9", ten="Keo vào gáy", don_vi_gia="kg", active=True)
    db.add_all([cd, keo])
    db.flush()
    dv = CongDoanDauViec(cong_doan_id=cd.id, piece_rate_id=1,
                         nang_suat_nguoi_gio=100, so_nguoi_tieu_chuan=1)
    dv.vat_tus.append(CongDoanDauViecVatTu(vat_tu_id=keo.id, thu_tu=0, cong_thuc_luong=None))
    db.add(dv)
    db.commit()

    ra, canh_bao = lsx_svc._vat_tu_bung(
        dv, SimpleNamespace(so_luong_vao=100, so_luong_ra=100, so_luot_chay=1), {})
    assert ra == []
    assert len(canh_bao) == 1 and "Keo vào gáy" in canh_bao[0]


def test_cong_thuc_gia_cua_may_ghi_de_cua_cong_doan(db):
    """Máy 5 màu khổ lớn và máy 2 màu khổ nhỏ có đơn giá khác nhau — nên giá phải theo máy."""
    from app.services.tinh_gia_service import _cong_doan_to_dict

    cd = CongDoan(ma="CD-P1", ten="In AB", nhom="print", cong_thuc_gia="to_dau_vao * 300")
    db.add(cd)
    db.commit()

    assert _cong_doan_to_dict(cd)["cong_thuc_gia"] == "to_dau_vao * 300"
    assert _cong_doan_to_dict(cd, ct_gia_may="to_dau_vao * 180")["cong_thuc_gia"] \
        == "to_dau_vao * 180"
    # Cặp có dòng nhưng ô công thức để TRỐNG ⇒ vẫn dùng công thức chung, không về rỗng.
    assert _cong_doan_to_dict(cd, ct_gia_may="")["cong_thuc_gia"] == "to_dau_vao * 300"


def test_buoc_to_van_bao_so_luot_chay_mac_dinh_mot():
    """Chủ chốt 06/09/2026: "mặc định là 1 cái số lượt qua máy ấy cho dù chọn loại bước là tổ".

    Trước đó `thoi_luong_buoc` ép `None` cho bước tổ, nên chip `so_luot_chay` trong công thức tiền
    công không có số nào để thế — mà tiền công thì CHỈ tính ở bước tổ.
    """
    from types import SimpleNamespace

    from app.services.lsx_service import thoi_luong_buoc

    to = SimpleNamespace(
        loai_buoc="to", so_luot_chay=2, nang_suat=100, so_nhan_cong=2,
        so_nhan_cong_tieu_chuan=2, phat_sinh_phut=0, so_luong_vao=1000,
        don_vi_vao="to", khoan_json={})
    dg = thoi_luong_buoc(to, None, (1000.0, "to", ""))["dien_giai"]
    assert dg["so_luot_chay"] == 2

    to.so_luot_chay = None      # chưa khai ⇒ hiểu là 1, không phải "không có"
    assert thoi_luong_buoc(to, None, (1000.0, "to", ""))["dien_giai"]["so_luot_chay"] == 1


def test_so_luot_KHONG_nhan_vao_gio_cua_buoc_to():
    """Khoá lại quyết định 06/09/2026: nhánh tổ giữ nguyên công thức, KHÔNG nhân lượt.

    Nhánh máy `_chay` có `× luot`, nhánh tổ `_chay_to` thì không. Đổi nhánh tổ là làm mọi bước tổ
    đang có đổi giờ ngay lần deploy kế — ngoài phạm vi. Số lượt ở bước tổ chỉ đi vào TIỀN CÔNG.
    """
    from types import SimpleNamespace

    from app.services.lsx_service import thoi_luong_buoc

    def _phut(luot):
        to = SimpleNamespace(
            loai_buoc="to", so_luot_chay=luot, nang_suat=100, so_nhan_cong=1,
            so_nhan_cong_tieu_chuan=1, phat_sinh_phut=0, so_luong_vao=1000,
            don_vi_vao="to", khoan_json={})
        return thoi_luong_buoc(to, None, (1000.0, "to", ""))["chiem_may_phut"]

    assert _phut(2) == _phut(1), "bước tổ: đổi số lượt KHÔNG đổi giờ"
