"""Xếp lịch 3 — lớp service, chạy trên LUỒNG THẬT (đơn → chuyển SX → tạo lệnh → sẵn sàng).

Tái dùng nguyên bộ dựng nguồn của `test_xep_lich_service.py` thay vì chép lại: hai màn phải nhìn
CÙNG một hình dạng dữ liệu, chép ra là hai bản trôi nhau. Bám `docs/spec-xep-lich-3.md` §4.1
(ranh giới hiệu năng), §5 (màn), §6 (API).
"""
from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy import event

from app.repositories.audit_repo import AuditLogRepository
from app.repositories.xep_lich_lenh_repo import XepLichLenhRepository
from app.services.xep_lich_3 import XepLich3Conflict, XepLich3NotFound, XepLich3Service

# Fixtures + helper dùng lại — import tên vào module này là pytest nhận luôn thành fixture.
from tests.test_xep_lich_service import (  # noqa: F401
    _hai_lsx_san_sang,
    _khai_giay_len_buoc_in,
    admin,
    customer,
    db,
    lsx_svc,
    orders,
)


@pytest.fixture
def svc3(db):
    return XepLich3Service(db, XepLichLenhRepository(db), AuditLogRepository(db))


@pytest.fixture
def lenh(db, orders, lsx_svc, admin, customer):
    """Một lệnh SẴN SÀNG có routing thật + giấy khai trên bước in (nếu không, giờ chạy = 0)."""
    ds = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    _khai_giay_len_buoc_in(db, ds[0].id)
    db.commit()
    return ds[0]


@pytest.fixture
def hai_lenh(db, orders, lsx_svc, admin, customer):
    ds = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    for l in ds:
        _khai_giay_len_buoc_in(db, l.id)
    db.commit()
    return ds


# ============================================================== đọc

def test_hang_cho_chua_lenh_san_sang_chua_co_moc(svc3, lenh):
    ds = svc3.hang_cho()
    assert lenh.id in [d["lsx_id"] for d in ds["dong"]]


def test_the_hang_cho_mang_du_so_de_nguoi_quyet(svc3, lenh):
    d = [x for x in svc3.hang_cho()["dong"] if x["lsx_id"] == lenh.id][0]
    for k in ("ma", "ten", "customer_name", "han_hoan_thanh_sx", "is_rush",
              "so_to_ke_hoach", "chay_phut", "so_buoc"):
        assert k in d, f"thieu khoa {k}"
    assert d["chay_phut"] > 0, "routing co buoc may ma gio chay = 0"


def test_dat_moc_xong_thi_roi_hang_cho(svc3, lenh):
    svc3.dat_moc(lenh.id, datetime(2026, 9, 11, 8, 0))
    assert lenh.id not in [d["lsx_id"] for d in svc3.hang_cho()["dong"]]


def test_hang_cho_phan_trang_o_may_chu(svc3, hai_lenh):
    ds = svc3.hang_cho(trang=1, cd_trang=1)
    assert len(ds["dong"]) == 1
    assert ds["tong"] >= 2                      # tổng là SAU lọc, không phải số dòng trả về


def test_hang_cho_tim_o_may_chu(svc3, lenh):
    ds = svc3.hang_cho(tim=lenh.ma)
    assert [d["lsx_id"] for d in ds["dong"]] == [lenh.id]
    assert svc3.hang_cho(tim="KHONG-CO-MA-NAY")["dong"] == []


def test_lich_chi_tra_lenh_CHAM_cua_so(svc3, lenh):
    """`lich()` bắt buộc cắt theo cửa sổ (§4.1) — không có đường trải cả lịch sử."""
    svc3.dat_moc(lenh.id, datetime(2026, 9, 11, 8, 0))
    trong = svc3.lich(tu=date(2026, 9, 10), den=date(2026, 9, 16))
    truoc = svc3.lich(tu=date(2026, 8, 1), den=date(2026, 8, 7))
    sau = svc3.lich(tu=date(2026, 12, 1), den=date(2026, 12, 7))
    assert [d["lsx_id"] for d in trong["dong"]] == [lenh.id]
    assert truoc["dong"] == [] and sau["dong"] == []


def test_dong_lich_mang_du_so_cho_thanh_hai_lop(svc3, lenh):
    svc3.dat_moc(lenh.id, datetime(2026, 9, 11, 8, 0))
    d = svc3.lich(tu=date(2026, 9, 10), den=date(2026, 9, 16))["dong"][0]
    assert d["ket_thuc"] >= d["bat_dau_at"]
    assert d["chay_phut"] > 0
    assert d["doan"] and all({"tu", "den", "buoc_index"} <= set(x) for x in d["doan"])
    tong = sum((x["den"] - x["tu"]).total_seconds() / 60 for x in d["doan"])
    assert tong == pytest.approx(d["chay_phut"], abs=0.5)


def test_thanh_dai_bang_gio_chay_cong_nghi_va_ngoai_ca(svc3, lenh):
    """Đây là toàn bộ mục tiêu của module — con số phải cộng đúng, không xấp xỉ."""
    d = svc3.dat_moc(lenh.id, datetime(2026, 9, 11, 8, 0))
    tong = (d["ket_thuc"] - d["bat_dau_at"]).total_seconds() / 60
    assert tong == pytest.approx(d["chay_phut"] + d["nghi_ngoai_ca_phut"], abs=0.5)


def test_chi_tiet_du_o_cua_panel(svc3, lenh):
    """Panel dưới — thiếu một khoá là FE nhận `undefined` mà không lỗi nào bật ra."""
    svc3.dat_moc(lenh.id, datetime(2026, 9, 11, 8, 0))
    ct = svc3.chi_tiet(lenh.id)
    for k in ("customer_name", "order_no", "customer_po_no", "sale_name", "so_luong_dat",
              "don_vi_tinh", "so_to_ke_hoach", "so_con", "han_hoan_thanh_sx", "han_giao_khach",
              "nguoi_phu_trach_ten", "luu_y_gui_xuong", "giay", "kho_in", "so_mau", "so_kem",
              "kip_chuan", "is_rush", "bat_dau_at", "ket_thuc", "chay_phut",
              "nghi_ngoai_ca_phut", "cong_doans"):
        assert k in ct, f"thieu khoa {k}"


def test_chi_tiet_lenh_chua_xep_van_mo_duoc(svc3, lenh):
    """Bấm thẻ hàng chờ cũng mở panel — chưa có lịch thì các ô lịch để trống, không nổ."""
    ct = svc3.chi_tiet(lenh.id)
    assert ct["bat_dau_at"] is None and ct["ket_thuc"] is None
    assert ct["cong_doans"]


def test_bang_cong_doan_KHONG_co_moc_tung_buoc(svc3, lenh):
    """§4: mốc từng bước là số THỪA ở màn cấp LỆNH — bốn chỗ khác cần thì lấy đường riêng."""
    svc3.dat_moc(lenh.id, datetime(2026, 9, 11, 8, 0))
    cd = svc3.chi_tiet(lenh.id)["cong_doans"][0]
    assert "bat_dau" not in cd and "ket_thuc" not in cd
    assert cd["mau_index"] in (0, 1, 2, 3)


def test_moc_tung_buoc_van_lay_duoc_qua_duong_rieng(svc3, lenh):
    svc3.dat_moc(lenh.id, datetime(2026, 9, 11, 8, 0))
    moc = svc3.moc_cong_doan([lenh.id])
    assert lenh.id in moc and moc[lenh.id]
    assert all(b.ket_thuc >= b.bat_dau for b in moc[lenh.id])


def test_lich_khong_N_cong_1_truy_van_routing(db, svc3, hai_lenh):
    """§4.1: routing cả lô nạp MỘT truy vấn, không hỏi từng lệnh."""
    for l in hai_lenh:
        svc3.dat_moc(l.id, datetime(2026, 9, 11, 8, 0))
    dem = {"n": 0}

    def _bat(conn, cur, stmt, params, ctx, many):
        s = stmt.strip().lower()
        if s.startswith("select") and "lsx_cong_doan" in s:
            dem["n"] += 1

    event.listen(db.get_bind(), "before_cursor_execute", _bat)
    try:
        svc3.lich(tu=date(2026, 9, 1), den=date(2026, 9, 30))
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", _bat)
    assert dem["n"] <= 2, f"N+1: {dem['n']} truy van routing cho {len(hai_lenh)} lenh"


# ============================================================== ghi

def test_dat_moc_lan_dau_tao_dong(svc3, lenh):
    r = svc3.dat_moc(lenh.id, datetime(2026, 9, 11, 8, 0))
    assert r["bat_dau_at"] == datetime(2026, 9, 11, 8, 0)
    assert r["ket_thuc"] > r["bat_dau_at"]
    assert r["da_doi"] is False and r["thong_bao"] is None


def test_dat_lai_thi_GHI_DE_khong_de_dong_thu_hai(db, svc3, lenh):
    from app.models.xep_lich_lenh import XepLichLenh

    a = svc3.dat_moc(lenh.id, datetime(2026, 9, 11, 8, 0))
    svc3.dat_moc(lenh.id, datetime(2026, 9, 14, 8, 0), a["updated_at"])
    assert db.query(XepLichLenh).filter_by(lsx_id=lenh.id).count() == 1


def test_moc_ngoai_gio_chay_thi_TU_DOI_va_bao(svc3, lenh):
    r = svc3.dat_moc(lenh.id, datetime(2026, 9, 13, 3, 0))   # CN, 03:00
    assert r["da_doi"] is True
    assert r["thong_bao"] and "dời" in r["thong_bao"]


def test_moc_da_doi_duoc_LUU_chu_khong_luu_moc_nguoi_tha(svc3, lenh):
    """Lưu mốc người thả thì mỗi lần đọc lại trượt thêm một nhát, thanh tự đi."""
    r = svc3.dat_moc(lenh.id, datetime(2026, 9, 13, 3, 0))
    lai = svc3.chi_tiet(lenh.id)
    assert lai["bat_dau_at"] == r["bat_dau_at"]


def test_nguoi_khac_vua_doi_thi_409(svc3, lenh):
    svc3.dat_moc(lenh.id, datetime(2026, 9, 11, 8, 0))
    with pytest.raises(XepLich3Conflict):
        svc3.dat_moc(lenh.id, datetime(2026, 9, 12, 8, 0), datetime(2020, 1, 1, 0, 0))


def test_khong_gui_chot_thi_van_ghi_duoc(svc3, lenh):
    """Đặt mốc lần đầu (kéo từ hàng chờ) không có gì để so — không được đòi chốt."""
    svc3.dat_moc(lenh.id, datetime(2026, 9, 11, 8, 0))
    assert svc3.dat_moc(lenh.id, datetime(2026, 9, 15, 8, 0))["bat_dau_at"].day == 15


def test_KHONG_CHAN_du_tre_han_sx(db, svc3, lenh):
    """§1: "KHÔNG CHẶN GÌ HẾT". Xếp xong sau hạn SX vẫn ghi được, chỉ để UI bày màu."""
    lenh.han_hoan_thanh_sx = date(2026, 9, 1)
    db.commit()
    r = svc3.dat_moc(lenh.id, datetime(2026, 9, 11, 8, 0))
    assert r["bat_dau_at"] is not None
    assert r["ket_thuc"].date() > lenh.han_hoan_thanh_sx


def test_xoa_moc_tra_lenh_ve_hang_cho(svc3, lenh):
    svc3.dat_moc(lenh.id, datetime(2026, 9, 11, 8, 0))
    svc3.xoa_moc(lenh.id)
    assert lenh.id in [d["lsx_id"] for d in svc3.hang_cho()["dong"]]


def test_xoa_moc_lenh_chua_xep_thi_404(svc3, lenh):
    with pytest.raises(XepLich3NotFound):
        svc3.xoa_moc(lenh.id)


def test_dat_moc_lenh_khong_ton_tai_thi_404(svc3):
    with pytest.raises(XepLich3NotFound):
        svc3.dat_moc(999_999, datetime(2026, 9, 11, 8, 0))
