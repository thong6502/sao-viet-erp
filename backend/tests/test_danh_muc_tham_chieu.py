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
from app.models.bu_hao import BuHao
from app.models.cong_doan import CongDoan
from app.models.don_vi_do import DonViDo
from app.models.khuon_be import KhuonBe
from app.models.loai_san_pham import LoaiSanPham
from app.models.department import Department
from app.models.may_thiet_bi import MayThietBi
from app.models.piece_work import PieceRate
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
    to = Department(name="ZZ Tổ mẫu", code="ZZTOM", la_san_xuat=True)
    db.add_all([cl, dv, to])
    db.commit()
    rows = {
        "cong_doan": CongDoan(ma="ZZCD", ten="ZZ Công đoạn", nhom="finishing"),
        "don_vi_do": dv,
        "bu_hao": BuHao(ma="ZZBH", ten="ZZ Bù hao"),
        "khuon_be": KhuonBe(ma="ZZKB", ten="ZZ Khuôn"),
        "loai_san_pham": LoaiSanPham(ma="ZZSP", ten="ZZ SP", structural_type="flat"),
        # Nhóm máy đặt tên RIÊNG: `_may_thiet_bi` chặn khi đây là máy CUỐI của nhóm mà có
        # công đoạn chỉ cho phép nhóm đó. Lấy tên thật ("Máy in") là mẫu tự chặn chính mình.
        "may_thiet_bi": MayThietBi(ma="ZZMAY", ten="ZZ Máy", loai_may="ZZ Nhóm riêng"),
        "chung_loai_giay": cl,
        "giay": GiayNguyen(ma="ZZG", ten="ZZ Giấy", chung_loai_giay_id=cl.id, gsm=100),
        "vat_tu": VatTuInAn(ma="ZZVT", ten="ZZ Vật tư"),
        # Công việc khoán (17/08/2026): cùng bảng `piece_rates` mà Lương khoán tra.
        "cong_viec_khoan": PieceRate(group_name="ZZ Tổ mẫu", department_id=to.id,
                                     ma="ZZKH", ten="ZZ Việc khoán", unit="zzkg", unit_price=100),
    }
    db.add_all([v for k, v in rows.items() if k not in ("don_vi_do", "chung_loai_giay")])
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


def test_bu_hao_bi_cong_doan_giu_lai(db):
    rows = _mau(db)
    rows["cong_doan"].bu_hao_id = rows["bu_hao"].id
    db.commit()
    tc = tham_chieu(db, "bu_hao", rows["bu_hao"])
    assert tc.chan == ["1 công đoạn tra mã này"], tc.chan


def test_chung_loai_giay_bi_giay_con_giu_lai(db):
    rows = _mau(db)
    tc = tham_chieu(db, "chung_loai_giay", rows["chung_loai_giay"])
    assert not tc.xoa_han_duoc, "giấy ZZG đang trỏ về chủng loại này"


def test_cascade_bao_bang_SO_chu_khong_chan(db):
    """Xoá công đoạn là bay định mức đầu việc theo (CASCADE thật ở DB). Không chặn, nhưng phải
    nói bằng số trước khi bấm — đó là dữ liệu khai tay, không hoàn tác được."""
    from app.models.cong_doan import CongDoanDauViec

    rows = _mau(db)
    to = Department(name="ZZ Tổ", code="ZZTO", la_san_xuat=True)
    db.add(to)
    db.commit()
    rate = PieceRate(group_name="ZZ Tổ", department_id=to.id, ten="ZZ đầu việc",
                     unit="cái", unit_price=1)
    db.add(rate)
    db.commit()
    db.add(CongDoanDauViec(cong_doan_id=rows["cong_doan"].id, piece_rate_id=rate.id,
                           nang_suat_nguoi_gio=100, so_nguoi_tieu_chuan=1, so_nguoi_toi_da=2))
    db.commit()

    tc = tham_chieu(db, "cong_doan", rows["cong_doan"])
    assert tc.xoa_han_duoc, "định mức là con CASCADE, không phải nơi-đang-dùng ⇒ không chặn"
    assert tc.keo_theo == ["1 định mức đầu việc"], tc.keo_theo
