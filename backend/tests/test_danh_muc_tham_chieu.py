"""Bản đồ "ai đang dùng mục danh mục này" — nền của luồng xoá.

Test này canh hai thứ khác nhau:
  1. MỌI hàm đếm CHẠY ĐƯỢC trên schema thật. Bản đồ tham chiếu viết bằng tay từ đọc model — sai
     một tên cột là 500 ngay lúc người dùng bấm Xóa, mà đó là lúc tệ nhất để phát hiện.
  2. Đếm ĐÚNG: tham chiếu bằng CHUỖI MÃ (đơn vị) cũng phải ra số, không thì "xoá hẳn" tưởng an
     toàn trong khi thực tế cắt đứt thật.
"""
from __future__ import annotations

import pytest

from app.db import Base, SessionLocal, engine
from app.db_migrations import run_migrations
from app.models.cong_doan import CongDoan
from app.models.don_vi_do import DonViDo
from app.models.khuon_be import KhuonBe
from app.models.loai_san_pham import LoaiSanPham
from app.models.may_thiet_bi import MayThietBi
from app.models.san_xuat_kcs import SanXuatKcsTieuChi
from app.models.xe import Xe
from app.models.vat_lieu_kho import ChungLoaiGiay, GiayNguyen, VatTuInAn
from app.services.danh_muc_tham_chieu import DEM_THEO_LOAI, tham_chieu


@pytest.fixture
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    s = SessionLocal()
    run_migrations(s)
    yield s
    s.close()


def _mau(db):
    """Một bản ghi cho mỗi loại — DB trắng, chưa ai dùng gì."""
    cl = ChungLoaiGiay(ma="ZZCL", ten="ZZ Chủng loại")
    dv = DonViDo(ma="zzkg", ten="ZZ Ký")
    db.add_all([cl, dv])
    db.commit()
    # Công đoạn phải có ID TRƯỚC: hạng mục kiểm KCS neo vào nó (`cong_doan_id` NOT NULL, mg `0285`).
    cd = CongDoan(ma="ZZCD", ten="ZZ Công đoạn", nhom="finishing")
    db.add(cd)
    db.commit()
    rows = {
        "cong_doan": cd,
        "don_vi_do": dv,
        "khuon_be": KhuonBe(ma="ZZKB", ten="ZZ Khuôn"),
        "loai_san_pham": LoaiSanPham(ma="ZZSP", ten="ZZ SP", structural_type="flat"),
        # Nhóm máy đặt tên RIÊNG: `_may_thiet_bi` chặn khi đây là máy CUỐI của nhóm mà có
        # công đoạn chỉ cho phép nhóm đó. Lấy tên thật ("Máy in") là mẫu tự chặn chính mình.
        "may_thiet_bi": MayThietBi(ma="ZZMAY", ten="ZZ Máy", loai_may="ZZ Nhóm riêng"),
        "chung_loai_giay": cl,
        "giay": GiayNguyen(ma="ZZG", ten="ZZ Giấy", chung_loai_giay_id=cl.id, gsm=100),
        "vat_tu": VatTuInAn(ma="ZZVT", ten="ZZ Vật tư"),
        # Hạng mục kiểm KCS — không ai trỏ ngược về nó (mg `0285` gỡ bảng nối) ⇒ xoá hẳn được.
        "san_xuat_kcs_tieu_chi": SanXuatKcsTieuChi(ma="ZZTC", ten="ZZ Tiêu chí", cong_doan_id=cd.id),
        # Xe giao hàng (12/09/2026) — `_xe` đếm CHUYẾN đã chạy xe này. Xe mẫu chưa chạy chuyến nào
        # nên xoá hẳn được; bài `test_xe_da_chay_chuyen...` mới là chỗ kiểm vế bị chặn.
        "xe": Xe(ma="ZZ-XE", ten="ZZ Xe mẫu"),
    }
    db.add_all([v for k, v in rows.items()
                if k not in ("don_vi_do", "chung_loai_giay", "cong_doan")])
    db.commit()
    return rows


def test_moi_ham_dem_chay_duoc_tren_schema_that(db):
    """Chặn lỗi gõ nhầm tên cột/bảng trong bản đồ — nó chỉ lộ ra lúc người dùng bấm Xóa."""
    rows = _mau(db)
    assert set(rows) == set(DEM_THEO_LOAI), "bản đồ và mẫu test phải phủ cùng bộ danh mục"
    for loai, obj in rows.items():
        tc = tham_chieu(db, loai, obj)              # chạy được là điều kiện tối thiểu
        if loai == "chung_loai_giay":
            # Mẫu có sẵn một loại giấy trỏ về nó ⇒ bị chặn là ĐÚNG (xem test riêng dưới).
            continue
        assert tc.xoa_han_duoc, f"{loai}: chưa ai dùng mà vẫn báo bị chặn — {tc.chan}"


def test_loai_la_thi_khong_cho_xoa_han(db):
    """Không biết ai đang dùng thì KHÔNG cho xoá hẳn — thà bắt ngừng-dùng còn hơn xoá nhầm."""
    tc = tham_chieu(db, "khong_co_loai_nay", object())
    assert not tc.xoa_han_duoc and tc.chan


def test_dem_duoc_tham_chieu_bang_CHUOI_MA(db):
    """Công đoạn trỏ đơn vị bằng MÃ chứ không bằng id — đếm theo id sẽ ra 0 và xoá nhầm."""
    rows = _mau(db)
    dv = rows["don_vi_do"]
    cd = rows["cong_doan"]
    cd.don_vi_vao = "zzkg"
    db.commit()

    tc = tham_chieu(db, "don_vi_do", dv)
    assert not tc.xoa_han_duoc
    assert any("công đoạn" in c for c in tc.chan), tc.chan


def test_bu_hao_khong_con_la_mot_loai_danh_muc(db):
    """Bù hao GỠ 22/09/2026 (mg `0327`) — bậc về thẳng công đoạn, không còn mục nào để trỏ tới.

    Bản đồ tham chiếu mà vẫn nhận loại đã gỡ là mở một đường vào luồng xoá bằng khoá không ai khai.
    """
    assert "bu_hao" not in DEM_THEO_LOAI
    tc = tham_chieu(db, "bu_hao", _mau(db)["cong_doan"])
    assert tc.chan == ["chưa rà được nơi dùng của danh mục này"] and not tc.xoa_han_duoc


def test_chung_loai_giay_bi_giay_con_giu_lai(db):
    rows = _mau(db)
    tc = tham_chieu(db, "chung_loai_giay", rows["chung_loai_giay"])
    assert not tc.xoa_han_duoc, "giấy ZZG đang trỏ về chủng loại này"


def test_cascade_bao_bang_SO_chu_khong_chan(db):
    """Xoá công đoạn là bay tab VẬT TƯ của nó theo (CASCADE thật ở DB, mg `0316`). Không chặn,
    nhưng phải nói bằng số trước khi bấm — công thức định mức là dữ liệu khai tay, không hoàn tác."""
    from app.models.cong_doan import CongDoanVatTu

    rows = _mau(db)
    muc = VatTuInAn(ma="ZZMUC", ten="ZZ Mực", don_vi_gia="kg", don_gia=1)
    keo = VatTuInAn(ma="ZZKEO", ten="ZZ Keo", don_vi_gia="kg", don_gia=1)
    db.add_all([muc, keo])
    db.flush()
    db.add_all([
        CongDoanVatTu(cong_doan_id=rows["cong_doan"].id, vat_tu_id=muc.id, thu_tu=0,
                      cong_thuc_luong="sl_vao / 1000"),
        CongDoanVatTu(cong_doan_id=rows["cong_doan"].id, vat_tu_id=keo.id, thu_tu=1),
    ])
    db.commit()

    tc = tham_chieu(db, "cong_doan", rows["cong_doan"])
    assert tc.xoa_han_duoc, "dòng vật tư là con CASCADE, không phải nơi-đang-dùng ⇒ không chặn"
    assert tc.keo_theo == ["2 dòng vật tư định mức"], tc.keo_theo
