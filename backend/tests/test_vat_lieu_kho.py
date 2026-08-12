"""Danh mục Giấy & Vật tư — CRUD chủng loại / giấy / vật tư (phẳng).

Model mới: `VatTuInAn` gộp phẳng (bỏ `Muc`/`BanKem` cũ); `GiayNguyen` ăn theo 1 Chủng loại
(`chung_loai_giay_id`, soft int). Self-contained in-memory DB.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
import app.models  # noqa: F401 — đăng ký metadata mọi bảng
from app.models.vat_lieu_kho import ChungLoaiGiay, GiayNguyen, VatTuInAn  # noqa: F401
from app.models.don_vi_do import DonViDo, DonViQuyDoi
from app.repositories.don_vi_do_repo import DonViDoRepository
from app.repositories.vat_lieu_kho_repo import VatLieuKhoRepository
from app.services.vat_lieu_kho_service import (
    VatLieuKhoDuplicate,
    VatLieuKhoService,
    VatLieuKhoValidationError,
)

# Đơn vị + cặp quy đổi tối thiểu. Từ 2026-08-08 đơn vị của mặt hàng phải là mã CÓ THẬT trong
# `don_vi_do` (không còn enum cứng), nên DB test phải có sẵn danh mục đơn vị.
_DV = [("kg", "kg", "khoi_luong"), ("g", "g", "khoi_luong"), ("tan", "tấn", "khoi_luong"),
       ("to", "tờ", "to"), ("ram", "ram", "to"), ("m2", "m²", "dien_tich"),
       ("thung", "thùng", "thung"), ("kem", "bản kẽm", "kem")]
_CAP = [("kg", "g", 1000, None), ("tan", "kg", 1000, None), ("ram", "to", 500, None),
        ("to", "kg", 0, "dinh_luong * dai * rong"), ("to", "m2", 0, "dai * rong")]


def _svc():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    ids = {}
    for ma, ten, ho in _DV:
        d = DonViDo(ma=ma, ten=ten, ho=ho)
        db.add(d)
        db.flush()
        ids[ma] = d.id
    for tu, den, hs, ct in _CAP:
        db.add(DonViQuyDoi(tu_id=ids[tu], den_id=ids[den], he_so=hs, cong_thuc=ct))
    db.commit()
    return db, VatLieuKhoService(VatLieuKhoRepository(db), DonViDoRepository(db))


def test_chung_loai_giay_crud():
    db, svc = _svc()
    c = svc.create("chung_loai_giay", dict(ma="COUCHE", ten="Couché", be_mat="bong"))
    assert c.id and c.ma == "COUCHE"
    with pytest.raises(VatLieuKhoValidationError):            # bề mặt sai
        svc.create("chung_loai_giay", dict(ma="X", ten="x", be_mat="xyz"))


def test_giay_crud_and_validate():
    db, svc = _svc()
    cl = svc.create("chung_loai_giay", dict(ma="COUCHE", ten="Couché"))
    g = svc.create("giay", dict(ma="C300", ten="Couché 300", chung_loai_giay_id=cl.id,
                                kho_dai=860, kho_rong=650, gsm=300, don_vi_gia="kg", don_gia=30000))
    assert g.id and g.ma == "C300" and g.gsm == 300 and g.chung_loai_giay_id == cl.id
    with pytest.raises(VatLieuKhoValidationError):            # thiếu chủng loại
        svc.create("giay", dict(ma="Y", ten="y", kho_dai=860, kho_rong=650, gsm=150))
    with pytest.raises(VatLieuKhoValidationError):            # gsm <= 0
        svc.create("giay", dict(ma="X", ten="x", chung_loai_giay_id=cl.id, kho_dai=860, kho_rong=650, gsm=0))
    with pytest.raises(VatLieuKhoDuplicate):
        svc.create("giay", dict(ma="C300", ten="khác", chung_loai_giay_id=cl.id, kho_dai=650, kho_rong=860, gsm=150))


def test_vat_tu_flat_crud():
    db, svc = _svc()
    v = svc.create("vat_tu", dict(ma="MUC-CMYK", ten="Mực process CMYK", don_vi_gia="kg",
                                  don_gia=8000, ghi_chu="4 màu"))
    assert v.id and v.ma == "MUC-CMYK" and v.don_gia == 8000
    with pytest.raises(VatLieuKhoValidationError):            # ĐVT sai
        svc.create("vat_tu", dict(ma="X", ten="x", don_vi_gia="xyz"))
    with pytest.raises(VatLieuKhoDuplicate):
        svc.create("vat_tu", dict(ma="MUC-CMYK", ten="khác"))


# --- đơn vị lấy từ danh mục Đơn vị & quy đổi ----------------------------------


def test_don_vi_phai_co_trong_danh_muc():
    """Mã lạ thì mọi quy đổi của món đó tắt lặng lẽ (đồ thị không có nút ấy) — chặn ngay lúc khai
    thay vì để tồn kho lệch rồi mới đi tìm."""
    db, svc = _svc()
    with pytest.raises(VatLieuKhoValidationError) as e:
        svc.create("vat_tu", dict(ma="X", ten="x", don_vi_gia="ban"))
    assert "Đơn vị & quy đổi" in str(e.value)


def test_don_vi_de_trong_van_luu_duoc():
    """"Chưa chọn đơn vị" là trạng thái THẬT — hàng cũ có mã lạ bị xoá trắng chờ người khai chọn,
    không được chặn họ lưu những sửa đổi khác."""
    db, svc = _svc()
    v = svc.create("vat_tu", dict(ma="X", ten="x"))
    assert v.don_vi_gia is None


def test_khong_con_quy_cach_dong_goi_o_danh_muc():
    """Quy cách đóng gói ĐÃ BỎ (10/08/2026): quy đổi chỉ khai ở danh mục Đơn vị & quy đổi.

    Gửi kèm hai field cũ cũng không được ghi — repo lọc theo whitelist, không có đường vòng.
    """
    db, svc = _svc()
    v = svc.create("vat_tu", dict(ma="KEO", ten="Keo", don_vi_gia="kg",
                                  don_vi_dong_goi="thung", he_so_dong_goi=3))
    assert not hasattr(v, "don_vi_dong_goi") and not hasattr(v, "he_so_dong_goi")


# --- hai cửa dùng chung cho Kho + NCC -----------------------------------------


def _giay_couche_150(db, svc, don_vi="kg"):
    cl = svc.create("chung_loai_giay", dict(ma="COUCHE", ten="Couché"))
    g = svc.create("giay", dict(ma="GY001", ten="Couché 150 65×86", chung_loai_giay_id=cl.id,
                                gsm=150, don_vi_gia=don_vi))
    g.kho_dai, g.kho_rong = 860, 650      # seed có ghi khổ; kho KHÔNG dùng tới (xem test dưới)
    db.commit()
    return g


def test_tim_mat_hang_gop_ca_hai_danh_muc():
    db, svc = _svc()
    _giay_couche_150(db, svc)
    svc.create("vat_tu", dict(ma="KEO", ten="Keo vào gáy", don_vi_gia="kg"))
    ra = svc.tim_mat_hang()
    assert {r["hang_loai"] for r in ra} == {"giay", "vat_tu"}
    assert {r["nhom"] for r in ra} == {"Giấy", "Vật tư khác"}


def test_tim_mat_hang_bo_qua_hang_ngung_dung():
    """Siết mà vẫn chọn được hàng đã ngừng dùng thì siết cũng như không."""
    db, svc = _svc()
    v = svc.create("vat_tu", dict(ma="CU", ten="Hàng cũ", don_vi_gia="kg"))
    svc.update("vat_tu", v.id, dict(ma="CU", ten="Hàng cũ", active=False))
    assert not [r for r in svc.tim_mat_hang() if r["ma"] == "CU"]


def test_giay_don_vi_kg_thi_chi_dem_theo_can():
    """Chủ chốt 2026-08-08: giấy chỉ đếm theo kg — KHÔNG bơm khổ vào quy đổi.

    Dù bản ghi có sẵn `kho_dai`/`kho_rong` (seed ghi), kho vẫn không được mời nhập "10 ram": form
    danh mục Giấy không có ô khổ nên giấy người dùng tự tạo sẽ khổ = 0, bơm khổ vào thì hai giấy
    cùng màn cư xử khác nhau."""
    db, svc = _svc()
    g = _giay_couche_150(db, svc)
    ra = svc.don_vi_cua_mat_hang("giay", g.id)
    assert ra["don_vi_goc"] == "kg"
    ma = {d["ma"] for d in ra["ds"]}
    assert {"kg", "g", "tan"} <= ma
    assert "to" not in ma and "ram" not in ma and "m2" not in ma


def test_giay_muon_dem_theo_to_thi_chon_don_vi_goc_la_to():
    """Đường thoát KHÔNG cần khổ: đặt đơn vị gốc = `tờ` thì cặp SỐ CỐ ĐỊNH `1 ram = 500 tờ` chạy,
    kho nhập "10 ram" ra 5.000 tờ."""
    db, svc = _svc()
    g = _giay_couche_150(db, svc, don_vi="to")
    ram = next(d for d in svc.don_vi_cua_mat_hang("giay", g.id)["ds"] if d["ma"] == "ram")
    assert 10 * ram["he_so_ve_goc"] == pytest.approx(5_000)


def test_don_vi_cua_vat_tu_khong_kho_thi_khong_hien_to():
    """Keo chỉ khai kg → không có khổ để chạy cạnh động, KHÔNG được mời người ta nhập "10 tờ keo".

    Cũng không còn "thùng": muốn nhập theo thùng thì khai hẳn đơn vị đó ở danh mục Đơn vị &
    quy đổi, chứ không khai riêng lẻ trong từng mặt hàng nữa.
    """
    db, svc = _svc()
    v = svc.create("vat_tu", dict(ma="KEO", ten="Keo", don_vi_gia="kg"))
    ra = svc.don_vi_cua_mat_hang("vat_tu", v.id)
    ma = {d["ma"] for d in ra["ds"]}
    assert {"kg", "g", "tan"} <= ma
    assert "to" not in ma and "ram" not in ma and "thung" not in ma


def test_don_vi_chua_khai_thi_noi_ly_do_chu_khong_doan():
    db, svc = _svc()
    v = svc.create("vat_tu", dict(ma="X", ten="Chưa khai đơn vị"))
    ra = svc.don_vi_cua_mat_hang("vat_tu", v.id)
    assert ra["ds"] == [] and ra["don_vi_goc"] is None
    assert "chưa chọn đơn vị tính" in ra["ly_do"]


def test_list_filter_active():
    db, svc = _svc()
    cl = svc.create("chung_loai_giay", dict(ma="FORD", ten="Ford"))
    svc.create("giay", dict(ma="G1", ten="g1", chung_loai_giay_id=cl.id, kho_dai=860, kho_rong=650, gsm=150))
    svc.create("giay", dict(ma="G2", ten="g2", chung_loai_giay_id=cl.id, kho_dai=860, kho_rong=650,
                            gsm=200, active=False))
    rows, total = svc.list("giay", active=True)
    assert total == 1 and rows[0].ma == "G1"
