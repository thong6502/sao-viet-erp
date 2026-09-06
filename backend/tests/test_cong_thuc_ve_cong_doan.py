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
